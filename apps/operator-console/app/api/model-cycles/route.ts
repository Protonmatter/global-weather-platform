import { desc } from "drizzle-orm";
import { getDb } from "../../../db";
import { modelCycles } from "../../../db/schema";

export async function GET() {
  const cycles = await getDb()
    .select()
    .from(modelCycles)
    .orderBy(desc(modelCycles.initializedAt))
    .limit(100);
  return Response.json({ cycles });
}
