import {
  GET as localGet,
  POST as localPost,
} from "../../observations/route";
import { recordAuditEventBestEffort } from "../../../../lib/audit";
import {
  actorFromRequest,
  adaptControlPlaneObservations,
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  ControlPlaneConfigurationError,
  deterministicObservationId,
  mappedJsonResponse,
  normalizeObservationInput,
  ObservationValidationError,
  problem,
  proxyToControlPlane,
  toControlPlaneObservation,
  type ObservationInput,
} from "../../../../lib/weather";

export async function GET(request: Request) {
  const mode = controlPlaneMode();
  if (mode === "local-development") return localGet(request);
  if (mode === "misconfigured") {
    return controlPlaneConfigurationProblem(request);
  }
  const upstream = await proxyToControlPlane(request, "/v1/observations");
  return upstream
    ? mappedJsonResponse(request, upstream, adaptControlPlaneObservations)
    : controlPlaneConfigurationProblem(request);
}

export async function POST(request: Request) {
  const mode = controlPlaneMode();
  if (mode === "local-development") return localPost(request);
  if (mode === "misconfigured") {
    return controlPlaneConfigurationProblem(request);
  }
  const actor = actorFromRequest(request);
  if (!actor) {
    return problem(
      request,
      401,
      "Authentication required",
      "Observation admission requires an authenticated workspace operator.",
      "urn:weather:problem:authentication-required",
    );
  }

  let input;
  try {
    const body = (await request.json()) as unknown;
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      throw new ObservationValidationError("A JSON object is required.");
    }
    input = normalizeObservationInput(body as ObservationInput);
  } catch (error) {
    if (error instanceof ObservationValidationError) {
      return problem(request, 422, "Invalid observation", error.message);
    }
    return problem(request, 400, "Invalid request", "A JSON body is required.");
  }

  const observationId = await deterministicObservationId(
    input.sourceDigest,
    input.decoderVersion,
    input.recordIndex,
  );
  const ingestionTime = new Date().toISOString();
  let upstream: Response;
  try {
    upstream = (await proxyToControlPlane(request, "/v1/observations", {
      actor,
      body: JSON.stringify(
        toControlPlaneObservation(input, observationId, ingestionTime),
      ),
      method: "POST",
      requireServiceAuth: true,
    })) as Response;
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
  if (upstream.ok) {
    const auditRecorded = await recordAuditEventBestEffort({
      actor,
      action: "observation.admitted",
      resourceType: "observation",
      resourceId: observationId,
      detail: {
        phenomenon: input.phenomenon,
        sourceDigest: input.sourceDigest,
        qualityDisposition: input.qualityDisposition,
        controlPlane: "remote-authoritative",
      },
    });
    if (!auditRecorded) upstream.headers.set("x-weather-edge-audit-status", "failed");
  }
  return upstream;
}
