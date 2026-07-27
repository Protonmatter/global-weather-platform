import { POST as localPost } from "../../source-records/route";
import { recordAuditEvent } from "../../../../lib/audit";
import {
  actorFromRequest,
  ControlPlaneConfigurationError,
  getRuntimeBindings,
  problem,
  proxyToControlPlane,
  readBoundedRequestBody,
  RequestBodyError,
  sha256Digest,
} from "../../../../lib/weather";

export async function POST(request: Request) {
  if (!getRuntimeBindings().CONTROL_PLANE_URL) return localPost(request);
  const actor = actorFromRequest(request);
  if (!actor) {
    return problem(
      request,
      401,
      "Authentication required",
      "Source-record retention requires an authenticated workspace operator.",
      "urn:weather:problem:authentication-required",
    );
  }

  let payload: ArrayBuffer;
  try {
    payload = await readBoundedRequestBody(request);
  } catch (error) {
    if (error instanceof RequestBodyError) {
      return problem(
        request,
        error.status,
        error.status === 413 ? "Payload too large" : "Invalid request",
        error.message,
      );
    }
    throw error;
  }
  if (payload.byteLength === 0) {
    return problem(
      request,
      422,
      "Invalid source record",
      "Source record payload must not be empty.",
    );
  }

  const digest = await sha256Digest(payload);
  let upstream: Response;
  try {
    upstream = (await proxyToControlPlane(
      request,
      `/v1/source-records/${digest}`,
      {
        actor,
        body: payload,
        method: "PUT",
        requireServiceAuth: true,
      },
    )) as Response;
  } catch (error) {
    if (error instanceof ControlPlaneConfigurationError) {
      return problem(
        request,
        503,
        "Control plane unavailable",
        error.message,
        "urn:weather:problem:control-plane-configuration",
      );
    }
    throw error;
  }
  if (!upstream.ok) return upstream;

  await recordAuditEvent({
    actor,
    action: "source_record.retained",
    resourceType: "source_record",
    resourceId: digest,
    detail: {
      byteLength: payload.byteLength,
      controlPlane: "remote-authoritative",
    },
  });
  return Response.json(
    {
      source_record_digest: digest,
      status: upstream.status === 201 ? "retained" : "already_retained",
      byte_length: payload.byteLength,
    },
    { status: upstream.status },
  );
}
