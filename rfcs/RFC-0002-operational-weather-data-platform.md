# RFC-0002: Operational weather data ingestion, serving, and visualization

**Status:** Accepted  
**Owners:** Platform Architecture, Data Platform, Independent Verification, Application Platform, SRE, Security, UX  
**Decision date:** 2026-08-12  
**Supersedes:** None  
**Related:** RFC-0001, ADR-0001, ADR-0002

## Problem

The platform has immutable source retention, canonical point observations, model-cycle inventory, WIS2 notification handling, GRIB2 inventory decoding, verification primitives, and an operator console. It does not yet provide an operational external-NWP path from provider publication through reproducible gridded assets to standards-based forecast serving and a forecast-map client.

A direct browser integration with an opaque commercial weather API would couple scientific meaning, availability, licensing, and presentation. It would also make it difficult to distinguish observation from forecast, deterministic guidance from probability, and provider output from platform-generated products.

## Decision

The platform SHALL implement a federated model-of-models architecture with four independently governed classes:

1. authoritative observations;
2. imported deterministic and ensemble guidance;
3. platform-generated calibrated or fused guidance;
4. official warnings and experimental products.

The first operational path SHALL use NOAA GFS for deterministic global guidance, NOAA GEFS for ensemble guidance, WIS2/BUFR observations for verification and calibration, and OpenWeather only as optional point-condition and alert enrichment.

The production data path SHALL be:

```text
provider publication
  -> isolated acquisition worker
  -> immutable source bytes and source-slice manifest
  -> validated decoder and canonical gridded asset
  -> scientific quality control
  -> atomic cycle publication
  -> OGC API EDR and presentation products
  -> forecast-map client
```

Only acquisition workloads MAY have provider Internet egress. API, forecast, calibration, tile, and UI workloads SHALL consume internal stores.

## Standards profile

The implementation SHALL pin exact adopted versions in the standards register. The initial profile is:

- RFC 2119 and RFC 8174 for normative language;
- RFC 9110 for HTTP semantics;
- RFC 3986 for URIs;
- RFC 3339 for interchange timestamps;
- RFC 8446 for TLS 1.3;
- RFC 9457 for API problem details;
- RFC 9700 when OAuth/OIDC is introduced;
- OGC API Environmental Data Retrieval 1.1;
- WMO WIS 2.0 and pinned WMO code tables;
- GRIB2 and BUFR with recorded ecCodes runtime versions;
- CF metadata conventions for normalized scientific arrays;
- NIST SP 800-218 SSDF 1.1 for secure development;
- WCAG 2.2 AA for user-facing applications.

## Canonical data boundaries

### Observation

An `Observation` is a measurement or observational report with point geometry, observation time, quality disposition, explicit unit, and source provenance.

### Model guidance field

A gridded model field SHALL be represented by `GridFieldAsset`; it SHALL NOT be expanded into one JSON observation per grid cell.

Every grid asset SHALL identify:

- model, version, cycle initialization, valid time, and lead;
- ensemble member when applicable;
- phenomenon, provider variable, vertical level, and unit;
- grid identity, dimensions, CRS, and longitude convention;
- immutable source digest and normalized digest;
- decoder version, source revision, quality disposition, and provenance.

The invariant `valid_at == initialized_at + lead_seconds` SHALL be enforced.

### Source slice

Selective GRIB byte-range retrieval SHALL produce a `SourceSliceManifest` recording provider, dataset, product, upstream object identity, byte interval, index digest, payload digest, and acquisition timestamps. Provider ETags SHALL NOT be treated as cryptographic content identities. Platform SHA-256 digests are authoritative.

## Cycle lifecycle

A model cycle SHALL use explicit lifecycle states:

```text
DISCOVERED -> INDEX_AVAILABLE -> DOWNLOADING -> PARTIAL
PARTIAL -> MINIMUM_USABLE -> COMPLETE
any pre-publication state -> QUARANTINED
published cycle -> SUPERSEDED -> EXPIRED
```

The catalog SHALL expose distinct `latest_published`, `latest_usable`, and `latest_complete` aliases. The default UI and API alias SHALL be `latest_usable`.

A newer partial cycle SHALL NOT replace an older usable cycle unless the configured minimum field manifest is satisfied.

## NOAA acquisition

The initial GFS manifest SHALL include 10 m U and V wind, 2 m temperature, 2 m relative humidity, mean sea-level pressure, surface gust, total cloud cover, and precipitation. Transport-oriented extensions SHOULD add boundary-layer height and winds at 925, 850, and 700 hPa.

The acquisition worker SHALL:

1. discover a model cycle;
2. retain and parse the GRIB index;
3. select required messages by provider field identity;
4. perform bounded byte-range retrieval;
5. retain source bytes before interpretation;
6. verify the requested and received byte intervals;
7. decode using a recorded ecCodes runtime version;
8. persist canonical assets and update cycle completeness idempotently.

Notification delivery SHALL be treated as at-least-once. Duplicate notifications and downloads SHALL not create duplicate logical assets.

## GEFS probability products

Every ensemble-derived probability SHALL include expected, available, and valid member counts. Missing members SHALL NOT silently disappear from the denominator.

Derived products SHALL preserve monotonic quantiles and exceedance probabilities. Deterministic GFS or OpenWeather values SHALL NOT be represented as a synthetic percentile.

## API and presentation

OGC API EDR SHALL be the primary scientific subsetting interface. The first profile SHALL provide landing, conformance, collections, collection metadata, and position queries; area and cube queries follow after gridded persistence is operational.

Convenience APIs MAY expose model cycles, aliases, grid assets, map manifests, and immutable tile assets. RFC 9457 responses SHALL be used for machine-readable failures.

Immutable assets SHOULD use long-lived cache headers and content-addressed URLs. Mutable aliases SHALL use short caching with validators.

## UX requirements

The forecast-map client SHALL:

- distinguish observed, forecast, ensemble consensus, official alert, and experimental states;
- always show model initialization, valid time, and forecast lead;
- provide provenance for every displayed field;
- use progressive disclosure for scientific details;
- provide keyboard and non-map equivalents;
- support reduced motion and a static-vector fallback;
- never encode essential meaning by color alone;
- preserve usable forecast content when GPU animation fails.

Wind animation SHALL consume physical U/V components. Direction conversion, tile serialization, browser reconstruction, and rendered displacement SHALL be tested end to end.

## Security and deployment

Production workloads SHALL run non-root, drop Linux capabilities, prohibit privilege escalation, use read-only root filesystems where practical, and use workload identity rather than static cloud credentials.

Raw source, canonical grid, derived tile, metadata, and control-plane permissions SHALL be separated. The public client SHALL never receive provider credentials.

Deployment SHALL support independent rollback of application versions and published model-cycle aliases.

## Verification and release gates

The following gates are mandatory before production promotion:

- executable specification and traceability validation;
- JSON Schema and consumer-contract validation;
- unit, property, differential, and metamorphic scientific tests;
- golden GRIB replay and malformed-input regression tests;
- integration testing from notification through API response;
- browser functional, accessibility, and visual regression testing;
- SAST, SCA, secret, container, IaC, parser-fuzz, and egress-policy checks;
- load, resilience, stale-data, data-rollback, and software-rollback exercises;
- signed image digest, SBOM, build provenance, and release evidence.

A provider or dependency failure MAY reduce freshness, availability, or confidence. It SHALL NOT corrupt scientific identity, source attribution, time semantics, or data integrity.

## Phase-1 implementation slice

This RFC's first implementation PR SHALL deliver:

- normative acquisition, grid-data, lifecycle, validation, security, and UX specifications;
- `SourceSliceManifest` and `GridFieldAsset` typed contracts and JSON Schemas;
- GFS index parsing and deterministic field/range selection;
- cycle lifecycle and minimum-usable promotion logic;
- longitude normalization and meteorological wind-vector invariants;
- deterministic binary U/V tile encoding contract;
- acquisition-only Kubernetes egress and hardened workload manifests;
- blocking schema-contract and scientific-validation workflows;
- test evidence and traceability entries.

Live NOAA credentials are not required because NODD is public. Live production object-store, queue, PostgreSQL, Zarr, CDN, and forecast-map rollout SHALL be implemented in subsequent independently reviewable slices using the contracts established here.

## Alternatives

1. **Browser-to-provider API calls.** Rejected because credentials, quotas, source semantics, and availability would leak into presentation.
2. **Convert every grid cell into an observation.** Rejected because it is semantically wrong and operationally unbounded.
3. **Store only rendered tiles.** Rejected because numeric scientific values and reproducibility would be lost.
4. **Publish the newest cycle immediately.** Rejected because partially published cycles can omit required fields.
5. **Treat OpenWeather as authoritative.** Rejected because it is a licensed blended provider suitable for enrichment, not the platform's scientific evidence foundation.

## Rollback

Application rollback and data publication rollback SHALL be independent. A failed application release reverts to the previous image digest. A failed model publication moves the serving alias to the prior usable cycle without deleting the failed source evidence or canonical assets.
