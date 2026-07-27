import { GET as localGet } from "../../model-cycles/route";
import {
  adaptControlPlaneModelCycles,
  mappedJsonResponse,
  proxyToControlPlane,
} from "../../../../lib/weather";

export async function GET(request: Request) {
  const upstream = await proxyToControlPlane(request, "/v1/model-cycles");
  return upstream
    ? mappedJsonResponse(request, upstream, adaptControlPlaneModelCycles)
    : localGet();
}
