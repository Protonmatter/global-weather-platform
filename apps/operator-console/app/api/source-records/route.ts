import { eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { auditEvents, sourceRecords } from "../../../db/schema";
import { auditEventValues } from "../../../lib/audit";
import {
  actorFromRequest,
  getBucket,
  MAX_SOURCE_RECORD_BYTES,
  problem,
  sha256Digest,
} from "../../../lib/weather";

export async function POST(request: Request) {
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
  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (declaredLength > MAX_SOURCE_RECORD_BYTES) {
    return problem(
      request,
      413,
      "Payload too large",
      `Source records are limited to ${MAX_SOURCE_RECORD_BYTES} bytes.`,
      "urn:weather:problem:source-record-too-large",
    );
  }

  const payload = await request.arrayBuffer();
  if (payload.byteLength === 0) {
    return problem(
      request,
      422,
      "Invalid source record",
      "Source record payload must not be empty.",
      "urn:weather:problem:invalid-source-record",
    );
  }
  if (payload.byteLength > MAX_SOURCE_RECORD_BYTES) {
    return problem(
      request,
      413,
      "Payload too large",
      `Source records are limited to ${MAX_SOURCE_RECORD_BYTES} bytes.`,
      "urn:weather:problem:source-record-too-large",
    );
  }

  const digest = await sha256Digest(payload);
  const objectKey = `source-records/${digest.slice(7, 9)}/${digest.slice(7)}`;
  const db = getDb();
  const existing = await db
    .select({ digest: sourceRecords.digest })
    .from(sourceRecords)
    .where(eq(sourceRecords.digest, digest))
    .limit(1);

  if (existing.length === 0) {
    await getBucket().put(objectKey, payload, {
      httpMetadata: {
        contentType:
          request.headers.get("content-type") ?? "application/octet-stream",
      },
      customMetadata: { digest },
    });
    const receivedAt = new Date().toISOString();
    const audit = await auditEventValues({
      actor,
      action: "source_record.retained",
      resourceType: "source_record",
      resourceId: digest,
      detail: { byteLength: payload.byteLength, objectKey },
    });
    await db.batch([
      db.insert(sourceRecords).values({
        digest,
        objectKey,
        byteLength: payload.byteLength,
        contentType:
          request.headers.get("content-type") ?? "application/octet-stream",
        receivedAt,
        createdBy: actor,
      }),
      db
        .insert(auditEvents)
        .values(audit)
        .onConflictDoNothing({ target: auditEvents.id }),
    ]);
  }

  return Response.json(
    {
      source_record_digest: digest,
      status: existing.length === 0 ? "retained" : "already_retained",
      byte_length: payload.byteLength,
    },
    { status: existing.length === 0 ? 201 : 200 },
  );
}
