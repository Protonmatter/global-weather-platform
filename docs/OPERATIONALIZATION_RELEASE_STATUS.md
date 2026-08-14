# Operationalization Release P0 — Build Status

**Status:** Implemented on pull request branch; awaiting review and merge  
**Base:** `main` after dependency-security PR #27  
**Validated code head:** `49daef2d892b6ee8b4d328112e980f97af4a55d1`

**GitHub Actions merge ref:** `3b1895e16d7fe5eaed7c10a3a8a9862aee18d47d`

## Implemented

### Repository and governance posture

- Repository text now accurately describes publicly viewable proprietary source; no open-source license is granted.
- `CODEOWNERS` resolves to the repository owner, `@Protonmatter`, rather than non-enforceable organization handles.
- Organization migration and independent scientific/security/SRE review teams remain a documented governance follow-up.

### Reproducible Python resolution

- `requirements/production.lock` and `requirements/ci.lock` are hash-pinned.
- Locks are generated with Python 3.12, `pip==26.1.2`, and `pip-tools==7.6.0`.
- Build-system dependencies, including `setuptools` and `wheel`, are included in the locks.
- Primary, bootstrap, specification, schema, scientific, weather-contract, and integration workflows install from the checked lock with `--require-hashes`.
- The permanent `python-lock` workflow regenerates locks and fails on drift.
- Release wheel construction uses the production lock, an immutable base-image digest, a disposable job-local Python environment, and an offline container build. The build does not install dependencies into the self-hosted runner's shared Python environment.

### Authoritative mutation accountability

- FastAPI now owns an append-only authoritative mutation-audit ledger.
- Audit events are immutable and include unique event ID, request ID, actor, action, resource type, resource ID, result, occurrence time, software version, and constrained detail.
- Persistent observation, source-record, and model-cycle mutations record `attempted` followed by terminal `succeeded` or `failed` events.
- Failure to persist the initial audit event blocks canonical state mutation.
- Terminal successes are written and synced under a hidden temporary name, then atomically published to the durable outbox before canonical state changes. An atomic outbox commit remains authoritative if compaction into the JSONL ledger cannot allocate additional space.
- Audit replay repairs only an unterminated invalid final ledger record after an interrupted append. A complete final event that is missing its newline is preserved and separated before the next append; malformed newline-terminated records still fail closed.
- Process startup reconciles pending successes against immutable source records, canonical observations, decoded-ingestion results, and request-specific model-cycle mutation markers. Only successes proven present for the exact mutation identity and content digest are published; uncertain entries remain pending.
- A failed source-record ingestion records `retained: true` whenever the immutable source bytes survive a downstream decoding, quality, or canonical-conflict failure and pass integrity verification.
- Request UUIDs are generated or validated, attached to request state, returned through `x-request-id`, and bound to audit events.

### Protected evidence access

- Production `GET /v1/source-records/{digest}` requires the control-plane bearer credential and trusted operator identity.
- Digest knowledge is no longer treated as authorization.
- Authorization occurs before existence disclosure or source-byte retrieval.

### Operator-console destination trust

- Remote `CONTROL_PLANE_URL` requires HTTPS, a DNS hostname, no userinfo, path, query, fragment, or IP literal, and an explicit `CONTROL_PLANE_ALLOWED_HOSTS` match.
- Local HTTP is permitted only for loopback development.
- Destination validation occurs before the BFF reads or attaches the service credential.
- Upstream responses are rebuilt from an explicit safe response-header set; cookies and internal/debug headers are discarded.

### Immutable release identity

- The checked acquisition manifest contains one non-deployable zero-digest source placeholder and remains at `replicas: 0`.
- The release renderer accepts only `repository@sha256:<64 lowercase hexadecimal characters>` references and rejects mutable tags and the placeholder digest.
- Internal release automation must write `release/image-ref.txt` after push, scan, signing, and attestation.
- CI renders the deployable acquisition manifest and release metadata binding Git SHA, image reference, production-lock digest, CI-lock digest, and deployment-manifest digest.
- Release evidence is uploaded as a retained workflow artifact.

## Verification evidence

GitHub Actions verified code head `49daef2d892b6ee8b4d328112e980f97af4a55d1` through pull-request merge ref `3b1895e16d7fe5eaed7c10a3a8a9862aee18d47d`. This document is intentionally committed after that code-changing commit so the evidence record does not claim to validate its own commit hash.

- Python tests: **307 passed**
- Python branch coverage: **90.84%**, above the required 90%
- Ruff lint: passed
- Ruff formatting: **121 files already formatted**
- Mypy strict mode: **48 source files, no issues**
- Operator-console unit contracts: **27 passed**
- Operator-console rendered-artifact tests: **2 passed**
- Operator-console lint, TypeScript checking, production build, and artifact validation: passed
- Hash-pinned lock regeneration and freshness comparison: passed
- Specification validation: passed
- JSON Schema and deployment contracts: passed
- Scientific validation: passed
- Fixture-driven integration validation: passed
- Focused weather contract validation: passed

All nine required workflows passed:

- `pr-fast`
- `ci-bootstrap`
- `spec-validation`
- `schema-contract`
- `scientific-validation`
- `weather-integration`
- `weather-contract`
- `operator-console`
- `python-lock`

CodeQL also passed for Actions, Python, and JavaScript/TypeScript. The image-publish workflow is not a pull-request check; the job-local environment change is covered here by an executable fake-tool build contract and shell syntax validation, not by a registry publish claim.

## Explicitly deferred

This release does not enable or claim:

- live NOAA, GEFS, WIS2, or OpenWeather acquisition;
- production PostgreSQL, object storage, or Zarr persistence;
- OAuth scopes or per-user raw-evidence authorization;
- atomic persistent cycle aliases or operational forecast publication;
- public forecast-map UI, accessibility certification, or visual-regression suite;
- production load, chaos, canary, staging replay, disaster-recovery, or data-rollback qualification;
- numerical weather-model execution.

## Activation boundary

The acquisition workload remains scaled to zero. Live transport activation still requires the complete checklist in `docs/WEATHER_DATA_DEPLOYMENT.md`, including tested provider transport, persistent stores, bounded retries, secret-redaction evidence, operational dashboards, staging replay, and approved production egress.
