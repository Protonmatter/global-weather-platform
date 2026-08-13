# Global Probabilistic Weather Platform

A spec-driven foundation for a live, global, probabilistic Earth-system forecasting platform.

The repository currently implements:

- normative specifications with executable traceability checks;
- canonical observation, forecast, model-cycle, grid-asset, source-slice, and provenance schemas;
- an append-only observation store with content-addressed raw source retention;
- WIS2 notification validation and GRIB2 field-inventory decoding;
- strict NOAA-style GRIB index parsing and deterministic required-field selection;
- GFS minimum-usable and complete product manifests;
- explicit model-cycle publication states and safe promotion rules;
- geographic, meteorological wind-vector, and binary U/V tile invariants;
- a FastAPI control-plane API with OGC EDR-style position queries;
- a separately deployable Sites operator console for authenticated observation and provenance workflows;
- baseline probabilistic verification functions;
- deny-by-default production network policy and a separate acquisition trust zone;
- CI gates for specifications, schemas, scientific invariants, integration paths, regression tests, security, and release evidence.

## Current scope

This is **Phase 1 foundation work**. It does not run a numerical weather model and does not yet enable live NOAA acquisition.

RFC-0002 defines the operational path from NOAA GFS/GEFS publication through immutable evidence, canonical gridded assets, cycle publication, OGC API EDR, presentation products, and a future forecast-map application.

The implemented Phase-1 slice establishes the contracts and deterministic logic needed before live transport and production persistence are enabled:

```text
provider GRIB index
  -> strict field and byte-range selection
  -> immutable source-slice manifest
  -> canonical grid-asset metadata
  -> cycle completeness and publication eligibility
  -> deterministic scientific/presentation wire contracts
```

The checked-in acquisition Deployment remains at `replicas: 0`. The `weather-platform-acquisition --require-live-transport` command fails closed until the separately gated downloader, queue, object-store, catalog, transport-trust, and outage tests exist.

See:

- [RFC-0002](rfcs/RFC-0002-operational-weather-data-platform.md)
- [weather data deployment and promotion](docs/WEATHER_DATA_DEPLOYMENT.md)
- [forecast-map UI and experience contract](docs/WEATHER_UI_EXPERIENCE.md)
- [network boundary](docs/NETWORK_BOUNDARY.md)

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,eccodes]'
make validate
make test
make run
```

The API starts at `http://127.0.0.1:8080`.

```bash
curl -s http://127.0.0.1:8080/healthz
curl -s -X POST http://127.0.0.1:8080/v1/source-records \
  -H 'content-type: application/json' \
  --data-binary @testdata/observations/temperature.json
curl -s 'http://127.0.0.1:8080/v1/observations?phenomenon=air_temperature'
```

`POST /v1/source-records` retains the raw record before decoding it. Canonical observations posted directly to `POST /v1/observations` must reference an already-retained source record; deposit undecoded bytes first with `PUT /v1/source-records/{digest}`.

## Weather validation targets

Focused gates can be run independently:

```bash
make weather-contract
make schema-contract
make scientific-validation
make weather-integration
make weather-regression
```

The focused targets use deterministic fixtures and do not call live weather providers. `make test` remains the complete branch-coverage gate.

The fixture-driven integration path proves:

```text
GRIB index
  -> selected required messages
  -> bounded source manifest
  -> usable/complete cycle evaluation
  -> canonical grid asset
  -> binary U/V tile encode/decode
```

## Engineering rules

1. Specifications are normative and use RFC 2119/RFC 8174 terminology.
2. Critical requirements require an owner, verification reference, and release gate.
3. Raw source records are immutable; corrected interpretations become new derived records.
4. Observations and gridded model guidance remain separate canonical types.
5. Model initialization time, valid time, and forecast lead are always explicit.
6. Provider ETags are metadata; platform-calculated SHA-256 digests are content identities.
7. Runtime telemetry is disabled unless an internal endpoint is explicitly configured.
8. Production egress is deny-by-default and opened only for documented acquisition workers.
9. Scientific changes require declared baselines, locked validation data, and independent review.
10. Application rollback and model-cycle publication rollback remain independent.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [docs/NETWORK_BOUNDARY.md](docs/NETWORK_BOUNDARY.md).

## Operator console

The recovered ChatGPT Site source is maintained in [`apps/operator-console`](apps/operator-console). It is a separate visualization/operator trust zone: FastAPI remains authoritative, while the Site acts as an authenticated BFF and progressive-disclosure console.

The operator console is not the forecast-map application described by RFC-0002.

```bash
make operator-console-install
make operator-console-check
```

The console retains its existing Sites project binding so deployments from this repository update the same versioned Site. See [`apps/operator-console/README.md`](apps/operator-console/README.md) and [`adrs/ADR-0002-operator-console-trust-zone.md`](adrs/ADR-0002-operator-console-trust-zone.md).

Authoritative deployments inject the same randomly generated, minimum 32-character service secret as `CONTROL_PLANE_TOKEN` in Sites and `WEATHER_CONTROL_PLANE_TOKEN` in FastAPI. The secret is never committed. Sites removes caller-supplied authorization and identity headers, requires the verified workspace identity for mutations, and forwards only its service token and the verified operator identity. Production containers set `WEATHER_ENVIRONMENT=production` and fail startup unless that token is injected.

## Explicit next implementation slices

The following remain separate, reviewable work:

- live NOAA NODD HTTP/S3 range acquisition and event delivery;
- production object storage, PostgreSQL catalog, and Zarr persistence;
- complete numeric GRIB field extraction and canonical-array writing;
- OGC EDR area/cube access and tile/map-manifest services;
- GEFS member ingestion and denominator-aware probability products;
- model-versus-observation verification and calibration;
- `apps/forecast-map` with accessible reduced-motion and non-WebGL fallbacks;
- optional cached OpenWeather point-condition and alert enrichment;
- load, resilience, staging replay, canary, and disaster-recovery qualification.

## Publish the initial private GitHub repository

The repository is initialized on `main`. From an authenticated workstation with the GitHub CLI:

```bash
./scripts/publish_github.sh
```

Defaults:

- Owner: `Protonmatter`
- Repository: `global-weather-platform`
- Visibility: `private`

Override these with `GITHUB_OWNER`, `GITHUB_REPOSITORY_NAME`, or `GITHUB_VISIBILITY`.

## License

Proprietary and confidential — see [LICENSE](LICENSE). This is a placeholder proprietary notice matching the repository's private posture; replace it with the copyright holder's chosen terms, including an open-source license, if and when the platform is licensed for wider distribution.
