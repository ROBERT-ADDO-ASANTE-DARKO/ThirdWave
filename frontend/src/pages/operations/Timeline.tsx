import { useEffect, useMemo, useState } from "react";
import { fetchActiveIncidents, fetchPendingReports, fetchResolvedIncidents } from "../../api/incidents";
import { fetchReportTimeline } from "../../api/timeline";
import type { EventType, Incident, PendingReport, ReportTimeline } from "../../api/types";
import { INK_NAVY, LEVEL_HEX, SIGNAL_TEAL } from "../../colors";
import { hazardLabel } from "../../components/PendingQueue";
import { TopBar } from "../../components/TopBar";
import { Card } from "../../components/ui";
import "./Timeline.css";

// Mirrors streamlit_app/features/govt_timeline.py exactly -- same three
// endpoints merged into one report picker, same real-vs-reconstructed
// distinction (backend/report_events.py's docstring: a ReportEvent row
// is a real logged event; anything older is best-effort reconstructed
// from the report's own timestamp columns and always labeled as such,
// never presented as a precise record).

type QueueStatus = "Pending" | "Verified" | "Responding" | "Resolved";

interface RecentReport {
  id: string;
  hazard_type: string;
  district: string | null;
  submitted_at: string;
  queue_status: QueueStatus;
}

function toRecent(r: PendingReport | Incident, queue_status: QueueStatus): RecentReport {
  return { id: r.id, hazard_type: r.hazard_type, district: r.district, submitted_at: r.submitted_at, queue_status };
}

const EVENT_LABEL: Record<EventType, string> = {
  submitted: "Submitted",
  verified: "Verified",
  rejected: "Rejected",
  responder_assigned: "Responder assigned",
  resolved: "Resolved",
};

const EVENT_COLOR: Record<EventType, string> = {
  submitted: SIGNAL_TEAL,
  verified: LEVEL_HEX.Low,
  rejected: LEVEL_HEX["Very High"],
  responder_assigned: SIGNAL_TEAL,
  resolved: INK_NAVY,
};

function WarningIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="tl-warning-icon">
      <path d="M12 4L21.5 20H2.5L12 4Z" stroke="#B8860B" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M12 10.5V14.5" stroke="#B8860B" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="17" r="0.9" fill="#B8860B" />
    </svg>
  );
}

function EventIcon({ type }: { type: EventType }) {
  switch (type) {
    case "submitted":
      return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M3 11.5L12 4L21 11.5" stroke="#fff" strokeWidth="1.8" strokeLinejoin="round" />
          <path d="M5 10V20H19V10" stroke="#fff" strokeWidth="1.8" />
        </svg>
      );
    case "verified":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 12.5L9.5 18L20 6" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "rejected":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 5L19 19M19 5L5 19" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case "responder_assigned":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="8.5" stroke="#fff" strokeWidth="1.6" />
          <path d="M12 7V12L15.3 14" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "resolved":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M6 3.5V20.5M6 4.5H17L14.5 8L17 11.5H6" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      );
  }
}

export function Timeline() {
  const [recent, setRecent] = useState<RecentReport[]>([]);
  const [selected, setSelected] = useState("");
  const [typedId, setTypedId] = useState("");
  const [timeline, setTimeline] = useState<ReportTimeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchPendingReports(), fetchActiveIncidents(), fetchResolvedIncidents(30)])
      .then(([pending, active, resolved]) => {
        const rows = [
          ...pending.map((r) => toRecent(r, "Pending")),
          ...active.map((r) => toRecent(r, r.response_status === "responding" ? "Responding" : "Verified")),
          ...resolved.map((r) => toRecent(r, "Resolved")),
        ];
        rows.sort((a, b) => b.submitted_at.localeCompare(a.submitted_at));
        setRecent(rows);
      })
      .catch(() => setRecent([]));
  }, []);

  const reportId = typedId.trim() || selected;

  useEffect(() => {
    if (!reportId) {
      setTimeline(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchReportTimeline(reportId)
      .then((data) => !cancelled && setTimeline(data))
      .catch((err) => !cancelled && setError(err?.response?.data?.detail ?? err?.message ?? `Could not load timeline for ${reportId}.`))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  const options = useMemo(
    () => recent.map((r) => ({ value: r.id, label: `${r.id} — ${hazardLabel(r.hazard_type)} — ${r.district ?? "outside pilot district"} — ${r.queue_status}` })),
    [recent],
  );

  return (
    <>
      <TopBar title="Flood/Incident Timeline" subtitle="Full event history for one report, submission to resolution" />

      <div className="tl-picker-row">
        <label className="tl-picker-field">
          <span>Pick a recent report</span>
          <select
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setTypedId("");
            }}
          >
            <option value="">(type an ID instead)</option>
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="tl-picker-field tl-picker-field-narrow">
          <span>...or enter a report ID directly</span>
          <input
            type="text"
            placeholder="e.g. RPT-20261115-63C86A"
            value={typedId}
            onChange={(e) => {
              setTypedId(e.target.value);
              setSelected("");
            }}
          />
        </label>
      </div>

      {!reportId && <p className="section-caption">Pick a report above, or type an ID, to see its timeline.</p>}

      {reportId && error && (
        <Card>
          <p className="error-text">Could not load timeline for {reportId}: {error}</p>
        </Card>
      )}

      {reportId && !error && loading && <p className="section-caption">Loading…</p>}

      {reportId && !error && !loading && timeline && timeline.events.length === 0 && (
        <Card>
          <p className="section-caption">No events at all for this report — it may not exist.</p>
        </Card>
      )}

      {timeline && timeline.events.length > 0 && (
        <>
          <Card className="tl-card">
            <div className="tl-list">
              {timeline.events.map((e, i) => (
                <div key={i} className="tl-row">
                  <div className="tl-rail">
                    <div className="tl-dot" style={{ background: EVENT_COLOR[e.event_type] }}>
                      <EventIcon type={e.event_type} />
                    </div>
                    {i < timeline.events.length - 1 && <div className="tl-line" />}
                  </div>
                  <div className="tl-body">
                    <span className="tl-label">{EVENT_LABEL[e.event_type]}</span>
                    <p className="tl-timestamp">{e.occurred_at.slice(0, 19).replace("T", " ")} UTC{e.detail ? ` — ${e.detail}` : ""}</p>
                    {e.reconstructed && (
                      <p className="tl-reconstructed">
                        <WarningIcon /> {e.note}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {timeline.untimed_notes.length > 0 && (
            <div className="tl-untimed-banner">
              {timeline.untimed_notes.map((note, i) => (
                <p key={i}>
                  <WarningIcon /> {note}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
