import {
  adaptControlPlaneHealth,
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  mappedJsonResponse,
  proxyToControlPlane,
} from "../../../../lib/weather";
import { GET as localHealth } from "../../health/route";

export async function GET(request: Request) {
  const mode = controlPlaneMode();
  if (mode === "local-development") return localHealth(request);
  if (mode === "misconfigured") {
    return controlPlaneConfigurationProblem(request);
  }
  const upstream = await proxyToControlPlane(request, "/healthz");
  return upstream
    ? mappedJsonResponse(request, upstream, adaptControlPlaneHealth)
    : controlPlaneConfigurationProblem(request);
}
