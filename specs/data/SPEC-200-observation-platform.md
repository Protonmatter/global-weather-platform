---
spec_id: SPEC-200
title: Observation platform
status: implemented
owners:
  - data-platform
  - observation-quality
standards:
  - WMO-WIS2
  - WMO-306
  - CF-CONVENTIONS
requirements:
  - id: DATA-RAW-0001
    statement: The original source message MUST be retained before interpretation or transformation.
    priority: critical
    verification: [TEST-UNIT-0001]
    release_gate: engineering
  - id: DATA-TIME-0002
    statement: Observation time, ingestion time, and source publication time MUST be represented independently when available.
    priority: critical
    verification: [TEST-SCHEMA-0001]
    release_gate: engineering
  - id: DATA-QC-0003
    statement: Every observation MUST carry an explicit quality disposition and quality flags.
    priority: high
    verification: [TEST-SCHEMA-0001]
    release_gate: engineering
---

# Observation platform

The observation platform receives untrusted source records, validates their envelope, preserves immutable source bytes or a content-addressed reference, and emits canonical observations with explicit provenance and quality state.
