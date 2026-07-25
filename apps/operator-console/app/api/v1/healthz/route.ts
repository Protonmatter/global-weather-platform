import { proxyToControlPlane } from "../../../../lib/weather";
import { GET as localHealth } from "../../health/route";

export async function GET(request: Request) {
  return (await proxyToControlPlane(request, "/healthz")) ?? localHealth();
}
