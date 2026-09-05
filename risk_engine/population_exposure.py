"""
population_exposure.py — Estimated population + building count exposed per
RiskZone grid cell, for the "Population / Infrastructure Exposure"
Streamlit feature.

Population: WorldPop Ghana 2020, unconstrained, 100m gridded population
count (data.worldpop.org, free, no key -- id 6365 via hub.worldpop.org REST
API). Downloaded once to /tmp, zonal-summed per cell, NOT shipped with the
app (120MB raster; the Streamlit app loads only this script's small JSON
output).

Infrastructure: building count per cell, already computed in
channel_encroachment_index.py (n_buildings, present for all 319 cells
regardless of whether the waterway-distance metric could be computed).

Usage
─────
    python3 population_exposure.py
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import rasterio
import rasterio.mask
import requests
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
POP_RASTER = Path("/tmp/worldpop/gha_ppp_2020.tif")
OUTPUT = HERE / "data" / "population_exposure.json"

SOURCE_NOTE = ("WorldPop Ghana 2020, unconstrained 100m gridded population count "
               "(data.worldpop.org, id 6365). Each pixel is an estimated person-count, "
               "summed per zone -- not a census, a model-based estimate. Building counts "
               "here are a CLEAN centroid-based assignment (one cell per building, no "
               "double-counting) -- deliberately different from "
               "channel_encroachment_index.py's n_buildings, which uses a padded/overlapping "
               "bbox appropriate for its own distance-to-waterway calculation but wrong for "
               "a district-wide infrastructure total (summing it double-counts buildings near "
               "cell edges: 228,330 vs. 123,944 unique buildings in the same area -- caught "
               "and fixed here, not shipped).")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def fetch_buildings_clean(grid_features) -> list:
    """Single bulk Overpass fetch for the whole grid extent, independent of
    channel_encroachment_index.py's own fetch (that script doesn't persist
    its raw building list, only its already-padded per-cell counts)."""
    bounds = [shape(f["geometry"]).bounds for f in grid_features]
    minlon = min(b[0] for b in bounds) - 0.001
    minlat = min(b[1] for b in bounds) - 0.001
    maxlon = max(b[2] for b in bounds) + 0.001
    maxlat = max(b[3] for b in bounds) + 0.001

    query = f'[out:json][timeout:60];(way["building"]({minlat},{minlon},{maxlat},{maxlon}););out geom;'
    headers = {"User-Agent": "ThirdWave-risk-engine/1.0 (research prototype)"}
    for attempt in range(3):
        try:
            resp = requests.post(OVERPASS_URL, data=query, headers=headers, timeout=90)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except Exception as exc:
            log.warning("Overpass fetch failed (attempt %d/3): %s", attempt + 1, exc)
            time.sleep(3)
    else:
        return []

    buildings = []
    for e in elements:
        if e.get("tags", {}).get("building") and e.get("geometry"):
            coords = [(pt["lon"], pt["lat"]) for pt in e["geometry"]]
            if len(coords) >= 3:
                try:
                    buildings.append(shape({"type": "Polygon", "coordinates": [coords]}))
                except Exception:
                    continue
    log.info("Fetched %d unique building footprints", len(buildings))
    return buildings


def run():
    if not POP_RASTER.exists():
        raise FileNotFoundError(
            f"{POP_RASTER} not found -- download first:\n"
            f"  curl -sL -o {POP_RASTER} https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/GHA/gha_ppp_2020.tif"
        )

    grid = json.loads(GRID_PATH.read_text())
    log.info("Computing population exposure for %d cells", len(grid["features"]))

    buildings = fetch_buildings_clean(grid["features"])
    centroids = [b.centroid for b in buildings]
    centroid_tree = STRtree(centroids) if centroids else None

    results = {}
    with rasterio.open(POP_RASTER) as src:
        for i, f in enumerate(grid["features"]):
            zone_id = f["properties"]["zone_id"]
            geom = shape(f["geometry"])
            try:
                out_image, _ = rasterio.mask.mask(src, [geom.__geo_interface__], crop=True, nodata=0, filled=True)
                pop_sum = float(np.nansum(np.where(out_image[0] > 0, out_image[0], 0)))
            except ValueError:
                # geometry doesn't overlap the raster window at all
                pop_sum = 0.0

            # Clean building count: a centroid belongs to exactly one cell,
            # so summing across all 319 cells reproduces the true unique total.
            n_buildings_clean = 0
            if centroid_tree is not None:
                candidate_idx = centroid_tree.query(geom)
                n_buildings_clean = sum(1 for j in candidate_idx if geom.contains(centroids[j]))

            results[zone_id] = {
                "estimated_population": round(pop_sum, 1),
                "n_buildings": n_buildings_clean,
                "score": f["properties"]["score"],
                "level": f["properties"]["level"],
                "assembly": f["properties"]["assembly"],
            }

            if (i + 1) % 50 == 0:
                log.info("  ... %d/%d cells done", i + 1, len(grid["features"]))

    total_pop = sum(r["estimated_population"] for r in results.values())
    total_buildings = sum(r["n_buildings"] for r in results.values())
    high_risk_pop = sum(r["estimated_population"] for r in results.values() if r["level"] in ("High", "Very High"))
    log.info("Total estimated population in pilot grid: %.0f", total_pop)
    log.info("Total buildings: %d", total_buildings)
    log.info("Estimated population in High/Very High zones: %.0f (%.1f%% of total)",
              high_risk_pop, 100 * high_risk_pop / total_pop if total_pop else 0)

    OUTPUT.write_text(json.dumps({"source_note": SOURCE_NOTE, "zones": results}, indent=2))
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    run()
