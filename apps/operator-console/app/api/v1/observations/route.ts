import {
  GET as localGet,
  POST as localPost,
} from "../../observations/route";
import { proxyToControlPlane } from "../../../../lib/weather";

export async function GET(request: Request) {
  return (
    (await proxyToControlPlane(request, "/v1/observations")) ??
    localGet(request)
  );
}

export async function POST(request: Request) {
  return (
    (await proxyToControlPlane(request, "/v1/observations")) ??
    localPost(request)
  );
}
