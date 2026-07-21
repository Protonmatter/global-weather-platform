---
spec_id: SPEC-100
title: System architecture
status: accepted
owners:
  - platform-architecture
  - security-architecture
standards:
  - NIST-SP-800-218
  - ISO-IEC-25010
requirements:
  - id: ARCH-NET-0001
    statement: Production application and model workloads MUST operate with deny-by-default egress.
    priority: critical
    verification: [TEST-SEC-0001]
    release_gate: security
  - id: ARCH-TEL-0002
    statement: Telemetry MUST remain disabled unless an approved internal endpoint is explicitly configured.
    priority: critical
    verification: [TEST-UNIT-0004]
    release_gate: security
  - id: ARCH-REL-0003
    statement: Source loss MUST produce explicit staleness and uncertainty behavior rather than silent continuity.
    priority: critical
    verification: [TEST-RES-0001]
    release_gate: operational
---

# System architecture

The architecture separates external acquisition, ingestion, scientific computation, application, management, public distribution, and research trust zones. Only acquisition workers may access allowlisted external data providers.
