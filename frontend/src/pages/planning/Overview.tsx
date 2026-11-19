import { TopBar } from "../../components/TopBar";
import { Card, CardHeader, KpiTile, LegendDot, LevelPill, ScoreBadge, StackedBar } from "../../components/ui";
import "./Overview.css";

// Mirrors Planning.dc.html's demo content 1:1.
const DISTRICT_VULNERABILITY = [
  { name: "Weija Gbawe Municipal", level: "Very High" as const },
  { name: "Korle Klottey Municipal", level: "High" as const },
  { name: "Ablekuma Central Municipal", level: "High" as const },
  { name: "Ablekuma North Municipal", level: "Moderate" as const },
  { name: "Ablekuma West Municipal", level: "Moderate" as const },
  { name: "Ayawaso Central Municipal", level: "Low" as const },
  { name: "Accra Metropolis", level: "Low" as const },
];

const ENCROACHMENT_BY_ASSEMBLY = [
  {
    name: "Weija Gbawe",
    cells: 160,
    segments: [
      { pct: 2.5, color: "var(--level-very-high)" },
      { pct: 10, color: "var(--level-moderate)" },
      { pct: 87.5, color: "var(--level-low)" },
    ],
  },
  {
    name: "Ablekuma North",
    cells: 35,
    segments: [
      { pct: 31, color: "var(--level-moderate)" },
      { pct: 69, color: "var(--level-low)" },
    ],
  },
  {
    name: "Korle Klottey",
    cells: 24,
    segments: [
      { pct: 25, color: "var(--level-moderate)" },
      { pct: 75, color: "var(--level-low)" },
    ],
  },
];

const DRAIN_PRIORITY = [
  { name: "Odaw Channel — Alajo segment", level: "Very High" as const, label: "Priority 1" },
  { name: "Onyasia Stream — Tetegu", level: "High" as const, label: "Priority 2" },
];

export function PlanningOverview() {
  return (
    <>
      <TopBar
        title="Planning Overview"
        subtitle="Longer-term risk, infrastructure, and enforcement across the pilot area"
      />

      <section aria-label="Key metrics" className="planning-kpis">
        <Card>
          <KpiTile label="Assemblies tracked" value="7" note="pilot grid, 1013 cells" />
        </Card>
        <Card>
          <KpiTile label="Cells near a channel" value="272" note="of 1013 pilot cells" />
        </Card>
        <Card>
          <KpiTile
            label="Worsening trend cells"
            value={<span style={{ color: "var(--level-very-high)" }}>5</span>}
            note="4 robust to the 2019 anomaly"
          />
        </Card>
        <Card>
          <KpiTile label="Possibly flood-contaminated" value="154" note={'"Improving" cells to read skeptically'} />
        </Card>
      </section>

      <section className="planning-body">
        <Card className="planning-vulnerability">
          <CardHeader title="District vulnerability" />
          <div className="planning-vuln-list">
            {DISTRICT_VULNERABILITY.map((d, i) => (
              <div key={d.name} className={`planning-vuln-row ${i === DISTRICT_VULNERABILITY.length - 1 ? "is-last" : ""}`}>
                <span className="planning-vuln-name">{d.name}</span>
                <LevelPill level={d.level} />
              </div>
            ))}
          </div>
        </Card>

        <div className="planning-side">
          <Card>
            <h2 className="planning-trend-title">Encroachment trend by assembly</h2>
            <p className="planning-trend-subtitle">Channel-adjacent cells, 2019–2026 NDBI slope</p>
            <div className="planning-trend-list">
              {ENCROACHMENT_BY_ASSEMBLY.map((a) => (
                <div key={a.name}>
                  <div className="planning-trend-row-label">
                    <span>{a.name}</span>
                    <span>{a.cells} cells</span>
                  </div>
                  <StackedBar segments={a.segments} />
                </div>
              ))}
            </div>
            <div className="planning-trend-legend">
              <LegendDot color="var(--level-very-high)" label="Worsening" />
              <LegendDot color="var(--level-moderate)" label="Stable" />
              <LegendDot color="var(--level-low)" label="Improving" />
            </div>
            <p className="planning-trend-note">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="planning-trend-note-icon">
                <path d="M12 4L21.5 20H2.5L12 4Z" stroke="#B8860B" strokeWidth="1.8" strokeLinejoin="round" />
                <path d="M12 10.5V14.5" stroke="#B8860B" strokeWidth="1.8" strokeLinecap="round" />
                <circle cx="12" cy="17" r="0.9" fill="#B8860B" />
              </svg>
              <span>
                154 "Improving" cells sit in an assembly with documented flood history — standing floodwater reads as
                non-built-up too. Confirmed via clean-day re-check for Weija Gbawe's 5 steepest cells.
              </span>
            </p>
          </Card>

          <Card>
            <CardHeader title="Drain maintenance priority" />
            <div className="planning-drain-list">
              {DRAIN_PRIORITY.map((d) => (
                <div key={d.name} className="planning-drain-row">
                  <span className="planning-drain-name">{d.name}</span>
                  <ScoreBadge level={d.level}>{d.label}</ScoreBadge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </section>
    </>
  );
}
