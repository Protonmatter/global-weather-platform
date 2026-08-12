# Operational Weather Data Platform Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first testable vertical slice for NOAA gridded-guidance ingestion contracts, deterministic GRIB index selection, cycle promotion, scientific invariants, secure deployment policy, and blocking CI evidence.

**Architecture:** Provider-specific acquisition produces immutable source-slice manifests and canonical gridded-asset metadata. Pure parsing, lifecycle, coordinate, and vector-wire functions are isolated from network and storage transports so they can be verified deterministically before live infrastructure is enabled.

**Tech Stack:** Python 3.12, Pydantic 2, JSON Schema 2020-12, pytest, Ruff, mypy strict, GitHub Actions, Kubernetes NetworkPolicy, ecCodes-compatible GRIB2 metadata.

## Global Constraints

- Normative requirements use RFC 2119/RFC 8174 terminology.
- HTTP behavior follows RFC 9110; errors follow RFC 9457.
- Timestamps use timezone-aware RFC 3339 semantics.
- Observation records and gridded model guidance remain separate types.
- Source evidence is content-addressed using platform-calculated SHA-256.
- `valid_at == initialized_at + lead_seconds` is mandatory.
- Only acquisition workloads may have external provider egress.
- Python branch coverage remains at least 90%; critical Phase-1 modules target 95% or better.
- Every implemented requirement has repository evidence in `specs/verification-map.yaml`.

---

### Task 1: Executable specifications and standards profile

**Files:**
- Create: `specs/data/SPEC-220-gridded-guidance.md`
- Create: `specs/data/SPEC-221-source-slices.md`
- Create: `specs/models/SPEC-320-cycle-publication.md`
- Create: `specs/validation/SPEC-420-weather-scientific-validation.md`
- Create: `specs/architecture/SPEC-120-weather-acquisition-boundary.md`
- Modify: `specs/verification-map.yaml`

**Interfaces:**
- Produces requirement IDs used by code, tests, CI, and traceability.

- [ ] Write specs with unique requirement IDs and planned verification entries.
- [ ] Run `python scripts/validate_specs.py`; expect success after all referenced verification IDs exist.
- [ ] Run `python scripts/generate_traceability.py`; commit the updated generated artifact.

### Task 2: Source-slice typed contract and JSON Schema

**Files:**
- Create: `src/weather_platform/domain/source_manifests.py`
- Create: `schemas/manifests/source-slice.schema.json`
- Create: `tests/unit/test_source_manifests.py`
- Modify: `tests/contract/test_schema_conformance.py`

**Interfaces:**
- Produces: `SourceSliceManifest`, `UpstreamObject`, `ByteSelection`, `SliceVerification`.

- [ ] Write failing tests proving byte ranges are non-negative, inclusive, ordered, bounded by upstream content length, and SHA-256 values use the `sha256:<hex>` form.
- [ ] Run `pytest tests/unit/test_source_manifests.py -q`; expect failure because the module does not exist.
- [ ] Implement Pydantic models with `extra="forbid"` and cross-field validators.
- [ ] Add equivalent JSON Schema constraints and golden valid/invalid contract cases.
- [ ] Run the focused unit and schema tests; expect pass.

### Task 3: Canonical gridded-asset contract

**Files:**
- Create: `src/weather_platform/domain/grid_assets.py`
- Create: `schemas/grids/grid-field-asset.schema.json`
- Create: `tests/unit/test_grid_assets.py`
- Modify: `tests/contract/test_schema_conformance.py`

**Interfaces:**
- Produces: `GridFieldAsset`, `StorageEncoding`, `LongitudeConvention`.
- Consumes: `GuidanceOrigin`, `QualityDisposition`, `Provenance`.

- [ ] Write failing tests for valid-time arithmetic, positive dimensions, ensemble member preservation, allowed storage encodings, and digest validation.
- [ ] Run the focused test and verify the expected import failure.
- [ ] Implement the Pydantic model and schema with matching names and invariants.
- [ ] Add a serialization round-trip test between the typed model and JSON Schema.
- [ ] Run focused and contract tests; expect pass.

### Task 4: Strict GRIB index parser and byte-range selector

**Files:**
- Create: `src/weather_platform/acquisition/__init__.py`
- Create: `src/weather_platform/acquisition/noaa/__init__.py`
- Create: `src/weather_platform/acquisition/noaa/grib_index.py`
- Create: `tests/unit/test_grib_index.py`

**Interfaces:**
- Produces:
  - `parse_grib_index(text: str, *, object_size: int) -> list[GribIndexEntry]`
  - `select_grib_messages(entries, requirements) -> list[SelectedMessage]`
  - `FieldRequirement(name: str, tokens: tuple[str, ...])`

- [ ] Write failing tests for normal NOAA index lines, CRLF input, missing final newline, descending offsets, duplicate offsets, malformed offsets, ambiguous required fields, missing required fields, and final-message range derivation.
- [ ] Run the focused tests and verify missing implementation failure.
- [ ] Implement a strict parser that preserves the original descriptor, derives inclusive byte intervals from adjacent offsets, and rejects non-monotonic or out-of-bounds input.
- [ ] Implement deterministic token-based selection requiring exactly one match per required field.
- [ ] Run focused tests; expect pass.

### Task 5: GFS minimum product manifest and cycle lifecycle

**Files:**
- Create: `src/weather_platform/acquisition/noaa/gfs.py`
- Create: `src/weather_platform/domain/cycle_lifecycle.py`
- Create: `tests/unit/test_gfs_manifest.py`
- Create: `tests/unit/test_cycle_lifecycle.py`

**Interfaces:**
- Produces:
  - `GFS_MINIMUM_FIELDS`
  - `CycleState`
  - `CyclePublicationState`
  - `evaluate_cycle(fields: Collection[ModelCycleField]) -> CyclePublicationState`

- [ ] Write failing tests proving a newer partial cycle is not usable, duplicate fields do not inflate completeness, all minimum fields make a cycle usable, and complete is distinct from minimum usable.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement stable canonical field names and provider-token predicates for 10 m U/V wind, 2 m temperature, 2 m relative humidity, mean sea-level pressure, gust, total cloud cover, and precipitation.
- [ ] Implement lifecycle transitions that reject backwards or illegal transitions.
- [ ] Run focused tests; expect pass.

### Task 6: Geographic and wind-vector scientific invariants

**Files:**
- Create: `src/weather_platform/grids/__init__.py`
- Create: `src/weather_platform/grids/coordinates.py`
- Create: `src/weather_platform/grids/wind.py`
- Create: `tests/unit/test_coordinates.py`
- Create: `tests/unit/test_wind.py`

**Interfaces:**
- Produces:
  - `normalize_longitude(longitude: float) -> float`
  - `wrapped_longitude_distance(a: float, b: float) -> float`
  - `meteorological_direction_to_uv(speed: float, degrees_from: float) -> tuple[float, float]`

- [ ] Write failing cardinal-direction, antimeridian, wrap-idempotence, non-finite-input, and negative-speed tests.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement finite-value validation, `[-180, 180)` normalization, wrapped angular distance, and meteorological direction conversion.
- [ ] Run focused tests; expect pass.

### Task 7: Deterministic binary U/V tile contract

**Files:**
- Create: `src/weather_platform/serving/__init__.py`
- Create: `src/weather_platform/serving/vector_tiles.py`
- Create: `tests/unit/test_vector_tiles.py`

**Interfaces:**
- Produces:
  - `VectorTileHeader`
  - `encode_vector_tile(u, v, *, width, height) -> bytes`
  - `decode_vector_tile(payload: bytes) -> tuple[VectorTileHeader, list[float], list[float]]`

- [ ] Write failing tests for deterministic output, shape mismatch, non-finite values, truncated payloads, cardinal vectors, constant fields, and bounded quantization error.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement a versioned big-endian header, signed 16-bit interleaved samples, explicit scale/offset values, and strict decoder length checks.
- [ ] Run focused tests; expect pass.

### Task 8: Secure deployment manifests

**Files:**
- Create: `deploy/k8s/weather-acquisition.yaml`
- Create: `deploy/k8s/weather-serving-network-policy.yaml`
- Create: `tests/contract/test_weather_deployment_policy.py`

**Interfaces:**
- Produces Kubernetes policy consumed by later Helm/Terraform slices.

- [ ] Write failing YAML-contract tests requiring non-root execution, dropped capabilities, no privilege escalation, read-only root filesystem, explicit resource limits, acquisition-only external egress, and no arbitrary serving egress.
- [ ] Run the focused contract test and verify missing-manifest failure.
- [ ] Implement namespace, ServiceAccount, Deployment/CronJob-compatible acquisition workload, ConfigMap, and NetworkPolicies with explicit DNS, object-store, metadata-store, and provider rules.
- [ ] Run the contract test; expect pass.

### Task 9: Blocking CI workflows and test taxonomy

**Files:**
- Create: `.github/workflows/schema-contract.yml`
- Create: `.github/workflows/scientific-validation.yml`
- Create: `.github/workflows/weather-integration.yml`
- Modify: `Makefile`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces required status contexts:
  - `schema-contract / validate`
  - `scientific-validation / validate`
  - `weather-integration / integration`

- [ ] Add pytest markers for `scientific`, `contract`, `integration`, and `regression` with strict marker validation.
- [ ] Add Make targets that run each gate explicitly.
- [ ] Add pinned-action workflows running Python 3.12 and the ecCodes extra where required.
- [ ] Ensure every workflow has minimal permissions, timeout, concurrency cancellation, and uploaded evidence artifacts.
- [ ] Run workflow syntax and repository validation tests.

### Task 10: Documentation, build status, and release evidence

**Files:**
- Modify: `README.md`
- Modify: `BUILD_STATUS.md`
- Create: `docs/WEATHER_DATA_DEPLOYMENT.md`
- Create: `docs/WEATHER_UI_EXPERIENCE.md`
- Modify: `artifacts/traceability.json`

**Interfaces:**
- Documents implemented behavior, explicit non-implementation, deployment topology, environment progression, SLOs, UI state model, accessibility, rollback, and follow-on slices.

- [ ] Document local fixture-driven validation without claiming live production deployment.
- [ ] Document dev, staging, canary, and production promotion gates.
- [ ] Document UI source/time/provenance rules and reduced-motion/GPU fallbacks.
- [ ] Regenerate traceability and verify it is clean.

### Task 11: Full verification and pull request

**Files:**
- No new implementation files.

- [ ] Run `make validate`.
- [ ] Run `make lint`.
- [ ] Run `make typecheck`.
- [ ] Run `make test`.
- [ ] Run focused schema, scientific, integration, and deployment-policy targets.
- [ ] Confirm branch coverage remains at or above the configured threshold.
- [ ] Inspect the complete diff for secrets, placeholders, schema/type drift, and unsupported completion claims.
- [ ] Open a draft pull request containing requirement IDs, risk analysis, verification evidence, deployment impact, rollback behavior, and explicit follow-on scope.
