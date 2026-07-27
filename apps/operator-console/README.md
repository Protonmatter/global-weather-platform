# Operator console

This application is the separately deployable visualization and operator trust
zone for the Global Probabilistic Weather Platform. It runs on OpenAI Sites
using Vinext and Cloudflare Worker-compatible bindings.

The Python FastAPI service at the repository root remains the authoritative
control plane. Set the server-side `CONTROL_PLANE_URL` runtime variable to proxy
supported API routes to FastAPI. Set `CONTROL_PLANE_TOKEN` to the same
minimum-32-character secret injected into FastAPI as
`WEATHER_CONTROL_PLANE_TOKEN`. The D1/R2 implementation is retained as a
bounded development fallback; it must not become a second source of
meteorological truth.

## Prerequisites

- Node.js `>=22.13.0`
- npm using the committed `package-lock.json`
- Linux or Git Bash with `flock`, `curl`, and GNU `timeout` for the bounded
  install and build wrappers

## Commands

From this directory:

```bash
npm ci
npm run lint
npm run typecheck
npm test
```

`npm test` performs a production build, validates the Sites artifact, and runs
the rendered HTML contract test. Root-level `make operator-console-*` targets
provide the same workflow.

For development:

```bash
npm run dev
```

## Runtime boundaries

- `.openai/hosting.json` binds the existing Site project, D1 database, and R2
  bucket. Keep its opaque project identifier unchanged.
- `CONTROL_PLANE_URL` is runtime configuration and must not be committed.
- `CONTROL_PLANE_TOKEN` is a secret runtime value. Never place it in the Sites
  manifest, source, logs, or audit detail.
- Workspace identity headers are trusted only at the Sites dispatch boundary.
- Mutating routes require an authenticated operator identity.
- The BFF strips caller authorization and identity headers, then supplies its
  service credential and the verified operator identity to FastAPI.
- Third-party telemetry and arbitrary provider egress are not enabled.
- Raw source data belongs in immutable object storage; D1 stores catalog and
  operational metadata.
- Operational GET routes are side-effect free. Synthetic observations and
  model cycles are not seeded by the deployed console.

Migration `0003_quarantine_legacy_fixtures.sql` removes the three previously
hardcoded model cycles and quarantines previously generated `validation-set/*`
observations with an explicit synthetic-fixture flag. Retained raw source bytes
and audit history remain immutable for accountability.

The mutation sequence is explicit: `POST /api/v1/source-records` retains the
bounded raw bytes by digest, then `POST /api/v1/observations` validates the
operator DTO and translates it to the canonical FastAPI schema. The console
never asks FastAPI's decode-and-ingest endpoint to interpret a retention-only
payload. Local edge audit events record authenticated BFF activity; they are
not presented as the authoritative meteorological store.

## Deployment and rollback

Sites deployments are built from a committed source revision and saved as
versioned releases. Deploy through the Sites workflow, not by creating an
independent Site. Roll back by redeploying the preceding saved Site version.

The current application provides observation ingestion, model-cycle status,
audit history, OGC EDR-style position queries, provenance, and quarantine-aware
operator views. It is not the deferred probabilistic forecast shell described
by `UX-001`.

## Source provenance

This application was imported from Global Weather Platform Site version 2 at
source commit `0d9bb9b286f92b53cf3b647525c277428ffd8a24`. The opaque project
binding in `.openai/hosting.json` preserves continuity with the existing
versioned deployment.
