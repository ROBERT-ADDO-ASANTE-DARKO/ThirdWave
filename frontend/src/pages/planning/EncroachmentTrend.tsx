import { useEffect, useMemo, useRef, useState } from "react";
import type L from "leaflet";
import { CircleMarker, MapContainer, Tooltip as LeafletTooltip } from "react-leaflet";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchEncroachmentByAssembly, fetchEncroachmentCells } from "../../api/encroachmentTrend";
import type { EncroachmentAssemblyRow, EncroachmentCell, EncroachmentDirection } from "../../api/types";
import { INK_NAVY } from "../../colors";
import { FullscreenToggle } from "../../components/FullscreenToggle";
import { MapStylePicker, StyleTileLayer, type MapStyle } from "../../components/MapStyle";
import { TopBar } from "../../components/TopBar";
import { Card, KpiTile } from "../../components/ui";
import { matchesQuery } from "../../searchMatch";
import "./EncroachmentTrend.css";

// Mirrors streamlit_app/features/govt_encroachment_trend.py exactly --
// see risk_engine/channel_encroachment_timeseries.py's docstring (via
// geo_data.py's encroachment_trend_cells()) for the full honesty record
// this page surfaces: 2019 reads anomalously high dataset-wide (both
// slopes shown, 2019-inclusive and excl.), and "Improving" cells in a
// documented-flood-history assembly may just be recurring floodwater
// reading as non-built-up in NDBI, not reduced construction -- CONFIRMED
// (not just plausible) for Weija Gbawe's 5 steepest cells via a clean-
// day Sentinel-2 re-fetch.

// Same axis govt_encroachment_trend.py's own _DIRECTION_COLOR uses --
// coincidentally the same hex values as LEVEL_HEX's Very High/Moderate/
// Low, but this is "trend direction," a different axis from zone
// severity, so it gets its own named map rather than borrowing Level.
const DIRECTION_COLOR: Record<EncroachmentDirection, string> = {
  Worsening: "#B0241D",
  Stable: "#B8860B",
  Improving: "#1E8A4C",
};

function cellLabel(c: EncroachmentCell): string {
  let name = c.zone_id;
  if (c.possible_flood_contamination) name += " ⚠";
  if (c.sensitive_to_2019) name += " 🗓";
  return name;
}

function buildChartData(cells: EncroachmentCell[]) {
  const years = new Set<string>();
  cells.forEach((c) => Object.keys(c.years).forEach((y) => years.add(y)));
  const sortedYears = [...years].sort();
  return sortedYears.map((y) => {
    const row: Record<string, number | string | null> = { year: y };
    cells.forEach((c) => {
      row[c.zone_id] = c.years[y]?.mean_ndbi_near_channel ?? null;
    });
    return row;
  });
}

function TrendChart({ title, caption, cells }: { title: string; caption?: string; cells: EncroachmentCell[] }) {
  const data = buildChartData(cells);
  return (
    <div className="et-chart-block">
      <h3 className="et-chart-title">{title}</h3>
      {caption && <p className="et-chart-caption">{caption}</p>}
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ left: 0, right: 10, top: 10, bottom: 0 }}>
          <CartesianGrid stroke="var(--surface-border-soft)" />
          <XAxis dataKey="year" tick={{ fontSize: 11, fill: "var(--text-secondary)" }} />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-secondary)" }}
            label={{ value: "Mean NDBI near channel", angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--text-secondary)" }}
          />
          <Tooltip contentStyle={{ fontFamily: "inherit", fontSize: 12, borderRadius: 8 }} />
          <Legend wrapperStyle={{ fontFamily: "inherit", fontSize: 11 }} />
          {cells.map((c) => (
            <Line
              key={c.zone_id}
              dataKey={c.zone_id}
              name={cellLabel(c)}
              stroke={DIRECTION_COLOR[c.direction]}
              connectNulls
              dot={{ r: 3 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function EncroachmentTrend() {
  const [byAssembly, setByAssembly] = useState<EncroachmentAssemblyRow[]>([]);
  const [selectedAssembly, setSelectedAssembly] = useState<string | null>(null);
  const [cells, setCells] = useState<EncroachmentCell[]>([]);
  const [loading, setLoading] = useState(true);
  const [cellsLoading, setCellsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [mapStyle, setMapStyle] = useState<MapStyle>("Streets");
  const mapWrapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<L.Map>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchEncroachmentByAssembly()
      .then((rows) => {
        if (cancelled) return;
        setByAssembly(rows);
        setSelectedAssembly((prev) => prev ?? rows[0]?.assembly ?? null);
        setError(null);
      })
      .catch((err) => !cancelled && setError(err?.response?.data?.detail ?? err?.message ?? "Could not load encroachment trend data."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedAssembly) return;
    let cancelled = false;
    setCellsLoading(true);
    fetchEncroachmentCells(selectedAssembly)
      .then((rows) => !cancelled && setCells(rows))
      .catch((err) => !cancelled && setError(err?.response?.data?.detail ?? err?.message ?? "Could not load cells."))
      .finally(() => !cancelled && setCellsLoading(false));
    return () => {
      cancelled = true;
    };
  }, [selectedAssembly]);

  const filteredByAssembly = byAssembly.filter((a) => matchesQuery([a.assembly], query));

  const totals = byAssembly.reduce(
    (acc, a) => ({
      cells: acc.cells + a.n_cells_near_channel,
      worsening: acc.worsening + a.n_worsening,
      improving: acc.improving + a.n_improving,
      sensitive: acc.sensitive + a.n_sensitive_to_2019,
      contaminated: acc.contaminated + a.n_possibly_flood_contaminated,
    }),
    { cells: 0, worsening: 0, improving: 0, sensitive: 0, contaminated: 0 },
  );

  const contaminatedAssemblies = byAssembly
    .filter((a) => a.n_possibly_flood_contaminated > 0)
    .map((a) => `${a.assembly} (${a.n_possibly_flood_contaminated})`)
    .join(", ");

  const center = useMemo((): [number, number] => {
    if (cells.length === 0) return [5.6037, -0.187];
    const lat = cells.reduce((s, c) => s + c.lat, 0) / cells.length;
    const lon = cells.reduce((s, c) => s + c.lon, 0) / cells.length;
    return [lat, lon];
  }, [cells]);

  const worst = [...cells].sort((a, b) => b.slope_per_year - a.slope_per_year).slice(0, 5);
  const mostImproving = [...cells].sort((a, b) => a.slope_per_year - b.slope_per_year).slice(0, 5);
  const showImprovingChart = mostImproving.some((c) => c.possible_flood_contamination);

  return (
    <>
      <TopBar
        title="Multi-Year Encroachment Trend"
        subtitle="Mean NDBI within 100m of mapped waterways, 2019–2026 — a direction, not a forecast"
        search={{ value: query, onChange: setQuery, placeholder: "Search by assembly name…" }}
      />

      {error && (
        <Card>
          <p className="error-text">{error}</p>
        </Card>
      )}

      {!loading && byAssembly.length === 0 && !error && (
        <Card>
          <p className="section-caption">No channel-adjacent cells with a computable trend yet.</p>
        </Card>
      )}

      {byAssembly.length > 0 && (
        <>
          <section className="section-kpis">
            <Card>
              <KpiTile label="Channel-adjacent cells tracked" value={totals.cells} />
            </Card>
            <Card>
              <KpiTile label="Worsening" value={<span style={{ color: DIRECTION_COLOR.Worsening }}>{totals.worsening}</span>} />
            </Card>
            <Card>
              <KpiTile label="Improving" value={<span style={{ color: DIRECTION_COLOR.Improving }}>{totals.improving}</span>} />
            </Card>
            <Card>
              <KpiTile
                label="Sensitive to 2019"
                value={totals.sensitive}
                note="Label flips once the confirmed-anomalous 2019 year is dropped from the fit"
              />
            </Card>
          </section>

          {totals.sensitive > 0 && (
            <div className="et-warning-banner">
              <strong>{totals.sensitive} cell(s)</strong> only get their Worsening/Stable/Improving label from
              including 2019 — refit on 2020–2026 alone and the label changes. 2019 reads anomalously high
              basin-wide; treat these cells' direction as uncertain and check the excl.-2019 slope before acting
              on them.
            </div>
          )}

          {totals.contaminated > 0 && (
            <div className="et-warning-banner">
              <strong>{totals.contaminated} "Improving" cell(s)</strong> sit in an assembly with documented flood
              history during the tracked years: {contaminatedAssemblies}. Standing floodwater reads as non-built-up
              in NDBI too — CONFIRMED for Weija Gbawe's 5 steepest cells (a clean, non-flood-day scene shows the
              built-up signal unchanged, not reduced); treat the rest as a lead to check, not a verified match.
            </div>
          )}

          <Card>
            <h2 className="section-title">By assembly</h2>
            {filteredByAssembly.length === 0 && <p className="section-caption">No assemblies match "{query}".</p>}
            {filteredByAssembly.length > 0 && (
              <table className="et-table">
                <thead>
                  <tr>
                    <th>Assembly</th>
                    <th>Cells near a channel</th>
                    <th>Worsening</th>
                    <th>Stable</th>
                    <th>Improving</th>
                    <th>Possibly flood-contaminated</th>
                    <th>Sensitive to 2019</th>
                    <th>Mean slope/year</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredByAssembly.map((a) => (
                    <tr
                      key={a.assembly}
                      className={a.assembly === selectedAssembly ? "et-row-selected" : ""}
                      onClick={() => setSelectedAssembly(a.assembly)}
                    >
                      <td>{a.assembly}</td>
                      <td>{a.n_cells_near_channel}</td>
                      <td style={{ color: DIRECTION_COLOR.Worsening, fontWeight: 700 }}>{a.n_worsening}</td>
                      <td>{a.n_stable}</td>
                      <td style={{ color: DIRECTION_COLOR.Improving }}>{a.n_improving}</td>
                      <td>{a.n_possibly_flood_contaminated || ""}</td>
                      <td>{a.n_sensitive_to_2019 || ""}</td>
                      <td>{a.mean_slope_per_year.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <label className="et-assembly-picker">
            <span>Inspect one assembly</span>
            <select value={selectedAssembly ?? ""} onChange={(e) => setSelectedAssembly(e.target.value)}>
              {byAssembly.map((a) => (
                <option key={a.assembly} value={a.assembly}>
                  {a.assembly}
                </option>
              ))}
            </select>
          </label>

          {cellsLoading && <p className="section-caption">Loading cells…</p>}

          {!cellsLoading && cells.length > 0 && (
            <div className="et-body">
              <div className="et-map-wrap" ref={mapWrapRef}>
                <MapContainer ref={leafletMapRef} center={center} zoom={13} className="et-map">
                  <StyleTileLayer style={mapStyle} />
                  {cells.map((c) => (
                    <CircleMarker
                      key={c.zone_id}
                      center={[c.lat, c.lon]}
                      radius={6}
                      pathOptions={{ color: INK_NAVY, weight: 1, fillColor: DIRECTION_COLOR[c.direction], fillOpacity: 0.8 }}
                    >
                      <LeafletTooltip>
                        <b>{c.zone_id}</b> — {c.direction} ({c.slope_per_year >= 0 ? "+" : ""}
                        {c.slope_per_year.toFixed(4)}/yr)
                        {c.sensitive_to_2019 && c.slope_per_year_excl_2019 != null && (
                          <>
                            <br />
                            excl. 2019: {c.slope_per_year_excl_2019 >= 0 ? "+" : ""}
                            {c.slope_per_year_excl_2019.toFixed(4)}/yr ({c.direction_excl_2019})
                          </>
                        )}
                        {c.possible_flood_contamination && (
                          <>
                            <br />
                            possible flood contamination
                          </>
                        )}
                      </LeafletTooltip>
                    </CircleMarker>
                  ))}
                </MapContainer>
                <FullscreenToggle targetRef={mapWrapRef} onToggle={() => setTimeout(() => leafletMapRef.current?.invalidateSize(), 50)} />
                <div className="et-map-actions">
                  <MapStylePicker value={mapStyle} onChange={setMapStyle} />
                </div>
                <div className="et-map-legend">
                  {(Object.keys(DIRECTION_COLOR) as EncroachmentDirection[]).map((d) => (
                    <span key={d} className="et-legend-item">
                      <span className="et-legend-dot" style={{ background: DIRECTION_COLOR[d] }} />
                      {d}
                    </span>
                  ))}
                </div>
              </div>

              <div className="et-charts">
                <Card>
                  <TrendChart title="Worst-trending (Worsening) cells here" cells={worst} caption={worst[0]?.trend_note} />
                </Card>
                {showImprovingChart && (
                  <Card>
                    <TrendChart
                      title='Steepest "Improving" cells here'
                      caption="⚠ = possible flood-year overlap, read skeptically · 🗓 = label flips once 2019 is dropped from the fit"
                      cells={mostImproving}
                    />
                  </Card>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
