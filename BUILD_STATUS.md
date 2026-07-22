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
- OGC API EDR position query with datetime subsetting, antimeridian-safe matching, and GeoJSON responses exposing units, provenance, and times
- RFC 9457 problem responses for validation, rejection, and internal errors
- Brier score, ensemble CRPS (standard and fair estimators), reliability bins, quantile invariants
- Dependence-aware baseline fusion weighting and effective ensemble size
- Verification dataset ledger: leakage-safe availability-at-issue partitioning and versioned, reproducible persistence and climatology baselines
- Telemetry disabled by default and restricted to internal collector names
- Deny-by-default Kubernetes network policy
- Internal-runner CI workflows using an internal Python package mirror

## Verification

- Specification validation: 19 requirements and 13 verification references
- JSON Schema meta-validation: 5 schemas
- Unit and contract tests: 142 passed
- Branch-aware coverage: 94.77%
- Ruff: passed
- Mypy strict mode: passed
- API smoke test: passed

## Partially implemented

- Acquisition transport integrity: issuer-allowlist verification, fail-closed on unpinned issuers, and upstream-checksum verification are implemented and tested; live MQTT/HTTPS acquisition wiring awaits a deployment target
- GRIB2/BUFR decoder service: pinned definition-table provenance, malformed-message rejection, decodable-but-suspect quarantine, and golden-corpus drift detection are implemented and tested; the low-level ecCodes decode is injected and requires the native ecCodes library

## Explicitly not implemented yet

- Live MQTT session and HTTP download wiring for the WIS2 consumer
- GRIB2, BUFR, radar, satellite, or external NWP adapters
- Object storage and indexed canonical storage
- OGC API EDR implementation
- Data assimilation
- Operational calibration or model fusion
- Forecast visualization client
- Numerical weather-model execution
- Production authentication and authorization
