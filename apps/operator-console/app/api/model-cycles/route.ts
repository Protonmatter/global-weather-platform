import { desc } from "drizzle-orm";
import { getDb } from "../../../db";
import { modelCycles } from "../../../db/schema";

const seedCycles = [
  {
    id: "gefs-35-20260724t18z",
    modelId: "GEFS",
    modelVersion: "35.0",
    guidanceOrigin: "imported",
    initializedAt: "2026-07-24T18:00:00.000Z",
    sourceRevision: "nomads-20260724-18",
    completeness: "complete",
    availableFieldCount: 816,
    expectedFieldCount: 816,
    updatedAt: "2026-07-24T19:08:00.000Z",
  },
  {
    id: "gfs-17-20260724t18z",
    modelId: "GFS",
    modelVersion: "17.0",
    guidanceOrigin: "imported",
    initializedAt: "2026-07-24T18:00:00.000Z",
    sourceRevision: "nomads-20260724-18",
    completeness: "partial",
    availableFieldCount: 672,
    expectedFieldCount: 720,
    updatedAt: "2026-07-24T18:56:00.000Z",
  },
  {
    id: "platform-calibration-20260724t12z",
    modelId: "Platform calibration",
    modelVersion: "0.1.0",
    guidanceOrigin: "experimental",
    initializedAt: "2026-07-24T12:00:00.000Z",
    sourceRevision: "validation-ledger-42",
    completeness: "partial",
    availableFieldCount: 44,
    expectedFieldCount: 60,
    updatedAt: "2026-07-24T15:20:00.000Z",
  },
];

export async function GET() {
  const db = getDb();
  await db
    .insert(modelCycles)
    .values(seedCycles)
    .onConflictDoNothing({ target: modelCycles.id });
  const cycles = await db
    .select()
    .from(modelCycles)
    .orderBy(desc(modelCycles.initializedAt))
    .limit(100);
  return Response.json({ cycles });
}
