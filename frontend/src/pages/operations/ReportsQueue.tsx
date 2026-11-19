import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchActiveIncidents, fetchPendingClusters, fetchResolvedIncidents } from "../../api/incidents";
import { resolveIncident, runSarCheck, verifyBulk, verifyReport } from "../../api/reports";
import type { Cluster, Incident } from "../../api/types";
import { ClusterCard, SyntheticBadge, hazardLabel } from "../../components/PendingQueue";
import { ConfidenceBadge, ZoneBadge } from "../../components/ReportBadges";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./ReportsQueue.css";

function SarCheckButton({ busy, onRun }: { busy: boolean; onRun: () => void }) {
  return (
    <button type="button" className="rq-btn rq-btn-outline rq-btn-sm" disabled={busy} onClick={onRun}>
      {busy ? "Querying Sentinel-1…" : "Run satellite (SAR) check"}
    </button>
  );
}

function VerifiedCard({ incident, busy, onSarCheck }: { incident: Incident; busy: boolean; onSarCheck: () => void }) {
  return (
    <Card className="rqq-card">
      <div className="rqq-card-head">
        <code>{incident.id}</code>
        {incident.synthetic && <SyntheticBadge />}
        <strong>{hazardLabel(incident.hazard_type)}</strong>
        <span className="rqq-district">{incident.district ?? "outside pilot district"}</span>
      </div>
      <p className="rq-report-caption">
        {incident.location_label} · verified {incident.verified_at?.slice(0, 16).replace("T", " ")} UTC
      </p>
      <ZoneBadge zone={incident.zone} />
      <div className="rq-confidence-row">
        <ConfidenceBadge confidence={incident.confidence} />
      </div>
      <SarCheckButton busy={busy} onRun={onSarCheck} />
      {/* Dispatch happens on Emergency Resource Allocation (the one place that models the real
          multi-agency NADMO/Fire/Medical/liaison picture) -- this just points there instead of
          duplicating a second, redundant "assign a responder" form. */}
      <p className="rqq-awaiting-note">
        Awaiting dispatch — assign a team in <Link to="/operations/resource-allocation">Emergency Resource Allocation</Link>.
      </p>
    </Card>
  );
}

function RespondingCard({
  incident,
  busy,
  onResolve,
  onSarCheck,
}: {
  incident: Incident;
  busy: boolean;
  onResolve: () => void;
  onSarCheck: () => void;
}) {
  return (
    <Card className="rqq-card">
      <div className="rqq-card-head">
        <code>{incident.id}</code>
        {incident.synthetic && <SyntheticBadge />}
        <strong>{hazardLabel(incident.hazard_type)}</strong>
        <span className="rqq-district">{incident.district ?? "outside pilot district"}</span>
      </div>
      <p className="rq-report-caption">{incident.location_label}</p>
      <p className="rqq-assigned-team">
        Team: {incident.assigned_responder} · ETA {incident.eta_minutes} min
      </p>
      <div className="rq-confidence-row">
        <ConfidenceBadge confidence={incident.confidence} />
      </div>
      <div className="rqq-actions-row">
        <SarCheckButton busy={busy} onRun={onSarCheck} />
        <button type="button" className="rq-btn rq-btn-outline rq-btn-sm" disabled={busy} onClick={onResolve}>
          Mark resolved
        </button>
      </div>
    </Card>
  );
}

export function ReportsQueue() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [active, setActive] = useState<Incident[]>([]);
  const [resolved, setResolved] = useState<Incident[]>([]);
  const [resolvedOpen, setResolvedOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const refresh = useCallback(() => {
    setLoading(true);
    return Promise.all([fetchPendingClusters(), fetchActiveIncidents(), fetchResolvedIncidents(20)])
      .then(([clu, inc, res]) => {
        setClusters(clu);
        setActive(inc);
        setResolved(res);
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
  const awaiting = active.filter((i) => i.response_status !== "responding");
  const responding = active.filter((i) => i.response_status === "responding");

  // Search narrows each section's own list -- it never navigates away or
  // hits the backend again; KPI counts above stay the true totals, not
  // "how many match the search."
  const filteredClusters = clusters.filter(
    (c) => matchesQuery([c.district], query) || c.reports.some((r) => matchesQuery([r.id, r.district, r.location_label, r.hazard_type], query)),
  );
  const filteredAwaiting = awaiting.filter((i) => matchesQuery([i.id, i.district, i.location_label, i.hazard_type], query));
  const filteredResponding = responding.filter((i) => matchesQuery([i.id, i.district, i.location_label, i.hazard_type, i.assigned_responder], query));
  const filteredResolved = resolved.filter((i) => matchesQuery([i.id, i.district, i.location_label, i.hazard_type], query));

  return (
    <>
      <TopBar
        title="Incoming Reports Queue"
        subtitle="Pending → Verified → Responding → Resolved"
        search={{ value: query, onChange: setQuery, placeholder: "Search reports by ID, district, or location…" }}
      />

      {error && (
        <Card>
          <p className="error-text">Could not load the queue: {error}</p>
        </Card>
      )}

      <section className="section-kpis">
        <Card>
          <KpiTile label="Pending" value={nPending} note={clusters.length ? `${clusters.length} cluster(s) to review` : undefined} />
        </Card>
        <Card>
          <KpiTile label="Verified, awaiting responder" value={awaiting.length} />
        </Card>
        <Card>
          <KpiTile label="Responding" value={responding.length} />
        </Card>
      </section>

      <div className="rqq-section">
        <h2 className="section-title">Pending — verify or reject</h2>
        <p className="section-caption">
          Reports within ~300m of each other are grouped as one likely flood event, worst (most reports) first —
          review and act on a cluster at once instead of report by report.
        </p>
        {!loading && clusters.length === 0 && (
          <p className="section-caption">No pending reports. Citizens submit these via the mobile app's Crowdsourced Flood Reporting.</p>
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
      </div>

      <div className="rqq-section">
        <h2 className="section-title">Verified — awaiting a responder</h2>
        {!loading && awaiting.length === 0 && <p className="section-caption">Nothing verified is waiting on a responder right now.</p>}
        {!loading && awaiting.length > 0 && filteredAwaiting.length === 0 && (
          <p className="section-caption">No matches for "{query}".</p>
        )}
        <div className="rqq-card-grid">
          {filteredAwaiting.map((inc) => (
            <VerifiedCard
              key={inc.id}
              incident={inc}
              busy={busyIds.has(inc.id)}
              onSarCheck={() => withBusy([inc.id], () => runSarCheck(inc.id))}
            />
          ))}
        </div>
      </div>

      <div className="rqq-section">
        <h2 className="section-title">Responding</h2>
        {!loading && responding.length === 0 && <p className="section-caption">No responder currently en route.</p>}
        {!loading && responding.length > 0 && filteredResponding.length === 0 && (
          <p className="section-caption">No matches for "{query}".</p>
        )}
        <div className="rqq-card-grid">
          {filteredResponding.map((inc) => (
            <RespondingCard
              key={inc.id}
              incident={inc}
              busy={busyIds.has(inc.id)}
              onResolve={() => withBusy([inc.id], () => resolveIncident(inc.id))}
              onSarCheck={() => withBusy([inc.id], () => runSarCheck(inc.id))}
            />
          ))}
        </div>
      </div>

      <Card>
        <button type="button" className="disclosure-toggle" onClick={() => setResolvedOpen((o) => !o)}>
          <span>
            Resolved — most recent {resolved.length}
          </span>
          <span>{resolvedOpen ? "▲" : "▼"}</span>
        </button>
        {resolvedOpen && (
          <div className="disclosure-body">
            {resolved.length === 0 && <p className="section-caption">No resolved incidents yet.</p>}
            {resolved.length > 0 && filteredResolved.length === 0 && <p className="section-caption">No matches for "{query}".</p>}
            {filteredResolved.map((inc) => (
              <p key={inc.id} className="rqq-resolved-row">
                <code>{inc.id}</code>
                {inc.synthetic && <SyntheticBadge />} {hazardLabel(inc.hazard_type)} — {inc.district ?? "outside pilot district"} —
                resolved {inc.resolved_at?.slice(0, 16).replace("T", " ")} UTC — confidence {inc.confidence.score}/100 (
                {inc.confidence.band})
              </p>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
