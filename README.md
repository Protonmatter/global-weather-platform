# Global Probabilistic Weather Platform

A spec-driven foundation for a live, global, probabilistic Earth-system forecasting platform.

This repository implements the first vertical slice:

- normative specifications with executable traceability checks;
- canonical observation, forecast, event, and provenance schemas;
- an immutable SHA-256 raw object store and append-only observation store;
- a FastAPI control-plane API;
- baseline probabilistic verification functions;
- deny-by-default Kubernetes egress policy;
- CI gates for specifications, schemas, tests, security, and release evidence.

## Current scope

This is **Phase 0 / early Phase 1**. It does not yet run a numerical weather model. It establishes the contracts and controls required before operational ingestion, assimilation, ensemble fusion, or model promotion.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
make validate
make test
make run
```

The API starts at `http://127.0.0.1:8080`.

```bash
curl -s http://127.0.0.1:8080/healthz
curl -s -X POST http://127.0.0.1:8080/v1/observations \
  -H 'content-type: application/json' \
  --data @testdata/observations/temperature.json
curl -s 'http://127.0.0.1:8080/v1/observations?phenomenon=air_temperature'
```

## Engineering rules

1. Specifications are normative and use RFC 2119/RFC 8174 terminology.
2. Critical requirements require an owner, verification reference, and release gate.
3. Raw source records are immutable, SHA-256-addressed, and retained before decoding; corrected interpretations become new derived records.
4. Runtime telemetry is disabled unless an internal endpoint is explicitly configured.
5. Production egress is deny-by-default and opened only for documented acquisition workers.
6. Scientific changes require declared baselines, locked validation data, and independent review.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/RAW_OBJECT_STORE.md](docs/RAW_OBJECT_STORE.md), and [docs/NETWORK_BOUNDARY.md](docs/NETWORK_BOUNDARY.md).

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
