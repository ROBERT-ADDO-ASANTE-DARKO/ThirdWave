"""
compare_obstruction_vs_gba.py — same validation methodology as
building_obstruction_height.py and gba_building_height.py (both cross-
checked against independently-computed impervious_pct), run side by side
on a SECOND city GlobalBuildingAtlas is expected to cover well, to see
whether GBA's weak Accra result (r=0.355) was really "no African
ground truth" specifically, or a more general property of the method.

Also surfaces a finding from building the fetch path itself: GBA.LoD1
keys buildings differently depending on local OSM coverage -- Ghana's
tile uses "google<PlusCode>GHA" (a raster of points, used where OSM
building coverage is too patchy to anchor to), the US tile uses
"osm<wayID>USA" (real OSM building footprints, joined here via a bulk
Overpass fetch -- see gba_height_fetch.fetch_osm_building_centroids).
That's already a signal about data quality before height accuracy is
even considered.

Test city: Boston, MA (explicitly one of PHDataset's named training/eval
cities -- see project chat history -- so if GBA validates anywhere, this
is a fair, not cherry-picked-favorable, place to check). ~54 km² AOI,
comparable in scale to the Accra pilot's 75 km².

Usage
─────
    python3 compare_obstruction_vs_gba.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import box, shape as shp_shape
from shapely.strtree import STRtree
from shapely.geometry import Point

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    _grid_shape, _make_transform, _zone_mask, _read_dem_window, fetch_pilot_rasters,
    score_geometry, PIXEL_DEG,
)
from risk_grid import build_grid
from fabdem_fetch import read_fabdem_window
from gba_height_fetch import fetch_gba_heights_osmid, fetch_osm_building_centroids

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "compare_obstruction_vs_gba_boston.json"
DIAGNOSTIC_PNG = HERE / "data" / "compare_obstruction_vs_gba_boston_diagnostic.png"

CITY = "Boston"
BBOX = (-71.10, 42.32, -71.00, 42.38)  # minlon, minlat, maxlon, maxlat -- ~54 km2
COUNTRY_ISO3 = "USA"
GBA_REGION_TILE = "northamerica/w075_n45_w070_n40"
CELL_M = 500.0
MAX_SCENES = 12  # only need impervious_pct as the validation reference here, not a real score
MAX_PLAUSIBLE_M = 200.0


def run():
    boundary_geom = box(*BBOX)
    shape_ = _grid_shape(BBOX, PIXEL_DEG)
    transform = _make_transform(BBOX, shape_)
    log.info("%s bbox %s, raster %dx%d (~%.0fm pixels)", CITY, BBOX, shape_[0], shape_[1], PIXEL_DEG * 111_000)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    water_occ, elev, wc_int, scenes_used = fetch_pilot_rasters(BBOX, shape_, catalog, MAX_SCENES)

    log.info("Fetching FABDEM for obstruction-height comparison...")
    fabdem = read_fabdem_window(BBOX, shape_)
    copdem = elev  # already fetched by fetch_pilot_rasters via the same _read_dem_window path
    obstruction = np.clip(copdem - fabdem, 0, MAX_PLAUSIBLE_M)

    log.info("Fetching OSM building centroids for GBA osm-id join...")
    osm_centroids = fetch_osm_building_centroids(BBOX)

    log.info("Fetching GBA.LoD1 heights (osm-id join)...")
    gba_points = fetch_gba_heights_osmid(BBOX, COUNTRY_ISO3, GBA_REGION_TILE, osm_centroids)
    gba_lats = np.array([p["lat"] for p in gba_points.values()])
    gba_lons = np.array([p["lon"] for p in gba_points.values()])
    gba_heights = np.array([p["height"] if p["height"] is not None else np.nan for p in gba_points.values()])
    gba_valid = np.isfinite(gba_heights) & (gba_heights > -900)
    log.info("%d/%d GBA points have a real height value", int(gba_valid.sum()), len(gba_heights))
    gba_pts_geom = [Point(lon, lat) for lon, lat in zip(gba_lons[gba_valid], gba_lats[gba_valid])]
    gba_heights_valid = np.clip(gba_heights[gba_valid], 0, MAX_PLAUSIBLE_M)
    gba_tree = STRtree(gba_pts_geom) if gba_pts_geom else None

    cells = build_grid(boundary_geom, CELL_M / 111_000)
    log.info("%s: %d grid cells", CITY, len(cells))

    rows = []
    for c in cells:
        geom = c["geometry"]
        r = score_geometry(geom, transform, shape_, water_occ, elev, wc_int, scenes_used)
        if r is None:
            continue
        mask = _zone_mask(geom, transform, shape_)
        obs_vals = obstruction[mask]
        obs_vals = obs_vals[np.isfinite(obs_vals)]
        mean_obstruction = float(np.mean(obs_vals)) if len(obs_vals) else None

        mean_gba = None
        n_gba = 0
        if gba_tree is not None:
            idx = gba_tree.query(geom)
            in_zone = [i for i in idx if geom.contains(gba_pts_geom[i])]
            n_gba = len(in_zone)
            if in_zone:
                mean_gba = float(np.mean(gba_heights_valid[in_zone]))

        rows.append({
            "impervious_pct": r["impervious_pct"],
            "mean_obstruction_m": mean_obstruction,
            "mean_gba_height_m": mean_gba,
            "n_gba_points": n_gba,
        })

    obs_pairs = [(row["mean_obstruction_m"], row["impervious_pct"]) for row in rows if row["mean_obstruction_m"] is not None]
    gba_pairs = [(row["mean_gba_height_m"], row["impervious_pct"]) for row in rows if row["mean_gba_height_m"] is not None]

    obs_corr = float(np.corrcoef(*zip(*obs_pairs))[0, 1]) if len(obs_pairs) > 10 else None
    gba_corr = float(np.corrcoef(*zip(*gba_pairs))[0, 1]) if len(gba_pairs) > 10 else None

    log.info("=" * 70)
    log.info("%s (n=%d cells): CopDEM-FABDEM obstruction vs impervious_pct -> r=%s (n=%d)",
              CITY, len(cells), f"{obs_corr:.3f}" if obs_corr is not None else "n/a", len(obs_pairs))
    log.info("%s (n=%d cells): GBA height vs impervious_pct              -> r=%s (n=%d)",
              CITY, len(cells), f"{gba_corr:.3f}" if gba_corr is not None else "n/a", len(gba_pairs))
    log.info("For reference, Accra pilot: CopDEM-FABDEM r=0.83 (1013 cells), GBA r=0.355 (846 cells)")
    log.info("=" * 70)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "city": CITY, "bbox": list(BBOX), "n_cells": len(cells),
        "gba_key_format": "osmid (real OSM building footprints -- unlike Ghana's Plus-Code raster fallback)",
        "n_osm_buildings_in_bbox": len(osm_centroids),
        "n_gba_points_joined": len(gba_points),
        "copdem_fabdem_obstruction_vs_impervious_corr": obs_corr,
        "gba_height_vs_impervious_corr": gba_corr,
        "n_cells_with_obstruction_data": len(obs_pairs),
        "n_cells_with_gba_data": len(gba_pairs),
        "accra_pilot_reference": {"copdem_fabdem_corr": 0.828, "gba_corr": 0.355},
        "rows": rows,
    }, indent=2))
    log.info("Saved -> %s", OUTPUT)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
        if obs_pairs:
            x, y = zip(*obs_pairs)
            axes[0].scatter(y, x, s=10, alpha=0.5, color="#c1621b")
            axes[0].set_title(f"{CITY}: CopDEM-FABDEM obstruction\nr={obs_corr:.3f}" if obs_corr else CITY)
            axes[0].set_xlabel("Impervious %"); axes[0].set_ylabel("Mean obstruction (m)")
        if gba_pairs:
            x, y = zip(*gba_pairs)
            axes[1].scatter(y, x, s=10, alpha=0.5, color="#1b7a9e")
            axes[1].set_title(f"{CITY}: GBA.LoD1 height\nr={gba_corr:.3f}" if gba_corr else CITY)
            axes[1].set_xlabel("Impervious %"); axes[1].set_ylabel("Mean GBA height (m)")
        fig.suptitle(f"{CITY} -- does building height correlate with known impervious land cover?")
        fig.tight_layout()
        fig.savefig(DIAGNOSTIC_PNG, dpi=130, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved -> %s", DIAGNOSTIC_PNG)
    except ImportError:
        pass


if __name__ == "__main__":
    run()
