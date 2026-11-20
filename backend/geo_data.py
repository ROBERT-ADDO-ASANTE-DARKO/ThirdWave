"""
geo_data.py — static risk_engine/ outputs, loaded once per process.

FastAPI-side equivalent of streamlit_app/data_loader.py's cached loaders,
with the same files and the same semantics, but @functools.lru_cache
instead of @st.cache_data (no Streamlit runtime here) -- same effect
(load from disk once, reuse the in-memory object after), different
decorator.

Phase 1 simplification, noted rather than silently dropped: only the 7
pilot-district assemblies and the 1013-cell pilot grid get the FULL
scoring pipeline (contributing_factors, confidence) here. Three
extended-coverage regions -- Ayawaso West (covers East Legon),
La-Nkwantanang-Madina, and Lower Volta (Ada East/West, South/North/
Central Tongu, Lower Manya, Asuogyaman -- the 2023 Akosombo dam-spillage
flood corridor) -- are also wired into zone_info_for_point()/
assign_district() at reduced fidelity (score/level only, via
ayawaso_west_risk_grid()/madina_risk_grid()/lower_volta_risk_grid()),
ported from streamlit_app/geo_tools.py's equivalent fallback (Madina) or
written fresh following that same pattern (Ayawaso West and Lower Volta,
neither of which had a citizen- or officer-facing point lookup anywhere
before this, despite Lower Volta already having a full risk grid +
channel-encroachment index computed and sitting in risk_engine/data/).
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
def obstruction_height() -> dict:
    """Copernicus DEM minus FABDEM, per pilot grid cell -- a free, real
    height-above-ground proxy (r=0.83 correlated with impervious land
    cover, see risk_engine/building_obstruction_height.py). ~30m-class,
    so it's a per-cell obstruction signal, not a building-level layer.
    Reported for context, not blended into any score -- same discipline
    as LULC elsewhere in this module."""
    return json.loads((DATA_DIR / "building_obstruction_height.json").read_text())


@lru_cache(maxsize=1)
def extended_assembly_geometries() -> gpd.GeoDataFrame:
    return gpd.read_file(DATA_DIR / "extended_district_assemblies.geojson")


@lru_cache(maxsize=1)
def extended_assembly_scores() -> list[dict]:
    """11 districts (the 7 pilot assemblies + Ayawaso West, Ga South, Tema,
    Ashaiman), added for regional context -- not part of the MVP pilot
    deliverable. Deliberately minimal field set, mirrors
    streamlit_app/data_loader.py's load_extended_district_scores(): this
    set was never re-audited for the pilot's full component-level
    display."""
    raw = json.loads((DATA_DIR / "extended_district_vulnerability.json").read_text())
    rows = [
        {
            "assembly": name,
            "score": r["score"],
            "level": r["level"],
            "water_occ_pct": r["water_occ_pct"],
            "low_elev_frac_pct": r["low_elev_frac_pct"],
            "in_original_pilot": r.get("in_original_pilot", False),
        }
        for name, r in raw.items()
    ]
    return sorted(rows, key=lambda r: -r["score"])


@lru_cache(maxsize=1)
def lower_volta_assembly_geometries() -> gpd.GeoDataFrame:
    return gpd.read_file(DATA_DIR / "lower_volta_district_assemblies.geojson")


@lru_cache(maxsize=1)
def lower_volta_assembly_scores() -> list[dict]:
    """The 7 Lower Volta basin districts (Ada East/West, Asuogyaman, Lower
    Manya, North/Central/South Tongu) -- full pilot-grade coverage, but a
    separate, non-contiguous region (~150km away, spanning 3 regions)
    from the Accra pilot, added for the 2023 Akosombo/Kpong dam-spillage
    flood history. The composite score here is a multi-year statistical
    measure (SAR + DEM + LULC) and cannot see a one-off dam-release flood
    -- every district still scores Low/Moderate despite that event; see
    historical_flood_events.json (AKOSOMBO-DAM-SPILLAGE-2023-09-15) for
    the real, separately-documented incident."""
    raw = json.loads((DATA_DIR / "lower_volta_district_vulnerability.json").read_text())
    rows = [
        {
            "assembly": name,
            "region": r.get("region"),
            "score": r["score"],
            "level": r["level"],
            "water_occ_pct": r["water_occ_pct"],
            "low_elev_frac_pct": r["low_elev_frac_pct"],
            "median_elev_m": r["median_elev_m"],
            "impervious_pct": r["impervious_pct"],
            "wetland_water_pct": r["wetland_water_pct"],
        }
        for name, r in raw.items()
    ]
    return sorted(rows, key=lambda r: -r["score"])


@lru_cache(maxsize=1)
def historical_events() -> list[dict]:
    return json.loads((DATA_DIR / "historical_flood_events.json").read_text())["events"]


@lru_cache(maxsize=1)
def grid_thresholds() -> dict:
    """Per-zone rainfall/river-level thresholds, keyed by bare zone_id (no
    "RZ-" prefix -- see zone_for_point()'s dicts for that distinction).
    Same file citizen_forecast.load_thresholds() reads."""
    return json.loads((DATA_DIR / "grid_zone_threshold_config.json").read_text())


@lru_cache(maxsize=1)
def assembly_scores() -> list[dict]:
    """The 7-assembly pilot vulnerability scores -- same file and shape as
    streamlit_app/data_loader.load_assembly_scores(), just a plain list of
    dicts here instead of a pandas DataFrame (this backend has no other use
    for pandas, so not worth adding as a dependency for one table)."""
    raw = json.loads((DATA_DIR / "pilot_zone_vulnerability.json").read_text())
    return [
        {
            "assembly": name, "score": r["score"], "level": r["level"],
            "water_occ_pct": r["water_occ_pct"], "low_elev_frac_pct": r["low_elev_frac_pct"],
            "median_elev_m": r["median_elev_m"], "impervious_pct": r["impervious_pct"],
            "wetland_water_pct": r["wetland_water_pct"],
        }
        for name, r in raw.items()
    ]


# Score -> level breakpoints, copied from risk_engine/geospatial_vulnerability.py
# (the same module that computed every *_district_vulnerability.json file
# below) rather than imported -- that module isn't on this backend's import
# path and pulling in its geopandas-heavy pipeline for one if/else isn't
# worth it. Only used to derive Ayawaso West's assembly-level level from a
# mean score, since (unlike Madina/Lower Volta) no ayawaso_west_district_
# vulnerability.json exists -- see _ayawaso_west_assembly_vulnerability().
def _score_to_level(score: float) -> str:
    return "Very High" if score >= 65 else "High" if score >= 45 else "Moderate" if score >= 25 else "Low"


@lru_cache(maxsize=1)
def madina_assembly_vulnerability() -> dict:
    """Assembly-level (not per-cell) SAR+DEM+LULC vulnerability for
    La-Nkwantanang-Madina Municipal -- same shape/formula as
    assembly_scores()'s pilot figures, independently computed and stored
    (unlike Ayawaso West's, see _ayawaso_west_assembly_vulnerability())."""
    return json.loads((DATA_DIR / "madina_district_vulnerability.json").read_text())


@lru_cache(maxsize=1)
def lower_volta_assembly_vulnerability() -> dict:
    """Same shape as madina_assembly_vulnerability(), for the Lower Volta
    region's 7 assemblies."""
    return json.loads((DATA_DIR / "lower_volta_district_vulnerability.json").read_text())


@lru_cache(maxsize=1)
def ayawaso_west_assembly_vulnerability() -> dict:
    """Ayawaso West Municipal has no independently-computed assembly-level
    vulnerability file (unlike Madina/Lower Volta) -- only its 156-cell
    ayawaso_west_risk_grid(). Derived here as the mean of those cells'
    score/water_occ_pct/impervious_pct, with level re-derived from the
    mean score via the same breakpoints _score_to_level() uses (the same
    formula, just aggregated now instead of at grid-build time) --
    labeled "derived", not claimed as independently computed, so a caller
    can treat it differently if that distinction matters."""
    g = ayawaso_west_risk_grid()
    score = round(float(g["score"].mean()), 1)
    return {
        "Ayawaso West Municipal": {
            "score": score, "level": _score_to_level(score),
            "water_occ_pct": round(float(g["water_occ_pct"].mean()), 2),
            "impervious_pct": round(float(g["impervious_pct"].mean()), 2),
            "derived": True,
            "note": "Derived as the mean of this assembly's 156 grid cells -- no independently "
                    "computed assembly-level figure exists for Ayawaso West the way it does for "
                    "Madina and Lower Volta.",
        }
    }


@lru_cache(maxsize=1)
def encroachment_index() -> dict:
    """OSM building-to-waterway distance per grid cell, keyed by bare
    zone_id -- same file as streamlit_app/data_loader.load_encroachment_index().
    Pilot grid only; see madina_channel_encroachment_index()/
    ayawaso_west_channel_encroachment_index()/
    lower_volta_channel_encroachment_index() for the extended-coverage
    equivalents."""
    return json.loads((DATA_DIR / "channel_encroachment_index.json").read_text())


@lru_cache(maxsize=1)
def madina_channel_encroachment_index() -> dict:
    """Same shape as encroachment_index(), for madina_risk_grid()'s cells."""
    return json.loads((DATA_DIR / "madina_channel_encroachment_index.json").read_text())


@lru_cache(maxsize=1)
def ayawaso_west_channel_encroachment_index() -> dict:
    """Same shape as encroachment_index(), for ayawaso_west_risk_grid()'s
    cells -- previously only read by streamlit_app/geo_tools.py's
    get_channel_encroachment_for_district(), filtered by assembly name,
    never joined to a specific point/zone lookup anywhere until now."""
    return json.loads((DATA_DIR / "ayawaso_west_channel_encroachment_index.json").read_text())


@lru_cache(maxsize=1)
def lower_volta_channel_encroachment_index() -> dict:
    """Same shape as encroachment_index(), for lower_volta_risk_grid()'s
    cells."""
    return json.loads((DATA_DIR / "lower_volta_channel_encroachment_index.json").read_text())


@lru_cache(maxsize=1)
def channel_encroachment_timeseries() -> dict:
    """Feature #8 (govt dashboard): risk_engine/channel_encroachment_timeseries.py's
    multi-year NDBI-near-channel trend, pilot grid only (272 of 1013
    cells sit near a mapped waterway at all; the rest are
    "no_waterway_nearby"). Never surfaced in any UI before -- this is
    the first reader. See that script's own docstring for why it tracks
    a continuous NDBI value rather than a binary built/not-built
    threshold (tried, didn't validate at any cutoff for this landscape),
    and why "trend" is a direction from a linear fit, not a forecast."""
    return json.loads((DATA_DIR / "channel_encroachment_timeseries.json").read_text())


# Thresholds on slope_per_year (NDBI units/year) for a 3-way trend
# label -- a judgment call on top of real per-cell linear-fit slopes
# (all 272 "ok" pilot cells have the full 8 requested years, 2019-2026,
# so this isn't fighting a thin-sample problem), NOT a validated
# ecological cutoff. Chosen from this project's own real distribution
# (272 cells: median slope -0.019, only 14 are positive at all) so
# "Worsening" isn't triggered by measurement noise around zero.
_ENCROACHMENT_WORSENING_SLOPE = 0.01
_ENCROACHMENT_IMPROVING_SLOPE = -0.01


# Confirmed, not hypothetical: cross-checked against historical_flood_events.json
# after the 5 steepest "Improving" cells (all in Weija Gbawe Municipal,
# spatially adjacent -- rows 12-15, cols 3-6, not independent samples)
# turned out to share one shape -- moderate-positive NDBI in 2019-2021,
# a sharp drop to strongly negative across 2022-2025, partial recovery
# in 2026 -- that lines up with WEIJA-DAM-FLOOD-2022-10-04 (the sharp
# 2022 drop), a partial 2020 dip matching WEIJA-DAM-FLOOD-2020-10-11,
# and continued depression in 2025 matching WEIJA-FLOOD-2025-05.
# Standing floodwater reads as strongly non-built-up in NDBI, same as
# any water body -- so "Improving" there most likely reflects recurring
# dam-release/storm flooding near the channel, not reduced construction.
# (2026 doesn't fit as cleanly despite two more documented Weija floods
# that year -- most likely the annual composite's cloud-free scenes
# just didn't land during either flood window; this doesn't overturn
# the match on the other four years.)
#
# CONFIRMED for these 5 cells specifically, not just plausible: re-fetched
# a single clean, low-cloud Sentinel-2 scene from a dry-season window far
# from each flood date (2022-02-10, 2025-02-04) instead of the annual
# median composite. Every cell's NDBI snapped back up to its 2019-2021
# baseline on that clean day (e.g. grid_r14_c3: 2025 composite -0.379 ->
# clean-day +0.180, at/above its own 2019 value of +0.169) -- the
# built-up signal near the channel is still there, just submerged on the
# days the annual composite happened to sample. Rules out the competing
# "floods discouraged construction, so there's genuinely less built-up
# area" explanation for these 5 cells: the clean-day signal is as strong
# or stronger than the pre-flood baseline, not reduced.
#
# Flagged generically below for any assembly/years combination with a
# documented flood, not hardcoded to Weija -- the same confound could
# apply anywhere this project has recurring flood history on record; only
# the 5 Weija cells above have been hand-verified against a clean-day
# scene, so elsewhere this is still "possible," not confirmed.
_FLOOD_HAZARD_TYPES = {"dam_release_flood", "urban_flood", "flash_flood", "river_flood"}


def _documented_flood_years(assembly: str | None, years: list[int]) -> list[int]:
    if not assembly:
        return []
    years_set = set(years)
    hit_years = set()
    for e in historical_events():
        if e.get("district") != assembly or e.get("hazard_type") not in _FLOOD_HAZARD_TYPES:
            continue
        date = e.get("date")
        if date and int(date[:4]) in years_set:
            hit_years.add(int(date[:4]))
    return sorted(hit_years)


def _encroachment_trend_direction(slope_per_year: float) -> str:
    if slope_per_year > _ENCROACHMENT_WORSENING_SLOPE:
        return "Worsening"
    if slope_per_year < _ENCROACHMENT_IMPROVING_SLOPE:
        return "Improving"
    return "Stable"


def _linear_slope(points: list[tuple[float, float]]) -> float | None:
    """Plain least-squares slope, no numpy -- this project's only other
    user of a per-cell linear fit is risk_engine/channel_encroachment_timeseries.py
    itself, which runs once offline; this is the one in-process fit."""
    n = len(points)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in points)
    den = sum((x - mean_x) ** 2 for x, _ in points)
    return num / den if den else None


# 2019 confirmed anomalous dataset-wide, not a per-cell quirk: across all
# 272 channel-adjacent cells, 2019 is the single highest NDBI year of the
# full 8-year series in 76.5% of them, and higher than 2020 in 87.1% --
# present in every one of the 7 assemblies (78.6%-100%), which rules out
# independent real construction-clearing (that wouldn't line up basin-
# wide in one calendar year). Checked and ruled out as the cause: the
# known Sentinel-2 baseline>=04.00 radiometric-offset bug (already
# correctly compensated in channel_encroachment_timeseries.py) and annual
# rainfall as a moisture confound (2019 wasn't the driest year on record
# for Accra -- 2020 and 2021 were drier yet read LOWER in NDBI, the
# opposite of what dry-soil-as-built-up would predict). Leading remaining
# hypothesis, unconfirmed: a scene-selection/seasonal skew specific to
# 2019's thinner early Sentinel-2 archive over Ghana -- not verifiable
# from this saved JSON, which only keeps a scene count per year, not
# dates. Refitting every cell's slope on 2020-2026 alone changes the
# Worsening/Stable/Improving label for 22.1% of all 272 cells (60 of
# them) -- a large enough swing that both slopes are surfaced below
# rather than trusting the 2019-inclusive one alone.
def encroachment_trend_cells(assembly: str | None = None) -> list[dict]:
    """Per-cell trend rows with a centroid attached (for mapping) --
    joined from risk_zones()'s geometry since the timeseries file itself
    only has zone_id/assembly, not geometry. Only cells with status "ok"
    AND a computable trend are returned (no waterway nearby, or no
    cloud-clear scenes at all, are both real outcomes, just not ones a
    trend chart can show)."""
    data = channel_encroachment_timeseries()
    geom_by_id = {z["id"].replace("RZ-", ""): z["geometry"] for z in risk_zones()}

    out = []
    for zone_id, z in data["zones"].items():
        if z["status"] != "ok" or z["trend"]["status"] != "ok":
            continue
        if assembly and z.get("assembly") != assembly:
            continue
        geom = geom_by_id.get(zone_id)
        if geom is None:
            continue
        centroid = shape(geom).centroid
        slope = z["trend"]["slope_per_year"]
        direction = _encroachment_trend_direction(slope)
        years_int = sorted(int(y) for y in z["years"])
        flood_years = _documented_flood_years(z.get("assembly"), years_int)

        points_excl_2019 = [
            (y, z["years"][str(y)]["mean_ndbi_near_channel"])
            for y in years_int if y != 2019 and z["years"][str(y)].get("mean_ndbi_near_channel") is not None
        ]
        slope_excl_2019 = _linear_slope(points_excl_2019)
        direction_excl_2019 = _encroachment_trend_direction(slope_excl_2019) if slope_excl_2019 is not None else None

        out.append({
            "zone_id": zone_id, "assembly": z.get("assembly"),
            "lon": centroid.x, "lat": centroid.y,
            "years": z["years"], "slope_per_year": slope, "n_years_used": z["trend"]["n_years_used"],
            "trend_note": z["trend"]["note"], "direction": direction,
            "slope_per_year_excl_2019": round(slope_excl_2019, 4) if slope_excl_2019 is not None else None,
            "direction_excl_2019": direction_excl_2019,
            "sensitive_to_2019": direction_excl_2019 is not None and direction_excl_2019 != direction,
            "documented_flood_years": flood_years,
            "possible_flood_contamination": direction == "Improving" and bool(flood_years),
        })
    return sorted(out, key=lambda r: r["slope_per_year"], reverse=True)


def encroachment_trend_by_assembly() -> list[dict]:
    """One row per assembly: how many of its channel-adjacent pilot
    cells are trending Worsening/Stable/Improving, plus the mean slope.
    Assemblies with zero channel-adjacent cells (no_waterway_nearby
    everywhere) are omitted, not shown as a false "0 worsening" row.
    n_possibly_flood_contaminated flags "Improving" cells in an
    assembly with documented flood history during the tracked years --
    see _documented_flood_years()'s comment for the confirmed Weija
    Gbawe case that prompted this. n_sensitive_to_2019 counts cells whose
    Worsening/Stable/Improving label flips once 2019 -- confirmed
    dataset-wide anomalous, see encroachment_trend_cells()'s comment --
    is dropped from the fit."""
    by_assembly: dict[str, dict] = {}
    for cell in encroachment_trend_cells():
        assembly = cell["assembly"] or "Unknown"
        row = by_assembly.setdefault(assembly, {
            "assembly": assembly, "n_cells_near_channel": 0,
            "n_worsening": 0, "n_stable": 0, "n_improving": 0,
            "n_possibly_flood_contaminated": 0, "n_sensitive_to_2019": 0, "_slopes": [],
        })
        row["n_cells_near_channel"] += 1
        row[f"n_{cell['direction'].lower()}"] += 1
        if cell["possible_flood_contamination"]:
            row["n_possibly_flood_contaminated"] += 1
        if cell["sensitive_to_2019"]:
            row["n_sensitive_to_2019"] += 1
        row["_slopes"].append(cell["slope_per_year"])

    out = []
    for row in by_assembly.values():
        slopes = row.pop("_slopes")
        row["mean_slope_per_year"] = round(sum(slopes) / len(slopes), 4)
        out.append(row)
    return sorted(out, key=lambda r: -r["n_worsening"])


@lru_cache(maxsize=1)
def emergency_facilities() -> dict:
    """Feature #4 (govt dashboard): real fire stations and hospitals from
    OSM Overpass (risk_engine/emergency_facilities.py, one-time fetch,
    same pattern as every other Overpass-sourced dataset here). Coverage
    checked before building on it, not assumed: 7 fire stations, 63
    hospitals in/near the pilot bbox; every one of the 7 pilot assemblies
    has a real fire station within ~0.6-4.6km of its centroid and at
    least one real hospital. NADMO offices, flood-response boats, and
    shelters are NOT in here -- not reliably mapped anywhere in Ghana
    OSM data, confirmed by checking rather than assumed; the resource
    allocation page keeps those as explicitly labeled fabricated demo
    data."""
    return json.loads((DATA_DIR / "emergency_facilities.json").read_text())


def nearest_facility(lat: float, lon: float, kind: str) -> dict | None:
    """Nearest real fire_station or hospital to one point, by straight-
    line distance (haversine_km -- same measure used for report
    clustering elsewhere in this project, good enough for "which real
    facility is closest," not a road-network ETA). kind must be
    "fire_stations" or "hospitals". None if that list is empty."""
    facilities = emergency_facilities().get(kind, [])
    if not facilities:
        return None
    best = min(facilities, key=lambda f: haversine_km(lat, lon, f["lat"], f["lon"]))
    return {**best, "distance_km": round(haversine_km(lat, lon, best["lat"], best["lon"]), 2)}


def _channel_encroachment_for_zone(zone_id: str, index: dict) -> dict | None:
    """The encroachment entry for one zone_id, reshaped to just the fields
    worth surfacing to a citizen (or Tide) -- dropped the raw building/
    waterway counts, kept score/level/min-distance. None when the cell
    has no entry or was 'insufficient_data' (too few OSM buildings/
    waterways mapped nearby to compute anything meaningful)."""
    entry = index.get(zone_id)
    if not entry or entry.get("status") != "ok":
        return None
    return {
        "score": entry["encroachment_score"],
        "level": entry["encroachment_level"],
        "min_building_to_waterway_m": entry["min_building_to_waterway_m"],
    }


# Curated, trimmed subset of streamlit_app/geo_tools.py's
# _DISTRICT_EVIDENCE_IMAGES (dropped the Lower Volta/South Tongu/etc.
# entries this backend doesn't cover, and the falsecolor variant of each
# site -- truecolor only, simpler for a citizen with no remote-sensing
# background). Applies to any assembly that has imagery, pilot or
# extended-coverage alike -- real evidence, no reason to withhold it from
# pilot zones just because this started as an extended-coverage gap.
_ASSEMBLY_EVIDENCE_IMAGES = {
    "Korle Klottey Municipal": [
        ("korle_klottey_christiansborg_s2_imagery.png", "Christiansborg"),
        ("korle_klottey_adabraka_s2_imagery.png", "Adabraka"),
    ],
    "La-Nkwantanang-Madina Municipal": [
        ("madina_zongo_s2_imagery.png", "Madina Zongo"),
    ],
    "Ablekuma Central Municipal": [
        ("ablekuma_central_korlebu_s2_imagery.png", "Korle Bu"),
        ("ablekuma_central_kaneshie_s2_imagery.png", "Kaneshie"),
    ],
    "Ablekuma North Municipal": [
        ("ablekuma_north_s2_imagery.png", "Ablekuma North"),
        ("alajo_s2_imagery.png", "Alajo"),
    ],
    "Weija Gbawe Municipal": [
        ("weija_tetegu_truecolor.png", "Tetegu"),
    ],
    "Ayawaso West Municipal": [
        ("ayawaso_west_encroachment_truecolor.png", "Ayawaso West encroachment site"),
    ],
    # Generated via risk_engine/pilot_sites_s2_truecolor.py -- the 3
    # pilot assemblies that had a confirmed "Very High" encroachment
    # score (channel_encroachment_index.json) but no satellite image
    # until now, closing that gap for full parity across all 7 pilot +
    # 2 extended-coverage assemblies.
    "Ablekuma West Municipal": [
        ("ablekuma_west_gbegbeyise_truecolor.png", "Gbegbeyise"),
    ],
    "Accra Metropolis": [
        ("accra_metropolis_old_fadama_truecolor.png", "Old Fadama"),
    ],
    "Ayawaso Central Municipal": [
        ("ayawaso_central_kokomlemle_truecolor.png", "Kokomlemle"),
    ],
    # Generated via risk_engine/lower_volta_s2_truecolor.py -- closing the
    # same satellite-evidence gap for all 7 Lower Volta extended-coverage
    # assemblies, each a confirmed "Very High" or "High" encroachment site.
    "Asuogyaman": [
        ("asuogyaman_akosombo_truecolor.png", "Akosombo"),
    ],
    "Lower Manya": [
        ("lower_manya_akuse_truecolor.png", "Akuse"),
    ],
    "North Tongu": [
        ("north_tongu_juapong_truecolor.png", "Juapong"),
    ],
    "South Tongu": [
        ("south_tongu_sokpoe_truecolor.png", "Sokpoe"),
    ],
    "Ada East": [
        ("ada_east_bigada_truecolor.png", "Big Ada"),
    ],
    "Ada West": [
        ("ada_west_matsekope_truecolor.png", "Matsekope"),
    ],
    "Central Tongu": [
        ("central_tongu_adidome_truecolor.png", "Adidome"),
    ],
}


def _satellite_evidence_for_assembly(assembly: str) -> list[dict]:
    """Real Sentinel-2 true-color imagery of a KNOWN hotspot site in this
    assembly -- NOT the citizen's exact searched location, a fixed
    reference image (see main.py's /evidence static mount). Only returns
    entries whose file actually exists on this checkout, same discipline
    as streamlit_app/geo_tools.py's get_satellite_evidence_paths_for_district."""
    out = []
    for filename, caption in _ASSEMBLY_EVIDENCE_IMAGES.get(assembly, []):
        if (DATA_DIR / "evidence" / filename).exists():
            out.append({"caption": caption, "url": f"/evidence/{filename}"})
    return out


@lru_cache(maxsize=1)
def population_exposure() -> dict:
    """Pilot-wide estimated population/building counts per grid cell --
    same file as streamlit_app/data_loader's equivalent read in
    geo_tools.get_population_exposure_summary()."""
    return json.loads((DATA_DIR / "population_exposure.json").read_text())


@lru_cache(maxsize=1)
def madina_risk_grid() -> gpd.GeoDataFrame:
    """318-cell fine grid over La-Nkwantanang-Madina Municipal -- same
    file streamlit_app/data_loader.load_madina_risk_grid_gdf() reads."""
    return gpd.read_file(DATA_DIR / "madina_risk_grid.geojson")


@lru_cache(maxsize=1)
def ayawaso_west_risk_grid() -> gpd.GeoDataFrame:
    """156-cell fine grid over Ayawaso West Municipal (covers East Legon).
    Same file shape as madina_risk_grid() (zone_id/assembly/score/level/
    geometry), but unlike Madina's, nothing anywhere in this project --
    citizen backend or officer Streamlit app -- had a point-lookup
    function reading it before this; only get_channel_encroachment_for_district()
    read it, filtered by exact assembly-name match, not by point."""
    return gpd.read_file(DATA_DIR / "ayawaso_west_risk_grid.geojson")


@lru_cache(maxsize=1)
def lower_volta_risk_grid() -> gpd.GeoDataFrame:
    """16,941-cell grid over the Lower Volta extended-coverage region (Ada
    East/West, South/North/Central Tongu, Lower Manya, Asuogyaman) -- the
    2023 Akosombo dam-spillage flood corridor. Same schema as
    madina_risk_grid()/ayawaso_west_risk_grid(); unlike those two, this
    region is geographically far from the pilot area and from each other,
    so there's no shared-border ambiguity needing a boundary polygon to
    decide which grid to check first -- see zone_info_for_point()/
    assign_district()."""
    return gpd.read_file(DATA_DIR / "lower_volta_risk_grid.geojson")


@lru_cache(maxsize=1)
def _ayawaso_west_boundary():
    """Ayawaso West Municipal's real administrative boundary, from
    extended_district_assemblies.geojson (11 districts, pilot + extended;
    only this one row is used here). NOT the same thing as
    ayawaso_west_risk_grid()'s own cell geometries: those are a 500m grid
    tiled over a buffered bounding box, so edge cells spill past the true
    municipal line -- confirmed empirically (3/318 of Madina's own grid
    cells' centroids fall inside this precise Ayawaso West boundary, and
    23/156 of Ayawaso West's own grid cells' centroids fall OUTSIDE it).
    Checking this real boundary first, before trying either fine grid,
    resolves which region actually owns a point in that overlap zone --
    checking the two fine grids directly in some arbitrary order (tried
    first, caught by testing against real data before relying on it)
    silently mislabeled points there depending on which grid happened to
    be checked first."""
    gdf = gpd.read_file(DATA_DIR / "extended_district_assemblies.geojson")
    return gdf[gdf["name"] == "Ayawaso West Municipal"].geometry.iloc[0]


# madina_risk_grid.geojson and ayawaso_west_risk_grid.geojson are both
# buffered-bbox tilings whose edge cells can spill past the true
# municipal line -- same failure mode _ayawaso_west_boundary() already
# documents for the overlap BETWEEN these two grids, confirmed here to
# also happen on their OUTER edges, into districts we don't cover at
# all. Found when a citizen correctly pointed out that real Adenta
# (Adentan Municipal District) coordinates were coming back labeled
# "La-Nkwantanang-Madina Municipal." Sampling both grids afterward turned
# up spillover into at least three different neighboring districts
# (Adentan, Ga East, Ledzokuku) -- a blocklist of known-wrong neighbor
# names would have to keep growing forever to stay ahead of this, so
# instead of that, _confirm_extended_assembly() POSITIVELY checks that a
# live reverse-geocode actually agrees with what the grid cell claims,
# rejecting the match otherwise -- generalizes to any such spillover,
# named or not, without having to enumerate every neighboring district
# by hand. No Adentan/Ga East/Ledzokuku boundary polygon exists anywhere
# in this project's data (extended_district_assemblies.geojson's 11 rows
# don't include any of them, or La-Nkwantanang-Madina either), so there's
# nothing to check against locally the way Ayawaso West's own real
# boundary works -- this is why it's a live cross-check, not a second
# local polygon. lower_volta_risk_grid.geojson is the same buffered-bbox
# tiling (it even carries its own boundary_overlap_frac column, unused
# here, as a hint that its own edge cells have the same issue), so its 7
# assemblies get the same treatment rather than waiting for a citizen to
# find the spillover first.
_ASSEMBLY_CONFIRMATION_TERMS = {
    "La-Nkwantanang-Madina Municipal": "madina",
    "Ayawaso West Municipal": "ayawaso west",
    "Ada East": "ada east",
    "Ada West": "ada west",
    "South Tongu": "south tongu",
    "North Tongu": "north tongu",
    "Central Tongu": "central tongu",
    "Lower Manya": "lower manya",
    "Asuogyaman": "asuogyaman",
}


def _confirm_extended_assembly(lon: float, lat: float, claimed_assembly: str) -> bool:
    """True if a live Nominatim reverse-geocode of (lon, lat) corroborates
    the extended-coverage grid's claimed assembly for this point. Fails
    OPEN (returns True, i.e. trusts the grid) on any network error or an
    empty/unparseable reverse-geocode result, and also if no confirmation
    term is registered for this assembly -- this is a safety net that
    rejects a KNOWN-WRONG match, not a strict allowlist that would start
    rejecting genuinely fine matches over a network hiccup."""
    term = _ASSEMBLY_CONFIRMATION_TERMS.get(claimed_assembly)
    if not term:
        return True
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "ThirdWave-backend/1.0"},
            timeout=5,
        )
        display_name = (resp.json().get("display_name") or "").lower()
    except Exception:
        return True
    if not display_name:
        return True
    return term in display_name


def assign_district(lon: float, lat: float) -> str | None:
    """Point-in-polygon against the 7 pilot assemblies, falling back to
    the Ayawaso West, Madina, and Lower Volta extended-coverage grids so a
    report submitted from East Legon, Madina, or the Lower Volta region
    gets tagged with its real district instead of silently None.

    Which of Ayawaso West/Madina to check is decided by
    _ayawaso_west_boundary() (the real admin line), not by trying both
    grids in some fixed order -- see that function's docstring for why
    (their buffered grid extents genuinely overlap near the shared
    border). Lower Volta is geographically far from both, so it's just a
    third fallback if neither of those two matched. A tentative hit is
    then rejected if _confirm_extended_assembly() can't corroborate it
    against a live reverse-geocode of the same point."""
    pt = Point(lon, lat)
    for _, row in assembly_geometries().iterrows():
        if row.geometry.contains(pt):
            return row["name"]
    gdf = ayawaso_west_risk_grid() if _ayawaso_west_boundary().contains(pt) else madina_risk_grid()
    hits = gdf[gdf.contains(pt)]
    if hits.empty:
        lv = lower_volta_risk_grid()
        hits = lv[lv.contains(pt)]
    if hits.empty:
        return None
    assembly = hits.iloc[0]["assembly"]
    if not _confirm_extended_assembly(lon, lat, assembly):
        return None
    return assembly


def zone_for_point(lon: float, lat: float) -> dict | None:
    """The fine-grained RiskZone containing this point, if any, falling
    back to the Ayawaso West/Madina/Lower Volta extended-coverage grids
    (tagged extended: True) the same way zone_info_for_point() does --
    same source and lookup as incident_store.zone_for_point(), extended
    to all three regions instead of just Lower Volta since this backend's
    geo_data.py already has Ayawaso West/Madina fine grids incident_store.py
    doesn't. Used by serializers.serialize_report() so a report submitted
    from any covered region -- not just the pilot district -- gets a real
    verification-context score instead of being silently reported as
    "outside all scored coverage.\""""
    pt = Point(lon, lat)
    for z in risk_zones():
        if shape(z["geometry"]).contains(pt):
            return z

    if _ayawaso_west_boundary().contains(pt):
        extended = _find_zone_in_grid(ayawaso_west_risk_grid(), lon, lat, _AYAWASO_WEST_COVERAGE_NOTE)
    else:
        extended = _find_zone_in_grid(madina_risk_grid(), lon, lat, _MADINA_COVERAGE_NOTE)
    if extended and not _confirm_extended_assembly(lon, lat, extended["assembly"]):
        extended = None
    if not extended:
        extended = _find_zone_in_grid(lower_volta_risk_grid(), lon, lat, _LOWER_VOLTA_COVERAGE_NOTE)
        if extended and not _confirm_extended_assembly(lon, lat, extended["assembly"]):
            extended = None
    if not extended or "score" not in extended:
        return None
    return {
        "id": extended["zone_id"], "score": extended["score"], "level": extended["level"],
        "assembly": extended["assembly"], "extended": True,
    }


# Adapted from streamlit_app/geo_tools.py's _find_zone_in_madina() note,
# rewritten to lead with a plain-language sentence a non-technical
# citizen can follow, introducing the more precise/technical framing
# afterward -- not field names like "channel_encroachment" or
# "contributing_factors", which are API shape, not something a citizen
# reading this on My Zone/Alert should ever see verbatim.
_MADINA_COVERAGE_NOTE = (
    "Madina is outside the main pilot area this app studies in full detail, so this score comes from a "
    "simpler, lower-detail check and may be less accurate than a pilot-area score. At this area's "
    "worst-known flooding spot (Madina Zongo), nearby buildings sit very close to a drainage channel -- a "
    "real risk that this score alone doesn't capture, even though the score itself reads \"Low.\" Don't "
    "treat a Low or Moderate score here as reassuring on its own -- also check the flood history below."
)
_AYAWASO_WEST_COVERAGE_NOTE = (
    "East Legon (Ayawaso West Municipal) is outside the main pilot area this app studies in full detail, "
    "so this score comes from a simpler, lower-detail check and may be less accurate than a pilot-area "
    "score. Treat it as a rough first read, not the same level of evidence as a pilot-area score."
)
_LOWER_VOLTA_COVERAGE_NOTE = (
    "This area is outside the main pilot area this app studies in full detail, so this score comes from a "
    "simpler, lower-detail check and may be less accurate than a pilot-area score. This stretch of the "
    "Lower Volta has a real history of flooding when water is released from the Akosombo Dam upstream -- "
    "a risk a satellite/terrain-based score like this one can't fully capture, so also check the flood "
    "history below."
)

# Curated, not fuzzy-matched against arbitrary resolved-address text: a
# historical event's location_name can explicitly name an area ("also
# affected ... East Legon") while its own stored lat/lon anchors at one
# pinpoint far away (a regional event spanning many communities) -- so
# nearby_historical_events()'s plain radius join misses it. Only these two
# extended regions have aliases for now, matching what's actually been
# asked for; the same gap exists for some pilot assemblies too (e.g.
# "Alajo" named in a Circle-anchored event 4.24km away) and could be
# extended here the same way.
_ASSEMBLY_NAME_ALIASES = {
    "Ayawaso West Municipal": ["East Legon"],
    "La-Nkwantanang-Madina Municipal": ["Madina"],
}


def _regionally_named_events(assembly: str, exclude: list[dict]) -> list[dict]:
    """Historical events whose location_name text names this assembly's
    area, but that aren't already in `exclude` (the precise radius-based
    nearby_historical_events() list) -- deduped by (name, date) so an
    event that happens to match both ways isn't listed twice."""
    aliases = _ASSEMBLY_NAME_ALIASES.get(assembly, [])
    if not aliases:
        return []
    already = {(e["name"], e["date"]) for e in exclude}
    out = []
    for e in historical_events():
        if (e["name"], e["date"]) in already:
            continue
        loc = e.get("location_name", "")
        if any(alias in loc for alias in aliases):
            out.append({
                "date": e["date"], "name": e["name"], "hazard_type": e.get("hazard_type"),
                "deaths": e.get("deaths"), "cause": e.get("cause"), "location_name": loc,
            })
    return out


def _find_zone_in_grid(gdf, lon: float, lat: float, coverage_note: str) -> dict | None:
    """Shared point-in-polygon lookup for the extended-coverage grids
    (Madina, Ayawaso West) -- both have identical schema and mechanics to
    streamlit_app/geo_tools.py's _find_zone_in_madina(), only the
    coverage_note text differs per region, so it's written once here."""
    pt = Point(lon, lat)
    hits = gdf[gdf.contains(pt)]
    if hits.empty:
        return None
    row = hits.iloc[0]
    out = {"zone_id": row["zone_id"], "assembly": row["assembly"], "coverage_note": coverage_note}
    if row.get("score") is not None:
        out["score"] = round(float(row["score"]), 1)
        out["level"] = row["level"]
    return out


def _score_hit_historical_note(events: list[dict], regional_events: list[dict] | None = None) -> str:
    """historical_context_note wording for a zone that DID resolve to a
    computed score -- pilot or extended-coverage, identical either way.
    regional_events (see _regionally_named_events()) are events named in
    this area's wider narrative without a precise nearby coordinate --
    mentioned separately so they're never conflated with the radius-based
    `events` count."""
    if events:
        note = (
            f"{len(events)} documented flood event(s) happened within {HISTORICAL_EVENT_RADIUS_KM:.0f}km of "
            "here -- worth weighing alongside the score above, since the score is based on satellite and "
            "terrain data and can miss some real risks, like flooding caused by releasing water from a dam."
        )
    else:
        note = (
            f"No documented flood events within {HISTORICAL_EVENT_RADIUS_KM:.0f}km in our records -- but "
            "that doesn't necessarily mean this area is safe, just that nothing has been recorded here yet."
        )
    if regional_events:
        note += (
            f" Separately, {len(regional_events)} past flood report(s) mention this general area by name, "
            "even though their exact location was recorded somewhere else nearby -- see below."
        )
    return note


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


def geocode_address(address: str) -> dict:
    """Geocode with the same two-step fallback find_zone_by_address uses
    -- "{address}, Accra, Ghana" can fail outright for a location the
    region hint doesn't fit, not just mis-resolve, so retry broadly
    ("Ghana") before giving up. Factored out so other callers (e.g. the
    citizen reporting flow's address search) get the same fallback
    without re-implementing it."""
    result = _geocode(address)
    if not result:
        result = _geocode(address, region_hint="Ghana")
        if not result:
            return {"error": f"Could not geocode '{address}'."}
    lat, lon, label = result
    return {"lat": lat, "lon": lon, "resolved_address": label}


@lru_cache(maxsize=1)
def _known_landmarks() -> list[str]:
    """Seed list for suggest_places()'s local/instant match -- assembled
    from dicts this backend already has (assembly_scores()'s 7 pilot
    names, _ASSEMBLY_NAME_ALIASES'/_ASSEMBLY_EVIDENCE_IMAGES' keys/values)
    rather than retyped by hand, so it can't silently drift out of sync
    with them, plus a short hand-picked list of well-known Accra
    neighborhoods within/near the covered area. This is a SEED list, not
    a rigorous mining of historical_flood_events.json's messy narrative
    location_name strings -- honestly incomplete, meant to grow over
    time, not a one-shot comprehensive solution."""
    names: set[str] = {z["assembly"] for z in assembly_scores()}
    names |= set(_ASSEMBLY_EVIDENCE_IMAGES.keys())
    names |= set(_ASSEMBLY_NAME_ALIASES.keys())
    for aliases in _ASSEMBLY_NAME_ALIASES.values():
        names.update(aliases)
    for images in _ASSEMBLY_EVIDENCE_IMAGES.values():
        for _filename, caption in images:
            if "encroachment site" not in caption:  # a description, not a place
                names.add(caption)
    names |= {
        "Kwame Nkrumah Circle", "Osu", "Dansoman", "Mallam", "Lapaz", "Abeka",
        "Achimota", "Oblogo", "Ashongman Estates", "Pantang", "Tse Addo",
        "Ofankor", "Kokomlemle", "Bubuashie", "North Kaneshie",
    }
    # Lower Volta extended-coverage region (_ASSEMBLY_CONFIRMATION_TERMS'
    # 7 assembly names, plus a few of its well-known towns).
    names |= {
        "Ada East", "Ada West", "South Tongu", "North Tongu", "Central Tongu",
        "Lower Manya", "Asuogyaman", "Sogakope", "Adafoah", "Akuse", "Juapong", "Kpetoe",
    }
    return sorted(names)


@lru_cache(maxsize=256)
def _nominatim_suggestions(query: str, limit: int) -> list[dict]:
    """Up to `limit` live candidates -- countrycodes=gh biases to Ghana,
    a refinement _geocode() itself doesn't have (deliberately not
    retrofitted there, see suggest_places()'s docstring). Cached so
    retyping/backspacing back to an already-seen query doesn't re-hit
    Nominatim; exceptions swallowed to [] since suggestions are a nicety,
    never the critical path a citizen's search depends on."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{query}, Accra, Ghana", "format": "json", "limit": limit, "countrycodes": "gh"},
            headers={"User-Agent": "ThirdWave-backend/1.0"},
            timeout=5,
        )
        return [
            {"label": r.get("display_name", query), "lat": float(r["lat"]), "lon": float(r["lon"]), "source": "nominatim"}
            for r in resp.json()
        ]
    except Exception:
        return []


def suggest_places(query: str, limit: int = 8) -> list[dict]:
    """Local curated matches first (instant, no network), falling back to
    live Nominatim candidates only if the curated list didn't return
    enough. Meant to be called debounced from the client (GET
    /geocode/suggest) -- the throttling that actually matters (never
    firing on every keystroke, respecting Nominatim's usage policy)
    happens client-side; this function itself is just "given a query,
    answer once," not a rate limiter."""
    q = query.strip()
    if len(q) < 2:
        return []
    local = [{"label": name, "source": "local"} for name in _known_landmarks() if q.lower() in name.lower()][:limit]
    if len(local) >= limit or len(q) < 3:
        return local
    return local + _nominatim_suggestions(q, limit - len(local))


def zone_info_for_point(lon: float, lat: float, label: str | None = None) -> dict:
    """Shared by find_zone_by_address() (address-in) and
    zone_info_by_point() (coordinates-in, e.g. from a GPS fix with no
    address text at all -- feature #4's "use my location" path, which
    find_zone_by_address() can't serve since it requires an address to
    geocode). Same score+historical-events join either way.

    Echoes lon/lat back in the result (added for feature #7, My Zone's
    nearby-citizen-reports join and inline map) -- the router needs them
    to run report_queries.verified_reports_near() and to center a map,
    and this is the one place both call paths (address and point) already
    have them in scope, so neither router has to re-geocode or thread
    them through separately.

    Falls back to the Ayawaso West (East Legon), Madina, and Lower Volta
    extended-coverage grids when the pilot grid misses, before giving up
    -- see _find_zone_in_grid()/the module docstring. Which of Ayawaso
    West/Madina to try first is decided by _ayawaso_west_boundary() (the
    real admin line), NOT by trying both fine grids in some order --
    their buffered bounding boxes genuinely overlap near their shared
    border, so order-based checking silently mislabels points there
    (confirmed empirically, see _ayawaso_west_boundary()'s docstring).
    Lower Volta is geographically far from both, so it's just a third
    fallback tried if neither of those two matched."""
    events = nearby_historical_events(lat, lon)
    zone = zone_for_point(lon, lat)

    if zone:
        zone_id = zone["id"].replace("RZ-", "")
        out = {
            "resolved_address": label, "lon": lon, "lat": lat, "zone_id": zone_id,
            "assembly": zone["assembly"], "score": zone["score"], "level": zone["level"],
            "confidence": zone["confidence"],
            "contributing_factors": [f["text"] for f in zone["contributing_factors"]],
            "nearby_historical_events": events,
        }
        encroachment = _channel_encroachment_for_zone(zone_id, encroachment_index())
        if encroachment:
            out["channel_encroachment"] = encroachment
        regional = _regionally_named_events(zone["assembly"], exclude=events)
        if regional:
            out["regionally_named_historical_events"] = regional
        evidence = _satellite_evidence_for_assembly(zone["assembly"])
        if evidence:
            out["satellite_evidence"] = evidence
        out["historical_context_note"] = _score_hit_historical_note(events, regional)
        return out

    if _ayawaso_west_boundary().contains(Point(lon, lat)):
        extended = _find_zone_in_grid(ayawaso_west_risk_grid(), lon, lat, _AYAWASO_WEST_COVERAGE_NOTE)
        encroachment_idx = ayawaso_west_channel_encroachment_index()
    else:
        extended = _find_zone_in_grid(madina_risk_grid(), lon, lat, _MADINA_COVERAGE_NOTE)
        encroachment_idx = madina_channel_encroachment_index()
    if extended and not _confirm_extended_assembly(lon, lat, extended["assembly"]):
        extended = None
    if not extended:
        extended = _find_zone_in_grid(lower_volta_risk_grid(), lon, lat, _LOWER_VOLTA_COVERAGE_NOTE)
        encroachment_idx = lower_volta_channel_encroachment_index()
        if extended and not _confirm_extended_assembly(lon, lat, extended["assembly"]):
            extended = None
    if extended:
        out = {"resolved_address": label, "lon": lon, "lat": lat, "nearby_historical_events": events, **extended}
        encroachment = _channel_encroachment_for_zone(extended["zone_id"], encroachment_idx)
        if encroachment:
            out["channel_encroachment"] = encroachment
        regional = _regionally_named_events(extended["assembly"], exclude=events)
        if regional:
            out["regionally_named_historical_events"] = regional
        evidence = _satellite_evidence_for_assembly(extended["assembly"])
        if evidence:
            out["satellite_evidence"] = evidence
        out["historical_context_note"] = _score_hit_historical_note(events, regional)
        return out

    out = {"resolved_address": label, "lon": lon, "lat": lat, "error": "This location is outside the pilot district's coverage area."}
    if events:
        out["nearby_historical_events"] = events
        out["historical_context_note"] = (
            f"No computed score available (outside pilot coverage), but {len(events)} documented flood "
            "event(s) exist within range."
        )
    return out


def find_zone_by_address(address: str) -> dict:
    """Ported from streamlit_app/geo_tools.py's function of the same name,
    simplified: it just geocodes and delegates to zone_info_for_point(),
    which already carries the Ayawaso West/Madina/Lower Volta extended-
    coverage fallback (Streamlit's own version duplicates that fallback
    chain inline instead, since it has no separate by-point entry
    function)."""
    geocoded = geocode_address(address)
    if "error" in geocoded:
        return geocoded
    lat, lon, label = geocoded["lat"], geocoded["lon"], geocoded["resolved_address"]
    return zone_info_for_point(lon, lat, label)
