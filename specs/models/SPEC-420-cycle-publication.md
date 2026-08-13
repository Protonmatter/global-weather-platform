---
spec_id: SPEC-420
title: Model cycle publication lifecycle
status: review
owners:
  - application-platform
  - data-platform
  - independent-verification
standards:
  - RFC-3339
  - WMO-GRIB2
requirements:
  - id: MODEL-CYCLE-0001
    statement: Model-cycle publication state MUST be explicit and MUST distinguish missing, partial, minimum-usable, complete, quarantined, superseded, and expired states.
    priority: critical
    verification: [TEST-CYCLE-0001]
    release_gate: operational
  - id: MODEL-USABLE-0002
    statement: A newer cycle MUST NOT replace the currently served usable cycle until its configured minimum required-field manifest is satisfied.
    priority: critical
    verification: [TEST-CYCLE-PUBLISH-0002]
    release_gate: operational
  - id: MODEL-IDEMPOTENT-0003
    statement: Duplicate provider notifications and field arrivals MUST NOT inflate completeness or create duplicate logical field identities.
    priority: critical
    verification: [TEST-CYCLE-0001, TEST-GRIB-0001]
    release_gate: engineering
  - id: MODEL-ALIAS-0004
    statement: The catalog SHOULD expose distinct latest-published, latest-usable, and latest-complete aliases, and user-facing defaults MUST resolve latest-usable.
    priority: high
    verification: [TEST-CYCLE-ALIAS-0003]
    release_gate: ux
---

# Model cycle publication lifecycle

Arrival order is not publication readiness. Required fields are evaluated per coherent grid, forecast lead, and ensemble-member scope against minimum and complete manifests. Duplicate arrivals within that exact scope do not inflate completeness, and illegal backwards state transitions are rejected.

Persistent serving replacement, latest-cycle aliases, and atomic publication remain planned. They require a durable model-asset catalog and serving integration before this specification can be promoted to `implemented` as a whole.
