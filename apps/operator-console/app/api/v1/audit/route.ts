import { desc } from "drizzle-orm";
import { getDb } from "../../../../db";
import { auditEvents } from "../../../../db/schema";
import {
  actorFromRequest,
  adaptControlPlaneAuditEvents,
  controlPlaneConfigurationProblem,
  controlPlaneMode,
  ControlPlaneConfigurationError,
  mappedJsonResponse,
  problem,
  proxyToControlPlane,
} from "../../../../lib/weather";

export async function GET(request: Request) {
  const actor = actorFromRequest(request);
  if (!actor) {
    return problem(
      request,
      401,
      "Authentication required",
      "Audit history requires an authenticated workspace operator.",
      "urn:weather:problem:authentication-required",
    );
  }
  const mode = controlPlaneMode();
  if (mode === "misconfigured") {
    return controlPlaneConfigurationProblem(request);
  }
  if (mode === "remote-authoritative") {
    let upstream: Response;
    try {
      upstream = (await proxyToControlPlane(request, "/v1/audit-events", {
        actor,
        requireServiceAuth: true,
      })) as Response;
    } catch (error) {
      if (error instanceof ControlPlaneConfigurationError) {
        return controlPlaneConfigurationProblem(request);
      }
      throw error;
    }
    return mappedJsonResponse(request, upstream, adaptControlPlaneAuditEvents);
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
