"""
Government — Pluvial Flood (Inundation) Simulator.

Answers "how could a rainfall event flood a specific location, like Circle"
-- but explicitly NOT via a calibrated hydraulic model (HEC-RAS/SWMM/
LISFLOOD-FP). Real hydraulic modeling needs drain/culvert capacity,
channel cross-sections and calibrated roughness this project has no source
for, and our 30m Copernicus DEM is too coarse for street-scale hydraulics
to be trustworthy -- the same data-scarcity wall that pushed the whole
project toward a composite score in the first place (see
govt_scenario_simulator.py for the same framing).

What this IS: a fast, transparent proxy (inundation_model.py) -- rainfall
depth x land-cover runoff coefficient, redistributed downhill with a
cellular-automaton diffusion step over the same DEM used everywhere else
in this project. Good for showing *where* water would plausibly collect
and roughly how much; not a substitute for engineering-grade flood
modeling before any real infrastructure decision.
"""

from __future__ import annotations

from pathlib import Path

import folium
import numpy as np
import requests
import streamlit as st
from streamlit_folium import st_folium

from data_loader import DATA_DIR, LEVEL_COLOR
from inundation_model import simulate_ponding, depth_to_rgba

INPUTS_PATH = DATA_DIR / "inundation_inputs.npz"
ITERATIONS = 250

# Same rainfall thresholds derive_thresholds() in geospatial_vulnerability.py
# is built from (BASE_RAINFALL_WARNING_MM / BASE_RAINFALL_CRITICAL_MM) --
# reused here as slider reference points, not re-derived.
WARNING_MM = 60.0
CRITICAL_MM = 110.0


@st.cache_resource
def load_inputs():
    if not INPUTS_PATH.exists():
        return None
    d = np.load(INPUTS_PATH)
    return d["dem"], d["worldcover"], d["bbox"]


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


def latlon_to_pixel(lat, lon, bbox, shape):
    minlon, minlat, maxlon, maxlat = bbox
    rows, cols = shape
    row = int((maxlat - lat) / (maxlat - minlat) * rows)
    col = int((lon - minlon) / (maxlon - minlon) * cols)
    row = min(max(row, 0), rows - 1)
    col = min(max(col, 0), cols - 1)
    return row, col


def render():
    st.subheader("Pluvial Flood Simulator")
    st.warning(
        "⚠️ **This is a simplified proxy, not a hydraulic model.** No HEC-RAS/SWMM/LISFLOOD-FP-style "
        "simulation is running -- we have no drain/culvert capacity, channel cross-section, or calibrated "
        "roughness data for the pilot district, and the 30m DEM is too coarse for trustworthy street-scale "
        "hydraulics. This shows rainfall redistributed downhill over real terrain (Copernicus DEM) with a "
        "land-cover-based runoff coefficient -- useful for *where* water would plausibly collect and roughly "
        "how deep, not for engineering decisions."
    )

    inputs = load_inputs()
    if inputs is None:
        st.error(
            "Inundation input rasters not found -- run risk_engine/precompute_inundation_inputs.py first."
        )
        return
    dem, wc_int, bbox = inputs
    shape = dem.shape

    col1, col2 = st.columns([2, 1])
    with col1:
        rainfall_mm = st.slider(
            "6-hour rainfall depth (mm)", 0, 180, 60, 5,
            help=f"Reference points: {WARNING_MM:.0f}mm is this project's rainfall Warning threshold, "
                 f"{CRITICAL_MM:.0f}mm is Critical (baseline zone; see derive_thresholds() in "
                 f"geospatial_vulnerability.py).",
        )
    with col2:
        st.caption(f"⚠️ Warning ref: {WARNING_MM:.0f}mm · 🔴 Critical ref: {CRITICAL_MM:.0f}mm")

    address = st.text_input("Check a specific location", placeholder="e.g. Kwame Nkrumah Circle")

    with st.spinner("Simulating..."):
        depth = simulate_ponding(dem, wc_int, rainfall_mm=rainfall_mm, iterations=ITERATIONS)

    point = None
    if address:
        geo = geocode(address)
        if geo:
            lat, lon, label = geo
            row, col = latlon_to_pixel(lat, lon, bbox, shape)
            point = (lat, lon, label, float(depth[row, col]), float(dem[row, col]))
        else:
            st.error(f"Couldn't find '{address}'.")

    k1, k2, k3 = st.columns(3)
    k1.metric("Area with standing water > 2cm", f"{(depth > 0.02).mean() * 100:.1f}%")
    k2.metric("Deepest simulated ponding", f"{depth.max():.2f} m")
    if point:
        k3.metric(f"Depth near {point[2].split(',')[0]}", f"{point[3] * 100:.0f} cm", f"elev {point[4]:.1f}m")
    else:
        k3.metric("Depth at a location", "—", "enter an address above")

    minlon, minlat, maxlon, maxlat = bbox
    center_lat, center_lon = point[0:2] if point else ((minlat + maxlat) / 2, (minlon + maxlon) / 2)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13 if point else 12, tiles="OpenStreetMap")

    rgba = depth_to_rgba(depth, max_depth_m=1.0)
    folium.raster_layers.ImageOverlay(
        image=rgba, bounds=[[minlat, minlon], [maxlat, maxlon]],
        opacity=1.0, name="Simulated ponding",
    ).add_to(m)

    if point:
        lat, lon, label, depth_m, elev_m = point
        folium.Marker(
            [lat, lon], tooltip=f"{label}<br>Simulated depth: {depth_m * 100:.0f}cm · elev {elev_m:.1f}m",
            icon=folium.Icon(color="red" if depth_m > 0.1 else "blue"),
        ).add_to(m)

    st_folium(m, height=460, use_container_width=True, returned_objects=[])
    st.caption(
        "Color scale: pale cyan (shallow, ~2-15cm) -> blue (moderate) -> violet (severe, ≥60cm). "
        "Depths below 2cm aren't shown. Isolated low points can show unrealistically deep pooling since "
        "this proxy has no storm drains actively removing water -- treat the deepest single pixels as "
        "'needs a real survey', not a literal forecast."
    )

    st.divider()
    st.markdown("**What this does and doesn't show**")
    st.markdown(
        "- ✅ Uses real terrain (Copernicus DEM) and real land cover (ESA WorldCover) for the pilot district.\n"
        "- ✅ Shows plausible *relative* differences -- low-lying, built-up areas like Circle pond more than "
        "elevated, vegetated ones, for the same rainfall.\n"
        "- ❌ Does NOT model flow velocity, flood timing/duration, or storm drain/culvert capacity -- a real "
        "drain would carry away water this proxy leaves standing.\n"
        "- ❌ Is NOT calibrated or validated against a measured flood event -- treat depths as indicative, "
        "not predictive.\n"
        "- ❌ Not a substitute for real hydraulic modeling (HEC-RAS/SWMM) before any infrastructure decision."
    )
