import { backendAsset } from "../api/client";
import type { Cluster, PendingReport } from "../api/types";
import { ConfidenceBadge, ZoneBadge } from "./ReportBadges";
import { Card } from "./ui";
import "./PendingQueue.css";

// Shared by Incident Verification and Reports Queue -- both render the
// same pending-report/cluster card with identical Verify/Reject actions
// (govt_verification_sandbox.py's _render_report_card() and
// govt_reports_queue.py's _render_pending_card(), same shape either way).

export function hazardLabel(h: string) {
  return h.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function SyntheticBadge() {
  return <span className="rq-synthetic-badge">SYNTHETIC</span>;
}

export function ReportCard({
  report,
  busy,
  onVerify,
  onReject,
}: {
  report: PendingReport;
  busy: boolean;
  onVerify: () => void;
  onReject: () => void;
}) {
  const photo = backendAsset(report.annotated_photo_url ?? report.photo_url);
  return (
    <div className="rq-report-card">
      <div className="rq-report-photo">
        {photo ? (
          <img src={photo} alt={report.annotated_photo_url ? "AI-annotated submission" : "Submitted photo"} />
        ) : (
          <span className="rq-report-photo-empty">{report.has_photo ? "Photo pending AI annotation" : "No photo submitted"}</span>
        )}
        {report.annotated_photo_url && <span className="rq-ai-badge">AI</span>}
      </div>

      <div className="rq-report-main">
        <div className="rq-report-head">
          <code>{report.id}</code>
          {report.synthetic && <SyntheticBadge />}
          <strong>{hazardLabel(report.hazard_type)}</strong>
          <span className="rq-report-district">{report.district ?? "outside pilot district"}</span>
        </div>
        <p className="rq-report-location">{report.location_label ?? `${report.lat.toFixed(4)}, ${report.lon.toFixed(4)}`}</p>
        <p className="rq-report-desc">{report.description}</p>
        {report.depth_hi_m != null && (
          <p className="rq-report-depth">
            Estimated depth: {report.depth_lo_m?.toFixed(1)}–{report.depth_hi_m.toFixed(1)}m
          </p>
        )}

        <div className="rq-confidence-row">
          <ConfidenceBadge confidence={report.confidence} />
        </div>
        <ZoneBadge zone={report.zone} />
      </div>

      <div className="rq-report-actions">
        <button type="button" className="rq-btn rq-btn-verify" disabled={busy} onClick={onVerify}>
          Verify
        </button>
        <button type="button" className="rq-btn rq-btn-reject" disabled={busy} onClick={onReject}>
          Reject
        </button>
      </div>
    </div>
  );
}

export function ClusterCard({
  cluster,
  busyIds,
  onVerify,
  onReject,
  onVerifyAll,
  onRejectAll,
}: {
  cluster: Cluster;
  busyIds: Set<string>;
  onVerify: (id: string) => void;
  onReject: (id: string) => void;
  onVerifyAll: (ids: string[]) => void;
  onRejectAll: (ids: string[]) => void;
}) {
  const ids = cluster.reports.map((r) => r.id);
  return (
    <Card className="rq-cluster-card">
      {cluster.n_reports > 1 && (
        <div className="rq-cluster-header">
          <span>
            Incident cluster — {cluster.n_reports} reports — {cluster.hazard_types.map(hazardLabel).join(", ")} —{" "}
            {cluster.district ?? "outside pilot district"}
            {cluster.any_synthetic && " · includes synthetic"}
          </span>
          <div className="rq-cluster-actions">
            <button type="button" className="rq-btn rq-btn-verify rq-btn-sm" onClick={() => onVerifyAll(ids)}>
              Verify all {cluster.n_reports}
            </button>
            <button type="button" className="rq-btn rq-btn-reject rq-btn-sm" onClick={() => onRejectAll(ids)}>
              Reject all {cluster.n_reports}
            </button>
          </div>
        </div>
      )}
      {cluster.corroborating_news.length > 0 && (
        <p className="rq-report-caption">
          {cluster.corroborating_news.length} possibly-related news report(s) in the last 72h — place-name text
          match, not a confirmed link.
        </p>
      )}
      <div className="rq-report-list">
        {cluster.reports.map((r) => (
          <ReportCard key={r.id} report={r} busy={busyIds.has(r.id)} onVerify={() => onVerify(r.id)} onReject={() => onReject(r.id)} />
        ))}
      </div>
    </Card>
  );
}
