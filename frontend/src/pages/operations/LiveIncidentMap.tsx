import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { CircleMarker, MapContainer, Marker, Popup, Tooltip } from "react-leaflet";
import { fetchActiveIncidents, fetchPendingClusters } from "../../api/incidents";
import type { Cluster, HazardType, Incident, Level } from "../../api/types";
import { INK_NAVY, LEVEL_HEX, worstLevel } from "../../colors";
import { FullscreenToggle } from "../../components/FullscreenToggle";
import { MapStylePicker, StyleTileLayer, type MapStyle } from "../../components/MapStyle";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile, LegendDot, PlaceholderNotice } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./LiveIncidentMap.css";

const ACCRA_FALLBACK_CENTER: [number, number] = [5.6037, -0.187];

const HAZARD_TYPES: HazardType[] = ["urban_flood", "flash_flood", "river_flood"];
const SEVERITY_LEVELS: Level[] = ["Very High", "High", "Moderate", "Low"];

function hazardLabel(h: HazardType) {
  return h.replace("_", " ");
}

function incidentIcon(responding: boolean) {
  const color = responding ? "#1E5FA8" : "#D4820A";
  return L.divIcon({
    className: "incident-divicon",
    html: `<svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M12 3L21.5 20H2.5L12 3Z" fill="${color}" stroke="#FFFFFF" stroke-width="1.5" stroke-linejoin="round"/><path d="M12 9.5V13.5" stroke="#FFFFFF" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="16.3" r="0.9" fill="#FFFFFF"/></svg>`,
    iconSize: [26, 26],
    iconAnchor: [13, 22],
  });
}

export function LiveIncidentMap() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [district, setDistrict] = useState<string>("all");
  const [hazardFilter, setHazardFilter] = useState<Set<HazardType>>(new Set(HAZARD_TYPES));
  const [severityFilter, setSeverityFilter] = useState<Set<Level>>(new Set(SEVERITY_LEVELS));
  const [mapStyle, setMapStyle] = useState<MapStyle>("Streets");
  const mapWrapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<L.Map>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchActiveIncidents(), fetchPendingClusters()])
      .then(([inc, clu]) => {
        if (cancelled) return;
        setIncidents(inc);
        setClusters(clu);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.response?.data?.detail ?? err?.message ?? "Could not reach the backend.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const districtOptions = useMemo(() => {
    const set = new Set<string>();
    incidents.forEach((i) => i.district && set.add(i.district));
    clusters.forEach((c) => c.district && set.add(c.district));
    return Array.from(set).sort();
  }, [incidents, clusters]);

  const filteredIncidents = useMemo(
    () =>
      incidents.filter(
        (i) =>
          (district === "all" || i.district === district) &&
          hazardFilter.has(i.hazard_type) &&
          (!i.zone || severityFilter.has(i.zone.level)) &&
          matchesQuery([i.id, i.district, i.location_label], query),
      ),
    [incidents, district, hazardFilter, severityFilter, query],
  );

  const filteredClusters = useMemo(
    () =>
      clusters.filter((c) => {
        if (district !== "all" && c.district !== district) return false;
        if (!c.hazard_types.some((h) => hazardFilter.has(h))) return false;
        const level = worstLevel(c.reports.map((r) => r.zone?.level));
        if (level && !severityFilter.has(level)) return false;
        return matchesQuery([c.district], query) || c.reports.some((r) => matchesQuery([r.id, r.location_label], query));
      }),
    [clusters, district, hazardFilter, severityFilter, query],
  );

  const center = useMemo((): [number, number] => {
    const points: [number, number][] = [
      ...filteredClusters.map((c): [number, number] => [c.centroid.lat, c.centroid.lon]),
      ...filteredIncidents.map((i): [number, number] => [i.lat, i.lon]),
    ];
    if (points.length === 0) return ACCRA_FALLBACK_CENTER;
    const lat = points.reduce((s, p) => s + p[0], 0) / points.length;
    const lon = points.reduce((s, p) => s + p[1], 0) / points.length;
    return [lat, lon];
  }, [filteredClusters, filteredIncidents]);

  // MapContainer's center prop only applies at mount -- react-leaflet
  // doesn't move an already-live map when it changes later. Changing the
  // district/hazard/severity filters or typing a search recomputes
  // `center` above but, without this, the map never follows (same root
  // cause as the Road Closures screen's "map doesn't adjust" bug).
  useEffect(() => {
    const map = leafletMapRef.current;
    if (!map) return;
    const points: [number, number][] = [
      ...filteredClusters.map((c): [number, number] => [c.centroid.lat, c.centroid.lon]),
      ...filteredIncidents.map((i): [number, number] => [i.lat, i.lon]),
    ];
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 15);
    } else {
      map.fitBounds(points, { padding: [50, 50], maxZoom: 15 });
    }
  }, [filteredClusters, filteredIncidents]);

  const nPending = clusters.reduce((s, c) => s + c.n_reports, 0);
  const nResponding = incidents.filter((i) => i.response_status === "responding").length;

  function toggle<T>(set: Set<T>, value: T, setter: (s: Set<T>) => void) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  return (
    <>
      <TopBar
        title="Live Incident Map"
        subtitle={`${incidents.length} active incident${incidents.length === 1 ? "" : "s"} across the pilot area · pending clusters and verified incidents pulled live from the backend`}
        actions={<MapStylePicker value={mapStyle} onChange={setMapStyle} />}
        search={{ value: query, onChange: setQuery, placeholder: "Search by report ID, location, or district…" }}
      />

      {error && (
        <Card>
          <PlaceholderNotice>Could not load live incident data: {error}</PlaceholderNotice>
        </Card>
      )}

      <section className="live-map-kpis">
        <Card>
          <KpiTile label="Pending clusters" value={clusters.length} />
        </Card>
        <Card>
          <KpiTile label="Pending reports" value={nPending} />
        </Card>
        <Card>
          <KpiTile label="Active incidents" value={incidents.length} />
        </Card>
        <Card>
          <KpiTile label="Responder assigned" value={nResponding} />
        </Card>
      </section>

      <div className="live-map-body">
        <aside className="live-map-filters">
          <div className="live-map-filter-group">
            <span className="live-map-filter-label">District</span>
            <select value={district} onChange={(e) => setDistrict(e.target.value)} className="live-map-select">
              <option value="all">All {districtOptions.length || 7} pilot assemblies</option>
              {districtOptions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          <div className="live-map-filter-group">
            <span className="live-map-filter-label">Hazard type</span>
            {HAZARD_TYPES.map((h) => (
              <label key={h} className="live-map-checkbox">
                <input type="checkbox" checked={hazardFilter.has(h)} onChange={() => toggle(hazardFilter, h, setHazardFilter)} />
                {hazardLabel(h)}
              </label>
            ))}
          </div>

          <div className="live-map-filter-group">
            <span className="live-map-filter-label">Severity</span>
            {SEVERITY_LEVELS.map((lv) => (
              <label key={lv} className="live-map-checkbox" style={{ color: LEVEL_HEX[lv], fontWeight: 700 }}>
                <input type="checkbox" checked={severityFilter.has(lv)} onChange={() => toggle(severityFilter, lv, setSeverityFilter)} />
                {lv}
              </label>
            ))}
          </div>
        </aside>

        <div className="live-map-canvas" ref={mapWrapRef}>
          {loading ? (
            <div className="live-map-loading">Loading live incident data…</div>
          ) : (
            <MapContainer ref={leafletMapRef} center={center} zoom={11} className="live-map-leaflet">
              <StyleTileLayer style={mapStyle} />

              {filteredClusters.map((c, i) => {
                const level = worstLevel(c.reports.map((r) => r.zone?.level));
                const color = level ? LEVEL_HEX[level] : "#6B7280";
                const radius = 8 + 3 * Math.min(c.n_reports, 8);
                return (
                  <CircleMarker
                    key={`cluster-${i}`}
                    center={[c.centroid.lat, c.centroid.lon]}
                    radius={radius}
                    pathOptions={{ color: INK_NAVY, weight: 1.5, fillColor: color, fillOpacity: 0.75 }}
                  >
                    <Tooltip>{c.n_reports} pending report(s)</Tooltip>
                    <Popup maxWidth={280}>
                      <div className="cluster-popup">
                        <b>
                          {c.n_reports} report(s){c.any_synthetic ? " (synthetic)" : ""} — {c.district ?? "outside pilot district"}
                        </b>
                        <div>Hazards: {c.hazard_types.map(hazardLabel).join(", ")}</div>
                        {c.corroborating_news.length > 0 && <div>{c.corroborating_news.length} corroborating news hit(s)</div>}
                        <ul>
                          {c.reports.slice(0, 5).map((r) => (
                            <li key={r.id}>
                              {hazardLabel(r.hazard_type)}
                              {r.depth_hi_m != null ? ` (${r.depth_lo_m}-${r.depth_hi_m}m)` : ""} —{" "}
                              {r.submitted_at.slice(0, 16).replace("T", " ")}
                            </li>
                          ))}
                          {c.n_reports > 5 && <li>+{c.n_reports - 5} more</li>}
                        </ul>
                      </div>
                    </Popup>
                  </CircleMarker>
                );
              })}

              {filteredIncidents.map((inc) => {
                const responding = inc.response_status === "responding";
                return (
                  <Marker key={inc.id} position={[inc.lat, inc.lon]} icon={incidentIcon(responding)}>
                    <Tooltip>Active: {hazardLabel(inc.hazard_type)}</Tooltip>
                    <Popup maxWidth={280}>
                      <div className="cluster-popup">
                        <b>
                          {inc.id}
                          {inc.synthetic ? " (synthetic)" : ""} — {inc.hazard_type.replace("_", " ")}
                        </b>
                        <div>{inc.district ?? "outside pilot district"}</div>
                        <div>Status: {(inc.response_status ?? "reported").replace(/^./, (c) => c.toUpperCase())}</div>
                        {inc.assigned_responder && (
                          <div>
                            Responder: {inc.assigned_responder}
                            {inc.eta_minutes != null ? `, ETA ${inc.eta_minutes} min` : ""}
                          </div>
                        )}
                      </div>
                    </Popup>
                  </Marker>
                );
              })}
            </MapContainer>
          )}

          <FullscreenToggle targetRef={mapWrapRef} onToggle={() => setTimeout(() => leafletMapRef.current?.invalidateSize(), 50)} />

          <div className="live-map-legend">
            {SEVERITY_LEVELS.map((lv) => (
              <LegendDot key={lv} color={LEVEL_HEX[lv]} label={lv} />
            ))}
            <span className="live-map-legend-sep" />
            <LegendDot color="#D4820A" label="Awaiting responder" />
            <LegendDot color="#1E5FA8" label="Responder assigned" />
          </div>
        </div>
      </div>

      {clusters.length > 0 && (
        <Card>
          <h2 className="live-map-table-title">Pending clusters, worst first</h2>
          <table className="live-map-table">
            <thead>
              <tr>
                <th>Reports</th>
                <th>District</th>
                <th>Hazards</th>
                <th>Zone level</th>
                <th>News corroboration</th>
                <th>Synthetic</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((c, i) => (
                <tr key={i}>
                  <td>{c.n_reports}</td>
                  <td>{c.district ?? "outside pilot district"}</td>
                  <td>{c.hazard_types.map(hazardLabel).join(", ")}</td>
                  <td>{worstLevel(c.reports.map((r) => r.zone?.level)) ?? "Unknown"}</td>
                  <td>{c.corroborating_news.length}</td>
                  <td>{c.any_synthetic ? "Yes" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
