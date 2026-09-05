"""
geo_tools.py — Tool functions the AI Assistant chat can call (Tier 1: query
what's already computed, not live remote-sensing -- see project chat
history for the Tier 1 / Tier 2 distinction). Each function here reads
data already produced and validated by risk_engine/*.py; none of them
compute anything new.

Each tool returns a small JSON-serializable dict, kept deliberately compact
-- these go back to Claude as tool_result content, and a bloated result
just burns tokens without adding value the model will use.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
from shapely.geometry import Point, shape

from data_loader import (
    DATA_DIR, load_risk_zones, load_assembly_scores, load_encroachment_index,
    load_historical_events, load_demo_seed_incidents,
)


def _geocode(address: str):
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


def find_zone_by_address(address: str) -> dict:
    """Geocode an address/landmark and return the pilot RiskZone that contains it."""
    result = _geocode(address)
    if not result:
        return {"error": f"Could not geocode '{address}'."}
    lat, lon, label = result
    pt = Point(lon, lat)
    zones = load_risk_zones()
    for z in zones:
        if shape(z["geometry"]).contains(pt):
            return {
                "resolved_address": label, "zone_id": z["id"].replace("RZ-", ""),
                "assembly": z["assembly"], "score": z["score"], "level": z["level"],
                "confidence": z["confidence"],
                "contributing_factors": [f["text"] for f in z["contributing_factors"]],
            }
    return {"resolved_address": label, "error": "This location is outside the pilot district's coverage area."}


def get_top_risk_zones(n: int = 5, level_filter: str | None = None) -> dict:
    """Top N zones by vulnerability score, optionally filtered to a level
    (Low/Moderate/High/Very High)."""
    zones = load_risk_zones()
    if level_filter:
        zones = [z for z in zones if z["level"] == level_filter]
    zones = sorted(zones, key=lambda z: -z["score"])[:n]
    return {"zones": [
        {"zone_id": z["id"].replace("RZ-", ""), "assembly": z["assembly"], "score": z["score"], "level": z["level"]}
        for z in zones
    ]}


def get_assembly_comparison() -> dict:
    """District/assembly-level vulnerability comparison (the 6-assembly pilot)."""
    df = load_assembly_scores()
    return {"assemblies": df[["assembly", "score", "level", "water_occ_pct", "impervious_pct"]].to_dict("records")}


def get_drain_priority(n: int = 5) -> dict:
    """Top N zones for drain maintenance priority (score + OSM encroachment severity)."""
    zones = load_risk_zones()
    encroachment = load_encroachment_index()
    rows = []
    for z in zones:
        zone_id = z["id"].replace("RZ-", "")
        enc = encroachment.get(zone_id, {})
        if enc.get("status") != "ok":
            continue
        rows.append({
            "zone_id": zone_id, "assembly": z["assembly"], "score": z["score"],
            "min_building_to_waterway_m": enc["min_building_to_waterway_m"],
            "encroachment_level": enc["encroachment_level"],
        })
    rows.sort(key=lambda r: r["min_building_to_waterway_m"])
    return {"priority_zones": rows[:n],
            "note": "Sorted by closest building-to-waterway distance (most encroached first)."}


def get_population_exposure_summary() -> dict:
    """Pilot-wide population/building exposure summary, and the breakdown by risk level."""
    raw = json.loads((Path(DATA_DIR) / "population_exposure.json").read_text())
    zones = raw["zones"]
    total_pop = sum(z["estimated_population"] for z in zones.values())
    total_buildings = sum(z["n_buildings"] for z in zones.values())
    by_level = {}
    for z in zones.values():
        lvl = z["level"]
        by_level.setdefault(lvl, {"population": 0, "buildings": 0})
        by_level[lvl]["population"] += z["estimated_population"]
        by_level[lvl]["buildings"] += z["n_buildings"]
    return {
        "total_estimated_population": round(total_pop), "total_buildings": total_buildings,
        "by_risk_level": {k: {"population": round(v["population"]), "buildings": v["buildings"]}
                           for k, v in by_level.items()},
        "source": "WorldPop Ghana 2020 gridded estimate + OSM building footprints",
    }


def get_historical_flood_events() -> dict:
    """Documented historical Accra flood events used to backtest this project's model."""
    events = load_historical_events()
    return {"events": [
        {"date": e["date"], "name": e["name"], "location": e.get("location_name"),
         "deaths": e.get("deaths"), "source": e.get("source")}
        for e in events
    ]}


def get_active_incidents() -> dict:
    """Currently active/seeded incidents (from this browser session + historical seed data)."""
    import streamlit as st
    seed = load_demo_seed_incidents()
    incidents = list(seed["incidents"])
    if "incidents" in st.session_state:
        incidents = st.session_state.incidents
    return {"incidents": [
        {"id": i["id"], "hazard_type": i["hazard_type"], "severity": i["severity"], "status": i["status"]}
        for i in incidents
    ]}


TOOLS = [
    {
        "name": "find_zone_by_address",
        "description": "Look up the flood vulnerability zone containing a given address or landmark in the pilot district.",
        "input_schema": {"type": "object", "properties": {
            "address": {"type": "string", "description": "An address or landmark, e.g. 'Kwame Nkrumah Circle'"}},
            "required": ["address"]},
    },
    {
        "name": "get_top_risk_zones",
        "description": "Get the top N highest-vulnerability zones in the pilot district, optionally filtered by risk level.",
        "input_schema": {"type": "object", "properties": {
            "n": {"type": "integer", "description": "Number of zones to return, default 5"},
            "level_filter": {"type": "string", "enum": ["Low", "Moderate", "High", "Very High"],
                              "description": "Optional: only return zones at this risk level"}},
            "required": []},
    },
    {
        "name": "get_assembly_comparison",
        "description": "Compare vulnerability scores across the 6 pilot district assemblies (municipal-level).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_drain_priority",
        "description": "Get the top N zones prioritized for drain maintenance, based on vulnerability score and how close buildings sit to mapped waterways (OSM encroachment analysis).",
        "input_schema": {"type": "object", "properties": {
            "n": {"type": "integer", "description": "Number of zones to return, default 5"}}, "required": []},
    },
    {
        "name": "get_population_exposure_summary",
        "description": "Get pilot-wide estimated population and building counts, broken down by flood risk level.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_historical_flood_events",
        "description": "Get documented historical Accra flood events (2010-2025) used to validate this project's flood risk model.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_active_incidents",
        "description": "Get currently active/historical flood incidents tracked by the system.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_FUNCTIONS = {
    "find_zone_by_address": find_zone_by_address,
    "get_top_risk_zones": get_top_risk_zones,
    "get_assembly_comparison": get_assembly_comparison,
    "get_drain_priority": get_drain_priority,
    "get_population_exposure_summary": get_population_exposure_summary,
    "get_historical_flood_events": get_historical_flood_events,
    "get_active_incidents": get_active_incidents,
}
