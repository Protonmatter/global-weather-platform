# Build status — baseline 0.1.0 with RFC-0002 Phase 1

## Implemented

### Specification, governance, and release evidence

- RFC-0002 operational weather-data architecture, approved design record, and task-level implementation plan
- Executable acquisition-boundary, source-slice, gridded-guidance, cycle-readiness, and scientific-validation specifications
- Requirement and verification registry with generated traceability checked in CI
- RFC 2119/RFC 8174 normative language and RFC 9457 API-problem conventions retained
- GitHub Actions pinned to current commit SHAs using Node-24-capable official action releases
- Cycle serving replacement and latest-cycle aliases explicitly retained as planned requirements rather than reported as implemented
- Repository-wide deny-by-default egress proof retained as planned; weather-specific acquisition and serving policy evidence remains separately implemented

### Existing platform foundation

- Spec front-matter schema and normative requirement validation
- Verification evidence registry checked against implemented specification statuses
- Generated requirement traceability artifact
- Observation, forecast, model-cycle, event, source-slice, grid-asset, and provenance JSON Schemas
- Typed canonical observation model with schema conformance tests
- Append-only JSONL observation store
- Content-addressed, write-once raw source-record store with no-follow regular-file enforcement and a configurable size bound
- Source-record ingestion that retains raw bytes before decoding, binds provenance digests, and derives deterministic content-addressed observation IDs
- Transport-agnostic WIS2 notification consumer with topic validation, retained notifications, upstream integrity verification, and distinct publication, receipt, and ingestion times
- Canonical observation admission requiring a retained source record and serialized across processes by an advisory file lock
- Quarantined observations retained and queryable but held out of the default serving path
- Model-guidance catalog with imported, platform, official-warning, and experimental origins and explicit missing/partial/complete inventory semantics
- FastAPI health, ingest, source-record, model-cycle, and query endpoints
- OGC API EDR-style position query with datetime subsetting, antimeridian-safe matching, and GeoJSON responses exposing units, provenance, and times
- RFC 9457 problem responses for validation, rejection, and internal errors
- Brier score, ensemble CRPS, reliability bins, quantile invariants, dependence-aware baseline fusion weighting, and effective ensemble size
- Verification dataset ledger with availability-at-issue partitioning and reproducible climatology baselines

### Operational weather Phase 1

- Frozen `SourceSliceManifest` and nested evidence contracts for bounded, inclusive provider byte ranges
- `SourceSliceManifest.from_retained_bytes` calculates SHA-256 identities from retained index and payload bytes and validates payload length against the selected range
- Platform-calculated SHA-256 identities kept distinct from provider ETags
- Monotonic discovery, download, receipt, and retention timestamp validation
- Frozen `GridFieldAsset` domain contract and JSON Schema for one model variable, level, valid time, grid, and ensemble member
- Immutable tuple-backed quality flags and frozen grid-specific provenance evidence
- Enforced invariant: `valid_at == initialized_at + lead_seconds`
- Valid-time arithmetic outside Python's supported datetime range is converted into a typed validation failure rather than escaping as `OverflowError`
- Empty ensemble-member identifiers, empty level units, empty quality-flag identifiers, and non-finite vertical levels rejected at typed admission
- Enforced source-digest/provenance and decoder-version/provenance agreement
- Accepted assets prohibited from carrying unresolved quality flags
- Strict NOAA-style GRIB index parsing with consecutive message-number validation, monotonic offsets, bounded final-message range derivation, and malformed-input rejection
- Deterministic required-field selection that fails on missing or ambiguous matches
- GFS minimum-usable field manifest for 10 m U/V wind, 2 m temperature, 2 m relative humidity, and mean sea-level pressure
- Extended complete manifest including gust, cloud cover, and precipitation
- Canonical ecCodes-to-platform GFS field identity mapping
- ecCodes `perturbationNumber` extraction preserves provider ensemble-member identities while deterministic messages remain unlabeled
- Explicit cycle states: discovered, index available, downloading, missing, partial, minimum usable, complete, quarantined, superseded, and expired
- Required-field readiness evaluated per coherent grid, forecast lead, and ensemble-member scope
- Duplicate arrivals within the exact product scope do not inflate completeness; mixed scopes are rejected
- Complete but not-yet-published cycles may transition to quarantine when integrity or scientific validation fails
- GeoJSON-range longitude normalization and antimeridian-safe angular distance, including extreme finite inputs that would overflow before wrapping
- Meteorological direction-to-U/V conversion validated against all cardinal directions
- Versioned deterministic binary U/V tile format with signed 16-bit interleaving, explicit scale/offset metadata, strict length validation, and bounded reconstruction error
- Overflow-safe vector quantization for very large finite component ranges; non-representable metadata fails closed with `VectorTileError`
- Fail-closed `weather-platform-acquisition` command; live transport is not enabled
- Hardened acquisition deployment contract with non-root execution, dropped capabilities, read-only root filesystem, and resource bounds
- Namespace-wide `weather-ingestion` Cilium default-deny policy prevents unlabeled or unapproved pods from inheriting unrestricted egress
- Approved acquisition pods receive an additive FQDN allowlist for provider TLS traffic over TCP 443 without plaintext HTTP L7 parsing
- Provider and cluster DNS queries pass through explicit Cilium DNS-proxy rules so `toFQDNs` identities can be learned without opening arbitrary DNS egress
- Separate serving namespace with default-deny ingress and egress
- Acquisition Deployment intentionally fixed at `replicas: 0` pending the live-transport activation gate

### Validation and CI/CD

- Repository-wide quality gate: Ruff lint, Ruff format, strict mypy, complete tests, and branch coverage
- Dedicated weather contract gate
- Dedicated JSON Schema and Kubernetes deployment-contract gate
- Dedicated scientific-validation gate
- Fixture-driven vertical-slice integration gate
- Immutable adversarial regression suite for antimeridian behavior, extreme finite longitude arithmetic, wind direction, duplicate arrivals, mixed product scopes, forecast-hour ambiguity, GRIB index gaps, model valid-time integrity and overflow, ensemble-member preservation, evidence immutability, empty quality identifiers, complete-cycle quarantine, namespace default-deny, TLS-safe provider egress, Cilium DNS observation, and extreme finite vector ranges
- JUnit evidence artifacts for focused schema, scientific, contract, and integration workflows
- Local Make targets matching the CI test taxonomy

### Operator console

- Separately deployable Sites operator console with authenticated mutation routes, D1/R2 edge persistence, audit history, provenance-aware observations, model-cycle status, and OGC EDR-style position queries
- BFF-to-FastAPI mutation authentication with fail-closed production configuration, explicit local-development fallback, verified operator propagation, and caller-header stripping
- Cross-runtime UUIDv5 observation identity and response-shaping contract tests
- Portable Bash invocation of Sites build/install/validation helpers without relying on executable-bit preservation
- Node 22 TypeScript-stripping unit-test path for direct tests of tracked TypeScript sources
- Rendered artifact tests for both unauthenticated sign-in redirection and verified-workspace HTML rendering

## Verification

Verified in GitHub Actions on the RFC-0002 Phase-1 pull request after all review remediation:

- Specification validation: **40 requirements and 25 verification references**
- JSON Schema meta-validation: **7 schemas**
- Python tests: **257 passed**
- Python branch coverage: **93.02%** against a required minimum of 90%
- Ruff lint: passed
- Ruff format: **106 files already formatted**
- Mypy strict mode: **41 source files, no issues**
- Weather contract workflow: passed
- Schema contract workflow: passed
- Scientific validation workflow: passed
- Fixture-driven weather integration workflow: passed
- Operator-console lint and TypeScript checks: passed
- Operator-console unit tests: **22 passed**
- Operator-console production build and artifact validation: passed
- Operator-console rendered-artifact tests: **2 passed**
- Full CI bootstrap workflow: passed
- Generated traceability freshness check: passed
- Pull-request review remediation: **20 P2 threads addressed and resolved**

## Partially implemented

- Acquisition transport integrity: issuer-allowlist verification, fail-closed handling of unpinned issuers, and upstream-checksum verification are implemented and tested in the existing transport-trust core; live NOAA HTTP/S3/SQS wiring is not enabled
- GRIB2/BUFR decoder service: real ecCodes GRIB2 inventory decoding, including provider ensemble-member identity extraction, is implemented and tested; numeric global-array extraction, canonical array persistence, and full BUFR-to-observation decoding remain follow-on work
- Model-cycle lifecycle: scope-aware readiness classification and state-transition validation are implemented; persistent serving replacement and latest-published/latest-usable/latest-complete aliases remain planned
- OGC API EDR: position queries exist; gridded area and cube queries await production grid persistence
- Forecast-product UI: the operator console covers authenticated control-plane workflows; the separate forecast-map experience remains specified but not implemented

## Explicitly not implemented yet

- Live NOAA NODD HTTP/S3 range acquisition
- NOAA publication-event or SQS integration
- Production object storage, PostgreSQL metadata catalog, or Zarr array store for gridded guidance
- Atomic live cycle publication backed by persistent model assets
- Latest-published, latest-usable, and latest-complete serving aliases
- Complete numeric GRIB field-array extraction and normalization
- OGC API EDR area and cube queries over persisted grids
- Scalar map tiles, binary vector tile HTTP endpoints, map manifests, CDN deployment, or cache invalidation
- GEFS member acquisition and denominator-aware operational probability products
- Model-versus-observation operational calibration or probabilistic fusion
- `apps/forecast-map`, WebGL wind animation, responsive forecast experience, browser accessibility suite, and visual regression suite
- OpenWeather One Call adapter, quota control, point-condition enrichment, or alert aggregation
- Provider credential-redaction tests tied to a live client
- Repository-wide proof that every production workload is covered by deny-by-default egress
- Production authentication and authorization beyond the implemented control-plane service credential and verified operator identity
- Production load qualification, resilience/chaos exercises, staging replay, canary rollout, disaster recovery, or live data rollback exercises
- Numerical weather-model execution

## Activation boundary

The acquisition Deployment MUST remain at zero replicas until the live-transport activation checklist in `docs/WEATHER_DATA_DEPLOYMENT.md` is satisfied. Phase 1 proves the contracts, scientific invariants, weather-specific deployment boundary, and deterministic fixture path; it does not claim an operational live weather feed.
