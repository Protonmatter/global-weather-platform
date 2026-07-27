import { desc } from "drizzle-orm";
import { getDb } from "../../../../db";
import { auditEvents } from "../../../../db/schema";
import {
  actorFromRequest,
  problem,
} from "../../../../lib/weather";

export async function GET(request: Request) {
  if (!actorFromRequest(request)) {
    return problem(
      request,
      401,
      "Authentication required",
      "Audit history requires an authenticated workspace operator.",
      "urn:weather:problem:authentication-required",
    );
  }
  const events = await getDb()
    .select()
    .from(auditEvents)
    .orderBy(desc(auditEvents.occurredAt))
    .limit(200);
  return Response.json({
    events: events.map((event) => ({
      ...event,
      detail: JSON.parse(event.detail) as Record<string, unknown>,
    })),
  });
}
