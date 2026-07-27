import { GET as localGet } from "../../model-cycles/route";
import {
  adaptControlPlaneModelCycles,
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  mappedJsonResponse,
  proxyToControlPlane,
} from "../../../../lib/weather";

export async function GET(request: Request) {
  const mode = controlPlaneMode();
  if (mode === "local-development") return localGet(request);
  if (mode === "misconfigured") {
    return controlPlaneConfigurationProblem(request);
  }
  const upstream = await proxyToControlPlane(request, "/v1/model-cycles");
  return upstream
    ? mappedJsonResponse(request, upstream, adaptControlPlaneModelCycles)
    : controlPlaneConfigurationProblem(request);
}
