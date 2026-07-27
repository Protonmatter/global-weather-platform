# Build status — baseline 0.1.0

## Implemented

- Spec front-matter schema and normative requirement validation
- Verification evidence registry checked against spec statuses
- Generated requirement traceability artifact
- Observation, forecast, model-cycle, and provenance JSON Schemas
- Typed canonical observation model with schema conformance tests
- Append-only JSONL observation store
- Content-addressed, write-once raw source record store with no-follow regular-file enforcement and a configurable size bound
- Source-record ingestion that retains raw bytes before decoding, binds provenance digests, and derives deterministic content-addressed observation ids
- Transport-agnostic WIS2 notification consumer: topic validation, retained notifications, upstream integrity verification, and distinct publication, receipt, and ingestion times
- Canonical observation admission requires a retained source record, serialized across processes by an advisory file lock
- Quarantined observations retained and queryable but held out of the default serving path
- Model guidance catalog with the four-way guidance distinction (imported, platform, official-warning, experimental) and explicit missing/partial cycle completeness
- FastAPI health, ingest, source-record, model-cycle, and query endpoints
- Separately deployable Sites operator console with authenticated mutation
  routes, D1/R2 edge persistence, audit history, provenance-aware observations,
  model-cycle status, and OGC EDR-style position queries
- BFF-to-FastAPI mutation authentication with fail-closed production
  configuration, explicit local-development fallback, verified operator
  propagation, and caller-header stripping
- Cross-runtime UUIDv5 observation identity and response-shaping contract tests
- OGC API EDR position query with datetime subsetting, antimeridian-safe matching, and GeoJSON responses exposing units, provenance, and times
- RFC 9457 problem responses for validation, rejection, and internal errors
- Brier score, ensemble CRPS (standard and fair estimators), reliability bins, quantile invariants
- Dependence-aware baseline fusion weighting and effective ensemble size
- Verification dataset ledger: leakage-safe availability-at-issue partitioning and versioned, reproducible persistence and climatology baselines
- Telemetry disabled by default and restricted to internal collector names
- Deny-by-default Kubernetes network policy
- GitHub-hosted pull-request quality gates plus isolated self-hosted release and
  deep-security workflows, with a runner registration helper and runbook

## Verification

- Specification validation: 19 requirements and 13 verification references
- JSON Schema meta-validation: 5 schemas
- Unit and contract tests: 147 passed
- Branch-aware coverage: 94.33%
- Ruff: passed
- Mypy strict mode: passed
- API smoke test: passed

## Partially implemented

- Acquisition transport integrity: issuer-allowlist verification, fail-closed on unpinned issuers, and upstream-checksum verification are implemented and tested; live MQTT/HTTPS acquisition wiring awaits a deployment target
- GRIB2/BUFR decoder service: real ecCodes GRIB2 decoding into the model-cycle field inventory is implemented and tested (runtime ecCodes version recorded, malformed rejection, golden-corpus drift detection); real ecCodes BUFR decoding into canonical observations is the remaining part. ecCodes is an optional (`eccodes`) extra

## Explicitly not implemented yet

- Live MQTT session and HTTP download wiring for the WIS2 consumer
- GRIB2, BUFR, radar, satellite, or external NWP adapters
- Object storage and indexed canonical storage
- Data assimilation
- Operational calibration or model fusion
- Probabilistic forecast visualization client / progressive-disclosure forecast
  shell (UX-001 remains deferred pending forecast products; the implemented
  operator console covers control-plane workflows only)
- Numerical weather-model execution
- Fine-grained production role authorization beyond the implemented BFF
  service credential and authenticated operator identity
