import { and, desc, eq, ne } from "drizzle-orm";
import { getDb } from "../../../db";
import { observations, sourceRecords } from "../../../db/schema";
import { recordAuditEvent } from "../../../lib/audit";
import {
  actorFromRequest,
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  deterministicObservationId,
  normalizeObservationInput,
  ObservationValidationError,
  problem,
  sha256Text,
  type NormalizedObservationInput,
  type ObservationInput,
} from "../../../lib/weather";

export async function GET(request: Request) {
  if (controlPlaneMode() !== "local-development") {
    return controlPlaneConfigurationProblem(request);
  }
  const url = new URL(request.url);
  const phenomenon = url.searchParams.get("phenomenon");
  const includeQuarantined =
    url.searchParams.get("include_quarantined") === "true";
  const conditions = [];
  if (phenomenon) conditions.push(eq(observations.phenomenon, phenomenon));
  if (!includeQuarantined) {
    conditions.push(ne(observations.qualityDisposition, "quarantine"));
  }

  const rows = await getDb()
    .select()
    .from(observations)
    .where(conditions.length ? and(...conditions) : undefined)
    .orderBy(desc(observations.observedAt))
    .limit(500);

  return Response.json({
    observations: rows.map((row) => ({
      ...row,
      qualityFlags: JSON.parse(row.qualityFlags) as string[],
    })),
  });
}

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
      "Observation admission requires an authenticated workspace operator.",
      "urn:weather:problem:authentication-required",
    );
  }

  let input: NormalizedObservationInput;
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

  const db = getDb();
  const retained = await db
    .select({ digest: sourceRecords.digest })
    .from(sourceRecords)
    .where(eq(sourceRecords.digest, input.sourceDigest))
    .limit(1);
  if (retained.length === 0) {
    return problem(
      request,
      422,
      "Invalid provenance",
      "Observation provenance must reference a retained source record.",
    );
  }

  const now = new Date().toISOString();
  const id = await deterministicObservationId(
    input.sourceDigest,
    input.decoderVersion,
    input.recordIndex,
  );
  const contentDigest = await sha256Text(JSON.stringify(input));
  const inserted = await db
    .insert(observations)
    .values({
      id,
      phenomenon: input.phenomenon,
      value: input.value,
      unit: input.unit,
      uncertainty: input.uncertainty,
      longitude: input.longitude,
      latitude: input.latitude,
      observedAt: input.observedAt,
      ingestedAt: now,
      qualityDisposition: input.qualityDisposition,
      qualityFlags: JSON.stringify(input.qualityFlags),
      sourceId: input.sourceId,
      sourceDigest: input.sourceDigest,
      decoderVersion: input.decoderVersion,
      recordIndex: input.recordIndex,
      contentDigest,
      createdBy: actor,
    })
    .onConflictDoNothing({ target: observations.id })
    .returning({ id: observations.id });

  if (inserted.length === 0) {
    const existing = await db
      .select({ contentDigest: observations.contentDigest })
      .from(observations)
      .where(eq(observations.id, id))
      .limit(1);
    if (
      existing.length === 0 ||
      existing[0].contentDigest !== contentDigest
    ) {
      return problem(
        request,
        409,
        "Observation conflict",
        `Observation ${id} conflicts with an existing canonical record.`,
        "urn:weather:problem:observation-conflict",
      );
    }
  }

  await recordAuditEvent({
    actor,
    action: "observation.admitted",
    resourceType: "observation",
    resourceId: id,
    detail: {
      phenomenon: input.phenomenon,
      sourceDigest: input.sourceDigest,
      qualityDisposition: input.qualityDisposition,
    },
  });

  return Response.json(
    {
      observation_id: id,
      status: inserted.length > 0 ? "accepted" : "already_accepted",
      ...(inserted.length > 0 ? { ingested_at: now } : {}),
    },
    { status: inserted.length > 0 ? 202 : 200 },
  );
}
