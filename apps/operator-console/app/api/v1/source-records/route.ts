import { POST as localPost } from "../../source-records/route";
import { proxyToControlPlane } from "../../../../lib/weather";

export async function POST(request: Request) {
  return (
    (await proxyToControlPlane(request, "/v1/source-records")) ??
    localPost(request)
  );
}
