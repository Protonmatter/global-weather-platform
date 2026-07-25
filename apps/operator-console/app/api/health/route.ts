import { count } from "drizzle-orm";
import { WEATHER_CONTRACT_VERSION } from "../../../contracts/weather";
import { getDb } from "../../../db";
import { auditEvents, observations, sourceRecords } from "../../../db/schema";
import { getRuntimeBindings } from "../../../lib/weather";

export async function GET() {
  const db = getDb();
  const [[observationCount], [sourceCount], [auditCount]] = await Promise.all([
    db.select({ value: count() }).from(observations),
    db.select({ value: count() }).from(sourceRecords),
    db.select({ value: count() }).from(auditEvents),
  ]);

  return Response.json({
    status: "ok",
    version: "0.3.0-site",
    contract_version: WEATHER_CONTRACT_VERSION,
    control_plane_mode: getRuntimeBindings().CONTROL_PLANE_URL
      ? "remote-authoritative"
      : "embedded-fallback",
    environment: "chatgpt-sites",
    telemetry_enabled: false,
    external_egress_enabled: false,
    persistence: {
      canonical_observations: observationCount?.value ?? 0,
      retained_source_records: sourceCount?.value ?? 0,
      audit_events: auditCount?.value ?? 0,
      structured_store: "available",
      object_store: "available",
    },
  });
}
