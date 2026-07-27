import { edrConformanceClasses } from "../../../../contracts/weather";

export async function GET() {
  return Response.json({ conformsTo: edrConformanceClasses });
}
