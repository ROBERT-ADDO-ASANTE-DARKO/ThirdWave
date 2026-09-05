"""
Government — 3D Flood View.

A local, close-up 3D mockup of simulated water against real buildings and
roads around a chosen point (e.g. Kwame Nkrumah Circle) -- built to make
the Pluvial Flood Simulator's numbers (govt_inundation_simulator.py /
inundation_model.py) legible at a glance, not as a new simulation.

Important honesty notes (also shown in-app):
  - Ground is rendered as a FLAT reference plane, not true 3D terrain --
    only building height and water depth are real relative extrusions.
    We have no terrain mesh/TerrainLayer source for this; showing a flat
    base avoids implying we do.
  - Building heights are NOT real data (OSM rarely tags building height in
    Accra) -- each is a rough estimate from footprint size, clearly an
    illustrative guess, not survey data.
  - Water depth uses TRUE scale (no vertical exaggeration) so the scene
    doesn't visually overstate how deep the simulated ponding is relative
    to a real building.
  - The water surface is the same simulate_ponding() output as the Pluvial
    Flood Simulator, just cropped to a small local window and upscaled
    (bilinear) for a smoother-looking polygon -- it is not a higher-
    resolution re-simulation.
"""

from __future__ import annotations

import pickle
import time
from pathlib import Path

import numpy as np
import pydeck as pdk
import requests
import streamlit as st
from PIL import Image
from rasterio.features import shapes as rio_shapes
from rasterio.transform import from_bounds as rio_from_bounds

from data_loader import DATA_DIR
from inundation_model import simulate_ponding, simulate_ponding_frames

INPUTS_PATH = DATA_DIR / "inundation_inputs.npz"
GRAPH_PATH = DATA_DIR / "pilot_road_network.gpickle"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
ITERATIONS = 250

DEPTH_BINS = [  # (lower_m, upper_m, representative_elevation_m, color_rgba, label)
    (0.02, 0.15, 0.10, [130, 190, 230, 160], "Shallow (2-15cm)"),
    (0.15, 0.40, 0.28, [50, 110, 200, 190], "Moderate (15-40cm)"),
    (0.40, 999.0, 0.55, [90, 30, 160, 220], "Severe (>40cm)"),
]
BUILDING_COLOR = [176, 164, 148, 235]
GROUND_COLOR = [223, 217, 200, 255]
ROAD_COLOR = [90, 90, 90, 200]


@st.cache_resource
def load_inundation_inputs():
    if not INPUTS_PATH.exists():
        return None
    d = np.load(INPUTS_PATH)
    return d["dem"], d["worldcover"], d["bbox"]


@st.cache_resource
def load_road_graph():
    if not GRAPH_PATH.exists():
        return None
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


@st.cache_data(ttl=3600)
def geocode(address: str):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{address}, Accra, Ghana", "format": "json", "limit": 1},
            headers={"User-Agent": "ThirdWave-streamlit-poc/1.0"},
            timeout=10,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", address)
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600)
def fetch_local_buildings(lat: float, lon: float, radius_m: int):
    query = f'[out:json][timeout:30];way["building"](around:{radius_m},{lat},{lon});out geom;'
    headers = {"User-Agent": "ThirdWave-streamlit-poc/1.0 (research prototype)"}
    try:
        resp = requests.post(OVERPASS_URL, data=query, headers=headers, timeout=45)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception:
        return []

    buildings = []
    for e in elements:
        geom = e.get("geometry")
        if not geom or len(geom) < 3:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom]
        buildings.append(coords)
    return buildings


def _footprint_area_m2(coords: list[tuple[float, float]], lat0: float) -> float:
    """Rough planar area in m^2 -- good enough for a height heuristic, not
    a survey-grade measurement."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat0))
    xs = [c[0] * m_per_deg_lon for c in coords]
    ys = [c[1] * m_per_deg_lat for c in coords]
    area = 0.0
    n = len(coords)
    for i in range(n):
        x1, y1 = xs[i], ys[i]
        x2, y2 = xs[(i + 1) % n], ys[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def build_building_layer(buildings: list, lat0: float):
    records = []
    for coords in buildings:
        area = _footprint_area_m2(coords, lat0)
        height = float(np.clip(np.sqrt(max(area, 1.0)) * 0.5, 4.0, 16.0))
        records.append({"polygon": coords, "elevation": height})
    return pdk.Layer(
        "PolygonLayer", records, get_polygon="polygon", get_elevation="elevation",
        extruded=True, elevation_scale=1, get_fill_color=BUILDING_COLOR,
        get_line_color=[120, 110, 95, 255], line_width_min_pixels=1, pickable=False,
    )


def build_ground_layer(minlon, minlat, maxlon, maxlat):
    rect = [[minlon, minlat], [maxlon, minlat], [maxlon, maxlat], [minlon, maxlat]]
    return pdk.Layer(
        "PolygonLayer", [{"polygon": rect}], get_polygon="polygon",
        extruded=False, get_fill_color=GROUND_COLOR, get_line_color=[0, 0, 0, 0],
    )


def build_road_layer(G, minlon, minlat, maxlon, maxlat):
    if G is None:
        return None
    paths = []
    for u, v, data in G.edges(data=True):
        x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
        x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
        if not (minlon <= (x1 + x2) / 2 <= maxlon and minlat <= (y1 + y2) / 2 <= maxlat):
            continue
        paths.append({"path": [[x1, y1], [x2, y2]]})
    if not paths:
        return None
    return pdk.Layer(
        "PathLayer", paths, get_path="path", get_width=4, get_color=ROAD_COLOR,
        width_min_pixels=2, pickable=False,
    )


def _local_window(dem_shape, bbox, lat0, lon0, radius_m):
    """Pixel + lon/lat bounds of the crop window around (lat0, lon0).
    Computed once and reused for every animation frame -- only the depth
    values inside this window change between frames, not its extent."""
    minlon, minlat, maxlon, maxlat = bbox
    rows, cols = dem_shape
    m_per_px_lat = (maxlat - minlat) / rows * 111_320.0
    m_per_px_lon = (maxlon - minlon) / cols * 111_320.0 * np.cos(np.radians(lat0))
    pad_px_r = int(np.ceil(radius_m / max(m_per_px_lat, 1))) + 2
    pad_px_c = int(np.ceil(radius_m / max(m_per_px_lon, 1))) + 2

    center_row = int((maxlat - lat0) / (maxlat - minlat) * rows)
    center_col = int((lon0 - minlon) / (maxlon - minlon) * cols)
    r0, r1 = max(center_row - pad_px_r, 0), min(center_row + pad_px_r + 1, rows)
    c0, c1 = max(center_col - pad_px_c, 0), min(center_col + pad_px_c + 1, cols)

    crop_minlon = minlon + c0 / cols * (maxlon - minlon)
    crop_maxlon = minlon + c1 / cols * (maxlon - minlon)
    crop_maxlat = maxlat - r0 / rows * (maxlat - minlat)
    crop_minlat = maxlat - r1 / rows * (maxlat - minlat)
    return (r0, r1, c0, c1), (crop_minlon, crop_minlat, crop_maxlon, crop_maxlat)


def _depth_crop_to_layer(local_depth: np.ndarray, crop_bounds) -> pdk.Layer | None:
    if local_depth.size == 0:
        return None
    crop_minlon, crop_minlat, crop_maxlon, crop_maxlat = crop_bounds
    upscale = 8
    up_img = Image.fromarray(local_depth.astype(np.float32)).resize(
        (local_depth.shape[1] * upscale, local_depth.shape[0] * upscale), Image.Resampling.BILINEAR
    )
    up_depth = np.array(up_img)
    transform = rio_from_bounds(crop_minlon, crop_minlat, crop_maxlon, crop_maxlat, up_depth.shape[1], up_depth.shape[0])

    cat = np.zeros(up_depth.shape, dtype=np.int32)
    for i, (lo, hi, _, _, _) in enumerate(DEPTH_BINS, start=1):
        cat[(up_depth >= lo) & (up_depth < hi)] = i

    records = []
    for geom, val in rio_shapes(cat, mask=cat > 0, transform=transform):
        val = int(val)
        if val < 1 or val > len(DEPTH_BINS):
            continue
        _, _, elev, color, _ = DEPTH_BINS[val - 1]
        coords = geom["coordinates"][0]
        records.append({"polygon": coords, "elevation": elev, "fill_color": color})

    if not records:
        return None
    return pdk.Layer(
        "PolygonLayer", records, get_polygon="polygon", get_elevation="elevation",
        extruded=True, elevation_scale=1, get_fill_color="fill_color",
        get_line_color=[0, 0, 0, 0], pickable=False,
    )


def build_water_layer(dem, wc_int, bbox, lat0, lon0, radius_m, rainfall_mm):
    (r0, r1, c0, c1), crop_bounds = _local_window(dem.shape, bbox, lat0, lon0, radius_m)
    depth_full = simulate_ponding(dem, wc_int, rainfall_mm=rainfall_mm, iterations=ITERATIONS)
    local_depth = depth_full[r0:r1, c0:c1]
    layer = _depth_crop_to_layer(local_depth, crop_bounds)
    return layer, crop_bounds


@st.cache_data(ttl=1800, show_spinner=False)
def build_water_layer_frames(_dem, _wc_int, bbox, lat0, lon0, radius_m, rainfall_mm, n_frames=18):
    """Precompute the animation: one water layer per CA snapshot. Cached on
    (bbox, lat0, lon0, radius_m, rainfall_mm) so replaying the same scenario
    (e.g. pressing Play again) doesn't re-simulate. dem/wc_int are prefixed
    with _ so Streamlit doesn't try to hash the full arrays."""
    (r0, r1, c0, c1), crop_bounds = _local_window(_dem.shape, bbox, lat0, lon0, radius_m)
    frames = simulate_ponding_frames(_dem, _wc_int, rainfall_mm=rainfall_mm, iterations=ITERATIONS, n_frames=n_frames)
    layers = [_depth_crop_to_layer(f[r0:r1, c0:c1], crop_bounds) for f in frames]
    return layers, crop_bounds


def render():
    st.subheader("3D Flood View")
    st.warning(
        "⚠️ **A visualization aid, not a new simulation.** Water depth here is the exact same "
        "simulate_ponding() output as the Pluvial Flood Simulator, just cropped to a small area and "
        "shown in 3D. Three things to know before reading it: (1) the ground is a **flat reference plane** "
        "-- real terrain relief isn't rendered in 3D here, only building height and water depth are true "
        "relative extrusions; (2) **building heights are estimated** from footprint size, not real survey "
        "data (OSM rarely has building height for Accra); (3) water depth uses **true scale, not "
        "exaggerated** -- so it will often look thin next to a building, which is the honest picture, not "
        "a rendering bug."
    )

    inputs = load_inundation_inputs()
    if inputs is None:
        st.error("Run risk_engine/precompute_inundation_inputs.py first.")
        return
    dem, wc_int, bbox = inputs

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        address = st.text_input("Location", value="Kwame Nkrumah Circle")
    with col2:
        radius_m = st.selectbox("View radius", [300, 500, 800], index=1)
    with col3:
        rainfall_mm = st.slider("Rainfall (mm)", 0, 180, 60, 5)

    if not address:
        st.info("Enter a location to build the 3D scene.")
        return
    geo = geocode(address)
    if not geo:
        st.error(f"Couldn't find '{address}'.")
        return
    lat, lon, label = geo

    with st.spinner("Fetching buildings and roads..."):
        buildings = fetch_local_buildings(lat, lon, radius_m)
        G = load_road_graph()

    if not buildings:
        st.warning("No OSM building footprints returned for this area/radius -- try a larger radius.")

    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat))
    dlat = radius_m / m_per_deg_lat
    dlon = radius_m / m_per_deg_lon
    minlon, minlat, maxlon, maxlat = lon - dlon, lat - dlat, lon + dlon, lat + dlat

    base_layers = [build_ground_layer(minlon, minlat, maxlon, maxlat)]
    road_layer = build_road_layer(G, minlon, minlat, maxlon, maxlat)
    if road_layer:
        base_layers.append(road_layer)
    building_layer = build_building_layer(buildings, lat) if buildings else None

    view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=16.2, pitch=55, bearing=15)

    def assemble(water_layer):
        layers = list(base_layers)
        if water_layer:
            layers.append(water_layer)
        if building_layer:
            layers.append(building_layer)
        return pdk.Deck(layers=layers, initial_view_state=view_state, map_provider=None, tooltip=False)

    play_col, caption_col = st.columns([1, 5])
    play = play_col.button("▶ Play rise")
    chart_slot = st.empty()

    if play:
        with st.spinner("Simulating rise..."):
            frames, _ = build_water_layer_frames(dem, wc_int, tuple(bbox), lat, lon, radius_m, rainfall_mm)
        for water_layer in frames:
            chart_slot.pydeck_chart(assemble(water_layer), height=520)
            time.sleep(0.12)
    else:
        water_layer, _ = build_water_layer(dem, wc_int, bbox, lat, lon, radius_m, rainfall_mm)
        chart_slot.pydeck_chart(assemble(water_layer), height=520)

    caption_col.caption(
        "\"Play rise\" replays the same CA model's own iteration order as a progression -- there's no "
        "real-world seconds-per-frame meaning, only earlier-vs-later in how the water redistributes."
    )
    st.caption(
        f"{label} · {len(buildings)} buildings · rainfall {rainfall_mm}mm (converged state) · "
        "🟦 shallow (2-15cm) · 🔵 moderate (15-40cm) · 🟪 severe (>40cm) standing water."
    )
    st.caption(
        "Water extent is smoothed from a coarse ~100m simulation grid (only a handful of raw cells fall "
        "inside this small a radius) -- read the smooth-looking boundary as an approximate extent, not a "
        "surveyed flood line."
    )
