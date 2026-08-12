---
spec_id: SPEC-220
title: Immutable weather source slices
status: implemented
owners:
  - data-platform
  - security
standards:
  - RFC-3339
  - SHA-256
  - WMO-GRIB2
requirements:
  - id: ACQ-SRC-0001
    statement: Every selectively retrieved provider byte range MUST produce an immutable source-slice manifest containing the upstream object identity, exact inclusive byte interval, index digest, payload digest, and acquisition timestamps.
    priority: critical
    verification: [TEST-SOURCE-0001]
    release_gate: engineering
  - id: ACQ-HASH-0002
    statement: The platform MUST calculate a SHA-256 digest for retained source bytes and MUST NOT treat a provider ETag as a cryptographic content identity.
    priority: critical
    verification: [TEST-SOURCE-0001]
    release_gate: security
  - id: ACQ-RANGE-0003
    statement: A source byte interval MUST be non-negative, ordered, and bounded by the declared upstream object length before it is admitted.
    priority: critical
    verification: [TEST-SOURCE-0001]
    release_gate: engineering
  - id: ACQ-TIME-0004
    statement: Discovery, download, receipt, and retention timestamps MUST be timezone-aware and MUST preserve their monotonic acquisition order.
    priority: high
    verification: [TEST-SOURCE-0001]
    release_gate: engineering
---

# Immutable weather source slices

Selective GRIB retrieval reduces bandwidth but does not reduce evidence requirements. The platform retains each selected byte interval and its index context as an independently verifiable source record.

Cross-field bounds and timestamp ordering are enforced by the typed domain model. JSON Schema enforces portable structural constraints; implementation validators enforce arithmetic relationships that standard JSON Schema cannot express portably.
