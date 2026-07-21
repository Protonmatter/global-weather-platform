---
spec_id: SPEC-210
title: Canonical data model
status: implemented
owners:
  - data-architecture
standards:
  - RFC-3339
  - RFC-7946
  - CF-CONVENTIONS
requirements:
  - id: DATA-UNIT-0001
    statement: Canonical values MUST include an explicit unit and MUST NOT infer units from field names.
    priority: critical
    verification: [TEST-SCHEMA-0001]
    release_gate: engineering
  - id: DATA-GEO-0002
    statement: Interchange geometry MUST use GeoJSON longitude and latitude ordering.
    priority: critical
    verification: [TEST-SCHEMA-0001]
    release_gate: engineering
  - id: DATA-MISS-0003
    statement: Missing values MUST remain distinguishable from measured zero and trace values.
    priority: critical
    verification: [TEST-SCHEMA-0001]
    release_gate: engineering
---

# Canonical data model

Canonical records preserve semantic support: point versus area, instant versus interval, vertical coordinate, valid time, uncertainty, and source lineage.
