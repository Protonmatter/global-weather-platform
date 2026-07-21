# Build status — DATA-001 implementation slice

## Implemented

- Spec front-matter schema and normative requirement validation
- Generated requirement traceability artifact
- Observation, forecast, model-cycle, and provenance JSON Schemas
- Immutable filesystem SHA-256 raw object store
- Exclusive create semantics with no overwrite path
- Full integrity revalidation when an object address is reused
- Symlink and non-regular-file rejection
- Maximum source-record size enforcement
- Raw-before-decode ingestion pipeline
- Deterministic derived observation IDs by source digest, decoder version, and record index
- Idempotent canonical writes for duplicate source records
- Raw evidence retention when decoding or quality disposition fails
- Canonical provenance binding to source digest and `cas://sha256/` URI
- Append-only JSONL observation store with locked idempotent batch writes
- FastAPI health, exact-byte ingest, and query endpoints
- RFC 9457-style problem response for service-level value errors
- Brier score, ensemble CRPS, reliability bins, quantile invariants
- Dependence-aware baseline fusion weighting and effective ensemble size
- Telemetry disabled by default and restricted to internal collector names
- Deny-by-default Kubernetes network policy
- Internal-runner CI workflows using an internal Python package mirror

## Verification

- Specification validation: 20 requirements
- JSON Schema meta-validation: 4 schemas
- Unit and contract tests: 39 passed
- Branch-aware coverage: 92.35%
- Ruff: passed
- Mypy strict mode: passed
- Raw-byte API round trip: passed
- Duplicate-ingestion idempotency: passed
- Corruption and symlink adversarial tests: passed
- Decoder-failure evidence-retention test: passed

## Explicitly not implemented yet

- Distributed or S3-compatible raw object backend
- Retention policy, legal hold, replication, and lifecycle enforcement
- WIS2, GRIB2, BUFR, radar, satellite, or external NWP adapters
- Indexed canonical storage and observation search
- OGC API EDR implementation
- Data assimilation
- Operational calibration or model fusion
- Forecast visualization client
- Numerical weather-model execution
- Production authentication and authorization
