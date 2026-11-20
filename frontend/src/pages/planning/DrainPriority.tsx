import { useEffect, useMemo, useRef, useState } from "react";
import type { Feature } from "geojson";
import type L from "leaflet";
import { GeoJSON, MapContainer, Tooltip as LeafletTooltip } from "react-leaflet";
import { fetchDrainPriority } from "../../api/drainPriority";
import type { DrainPriorityGap, DrainPriorityZone } from "../../api/types";
import { INK_NAVY, LEVEL_HEX } from "../../colors";
import { FullscreenToggle } from "../../components/FullscreenToggle";
import { MapStylePicker, StyleTileLayer, type MapStyle } from "../../components/MapStyle";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile, LegendDot, LevelPill } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./DrainPriority.css";

// Mirrors streamlit_app/features/govt_drain_priority.py: ranks pilot-grid
// zones for drain/channel maintenance budget by combining the composite
// vulnerability score with OSM channel-encroachment proximity (closer
// building-to-waterway distance -> higher priority). Zones without usable
// OSM coverage are shown separately, never silently dropped or treated as
// low-priority.

const SEVERITY_LEVELS = ["Very High", "High", "Moderate", "Low"] as const;

function geometryPoints(geometry: DrainPriorityZone["geometry"]): [number, number][] {
  const rings = geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
  const points: [number, number][] = [];
  for (const ring of rings) for (const [lon, lat] of ring) points.push([lat, lon]);
  return points;
}

function centerOf(zones: DrainPriorityZone[]): [number, number] {
  const points = zones.flatMap((z) => geometryPoints(z.geometry));
  if (points.length === 0) return [5.6037, -0.187];
  const lat = points.reduce((s, p) => s + p[0], 0) / points.length;
  const lon = points.reduce((s, p) => s + p[1], 0) / points.length;
  return [lat, lon];
}

export function DrainPriority() {
  const [withData, setWithData] = useState<DrainPriorityZone[]>([]);
  const [withoutData, setWithoutData] = useState<DrainPriorityGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [topN, setTopN] = useState(15);
  const [showGapList, setShowGapList] = useState(false);
  const [mapStyle, setMapStyle] = useState<MapStyle>("Streets");
  const mapWrapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<L.Map>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDrainPriority()
      .then((res) => {
        if (cancelled) return;
        setWithData(res.with_data);
        setWithoutData(res.without_data);
        setError(null);
      })
      .catch((err) => !cancelled && setError(err?.response?.data?.detail ?? err?.message ?? "Could not reach the backend."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = withData.filter((z) => matchesQuery([z.zone_id, z.assembly], query));
  const filteredGaps = withoutData.filter((z) => matchesQuery([z.zone_id, z.assembly], query));
  const maxTopN = Math.max(5, Math.min(50, filtered.length));
  const top = filtered.slice(0, Math.min(topN, maxTopN || topN));

  const center = useMemo(() => centerOf(top), [top]);

  // MapContainer's center prop only applies at mount -- react-leaflet
  // doesn't move an already-live map when it changes later. Narrowing
  // via search or the top-N slider recomputes `top`/`center` above but,
  // without this, the map itself never follows (same root cause as the
  // Road Closures screen's "map doesn't adjust" bug).
  useEffect(() => {
    const map = leafletMapRef.current;
    if (!map) return;
    const points = top.flatMap((z) => geometryPoints(z.geometry));
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 15);
    } else {
      map.fitBounds(points, { padding: [50, 50], maxZoom: 16 });
    }
  }, [top]);

  return (
    <>
      <TopBar
        title="Drain Maintenance Prioritization"
        subtitle="Ranked drain/channel segments for maintenance budget allocation"
        actions={<MapStylePicker value={mapStyle} onChange={setMapStyle} />}
        search={{ value: query, onChange: setQuery, placeholder: "Search by zone or assembly…" }}
      />

      <div className="dp-warning-banner">
        <span>⚠️</span>
        <span>
          "Persistent hotspot" here means multi-year SAR water occurrence (2020-2024), not verified repeat-incident
          history — that needs live pilot data this project doesn't have yet.
        </span>
      </div>

      {error && (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      )}

      {loading && <p className="section-caption">Loading…</p>}

      <section className="section-kpis">
        <Card>
          <KpiTile label="Zones with encroachment data" value={withData.length} />
        </Card>
        <Card>
          <KpiTile label="Zones needing field survey" value={withoutData.length} />
        </Card>
        <Card>
          <KpiTile label="Top priority zone" value={filtered[0]?.zone_id ?? "n/a"} note={filtered[0]?.assembly} />
        </Card>
      </section>

      {filtered.length === 0 && !loading && (
        <Card>
          <p className="section-caption">No zones match "{query}".</p>
        </Card>
      )}

      {filtered.length > 0 && (
        <>
          <Card className="dp-top-n-card">
            <label className="dp-top-n-label">
              Show top {topN} priority zone{topN === 1 ? "" : "s"}
              <input
                type="range"
                min={5}
                max={maxTopN}
                value={Math.min(topN, maxTopN)}
                onChange={(e) => setTopN(Number(e.target.value))}
                disabled={maxTopN <= 5}
              />
            </label>
          </Card>

          <div className="dp-body">
            <div className="dp-map-wrap" ref={mapWrapRef}>
              <MapContainer ref={leafletMapRef} center={center} zoom={13} className="dp-map">
                <StyleTileLayer style={mapStyle} />
                {top.map((z) => (
                  <GeoJSON
                    key={z.zone_id}
                    data={{ type: "Feature", geometry: z.geometry, properties: {} } as Feature}
                    style={{ color: INK_NAVY, weight: 1, fillColor: LEVEL_HEX[z.level], fillOpacity: 0.65 }}
                  >
                    <LeafletTooltip>
                      <b>{z.zone_id}</b>
                      <br />
                      Priority: {z.priority.toFixed(0)}
                      <br />
                      {z.encroachment_text}
                      {z.obstruction_m != null && (
                        <>
                          <br />
                          Obstruction: {z.obstruction_m.toFixed(1)}m
                        </>
                      )}
                    </LeafletTooltip>
                  </GeoJSON>
                ))}
              </MapContainer>
              <FullscreenToggle targetRef={mapWrapRef} onToggle={() => setTimeout(() => leafletMapRef.current?.invalidateSize(), 50)} />
              <div className="dp-map-legend">
                {SEVERITY_LEVELS.map((lv) => (
                  <LegendDot key={lv} color={LEVEL_HEX[lv]} label={lv} />
                ))}
              </div>
            </div>

            <Card className="dp-list-card">
              <h2 className="dp-list-title">Priority list</h2>
              <div className="dp-table-scroll">
                <table className="dp-table">
                  <thead>
                    <tr>
                      <th>Zone</th>
                      <th>Assembly</th>
                      <th>Score</th>
                      <th>Nearest waterway (m)</th>
                      <th>Obstruction (m)</th>
                      <th>Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((z) => (
                      <tr key={z.zone_id}>
                        <td>{z.zone_id}</td>
                        <td>{z.assembly}</td>
                        <td>{z.score.toFixed(1)}</td>
                        <td>{z.min_dist_m.toFixed(1)}</td>
                        <td>{z.obstruction_m != null ? z.obstruction_m.toFixed(1) : "—"}</td>
                        <td>{z.priority.toFixed(0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="section-caption dp-obstruction-caption">
                Obstruction (m): Copernicus DEM minus FABDEM, a free per-cell height-above-ground proxy (r=0.83
                correlated with impervious land cover). ~30m-class, not a building-level layer, and not part of the
                Priority score above — shown for context, same as everywhere else this project discloses without
                blending. FABDEM: CC BY-NC-SA 4.0, Hawker et al. 2022, Univ. of Bristol / Fathom.
              </p>
            </Card>
          </div>
        </>
      )}

      {withoutData.length > 0 && (
        <Card>
          <button type="button" className="dp-gap-toggle" onClick={() => setShowGapList((v) => !v)}>
            {showGapList ? "▾" : "▸"} {filteredGaps.length} zone{filteredGaps.length === 1 ? "" : "s"} need
            {filteredGaps.length === 1 ? "s" : ""} a field survey (no usable OSM waterway/building data)
          </button>
          {showGapList && (
            <>
              <p className="section-caption">
                These zones might genuinely need drain maintenance too — there just isn't enough free vector data to
                compute an encroachment estimate. Don't read absence from this list as "no risk."
              </p>
              <div className="dp-table-scroll dp-gap-scroll">
                <table className="dp-table">
                  <thead>
                    <tr>
                      <th>Zone</th>
                      <th>Assembly</th>
                      <th>Score</th>
                      <th>Level</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredGaps.map((z) => (
                      <tr key={z.zone_id}>
                        <td>{z.zone_id}</td>
                        <td>{z.assembly}</td>
                        <td>{z.score.toFixed(1)}</td>
                        <td>
                          <LevelPill level={z.level} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      )}
    </>
  );
}
