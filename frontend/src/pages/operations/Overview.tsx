import { Link } from "react-router-dom";
import { TopBar } from "../../components/TopBar";
import { Card, CardHeader, KpiTile, LevelPill, Pill, ProgressRow, ScoreBadge } from "../../components/ui";
import "./Overview.css";

// Content mirrors the Design-canvas mockup's Main.dc.html 1:1 (same demo
// incidents, road segments, briefing-queue entry, district report counts)
// so this is a faithful React build of that concept, not a reinterpretation.
const ACTIVE_INCIDENTS = [
  {
    id: "INC-20261117-A41C",
    level: "Very High" as const,
    description: "Kwame Nkrumah Circle · Korle Klottey Municipal · depth 1.4m",
    tags: [
      { label: "NADMO: Korle Klottey", tone: "teal" as const },
      { label: "Fire: Ghana Fire Service", tone: "teal" as const },
      { label: "Medical: Ridge Hospital", tone: "teal" as const },
    ],
  },
  {
    id: "INC-20261117-B2F1",
    level: "High" as const,
    description: "Tetegu, Weija Gbawe Municipal · confidence 0.82, 3 corroborating reports",
    tags: [
      { label: "NADMO: Weija Gbawe", tone: "teal" as const },
      { label: "Awaiting dispatch", tone: "neutral" as const },
    ],
  },
  {
    id: "INC-20261116-9D03",
    level: "Moderate" as const,
    description: "North Kaneshie, Ablekuma Central Municipal · responding, ETA 12 min",
    tags: [{ label: "NADMO: Ablekuma Central", tone: "green" as const }],
  },
];

const ROAD_CLOSURES = [
  { name: "Nsawam Road", score: 86, action: "Full closure", level: "Very High" as const },
  { name: "Ring Road Central", score: 71, action: "Emergency only", level: "High" as const },
  { name: "Tip Toe Lane", score: 52, action: "Monitor", level: "Moderate" as const },
];

const DISTRICT_REPORTS = [
  { district: "Weija Gbawe", count: 11, max: 12 },
  { district: "Korle Klottey", count: 7, max: 12 },
  { district: "Ablekuma North", count: 5, max: 12 },
  { district: "Accra Metropolis", count: 2, max: 12 },
];

export function OperationsOverview() {
  return (
    <>
      <TopBar
        title="Operations Overview"
        subtitle="Live incident coordination across 7 pilot assemblies · Tuesday, 18 Nov 2026"
      />

      <section aria-label="Key metrics" className="overview-kpis">
        <Card>
          <KpiTile label="Active incidents" value="4" note="1 Very High severity" noteTone="bad" />
        </Card>
        <Card>
          <KpiTile label="Pending verification" value="3" note="2 synthetic, 1 live report" />
        </Card>
        <Card>
          <KpiTile
            label="Avg. verification → response"
            value="18"
            unit="min"
            note="n = 11 resolved incidents"
            noteTone="good"
          />
        </Card>
        <Card>
          <KpiTile
            label="Districts flagged for briefing"
            value="1"
            note={<Link to="/operations/briefing-review">Review queue →</Link>}
          />
        </Card>
      </section>

      <section className="overview-body">
        <Card className="overview-incidents">
          <CardHeader
            title="Active incidents — resource coordination"
            action={<Link to="/operations/live-map">View all</Link>}
          />
          <div className="overview-incident-list">
            {ACTIVE_INCIDENTS.map((incident) => (
              <div key={incident.id} className="overview-incident-row">
                <div className="overview-incident-main">
                  <div className="overview-incident-head">
                    <span className="overview-incident-id">{incident.id}</span>
                    <LevelPill level={incident.level} />
                  </div>
                  <p className="overview-incident-desc">{incident.description}</p>
                </div>
                <div className="overview-incident-tags">
                  {incident.tags.map((tag) => (
                    <Pill key={tag.label} tone={tag.tone}>
                      {tag.label}
                    </Pill>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="overview-side">
          <Card>
            <CardHeader title="Road closure recommendations" />
            <div className="overview-closures">
              {ROAD_CLOSURES.map((road) => (
                <div key={road.name} className="overview-closure-row">
                  <span className="overview-closure-name">{road.name}</span>
                  <ScoreBadge level={road.level}>
                    {road.score} · {road.action}
                  </ScoreBadge>
                </div>
              ))}
            </div>
            <Link to="/operations/road-closures" className="overview-link-more">
              See all 10 flagged segments →
            </Link>
          </Card>

          <div className="overview-briefing-card">
            <h2 className="overview-briefing-title">Briefing queue</h2>
            <p className="overview-briefing-text">
              La-Nkwantanang-Madina Municipal — nearest building 0.0m from a mapped waterway (65
              buildings within 20m).
            </p>
            <Link to="/operations/briefing-review" className="overview-briefing-cta">
              Draft briefing →
            </Link>
          </div>

          <Card>
            <CardHeader title="Reports by district (7d)" />
            <div className="overview-reports">
              {DISTRICT_REPORTS.map((row) => (
                <ProgressRow
                  key={row.district}
                  label={row.district}
                  value={row.count}
                  max={row.max}
                  display={row.count}
                />
              ))}
            </div>
          </Card>
        </div>
      </section>
    </>
  );
}
