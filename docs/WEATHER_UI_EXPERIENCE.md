# Forecast-map UI and experience contract

This document defines the product and validation contract for the future `apps/forecast-map` application. The forecast-map application is **not implemented in Phase 1**. The current operator console remains an authenticated control-plane application and must not be treated as the public or general forecast experience.

## Product objective

The forecast-map application should let a user answer, without interpreting opaque model jargon:

1. What conditions are expected at this place and time?
2. Is this an observation, a deterministic forecast, an ensemble product, an official warning, or an experiment?
3. Which model cycle and valid time produced the displayed value?
4. How uncertain or incomplete is the guidance?
5. Is the data current, stale, partial, or unavailable?
6. Where did the value come from, and what transformations were applied?

## Information architecture

### Primary map shell

```text
┌──────────────────────────────────────────────────────────────┐
│ Location/search    Layer    Model/cycle    Valid time       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                         WEATHER MAP                          │
│                                                              │
│             scalar field + optional wind vectors            │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ ◀ previous  ─────────────●────────────────  next ▶          │
├──────────────────────────────────────────────────────────────┤
│ Selected-point summary                                      │
│ 14 °C · wind NW 12 mph · pressure 1009 hPa                  │
│ GFS · initialized 18:00 UTC · valid 21:00 UTC · +3 h        │
│ [Details] [Ensemble] [Source and provenance]                 │
└──────────────────────────────────────────────────────────────┘
```

### Progressive disclosure

Level 0 — decision summary:

- temperature or selected field;
- condition and precipitation where available;
- wind summary;
- important hazard or official warning;
- plain-language freshness state.

Level 1 — forecast detail:

- hourly or valid-time timeline;
- precipitation and wind;
- uncertainty indicator;
- source label.

Level 2 — model detail:

- provider/model;
- initialization and valid times;
- lead time;
- ensemble range and threshold probabilities;
- cycle completeness and member count.

Level 3 — scientific provenance:

- variable and level;
- grid and resolution;
- interpolation method;
- source-record digest;
- normalized-asset digest;
- decoder and transformation versions.

## Mandatory data-state labels

The UI must use explicit, accessible labels for:

```text
OBSERVED
DETERMINISTIC FORECAST
ENSEMBLE CONSENSUS
OFFICIAL WARNING
EXPERIMENTAL
```

Presentation color alone is insufficient. Each label must be available to assistive technology and in the non-map summary.

## Time semantics

The interface must always make these concepts distinct:

- `initialized_at` — when the model cycle began;
- `valid_at` — when the value applies;
- `lead` — elapsed forecast time from initialization;
- `observed_at` — for measurements only;
- `received_at` or freshness age — operational delivery metadata.

Preferred display:

```text
GFS · initialized 18:00 UTC · valid 03:00 UTC · +9 h
```

Avoid ambiguous labels such as “updated recently” as the only time indicator.

## Cycle and freshness states

The user experience must distinguish:

- a newly discovered but incomplete cycle;
- the current `latest_usable` cycle;
- a complete cycle;
- a stale but still usable prior cycle;
- a quarantined cycle;
- no usable data.

A newer partial cycle must not visually replace the currently usable cycle. It may appear in an advanced cycle picker with an `INCOMPLETE` label.

Suggested state messages:

| State | User-facing behavior |
|---|---|
| Usable/current | Normal display with source and time |
| Partial newer cycle | Continue serving prior usable cycle; disclose newer cycle in advanced details |
| Stale | Keep last usable field, show explicit age and provider delay |
| Quarantined | Never serve by default; operator-only diagnostic visibility |
| No usable cycle | Replace map values with an unavailable state; do not fabricate continuity |

## Map layers

### Scalar fields

Temperature, pressure, humidity, cloud cover, and precipitation should be numeric textures or numeric tiles with independent palette metadata. Scientific values must not exist only as rendered colors.

Every layer manifest should identify:

- field identity and unit;
- cycle and valid time;
- palette and numeric range;
- missing-value semantics;
- source/provenance reference;
- cache identity and staleness.

### Wind

Wind animation must use U and V components. It must not derive particle motion from screen-space arrows or color direction.

Validation must span:

```text
canonical U/V
  -> tile quantization
  -> browser decode
  -> shader texture
  -> particle displacement
```

Cardinal truth cases:

- wind from north moves south;
- wind from east moves west;
- wind from south moves north;
- wind from west moves east.

### Probabilities

Ensemble products should show:

- quantile range;
- threshold probability;
- available and expected member counts;
- calibration state where applicable.

Do not display a deterministic value as a synthetic percentile. Missing members must remain visible in the denominator.

## Selected-point inspection

A click, tap, keyboard selection, or search result should open the same semantic point panel. It should query a standards-based point endpoint rather than estimate values solely from rendered pixels.

Required fields:

```text
location
field value and unit
model/provider
initialization time
valid time
lead
cycle state
source status
uncertainty or member count
provenance link
```

The panel should include a text/table representation usable without the map.

## Accessibility baseline

Target: WCAG 2.2 AA.

Required behaviors:

- keyboard access to all controls;
- visible focus and logical focus order;
- semantic buttons, tabs, dialogs, sliders, and status regions;
- timeline control operable with keyboard and assistive technology;
- text alternatives for map-selected conditions;
- non-map list/table for searched or selected points;
- no essential meaning encoded only by color or particle direction;
- minimum contrast for labels and controls;
- screen-reader announcements for layer, time, cycle, and error changes;
- large enough touch targets on mobile;
- user preference for units, time zone, and reduced motion retained without blocking core content.

## Reduced motion and rendering fallback

The application must honor:

```css
@media (prefers-reduced-motion: reduce)
```

Fallback order:

```text
GPU particles
  -> reduced particle density
  -> static vector arrows
  -> server-rendered raster
  -> non-map textual forecast
```

Failure of WebGL, a shader, or animation must not remove forecast values or provenance.

## Responsive behavior

### Desktop

- map and detail panel can remain visible together;
- advanced model and ensemble controls may use a side panel;
- timeline can expose more valid times and cycle comparisons.

### Tablet

- map remains primary;
- selected-point details use a collapsible panel;
- timeline touch targets remain independent and labelled.

### Mobile

- selected-point summary uses a bottom sheet;
- particle density and tile resolution may be reduced;
- advanced controls use separate views rather than dense overlays;
- map interaction must not prevent page scrolling or screen-reader navigation;
- the non-map forecast summary is available before or alongside the map.

## Error prevention and recovery

The UI must not silently substitute one product for another. Examples:

- a failed GFS layer must not fall back to OpenWeather without an explicit source change;
- an observation must not replace a forecast value under the same label;
- a stale cycle must not appear current because the browser cache served an old manifest;
- unit conversion must preserve the original unit and conversion definition in provenance;
- a layer error must identify whether the failure is source, cycle, tile, browser, or network related where safely knowable.

Errors should follow a consistent structure:

```text
What failed
Which displayed data is affected
Whether last known good data is still being shown
How old that data is
What action is available
```

## Performance experience targets

Proposed targets for representative hardware and network conditions:

| Interaction | Target |
|---|---:|
| Initial application shell | < 2.5 s on representative mobile |
| Control response | < 100 ms |
| Timeline selection feedback | < 300 ms |
| Cached map tile p95 | < 250 ms |
| Desktop wind animation | 60 fps target |
| Mobile wind animation | at least 30 fps target or fallback |

Performance degradation should reduce visual density before reducing correctness or provenance.

## Browser test matrix

Functional tests must cover:

- location search;
- map pan and zoom;
- keyboard map/point selection;
- layer change;
- valid-time change;
- cycle change;
- animation play/pause;
- source/provenance panel;
- ensemble details;
- stale, partial, unavailable, and quarantined states;
- reduced motion;
- WebGL unavailable;
- mobile bottom sheet;
- unit and time-zone changes;
- browser back/forward state restoration.

## Visual regression

Use deterministic fixture data, fixed viewports, fixed times, and pinned browser versions. Never use live NOAA output as a visual-regression reference.

Required snapshots:

- wind layer;
- temperature layer;
- precipitation layer;
- pressure layer;
- ensemble spread/probability;
- partial cycle;
- stale cycle;
- provider unavailable;
- light and dark presentation;
- desktop, tablet, and mobile;
- antimeridian;
- reduced-motion/static-vector fallback.

## Scientific UI acceptance

A browser test must validate values and direction, not only pixels. Example:

```text
fixture U = +10, V = 0
expected reconstructed vector = eastward
expected particle displacement = positive screen/world east direction
```

The test must separately verify point inspection against the canonical numeric value.

## Security and privacy

- no provider credential or signed provider URL in browser code;
- no arbitrary client-supplied upstream URL;
- map and provenance links restricted to platform-owned routes;
- CSP, frame, origin, and asset policies defined before production;
- user location handled according to explicit product privacy requirements;
- location history not persisted by default unless the product specification requires it;
- error telemetry excludes exact sensitive locations where applicable.

## Definition of done for `apps/forecast-map`

The forecast-map application is not complete until:

- model/observation states are visibly and semantically distinct;
- initialization, valid time, lead, source, and staleness are always available;
- point values come from numeric scientific APIs;
- wind direction passes storage-to-render cardinal tests;
- reduced-motion and no-WebGL fallbacks preserve content;
- keyboard and screen-reader workflows pass;
- deterministic functional and visual regression suites pass;
- source credentials remain server-side;
- performance, error recovery, and stale-cycle tests meet the approved specification;
- each implemented UX requirement is linked to repository evidence in `specs/verification-map.yaml`.
