# Operational Weather Data Platform — Approved Design

**Date:** 2026-08-12  
**RFC:** `rfcs/RFC-0002-operational-weather-data-platform.md`  
**Approval:** User approved the design in the implementation request preceding this branch.

## Objective

Deliver an RFC-aligned, spec-driven path for importing NOAA deterministic and ensemble model guidance without conflating it with observations, preserving immutable source evidence, and exposing reproducible scientific and presentation contracts.

## Architecture

The design separates provider acquisition, evidence retention, scientific normalization, model-cycle publication, standards-based serving, and browser presentation.

```text
NOAA GFS/GEFS + WIS2 + optional OpenWeather
  -> provider-isolated acquisition
  -> immutable raw records and byte-slice manifests
  -> ecCodes decode and canonical grid assets
  -> cycle completeness and scientific QC
  -> OGC API EDR / map asset service
  -> forecast-map application
```

Only acquisition workers have external provider egress. Downstream services read internal content-addressed stores.

## Phase-1 boundaries

This implementation slice establishes the contracts and deterministic pure logic needed before enabling live acquisition:

- source-slice and gridded-asset models;
- provider index parsing and range selection;
- cycle lifecycle and publication eligibility;
- coordinate and wind-vector invariants;
- deterministic vector-tile wire format;
- executable specifications, schemas, CI gates, deployment security policy, and traceability.

The slice does not claim that production S3/SQS/PostgreSQL/Zarr/CDN or the forecast-map UI is deployed. Those are subsequent slices that consume the contracts defined here.

## Components

### Domain contracts

`SourceSliceManifest` records upstream object identity, exact byte interval, index and payload SHA-256 digests, and acquisition timestamps.

`GridFieldAsset` records model/cycle/member, phenomenon, level, units, grid geometry, immutable source identity, normalized identity, quality state, and provenance.

### NOAA GRIB index selector

A strict parser accepts standard colon-delimited GRIB index lines, preserves provider metadata, derives message byte ranges from adjacent offsets, and rejects malformed, duplicate, descending, or unbounded selections.

Field selection is declarative. A required-field manifest maps stable canonical names to provider match predicates. Selection fails explicitly when a required field is missing or ambiguous.

### Cycle lifecycle

Cycle state is modeled explicitly. Publication eligibility is based on a minimum field manifest rather than arrival order. Duplicate events are idempotent.

### Geographic and vector contracts

Longitude normalization uses wrapped GeoJSON longitude semantics. Meteorological direction conversion is validated against north/east/south/west truth cases. Vector-tile encoding uses deterministic signed 16-bit quantization with explicit scale and offset metadata.

### Deployment policy

Acquisition and serving are separate Kubernetes trust zones. Acquisition receives only the minimum Internet and storage egress. Serving has no arbitrary provider egress. Workloads run non-root with dropped capabilities and read-only root filesystems where practical.

## Error handling

Malformed or ambiguous provider metadata is rejected before download. Hash or range mismatches quarantine a source slice. Incomplete cycles remain visible but cannot become `latest_usable`. Provider failure serves the previous usable cycle with explicit staleness.

## Testing strategy

The test hierarchy is:

1. unit tests for typed contracts and parsers;
2. property/metamorphic tests for longitude, time, range, and quantization invariants;
3. schema conformance and consumer contracts;
4. integration tests using deterministic GRIB index and payload fixtures;
5. scientific validation for vector direction and cycle semantics;
6. deployment-policy tests;
7. later end-to-end browser tests from source notification to rendered map.

Every production defect must add a regression fixture.

## UX design constraints

The future forecast client must distinguish observed, deterministic forecast, ensemble consensus, official warning, and experimental output. It must show initialization time, valid time, lead, source, and staleness. Reduced-motion and non-WebGL fallbacks are mandatory.

## Design self-review

- No placeholders or unresolved architectural decisions remain for Phase 1.
- Live infrastructure is explicitly separated from the contract slice rather than implied as complete.
- The typed models, JSON Schemas, specifications, tests, and CI gates use consistent field names.
- Observation and gridded guidance remain separate throughout the architecture.
