# ADR-0002: Operator console trust zone

**Status:** Accepted
**Owners:** Platform Architecture, Platform SRE, Product Security

## Context

The platform needs authenticated operational workflows and progressive
disclosure for provenance, observation quality, model-cycle completeness, and
OGC EDR queries. Implementing these concerns inside the Python control-plane
service would couple presentation deployment to authoritative weather-domain
logic. Maintaining a separate edge backend without a declared boundary would
instead create competing sources of truth.

## Decision

Maintain `apps/operator-console` as a separately deployable visualization and
operator trust zone.

- FastAPI remains authoritative for weather-domain semantics and canonical
  control-plane operations.
- The Site is a backend-for-frontend for authentication, response shaping, and
  operator workflows.
- Production deployments configure `CONTROL_PLANE_URL` server-side and fail
  closed when it is missing. Local D1/R2 routing requires the explicit
  development-only `CONTROL_PLANE_MODE=local-development` binding.
- Production deployments inject a shared service credential through
  `CONTROL_PLANE_TOKEN` in Sites and `WEATHER_CONTROL_PLANE_TOKEN` in FastAPI.
  FastAPI refuses production startup without it.
- The BFF allowlists forwarded headers, discards caller authorization and
  identity claims, and forwards only the verified Sites actor with the service
  credential on mutations.
- The Site-local D1/R2 path is a bounded prototype and explicit development
  fallback; it is not selected implicitly by missing production configuration.
- A failed Site-local audit write after a successful authoritative mutation is
  logged without operator or resource identifiers and surfaced through a
  response header without changing the successful upstream status.
- Sites identity headers are trusted only at the verified dispatch boundary.
- The existing opaque Sites project binding remains versioned with the source.
- The probabilistic forecast shell in `UX-001` remains deferred until real
  forecast products and WCAG 2.2 AA acceptance evidence exist.

## Consequences

The repository gains a Node.js build and an independently deployable artifact.
Contract drift between Python schemas and TypeScript types remains a release
risk. Until generated contracts replace the manually versioned TypeScript
contract, cross-runtime golden tests and BFF response-shaping tests are release
gates.

## Rollback

Remove the operator-console application and its CI gate without changing the
Python API or data contracts. A deployed Site can be rolled back independently
to its preceding saved version.
