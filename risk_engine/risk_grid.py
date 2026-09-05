"""
risk_grid.py — Fine-grained RiskZone grid for the ThirdWave pilot district.

Why this exists: scoring the 6 municipal assemblies as whole units (see
geospatial_vulnerability.py) averages a ~15-30 km^2 area into one number.
Validating against the June 3 2015 Kwame Nkrumah Circle disaster showed why
that's a problem — the pixel-level SAR/DEM data at Circle itself is a strong
flood signature (2.5x the pilot-wide water occurrence, 3x lower elevation),
but Circle's containing assembly (Ablekuma North) came out as the LOWEST
scoring zone because the hotspot gets diluted across a large, mostly-dry
municipality. Assembly-level granularity is too coarse for the threshold
engine to actually do its job.

This script re-scores the same underlying rasters (SAR water occurrence,
Copernicus DEM, ESA WorldCover) over a regular grid of small cells clipped
to the pilot boundary, so a hotspot drives its own threshold instead of
being averaged into an administrative unit it barely touches.

Each cell becomes a candidate RiskZone row (spec Section 9: RiskZone has its
own geometry, independent of District) — cell_id is the zone_id, the
majority-overlap assembly is kept as a human-readable label only.

Usage
─────
    python3 risk_grid.py                    # default 500m cells, 40 SAR scenes
    python3 risk_grid.py --cell-m 250        # finer grid
    python3 risk_grid.py --scenes 20         # faster
    python3 risk_grid.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping
from shapely.ops import unary_union

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    _grid_shape, _make_transform, fetch_pilot_rasters, score_geometry, derive_thresholds,
    PIXEL_DEG, PILOT_BOUNDARY, PILOT_ZONES,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
GRID_OUTPUT = HERE / "data" / "pilot_risk_grid.geojson"
GRID_THRESHOLDS_OUTPUT = HERE / "data" / "grid_zone_threshold_config.json"

DEG_PER_METER = 1 / 111_000  # approximation, fine at this latitude/scale

# Keep a cell only if at least this fraction of its area sits inside the
# actual pilot boundary — drops slivers along the edge that would otherwise
# produce noisy, barely-covered zones.
MIN_BOUNDARY_OVERLAP_FRAC = 0.15


def build_grid(boundary_geom, cell_deg: float) -> list[dict]:
    minlon, minlat, maxlon, maxlat = boundary_geom.bounds
    cells = []
    lat = minlat
    row = 0
    while lat < maxlat:
        lon = minlon
        col = 0
        while lon < maxlon:
            cell = box(lon, lat, lon + cell_deg, lat + cell_deg)
            if boundary_geom.intersects(cell):
                overlap = boundary_geom.intersection(cell)
                frac = overlap.area / cell.area
                if frac >= MIN_BOUNDARY_OVERLAP_FRAC:
                    cells.append({"row": row, "col": col, "geometry": cell, "boundary_overlap_frac": round(frac, 3)})
            lon += cell_deg
            col += 1
        lat += cell_deg
        row += 1
    return cells


def assign_assembly(cell_geom, assemblies_gdf) -> str:
    """Label a cell with whichever assembly it overlaps most — display-only,
    the cell's own geometry is what actually drives its score/thresholds."""
    best_name, best_overlap = "unknown", 0.0
    for _, row in assemblies_gdf.iterrows():
        overlap = cell_geom.intersection(row["geometry"]).area
        if overlap > best_overlap:
            best_overlap, best_name = overlap, row["name"]
    return best_name


def run(cell_m: float = 500.0, max_scenes: int = 40, dry_run: bool = False):
    boundary_gdf = gpd.read_file(PILOT_BOUNDARY)
    boundary_geom = unary_union(boundary_gdf.geometry)
    assemblies_gdf = gpd.read_file(PILOT_ZONES)

    cell_deg = cell_m * DEG_PER_METER
    cells = build_grid(boundary_geom, cell_deg)
    log.info("Built %d grid cells (%.0fm, >=%.0f%% inside boundary)",
             len(cells), cell_m, MIN_BOUNDARY_OVERLAP_FRAC * 100)

    for c in cells:
        c["assembly"] = assign_assembly(c["geometry"], assemblies_gdf)
        c["zone_id"] = f"grid_r{c['row']}_c{c['col']}"

    minlon, minlat, maxlon, maxlat = boundary_geom.bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)
    transform = _make_transform(bbox, shape)
    log.info("Analysis raster grid: %d rows x %d cols (~%.0fm pixels)", shape[0], shape[1], PIXEL_DEG * 111_000)

    if dry_run:
        log.info("Dry-run - config OK, exiting")
        return

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    water_occ, elev, wc_int, scenes_used = fetch_pilot_rasters(bbox, shape, catalog, max_scenes)

    features = []
    thresholds = {}
    skipped = 0
    for c in cells:
        r = score_geometry(c["geometry"], transform, shape, water_occ, elev, wc_int, scenes_used)
        if r is None:
            skipped += 1
            continue
        props = {
            "zone_id": c["zone_id"], "assembly": c["assembly"],
            "boundary_overlap_frac": c["boundary_overlap_frac"], **r,
        }
        # LULC breakdown is verbose per-cell noise at this granularity; keep
        # it out of the GeoJSON properties (still in the JSON via score_geometry
        # if needed) to keep the map payload lean. Drop from the feature only.
        props.pop("lulc_breakdown_pct", None)
        features.append({"type": "Feature", "properties": props, "geometry": mapping(c["geometry"])})
        thresholds[c["zone_id"]] = {
            "zone_id": c["zone_id"], "assembly": c["assembly"],
            "vulnerability_score": r["score"], **derive_thresholds(r["score"]),
        }

    log.info("Scored %d cells (%d skipped - zero pixel coverage)", len(features), skipped)

    scores_sorted = sorted(features, key=lambda f: -f["properties"]["score"])
    log.info("Top 5 hottest cells:")
    for f in scores_sorted[:5]:
        p = f["properties"]
        log.info("  %-16s (%-28s) score=%5.1f %-10s water=%5.1f%% elev<=5m=%5.1f%%",
                 p["zone_id"], p["assembly"], p["score"], p["level"], p["water_occ_pct"], p["low_elev_frac_pct"])

    GRID_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    GRID_OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))
    log.info("Saved -> %s", GRID_OUTPUT)

    GRID_THRESHOLDS_OUTPUT.write_text(json.dumps(thresholds, indent=2))
    log.info("Saved -> %s", GRID_THRESHOLDS_OUTPUT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-grained RiskZone grid for the ThirdWave pilot district")
    parser.add_argument("--cell-m", type=float, default=500.0, help="Grid cell size in meters (default 500)")
    parser.add_argument("--scenes", type=int, default=40, help="Max S1 scenes to process (default 40)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(cell_m=args.cell_m, max_scenes=args.scenes, dry_run=args.dry_run)
