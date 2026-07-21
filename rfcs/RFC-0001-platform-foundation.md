# RFC-0001: Platform foundation

**Status:** Accepted  
**Owners:** Platform Architecture, Data Platform, Independent Verification

## Problem

Forecast development cannot begin safely without stable data semantics, provenance, test evidence, and deployment boundaries.

## Decision

Implement the first vertical slice as a Python control plane with JSON Schema interchange contracts, append-only source preservation, FastAPI APIs, and separately deployable scientific/HPC workloads.

## Alternatives

1. Begin with a weather-model fork. Rejected because ingestion, traceability, and verification would remain undefined.
2. Build only a visualization client. Rejected because model semantics and uncertainty would be presentation-dependent.
3. Use Python for all numerical kernels. Rejected; Python governs workflows and interfaces, while future production numerical kernels may use Fortran, C++, JAX, or accelerator-native implementations.

## Rollback

The data and API contracts are versioned. A replacement control plane must preserve the schemas or provide an explicit migration.
