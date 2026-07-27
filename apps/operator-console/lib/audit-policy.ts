export async function bestEffortAudit(
  context: { action: string; resourceType: string },
  writer: () => Promise<void>,
) {
  try {
    await writer();
    return true;
  } catch (error) {
    console.error(
      JSON.stringify({
        event: "edge_audit_write_failed",
        action: context.action,
        resourceType: context.resourceType,
        errorType: error instanceof Error ? error.name : "unknown",
      }),
    );
    return false;
  }
}
