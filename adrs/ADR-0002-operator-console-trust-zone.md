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
- Production deployments configure `CONTROL_PLANE_URL` server-side.
- The Site-local D1/R2 path is a bounded prototype and development fallback.
- Sites identity headers are trusted only at the verified dispatch boundary.
- The existing opaque Sites project binding remains versioned with the source.
- The probabilistic forecast shell in `UX-001` remains deferred until real
  forecast products and WCAG 2.2 AA acceptance evidence exist.

## Consequences

The repository gains a Node.js build and an independently deployable artifact.
Contract drift between Python schemas and TypeScript types remains a release
risk until generated contracts and a drift gate replace the current manually
versioned TypeScript contract.

## Rollback

Remove the operator-console application and its CI gate without changing the
Python API or data contracts. A deployed Site can be rolled back independently
to its preceding saved version.
