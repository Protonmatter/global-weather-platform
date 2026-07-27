import { desc } from "drizzle-orm";
import { getDb } from "../../../db";
import { modelCycles } from "../../../db/schema";
import {
  controlPlaneConfigurationProblem,
  controlPlaneMode,
} from "../../../lib/weather";

export async function GET(request: Request) {
  if (controlPlaneMode() !== "local-development") {
    return controlPlaneConfigurationProblem(request);
  }
  const cycles = await getDb()
    .select()
    .from(modelCycles)
    .orderBy(desc(modelCycles.initializedAt))
    .limit(100);
  return Response.json({ cycles });
}
