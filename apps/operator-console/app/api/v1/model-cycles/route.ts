import { GET as localGet } from "../../model-cycles/route";
import { proxyToControlPlane } from "../../../../lib/weather";

export async function GET(request: Request) {
  return (
    (await proxyToControlPlane(request, "/v1/model-cycles")) ??
    localGet()
  );
}
