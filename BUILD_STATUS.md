# Build status — baseline 0.1.0

## Implemented

- Spec front-matter schema and normative requirement validation
- Verification evidence registry checked against spec statuses
- Generated requirement traceability artifact
- Observation, forecast, model-cycle, and provenance JSON Schemas
- Typed canonical observation model with schema conformance tests
- Append-only JSONL observation store
- Content-addressed, write-once raw source record store with no-follow regular-file enforcement and a configurable size bound
- Source-record ingestion that retains raw bytes before decoding and binds provenance digests
- Transport-agnostic WIS2 notification consumer: topic validation, retained notifications, upstream integrity verification, and distinct publication, receipt, and ingestion times
- Canonical observation admission requires a retained source record
- FastAPI health, ingest, source-record, and query endpoints
- RFC 9457 problem responses for validation, rejection, and internal errors
- Brier score, ensemble CRPS (standard and fair estimators), reliability bins, quantile invariants
- Dependence-aware baseline fusion weighting and effective ensemble size
- Telemetry disabled by default and restricted to internal collector names
- Deny-by-default Kubernetes network policy
- Internal-runner CI workflows using an internal Python package mirror

## Verification

- Specification validation: 17 requirements and 12 verification references
- JSON Schema meta-validation: 4 schemas
- Unit and contract tests: 101 passed
- Branch-aware coverage: 95.19%
- Ruff: passed
- Mypy strict mode: passed
- API smoke test: passed

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
