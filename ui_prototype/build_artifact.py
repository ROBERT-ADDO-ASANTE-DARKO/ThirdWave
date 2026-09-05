"""Build the Risk Map + Risk Detail Drawer artifact HTML, embedding real
computed data (risk_zones.json, district boundary/assemblies) rather than
placeholder content. Run this, then the Artifact tool publishes the output.
"""
import json
from pathlib import Path

DATA_DIR = Path("/teamspace/studios/this_studio/ThirdWave/risk_engine/data")
OUT = Path("/teamspace/studios/this_studio/ThirdWave/ui_prototype/risk_map.html")

zones_raw = json.loads((DATA_DIR / "risk_zones.json").read_text())["zones"]
boundary = json.loads((DATA_DIR / "pilot_district_boundary.geojson").read_text())
assemblies = json.loads((DATA_DIR / "pilot_district_assemblies.geojson").read_text())

# Trim to exactly what the UI renders -- smaller payload, no unused precision.
zones_out = []
for z in zones_raw:
    coords = z["geometry"]["coordinates"][0]
    coords_r = [[round(x, 6), round(y, 6)] for x, y in coords]
    zones_out.append({
        "id": z["id"].replace("RZ-", ""),
        "poly": coords_r,
        "level": z["level"],
        "score": z["score"],
        "confidence": z["confidence"],
        "assembly": z["assembly"],
        "factors": [
            {"type": f["type"], "source": f["source"], "text": f["text"],
             "insufficient": f.get("data_insufficient", False)}
            for f in z["contributing_factors"]
        ],
        "valid_from": z["valid_from"][:10],
        "valid_to": z["valid_to"][:10],
        "model_version": z["model_version"],
    })

boundary_coords = [[round(x, 6), round(y, 6)] for x, y in boundary["features"][0]["geometry"]["coordinates"][0]]
assembly_out = []
for f in assemblies["features"]:
    geom = f["geometry"]
    rings = geom["coordinates"] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
    assembly_out.append({
        "name": f["properties"]["name"],
        "rings": [[[round(x, 6), round(y, 6)] for x, y in ring] for ring in (rings if geom["type"] == "Polygon" else geom["coordinates"])],
    })

# Circle reference point (validated throughout this project's chat history)
CIRCLE = {"lon": -0.215275, "lat": 5.569222, "label": "Kwame Nkrumah Circle"}

# Aerial imagery: only two zones in the whole 319-cell grid have real,
# validated aerial imagery attached (fetched and visually confirmed earlier
# in this project). This is NOT a stand-in for full coverage -- embedding
# imagery for all 319 zones is infeasible client-side (roughly 500KB-1MB
# each, well over the artifact's payload budget) and the artifact CSP
# blocks live tile fetches from Esri/Google/Bing at runtime regardless. In
# the real MVP, this is the Backend Engineer's job -- the Django API proxies
# and caches imagery server-side per spec's architecture, which sidesteps
# both constraints. This demonstrates the intended UX honestly for the two
# zones it actually covers, and discloses absence everywhere else.
import base64
AERIAL_IMAGES = {}
for zone_id, tmp_name in [("grid_r11_c14", "/tmp/circle_z18_stitched_web.jpg"),
                          ("grid_r8_c1", "/tmp/ablekuma_z18_stitched_web.jpg")]:
    b64 = base64.b64encode(Path(tmp_name).read_bytes()).decode("ascii")
    AERIAL_IMAGES[zone_id] = f"data:image/jpeg;base64,{b64}"

AERIAL_META = {
    "grid_r11_c14": {"caption": "Kwame Nkrumah Circle interchange -- Odaw River channel visible bottom-left, "
                                 "dense informal settlement built to its banks.",
                      "source": "Esri World Imagery, z18"},
    "grid_r8_c1": {"caption": "Ablekuma West hotspot -- rectangular basins are water treatment/settling "
                               "infrastructure, not natural wetland (corrects an earlier hypothesis in this project).",
                    "source": "Esri World Imagery, z18"},
}

DATA_JSON = json.dumps({
    "zones": zones_out,
    "boundary": boundary_coords,
    "assemblies": assembly_out,
    "circle": CIRCLE,
    "aerial": AERIAL_IMAGES,
    "aerialMeta": AERIAL_META,
}, separators=(",", ":"))

print(f"Embedded data size: {len(DATA_JSON) / 1024:.0f} KB, {len(zones_out)} zones")

TEMPLATE = r"""<!doctype html>
<title>ThirdWave Risk Map</title>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --ink-navy: #0B2545;
  --steel-blue: #1E4E6B;
  --signal-teal: #1B7A9E;
  --paper: #F7F9FA;
  --surface: #FFFFFF;
  --border: #DCE3E8;
  --text: #16232E;
  --text-muted: #5B6B76;
  --risk-low: #1E8A4C;
  --risk-watch: #B8860B;
  --risk-warning: #C1621B;
  --risk-critical: #B0241D;
  --shadow: 0 8px 28px rgba(11,37,69,0.14);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ink-navy: #0E3A6E;
    --steel-blue: #2C6C93;
    --signal-teal: #3FB3DE;
    --paper: #0A121C;
    --surface: #101B29;
    --border: #223244;
    --text: #E7EEF3;
    --text-muted: #8CA0AF;
    --risk-low: #35B871;
    --risk-watch: #E0AC2E;
    --risk-warning: #E8813C;
    --risk-critical: #F0473C;
    --shadow: 0 8px 28px rgba(0,0,0,0.5);
  }
}
:root[data-theme="dark"] {
  --ink-navy: #0E3A6E;
  --steel-blue: #2C6C93;
  --signal-teal: #3FB3DE;
  --paper: #0A121C;
  --surface: #101B29;
  --border: #223244;
  --text: #E7EEF3;
  --text-muted: #8CA0AF;
  --risk-low: #35B871;
  --risk-watch: #E0AC2E;
  --risk-warning: #E8813C;
  --risk-critical: #F0473C;
  --shadow: 0 8px 28px rgba(0,0,0,0.5);
}

* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--text);
  font-family: "IBM Plex Sans", -apple-system, "Segoe UI", sans-serif;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.mono { font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace; font-feature-settings: "tnum"; }

/* ---------- Header ---------- */
header {
  background: var(--ink-navy);
  color: #fff;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
  z-index: 20;
  box-shadow: var(--shadow);
}
.ring {
  width: 26px; height: 26px; flex-shrink: 0;
}
.ring circle { fill: none; stroke: var(--signal-teal); }
.wordmark { font-weight: 700; font-size: 16px; letter-spacing: 0.02em; }
.wordmark span { color: var(--signal-teal); }
.crumb { font-size: 12.5px; color: #B9CBDA; padding-left: 12px; border-left: 1px solid rgba(255,255,255,0.25); }

.kpis {
  display: flex;
  gap: 22px;
  margin-left: auto;
  align-items: center;
}
.kpi { text-align: right; }
.kpi .n { font-family: "IBM Plex Mono", monospace; font-weight: 600; font-size: 15px; line-height: 1; }
.kpi .l { font-size: 10.5px; color: #9FB4C4; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 3px; }

/* ---------- Layout ---------- */
main {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}
.map-pane {
  flex: 1;
  position: relative;
  background:
    linear-gradient(var(--border) 1px, transparent 1px) 0 0/32px 32px,
    linear-gradient(90deg, var(--border) 1px, transparent 1px) 0 0/32px 32px,
    var(--paper);
  background-blend-mode: normal;
  opacity: 1;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .map-pane { background-color: var(--paper); } }
.map-pane svg { width: 100%; height: 100%; display: block; }

.zone-cell {
  stroke: rgba(255,255,255,0.55);
  stroke-width: 0.4;
  cursor: pointer;
  transition: filter 120ms ease, stroke-width 120ms ease;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .zone-cell { stroke: rgba(10,18,28,0.55); } }
:root[data-theme="dark"] .zone-cell { stroke: rgba(10,18,28,0.55); }
.zone-cell:hover { filter: brightness(1.18); stroke-width: 1.4; stroke: var(--signal-teal); }
.zone-cell.selected { stroke: var(--signal-teal); stroke-width: 2.2; }
.zone-cell.insufficient { opacity: 0.55; }

.assembly-outline { fill: none; stroke: var(--ink-navy); stroke-width: 1.1; stroke-dasharray: 3 3; opacity: 0.55; pointer-events: none; }
.boundary-outline { fill: none; stroke: var(--ink-navy); stroke-width: 1.8; opacity: 0.85; pointer-events: none; }

.circle-marker circle { fill: var(--surface); stroke: var(--signal-teal); stroke-width: 2; }
.circle-marker circle.dot { fill: var(--signal-teal); stroke: none; }
.circle-marker text {
  font-family: "IBM Plex Sans", sans-serif;
  font-weight: 600;
  font-size: 3.4px;
  fill: var(--text);
  paint-order: stroke;
  stroke: var(--paper);
  stroke-width: 0.6px;
}

/* ---------- Legend ---------- */
.legend {
  position: absolute;
  left: 16px;
  bottom: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: var(--shadow);
  font-size: 12px;
  min-width: 168px;
}
.legend h4 { margin: 0 0 8px; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 600; }
.legend-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.legend-swatch { width: 11px; height: 11px; border-radius: 3px; flex-shrink: 0; }
.legend-row .n { margin-left: auto; color: var(--text-muted); font-family: "IBM Plex Mono", monospace; font-size: 11px; }

.data-note {
  position: absolute;
  right: 16px;
  bottom: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 13px;
  font-size: 11px;
  color: var(--text-muted);
  box-shadow: var(--shadow);
  max-width: 320px;
  line-height: 1.5;
}
.data-note b { color: var(--text); }

/* ---------- Filter bar ---------- */
.filter-bar {
  position: absolute;
  top: 16px;
  left: 16px;
  display: flex;
  gap: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 5px;
  box-shadow: var(--shadow);
}
.filter-btn {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  padding: 7px 12px;
  border-radius: 7px;
  cursor: pointer;
}
.filter-btn:hover { background: var(--paper); }
.filter-btn.active { background: var(--ink-navy); color: #fff; }
.filter-btn:focus-visible, .zone-cell:focus-visible, .drawer-close:focus-visible { outline: 2px solid var(--signal-teal); outline-offset: 2px; }

/* ---------- Drawer ---------- */
.drawer {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 380px;
  max-width: 92vw;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 24px rgba(11,37,69,0.10);
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 220ms ease;
  z-index: 15;
}
.drawer.open { transform: translateX(0); }
@media (prefers-reduced-motion: reduce) { .drawer { transition: none; } }

.drawer-head {
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.drawer-head-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.drawer-title { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.drawer-id { font-family: "IBM Plex Mono", monospace; font-size: 15px; font-weight: 600; margin-top: 2px; }
.drawer-close {
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 7px;
  width: 28px; height: 28px;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 15px;
  line-height: 1;
  flex-shrink: 0;
}
.drawer-close:hover { color: var(--text); }

.score-row { display: flex; align-items: center; gap: 12px; }
.score-big { font-family: "IBM Plex Mono", monospace; font-size: 34px; font-weight: 600; line-height: 1; }
.pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 11px; border-radius: 999px;
  font-size: 12px; font-weight: 600; color: #fff;
}
.pill .dot { width: 7px; height: 7px; border-radius: 50%; background: rgba(255,255,255,0.85); }
.confidence-note { font-size: 11.5px; color: var(--text-muted); }

.drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px 20px; }

.aerial-block { margin-bottom: 20px; }
.aerial-img-wrap {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border);
  aspect-ratio: 1 / 1;
  background: var(--paper);
}
.aerial-img-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }
.aerial-source-tag {
  position: absolute; left: 8px; bottom: 8px;
  background: rgba(11,37,69,0.78);
  color: #fff;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 999px;
  font-family: "IBM Plex Mono", monospace;
}
.aerial-caption { font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-top: 8px; }
.aerial-empty {
  aspect-ratio: 16 / 9;
  border: 1px dashed var(--border);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 6px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
  padding: 16px;
  background: var(--paper);
}
.aerial-empty svg { opacity: 0.4; }
.section-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); font-weight: 600; margin: 0 0 10px; }
.factor {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 11px 13px;
  margin-bottom: 9px;
}
.factor.insufficient { border-style: dashed; opacity: 0.85; }
.factor-type { font-size: 11px; font-weight: 600; color: var(--steel-blue); margin-bottom: 4px; }
.factor-text { font-size: 13px; line-height: 1.48; }
.factor-source { font-size: 10.5px; color: var(--text-muted); margin-top: 6px; font-family: "IBM Plex Mono", monospace; }
.gap-flag { display: inline-block; margin-top: 6px; font-size: 10.5px; font-weight: 600; color: var(--risk-warning); }

.meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 18px; font-size: 12px; }
.meta-grid div { color: var(--text-muted); }
.meta-grid b { display: block; color: var(--text); font-family: "IBM Plex Mono", monospace; font-weight: 500; margin-top: 2px; font-size: 12.5px; }

.drawer-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  padding: 30px; text-align: center; color: var(--text-muted); font-size: 13px;
}

.hint {
  padding: 8px 20px;
  background: var(--paper);
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
}
</style>

<header>
  <svg class="ring" viewBox="0 0 26 26" aria-hidden="true">
    <circle cx="13" cy="13" r="4" stroke-width="1.6" opacity="0.95"/>
    <circle cx="13" cy="13" r="8" stroke-width="1.3" opacity="0.6"/>
    <circle cx="13" cy="13" r="11.5" stroke-width="1" opacity="0.3"/>
  </svg>
  <div>
    <div class="wordmark">Third<span>Wave</span></div>
  </div>
  <div class="crumb">Government &middot; Risk Map &middot; Pilot District</div>
  <div class="kpis" id="kpis"></div>
</header>

<main>
  <div class="map-pane">
    <div class="filter-bar" id="filterBar"></div>
    <svg id="mapSvg" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid meet"></svg>
    <div class="legend">
      <h4>District Risk Level</h4>
      <div id="legendRows"></div>
    </div>
    <div class="data-note">
      <b>Source:</b> Sentinel-1 SAR &middot; Copernicus DEM &middot; ESA WorldCover &middot; OpenStreetMap encroachment index.
      <div style="margin-top:4px">500m grid &middot; last computed 2026-09-01 &middot; not live pilot data</div>
    </div>
  </div>

  <div class="drawer" id="drawer">
    <div id="drawerContent"></div>
  </div>
</main>

<div class="hint">Click a zone to open its Risk Detail &middot; prototype built from this project's own computed risk_zones.json &mdash; not synthetic placeholder data</div>

<script>
const DATA = __DATA_JSON__;

const LEVEL_COLOR = {
  "Low": "var(--risk-low)",
  "Moderate": "var(--risk-watch)",
  "High": "var(--risk-warning)",
  "Very High": "var(--risk-critical)",
};
const LEVEL_ORDER = ["Low", "Moderate", "High", "Very High"];

// ---- Simple equirectangular projection into a 1000x1000 viewBox ----
let bounds = null;
function computeBounds() {
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const pt of DATA.boundary) {
    minLon = Math.min(minLon, pt[0]); maxLon = Math.max(maxLon, pt[0]);
    minLat = Math.min(minLat, pt[1]); maxLat = Math.max(maxLat, pt[1]);
  }
  const padLon = (maxLon - minLon) * 0.04, padLat = (maxLat - minLat) * 0.04;
  bounds = { minLon: minLon - padLon, maxLon: maxLon + padLon, minLat: minLat - padLat, maxLat: maxLat + padLat };
}
function project([lon, lat]) {
  const x = (lon - bounds.minLon) / (bounds.maxLon - bounds.minLon) * 1000;
  const y = 1000 - (lat - bounds.minLat) / (bounds.maxLat - bounds.minLat) * 1000;
  return [x.toFixed(2), y.toFixed(2)];
}
function polyPath(coords) {
  return coords.map((c, i) => (i === 0 ? "M" : "L") + project(c).join(",")).join(" ") + " Z";
}

const svgNS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {
  const e = document.createElementNS(svgNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

let selectedId = null;
let activeFilter = "all";

function render() {
  computeBounds();
  const svg = document.getElementById("mapSvg");
  svg.innerHTML = "";

  // District boundary
  svg.appendChild(el("path", { d: polyPath(DATA.boundary), class: "boundary-outline" }));

  // Assembly outlines
  for (const a of DATA.assemblies) {
    for (const ring of a.rings) {
      svg.appendChild(el("path", { d: polyPath(ring), class: "assembly-outline" }));
    }
  }

  // Zone cells
  for (const z of DATA.zones) {
    const passesFilter = activeFilter === "all" ||
      (activeFilter === "moderate" && LEVEL_ORDER.indexOf(z.level) >= 1) ||
      (activeFilter === "high" && LEVEL_ORDER.indexOf(z.level) >= 2);
    const insufficient = z.factors.some(f => f.insufficient);
    const path = el("path", {
      d: polyPath(z.poly),
      fill: LEVEL_COLOR[z.level],
      class: "zone-cell" + (insufficient ? " insufficient" : "") + (z.id === selectedId ? " selected" : ""),
      tabindex: "0",
      role: "button",
      "aria-label": `Zone ${z.id}, ${z.level}, score ${z.score}`,
      opacity: passesFilter ? "1" : "0.12",
    });
    path.style.pointerEvents = passesFilter ? "auto" : "none";
    path.addEventListener("click", () => selectZone(z.id));
    path.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectZone(z.id); } });
    svg.appendChild(path);
  }

  // Circle reference marker
  const [cx, cy] = project([DATA.circle.lon, DATA.circle.lat]);
  const marker = el("g", { class: "circle-marker" });
  marker.appendChild(el("circle", { cx, cy, r: 7, class: "" }));
  marker.appendChild(el("circle", { cx, cy, r: 2, class: "dot" }));
  const label = el("text", { x: parseFloat(cx) + 10, y: parseFloat(cy) + 3 });
  label.textContent = DATA.circle.label;
  marker.appendChild(label);
  svg.appendChild(marker);
}

function selectZone(id) {
  selectedId = id;
  render();
  const z = DATA.zones.find(z => z.id === id);
  renderDrawer(z);
  document.getElementById("drawer").classList.add("open");
}

function renderDrawer(z) {
  const content = document.getElementById("drawerContent");
  if (!z) {
    content.innerHTML = '<div class="drawer-empty">Select a zone on the map to see its full risk detail and contributing factors.</div>';
    return;
  }
  const levelColor = LEVEL_COLOR[z.level];
  const factorsHtml = z.factors.map(f => `
    <div class="factor${f.insufficient ? " insufficient" : ""}">
      <div class="factor-type">${labelForType(f.type)}</div>
      <div class="factor-text">${f.text}</div>
      <div class="factor-source">${f.source}</div>
      ${f.insufficient ? '<div class="gap-flag">&#9888; Data gap disclosed, not defaulted to Low</div>' : ""}
    </div>`).join("");

  content.innerHTML = `
    <div class="drawer-head">
      <div class="drawer-head-top">
        <div>
          <div class="drawer-title">Risk Zone</div>
          <div class="drawer-id">${z.id}</div>
        </div>
        <button class="drawer-close" id="closeBtn" aria-label="Close">&times;</button>
      </div>
      <div class="score-row">
        <div class="score-big mono">${z.score.toFixed(1)}</div>
        <span class="pill" style="background:${levelColor}"><span class="dot"></span>${z.level}</span>
      </div>
      <div class="confidence-note">Confidence ${(z.confidence * 100).toFixed(0)}% &middot; ${z.assembly}</div>
    </div>
    <div class="drawer-body">
      ${aerialHtml(z.id)}
      <p class="section-label">Contributing Factors</p>
      ${factorsHtml}
      <div class="meta-grid">
        <div>Valid from<b class="mono">${z.valid_from}</b></div>
        <div>Valid to<b class="mono">${z.valid_to}</b></div>
        <div>Model version<b class="mono">${z.model_version}</b></div>
        <div>Hazard<b class="mono">flood</b></div>
      </div>
    </div>
  `;
  document.getElementById("closeBtn").addEventListener("click", closeDrawer);
}

function closeDrawer() {
  document.getElementById("drawer").classList.remove("open");
  selectedId = null;
  render();
}

function aerialHtml(zoneId) {
  const img = DATA.aerial[zoneId];
  if (img) {
    const meta = DATA.aerialMeta[zoneId] || {};
    return `
      <div class="aerial-block">
        <p class="section-label">Aerial View</p>
        <div class="aerial-img-wrap">
          <img src="${img}" alt="Aerial imagery of zone ${zoneId}" loading="lazy">
          <span class="aerial-source-tag">${meta.source || "Aerial imagery"}</span>
        </div>
        ${meta.caption ? `<div class="aerial-caption">${meta.caption}</div>` : ""}
      </div>`;
  }
  return `
    <div class="aerial-block">
      <p class="section-label">Aerial View</p>
      <div class="aerial-empty">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></svg>
        <span>No aerial imagery captured for this zone yet.<br>Only 2 of 319 zones have been visually surveyed so far &mdash; see project notes.</span>
      </div>
    </div>`;
}

function labelForType(t) {
  return {
    sar_water_occurrence: "SAR Water Occurrence",
    low_elevation: "Elevation",
    land_cover_context: "Land Cover",
    channel_encroachment: "Channel Encroachment",
  }[t] || t;
}

// ---- KPI strip ----
function renderKpis() {
  const counts = { "Low": 0, "Moderate": 0, "High": 0, "Very High": 0 };
  for (const z of DATA.zones) counts[z.level]++;
  const kpis = document.getElementById("kpis");
  const items = [
    { n: DATA.zones.length, l: "Zones" },
    { n: counts["High"] + counts["Very High"], l: "High + Very High" },
    { n: DATA.zones.filter(z => z.factors.some(f => f.insufficient)).length, l: "Data Gaps" },
  ];
  kpis.innerHTML = items.map(k => `<div class="kpi"><div class="n mono">${k.n}</div><div class="l">${k.l}</div></div>`).join("");
}

// ---- Legend ----
function renderLegend() {
  const counts = { "Low": 0, "Moderate": 0, "High": 0, "Very High": 0 };
  for (const z of DATA.zones) counts[z.level]++;
  document.getElementById("legendRows").innerHTML = LEVEL_ORDER.map(l => `
    <div class="legend-row">
      <span class="legend-swatch" style="background:${LEVEL_COLOR[l]}"></span>
      <span>${l}</span>
      <span class="n">${counts[l]}</span>
    </div>`).join("");
}

// ---- Filter bar ----
function renderFilterBar() {
  const bar = document.getElementById("filterBar");
  const opts = [["all", "All Zones"], ["moderate", "Moderate+"], ["high", "High+"]];
  bar.innerHTML = opts.map(([key, label]) =>
    `<button class="filter-btn${activeFilter === key ? " active" : ""}" data-key="${key}">${label}</button>`
  ).join("");
  bar.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => { activeFilter = btn.dataset.key; renderFilterBar(); render(); });
  });
}

renderKpis();
renderLegend();
renderFilterBar();
render();
renderDrawer(null);
</script>
"""

html = TEMPLATE.replace("__DATA_JSON__", DATA_JSON)
OUT.write_text(html)
print(f"Wrote {OUT} ({len(html)/1024:.0f} KB)")
