import type { Confidence, Zone } from "../api/types";
import { CONFIDENCE_COLOR, LEVEL_HEX } from "../colors";
import "./ReportBadges.css";

// Shared by Incident Verification and Reports Queue -- both render the
// exact same zone/confidence context on a report card, mirroring
// govt_verification_sandbox.py's _render_report_card() and
// govt_reports_queue.py's _zone_badge()/_confidence_badge().

export function ZoneBadge({ zone }: { zone: Zone | null }) {
  if (!zone) {
    return (
      <p className="badge-caption">
        This location falls outside all scored coverage (pilot or extended) — no pre-existing static score to
        cross-check against.
      </p>
    );
  }
  const color = LEVEL_HEX[zone.level];
  return (
    <>
      <span className="context-badge" style={{ background: `${color}22`, borderColor: color, color }}>
        Verification context: this zone's existing static score is{" "}
        <b>
          {zone.score.toFixed(1)} ({zone.level})
        </b>
        {zone.extended ? " (extended-coverage grid)" : ""} — {zone.id.replace("RZ-", "")}
      </span>
      {zone.extended && (
        <p className="badge-caption">
          Extended-coverage grid, not the MVP pilot — same statistical SAR/DEM/land-cover formula, which
          structurally can't see a one-off event like a dam release.
        </p>
      )}
    </>
  );
}

function confidenceDetailLines(c: Confidence): string[] {
  const lines: string[] = [];
  const pc = c.signals.photo_check;
  if (!pc || pc.status === "no_photo") lines.push("No photo submitted.");
  else if (pc.status === "checked") {
    lines.push(`Photo AI check: ${pc.shows_flooding ? "shows flooding" : "does not show flooding"} — ${pc.note || "no further detail"}`);
  } else {
    lines.push(`Photo AI check failed: ${pc.detail ?? "unknown error"}`);
  }

  const n = c.signals.cluster_size ?? 1;
  lines.push(n > 1 ? `${n} independent report(s) within ~300m.` : "Only 1 report at this location so far.");
  lines.push(c.signals.news_hits ? `${c.signals.news_hits} corroborating news hit(s) (last 72h).` : "No corroborating news found.");
  lines.push(
    c.signals.nearby_historical_events
      ? `${c.signals.nearby_historical_events} documented flood event(s) nearby.`
      : "No documented flood history nearby.",
  );

  const sar = c.signals.sar;
  if (sar?.status === "checked") lines.push(`Satellite (SAR) check: ${sar.verdict}`);
  else if (sar?.status === "not_yet_checked") lines.push("Satellite (SAR) check: not yet run.");
  else if (sar?.status === "not_applicable") lines.push("Satellite (SAR) check: only available once verified.");
  else if (sar) lines.push(`Satellite (SAR) check failed: ${sar.detail ?? "unknown error"}`);
  return lines;
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const color = CONFIDENCE_COLOR[confidence.band] ?? "#6B7280";
  return (
    <details className="confidence-details">
      <summary className="context-badge" style={{ background: `${color}1A`, borderColor: color, color }}>
        Confidence: <b>{confidence.score}/100 ({confidence.band})</b>
      </summary>
      <p className="badge-caption confidence-why">Why this score? (aid, not a verdict — use your own judgment)</p>
      <ul className="confidence-lines">
        {confidenceDetailLines(confidence).map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </details>
  );
}
