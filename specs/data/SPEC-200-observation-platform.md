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
    verification: [TEST-UNIT-RAW-0001, TEST-INGEST-0001]
    release_gate: engineering
  - id: DATA-RAW-0002
    statement: Raw source objects MUST be immutable, content-addressed by SHA-256, and revalidated when an existing address is reused.
    priority: critical
    verification: [TEST-UNIT-RAW-0002, TEST-UNIT-RAW-0003]
    release_gate: engineering
  - id: DATA-RAW-0003
    statement: Reprocessing an identical source record with the same decoder version MUST NOT duplicate canonical observations.
    priority: critical
    verification: [TEST-INGEST-0002, TEST-CONTRACT-RAW-0001]
    release_gate: engineering
  - id: DATA-PROV-0004
    statement: Every canonical observation MUST reference the immutable source object URI and source record digest used to derive it.
    priority: critical
    verification: [TEST-SCHEMA-0001, TEST-INGEST-0001]
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

The observation platform receives untrusted source records, stores exact source bytes in an immutable SHA-256 content-addressed object store, validates and decodes the record, and emits canonical observations with deterministic derived identifiers and explicit source-object provenance.

The filesystem implementation is the Phase-1 reference backend. Production object-storage backends must preserve the same immutability, integrity verification, address format, and idempotency contracts.
