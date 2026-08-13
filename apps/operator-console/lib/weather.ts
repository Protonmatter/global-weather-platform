import {
  ControlPlaneConfigurationError,
  getRuntimeBindings,
  problem,
  type ControlPlaneMode,
  type WeatherRuntimeEnv,
} from "./weather-core.ts";

export * from "./weather-core.ts";

type OperationalRuntimeEnv = WeatherRuntimeEnv & {
  CONTROL_PLANE_ALLOWED_HOSTS?: string;
};

const SAFE_RESPONSE_HEADERS = [
  "cache-control",
  "content-type",
  "etag",
  "last-modified",
  "retry-after",
  "x-request-id",
] as const;

const DNS_HOSTNAME =
  /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

function operationalRuntime(): OperationalRuntimeEnv {
  return getRuntimeBindings() as OperationalRuntimeEnv;
}

function normalizeHostname(value: string) {
  return value.trim().toLowerCase().replace(/\.$/, "");
}

function isIpv4Literal(value: string) {
  const octets = value.split(".");
  return (
    octets.length === 4 &&
    octets.every((octet) => {
      if (!/^\d{1,3}$/.test(octet)) return false;
      const number = Number(octet);
      return number >= 0 && number <= 255;
    })
  );
}

function isIpLiteral(value: string) {
  const hostname = value.replace(/^\[/, "").replace(/\]$/, "");
  return hostname.includes(":") || isIpv4Literal(hostname);
}

function configuredAllowedHosts(runtime: OperationalRuntimeEnv) {
  const processValue =
    typeof process === "undefined"
      ? undefined
      : process.env.CONTROL_PLANE_ALLOWED_HOSTS;
  const raw = runtime.CONTROL_PLANE_ALLOWED_HOSTS ?? processValue ?? "";
  const hosts = raw
    .split(",")
    .map(normalizeHostname)
    .filter(Boolean);
  if (hosts.length === 0) {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL requires a non-empty CONTROL_PLANE_ALLOWED_HOSTS allowlist.",
    );
  }
  for (const hostname of hosts) {
    if (!DNS_HOSTNAME.test(hostname) || isIpLiteral(hostname)) {
      throw new ControlPlaneConfigurationError(
        "CONTROL_PLANE_ALLOWED_HOSTS must contain DNS hostnames only.",
      );
    }
  }
  return hosts;
}

function isLoopbackHostname(value: string) {
  const hostname = value.replace(/^\[/, "").replace(/\]$/, "").toLowerCase();
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function validateUrlShape(url: URL) {
  if (url.username || url.password) {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL must not contain user information.",
    );
  }
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL must identify an origin without a path, query, or fragment.",
    );
  }
}

export function validatedControlPlaneBaseUrl(): string | null {
  const runtime = operationalRuntime();
  const raw = runtime.CONTROL_PLANE_URL?.trim();
  if (!raw) return null;

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL must be a valid absolute URL.",
    );
  }
  validateUrlShape(url);

  if (
    runtime.CONTROL_PLANE_MODE === "local-development" &&
    isLoopbackHostname(url.hostname)
  ) {
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      throw new ControlPlaneConfigurationError(
        "CONTROL_PLANE_URL must use HTTP or HTTPS for loopback development.",
      );
    }
    return url.origin;
  }

  if (url.protocol !== "https:") {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL must use HTTPS outside loopback development.",
    );
  }

  const hostname = normalizeHostname(url.hostname);
  if (!DNS_HOSTNAME.test(hostname) || isIpLiteral(hostname)) {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL must use an approved DNS hostname, not an IP literal.",
    );
  }

  const allowedHosts = configuredAllowedHosts(runtime);
  if (
    !allowedHosts.some(
      (allowed) => hostname === allowed || hostname.endsWith(`.${allowed}`),
    )
  ) {
    throw new ControlPlaneConfigurationError(
      "CONTROL_PLANE_URL hostname is not in CONTROL_PLANE_ALLOWED_HOSTS.",
    );
  }
  return url.origin;
}

export function controlPlaneMode(): ControlPlaneMode {
  const runtime = operationalRuntime();
  if (!runtime.CONTROL_PLANE_URL?.trim()) {
    return runtime.CONTROL_PLANE_MODE === "local-development"
      ? "local-development"
      : "misconfigured";
  }
  try {
    validatedControlPlaneBaseUrl();
  } catch (error) {
    if (error instanceof ControlPlaneConfigurationError) return "misconfigured";
    throw error;
  }
  return "remote-authoritative";
}

export function controlPlaneConfigurationProblem(request: Request) {
  return problem(
    request,
    503,
    "Control plane unavailable",
    "CONTROL_PLANE_URL must identify an approved control-plane origin.",
    "urn:weather:problem:control-plane-configuration",
  );
}

export function safeUpstreamResponseHeaders(source: Headers) {
  const safe = new Headers();
  for (const name of SAFE_RESPONSE_HEADERS) {
    const value = source.get(name);
    if (value !== null) safe.set(name, value);
  }
  const location = source.get("location");
  if (location?.startsWith("/")) safe.set("location", location);
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
  const baseUrl = validatedControlPlaneBaseUrl();
  if (!baseUrl) return null;
  if (!upstreamPath.startsWith("/")) {
    throw new ControlPlaneConfigurationError(
      "Control-plane upstream paths must be absolute application paths.",
    );
  }

  const runtime = operationalRuntime();
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(upstreamPath, `${baseUrl}/`);
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
