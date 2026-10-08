"""
geo_data.py — static risk_engine/ outputs, loaded once per process.

FastAPI-side equivalent of streamlit_app/data_loader.py's cached loaders,
with the same files and the same semantics, but @functools.lru_cache
instead of @st.cache_data (no Streamlit runtime here) -- same effect
(load from disk once, reuse the in-memory object after), different
decorator.

Phase 1 simplification, noted rather than silently dropped: only the 6
pilot-district assemblies and the 1013-cell pilot grid are wired up here.
incident_store.assign_district()/zone_for_point() also fall back to the
separate Lower Volta extended-coverage region; that fallback isn't ported
yet since Phase 1's walking skeleton (report -> queue -> verify -> push)
doesn't need it. Same file, same pattern, to add later:
risk_engine/data/lower_volta_district_assemblies.geojson +
lower_volta_risk_grid.geojson.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, shape

DATA_DIR = Path(__file__).parent.parent / "risk_engine" / "data"


@lru_cache(maxsize=1)
def assembly_geometries() -> gpd.GeoDataFrame:
    return gpd.read_file(DATA_DIR / "pilot_district_assemblies.geojson")


@lru_cache(maxsize=1)
def risk_zones() -> list[dict]:
    return json.loads((DATA_DIR / "risk_zones.json").read_text())["zones"]


@lru_cache(maxsize=1)
def historical_events() -> list[dict]:
    return json.loads((DATA_DIR / "historical_flood_events.json").read_text())["events"]


def assign_district(lon: float, lat: float) -> str | None:
    """Point-in-polygon against the 7 pilot assemblies -- same approach as
    incident_store.assign_district(), Lower Volta fallback not yet ported
    (see module docstring)."""
    pt = Point(lon, lat)
    for _, row in assembly_geometries().iterrows():
        if row.geometry.contains(pt):
            return row["name"]
    return None


def zone_for_point(lon: float, lat: float) -> dict | None:
    """The fine-grained RiskZone containing this point, if any -- same
    source and lookup as incident_store.zone_for_point()."""
    pt = Point(lon, lat)
    for z in risk_zones():
        if shape(z["geometry"]).contains(pt):
            return z
    return None
