import { GET as localEdrPosition } from "../../../../../edr/route";
import {
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  parseWktPoint,
  problem,
  proxyToControlPlane,
} from "../../../../../../../lib/weather";

export async function GET(request: Request) {
  const mode = controlPlaneMode();
  if (mode === "misconfigured") {
    return controlPlaneConfigurationProblem(request);
  }
  const upstream = await proxyToControlPlane(
    request,
    "/v1/edr/collections/observations/position",
  );
  if (upstream) return upstream;
  if (mode !== "local-development") {
    return controlPlaneConfigurationProblem(request);
  }

  const incoming = new URL(request.url);
  const coords = incoming.searchParams.get("coords");
  if (!coords) {
    return problem(
      request,
      400,
      "Invalid position",
      "coords is required and must be a WKT POINT(lon lat).",
    );
  }
  let point: ReturnType<typeof parseWktPoint>;
  try {
    point = parseWktPoint(coords);
  } catch (error) {
    return problem(
      request,
      400,
      "Invalid position",
      error instanceof Error ? error.message : "Invalid WKT position.",
    );
  }
  const local = new URL(request.url);
  local.pathname = "/api/edr";
  local.searchParams.delete("coords");
  local.searchParams.set("longitude", String(point.longitude));
  local.searchParams.set("latitude", String(point.latitude));
  const parameterName = local.searchParams.get("parameter-name");
  if (parameterName) {
    local.searchParams.set("parameter_name", parameterName);
    local.searchParams.delete("parameter-name");
  }
  return localEdrPosition(new Request(local, request));
}
