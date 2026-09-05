"""
extended_coverage.py — Vulnerability scoring for districts beyond the MVP
pilot boundary, added for documented flood history: Weija Gbawe and Ga South
(Weija Dam spillage, Oct 2022 and recurring), Tema Metropolitan and Ashaiman
Municipal (June 2010 flood, 17+ deaths, 9,000+ displaced).

This is explicitly NOT a redefinition of the MVP pilot district (spec
Section 2.1 scopes the MVP to one pilot district on purpose). It's a
separate "extended coverage" dataset for regional context / team demos,
kept apart from pilot_*.geojson so nothing about the actual pilot deliverable
changes.

Geometry note: the 4 new districts split into two disjoint clusters when
combined with the existing 6 -- Weija Gbawe/Ga South border the existing
pilot directly, but Tema/Ashaiman sit ~10-15km east with no shared district
boundary. Each cluster gets its own tight bbox and is processed
independently, rather than one bbox spanning the (irrelevant) gap between
them.

Usage
─────
    python3 extended_coverage.py                 # all clusters, 500m grid, 40 scenes
    python3 extended_coverage.py --scenes 20
    python3 extended_coverage.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    _grid_shape, _make_transform, fetch_pilot_rasters, score_geometry, derive_thresholds,
    PIXEL_DEG,
)
from risk_grid import build_grid, assign_assembly

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
ASSEMBLIES_PATH = HERE / "data" / "extended_district_assemblies.geojson"
DISTRICT_SCORES_OUTPUT = HERE / "data" / "extended_district_vulnerability.json"
GRID_OUTPUT = HERE / "data" / "extended_risk_grid.geojson"
THRESHOLDS_OUTPUT = HERE / "data" / "extended_grid_zone_threshold_config.json"

CLUSTER_TOUCH_TOLERANCE_DEG = 0.001  # ~110m
CELL_M_DEFAULT = 500.0


def find_clusters(gdf: gpd.GeoDataFrame) -> list[list[int]]:
    """Connected components: districts within CLUSTER_TOUCH_TOLERANCE_DEG of
    each other are processed together in one bbox; disjoint groups (like
    Tema/Ashaiman vs. the western block) get their own bbox each."""
    n = len(gdf)
    adj = {i: set() for i in range(n)}
    geoms = list(gdf.geometry)
    for i in range(n):
        for j in range(i + 1, n):
            if geoms[i].distance(geoms[j]) < CLUSTER_TOUCH_TOLERANCE_DEG:
                adj[i].add(j)
                adj[j].add(i)
    seen, clusters = set(), []
    for i in range(n):
        if i in seen:
            continue
        stack, comp = [i], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            seen.add(x)
            stack.extend(adj[x] - comp)
        clusters.append(sorted(comp))
    return clusters


def run(cell_m: float = CELL_M_DEFAULT, max_scenes: int = 40, dry_run: bool = False):
    gdf = gpd.read_file(ASSEMBLIES_PATH)
    clusters = find_clusters(gdf)
    log.info("Districts: %d, split into %d cluster(s)", len(gdf), len(clusters))
    for ci, comp in enumerate(clusters):
        names = [gdf.iloc[i]["name"] for i in comp]
        log.info("  Cluster %d: %s", ci, ", ".join(names))

    if dry_run:
        log.info("Dry-run - config OK, exiting")
        return

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    district_results: dict = {}
    grid_features: list = []
    thresholds: dict = {}

    for ci, comp in enumerate(clusters):
        cluster_gdf = gdf.iloc[comp].reset_index(drop=True)
        cluster_names = list(cluster_gdf["name"])
        log.info("=== Cluster %d: %s ===", ci, ", ".join(cluster_names))

        boundary_geom = unary_union(cluster_gdf.geometry)
        minlon, minlat, maxlon, maxlat = boundary_geom.bounds
        pad = 0.01
        bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
        shape_ = _grid_shape(bbox, PIXEL_DEG)
        transform = _make_transform(bbox, shape_)
        log.info("Cluster %d bbox: %s, raster %dx%d", ci, bbox, shape_[0], shape_[1])

        water_occ, elev, wc_int, scenes_used = fetch_pilot_rasters(bbox, shape_, catalog, max_scenes)

        # District (assembly) level scores for this cluster
        for _, row in cluster_gdf.iterrows():
            name = str(row["name"])
            r = score_geometry(row["geometry"], transform, shape_, water_occ, elev, wc_int, scenes_used)
            if r is None:
                log.warning("  %s: zero-pixel mask, skipping", name)
                continue
            r["cluster"] = ci
            r["in_original_pilot"] = bool(row["in_original_pilot"])
            district_results[name] = r
            log.info("  %-30s score=%5.1f %-10s water=%5.1f%% elev<=5m=%5.1f%%",
                     name, r["score"], r["level"], r["water_occ_pct"], r["low_elev_frac_pct"])

        # Fine grid for this cluster
        cells = build_grid(boundary_geom, cell_m / 111_000)
        log.info("  Cluster %d: %d grid cells", ci, len(cells))
        for c in cells:
            c["assembly"] = assign_assembly(c["geometry"], cluster_gdf)
            c["zone_id"] = f"ext_c{ci}_r{c['row']}_c{c['col']}"
            r = score_geometry(c["geometry"], transform, shape_, water_occ, elev, wc_int, scenes_used)
            if r is None:
                continue
            props = {"zone_id": c["zone_id"], "assembly": c["assembly"], "cluster": ci,
                      "boundary_overlap_frac": c["boundary_overlap_frac"], **r}
            props.pop("lulc_breakdown_pct", None)
            grid_features.append({"type": "Feature", "properties": props, "geometry": mapping(c["geometry"])})
            thresholds[c["zone_id"]] = {
                "zone_id": c["zone_id"], "assembly": c["assembly"], "cluster": ci,
                "vulnerability_score": r["score"], **derive_thresholds(r["score"]),
            }

    DISTRICT_SCORES_OUTPUT.write_text(json.dumps(district_results, indent=2))
    log.info("Saved -> %s", DISTRICT_SCORES_OUTPUT)

    GRID_OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": grid_features}, indent=2))
    log.info("Saved -> %s (%d cells total)", GRID_OUTPUT, len(grid_features))

    THRESHOLDS_OUTPUT.write_text(json.dumps(thresholds, indent=2))
    log.info("Saved -> %s", THRESHOLDS_OUTPUT)

    ranked = sorted(district_results.items(), key=lambda x: -x[1]["score"])
    log.info("All %d districts ranked by score:", len(ranked))
    for name, r in ranked:
        tag = "existing pilot" if r["in_original_pilot"] else "NEW"
        log.info("  %-30s score=%5.1f %-10s (%s)", name, r["score"], r["level"], tag)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extended-coverage vulnerability scoring beyond the MVP pilot")
    parser.add_argument("--cell-m", type=float, default=CELL_M_DEFAULT)
    parser.add_argument("--scenes", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(cell_m=args.cell_m, max_scenes=args.scenes, dry_run=args.dry_run)
