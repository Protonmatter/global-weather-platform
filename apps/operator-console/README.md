# Operator console

This application is the separately deployable visualization and operator trust
zone for the Global Probabilistic Weather Platform. It runs on OpenAI Sites
using Vinext and Cloudflare Worker-compatible bindings.

The Python FastAPI service at the repository root remains the authoritative
control plane. Set the server-side `CONTROL_PLANE_URL` runtime variable to proxy
supported API routes to FastAPI. The D1/R2 implementation is retained as a
bounded edge prototype and local fallback; it must not become a second source
of meteorological truth.

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
- Workspace identity headers are trusted only at the Sites dispatch boundary.
- Mutating routes require an authenticated operator identity.
- Third-party telemetry and arbitrary provider egress are not enabled.
- Raw source data belongs in immutable object storage; D1 stores catalog and
  operational metadata.

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
