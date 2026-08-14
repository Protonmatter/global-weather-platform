# Global Probabilistic Weather Platform

A spec-driven foundation for a live, global, probabilistic Earth-system forecasting platform.

The repository currently implements:

- normative specifications with executable traceability checks;
- canonical observation, forecast, model-cycle, grid-asset, source-slice, and provenance schemas;
- content-addressed raw-source retention and an append-only observation store;
- authoritative attempted/succeeded/failed mutation audit events with request correlation;
- WIS2 notification validation and GRIB2 field-inventory decoding;
- strict NOAA-style GRIB index parsing and deterministic required-field selection;
- GFS minimum-usable and complete product manifests;
- explicit model-cycle readiness states and safe transition rules;
- geographic, meteorological wind-vector, and binary U/V tile invariants;
- a FastAPI control-plane API with OGC EDR-style position queries;
- authenticated raw-evidence retrieval in production;
- a separately deployable Sites operator console with validated upstream destinations;
- baseline probabilistic verification functions;
- deny-by-default production network policy and a separate acquisition trust zone;
- hash-pinned Python dependency locks and digest-bound release rendering;
- CI gates for specifications, schemas, scientific invariants, integration paths, regression tests, security, and release evidence.

## Current scope

This remains **Phase 1 foundation work**. It does not run a numerical weather model and does not yet enable live NOAA acquisition.

RFC-0002 defines the operational path from NOAA GFS/GEFS publication through immutable evidence, canonical gridded assets, cycle publication, OGC API EDR, presentation products, and a future forecast-map application.

The checked-in acquisition Deployment remains at `replicas: 0`. Its image field is a non-deployable zero-digest placeholder that the internal release workflow must replace with an attested `repository@sha256:<digest>` reference. The acquisition command also fails closed until the separately gated downloader, queue, object-store, catalog, transport-trust, and outage tests exist.

See:

- [RFC-0002](rfcs/RFC-0002-operational-weather-data-platform.md)
- [weather data deployment and promotion](docs/WEATHER_DATA_DEPLOYMENT.md)
- [forecast-map UI and experience contract](docs/WEATHER_UI_EXPERIENCE.md)
- [network boundary](docs/NETWORK_BOUNDARY.md)
- [repository posture](docs/REPOSITORY_POSTURE.md)

## Repository posture

The source is publicly viewable and proprietary. Public visibility does not grant an open-source license or permission to copy, modify, redistribute, sublicense, or sell the software. See [LICENSE](LICENSE) and [docs/REPOSITORY_POSTURE.md](docs/REPOSITORY_POSTURE.md).

The repository is currently owned by the `Protonmatter` personal account, so `@Protonmatter` is the enforceable CODEOWNER. Migration to a GitHub organization with real scientific, security, data-architecture, and SRE teams remains the appropriate next governance step.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements/ci.lock
python -m pip install --no-build-isolation --no-deps -e .
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

`POST /v1/source-records` retains raw bytes before decoding them. Canonical observations posted directly to `POST /v1/observations` must reference an already-retained source record; deposit undecoded bytes first with `PUT /v1/source-records/{digest}`.

Production mutations and raw-source retrieval require both the control-plane bearer credential and the trusted `x-weather-actor` identity supplied by the authenticated BFF. Development mode retains the direct local workflow.

## Reproducible dependencies

`requirements/production.lock` and `requirements/ci.lock` are generated with Python 3.12 and the pinned compiler declared in `.github/workflows/python-lock.yml`. Both files contain package hashes. The lock workflow regenerates them and fails when checked files differ.

Regenerate locally with:

```bash
python3.12 -m pip install 'pip==26.1.2' 'pip-tools==7.6.0'
bash scripts/compile_requirements.sh requirements
```

## Weather validation targets

```bash
make weather-contract
make schema-contract
make scientific-validation
make weather-integration
make weather-regression
```

The focused targets use deterministic fixtures and do not call live weather providers. `make test` remains the complete branch-coverage gate.

## Engineering rules

1. Specifications are normative and use RFC 2119/RFC 8174 terminology.
2. Critical requirements require an owner, verification reference, and release gate.
3. Raw source records are immutable; corrected interpretations become new derived records.
4. Observations and gridded model guidance remain separate canonical types.
5. Model initialization time, valid time, and forecast lead are always explicit.
6. Provider ETags are metadata; platform-calculated SHA-256 digests are content identities.
7. Persistent mutations produce authoritative lifecycle audit events before and after state changes.
8. Runtime telemetry is disabled unless an approved internal endpoint is explicitly configured.
9. Production egress is deny-by-default and opened only for documented acquisition workers.
10. Application rollback and model-cycle publication rollback remain independent.

## Operator console

The OpenAI Sites source is maintained in [`apps/operator-console`](apps/operator-console). It is a separate visualization/operator trust zone: FastAPI remains authoritative, while the Site acts as an authenticated BFF and progressive-disclosure console.

The operator console is not the forecast-map application described by RFC-0002.

```bash
make operator-console-install
make operator-console-check
```

Authoritative deployments configure:

- `CONTROL_PLANE_URL` as an HTTPS origin with no path, query, fragment, userinfo, or IP literal;
- `CONTROL_PLANE_ALLOWED_HOSTS` as a non-empty comma-separated DNS suffix allowlist;
- `CONTROL_PLANE_TOKEN` with the same minimum 32-character secret injected into FastAPI as `WEATHER_CONTROL_PLANE_TOKEN`.

The BFF validates the destination before attaching the credential, strips caller authorization and identity headers, supplies only the service credential and verified operator identity, and forwards only an explicit safe response-header set.

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

## License

Publicly viewable proprietary source; no open-source license is granted. See [LICENSE](LICENSE).
