import { and, desc, eq, ne } from "drizzle-orm";
import { getDb } from "../../../db";
import { auditEvents, observations, sourceRecords } from "../../../db/schema";
import { auditEventValues } from "../../../lib/audit";
import {
  actorFromRequest,
  deterministicObservationId,
  isFiniteNumber,
  isPhenomenon,
  problem,
  sha256Text,
  type QualityDisposition,
} from "../../../lib/weather";

type ObservationInput = {
  phenomenon?: unknown;
  value?: unknown;
  unit?: unknown;
  uncertainty?: unknown;
  longitude?: unknown;
  latitude?: unknown;
  observedAt?: unknown;
  qualityDisposition?: unknown;
  qualityFlags?: unknown;
  sourceId?: unknown;
  sourceDigest?: unknown;
  decoderVersion?: unknown;
  recordIndex?: unknown;
};

const dispositions = new Set<QualityDisposition>([
  "accept",
  "accept_with_flags",
  "quarantine",
]);

export async function GET(request: Request) {
  const url = new URL(request.url);
  const phenomenon = url.searchParams.get("phenomenon");
  const includeQuarantined =
    url.searchParams.get("include_quarantined") === "true";
  const conditions = [];
  if (phenomenon) conditions.push(eq(observations.phenomenon, phenomenon));
  if (!includeQuarantined) {
    conditions.push(ne(observations.qualityDisposition, "quarantine"));
  }

  const db = getDb();
  const rows = await db
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
  let payload: ObservationInput;
  try {
    payload = (await request.json()) as ObservationInput;
  } catch {
    return problem(request, 400, "Invalid request", "A JSON body is required.");
  }

  if (!isPhenomenon(payload.phenomenon)) {
    return problem(
      request,
      422,
      "Invalid observation",
      "phenomenon must use lowercase snake_case.",
    );
  }
  if (payload.value !== null && !isFiniteNumber(payload.value)) {
    return problem(
      request,
      422,
      "Invalid observation",
      "value must be a finite number or null.",
    );
  }
  if (
    typeof payload.unit !== "string" ||
    payload.unit.trim().length === 0 ||
    payload.unit.length > 24
  ) {
    return problem(
      request,
      422,
      "Invalid observation",
      "unit is required.",
    );
  }
  if (
    !isFiniteNumber(payload.longitude) ||
    payload.longitude < -180 ||
    payload.longitude > 180 ||
    !isFiniteNumber(payload.latitude) ||
    payload.latitude < -90 ||
    payload.latitude > 90
  ) {
    return problem(
      request,
      422,
      "Invalid observation",
      "Coordinates must be valid CRS84 longitude and latitude values.",
    );
  }
  const observedAt = new Date(String(payload.observedAt));
  if (Number.isNaN(observedAt.getTime())) {
    return problem(
      request,
      422,
      "Invalid observation",
      "observedAt must be an ISO 8601 timestamp.",
    );
  }
  if (
    typeof payload.qualityDisposition !== "string" ||
    !dispositions.has(payload.qualityDisposition as QualityDisposition)
  ) {
    return problem(
      request,
      422,
      "Invalid observation",
      "qualityDisposition must be accept, accept_with_flags, or quarantine.",
    );
  }
  const qualityFlags = Array.isArray(payload.qualityFlags)
    ? payload.qualityFlags.filter(
        (flag): flag is string => typeof flag === "string",
      )
    : [];
  if (
    payload.qualityDisposition === "accept" &&
    qualityFlags.length > 0
  ) {
    return problem(
      request,
      422,
      "Invalid observation",
      "Accepted observations cannot carry unresolved quality flags.",
    );
  }
  if (
    typeof payload.sourceDigest !== "string" ||
    !/^sha256:[a-f0-9]{64}$/.test(payload.sourceDigest)
  ) {
    return problem(
      request,
      422,
      "Invalid provenance",
      "A retained SHA-256 source record digest is required.",
    );
  }

  const db = getDb();
  const retained = await db
    .select({ digest: sourceRecords.digest })
    .from(sourceRecords)
    .where(eq(sourceRecords.digest, payload.sourceDigest))
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
  const decoderVersion =
    typeof payload.decoderVersion === "string" && payload.decoderVersion.trim()
      ? payload.decoderVersion.trim()
      : "site-json-adapter/1.0.0";
  const recordIndex =
    typeof payload.recordIndex === "number" &&
    Number.isInteger(payload.recordIndex) &&
    payload.recordIndex >= 0
      ? payload.recordIndex
      : 0;
  const id = await deterministicObservationId(
    payload.sourceDigest,
    decoderVersion,
    recordIndex,
  );
  const sourceId =
    typeof payload.sourceId === "string" && payload.sourceId.trim()
      ? payload.sourceId.trim()
      : "operator-input";
  const normalizedContent = {
    phenomenon: payload.phenomenon,
    value: payload.value,
    unit: payload.unit.trim(),
    uncertainty: isFiniteNumber(payload.uncertainty)
      ? payload.uncertainty
      : null,
    longitude: payload.longitude,
    latitude: payload.latitude,
    observedAt: observedAt.toISOString(),
    qualityDisposition: payload.qualityDisposition,
    qualityFlags: [...new Set(qualityFlags)].sort(),
    sourceId,
    sourceDigest: payload.sourceDigest,
    decoderVersion,
    recordIndex,
  };
  const contentDigest = await sha256Text(JSON.stringify(normalizedContent));
  const existing = await db
    .select({ contentDigest: observations.contentDigest })
    .from(observations)
    .where(eq(observations.id, id))
    .limit(1);
  if (
    existing.length > 0 &&
    existing[0].contentDigest &&
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
  if (existing.length > 0) {
    return Response.json(
      { observation_id: id, status: "already_accepted" },
      { status: 200 },
    );
  }
  const audit = await auditEventValues({
    actor,
    action: "observation.admitted",
    resourceType: "observation",
    resourceId: id,
    detail: {
      phenomenon: payload.phenomenon,
      sourceDigest: payload.sourceDigest,
      qualityDisposition: payload.qualityDisposition,
    },
  });
  await db.batch([
    db.insert(observations).values({
    id,
    phenomenon: payload.phenomenon,
    value: payload.value,
    unit: payload.unit.trim(),
    uncertainty: isFiniteNumber(payload.uncertainty)
      ? payload.uncertainty
      : null,
    longitude: payload.longitude,
    latitude: payload.latitude,
    observedAt: observedAt.toISOString(),
    ingestedAt: now,
    qualityDisposition: payload.qualityDisposition,
    qualityFlags: JSON.stringify([...new Set(qualityFlags)].sort()),
    sourceId,
    sourceDigest: payload.sourceDigest,
    decoderVersion,
    recordIndex,
    contentDigest,
    createdBy: actor,
    }),
    db
      .insert(auditEvents)
      .values(audit)
      .onConflictDoNothing({ target: auditEvents.id }),
  ]);

  return Response.json(
    { observation_id: id, status: "accepted", ingested_at: now },
    { status: 202 },
  );
}
