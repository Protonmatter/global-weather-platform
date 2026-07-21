---
spec_id: SPEC-800
title: Validation plan
status: accepted
owners:
  - independent-verification
  - quality-engineering
standards:
  - ISO-IEC-25010
  - NIST-AI-RMF-MEASURE
requirements:
  - id: VAL-BASE-0001
    statement: Every candidate forecast method MUST be compared with declared operational, persistence, and climatological baselines when applicable.
    priority: critical
    verification: [TEST-SCI-0001]
    release_gate: scientific
  - id: VAL-SLICE-0002
    statement: Validation MUST report skill by lead time, region, season, regime, event magnitude, and observation density where sample size permits.
    priority: critical
    verification: [REPORT-SCORECARD-0001]
    release_gate: scientific
  - id: VAL-LEAK-0003
    statement: Historical evaluation MUST prevent use of data unavailable at the simulated forecast issuance time.
    priority: critical
    verification: [TEST-SCI-0002]
    release_gate: scientific
---

# Validation plan

Validation combines software tests, numerical benchmarks, proper scoring rules, uncertainty intervals, golden events, prospective shadow operation, and independent approval.
