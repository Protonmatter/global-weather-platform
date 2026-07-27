"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Observation = {
  id: string;
  phenomenon: string;
  value: number | null;
  unit: string;
  uncertainty: number | null;
  longitude: number;
  latitude: number;
  observedAt: string;
  ingestedAt: string;
  qualityDisposition: string;
  qualityFlags: string[];
  sourceId: string;
  sourceDigest: string;
  decoderVersion: string;
};

type ModelCycle = {
  id: string;
  modelId: string;
  modelVersion: string;
  guidanceOrigin: string;
  initializedAt: string;
  completeness: string;
  availableFieldCount: number;
  expectedFieldCount: number;
  updatedAt: string;
};

type Health = {
  status: string;
  version: string;
  contract_version: string;
  control_plane_mode: string;
  telemetry_enabled: boolean;
  external_egress_enabled: boolean;
  persistence: {
    canonical_observations: number | null;
    retained_source_records: number | null;
    audit_events: number | null;
  };
};

type Toast = { tone: "good" | "bad"; message: string } | null;

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) =>
    letter.toUpperCase(),
  );
}

function ageLabel(value: string) {
  const minutes = Math.max(
    0,
    Math.round((Date.now() - new Date(value).getTime()) / 60_000),
  );
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & { detail?: string; error?: string };
  if (!response.ok) {
    throw new Error(body.detail ?? body.error ?? "Request failed");
  }
  return body;
}

export default function WeatherConsole({
  operatorName,
  operatorEmail,
}: {
  operatorName: string;
  operatorEmail: string | null;
}) {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [cycles, setCycles] = useState<ModelCycle[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [showQuarantine, setShowQuarantine] = useState(false);
  const [phenomenon, setPhenomenon] = useState("all");
  const [selected, setSelected] = useState<Observation | null>(null);
  const [toast, setToast] = useState<Toast>(null);

  const loadData = useCallback(async () => {
    try {
      const observationQuery = new URLSearchParams();
      if (showQuarantine) observationQuery.set("include_quarantined", "true");
      const [observationData, cycleData, healthData] = await Promise.all([
        fetch(`/api/v1/observations?${observationQuery}`, { cache: "no-store" }).then(
          (response) => responseJson<{ observations: Observation[] }>(response),
        ),
        fetch("/api/v1/model-cycles", { cache: "no-store" }).then((response) =>
          responseJson<{ cycles: ModelCycle[] }>(response),
        ),
        fetch("/api/v1/healthz", { cache: "no-store" }).then((response) =>
          responseJson<Health>(response),
        ),
      ]);
      setObservations(observationData.observations);
      setCycles(cycleData.cycles);
      setHealth(healthData);
    } catch (error) {
      setToast({
        tone: "bad",
        message:
          error instanceof Error
            ? error.message
            : "The weather backend is unavailable.",
      });
    } finally {
      setLoading(false);
    }
  }, [showQuarantine]);

  useEffect(() => {
    // This effect is the client-side synchronization boundary for the backend.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const phenomena = useMemo(
    () => [...new Set(observations.map((item) => item.phenomenon))].sort(),
    [observations],
  );
  const visibleObservations = useMemo(
    () =>
      phenomenon === "all"
        ? observations
        : observations.filter((item) => item.phenomenon === phenomenon),
    [observations, phenomenon],
  );
  const acceptedCount = observations.filter(
    (item) => item.qualityDisposition !== "quarantine",
  ).length;
  const partialCycles = cycles.filter(
    (cycle) => cycle.completeness !== "complete",
  ).length;

  return (
    <main className="console-shell">
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Atmos overview">
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>
          <span>
            <strong>Atmos</strong>
            <small>Global weather platform</small>
          </span>
        </a>
        <nav className="topnav" aria-label="Primary navigation">
          <a className="active" href="#overview">
            Overview
          </a>
          <a href="#observations">Observations</a>
          <a href="#guidance">Guidance</a>
          <a href="#provenance">Provenance</a>
        </nav>
        <div className="operator">
          <span className="operator-dot" aria-hidden="true" />
          <span>
            <strong>{operatorName}</strong>
            <small>{operatorEmail ?? "Private workspace"}</small>
          </span>
        </div>
      </header>

      <section className="hero" id="overview">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-pulse" />
            Observation control plane
          </div>
          <h1>See what the atmosphere is saying.</h1>
          <p>
            A provenance-first workspace for canonical observations, imported
            model guidance, and uncertainty-aware operational decisions.
          </p>
        </div>
        <div className="hero-status">
          <div>
            <span>Backend</span>
            <strong className={health?.status === "ok" ? "positive" : ""}>
              {health?.status === "ok" ? "Operational" : "Connecting"}
            </strong>
          </div>
          <div>
            <span>Telemetry</span>
            <strong>{health?.telemetry_enabled ? "Enabled" : "Disabled"}</strong>
          </div>
          <div>
            <span>External egress</span>
            <strong>
              {health?.external_egress_enabled ? "Enabled" : "Deny by default"}
            </strong>
          </div>
        </div>
      </section>

      <section className="metric-grid" aria-label="Platform metrics">
        <article className="metric-card">
          <span>Canonical observations</span>
          <strong>{health?.persistence?.canonical_observations ?? "—"}</strong>
          <small>{acceptedCount} visible after quality policy</small>
        </article>
        <article className="metric-card">
          <span>Retained source records</span>
          <strong>{health?.persistence?.retained_source_records ?? "—"}</strong>
          <small>Content-addressed object storage</small>
        </article>
        <article className="metric-card">
          <span>Audit events</span>
          <strong>{health?.persistence?.audit_events ?? "—"}</strong>
          <small>Append-only operator accountability</small>
        </article>
        <article className="metric-card">
          <span>Serving contract</span>
          <strong>OGC EDR</strong>
          <small>
            v{health?.contract_version ?? "1.0.0"} · {cycles.length || 0} cycles
            · {partialCycles} partial
          </small>
        </article>
      </section>

      <section className="workspace-grid">
        <article className="map-card">
          <div className="section-heading">
            <div>
              <span className="section-kicker">Global situation</span>
              <h2>Observation coverage</h2>
            </div>
            <div className="segmented" aria-label="Observation filter">
              <button
                className={phenomenon === "all" ? "selected" : ""}
                onClick={() => setPhenomenon("all")}
                type="button"
              >
                All
              </button>
              {phenomena.slice(0, 2).map((item) => (
                <button
                  className={phenomenon === item ? "selected" : ""}
                  key={item}
                  onClick={() => setPhenomenon(item)}
                  type="button"
                >
                  {titleCase(item).split(" ")[0]}
                </button>
              ))}
            </div>
          </div>

          <div className="world-map" aria-label="Global observation map">
            <div className="map-glow map-glow-one" />
            <div className="map-glow map-glow-two" />
            <div className="continent continent-americas" />
            <div className="continent continent-eurasia" />
            <div className="continent continent-africa" />
            <div className="continent continent-australia" />
            {visibleObservations.map((item) => (
              <button
                aria-label={`${titleCase(item.phenomenon)} at ${item.latitude.toFixed(2)}, ${item.longitude.toFixed(2)}`}
                className={`map-marker ${selected?.id === item.id ? "active" : ""}`}
                key={item.id}
                onClick={() => setSelected(item)}
                style={{
                  left: `${((item.longitude + 180) / 360) * 100}%`,
                  top: `${((90 - item.latitude) / 180) * 100}%`,
                }}
                type="button"
              >
                <span />
              </button>
            ))}
            <div className="map-label map-label-a">North America</div>
            <div className="map-label map-label-b">Europe</div>
            <div className="map-label map-label-c">Pacific</div>
            <div className="map-legend">
              <span>
                <i className="legend-dot" /> Accepted
              </span>
              <span>{visibleObservations.length} stations shown</span>
            </div>
          </div>

          {selected ? (
            <div className="selection-strip" id="provenance">
              <div>
                <span>{titleCase(selected.phenomenon)}</span>
                <strong>
                  {selected.value ?? "Missing"} {selected.unit}
                </strong>
              </div>
              <div>
                <span>Valid time</span>
                <strong>{formatTime(selected.observedAt)}</strong>
              </div>
              <div>
                <span>Quality</span>
                <strong>{titleCase(selected.qualityDisposition)}</strong>
              </div>
              <div className="provenance-cell">
                <span>Source digest</span>
                <code>{selected.sourceDigest.slice(0, 22)}…</code>
              </div>
              <button
                aria-label="Close observation details"
                onClick={() => setSelected(null)}
                type="button"
              >
                ×
              </button>
            </div>
          ) : null}
        </article>

        <aside className="activity-card" id="guidance">
          <div className="section-heading">
            <div>
              <span className="section-kicker">Guidance catalog</span>
              <h2>Latest cycles</h2>
            </div>
            <span className="api-badge">Live API</span>
          </div>
          <div className="cycle-list">
            {cycles.map((cycle) => {
              const completeness = Math.round(
                cycle.expectedFieldCount > 0
                  ? (cycle.availableFieldCount / cycle.expectedFieldCount) * 100
                  : 0,
              );
              return (
                <article className="cycle" key={cycle.id}>
                  <div className="cycle-title">
                    <div>
                      <strong>{cycle.modelId}</strong>
                      <span>{cycle.modelVersion}</span>
                    </div>
                    <span className={`origin origin-${cycle.guidanceOrigin}`}>
                      {titleCase(cycle.guidanceOrigin)}
                    </span>
                  </div>
                  <div className="progress-track" aria-label={`${completeness}% complete`}>
                    <span style={{ width: `${completeness}%` }} />
                  </div>
                  <div className="cycle-meta">
                    <span>{completeness}% fields available</span>
                    <span>{ageLabel(cycle.updatedAt)}</span>
                  </div>
                </article>
              );
            })}
            {!loading && cycles.length === 0 ? (
              <p className="empty-copy">No model cycles are catalogued.</p>
            ) : null}
          </div>
          <div className="trust-note">
            <span className="trust-icon">i</span>
            <p>
              Imported, platform, experimental, and official guidance remain
              explicitly separated.
            </p>
          </div>
        </aside>
      </section>

      <section className="observation-card" id="observations">
        <div className="section-heading">
          <div>
            <span className="section-kicker">Canonical store</span>
            <h2>Recent observations</h2>
          </div>
          <div className="observation-actions">
            <label className="quarantine-toggle">
              <input
                checked={showQuarantine}
                onChange={(event) => setShowQuarantine(event.target.checked)}
                type="checkbox"
              />
              <span />
              Include quarantine
            </label>
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Phenomenon</th>
                <th>Value</th>
                <th>Position</th>
                <th>Valid time</th>
                <th>Quality</th>
                <th>Provenance</th>
              </tr>
            </thead>
            <tbody>
              {observations.slice(0, 12).map((item) => (
                <tr key={item.id} onClick={() => setSelected(item)}>
                  <td>
                    <strong>{titleCase(item.phenomenon)}</strong>
                    <small>{item.sourceId}</small>
                  </td>
                  <td>
                    {item.value ?? "Missing"} {item.unit}
                  </td>
                  <td>
                    {item.latitude.toFixed(2)}, {item.longitude.toFixed(2)}
                  </td>
                  <td>{formatTime(item.observedAt)}</td>
                  <td>
                    <span
                      className={`quality quality-${item.qualityDisposition}`}
                    >
                      {titleCase(item.qualityDisposition)}
                    </span>
                  </td>
                  <td>
                    <code>{item.sourceDigest.slice(7, 19)}…</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && observations.length === 0 ? (
            <div className="empty-state">
              <span className="empty-orbit" aria-hidden="true" />
              <h3>The canonical store is ready.</h3>
              <p>
                Use the authenticated ingestion API to retain real source
                records and admit schema-valid observations with provenance.
              </p>
            </div>
          ) : null}
        </div>
      </section>

      <footer>
        <span>Atmos control plane · {health?.version ?? "0.3.0-site"}</span>
        <span>Raw records immutable · Quarantine excluded by default</span>
      </footer>

      {toast ? (
        <div className={`toast toast-${toast.tone}`} role="status">
          <span />
          {toast.message}
        </div>
      ) : null}
    </main>
  );
}
