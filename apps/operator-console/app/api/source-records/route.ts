import { getDb } from "../../../db";
import { sourceRecords } from "../../../db/schema";
import { recordAuditEvent } from "../../../lib/audit";
import {
  actorFromRequest,
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  getBucket,
  problem,
  readBoundedRequestBody,
  RequestBodyError,
  sha256Digest,
} from "../../../lib/weather";

export async function POST(request: Request) {
  if (controlPlaneMode() !== "local-development") {
    return controlPlaneConfigurationProblem(request);
  }
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
        error.status === 413
          ? "urn:weather:problem:source-record-too-large"
          : "urn:weather:problem:invalid-request",
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
      "urn:weather:problem:invalid-source-record",
    );
  }

  const digest = await sha256Digest(payload);
  const objectKey = `source-records/${digest.slice(7, 9)}/${digest.slice(7)}`;
  const contentType =
    request.headers.get("content-type") ?? "application/octet-stream";
  await getBucket().put(objectKey, payload, {
    httpMetadata: { contentType },
    customMetadata: { digest },
  });

  const receivedAt = new Date().toISOString();
  const inserted = await getDb()
    .insert(sourceRecords)
    .values({
      digest,
      objectKey,
      byteLength: payload.byteLength,
      contentType,
      receivedAt,
      createdBy: actor,
    })
    .onConflictDoNothing({ target: sourceRecords.digest })
    .returning({ digest: sourceRecords.digest });

  await recordAuditEvent({
    actor,
    action: "source_record.retained",
    resourceType: "source_record",
    resourceId: digest,
    detail: { byteLength: payload.byteLength, objectKey },
  });

  return Response.json(
    {
      source_record_digest: digest,
      status: inserted.length > 0 ? "retained" : "already_retained",
      byte_length: payload.byteLength,
    },
    { status: inserted.length > 0 ? 201 : 200 },
  );
}
