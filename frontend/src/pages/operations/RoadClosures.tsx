import { useEffect, useMemo, useRef, useState } from "react";
import type L from "leaflet";
import { Polyline, MapContainer, Tooltip } from "react-leaflet";
import { fetchRoadClosureScores, fetchRoadClosuresByIncident } from "../../api/roadClosures";
import type { Highway, RoadClosureByIncident, RoadClosureScore } from "../../api/types";
import { LEVEL_HEX } from "../../colors";
import { FullscreenToggle } from "../../components/FullscreenToggle";
import { MapStylePicker, StyleTileLayer, type MapStyle } from "../../components/MapStyle";
import { SyntheticBadge, hazardLabel } from "../../components/PendingQueue";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile, ScoreBadge } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./RoadClosures.css";

// Mirrors streamlit_app/features/govt_road_closures.py exactly -- two
// views over the SAME underlying avoidance data Safer Routing already
// computes (route_engine.py's INCIDENT_AVOID_RADIUS_DEG): a per-road
// weighted closure score (the headline table/map) and a simpler
// per-incident "what roads does THIS incident touch" view underneath.
// Advisory only, in both -- an officer decides whether to actually
// close anything.

function highwayLabel(h: Highway): string {
  if (!h) return "unknown";
  return Array.isArray(h) ? h.join(" / ") : h;
}

// A generic OSM name like "Unnamed road" legitimately recurs across
// unrelated, non-contiguous regions (pilot/Lower Volta/Ayawaso West/
// Madina) -- road_closure_score.py now keeps those as separate rows
// (keyed by name+region server-side) instead of merging them, so
// row.name alone is no longer a unique React key here either.
function rowKey(row: RoadClosureScore): string {
  return `${row.name}::${row.incident_ids.join(",")}`;
}

const SEVERITY_LEVELS = ["Very High", "High", "Moderate", "Low"] as const;

const SIGNAL_ROWS: { key: keyof RoadClosureScore["signals"]; label: string; weightPct: number }[] = [
  { key: "water_depth", label: "Water depth", weightPct: 35 },
  { key: "report_count", label: "Reports", weightPct: 25 },
  { key: "road_classification", label: "Road class", weightPct: 15 },
  { key: "historical_frequency", label: "Flood history", weightPct: 15 },
  { key: "rainfall_forecast", label: "Rainfall", weightPct: 10 },
];

function signalRawText(row: RoadClosureScore, key: (typeof SIGNAL_ROWS)[number]["key"]): string {
  switch (key) {
    case "water_depth":
      return row.max_depth_hi_m != null ? `${row.max_depth_hi_m.toFixed(1)}m` : "not estimated";
    case "report_count":
      return `${row.n_verified_reports} report(s)`;
    case "road_classification":
      return highwayLabel(row.highway);
    case "historical_frequency":
      return `${row.n_nearby_historical_events} event(s)`;
    case "rainfall_forecast":
      return row.near_term_rainfall_mm != null ? `${row.near_term_rainfall_mm.toFixed(1)}mm` : "unavailable";
  }
}

function SegmentRow({ row }: { row: RoadClosureScore }) {
  return (
    <details className="rc-row">
      <summary className="rc-row-summary">
        <span className="rc-row-grid">
          <span className="rc-road-name">{row.name}</span>
          <ScoreBadge level={row.level}>
            {row.emoji} {row.action}
          </ScoreBadge>
          <span className="rc-cell">{row.closure_score}</span>
          <span className="rc-cell">{row.max_depth_hi_m != null ? `${row.max_depth_hi_m.toFixed(1)}m` : "not estimated"}</span>
          <span className="rc-cell">{row.n_verified_reports}</span>
        </span>
      </summary>
      <div className="rc-breakdown">
        <span className="rc-breakdown-title">
          Why {row.name} scored {row.closure_score}
        </span>
        <div className="rc-breakdown-rows">
          {SIGNAL_ROWS.map(({ key, label, weightPct }) => (
            <div key={key} className="rc-breakdown-row">
              <span className="rc-breakdown-label">
                {label} ({weightPct}%)
              </span>
              <div className="rc-breakdown-track">
                <div className="rc-breakdown-fill" style={{ width: `${row.signals[key] * 100}%` }} />
              </div>
              <span className="rc-breakdown-value">{signalRawText(row, key)}</span>
            </div>
          ))}
        </div>
        <p className="rc-breakdown-note">
          {row.action_basis === "depth"
            ? `Action decided by the ${row.max_depth_hi_m?.toFixed(1)}m depth reading above, not the closure score.`
            : "Action decided by the closure score (no depth estimate was available from any report here)."}
        </p>
      </div>
    </details>
  );
}

function ByIncidentRow({ d }: { d: RoadClosureByIncident }) {
  return (
    <div className="rc-incident-row">
      <div className="rc-incident-head">
        <code>{d.id}</code>
        {d.synthetic && <SyntheticBadge />}
        <strong>{hazardLabel(d.hazard_type)}</strong>
        <span className="rc-incident-district">{d.district ?? "outside pilot district"}</span>
      </div>
      <p className="rq-report-caption">{d.location_label ?? `${d.lat.toFixed(4)}, ${d.lon.toFixed(4)}`}</p>
      {d.affected_segments.length === 0 ? (
        <p className="section-caption">No mapped road segment found within the avoidance radius of this point.</p>
      ) : (
        <ul className="rc-incident-segments">
          {d.affected_segments.map((seg) => (
            <li key={seg.name}>
              <strong>{seg.name}</strong> ({highwayLabel(seg.highway)}) — {seg.n_edges} edge(s)
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RoadClosures() {
  const [scores, setScores] = useState<RoadClosureScore[]>([]);
  const [byIncident, setByIncident] = useState<RoadClosureByIncident[]>([]);
  const [byIncidentOpen, setByIncidentOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mapStyle, setMapStyle] = useState<MapStyle>("Streets");
  const [query, setQuery] = useState("");
  const [district, setDistrict] = useState("all");
  const mapWrapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<L.Map>(null);

  // road_closure_score.compute() groups segments by incident proximity,
  // not by district directly -- a flagged segment's district(s) have to
  // be derived from which incident(s) flagged it (incident_ids), cross-
  // referenced against the by-incident view's real district field.
  const districtByIncidentId = useMemo(
    () => Object.fromEntries(byIncident.map((d) => [d.id, d.district])),
    [byIncident],
  );
  const districtsForRow = (row: RoadClosureScore): string[] =>
    [...new Set(row.incident_ids.map((id) => districtByIncidentId[id]).filter((d): d is string => !!d))];

  const districtOptions = useMemo(
    () => [...new Set(byIncident.map((d) => d.district).filter((d): d is string => !!d))].sort(),
    [byIncident],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchRoadClosureScores(), fetchRoadClosuresByIncident()])
      .then(([sc, bi]) => {
        if (cancelled) return;
        setScores(sc);
        setByIncident(bi);
        setError(null);
      })
      .catch((err) => !cancelled && setError(err?.response?.data?.detail ?? err?.message ?? "Could not reach the backend."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredScores = scores.filter(
    (row) =>
      (district === "all" || districtsForRow(row).includes(district)) &&
      matchesQuery([row.name, highwayLabel(row.highway)], query),
  );
  const filteredByIncident = byIncident.filter(
    (d) => (district === "all" || d.district === district) && matchesQuery([d.id, d.district, d.location_label, d.hazard_type], query),
  );

  const center = useMemo((): [number, number] => {
    const points = filteredScores.flatMap((s) => s.coords.flat());
    if (points.length === 0) return [5.6037, -0.187];
    const lat = points.reduce((s, p) => s + p[0], 0) / points.length;
    const lon = points.reduce((s, p) => s + p[1], 0) / points.length;
    return [lat, lon];
  }, [filteredScores]);

  // MapContainer's center/zoom props only apply at mount -- react-leaflet
  // doesn't re-center an already-live map when they change later. Without
  // this, picking a different district recomputes `center` above but the
  // map itself never moves. Regions can be ~100km apart (pilot vs. Lower
  // Volta vs. Ayawaso West/Madina), so fitBounds over every point, not a
  // fixed zoom at the averaged centroid, is what actually gets the
  // selected district on screen.
  useEffect(() => {
    const map = leafletMapRef.current;
    if (!map) return;
    const points = filteredScores.flatMap((s) => s.coords.flat());
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 15);
    } else {
      map.fitBounds(points, { padding: [50, 50], maxZoom: 16 });
    }
  }, [filteredScores]);

  const fullClosure = scores.filter((r) => r.action === "Full closure").length;
  const noAction = scores.filter((r) => r.action === "No action").length;

  return (
    <>
      <TopBar
        title="Road Closure Recommendations"
        subtitle="Advisory only — an officer still decides whether to actually close anything"
        actions={<MapStylePicker value={mapStyle} onChange={setMapStyle} />}
        search={{ value: query, onChange: setQuery, placeholder: "Search roads by name or type…" }}
      />

      {error && (
        <Card>
          <p className="error-text">Could not load road closure scores: {error}</p>
        </Card>
      )}

      <section className="section-kpis">
        <Card>
          <KpiTile label="Road segments flagged" value={scores.length} />
        </Card>
        <Card>
          <KpiTile label="Full closure recommended" value={fullClosure} />
        </Card>
        <Card>
          <KpiTile label="No action needed" value={noAction} />
        </Card>
      </section>

      {!loading && scores.length === 0 && !error && (
        <Card>
          <p className="section-caption">No active incidents right now — nothing to flag for closure.</p>
        </Card>
      )}

      {scores.length > 0 && (
        <div className="rc-filter-row">
          <label className="rc-filter-field">
            <span>District / town</span>
            <select value={district} onChange={(e) => setDistrict(e.target.value)}>
              <option value="all">All districts with active incidents ({districtOptions.length})</option>
              {districtOptions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {scores.length > 0 && filteredScores.length === 0 && (
        <Card>
          <p className="section-caption">
            {query
              ? `No flagged segments match "${query}".`
              : `No flagged road segments in ${district} — the loaded road network (pilot district, Lower Volta basin, Ayawaso West, and Madina) may not cover this area yet, even though the incident itself is real.`}
          </p>
        </Card>
      )}

      {filteredScores.length > 0 && (
        <div className="rc-body">
          <Card className="rc-table-card">
            <h2 className="section-title">Flagged segments{district !== "all" ? ` — ${district}` : ""}</h2>
            <div className="rc-row-grid rc-header-row">
              <span>Road</span>
              <span>Recommendation</span>
              <span>Score</span>
              <span>Depth</span>
              <span>Reports</span>
            </div>
            <div className="rc-table-rows">
              {filteredScores.map((row) => (
                <SegmentRow key={rowKey(row)} row={row} />
              ))}
            </div>
          </Card>

          <div className="rc-map-wrap" ref={mapWrapRef}>
            <MapContainer ref={leafletMapRef} center={center} zoom={14} className="rc-map">
              <StyleTileLayer style={mapStyle} />
              {filteredScores.map((row) =>
                row.coords.map((line, i) => (
                  <Polyline key={`${rowKey(row)}-${i}`} positions={line} pathOptions={{ color: LEVEL_HEX[row.level], weight: 6, opacity: 0.85 }}>
                    <Tooltip>
                      {row.emoji} {row.name} ({highwayLabel(row.highway)}) — {row.action}
                    </Tooltip>
                  </Polyline>
                )),
              )}
            </MapContainer>
            <FullscreenToggle targetRef={mapWrapRef} onToggle={() => setTimeout(() => leafletMapRef.current?.invalidateSize(), 50)} />
            <div className="rc-map-legend">
              {SEVERITY_LEVELS.map((lv) => (
                <span key={lv} className="rc-legend-item">
                  <span className="rc-legend-swatch" style={{ background: LEVEL_HEX[lv] }} />
                  {lv} urgency
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      <Card>
        <button type="button" className="disclosure-toggle" onClick={() => setByIncidentOpen((o) => !o)}>
          <span>Detail: by incident instead of by road</span>
          <span>{byIncidentOpen ? "▲" : "▼"}</span>
        </button>
        {byIncidentOpen && (
          <div className="rc-incident-list">
            {byIncident.length === 0 && <p className="section-caption">No active incidents right now.</p>}
            {byIncident.length > 0 && filteredByIncident.length === 0 && (
              <p className="section-caption">No incidents match the current district/search filter.</p>
            )}
            {filteredByIncident.map((d) => (
              <ByIncidentRow key={d.id} d={d} />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
