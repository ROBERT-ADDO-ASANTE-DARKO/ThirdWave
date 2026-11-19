import { useCallback, useEffect, useState } from "react";
import { fetchActiveIncidents, fetchPendingClusters } from "../../api/incidents";
import { geocodeAddress, resolveIncident, submitTestReport, verifyBulk, verifyReport } from "../../api/reports";
import type { Cluster, HazardType, Incident } from "../../api/types";
import { ClusterCard, SyntheticBadge, hazardLabel } from "../../components/PendingQueue";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./IncidentVerification.css";

const HAZARD_OPTIONS: HazardType[] = ["urban_flood", "flash_flood", "river_flood"];

function SeedPanel({ onSeeded }: { onSeeded: () => void }) {
  const [hazardType, setHazardType] = useState<HazardType>("urban_flood");
  const [address, setAddress] = useState("");
  const [description, setDescription] = useState("");
  const [depthLo, setDepthLo] = useState("0.3");
  const [depthHi, setDepthHi] = useState("0.6");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setStatus(null);
    try {
      const geo = await geocodeAddress(address);
      await submitTestReport({
        lon: geo.lon,
        lat: geo.lat,
        hazardType,
        description: description || `Test report near ${geo.resolved_address}`,
        locationLabel: geo.resolved_address,
        depthLoM: depthLo ? Number(depthLo) : undefined,
        depthHiM: depthHi ? Number(depthHi) : undefined,
      });
      setStatus(`Seeded a synthetic report near ${geo.resolved_address}.`);
      setDescription("");
      onSeeded();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not seed a test report.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="iv-seed-panel">
      <div>
        <span className="iv-seed-title">Seed a test report</span>
        <p className="iv-seed-subtitle">
          Submits a real, clearly-tagged synthetic report through the same public pipeline a citizen's phone uses
          (<code>POST /reports</code>, <code>synthetic=true</code>) — not a separate demo system. Useful for exercising
          this queue when the live database has nothing pending.
        </p>
      </div>

      <label className="iv-seed-field">
        <span>Hazard type</span>
        <select value={hazardType} onChange={(e) => setHazardType(e.target.value as HazardType)}>
          {HAZARD_OPTIONS.map((h) => (
            <option key={h} value={h}>
              {hazardLabel(h)}
            </option>
          ))}
        </select>
      </label>

      <label className="iv-seed-field">
        <span>Location (address or landmark)</span>
        <input type="text" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="e.g. Kaneshie Market" />
      </label>

      <label className="iv-seed-field">
        <span>Description</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional — defaults to a short auto-generated note" rows={2} />
      </label>

      <div className="iv-seed-depth-row">
        <label className="iv-seed-field">
          <span>Depth lo (m)</span>
          <input type="number" step="0.1" min="0" value={depthLo} onChange={(e) => setDepthLo(e.target.value)} />
        </label>
        <label className="iv-seed-field">
          <span>Depth hi (m)</span>
          <input type="number" step="0.1" min="0" value={depthHi} onChange={(e) => setDepthHi(e.target.value)} />
        </label>
      </div>

      <button type="button" className="rq-btn rq-btn-primary" disabled={busy || !address.trim()} onClick={submit}>
        {busy ? "Seeding…" : "Seed this report"}
      </button>

      {status && <p className="iv-seed-status">{status}</p>}
    </div>
  );
}

export function IncidentVerification() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const refresh = useCallback(() => {
    setLoading(true);
    return Promise.all([fetchPendingClusters(), fetchActiveIncidents()])
      .then(([clu, inc]) => {
        setClusters(clu);
        setIncidents(inc);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Could not reach the backend."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function withBusy(ids: string[], fn: () => Promise<unknown>) {
    setBusyIds((prev) => new Set([...prev, ...ids]));
    return fn()
      .then(() => refresh())
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Action failed."))
      .finally(() =>
        setBusyIds((prev) => {
          const next = new Set(prev);
          ids.forEach((id) => next.delete(id));
          return next;
        }),
      );
  }

  const nPending = clusters.reduce((s, c) => s + c.n_reports, 0);
  const nSynthetic = clusters.reduce((s, c) => s + c.reports.filter((r) => r.synthetic).length, 0);

  const filteredClusters = clusters.filter(
    (c) => matchesQuery([c.district], query) || c.reports.some((r) => matchesQuery([r.id, r.district, r.location_label, r.hazard_type], query)),
  );
  const filteredIncidents = incidents.filter((i) => matchesQuery([i.id, i.district, i.location_label, i.hazard_type], query));

  return (
    <>
      <TopBar
        title="Incident Verification"
        subtitle="Real and synthetic reports flow through one identical pipeline"
        search={{ value: query, onChange: setQuery, placeholder: "Search reports by ID, district, or location…" }}
      />

      {error && (
        <Card>
          <p className="error-text">Could not load verification queue: {error}</p>
        </Card>
      )}

      <section className="section-kpis">
        <Card>
          <KpiTile label="Pending reports" value={nPending} note={clusters.length ? `${clusters.length} cluster(s) to review` : undefined} />
        </Card>
        <Card>
          <KpiTile label="Active incidents" value={incidents.length} />
        </Card>
        <Card>
          <KpiTile label="Synthetic in queue" value={nSynthetic} />
        </Card>
      </section>

      <div className="iv-body">
        <div className="iv-queue">
          <h2 className="section-title">Pending reports — verify before they become active incidents</h2>
          <p className="section-caption">
            Reports within ~300m of each other are grouped as one likely flood event, worst first.
          </p>

          {loading && <p className="section-caption">Loading…</p>}
          {!loading && clusters.length === 0 && (
            <p className="section-caption">No pending reports. Seed one on the right, or submit via the citizen app.</p>
          )}
          {!loading && clusters.length > 0 && filteredClusters.length === 0 && (
            <p className="section-caption">No pending reports match "{query}".</p>
          )}

          {filteredClusters.map((c, i) => (
            <ClusterCard
              key={i}
              cluster={c}
              busyIds={busyIds}
              onVerify={(id) => withBusy([id], () => verifyReport(id, true))}
              onReject={(id) => withBusy([id], () => verifyReport(id, false))}
              onVerifyAll={(ids) => withBusy(ids, () => verifyBulk(ids, true))}
              onRejectAll={(ids) => withBusy(ids, () => verifyBulk(ids, false))}
            />
          ))}

          <h2 className="section-title section-title-spaced">Active incidents — currently routed around by Safer Routing</h2>
          {!loading && incidents.length === 0 && <p className="section-caption">No active incidents right now.</p>}
          {!loading && incidents.length > 0 && filteredIncidents.length === 0 && (
            <p className="section-caption">No matches for "{query}".</p>
          )}
          {filteredIncidents.map((inc) => (
            <Card key={inc.id} className="iv-incident-row">
              <div>
                <code>{inc.id}</code>
                {inc.synthetic && <SyntheticBadge />}
                <strong> {hazardLabel(inc.hazard_type)}</strong> — {inc.district ?? "outside pilot district"}
                <p className="rq-report-caption">
                  {inc.location_label} · verified {inc.verified_at?.slice(0, 16).replace("T", " ")} UTC
                </p>
              </div>
              <button
                type="button"
                className="rq-btn rq-btn-outline rq-btn-sm"
                disabled={busyIds.has(inc.id)}
                onClick={() => withBusy([inc.id], () => resolveIncident(inc.id))}
              >
                Mark resolved
              </button>
            </Card>
          ))}
        </div>

        <aside className="iv-sidebar">
          <SeedPanel onSeeded={refresh} />
        </aside>
      </div>
    </>
  );
}
