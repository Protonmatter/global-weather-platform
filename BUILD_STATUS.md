# Build status — baseline 0.1.0

## Implemented

- Spec front-matter schema and normative requirement validation
- Generated requirement traceability artifact
- Observation, forecast, model-cycle, and provenance JSON Schemas
- Typed canonical observation model
- Append-only JSONL observation store
- FastAPI health, ingest, and query endpoints
- RFC 9457-style problem response for service-level value errors
- Brier score, ensemble CRPS, reliability bins, quantile invariants
- Dependence-aware baseline fusion weighting and effective ensemble size
- Telemetry disabled by default and restricted to internal collector names
- Deny-by-default Kubernetes network policy
- Internal-runner CI workflows using an internal Python package mirror

## Verification

- Specification validation: 17 requirements
- JSON Schema meta-validation: 4 schemas
- Unit and contract tests: 26 passed
- Branch-aware coverage: 94.07%
- Ruff: passed
- Mypy strict mode: passed
- API smoke test: passed

## Explicitly not implemented yet

- WIS2, GRIB2, BUFR, radar, satellite, or external NWP adapters
- Object storage and indexed canonical storage
- OGC API EDR implementation
- Data assimilation
- Operational calibration or model fusion
- Forecast visualization client
- Numerical weather-model execution
- Production authentication and authorization
