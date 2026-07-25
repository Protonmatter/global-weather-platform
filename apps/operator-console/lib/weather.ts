export const MAX_SOURCE_RECORD_BYTES = 8 * 1024 * 1024;

export type QualityDisposition =
  | "accept"
  | "accept_with_flags"
  | "quarantine";

type WeatherRuntimeEnv = {
  DB?: D1Database;
  BUCKET?: R2Bucket;
  CONTROL_PLANE_URL?: string;
};

export function getRuntimeBindings(): WeatherRuntimeEnv {
  const runtime = globalThis as typeof globalThis & {
    __WEATHER_ENV__?: WeatherRuntimeEnv;
  };
  return runtime.__WEATHER_ENV__ ?? {};
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
  return request.headers.get("oai-authenticated-user-email");
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

export async function deterministicObservationId(
  sourceDigest: string,
  decoderVersion: string,
  recordIndex: number,
) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(
      `${sourceDigest}\u0000${decoderVersion}\u0000${recordIndex}`,
    ),
  );
  const bytes = new Uint8Array(digest).slice(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function proxyToControlPlane(
  request: Request,
  upstreamPath: string,
) {
  const baseUrl = getRuntimeBindings().CONTROL_PLANE_URL?.replace(/\/+$/, "");
  if (!baseUrl) return null;
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(`${baseUrl}${upstreamPath}`);
  upstreamUrl.search = incomingUrl.search;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("cookie");
  const actor = actorFromRequest(request);
  if (actor) headers.set("x-weather-actor", actor);
  const response = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body:
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : request.body,
    redirect: "manual",
  });
  return new Response(response.body, {
    status: response.status,
    headers: response.headers,
  });
}

export function angularDistanceDegrees(
  lon1: number,
  lat1: number,
  lon2: number,
  lat2: number,
) {
  let deltaLongitude = Math.abs(lon1 - lon2) % 360;
  if (deltaLongitude > 180) deltaLongitude = 360 - deltaLongitude;
  return Math.sqrt(deltaLongitude ** 2 + Math.abs(lat1 - lat2) ** 2);
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
    const date = new Date(bound);
    if (Number.isNaN(date.getTime())) {
      throw new Error("datetime must use ISO 8601 timestamps");
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
