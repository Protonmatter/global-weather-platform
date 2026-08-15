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
  - id: DATA-ING-0004
    statement: Canonical observation batches and their request-specific completion receipts MUST use one ordered recoverable commit so a receipt cannot become authoritative before every observation in its batch.
    priority: critical
    verification: [TEST-INGEST-0001]
    release_gate: operational
---

# Observation platform

The observation platform receives untrusted source records, validates their envelope, preserves immutable source bytes or a content-addressed reference, and emits canonical observations with explicit provenance and quality state. Ingestion completion receipts are the final records in the same durable append payload as their canonical observation batch, allowing recovery to distinguish a complete commit from an interrupted append without re-decoding the source.

Quarantined observations are retained and remain queryable for review, but are held out of the default serving path until their quality state is cleared. Rejected observations never enter the canonical store; their retained source record remains available for audit.
