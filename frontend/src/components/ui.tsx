import type { ReactNode } from "react";
import "./ui.css";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`uw-card ${className}`}>{children}</div>;
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="uw-card-header">
      <h2 className="uw-card-title">{title}</h2>
      {action}
    </div>
  );
}

export type Level = "Low" | "Moderate" | "High" | "Very High";

export const LEVEL_COLOR: Record<Level, string> = {
  Low: "var(--level-low)",
  Moderate: "var(--level-moderate)",
  High: "var(--level-high)",
  "Very High": "var(--level-very-high)",
};

export function LevelPill({ level }: { level: Level }) {
  return (
    <span className="uw-pill" style={{ background: `${LEVEL_COLOR[level]}1A`, color: LEVEL_COLOR[level] }}>
      <span className="uw-pill-dot" style={{ background: LEVEL_COLOR[level] }} />
      {level}
    </span>
  );
}

export function Pill({ children, tone = "teal" }: { children: ReactNode; tone?: "teal" | "neutral" | "green" }) {
  const toneMap = {
    teal: { bg: "var(--signal-teal)", fg: "var(--signal-teal)" },
    neutral: { bg: "var(--text-muted)", fg: "var(--text-secondary)" },
    green: { bg: "var(--level-low)", fg: "var(--level-low)" },
  } as const;
  const t = toneMap[tone];
  return (
    <span className="uw-pill uw-pill-tag" style={{ background: `${t.bg}1A`, color: t.fg }}>
      {children}
    </span>
  );
}

export function KpiTile({
  label,
  value,
  unit,
  note,
  noteTone = "muted",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  note?: ReactNode;
  noteTone?: "muted" | "good" | "bad";
}) {
  return (
    <div className="uw-kpi">
      <span className="uw-kpi-label">{label}</span>
      <div className="uw-kpi-value">
        {value}
        {unit && <span className="uw-kpi-unit"> {unit}</span>}
      </div>
      {note && <span className={`uw-kpi-note uw-kpi-note-${noteTone}`}>{note}</span>}
    </div>
  );
}

export function ProgressRow({ label, value, max, display }: { label: string; value: number; max: number; display: ReactNode }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="uw-progress-row">
      <span className="uw-progress-label">{label}</span>
      <div className="uw-progress-track">
        <div className="uw-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="uw-progress-value">{display}</span>
    </div>
  );
}

export function PlaceholderNotice({ children }: { children: ReactNode }) {
  return <div className="uw-placeholder-notice">{children}</div>;
}

export function ScoreBadge({ level, children }: { level: Level; children: ReactNode }) {
  return (
    <span className="uw-pill uw-score-badge" style={{ background: `${LEVEL_COLOR[level]}1A`, color: LEVEL_COLOR[level] }}>
      {children}
    </span>
  );
}

export function StackedBar({ segments }: { segments: { pct: number; color: string }[] }) {
  return (
    <div className="uw-stacked-bar">
      {segments.map((seg, i) => (
        <div key={i} style={{ width: `${seg.pct}%`, background: seg.color }} />
      ))}
    </div>
  );
}

export function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="uw-legend-dot">
      <span style={{ background: color }} />
      {label}
    </span>
  );
}
