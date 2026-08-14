export const MAX_SOURCE_RECORD_BYTES = 8 * 1024 * 1024;

const OBSERVATION_ID_NAMESPACE = "aaea81f8-6c64-583a-98bc-941faf205ff2";
const AWARE_ISO_TIMESTAMP =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

const SAFE_RESPONSE_HEADERS = [
  "allow",
  "cache-control",
  "content-type",
  "etag",
  "last-modified",
  "retry-after",
  "www-authenticate",
  "x-request-id",
] as const;

export type QualityDisposition =
  | "accept"
  | "accept_with_flags"
  | "quarantine";

export type WeatherRuntimeEnv = {
  DB?: D1Database;
  BUCKET?: R2Bucket;
  CONTROL_PLANE_URL?: string;
  CONTROL_PLANE_TOKEN?: string;
  CONTROL_PLANE_MODE?: string;
};

export type ControlPlaneMode =
  | "remote-authoritative"
  | "local-development"
  | "misconfigured";

export type ObservationInput = {
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

export type NormalizedObservationInput = {
  phenomenon: string;
  value: number | null;
  unit: string;
  uncertainty: number | null;
  longitude: number;
  latitude: number;
  observedAt: string;
  qualityDisposition: QualityDisposition;
  qualityFlags: string[];
  sourceId: string;
  sourceDigest: string;
  decoderVersion: string;
  recordIndex: number;
};

export class RequestBodyError extends Error {
  readonly status: 400 | 413;

  constructor(status: 400 | 413, message: string) {
    super(message);
    this.status = status;
  }
}

export class ControlPlaneConfigurationError extends Error {}

export class ObservationValidationError extends Error {}

export function getRuntimeBindings(): WeatherRuntimeEnv {
  const runtime = globalThis as typeof globalThis & {
    __WEATHER_ENV__?: WeatherRuntimeEnv;
  };
  return runtime.__WEATHER_ENV__ ?? {};
}

export function controlPlaneMode(): ControlPlaneMode {
  const runtime = getRuntimeBindings();
  if (runtime.CONTROL_PLANE_URL?.trim()) return "remote-authoritative";
  return runtime.CONTROL_PLANE_MODE === "local-development"
    ? "local-development"
    : "misconfigured";
}

export function controlPlaneConfigurationProblem(request: Request) {
  return problem(
    request,
    503,
    "Control plane unavailable",
    "CONTROL_PLANE_URL is required unless CONTROL_PLANE_MODE is explicitly set to local-development.",
    "urn:weather:problem:control-plane-configuration",
  );
}

export function getBucket(): R2Bucket {
  const binding = getRuntimeBindings().BUCKET;
  if (!binding) {
    throw new Error("Weather source-record storage is unavailable.");
  }
  return binding;
}

export function problem(
  request: Request,
  status: number,
  title: string,
  detail: string,
  type = "about:blank",
) {
  return Response.json(
    {
      type,
      title,
      status,
      detail,
      instance: new URL(request.url).pathname,
    },
    {
      status,
      headers: { "content-type": "application/problem+json" },
    },
  );
}

export function actorFromRequest(request: Request) {
  const actor = request.headers.get("oai-authenticated-user-email")?.trim();
  return actor || null;
}

export async function sha256Digest(payload: ArrayBuffer) {
  const digest = await crypto.subtle.digest("SHA-256", payload);
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `sha256:${hex}`;
}

export async function sha256Text(value: string) {
  return sha256Digest(new TextEncoder().encode(value).buffer);
}

function uuidBytes(value: string) {
  const compact = value.replaceAll("-", "");
  if (!/^[0-9a-f]{32}$/i.test(compact)) {
    throw new Error("Invalid UUID value.");
  }
  return Uint8Array.from(
    compact.match(/.{2}/g) ?? [],
    (pair) => Number.parseInt(pair, 16),
  );
}

function formatUuid(bytes: Uint8Array) {
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function deterministicObservationId(
  sourceDigest: string,
  decoderVersion: string,
  recordIndex: number,
) {
  const namespace = uuidBytes(OBSERVATION_ID_NAMESPACE);
  const name = new TextEncoder().encode(
    `${sourceDigest}|${decoderVersion}|${recordIndex}`,
  );
  const input = new Uint8Array(namespace.length + name.length);
  input.set(namespace);
  input.set(name, namespace.length);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-1", input));
  const bytes = digest.slice(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return formatUuid(bytes);
}

export async function readBoundedRequestBody(
  request: Request,
  maximum = MAX_SOURCE_RECORD_BYTES,
) {
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    if (!/^\d+$/.test(contentLength)) {
      throw new RequestBodyError(400, "Invalid Content-Length header.");
    }
    const declaredLength = Number(contentLength);
    if (!Number.isSafeInteger(declaredLength)) {
      throw new RequestBodyError(400, "Invalid Content-Length header.");
    }
    if (declaredLength > maximum) {
      throw new RequestBodyError(
        413,
        `Source records are limited to ${maximum} bytes.`,
      );
    }
  }

  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (byteLength + value.byteLength > maximum) {
      await reader.cancel("source record size limit exceeded");
      throw new RequestBodyError(
        413,
        `Source records are limited to ${maximum} bytes.`,
      );
    }
    chunks.push(value);
    byteLength += value.byteLength;
  }
  const payload = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    payload.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return payload.buffer;
}

export function safeUpstreamResponseHeaders(source: Headers) {
  const safe = new Headers();
  for (const name of SAFE_RESPONSE_HEADERS) {
    const value = source.get(name);
    if (value !== null) safe.set(name, value);
  }
  const location = source.get("location");
  if (location !== null && (location === "/" || /^\/[^/\\]/.test(location))) {
    safe.set("location", location);
  }
  return safe;
}

export async function proxyToControlPlane(
  request: Request,
  upstreamPath: string,
  options: {
    actor?: string;
    body?: BodyInit | null;
    method?: string;
    requireServiceAuth?: boolean;
  } = {},
) {
  const runtime = getRuntimeBindings();
  const baseUrl = runtime.CONTROL_PLANE_URL?.trim().replace(/\/+$/, "");
  if (!baseUrl) return null;
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(`${baseUrl}${upstreamPath}`);
  upstreamUrl.search = incomingUrl.search;

  const headers = new Headers();
  for (const name of ["accept", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (options.actor) headers.set("x-weather-actor", options.actor);
  const token = runtime.CONTROL_PLANE_TOKEN?.trim();
  if (options.requireServiceAuth && (!token || token.length < 32)) {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_TOKEN is required for authoritative mutations.",
    );
  }
  if (token) headers.set("authorization", `Bearer ${token}`);

  const method = options.method ?? request.method;
  const response = await fetch(upstreamUrl, {
    method,
    headers,
    body:
      method === "GET" || method === "HEAD"
        ? undefined
        : options.body === undefined
          ? request.body
          : options.body,
    redirect: "manual",
  });
  return new Response(response.body, {
    status: response.status,
    headers: safeUpstreamResponseHeaders(response.headers),
  });
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string) {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string.`);
  }
  return value;
}

export function adaptControlPlaneObservations(payload: unknown) {
  if (!Array.isArray(payload)) {
    throw new Error("The control plane returned an invalid observation list.");
  }
  return {
    observations: payload.map((value) => {
      const item = record(value, "observation");
      const geometry = record(item.geometry, "observation.geometry");
      const provenance = record(item.provenance, "observation.provenance");
      const coordinates = geometry.coordinates;
      if (
        !Array.isArray(coordinates) ||
        !isFiniteNumber(coordinates[0]) ||
        !isFiniteNumber(coordinates[1])
      ) {
        throw new Error("The control plane returned invalid coordinates.");
      }
      const flags = item.quality_flags;
      if (!Array.isArray(flags) || !flags.every((flag) => typeof flag === "string")) {
        throw new Error("The control plane returned invalid quality flags.");
      }
      if (item.value !== null && !isFiniteNumber(item.value)) {
        throw new Error("The control plane returned an invalid observation value.");
      }
      if (
        item.uncertainty !== null &&
        item.uncertainty !== undefined &&
        (!isFiniteNumber(item.uncertainty) || item.uncertainty < 0)
      ) {
        throw new Error("The control plane returned invalid uncertainty.");
      }
      if (
        coordinates[0] < -180 ||
        coordinates[0] > 180 ||
        coordinates[1] < -90 ||
        coordinates[1] > 90
      ) {
        throw new Error("The control plane returned out-of-range coordinates.");
      }
      return {
        id: requiredString(item.observation_id, "observation_id"),
        phenomenon: requiredString(item.phenomenon, "phenomenon"),
        value: item.value,
        unit: requiredString(item.unit, "unit"),
        uncertainty:
          item.uncertainty === null || item.uncertainty === undefined
            ? null
            : item.uncertainty,
        longitude: coordinates[0],
        latitude: coordinates[1],
        observedAt: requiredString(item.observation_time, "observation_time"),
        ingestedAt: requiredString(item.ingestion_time, "ingestion_time"),
        qualityDisposition: requiredString(
          item.quality_disposition,
          "quality_disposition",
        ),
        qualityFlags: flags,
        sourceId: requiredString(provenance.source_id, "provenance.source_id"),
        sourceDigest: requiredString(
          provenance.source_record_digest,
          "provenance.source_record_digest",
        ),
        decoderVersion: requiredString(
          provenance.decoder_version,
          "provenance.decoder_version",
        ),
      };
    }),
  };
}

export function adaptControlPlaneModelCycles(payload: unknown) {
  if (!Array.isArray(payload)) {
    throw new Error("The control plane returned an invalid model-cycle list.");
  }
  return {
    cycles: payload.map((value) => {
      const item = record(value, "model cycle");
      const initializedAt = requiredString(item.initialized_at, "initialized_at");
      const availableFieldCount = Number(item.available_field_count ?? 0);
      const expectedFieldCount = Number(
        item.expected_field_count ??
          availableFieldCount + Number(item.missing_field_count ?? 0),
      );
      const modelId = requiredString(item.model_id, "model_id");
      const modelVersion = requiredString(item.model_version, "model_version");
      const sourceRevision = requiredString(item.source_revision, "source_revision");
      if (
        !Number.isInteger(availableFieldCount) ||
        availableFieldCount < 0 ||
        !Number.isInteger(expectedFieldCount) ||
        expectedFieldCount < availableFieldCount
      ) {
        throw new Error("The control plane returned invalid field counts.");
      }
      return {
        id:
          typeof item.id === "string"
            ? item.id
            : `${modelId}:${modelVersion}:${initializedAt}:${sourceRevision}`,
        modelId,
        modelVersion,
        guidanceOrigin: requiredString(item.guidance_origin, "guidance_origin"),
        initializedAt,
        sourceRevision,
        completeness: requiredString(item.completeness, "completeness"),
        availableFieldCount,
        expectedFieldCount,
        updatedAt:
          typeof item.updated_at === "string" ? item.updated_at : initializedAt,
      };
    }),
  };
}

export function adaptControlPlaneHealth(payload: unknown) {
  const item = record(payload, "health response");
  return {
    status: requiredString(item.status, "status"),
    version: requiredString(item.version, "version"),
    contract_version: "1.0.0",
    control_plane_mode: "remote-authoritative",
    environment:
      typeof item.environment === "string" ? item.environment : "unknown",
    telemetry_enabled: item.telemetry_enabled === true,
    external_egress_enabled: item.external_egress_enabled === true,
    persistence: {
      canonical_observations: null,
      retained_source_records: null,
      audit_events: null,
      structured_store: "authoritative",
      object_store: "authoritative",
    },
  };
}

export function adaptControlPlaneEdrCollections(payload: unknown) {
  const document = record(payload, "EDR collections response");
  if (!Array.isArray(document.collections)) {
    throw new Error("The control plane returned an invalid EDR collection list.");
  }
  return {
    ...document,
    collections: document.collections.map((value) => {
      const collection = record(value, "EDR collection");
      const dataQueries = record(collection.data_queries, "EDR data_queries");
      const position = record(dataQueries.position, "EDR position query");
      const link = record(position.link, "EDR position link");
      const href = requiredString(link.href, "EDR position href");
      return {
        ...collection,
        data_queries: {
          ...dataQueries,
          position: {
            ...position,
            link: {
              ...link,
              href: href.startsWith("/v1/edr/") ? `/api${href}` : href,
            },
          },
        },
      };
    }),
  };
}

export async function mappedJsonResponse(
  request: Request,
  response: Response,
  mapper: (payload: unknown) => unknown,
) {
  if (!response.ok) return response;
  try {
    const headers = safeUpstreamResponseHeaders(response.headers);
    headers.delete("content-type");
    headers.delete("etag");
    return Response.json(mapper(await response.json()), {
      status: response.status,
      headers,
    });
  } catch {
    return problem(
      request,
      502,
      "Invalid control-plane response",
      "The authoritative control plane returned an incompatible response.",
      "urn:weather:problem:control-plane-contract",
    );
  }
}

function invalidObservation(message: string): never {
  throw new ObservationValidationError(message);
}

export function normalizeObservationInput(
  payload: ObservationInput,
): NormalizedObservationInput {
  if (!isPhenomenon(payload.phenomenon)) {
    invalidObservation("phenomenon must use lowercase snake_case.");
  }
  if (payload.value !== null && !isFiniteNumber(payload.value)) {
    invalidObservation("value must be a finite number or null.");
  }
  const unit = typeof payload.unit === "string" ? payload.unit.trim() : "";
  if (!unit || unit.length > 24) invalidObservation("unit is required and must not exceed 24 characters.");
  if (
    payload.uncertainty !== undefined &&
    payload.uncertainty !== null &&
    (!isFiniteNumber(payload.uncertainty) || payload.uncertainty < 0)
  ) {
    invalidObservation("uncertainty must be a non-negative finite number or null.");
  }
  if (
    !isFiniteNumber(payload.longitude) ||
    payload.longitude < -180 ||
    payload.longitude > 180 ||
    !isFiniteNumber(payload.latitude) ||
    payload.latitude < -90 ||
    payload.latitude > 90
  ) {
    invalidObservation("Coordinates must be valid CRS84 longitude and latitude values.");
  }
  if (typeof payload.observedAt !== "string" || !AWARE_ISO_TIMESTAMP.test(payload.observedAt)) {
    invalidObservation("observedAt must be an ISO 8601 timestamp with a timezone.");
  }
  const observedAt = new Date(payload.observedAt);
  if (Number.isNaN(observedAt.getTime())) {
    invalidObservation("observedAt must be a valid ISO 8601 timestamp.");
  }
  const dispositions = new Set<QualityDisposition>([
    "accept",
    "accept_with_flags",
    "quarantine",
  ]);
  if (
    typeof payload.qualityDisposition !== "string" ||
    !dispositions.has(payload.qualityDisposition as QualityDisposition)
  ) {
    invalidObservation(
      "qualityDisposition must be accept, accept_with_flags, or quarantine.",
    );
  }
  const rawFlags = payload.qualityFlags ?? [];
  if (!Array.isArray(rawFlags) || !rawFlags.every((flag) => typeof flag === "string")) {
    invalidObservation("qualityFlags must be an array of strings.");
  }
  if (new Set(rawFlags).size !== rawFlags.length) {
    invalidObservation("qualityFlags must not contain duplicates.");
  }
  if (payload.qualityDisposition === "accept" && rawFlags.length > 0) {
    invalidObservation("Accepted observations cannot carry unresolved quality flags.");
  }
  if (
    typeof payload.sourceDigest !== "string" ||
    !/^sha256:[a-f0-9]{64}$/.test(payload.sourceDigest)
  ) {
    invalidObservation("A retained SHA-256 source record digest is required.");
  }
  const sourceId =
    typeof payload.sourceId === "string" && payload.sourceId.trim()
      ? payload.sourceId.trim()
      : "operator-input";
  const decoderVersion =
    typeof payload.decoderVersion === "string" && payload.decoderVersion.trim()
      ? payload.decoderVersion.trim()
      : "site-json-adapter/1.0.0";
  const recordIndex = payload.recordIndex ?? 0;
  if (!Number.isInteger(recordIndex) || Number(recordIndex) < 0) {
    invalidObservation("recordIndex must be a non-negative integer.");
  }
  return {
    phenomenon: payload.phenomenon,
    value: payload.value,
    unit,
    uncertainty:
      payload.uncertainty === undefined || payload.uncertainty === null
        ? null
        : payload.uncertainty,
    longitude: payload.longitude,
    latitude: payload.latitude,
    observedAt: observedAt.toISOString(),
    qualityDisposition: payload.qualityDisposition as QualityDisposition,
    qualityFlags: [...rawFlags].sort(),
    sourceId,
    sourceDigest: payload.sourceDigest,
    decoderVersion,
    recordIndex: Number(recordIndex),
  };
}

export function toControlPlaneObservation(
  input: NormalizedObservationInput,
  observationId: string,
  ingestionTime: string,
) {
  return {
    schema_version: "1.0.0",
    observation_id: observationId,
    phenomenon: input.phenomenon,
    value: input.value,
    unit: input.unit,
    uncertainty: input.uncertainty,
    trace: false,
    geometry: {
      type: "Point",
      coordinates: [input.longitude, input.latitude],
    },
    vertical_coordinate: null,
    observation_time: input.observedAt,
    ingestion_time: ingestionTime,
    quality_disposition: input.qualityDisposition,
    quality_flags: input.qualityFlags,
    provenance: {
      source_id: input.sourceId,
      source_record_digest: input.sourceDigest,
      digest_verification: "platform",
      ingested_at: ingestionTime,
      decoder_version: input.decoderVersion,
    },
  };
}

export function angularDistanceDegrees(
  lon1: number,
  lat1: number,
  lon2: number,
  lat2: number,
) {
  const radians = Math.PI / 180;
  const phi1 = lat1 * radians;
  const phi2 = lat2 * radians;
  const deltaLambda = (lon2 - lon1) * radians;
  const cosine =
    Math.sin(phi1) * Math.sin(phi2) +
    Math.cos(phi1) * Math.cos(phi2) * Math.cos(deltaLambda);
  return Math.acos(Math.min(1, Math.max(-1, cosine))) / radians;
}

export function longitudeRanges(
  longitude: number,
  latitude: number,
  withinDegrees: number,
) {
  const radians = Math.PI / 180;
  const latitudeRadians = latitude * radians;
  const radiusRadians = withinDegrees * radians;
  const reachesPole =
    Math.abs(latitudeRadians) + radiusRadians >= Math.PI / 2;
  const longitudeRadius = reachesPole
    ? 180
    : Math.asin(
        Math.min(
          1,
          Math.sin(radiusRadians) / Math.cos(latitudeRadians),
        ),
      ) / radians;
  if (longitudeRadius >= 180) return [[-180, 180]] as const;
  const minimum = longitude - longitudeRadius;
  const maximum = longitude + longitudeRadius;
  if (minimum < -180) {
    return [
      [minimum + 360, 180],
      [-180, maximum],
    ] as const;
  }
  if (maximum > 180) {
    return [
      [minimum, 180],
      [-180, maximum - 360],
    ] as const;
  }
  return [[minimum, maximum]] as const;
}

export function parseWktPoint(value: string) {
  const match = /^\s*POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)\s*$/i.exec(
    value,
  );
  if (!match) throw new Error("coords must be a WKT POINT(lon lat)");
  const longitude = Number(match[1]);
  const latitude = Number(match[2]);
  if (longitude < -180 || longitude > 180) {
    throw new Error("longitude must be in [-180, 180]");
  }
  if (latitude < -90 || latitude > 90) {
    throw new Error("latitude must be in [-90, 90]");
  }
  return { longitude, latitude };
}

export function parseDatetimeInterval(value: string | null) {
  if (!value) return { start: null, end: null };
  const parseBound = (bound: string) => {
    if (!bound || bound === "..") return null;
    if (!AWARE_ISO_TIMESTAMP.test(bound)) {
      throw new Error("datetime must use ISO 8601 timestamps with a timezone");
    }
    const date = new Date(bound);
    if (Number.isNaN(date.getTime())) {
      throw new Error("datetime must use valid ISO 8601 timestamps");
    }
    return date.toISOString();
  };
  if (!value.includes("/")) {
    const instant = parseBound(value);
    return { start: instant, end: instant };
  }
  const [rawStart, rawEnd] = value.split("/", 2);
  const start = parseBound(rawStart);
  const end = parseBound(rawEnd);
  if (start && end && end < start) {
    throw new Error("datetime interval end must not precede start");
  }
  return { start, end };
}

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function isPhenomenon(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[a-z][a-z0-9_]*$/.test(value) &&
    value.length <= 80
  );
}
