# Operationalization Release P0 — Design

**Status:** Approved for implementation  
**Date:** 2026-08-13

## Goal

Harden the Phase-1 weather platform before live provider acquisition or broader deployment.

## Scope

1. Align documentation with the repository's publicly viewable, proprietary-source posture.
2. Replace non-functional CODEOWNERS entries with the repository owner until organization teams exist.
3. Add hash-pinned Python production and CI lock files generated with Python 3.12 and pip-tools 7.6.0.
4. Add a Python-side append-only authoritative mutation audit ledger.
5. Require control-plane authentication for raw source-record retrieval.
6. Validate the Sites `CONTROL_PLANE_URL` against HTTPS and an explicit hostname allowlist before adding the service credential.
7. Forward only an explicit safe set of upstream response headers.
8. Replace mutable deployment image tags with a release-rendered immutable digest reference.

## Audit design

Each persistent mutation records immutable events with a unique event ID, request ID, actor, action, resource type, resource ID, result, timestamp, software version, and sanitized detail. The control plane records `attempted` before changing state and records `succeeded` or `failed` before returning.

## Control-plane destination rules

Remote mode requires HTTPS, no userinfo, no query or fragment, no non-root path, a DNS hostname rather than an IP literal, and an exact or subdomain match against `CONTROL_PLANE_ALLOWED_HOSTS`. Local development may use HTTP only for loopback hosts.

## Release identity

The checked-in acquisition manifest contains a documented zero-digest placeholder, never a mutable tag. Release automation requires a real `repository@sha256:<64-hex>` reference, renders the deployable manifest, and publishes release metadata as workflow evidence.

## Acceptance criteria

- Dependency security PR #27 is merged.
- Python installs and builds use hash-pinned lock files.
- Persistent mutations produce authoritative audit lifecycle events.
- Raw source reads fail closed without service authentication and actor identity.
- Invalid control-plane destinations are rejected before credentials are attached.
- Rendered deployment output contains the exact release image digest.
- Existing and new CI gates pass on the exact PR head.

## Exclusions

No live NOAA acquisition, production PostgreSQL/S3/Zarr migration, scoped OAuth implementation, public forecast-map client, or numerical model execution is included.
