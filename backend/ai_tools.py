"""
ai_tools.py — tool functions the AI Assistant chat can call, backend port
of streamlit_app/geo_tools.py's TOOLS/TOOL_FUNCTIONS for Phase 4 feature
#6. Each function reads data already computed by risk_engine/*.py (or
queries this backend's own live Report table); none of them compute
anything new (same Tier 1 scope as the Streamlit version).

Scope cuts from the Streamlit version, documented rather than silently
dropped (same discipline as geo_data.py's Phase 1 notes):
- Pilot district only -- no Lower Volta / Ayawaso West / La-Nkwantanang-
  Madina extended-coverage fallback (find_zone_by_address, assembly
  comparison, drain priority, population exposure are all pilot-only
  here, same as everywhere else in this backend).
- No Sentinel-1 SAR corroboration on citizen reports (citizen_report_sar_check.py
  is a separate offline pipeline script, not ported here) -- live reports
  are returned without the sar_corroboration field the Streamlit version
  attaches.
- No per-district channel-encroachment breakdown or satellite-evidence-
  image lookup (get_channel_encroachment_for_district /
  get_satellite_evidence_paths_for_district) -- those are government-
  briefing-specific tools (demo imagery tied to parallel git branches);
  get_drain_priority covers the citizen-relevant "where's encroachment
  worst" question pilot-wide instead.
- get_active_incidents reads this backend's real Report table instead of
  Streamlit's synthetic demo-seed/session-state incidents -- a live
  replacement, not a missing feature.

Live DB access (get_active_incidents, get_verified_citizen_reports_for_district,
and the nearby-reports join inside find_zone_by_address) needs a SQLModel
Session, which a tool-input schema from Claude can't supply -- build_tool_functions()
binds the current request's session via closure instead, called fresh per
request by routers/assistant.py (same reason routers/routing.py doesn't
reuse a module-level session).
"""

from __future__ import annotations

from sqlmodel import Session, select

import geo_data
from clustering import haversine_km
from models import Report

NEARBY_REPORT_RADIUS_KM = 2.0

SYSTEM_PROMPT = """You are the ThirdWave AI Assistant, embedded in a flood early-warning \
system for a pilot district in Accra, Ghana. You answer questions about flood \
vulnerability by calling the tools available to you -- all of them read data that \
was already computed by an offline geospatial pipeline (Sentinel-1 SAR water \
occurrence, Copernicus DEM elevation, ESA WorldCover, OpenStreetMap buildings/waterways, \
WorldPop population) or this app's own live, officer-verified citizen reports. You do \
not have live satellite access and cannot run new geospatial analysis -- only look up \
what has already been computed.

Rules:
- Always call a tool rather than guessing at numbers, zone IDs, or scores.
- If a tool returns an error (e.g. an address couldn't be geocoded, or a location is \
outside the pilot district), say so plainly -- don't invent a fallback answer.
- Keep answers concise and concrete: cite zone IDs, scores, and levels when relevant.
- This is a proof-of-concept pilot covering a small area of Accra, not all of Ghana -- \
if asked about somewhere clearly outside the pilot district, say the pilot doesn't \
cover it rather than guessing.
- The computed score is NOT the whole picture. find_zone_by_address also returns any \
documented historical flood events, and any live verified citizen reports, near that \
location -- always mention them when present, and treat them as real, independent \
evidence, not a footnote. The score is built from satellite/terrain data (SAR, DEM, \
land cover) and structurally cannot see hazard types like dam-release floods, drainage \
encroachment, or one-off infrastructure failures -- a "Low" score next to a documented \
flood history is a real gap in what the score can see, not a contradiction to explain \
away. Say so plainly when it happens.
"""


def _nearby_verified_reports(session: Session, lon: float, lat: float) -> list[dict]:
    reports = session.exec(select(Report).where(Report.status == "verified")).all()
    out = []
    for r in reports:
        d = haversine_km(lon, lat, r.lon, r.lat)
        if d <= NEARBY_REPORT_RADIUS_KM:
            out.append({
                "report_id": r.id, "hazard_type": r.hazard_type, "description": r.description,
                "location_label": r.location_label, "distance_km": round(d, 2),
                "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            })
    return sorted(out, key=lambda x: x["distance_km"])


def _find_zone_by_address(session: Session, address: str) -> dict:
    geocoded = geo_data.geocode_address(address)
    if "error" in geocoded:
        return geocoded
    lat, lon, label = geocoded["lat"], geocoded["lon"], geocoded["resolved_address"]
    out = geo_data.zone_info_for_point(lon, lat, label)
    out["nearby_verified_citizen_reports"] = _nearby_verified_reports(session, lon, lat)
    return out


def _get_top_risk_zones(n: int = 5, level_filter: str | None = None) -> dict:
    zones = geo_data.risk_zones()
    if level_filter:
        zones = [z for z in zones if z["level"] == level_filter]
    zones = sorted(zones, key=lambda z: -z["score"])[:n]
    return {"zones": [
        {"zone_id": z["id"].replace("RZ-", ""), "assembly": z["assembly"], "score": z["score"], "level": z["level"]}
        for z in zones
    ]}


def _get_assembly_comparison() -> dict:
    return {"assemblies": geo_data.assembly_scores()}


def _get_drain_priority(n: int = 5) -> dict:
    zones = geo_data.risk_zones()
    encroachment = geo_data.encroachment_index()
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


def _get_population_exposure_summary() -> dict:
    zones = geo_data.population_exposure()["zones"]
    total_pop = sum(z["estimated_population"] for z in zones.values())
    total_buildings = sum(z["n_buildings"] for z in zones.values())
    by_level: dict[str, dict] = {}
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


def _get_historical_flood_events() -> dict:
    events = geo_data.historical_events()
    return {"events": [
        {"date": e["date"], "name": e["name"], "location": e.get("location_name"),
         "deaths": e.get("deaths"), "source": e.get("source")}
        for e in events
    ]}


def _get_active_incidents(session: Session) -> dict:
    reports = session.exec(select(Report).where(Report.status == "verified")).all()
    return {"incidents": [
        {
            "id": r.id, "hazard_type": r.hazard_type, "district": r.district,
            "depth_lo_m": r.depth_lo_m, "depth_hi_m": r.depth_hi_m,
            "synthetic": r.synthetic,
        }
        for r in reports
    ]}


def _get_verified_citizen_reports_for_district(session: Session, district: str) -> dict:
    reports = session.exec(
        select(Report).where(Report.status == "verified", Report.district == district)
    ).all()
    return {
        "district": district, "n_verified_reports": len(reports),
        "reports": [
            {
                "report_id": r.id, "hazard_type": r.hazard_type, "description": r.description,
                "location_label": r.location_label, "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            }
            for r in reports
        ],
    }


TOOLS = [
    {
        "name": "find_zone_by_address",
        "description": "Look up the flood vulnerability zone containing a given address or landmark in the pilot district. Also returns any documented historical flood events and live officer-verified citizen reports within ~2km, since the computed score alone can miss hazard types (like dam-release floods or localized drainage encroachment) its satellite/terrain inputs can't detect -- always consider all three together.",
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
        "description": "Compare vulnerability scores across the pilot district's assemblies (municipal-level).",
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
        "description": "Get documented historical Accra flood events used to validate this project's flood risk model.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_active_incidents",
        "description": "Get currently active, officer-verified flood incidents in the pilot district.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_verified_citizen_reports_for_district",
        "description": "Get live, officer-verified citizen flood reports for one specific district/assembly in the pilot district.",
        "input_schema": {"type": "object", "properties": {
            "district": {"type": "string", "description": "Exact assembly/district name, e.g. 'Weija Gbawe Municipal'"}},
            "required": ["district"]},
    },
]


def build_tool_functions(session: Session) -> dict:
    """Binds the request's DB session into the tools that need one, via
    closure -- Claude's tool_use input schema has no way to pass a
    Session, so this is called fresh per request instead of module-level
    TOOL_FUNCTIONS (see module docstring)."""
    return {
        "find_zone_by_address": lambda address: _find_zone_by_address(session, address),
        "get_top_risk_zones": _get_top_risk_zones,
        "get_assembly_comparison": lambda: _get_assembly_comparison(),
        "get_drain_priority": _get_drain_priority,
        "get_population_exposure_summary": lambda: _get_population_exposure_summary(),
        "get_historical_flood_events": lambda: _get_historical_flood_events(),
        "get_active_incidents": lambda: _get_active_incidents(session),
        "get_verified_citizen_reports_for_district": lambda district: _get_verified_citizen_reports_for_district(session, district),
    }
