import { and, desc, gte, inArray, lte, ne, or } from "drizzle-orm";
import { getDb } from "../../../db";
import { observations } from "../../../db/schema";
import {
  angularDistanceDegrees,
  isPhenomenon,
  longitudeRanges,
  parseDatetimeInterval,
  problem,
} from "../../../lib/weather";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const longitude = Number(url.searchParams.get("longitude"));
  const latitude = Number(url.searchParams.get("latitude"));
  const withinDegrees = Number(url.searchParams.get("within_degrees") ?? "0.5");
  const rawPhenomena = url.searchParams.get("parameter_name");
  const limit = Number(url.searchParams.get("limit") ?? "1000");
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
  if (!Number.isInteger(limit) || limit < 1 || limit > 10_000) {
    return problem(
      request,
      400,
      "Invalid limit",
      "limit must be an integer between 1 and 10000.",
    );
  }

  const phenomena = rawPhenomena
    ?.split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  if (phenomena && (phenomena.length === 0 || phenomena.some((name) => !isPhenomenon(name)))) {
    return problem(
      request,
      400,
      "Invalid parameter name",
      "parameter_name must contain comma-separated canonical phenomenon names.",
    );
  }

  const conditions = [];
  if (phenomena) conditions.push(inArray(observations.phenomenon, phenomena));
  if (!includeQuarantined) {
    conditions.push(ne(observations.qualityDisposition, "quarantine"));
  }
  if (interval.start) {
    conditions.push(gte(observations.observedAt, interval.start));
  }
  if (interval.end) {
    conditions.push(lte(observations.observedAt, interval.end));
  }
  conditions.push(
    gte(observations.latitude, Math.max(-90, latitude - withinDegrees)),
    lte(observations.latitude, Math.min(90, latitude + withinDegrees)),
  );
  const ranges = longitudeRanges(longitude, latitude, withinDegrees);
  if (!(ranges.length === 1 && ranges[0][0] === -180 && ranges[0][1] === 180)) {
    conditions.push(
      or(
        ...ranges.map(([minimum, maximum]) =>
          and(
            gte(observations.longitude, minimum),
            lte(observations.longitude, maximum),
          ),
        ),
      )!,
    );
  }

  const features = [];
  const batchSize = 1000;
  let offset = 0;
  while (features.length < limit) {
    const rows = await getDb()
      .select()
      .from(observations)
      .where(and(...conditions))
      .orderBy(desc(observations.observedAt))
      .limit(batchSize)
      .offset(offset);
    for (const row of rows) {
      if (
        angularDistanceDegrees(
          longitude,
          latitude,
          row.longitude,
          row.latitude,
        ) > withinDegrees
      ) {
        continue;
      }
      features.push({
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
      });
      if (features.length >= limit) break;
    }
    offset += rows.length;
    if (rows.length < batchSize) break;
  }

  return Response.json({
    type: "FeatureCollection",
    numberReturned: features.length,
    query: {
      coords: `POINT(${longitude} ${latitude})`,
      within_degrees: withinDegrees,
      parameter_name: rawPhenomena,
      datetime: url.searchParams.get("datetime"),
    },
    features,
  });
}
