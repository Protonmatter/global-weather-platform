---
spec_id: SPEC-400
title: Model guidance catalog
status: implemented
owners:
  - data-platform
  - program-governance
standards:
  - WMO-306
  - NIST-AI-RMF
requirements:
  - id: MODEL-CAT-0001
    statement: Imported, platform-generated, official-warning, and experimental guidance MUST be labeled distinctly and MUST NOT be conflated.
    priority: critical
    verification: [TEST-CONTRACT-0001]
    release_gate: governance
  - id: MODEL-CAT-0002
    statement: Missing and partial model cycles MUST be represented explicitly rather than as silently absent data.
    priority: high
    verification: [TEST-CATALOG-0001]
    release_gate: engineering
  - id: MODEL-CAT-0003
    statement: A model-cycle catalog append MUST make both the record contents and a newly created catalog directory entry durable before reporting success.
    priority: critical
    verification: [TEST-CATALOG-0001]
    release_gate: engineering
---

# Model guidance catalog

The catalog indexes external and platform model cycles by model, version, cycle initialization, source revision, grid, variable, level, and lead. Every cycle carries an explicit guidance origin, so imported provider guidance is never confused with platform-generated or experimental output. Each cycle declares its expected field inventory, so a cycle that is missing or only partially available is represented explicitly rather than appearing as silently absent data. Catalog appends sync their record data before success and sync the parent directory when first creating the catalog, preserving creation across a power loss.
