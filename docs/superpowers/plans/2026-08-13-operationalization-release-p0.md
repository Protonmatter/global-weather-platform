# Operationalization Release P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task.

**Goal:** Harden dependency resolution, trust boundaries, auditability, evidence access, and deployment identity before live acquisition.

**Architecture:** FastAPI remains authoritative, Sites remains the authenticated BFF, Python dependencies become hash locked, and release manifests are rendered from immutable image references.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, pip-tools 7.6.0, TypeScript, GitHub Actions, Kubernetes.

## Tasks

1. **Repository posture and ownership**
   - Update `LICENSE`, `README.md`, `.github/CODEOWNERS`, and add `docs/REPOSITORY_POSTURE.md`.
   - Preserve proprietary rights while accurately stating that the repository is publicly viewable.

2. **Python dependency locks**
   - Add production and CI hash-pinned lock files.
   - Add `scripts/compile_requirements.sh` and a lock-freshness workflow.
   - Install CI and build dependencies from locks with hash enforcement.

3. **Authoritative audit ledger**
   - Add frozen mutation-audit domain records and a flock-backed append-only store.
   - Add request IDs and attempted/succeeded/failed lifecycle events to persistent mutations.

4. **Raw evidence authorization**
   - Require service authentication and trusted actor identity for raw source-record retrieval.

5. **Sites upstream validation**
   - Require HTTPS and an explicit hostname allowlist in remote mode.
   - Permit HTTP only for loopback local development.
   - Forward only an explicit safe response-header set.

6. **Immutable release image**
   - Replace mutable deployment tags with a zero-digest source placeholder.
   - Add a renderer that requires a real `repository@sha256:<64-hex>` image reference.
   - Publish rendered deployment and release metadata as build evidence.

7. **Validation**
   - Add unit, contract, integration, and operator-console tests.
   - Run every existing required workflow and update `BUILD_STATUS.md` with exact evidence.
   - Open a draft PR against `main`.
