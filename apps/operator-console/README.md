# Operator console

This application is the separately deployable visualization and operator trust zone for the Global Probabilistic Weather Platform. It runs on OpenAI Sites using Vinext and Cloudflare Worker-compatible bindings.

The Python FastAPI service remains the authoritative control plane. The D1/R2 implementation is a bounded development fallback and must not become a second source of meteorological truth.

## Authoritative runtime configuration

A deployed Site requires:

```text
CONTROL_PLANE_URL=https://api.weather.example
CONTROL_PLANE_ALLOWED_HOSTS=weather.example
CONTROL_PLANE_TOKEN=<same minimum-32-character value as WEATHER_CONTROL_PLANE_TOKEN>
```

`CONTROL_PLANE_URL` must:

- use HTTPS outside local loopback development;
- identify an origin only, with no userinfo, non-root path, query, or fragment;
- use a DNS hostname rather than an IP literal;
- exactly match, or be a subdomain of, one entry in the comma-separated `CONTROL_PLANE_ALLOWED_HOSTS` list.

The destination is validated before the BFF attaches the bearer credential. Responses are reconstructed using an explicit safe header set; cookies and internal/debug headers are not forwarded, and redirect locations are limited to same-origin path references with exactly one leading slash.

The local Vite configuration injects `CONTROL_PLANE_MODE=local-development`. In that mode, HTTP is allowed only for `localhost`, `127.0.0.1`, or `::1`. Do not configure `local-development` on a deployed Site.

## Prerequisites

- Node.js `>=22.13.0`
- npm using the committed `package-lock.json`
- Linux or Git Bash with `flock`, `curl`, and GNU `timeout`

## Commands

```bash
npm ci
npm run lint
npm run typecheck
npm test
```

`npm test` runs unit contracts, a production build, Sites artifact validation, and rendered HTML tests. Root-level `make operator-console-*` targets provide the same workflow.

For development:

```bash
npm run dev
```

## Trust boundaries

- `.openai/hosting.json` preserves the existing Site, D1, and R2 project bindings.
- Runtime URLs, host allowlists, and credentials are deployment configuration and must not be committed as production values.
- `CONTROL_PLANE_TOKEN` must never appear in source, manifests, logs, traces, audit detail, or browser JavaScript.
- Workspace identity headers are trusted only at the Sites dispatch boundary.
- Mutating routes require an authenticated operator identity.
- The BFF discards caller-supplied authorization and identity headers, then supplies only its service credential and verified operator identity to FastAPI.
- Raw source data belongs in immutable authoritative storage; D1 stores edge catalog and operational metadata only.
- Operational GET routes are side-effect free.
- Third-party telemetry and arbitrary provider egress are not enabled.

## Mutation and audit behavior

The mutation sequence is explicit:

1. `POST /api/v1/source-records` hashes and retains bounded source bytes through the authoritative control plane.
2. `POST /api/v1/observations` validates the operator DTO and translates it to the canonical FastAPI schema.
3. FastAPI writes authoritative `attempted` and terminal `succeeded` or `failed` mutation events bound to one request UUID.
4. The Sites edge records a supplementary best-effort audit event.

If edge audit persistence fails after an upstream success, the BFF preserves the authoritative success and returns `x-weather-edge-audit-status: failed`. Edge audit is supplemental; the FastAPI audit ledger is authoritative.

Raw source-record retrieval is also protected by the control-plane service credential and trusted actor identity. Knowing a content digest is not authorization.

## Deployment and rollback

Sites deployments are built from committed source revisions and saved as versioned releases. Deploy through the existing Sites workflow. Roll back by redeploying the preceding saved Site version.

The application provides observation ingestion, model-cycle status, audit history, OGC EDR-style position queries, provenance, and quarantine-aware operator views. It is not the deferred probabilistic forecast shell described by `UX-001`.

## Source provenance

This application was imported from Global Weather Platform Site version 2 at source commit `0d9bb9b286f92b53cf3b647525c277428ffd8a24`. The opaque project binding in `.openai/hosting.json` preserves continuity with the existing versioned deployment.
