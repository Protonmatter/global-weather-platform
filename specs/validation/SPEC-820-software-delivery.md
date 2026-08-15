---
spec_id: SPEC-820
title: Software delivery and dependency integrity
status: implemented
owners:
  - quality-engineering
  - site-reliability-engineering
standards:
  - RFC-2119
  - RFC-8174
  - NIST-SSDF-1.1
  - SLSA-1.0
requirements:
  - id: DEL-SPEC-0001
    statement: Every production change MUST trace normative requirements to repository-resident verification evidence before release construction.
    priority: critical
    verification: [TEST-DELIVERY-0001]
    release_gate: governance
  - id: DEL-CI-0002
    statement: The continuous integration gate MUST validate specifications, dependency integrity, Python quality, operator-console quality, contracts, scientific invariants, integration paths, and end-to-end behavior for the exact candidate revision.
    priority: critical
    verification: [TEST-DELIVERY-0002]
    release_gate: engineering
  - id: DEL-END-0003
    statement: End-to-end verification MUST cross the built operator-console worker, authenticated control-plane HTTP boundary, canonical persistence, read API, and authoritative audit ledger without live provider dependencies.
    priority: critical
    verification: [TEST-E2E-0001]
    release_gate: operational
  - id: DEL-CD-0004
    statement: Release construction MUST depend on a successful complete continuous integration gate for the same Git commit and MUST emit immutable signed release evidence before any environment promotion.
    priority: critical
    verification: [TEST-DELIVERY-0003]
    release_gate: operational
  - id: DEL-DEP-0005
    statement: Runtime and CI dependency graphs MUST be installed from committed integrity-checked locks, release dependency resolution MUST exclude inherited secondary package sources and use only the approved internal mirror, direct compatibility ranges MUST be bounded, build runtimes and automation actions MUST be pinned, and automated version updates MUST pass the complete delivery gate.
    priority: critical
    verification: [TEST-DEPS-0001]
    release_gate: security
---

# Software delivery and dependency integrity

The repository uses specifications as the first delivery artifact. A candidate
revision is releasable only when its requirement registry and generated
traceability artifact are current and the same revision passes the complete CI
fan-out.

The end-to-end lane uses deterministic local evidence. It starts the production
FastAPI application as a separate process, sends authenticated requests through
the built operator-console Worker, and verifies canonical reads plus authoritative
audit lifecycle events. It does not contact weather providers or production
services.

Python application manifests declare bounded compatibility ranges while release
and CI installation use exact SHA-256-checked lock graphs. JavaScript direct
dependencies are exact, the npm lock retains registry integrity values, language
runtimes are repository-pinned, and third-party workflow actions use immutable
commit references. Release installation uses a job-local Python environment,
an isolated pip client, an explicit approved index, and a generated configuration
that clears inherited extra indexes and find-links sources. Scheduled dependency
pull requests are grouped by ecosystem; major upgrades remain deliberate
specification changes.

Continuous delivery constructs, scans, signs, and attests an immutable image only
after the complete reusable CI gate succeeds for the same workflow revision.
Production activation remains a separate protected-environment decision and is
not implied by release construction.
