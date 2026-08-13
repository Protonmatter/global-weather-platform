---
spec_id: SPEC-810
title: Weather scientific and presentation validation
status: review
owners:
  - independent-verification
  - earth-system-science
  - ux
standards:
  - OGC-API-EDR-1.1
  - WCAG-2.2-AA
requirements:
  - id: SCI-LON-0001
    statement: Longitude normalization MUST use wrapped GeoJSON longitude semantics and MUST preserve antimeridian proximity.
    priority: critical
    verification: [TEST-WIND-0001]
    release_gate: scientific
  - id: SCI-WIND-0002
    statement: Meteorological wind direction conversion MUST produce physical U and V components whose cardinal signs correspond to motion away from the reported source direction.
    priority: critical
    verification: [TEST-WIND-0001]
    release_gate: scientific
  - id: SCI-TILE-0003
    statement: Vector tile encoding and decoding MUST be deterministic, MUST reject non-finite values and malformed lengths, and MUST bound component reconstruction error by the declared quantization scale.
    priority: critical
    verification: [TEST-TILE-0001]
    release_gate: scientific
  - id: UX-WEATHER-0004
    statement: A weather client MUST distinguish observation, deterministic forecast, ensemble consensus, official warning, and experimental output and MUST expose initialization time, valid time, lead, source, and staleness.
    priority: critical
    verification: [TEST-UX-0001]
    release_gate: ux
  - id: UX-MOTION-0005
    statement: A weather client MUST provide reduced-motion and non-WebGL fallbacks without removing the underlying forecast information.
    priority: high
    verification: [TEST-UX-0001]
    release_gate: ux
---

# Weather scientific and presentation validation

Scientific validation spans the complete representation chain. A wind sign error that survives storage but is introduced during quantization or browser reconstruction is still a scientific failure.

Phase 1 implements coordinate, wind, and vector-tile invariants. Browser and accessibility verification remain planned until the forecast-map application is introduced.
