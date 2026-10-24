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
import requests
from shapely.geometry import Point, shape

from clustering import haversine_km

DATA_DIR = Path(__file__).parent.parent / "risk_engine" / "data"
HISTORICAL_EVENT_RADIUS_KM = 2.0


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


def _geocode(address: str, region_hint: str = "Accra, Ghana") -> tuple[float, float, str] | None:
    """Same Nominatim pattern as streamlit_app/geo_tools.py's _geocode()."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{address}, {region_hint}", "format": "json", "limit": 1},
            headers={"User-Agent": "ThirdWave-backend/1.0"},
            timeout=10,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", address)
    except Exception:
        pass
    return None


def nearby_historical_events(lat: float, lon: float, radius_km: float = HISTORICAL_EVENT_RADIUS_KM) -> list[dict]:
    """Same join streamlit_app/geo_tools.py's find_zone_by_address uses --
    a computed score alone can miss hazard types (dam-release floods) its
    satellite/terrain inputs can't detect, so this is always returned
    alongside the zone lookup, not as a separate call the client has to
    remember to make."""
    out = []
    for e in historical_events():
        if e.get("lat") is None or e.get("lon") is None:
            continue
        d = haversine_km(lon, lat, e["lon"], e["lat"])
        if d <= radius_km:
            out.append({
                "date": e["date"], "name": e["name"], "hazard_type": e.get("hazard_type"),
                "deaths": e.get("deaths"), "cause": e.get("cause"),
                "distance_km": round(d, 2),
            })
    return sorted(out, key=lambda r: r["distance_km"])


def find_zone_by_address(address: str) -> dict:
    """Ported from streamlit_app/geo_tools.py's function of the same name.
    Lower Volta extended-coverage fallback is NOT ported -- same Phase 1
    simplification as assign_district()/zone_for_point() (see module
    docstring): a location outside the pilot grid returns an
    out-of-coverage error here, where the Streamlit version would also
    try the separate Lower Volta basin grid."""
    result = _geocode(address)
    if not result:
        # "{address}, Accra, Ghana" can fail outright for a location the
        # region hint doesn't fit, not just mis-resolve -- retry broadly
        # before giving up.
        result = _geocode(address, region_hint="Ghana")
        if not result:
            return {"error": f"Could not geocode '{address}'."}
    lat, lon, label = result
    events = nearby_historical_events(lat, lon)
    zone = zone_for_point(lon, lat)

    if zone:
        out = {
            "resolved_address": label, "zone_id": zone["id"].replace("RZ-", ""),
            "assembly": zone["assembly"], "score": zone["score"], "level": zone["level"],
            "confidence": zone["confidence"],
            "contributing_factors": [f["text"] for f in zone["contributing_factors"]],
            "nearby_historical_events": events,
        }
        out["historical_context_note"] = (
            f"{len(events)} documented flood event(s) within {HISTORICAL_EVENT_RADIUS_KM:.0f}km -- weigh "
            "this alongside the computed score, don't rely on the score alone, especially for hazard types "
            "(like dam-release floods) the score's satellite/terrain inputs can't see coming."
            if events else
            f"No documented flood events within {HISTORICAL_EVENT_RADIUS_KM:.0f}km in our curated record "
            "-- absence of history here is not the same as absence of risk."
        )
        return out

    out = {"resolved_address": label, "error": "This location is outside the pilot district's coverage area."}
    if events:
        out["nearby_historical_events"] = events
        out["historical_context_note"] = (
            f"No computed score available (outside pilot coverage), but {len(events)} documented flood "
            "event(s) exist within range."
        )
    return out
