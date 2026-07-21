---
spec_id: SPEC-000
title: Program charter
status: accepted
owners:
  - program-governance
  - scientific-director
standards:
  - RFC-2119
  - RFC-8174
  - NIST-AI-RMF
requirements:
  - id: PROG-GOV-0001
    statement: The platform MUST distinguish official warnings, imported guidance, platform-generated operational guidance, and experimental output.
    priority: critical
    verification: [TEST-CONTRACT-0001]
    release_gate: governance
  - id: PROG-GOV-0002
    statement: Every production forecast product MUST bind software, model, configuration, calibration, schema, source policy, and validation evidence into one release unit.
    priority: critical
    verification: [TEST-TRACE-0001]
    release_gate: governance
---

# Program charter

The program builds a continuously updated, provenance-preserving, probabilistic Earth-system forecasting platform. Initial releases consume authoritative observations and external forecast guidance while establishing the controls required for data assimilation, regional numerical modeling, AI forecasting, and coupled-system prediction.
