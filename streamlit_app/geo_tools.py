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
import os
from pathlib import Path

import requests
from shapely.geometry import Point, shape

from data_loader import (
    DATA_DIR, load_risk_zones, load_assembly_scores, load_encroachment_index,
    load_historical_events, load_demo_seed_incidents, load_lower_volta_risk_grid_gdf,
)

# Same backend the briefing-review page talks to (govt_briefing_review.py)
# -- verified citizen reports live in the FastAPI/SQLite backend, not in a
# risk_engine/data/*.json file, so reaching them means an HTTP call, not a
# local read like every other tool in this module.
BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")
CITIZEN_SAR_CHECKS_PATH = Path(DATA_DIR) / "dam_spillage_sar" / "citizen_report_checks.json"

# Known channel-encroachment index files across this project's several
# parallel branches (see .claude/plans/temporal-waddling-trinket.md) --
# not every file exists on every checkout (e.g. the East Legon one lives
# only on the ayawaso-west-encroachment branch), so this is read
# defensively: a missing file is skipped, not an error, same discipline
# every other optional-data read in this project follows.
_ENCROACHMENT_INDEX_FILES = {
    "channel_encroachment_index.json": "pilot district",
    "lower_volta_channel_encroachment_index.json": "Lower Volta basin",
    "ayawaso_west_channel_encroachment_index.json": "Ayawaso West (East Legon)",
    "madina_channel_encroachment_index.json": "La-Nkwantanang-Madina",
}


HISTORICAL_EVENT_RADIUS_KM = 2.0


def _haversine_km(lon1, lat1, lon2, lat2) -> float:
    from math import radians, sin, cos, asin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def _nearby_historical_events(lat: float, lon: float, radius_km: float = HISTORICAL_EVENT_RADIUS_KM) -> list[dict]:
    """Historical events within radius_km of a point -- the piece that
    makes get_historical_flood_events() more than a separate, easy-to-skip
    tool: find_zone_by_address calls this directly so a computed score is
    never presented without also surfacing whether this exact area has a
    documented flooding history, per project chat history ("the chatbot
    must use historical reports as additional context besides the risk
    score")."""
    out = []
    for e in load_historical_events():
        if e.get("lat") is None or e.get("lon") is None:
            continue
        d = _haversine_km(lon, lat, e["lon"], e["lat"])
        if d <= radius_km:
            out.append({
                "date": e["date"], "name": e["name"], "hazard_type": e.get("hazard_type"),
                "deaths": e.get("deaths"), "cause": e.get("cause"),
                "distance_km": round(d, 2),
            })
    return sorted(out, key=lambda r: r["distance_km"])


def _sar_checks_by_report_id() -> dict:
    if not CITIZEN_SAR_CHECKS_PATH.exists():
        return {}
    return json.loads(CITIZEN_SAR_CHECKS_PATH.read_text())


def _nearby_verified_reports(lat: float, lon: float, radius_km: float = HISTORICAL_EVENT_RADIUS_KM) -> list[dict]:
    """Verified citizen reports within radius_km of a point, live from the
    backend (not a static risk_engine/data file -- see BACKEND_URL),
    attached with any Sentinel-1 SAR corroboration already computed for
    that exact report by citizen_report_sar_check.py. Mirrors
    _nearby_historical_events()'s role: a computed score should never be
    shown without also surfacing live citizen evidence nearby, same as it
    already does for curated historical events. Fails soft (empty list +
    a note) if the backend isn't reachable -- a down backend must not
    break the rest of the tool-calling loop."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/incidents/nearby", params={"lat": lat, "lon": lon, "radius_km": radius_km}, timeout=8,
        )
        resp.raise_for_status()
        reports = resp.json()
    except Exception as exc:
        return [{"error": f"Could not reach the citizen-reports backend ({exc}) -- this does NOT mean there are "
                           "no nearby reports, only that they couldn't be checked."}]

    checks = _sar_checks_by_report_id()
    out = []
    for r in reports:
        entry = {
            "report_id": r["id"], "hazard_type": r["hazard_type"], "description": r["description"],
            "location_label": r.get("location_label"), "distance_km": r["distance_km"],
            "verified_at": r.get("verified_at"),
        }
        check = checks.get(r["id"])
        if check:
            if "error" in check:
                entry["sar_corroboration"] = {"status": "check_failed", "detail": check["error"]}
            else:
                entry["sar_corroboration"] = {
                    "new_flood_at_peak_km2": check["new_flood_at_peak_km2"], "verdict": check["verdict"],
                    "scene_dates": check["scene_dates"],
                }
        else:
            entry["sar_corroboration"] = {"status": "not_yet_checked"}
        out.append(entry)
    return out


def get_verified_citizen_reports_for_district(district: str) -> dict:
    """Verified citizen flood reports for a district, straight from the
    live backend (not historical/curated data -- see
    get_historical_flood_events for that), each with any Sentinel-1 SAR
    corroboration already computed for it by citizen_report_sar_check.py.
    This is the live counterpart to historical events: use it to show a
    district assembly that current, on-the-ground reports are backed by
    independent satellite evidence, not just citizen testimony alone."""
    try:
        resp = requests.get(f"{BACKEND_URL}/incidents/active", params={"district": district}, timeout=8)
        resp.raise_for_status()
        reports = resp.json()
    except Exception as exc:
        return {"district": district, "error": f"Could not reach the citizen-reports backend ({exc})."}

    checks = _sar_checks_by_report_id()
    out = []
    for r in reports:
        entry = {
            "report_id": r["id"], "hazard_type": r["hazard_type"], "description": r["description"],
            "location_label": r.get("location_label"), "verified_at": r.get("verified_at"),
        }
        check = checks.get(r["id"])
        if check:
            if "error" in check:
                entry["sar_corroboration"] = {"status": "check_failed", "detail": check["error"]}
            else:
                entry["sar_corroboration"] = {
                    "new_flood_at_peak_km2": check["new_flood_at_peak_km2"], "verdict": check["verdict"],
                    "scene_dates": check["scene_dates"],
                }
        else:
            entry["sar_corroboration"] = {"status": "not_yet_checked"}
        out.append(entry)
    return {
        "district": district, "n_verified_reports": len(out), "reports": out,
        "note": "sar_corroboration is from citizen_report_sar_check.py, a Sentinel-1 change-detection check "
                "anchored to this exact report's location and submission date -- 'not_yet_checked' means that "
                "script hasn't run for this report, not that satellite evidence is absent.",
    }


def _geocode(address: str, region_hint: str = "Accra, Ghana"):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{address}, {region_hint}", "format": "json", "limit": 1},
            headers={"User-Agent": "ThirdWave-streamlit-poc/1.0"},
            timeout=10,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", address)
    except Exception:
        pass
    return None


def _find_zone_in_lower_volta(lat: float, lon: float) -> dict | None:
    """Lower Volta is a separate, non-contiguous extended-coverage region
    (Akosombo/Akuse/Sogakope/Ada basin, ~150km from Accra) -- checked only
    after the pilot grid misses, and only against a broadly re-geocoded
    point (see find_zone_by_address), since the pilot-biased "Accra, Ghana"
    geocode query can mis-resolve outlying basin towns."""
    pt = Point(lon, lat)
    gdf = load_lower_volta_risk_grid_gdf()
    hits = gdf[gdf.contains(pt)]
    if hits.empty:
        return None
    row = hits.iloc[0]
    return {
        "zone_id": row["zone_id"], "assembly": row["assembly"],
        "score": round(float(row["score"]), 1), "level": row["level"],
        "coverage_note": (
            "This is in the Lower Volta extended-coverage region, NOT the MVP pilot district -- it gets "
            "the same fine-grid treatment (500m cells, roads, population, encroachment) but the score is "
            "the same multi-year statistical SAR/DEM/land-cover formula, which structurally cannot see a "
            "one-off dam-release flood. This basin has documented 2023 Akosombo/Kpong dam-spillage "
            "flooding (35,857 displaced at Mepe) -- check nearby_historical_events below before treating "
            "a Low/Moderate score here as reassuring."
        ),
    }


def find_zone_by_address(address: str) -> dict:
    """Geocode an address/landmark and return the pilot RiskZone that
    contains it, PLUS any documented historical flood events within ~2km --
    the computed score and the historical record are always returned
    together, not as two things the model has to remember to combine
    itself. A zone can look "Low" on the computed score yet still sit near
    a real, documented flood (e.g. dam-release events, which the score's
    SAR/DEM/land-cover inputs have no way to anticipate) -- that's exactly
    the gap this join surfaces rather than hides."""
    result = _geocode(address)
    if not result:
        # "{address}, Accra, Ghana" can fail outright for a basin town
        # (e.g. Mepe, Akuse) rather than just mis-resolving -- retry broadly
        # before giving up entirely.
        result = _geocode(address, region_hint="Ghana")
        if not result:
            return {"error": f"Could not geocode '{address}'."}
    lat, lon, label = result
    nearby_events = _nearby_historical_events(lat, lon)
    pt = Point(lon, lat)
    zones = load_risk_zones()
    for z in zones:
        if shape(z["geometry"]).contains(pt):
            out = {
                "resolved_address": label, "zone_id": z["id"].replace("RZ-", ""),
                "assembly": z["assembly"], "score": z["score"], "level": z["level"],
                "confidence": z["confidence"],
                "contributing_factors": [f["text"] for f in z["contributing_factors"]],
            }
            if nearby_events:
                out["nearby_historical_events"] = nearby_events
                out["historical_context_note"] = (
                    f"{len(nearby_events)} documented flood event(s) within "
                    f"{HISTORICAL_EVENT_RADIUS_KM:.0f}km -- weigh this alongside the computed score, "
                    "don't rely on the score alone, especially for hazard types (like dam-release "
                    "floods) the score's satellite/terrain inputs can't see coming."
                )
            else:
                out["nearby_historical_events"] = []
                out["historical_context_note"] = f"No documented flood events within {HISTORICAL_EVENT_RADIUS_KM:.0f}km in our curated record -- absence of history here is not the same as absence of risk."
            out["nearby_verified_citizen_reports"] = _nearby_verified_reports(lat, lon)
            return out
    # Not in the pilot grid -- try the Lower Volta basin before giving up.
    # Re-geocode broadly ("Ghana", not "Accra, Ghana"): the pilot-biased
    # query above can mis-resolve outlying towns like Akosombo/Sogakope/Ada.
    broad = _geocode(address, region_hint="Ghana")
    if broad:
        b_lat, b_lon, b_label = broad
        lv = _find_zone_in_lower_volta(b_lat, b_lon)
        if lv:
            lv["resolved_address"] = b_label
            b_events = _nearby_historical_events(b_lat, b_lon)
            lv["nearby_historical_events"] = b_events
            lv["historical_context_note"] = (
                f"{len(b_events)} documented flood event(s) within {HISTORICAL_EVENT_RADIUS_KM:.0f}km -- "
                "weigh this alongside the computed score."
                if b_events else
                f"No documented flood events within {HISTORICAL_EVENT_RADIUS_KM:.0f}km in our curated "
                "record -- absence of history here is not the same as absence of risk."
            )
            lv["nearby_verified_citizen_reports"] = _nearby_verified_reports(b_lat, b_lon)
            return lv

    out = {"resolved_address": label, "error": "This location is outside the pilot district's coverage area."}
    if nearby_events:
        out["nearby_historical_events"] = nearby_events
        out["historical_context_note"] = (
            f"No computed score available (outside pilot coverage), but {len(nearby_events)} documented "
            "flood event(s) exist within range -- mention this even though there's no score to give."
        )
    out["nearby_verified_citizen_reports"] = _nearby_verified_reports(lat, lon)
    return out


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
    """District/assembly-level vulnerability comparison (the 7-assembly pilot)."""
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


def get_channel_encroachment_for_district(district: str) -> dict:
    """Channel-encroachment index results (OSM building-to-waterway
    distance) for one district/assembly, searched across every
    encroachment-index file this project has produced (pilot, Lower
    Volta, Ayawaso West -- whichever exist on this checkout). Returns the
    worst (closest) cells found, not every cell, since a briefing needs
    the headline finding, not a full dump."""
    import geopandas as gpd

    grid_files = {
        "channel_encroachment_index.json": "pilot_risk_grid.geojson",
        "lower_volta_channel_encroachment_index.json": "lower_volta_risk_grid.geojson",
        "ayawaso_west_channel_encroachment_index.json": "ayawaso_west_risk_grid.geojson",
        "madina_channel_encroachment_index.json": "madina_risk_grid.geojson",
    }
    worst: list[dict] = []
    searched_sources = []
    for index_name, grid_name in grid_files.items():
        index_path = Path(DATA_DIR) / index_name
        grid_path = Path(DATA_DIR) / grid_name
        if not index_path.exists() or not grid_path.exists():
            continue
        searched_sources.append(_ENCROACHMENT_INDEX_FILES.get(index_name, index_name))
        index = json.loads(index_path.read_text())
        grid = gpd.read_file(grid_path)
        if "assembly" not in grid.columns:
            continue
        district_zone_ids = set(grid.loc[grid["assembly"] == district, "zone_id"])
        if not district_zone_ids:
            continue
        for zone_id in district_zone_ids:
            rec = index.get(zone_id)
            if rec and rec.get("status") == "ok":
                worst.append({
                    "zone_id": zone_id, "min_building_to_waterway_m": rec["min_building_to_waterway_m"],
                    "encroachment_level": rec["encroachment_level"], "n_buildings": rec["n_buildings"],
                })
    worst.sort(key=lambda r: r["min_building_to_waterway_m"])
    return {
        "district": district, "sources_searched": searched_sources,
        "n_cells_with_findings": len(worst), "worst_cells": worst[:10],
        "note": "min_building_to_waterway_m is from OpenStreetMap geometry, not a field survey -- "
                "say so if citing it.",
    }


# Evidence images this project has actually produced and verified this
# session (true/false-color satellite crops, each manually checked against
# the real OSM waterway/building overlay before being trusted -- see
# project chat history). A small explicit map, not filename-guessing: the
# naming across risk_engine/data/*.png isn't consistent enough to pattern-
# match reliably, and a wrong image attached to the wrong district would
# be worse than a missing one.
_DISTRICT_EVIDENCE_IMAGES = {
    "La-Nkwantanang-Madina Municipal": ["madina_zongo_s2_imagery.png"],
    "Ablekuma Central Municipal": ["ablekuma_central_korlebu_s2_imagery.png", "ablekuma_central_kaneshie_s2_imagery.png"],
    "Ablekuma North Municipal": ["ablekuma_north_s2_imagery.png", "alajo_s2_imagery.png"],
    "Weija Gbawe Municipal": ["weija_tetegu_truecolor.png", "weija_tetegu_falsecolor.png"],
    "Ayawaso West Municipal": ["ayawaso_west_encroachment_truecolor.png", "ayawaso_west_encroachment_falsecolor.png"],
    "South Tongu": ["sogakope_s2_imagery.png"],
    "Lower Manya": ["akuse_s2_imagery.png"],
    "North Tongu": ["juapong_s2_imagery.png"],
    "Asuogyaman": ["juapong_s2_imagery.png"],
    "Ada East": ["adafoah_s2_imagery.png"],
}


def get_satellite_evidence_paths_for_district(district: str) -> dict:
    """Which verified satellite-evidence images (if any) exist for this
    district, and whether they're actually present on this checkout right
    now (several live on different git branches -- see
    .claude/plans/temporal-waddling-trinket.md). Paths are relative to
    risk_engine/data/."""
    names = _DISTRICT_EVIDENCE_IMAGES.get(district, [])
    out = []
    for name in names:
        out.append({"filename": name, "present_on_this_checkout": (Path(DATA_DIR) / name).exists()})
    return {"district": district, "images": out}


TOOLS = [
    {
        "name": "find_zone_by_address",
        "description": "Look up the flood vulnerability zone containing a given address or landmark in the pilot district. Also returns any documented historical flood events within ~2km, since the computed score alone can miss hazard types (like dam-release floods) its satellite/terrain inputs can't detect -- always consider both together.",
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
    {
        "name": "get_channel_encroachment_for_district",
        "description": "Get channel-encroachment index findings (how close buildings sit to mapped waterways) for one specific district/assembly, searched across every encroachment-index file this project has produced.",
        "input_schema": {"type": "object", "properties": {
            "district": {"type": "string", "description": "Exact assembly/district name, e.g. 'Weija Gbawe Municipal' or 'South Tongu'"}},
            "required": ["district"]},
    },
    {
        "name": "get_satellite_evidence_paths_for_district",
        "description": "Check which verified satellite-imagery evidence files (if any) exist for a district, confirming they are present before citing them.",
        "input_schema": {"type": "object", "properties": {
            "district": {"type": "string", "description": "Exact assembly/district name"}},
            "required": ["district"]},
    },
    {
        "name": "get_verified_citizen_reports_for_district",
        "description": "Get live, officer-verified citizen flood reports for a district from the ThirdWave backend, each annotated with any Sentinel-1 SAR satellite corroboration already computed for that specific report (citizen_report_sar_check.py). Use this for current/live evidence, separate from the curated historical record.",
        "input_schema": {"type": "object", "properties": {
            "district": {"type": "string", "description": "Exact assembly/district name"}},
            "required": ["district"]},
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
    "get_channel_encroachment_for_district": get_channel_encroachment_for_district,
    "get_satellite_evidence_paths_for_district": get_satellite_evidence_paths_for_district,
    "get_verified_citizen_reports_for_district": get_verified_citizen_reports_for_district,
}


BRIEFING_SECTION_KEYS = ["purpose", "context", "finding", "implications", "sources"]

BRIEFING_SYSTEM_PROMPT = """You are drafting a short flood-risk briefing document for a Ghanaian district \
assembly, grounded ONLY in data you look up via the tools available to you -- the same tools the ThirdWave AI \
Assistant uses. Never invent a figure, date, or finding; if a tool returns nothing useful for this district, \
say so in the relevant section rather than filling the gap with a plausible-sounding guess.

Call get_historical_flood_events, get_channel_encroachment_for_district, \
get_satellite_evidence_paths_for_district, and get_verified_citizen_reports_for_district for the requested \
district before writing anything. Use get_assembly_comparison too if it helps explain how this district's \
generic risk score compares to others.

Write five sections, each 2-4 short sentences, plain language for a non-technical official reader (this mirrors \
real briefings already written by hand for Weija Gbawe, East Legon/Ayawaso West, and South Tongu -- match that \
tone: lead with the point, cite real numbers/dates, no padding):
- purpose: what this briefing is and why it exists for this district, in one or two sentences.
- context: relevant history -- documented flood events, recurrence pattern, any official findings (e.g. a task \
force report) already on record for this area. If get_verified_citizen_reports_for_district returned any \
reports, mention them here too as current/live evidence, distinct from the historical record -- and if any of \
them have SAR corroboration ("new_flood_at_peak_km2" > 0), say so explicitly as independent satellite backing \
for a citizen's claim.
- finding: the channel-encroachment result (or its absence) and what it means, mentioning whether verified \
satellite imagery exists for this finding (say so explicitly either way -- never claim imagery support that \
get_satellite_evidence_paths_for_district didn't confirm present).
- implications: 2-4 concrete, numbered recommendations for the assembly, grounded in what was actually found.
- sources: list the real source URLs returned by the tools (historical events' `source` fields), one per line.

When you are done calling tools, respond with ONLY a JSON object (no prose outside it, no markdown code fence) \
with exactly these keys: purpose, context, finding, implications, sources. Each value is a markdown-formatted \
string body for that section (no "## Heading" line -- the document template adds headings itself)."""


def draft_briefing(district: str, trigger_reason: str = "manual", source_finding: str | None = None) -> dict:
    """Runs a dedicated tool-calling turn (same engine as the AI Assistant
    chat, see claude_client.run_tool_loop) to draft the 5 briefing
    sections for one district. Returns {"sections": {...}, "tool_log": [...]}
    on success, or {"error": ...} if the model's final answer wasn't valid
    JSON with the expected keys -- this is a DRAFT for a human to review
    and edit, never auto-published (see govt_briefing_review.py and
    backend/routers/briefings.py's module docstrings for the same
    human-in-the-loop discipline vlm_client.py already established)."""
    from claude_client import get_client, run_tool_loop

    client = get_client()
    user_msg = f"Draft a briefing for {district}."
    if source_finding:
        user_msg += f" This was triggered by: {source_finding} (reason: {trigger_reason})."
    messages = [{"role": "user", "content": user_msg}]
    final_text, tool_log = run_tool_loop(
        client, system=BRIEFING_SYSTEM_PROMPT, tools=TOOLS, tool_functions=TOOL_FUNCTIONS,
        messages=messages, max_rounds=6, max_tokens=2048,
    )
    try:
        text = final_text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        sections = json.loads(text)
        missing = [k for k in BRIEFING_SECTION_KEYS if k not in sections]
        if missing:
            return {"error": f"Model's draft was missing section(s): {missing}", "raw": final_text, "tool_log": tool_log}
        return {"sections": {k: sections[k] for k in BRIEFING_SECTION_KEYS}, "tool_log": tool_log}
    except json.JSONDecodeError as exc:
        return {"error": f"Model's final answer wasn't valid JSON: {exc}", "raw": final_text, "tool_log": tool_log}
