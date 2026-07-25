import { and, desc, eq, gte, lte, ne } from "drizzle-orm";
import { getDb } from "../../../db";
import { observations } from "../../../db/schema";
import {
  angularDistanceDegrees,
  parseDatetimeInterval,
  problem,
} from "../../../lib/weather";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const longitude = Number(url.searchParams.get("longitude"));
  const latitude = Number(url.searchParams.get("latitude"));
  const withinDegrees = Number(url.searchParams.get("within_degrees") ?? "2");
  const phenomenon = url.searchParams.get("parameter_name");
  const includeQuarantined =
    url.searchParams.get("include_quarantined") === "true";
  let interval: ReturnType<typeof parseDatetimeInterval>;
  try {
    interval = parseDatetimeInterval(url.searchParams.get("datetime"));
  } catch (error) {
    return problem(
      request,
      400,
      "Invalid datetime",
      error instanceof Error ? error.message : "Invalid datetime interval.",
    );
  }

  if (
    !Number.isFinite(longitude) ||
    longitude < -180 ||
    longitude > 180 ||
    !Number.isFinite(latitude) ||
    latitude < -90 ||
    latitude > 90
  ) {
    return problem(
      request,
      400,
      "Invalid position",
      "longitude and latitude must define a valid CRS84 position.",
    );
  }
  if (
    !Number.isFinite(withinDegrees) ||
    withinDegrees <= 0 ||
    withinDegrees > 45
  ) {
    return problem(
      request,
      400,
      "Invalid radius",
      "within_degrees must be greater than 0 and at most 45.",
    );
  }

  const conditions = [];
  if (phenomenon) conditions.push(eq(observations.phenomenon, phenomenon));
  if (!includeQuarantined) {
    conditions.push(ne(observations.qualityDisposition, "quarantine"));
  }
  if (interval.start) {
    conditions.push(gte(observations.observedAt, interval.start));
  }
  if (interval.end) {
    conditions.push(lte(observations.observedAt, interval.end));
  }

  const rows = await getDb()
    .select()
    .from(observations)
    .where(conditions.length ? and(...conditions) : undefined)
    .orderBy(desc(observations.observedAt))
    .limit(10_000);

  const features = rows
    .filter(
      (row) =>
        angularDistanceDegrees(
          longitude,
          latitude,
          row.longitude,
          row.latitude,
        ) <= withinDegrees,
    )
    .slice(0, 1_000)
    .map((row) => ({
      type: "Feature",
      id: row.id,
      geometry: {
        type: "Point",
        coordinates: [row.longitude, row.latitude],
      },
      properties: {
        phenomenon: row.phenomenon,
        value: row.value,
        unit: row.unit,
        uncertainty: row.uncertainty,
        quality_disposition: row.qualityDisposition,
        valid_time: row.observedAt,
        issued_at: row.ingestedAt,
        provenance: {
          source_id: row.sourceId,
          source_record_digest: row.sourceDigest,
          digest_verification: "platform",
          decoder_version: row.decoderVersion,
          ingested_at: row.ingestedAt,
        },
      },
    }));

  return Response.json({
    type: "FeatureCollection",
    numberReturned: features.length,
    query: {
      coords: `POINT(${longitude} ${latitude})`,
      within_degrees: withinDegrees,
      parameter_name: phenomenon,
      datetime: url.searchParams.get("datetime"),
    },
    features,
  });
}
