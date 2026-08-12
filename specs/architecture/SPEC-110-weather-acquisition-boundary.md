---
spec_id: SPEC-110
title: Weather acquisition trust boundary
status: review
owners:
  - platform-architecture
  - security
  - sre
standards:
  - RFC-8446
  - NIST-SSDF-1.1
  - KUBERNETES-NETWORKPOLICY
requirements:
  - id: SEC-EGRESS-0001
    statement: Only approved acquisition workloads MAY establish external provider connections; serving, forecast, calibration, and visualization workloads MUST NOT have arbitrary Internet egress.
    priority: critical
    verification: [TEST-DEPLOY-0001]
    release_gate: security
  - id: SEC-WORKLOAD-0002
    statement: Weather acquisition workloads MUST run as non-root, MUST drop Linux capabilities, MUST prohibit privilege escalation, and SHOULD use a read-only root filesystem.
    priority: critical
    verification: [TEST-DEPLOY-0001]
    release_gate: security
  - id: SEC-SECRET-0003
    statement: Provider credentials MUST NOT be delivered to browser clients or recorded in source data, provenance, logs, traces, metrics labels, or release evidence.
    priority: critical
    verification: [TEST-SECRET-0001]
    release_gate: security
---

# Weather acquisition trust boundary

External weather providers are isolated behind acquisition workers. Downstream services consume retained internal objects and catalogs rather than making provider calls. Production egress policy is deny-by-default and provider access is explicitly declared.

The Phase-1 deployment contract uses a Cilium FQDN policy for provider names and a Kubernetes default-deny policy for serving workloads. Deployments that do not use Cilium MUST provide an equivalent egress gateway or policy engine before production promotion.
