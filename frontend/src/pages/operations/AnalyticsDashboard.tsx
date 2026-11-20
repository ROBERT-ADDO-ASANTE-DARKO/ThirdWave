import { useEffect, useMemo, useRef, useState } from "react";
import type L from "leaflet";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CircleMarker, MapContainer, Tooltip as LeafletTooltip } from "react-leaflet";
import { fetchByDistrict, fetchHotspots, fetchResponseTimes } from "../../api/analytics";
import type { DistrictCount, Hotspot, LatencyStats, ResponseTimeStats } from "../../api/types";
import { INK_NAVY, LEVEL_HEX } from "../../colors";
import { FullscreenToggle } from "../../components/FullscreenToggle";
import { MapStylePicker, StyleTileLayer, type MapStyle } from "../../components/MapStyle";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile, ScoreBadge } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./AnalyticsDashboard.css";

// Mirrors streamlit_app/features/govt_analytics.py exactly -- three real,
// honest-about-thin-data views over the live Report table
// (backend/analytics.py): response-time latency (n always shown next to
// the number), a plain count by district x status, and recurring
// hotspots (clustered verified/resolved reports only, paired with the
// location's existing static vulnerability score for context).

const STATUS_COLOR = {
  pending: "#B8860B",
  verified: "#1B7A9E",
  rejected: "#8B98A5",
  resolved: "#1E8A4C",
} as const;

function kpiLatency(stat: LatencyStats): { value: string; unit?: string; note?: string } {
  if (stat.n === 0 || stat.median_min == null) return { value: "No data yet" };
  const hours = stat.median_min / 60;
  const note = `median, n=${stat.n}`;
  return hours >= 1 ? { value: hours.toFixed(1), unit: "h", note } : { value: stat.median_min.toFixed(0), unit: "min", note };
}

function HotspotRow({ h }: { h: Hotspot }) {
  return (
    <div className="an-hotspot-row">
      <div className="an-hotspot-head">
        <span className="an-hotspot-location">{h.district ?? "outside pilot district"}</span>
        <span className="an-hotspot-n">n = {h.n_reports}</span>
      </div>
      <p className="an-hotspot-caption">{h.hazard_types.map((t) => t.replace("_", " ")).join(", ")}</p>
      {h.static_zone ? (
        <ScoreBadge level={h.static_zone.level}>
          Static score here: {h.static_zone.score.toFixed(1)} ({h.static_zone.level})
        </ScoreBadge>
      ) : (
        <p className="an-hotspot-caption">Outside all scored coverage — no static score to compare against.</p>
      )}
    </div>
  );
}

export function AnalyticsDashboard() {
  const [responseTimes, setResponseTimes] = useState<ResponseTimeStats | null>(null);
  const [byDistrict, setByDistrict] = useState<DistrictCount[]>([]);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [hotspotsNote, setHotspotsNote] = useState("");
  const [nConsidered, setNConsidered] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mapStyle, setMapStyle] = useState<MapStyle>("Streets");
  const [query, setQuery] = useState("");
  const mapWrapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<L.Map>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchResponseTimes(), fetchByDistrict(), fetchHotspots()])
      .then(([rt, bd, hs]) => {
        if (cancelled) return;
        setResponseTimes(rt);
        setByDistrict(bd);
        setHotspots(hs.hotspots);
        setHotspotsNote(hs.note);
        setNConsidered(hs.n_verified_or_resolved_reports_considered);
        setError(null);
      })
      .catch((err) => !cancelled && setError(err?.response?.data?.detail ?? err?.message ?? "Could not load analytics."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredByDistrict = byDistrict.filter((d) => matchesQuery([d.district], query));
  const filteredHotspots = hotspots.filter((h) => matchesQuery([h.district, ...h.hazard_types], query));

  const chartData = useMemo(() => [...filteredByDistrict].reverse(), [filteredByDistrict]);

  const hotspotCenter = useMemo((): [number, number] => {
    if (filteredHotspots.length === 0) return [5.6037, -0.187];
    return [filteredHotspots[0].centroid.lat, filteredHotspots[0].centroid.lon];
  }, [filteredHotspots]);

  // MapContainer's center prop only applies at mount -- react-leaflet
  // doesn't move an already-live map when it changes later. Searching
  // recomputes `hotspotCenter` above but, without this, the map never
  // follows (same root cause as the Road Closures screen's "map doesn't
  // adjust" bug).
  useEffect(() => {
    const map = leafletMapRef.current;
    if (!map) return;
    const points = filteredHotspots.map((h): [number, number] => [h.centroid.lat, h.centroid.lon]);
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 15);
    } else {
      map.fitBounds(points, { padding: [50, 50], maxZoom: 15 });
    }
  }, [filteredHotspots]);

  const verification = responseTimes ? kpiLatency(responseTimes.verification_latency) : null;
  const resolution = responseTimes ? kpiLatency(responseTimes.resolution_latency) : null;

  return (
    <>
      <TopBar
        title="Analytics Dashboard"
        subtitle="Response-time performance and recurring hotspots — real counts, caveated where thin"
        search={{ value: query, onChange: setQuery, placeholder: "Search by district or hazard type…" }}
      />

      {error && (
        <Card>
          <p className="error-text">Could not load analytics: {error}</p>
        </Card>
      )}

      {!loading && responseTimes && (
        <>
          <h2 className="section-title">Response times</h2>
          <section className="section-kpis">
            <Card>
              <KpiTile label="Total reports (all time)" value={responseTimes.total_reports} />
            </Card>
            <Card>
              <KpiTile label="Verification time" value={verification!.value} unit={verification!.unit} note={verification!.note} />
            </Card>
            <Card>
              <KpiTile label="Resolution time" value={resolution!.value} unit={resolution!.unit} note={resolution!.note} />
            </Card>
          </section>
          <p className="section-caption">
            Verification: submitted → verified. Resolution: verified → resolved. Medians shown, not means, so one
            slow outlier doesn't dominate — n is the actual sample size behind each number.
          </p>
        </>
      )}

      <h2 className="section-title section-title-spaced">Reports by district</h2>
      {!loading && byDistrict.length === 0 && <p className="section-caption">No reports yet.</p>}
      {byDistrict.length > 0 && filteredByDistrict.length === 0 && (
        <p className="section-caption">No districts match "{query}".</p>
      )}
      {filteredByDistrict.length > 0 && (
        <Card>
          <ResponsiveContainer width="100%" height={Math.max(220, 60 * chartData.length)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
              <CartesianGrid horizontal={false} stroke="var(--surface-border-soft)" />
              <XAxis type="number" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} allowDecimals={false} />
              <YAxis type="category" dataKey="district" width={170} tick={{ fontSize: 11.5, fill: "var(--text-primary)" }} />
              <Tooltip contentStyle={{ fontFamily: "inherit", fontSize: 12, borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontFamily: "inherit", fontSize: 12 }} />
              <Bar dataKey="pending" stackId="a" fill={STATUS_COLOR.pending} name="Pending" stroke="var(--surface-page)" strokeWidth={2} />
              <Bar dataKey="verified" stackId="a" fill={STATUS_COLOR.verified} name="Verified" stroke="var(--surface-page)" strokeWidth={2} />
              <Bar dataKey="rejected" stackId="a" fill={STATUS_COLOR.rejected} name="Rejected" stroke="var(--surface-page)" strokeWidth={2} />
              <Bar dataKey="resolved" stackId="a" fill={STATUS_COLOR.resolved} name="Resolved" stroke="var(--surface-page)" strokeWidth={2} />
            </BarChart>
          </ResponsiveContainer>

          <table className="an-table">
            <thead>
              <tr>
                <th>District</th>
                <th>Total</th>
                <th>Pending</th>
                <th>Verified</th>
                <th>Rejected</th>
                <th>Resolved</th>
              </tr>
            </thead>
            <tbody>
              {filteredByDistrict.map((d) => (
                <tr key={d.district}>
                  <td>{d.district}</td>
                  <td>{d.total}</td>
                  <td>{d.pending}</td>
                  <td>{d.verified}</td>
                  <td>{d.rejected}</td>
                  <td>{d.resolved}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <h2 className="section-title section-title-spaced">Recurring hotspots</h2>
      <p className="section-caption">{hotspotsNote}</p>
      {!loading && hotspots.length === 0 && (
        <Card>
          <p className="section-caption">
            No location has 2+ verified/resolved reports yet (out of {nConsidered} total) — nothing to flag as a
            repeat-incident candidate.
          </p>
        </Card>
      )}
      {hotspots.length > 0 && filteredHotspots.length === 0 && (
        <Card>
          <p className="section-caption">No hotspots match "{query}".</p>
        </Card>
      )}

      {filteredHotspots.length > 0 && (
        <div className="an-hotspot-body">
          <div className="an-map-wrap" ref={mapWrapRef}>
            <MapContainer ref={leafletMapRef} center={hotspotCenter} zoom={13} className="an-map">
              <StyleTileLayer style={mapStyle} />
              {filteredHotspots.map((h, i) => {
                const color = h.static_zone ? LEVEL_HEX[h.static_zone.level] : "#6B7280";
                return (
                  <CircleMarker
                    key={i}
                    center={[h.centroid.lat, h.centroid.lon]}
                    radius={10 + 2 * h.n_reports}
                    pathOptions={{ color: INK_NAVY, weight: 1.5, fillColor: color, fillOpacity: 0.75 }}
                  >
                    <LeafletTooltip>
                      {h.n_reports} report(s){h.any_synthetic ? " (synthetic)" : ""} — {h.district ?? "outside pilot district"}
                    </LeafletTooltip>
                  </CircleMarker>
                );
              })}
            </MapContainer>
            <FullscreenToggle targetRef={mapWrapRef} onToggle={() => setTimeout(() => leafletMapRef.current?.invalidateSize(), 50)} />
            <div className="an-map-actions">
              <MapStylePicker value={mapStyle} onChange={setMapStyle} />
            </div>
          </div>

          <Card className="an-hotspot-list">
            {filteredHotspots.map((h, i) => (
              <HotspotRow key={i} h={h} />
            ))}
          </Card>
        </div>
      )}
    </>
  );
}
