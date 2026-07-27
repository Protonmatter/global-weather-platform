import {
  adaptControlPlaneHealth,
  mappedJsonResponse,
  proxyToControlPlane,
} from "../../../../lib/weather";
import { GET as localHealth } from "../../health/route";

export async function GET(request: Request) {
  const upstream = await proxyToControlPlane(request, "/healthz");
  return upstream
    ? mappedJsonResponse(request, upstream, adaptControlPlaneHealth)
    : localHealth();
}
