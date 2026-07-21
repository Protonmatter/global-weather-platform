---
spec_id: SPEC-410
title: Probabilistic calibration
status: accepted
owners:
  - probabilistic-modeling
  - independent-verification
standards:
  - NIST-AI-RMF
  - ISO-IEC-5259
requirements:
  - id: MODEL-CAL-0001
    statement: Calibration MUST be trained, tuned, and evaluated on temporally separated datasets.
    priority: critical
    verification: [TEST-SCI-0001]
    release_gate: scientific
  - id: MODEL-CAL-0002
    statement: Ensemble fusion MUST account for model-error dependence and MUST NOT treat correlated variants as independent evidence.
    priority: critical
    verification: [TEST-UNIT-0003]
    release_gate: scientific
  - id: MODEL-CAL-0003
    statement: Forecast probabilities and quantiles MUST satisfy boundedness and monotonicity invariants.
    priority: critical
    verification: [TEST-UNIT-0002]
    release_gate: scientific
---

# Probabilistic calibration

The first implementation provides scoring and invariants. Operational calibration methods will be added behind champion-challenger controls with locked validation datasets and prospective shadow runs.
