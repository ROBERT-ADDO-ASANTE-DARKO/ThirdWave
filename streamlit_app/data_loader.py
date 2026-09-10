"""
data_loader.py — cached loaders for the risk_engine/ computed data.

Every function here reads a file already produced and validated earlier in
this project (see project memory / risk_engine/*.py) -- this module does not
compute anything new, it just loads and lightly reshapes for the UI.
Cached with st.cache_data so switching between feature pages doesn't re-read
disk on every rerun (Streamlit reruns the whole script on each interaction).
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent.parent / "risk_engine" / "data"


@st.cache_data
def load_assembly_scores() -> pd.DataFrame:
    """The 7-assembly pilot vulnerability scores (geospatial_vulnerability.py output)."""
    raw = json.loads((DATA_DIR / "pilot_zone_vulnerability.json").read_text())
    rows = []
    for name, r in raw.items():
        rows.append({
            "assembly": name,
            "score": r["score"],
            "level": r["level"],
            "water_occ_pct": r["water_occ_pct"],
            "low_elev_frac_pct": r["low_elev_frac_pct"],
            "median_elev_m": r["median_elev_m"],
            "impervious_pct": r["impervious_pct"],
            "wetland_water_pct": r["wetland_water_pct"],
            "vegetation_pct": r["vegetation_pct"],
        })
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


@st.cache_data
def load_extended_district_scores() -> pd.DataFrame:
    """All 10 districts (6 pilot + Weija Gbawe, Ga South, Tema, Ashaiman)."""
    raw = json.loads((DATA_DIR / "extended_district_vulnerability.json").read_text())
    rows = []
    for name, r in raw.items():
        rows.append({
            "assembly": name,
            "score": r["score"],
            "level": r["level"],
            "water_occ_pct": r["water_occ_pct"],
            "low_elev_frac_pct": r["low_elev_frac_pct"],
            "in_original_pilot": r.get("in_original_pilot", False),
        })
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


@st.cache_data
def load_assembly_geometries() -> gpd.GeoDataFrame:
    """Assembly polygons for the pilot's 6 districts, for mapping."""
    return gpd.read_file(DATA_DIR / "pilot_district_assemblies.geojson")


@st.cache_data
def load_extended_assembly_geometries() -> gpd.GeoDataFrame:
    return gpd.read_file(DATA_DIR / "extended_district_assemblies.geojson")


@st.cache_data
def load_risk_zones() -> list[dict]:
    """The 1013 fine-grained RiskZone records (score, contributing_factors, etc.)."""
    return json.loads((DATA_DIR / "risk_zones.json").read_text())["zones"]


@st.cache_data
def load_risk_grid_gdf() -> gpd.GeoDataFrame:
    return gpd.read_file(DATA_DIR / "pilot_risk_grid.geojson")


@st.cache_data
def load_encroachment_index() -> dict:
    return json.loads((DATA_DIR / "channel_encroachment_index.json").read_text())


@st.cache_data
def load_historical_events() -> list[dict]:
    return json.loads((DATA_DIR / "historical_flood_events.json").read_text())["events"]


@st.cache_data
def load_demo_seed_incidents() -> dict:
    return json.loads((DATA_DIR / "demo_seed_incidents.json").read_text())


LEVEL_COLOR = {
    "Low": "#1E8A4C",
    "Moderate": "#B8860B",
    "High": "#C1621B",
    "Very High": "#B0241D",
}

# Spec Section 8.1 design tokens, reused from the ThirdWave design system.
INK_NAVY = "#0B2545"
STEEL_BLUE = "#1E4E6B"
SIGNAL_TEAL = "#1B7A9E"
