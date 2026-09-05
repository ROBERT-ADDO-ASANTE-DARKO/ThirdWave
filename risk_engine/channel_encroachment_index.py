"""
channel_encroachment_index.py — Building-to-waterway encroachment distance
per pilot grid cell, computed from free OSM vector data (Overpass API).

Complements (does not replace) the SAR/DEM/LULC vulnerability score:
SAR tells us a cell has elevated water occurrence (statistical, multi-year);
this tells us WHY, where free data supports it -- how close the nearest
building sits to a mapped river/drain, a real proxy for drainage-channel
encroachment (the mechanism directly observed at Kwame Nkrumah Circle: 2.0m
minimum building-to-channel distance, confirmed both visually in
circle_z18_stitched.jpg and numerically here).

Reported alongside the score, not blended into it -- same discipline as
LULC and the Sentinel-2 cross-validation earlier in this project: report
what free data supports, flag plainly where it doesn't (OSM coverage is
uneven -- Ablekuma West has good building coverage but almost no mapped
waterways, so this metric will be marked insufficient_data there).

Usage
─────
    python3 channel_encroachment_index.py
    python3 channel_encroachment_index.py --grid data/pilot_risk_grid.geojson
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import requests
from shapely.geometry import shape, LineString, Polygon
from shapely.ops import unary_union

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
DEFAULT_GRID = HERE / "data" / "pilot_risk_grid.geojson"
OUTPUT = HERE / "data" / "channel_encroachment_index.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEG_TO_M = 111_000

# Minimum number of buildings AND at least one waterway feature required
# before trusting a cell's encroachment number -- below this, OSM coverage
# is too thin to compute anything meaningful (mirrors the Ablekuma West
# finding: 473 buildings but only 1 unnamed waterway isn't enough).
MIN_BUILDINGS = 5
MIN_WATERWAYS = 1

# Cell-level distance bands for the encroachment index (0-100, higher = more
# encroached), derived from the Circle finding (min 2.0m, several buildings
# within 10-20m) as the high end of the scale.
BAND_VERY_CLOSE_M = 10
BAND_CLOSE_M = 30
BAND_MODERATE_M = 75


def query_overpass(bbox: tuple[float, float, float, float], retries: int = 3) -> dict:
    minlon, minlat, maxlon, maxlat = bbox
    query = f"""
    [out:json][timeout:30];
    (
      way["waterway"]({minlat},{minlon},{maxlat},{maxlon});
      way["building"]({minlat},{minlon},{maxlat},{maxlon});
    );
    out geom;
    """
    headers = {"User-Agent": "ThirdWave-risk-engine/1.0 (research prototype)"}
    for attempt in range(retries):
        try:
            resp = requests.post(OVERPASS_URL, data=query, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("Overpass query failed (attempt %d/%d): %s", attempt + 1, retries, exc)
            time.sleep(2 * (attempt + 1))
    return {"elements": []}


def encroachment_score(min_dist_m: float) -> tuple[float, str]:
    if min_dist_m <= BAND_VERY_CLOSE_M:
        return 100.0, "Very High"
    if min_dist_m <= BAND_CLOSE_M:
        return 70.0, "High"
    if min_dist_m <= BAND_MODERATE_M:
        return 40.0, "Moderate"
    return 10.0, "Low"


def run(grid_path: Path):
    grid = json.loads(grid_path.read_text())
    log.info("Computing channel encroachment index for %d cells (grid: %s)", len(grid["features"]), grid_path.name)

    # One bulk Overpass fetch for the whole pilot boundary, then a local
    # spatial join per cell -- 319 individual queries against a public,
    # rate-limited instance would be slow and inconsiderate; this is one
    # request instead.
    all_bounds = [shape(f["geometry"]).bounds for f in grid["features"]]
    minlon = min(b[0] for b in all_bounds) - 0.001
    minlat = min(b[1] for b in all_bounds) - 0.001
    maxlon = max(b[2] for b in all_bounds) + 0.001
    maxlat = max(b[3] for b in all_bounds) + 0.001
    log.info("Bulk-fetching OSM buildings/waterways for the whole pilot extent: (%.4f,%.4f,%.4f,%.4f)",
             minlon, minlat, maxlon, maxlat)

    data = query_overpass((minlon, minlat, maxlon, maxlat))
    elements = data.get("elements", [])

    all_waterways = []
    for e in elements:
        tags = e.get("tags", {})
        if tags.get("waterway") and e.get("geometry"):
            coords = [(pt["lon"], pt["lat"]) for pt in e["geometry"]]
            if len(coords) >= 2:
                all_waterways.append(LineString(coords))

    all_buildings = []
    for e in elements:
        tags = e.get("tags", {})
        if tags.get("building") and e.get("geometry"):
            coords = [(pt["lon"], pt["lat"]) for pt in e["geometry"]]
            if len(coords) >= 3:
                all_buildings.append(Polygon(coords))

    log.info("Pilot-wide: %d buildings, %d waterway features fetched", len(all_buildings), len(all_waterways))

    from shapely.strtree import STRtree  # Shapely 2.x STRtree is native (GEOS-backed), no external rtree package needed
    building_tree = STRtree(all_buildings) if all_buildings else None
    waterway_union_all = unary_union(all_waterways) if all_waterways else None

    results = {}
    for i, f in enumerate(grid["features"]):
        zone_id = f["properties"]["zone_id"]
        cell_geom = shape(f["geometry"])
        bounds = cell_geom.bounds
        pad = 0.001  # ~110m context padding so channel data at the cell edge isn't missed
        query_box = Polygon.from_bounds(bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad)

        if building_tree is None:
            results[zone_id] = {"status": "insufficient_data", "n_buildings": 0, "n_waterways": len(all_waterways),
                                 "note": "No buildings in pilot-wide OSM fetch."}
            continue

        candidate_idx = building_tree.query(query_box)
        buildings_here = [all_buildings[j] for j in candidate_idx if all_buildings[j].intersects(query_box)]
        waterways_here = [w for w in all_waterways if w.intersects(query_box)]

        if len(buildings_here) < MIN_BUILDINGS or len(waterways_here) < MIN_WATERWAYS:
            results[zone_id] = {
                "status": "insufficient_data", "n_buildings": len(buildings_here), "n_waterways": len(waterways_here),
                "note": f"Below coverage threshold (need >={MIN_BUILDINGS} buildings and >={MIN_WATERWAYS} waterway, "
                        f"got {len(buildings_here)} buildings and {len(waterways_here)} waterways).",
            }
            continue

        local_waterway_union = unary_union(waterways_here)
        dists_m = sorted(b.distance(local_waterway_union) * DEG_TO_M for b in buildings_here)
        min_dist = dists_m[0]
        median_dist = dists_m[len(dists_m) // 2]
        n_within_20m = sum(1 for d in dists_m if d <= 20)
        score, level = encroachment_score(min_dist)

        results[zone_id] = {
            "status": "ok", "n_buildings": len(buildings_here), "n_waterways": len(waterways_here),
            "min_building_to_waterway_m": round(min_dist, 1), "median_building_to_waterway_m": round(median_dist, 1),
            "n_buildings_within_20m": n_within_20m, "encroachment_score": score, "encroachment_level": level,
        }

        if (i + 1) % 50 == 0:
            log.info("  ... %d/%d cells done", i + 1, len(grid["features"]))

    n_ok = sum(1 for r in results.values() if r["status"] == "ok")
    n_insufficient = len(results) - n_ok
    log.info("Done: %d cells with a computable index, %d flagged insufficient_data", n_ok, n_insufficient)

    if n_ok:
        top = sorted(
            [(zid, r) for zid, r in results.items() if r["status"] == "ok"],
            key=lambda x: x[1]["min_building_to_waterway_m"],
        )[:5]
        log.info("Most encroached cells (closest building to a mapped waterway):")
        for zid, r in top:
            log.info("  %-16s min=%.1fm  level=%s  (%d buildings, %d waterways)",
                     zid, r["min_building_to_waterway_m"], r["encroachment_level"], r["n_buildings"], r["n_waterways"])

    OUTPUT.write_text(json.dumps(results, indent=2))
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    args = parser.parse_args()
    run(args.grid)
