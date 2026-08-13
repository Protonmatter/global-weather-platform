# Weather data deployment and promotion

This document defines the deployment contract for the operational-weather work introduced by RFC-0002. It distinguishes the Phase-1 implementation that exists in this repository from the live provider, persistence, and serving components that remain gated follow-on work.

## Current deployment state

Phase 1 implements and verifies:

- immutable provider byte-slice manifests;
- canonical gridded-field metadata;
- strict NOAA GRIB index parsing and field selection;
- GFS minimum-usable and complete field manifests;
- model-cycle publication-state evaluation;
- longitude and meteorological wind-vector invariants;
- deterministic binary U/V tile serialization;
- acquisition and serving network-policy contracts;
- a fail-closed acquisition command;
- schema, scientific, integration, regression, and deployment-policy CI gates.

Phase 1 does **not** enable live NOAA acquisition. The checked-in acquisition Deployment has `replicas: 0`, and `weather-platform-acquisition --require-live-transport` exits with a configuration error. This prevents a policy scaffold from being mistaken for an operational feed.

## Target runtime topology

```text
NOAA GFS / GEFS      WIS2 observations      OpenWeather enrichment
        \                    |                       /
         \                   |                      /
          +---- provider-isolated acquisition workers ----+
                                   |
                            immutable source bytes
                            source-slice manifests
                                   |
                          decoder and scientific QC
                                   |
                  canonical arrays and metadata catalog
                                   |
               +-------------------+-------------------+
               |                                       |
          OGC API EDR                           presentation builder
               |                                       |
        scientific queries                    scalar/vector tile assets
               |                                       |
               +-------------------+-------------------+
                                   |
                           forecast-map application
```

Only acquisition workloads may connect to provider endpoints. Forecast APIs, tile builders, calibration workers, verification workers, and user interfaces consume internal stores.

## Trust zones

### `weather-ingestion`

Purpose:

- discover provider objects or receive publication notifications;
- retrieve indexes and bounded source byte ranges;
- validate transport and source integrity;
- retain source evidence before interpretation;
- submit canonical metadata to internal stores.

Required controls:

- non-root execution;
- `RuntimeDefault` seccomp;
- all Linux capabilities dropped;
- privilege escalation disabled;
- read-only root filesystem;
- bounded temporary storage and memory/CPU limits;
- workload identity rather than static object-store credentials;
- provider destinations declared through an egress gateway or equivalent FQDN-aware policy;
- credentials excluded from process arguments, logs, traces, metrics, manifests, and provenance.

The Phase-1 Cilium policy names NOAA GFS, NOAA GEFS, and OpenWeather endpoints as the intended external destinations. A production deployment must separately declare internal object-store, catalog, queue, and time-service addresses for its environment.

### `weather-data`

Purpose:

- immutable source-object storage;
- canonical array storage;
- PostgreSQL metadata and lineage catalog;
- queue and event state.

Required authorization separation:

```text
acquisition worker  -> create raw objects and manifests; no delete
normalizer          -> read raw, create normalized objects; no raw delete
tile builder        -> read normalized, create presentation assets
forecast API        -> read catalog and published assets only
verification worker -> read forecasts and observations, write scorecards
```

### `weather-serving`

Purpose:

- OGC API EDR;
- model-cycle and provenance APIs;
- map manifests and immutable presentation assets;
- forecast-map backend-for-frontend where required.

The namespace is deny-by-default. Production policy must add only named ingress and internal data dependencies. It must not add arbitrary provider Internet access.

## Environment progression

```text
developer fixture
  -> pull-request integration
  -> shared integration
  -> staging replay
  -> prospective scientific validation
  -> production canary
  -> production
```

### Developer fixture

Required command set:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,eccodes]'
make validate
make weather-contract
make schema-contract
make scientific-validation
make weather-integration
make test
```

Development tests use deterministic indexes, manifests, fields, and vector tiles. They do not depend on live NOAA output.

### Pull-request integration

Blocking gates:

- `pr-fast / quality` — Ruff, formatting, strict mypy, complete test suite, branch coverage;
- `spec-validation / validate` — specification schema, unique IDs, verification evidence, generated traceability;
- `schema-contract / validate` — JSON Schema and Kubernetes deployment contracts;
- `scientific-validation / validate` — coordinate, time, vector, probability, and regression invariants;
- `weather-integration / integration` — fixture path from GRIB index through published scientific wire products;
- `weather-contract / validate` — focused Phase-1 contract suite.

### Shared integration

A later live-transport slice must provision disposable equivalents of:

- S3-compatible object storage;
- PostgreSQL;
- queue/event delivery;
- acquisition worker;
- normalizer;
- API and tile service.

The integration test must prove:

```text
publication event
  -> deduplicated acquisition
  -> retained source and manifest
  -> hash/range verification
  -> decoder output
  -> canonical grid asset
  -> cycle-state transition
  -> EDR sample
  -> presentation tile
```

### Staging replay

Staging promotion requires replay of locked GFS and GEFS cycles. The same source bytes and decoder version must produce identical canonical identities and equivalent numeric arrays within declared tolerances.

Required exercises:

- complete cycle;
- partial cycle;
- duplicate notification;
- missing ensemble member;
- truncated source object;
- invalid index;
- provider timeout and retry exhaustion;
- stale-cycle serving;
- antimeridian and polar sampling;
- data alias rollback;
- application rollback.

### Production canary

Software and data publication are separate promotions.

Software canary progression:

```text
5% -> 25% -> 50% -> 100%
```

A model cycle progresses independently:

```text
DISCOVERED
  -> INDEX_AVAILABLE
  -> DOWNLOADING
  -> PARTIAL
  -> MINIMUM_USABLE
  -> COMPLETE
```

A cycle can also become `QUARANTINED`, `SUPERSEDED`, or `EXPIRED`. The default user-facing alias resolves to the newest `MINIMUM_USABLE` or `COMPLETE` cycle; arrival of a newer incomplete cycle does not replace it.

## Persistence contract

### Raw evidence

Recommended path:

```text
raw/{provider}/{dataset}/{yyyy}/{mm}/{dd}/{sha256}
```

Properties:

- content addressed;
- immutable or object-locked;
- encrypted at rest;
- source manifest stored separately from provider-supplied metadata;
- lifecycle policy based on reproducibility requirements;
- no public access.

Provider ETags are retained as metadata but are not treated as cryptographic identities. The platform SHA-256 digest remains authoritative.

### Canonical arrays

The target normalized representation is Zarr v3 or an equivalently reviewable multidimensional format. Logical dimensions include:

```text
model, cycle, valid_time, member, level, latitude, longitude
```

Chunking is a product decision and must be benchmarked against:

- point and area EDR queries;
- valid-time playback;
- ensemble extraction;
- tile generation;
- verification and replay.

### Metadata catalog

PostgreSQL should contain identities and lineage rather than full global arrays. Core tables should cover providers, datasets, source records, manifests, cycles, cycle fields, grid definitions, grid assets, derived products, verification runs, quarantine events, and release evidence.

## Configuration and secrets

Expected production settings will include provider enablement, dataset/product identifiers, required-field manifests, source-size bounds, queue endpoints, internal stores, and publication thresholds.

Rules:

- no provider key in Git, images, browser bundles, source URIs, logs, traces, or metrics labels;
- short-lived workload credentials where supported;
- secret rotation independent from application image rollout;
- OpenWeather disabled unless a key and quota policy are explicitly supplied;
- NOAA public-data access still passes through transport-integrity and egress controls.

## Observability

Minimum metrics:

```text
weather_acquisition_lag_seconds
weather_cycle_age_seconds
weather_cycle_completeness_ratio
weather_source_download_failures_total
weather_source_integrity_failures_total
weather_decode_duration_seconds
weather_decode_failures_total
weather_quarantined_assets_total
weather_edr_latency_seconds
weather_tile_latency_seconds
weather_tile_cache_hit_ratio
```

Minimum structured fields:

```text
provider
dataset
model_id
cycle
valid_time
forecast_hour
source_digest
normalized_digest
run_id
quality_disposition
```

Do not put credentials, complete signed URLs, or unbounded provider payloads in telemetry.

## Initial service objectives

These are proposed targets to validate before production commitment:

| Capability | Proposed objective |
|---|---:|
| Forecast API availability | 99.9% |
| Published-cycle corruption | 0 tolerated |
| Provenance coverage of displayed values | 100% |
| Cached metadata/API p95 | < 250 ms |
| Point/position query p95 | < 500 ms |
| Cached tile p95 | < 250 ms |
| Uncached tile p95 | < 1.5 s |

A provider outage may reduce freshness or availability. It must not alter source identity, time semantics, or stored values.

## Rollback

### Application rollback

Revert the active image digest and configuration release. Do not mutate retained scientific evidence.

### Data rollback

Move the serving alias from a failed cycle to the previous usable cycle. Keep the failed cycle and its quarantine evidence for investigation.

### Decoder rollback

Re-enable the prior decoder version and regenerate derived objects from immutable source bytes. A new decoder interpretation receives a new derived identity; existing evidence is not overwritten.

## Live-transport activation gate

The acquisition Deployment must remain at zero replicas until all of the following exist:

- tested HTTP/S3 range downloader;
- queue/poll discovery adapter;
- issuer/transport trust integration;
- payload length and digest verification;
- bounded retries and idempotency keys;
- object-store and catalog adapters;
- provider outage and stale-cycle integration tests;
- secret-redaction tests;
- operational dashboards and alerts;
- staging replay evidence;
- approved production egress policy.
