import { getDb } from "../db";
import { auditEvents } from "../db/schema";
import { bestEffortAudit } from "./audit-policy";
import { sha256Text } from "./weather";

export async function auditEventValues(input: {
  actor: string;
  action: string;
  resourceType: string;
  resourceId: string;
  detail?: Record<string, unknown>;
}) {
  const occurredAt = new Date().toISOString();
  const id = await sha256Text(
    `${input.actor}\u0000${input.action}\u0000${input.resourceType}\u0000${input.resourceId}`,
  );
  return {
    id,
    actor: input.actor,
    action: input.action,
    resourceType: input.resourceType,
    resourceId: input.resourceId,
    occurredAt,
    detail: JSON.stringify(input.detail ?? {}),
  };
}

export async function recordAuditEvent(input: {
  actor: string;
  action: string;
  resourceType: string;
  resourceId: string;
  detail?: Record<string, unknown>;
}) {
  const values = await auditEventValues(input);
  await getDb()
    .insert(auditEvents)
    .values(values)
    .onConflictDoNothing({ target: auditEvents.id });
}

export async function recordAuditEventBestEffort(
  input: Parameters<typeof recordAuditEvent>[0],
) {
  return bestEffortAudit(
    { action: input.action, resourceType: input.resourceType },
    () => recordAuditEvent(input),
  );
}
