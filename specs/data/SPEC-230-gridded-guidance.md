---
spec_id: SPEC-230
title: Canonical gridded model guidance
status: implemented
owners:
  - data-architecture
  - earth-system-science
standards:
  - RFC-3339
  - CF-CONVENTIONS
  - WMO-GRIB2
requirements:
  - id: DATA-GRID-0001
    statement: Gridded model guidance MUST be represented as a canonical grid asset and MUST NOT be expanded into one point observation per grid cell.
    priority: critical
    verification: [TEST-GRID-0001]
    release_gate: architecture
  - id: DATA-GRID-0002
    statement: Every grid asset MUST identify model initialization time, valid time, and lead, and valid time MUST equal initialization time plus lead.
    priority: critical
    verification: [TEST-GRID-0001]
    release_gate: scientific
  - id: DATA-LINEAGE-0003
    statement: Every grid asset MUST retain immutable source and normalized content digests, source revision, decoder version, unit, grid identity, and provenance.
    priority: critical
    verification: [TEST-GRID-0001, TEST-SCHEMA-0002]
    release_gate: engineering
  - id: DATA-ENSEMBLE-0004
    statement: Ensemble guidance MUST preserve the provider member identifier and MUST NOT collapse distinct members into an unlabelled deterministic field.
    priority: critical
    verification: [TEST-GRID-0001]
    release_gate: scientific
  - id: DATA-QUALITY-0005
    statement: An accepted grid asset MUST NOT carry unresolved quality flags; suspect assets SHOULD be admitted only with an explicit non-accept disposition.
    priority: high
    verification: [TEST-GRID-0001]
    release_gate: scientific
---

# Canonical gridded model guidance

A grid asset is metadata for one model variable, vertical level, valid time, grid, and ensemble member. Numeric values remain in a scientific array or immutable source representation; the catalog record makes that array discoverable and reproducible.

The ecCodes inventory decoder reads the provider `perturbationNumber` into the canonical member identity when the GRIB message defines it. Deterministic messages retain `member: null`, so ensemble members remain distinguishable without fabricating a member label.

Phase 1 defines metadata and wire contracts. Production Zarr/COG persistence is a later slice that consumes this contract.
