"""
lower_volta_coverage.py — Full pilot-grade vulnerability scoring for the
Lower Volta basin: Asuogyaman (Akosombo/Kpong), Lower Manya (Akuse), North
Tongu (Mepe/Battor), Central Tongu (Adidome), South Tongu (Sogakope), Ada
East and Ada West (Ada Foah) — seven districts across three regions
(Eastern, Volta, Greater Accra) with documented flooding from the 2023
Akosombo/Kpong dam spillage (35,857 displaced at Mepe alone; see
data/historical_flood_events.json, AKOSOMBO-DAM-SPILLAGE-2023-09-15) and
recurring Volta-basin flooding more generally.

This is explicitly NOT a redefinition of the MVP pilot district (spec
Section 2.1 scopes the MVP to one pilot district in Accra on purpose), and
it is also NOT merged into extended_coverage.py's Ga South/Tema/Ashaiman
dataset -- the Lower Volta is ~150km from Accra, spans a different flood
mechanism entirely (dam-release / riverine, not urban pluvial + tidal),
and deserves its own labeled dataset rather than implying one regional
context. Kept apart from pilot_*.geojson and extended_*.geojson so nothing
about the actual pilot deliverable changes.

Unlike extended_coverage.py's two disjoint clusters (Weija Gbawe/Ga South
vs. Tema/Ashaiman), all seven Lower Volta districts form ONE connected
component -- North Tongu borders every other district in the set (verified
against OCHA COD-AB ADM2 geometry, distance < 0.001 deg) -- so this uses a
single bbox spanning the whole basin rather than find_clusters() splitting.

"Full pilot-grade treatment" (per user decision, 2026-09-11): unlike
extended_coverage.py's district score + grid only, this basin gets the
same depth as the actual pilot -- fine 500m grid AND road network AND
population exposure AND channel encroachment. Those three companion
pipelines (build_road_network.py, population_exposure.py,
channel_encroachment_index.py) were extended with --boundary/--grid/--out
CLI args and are run separately against this script's outputs; see
run_full_pipeline.sh.

Usage
─────
    python3 lower_volta_coverage.py                 # 500m grid, 40 scenes
    python3 lower_volta_coverage.py --scenes 20
    python3 lower_volta_coverage.py --dry-run
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
ADMIN_SOURCE = HERE / "data" / "gha_admin2.geojson"

ASSEMBLIES_PATH = HERE / "data" / "lower_volta_district_assemblies.geojson"
BOUNDARY_PATH = HERE / "data" / "lower_volta_district_boundary.geojson"
DISTRICT_SCORES_OUTPUT = HERE / "data" / "lower_volta_district_vulnerability.json"
GRID_OUTPUT = HERE / "data" / "lower_volta_risk_grid.geojson"
THRESHOLDS_OUTPUT = HERE / "data" / "lower_volta_grid_zone_threshold_config.json"

CELL_M_DEFAULT = 500.0

DISTRICTS = [
    "Asuogyaman",    # Akosombo / Kpong dam, Eastern Region
    "Lower Manya",   # Akuse, Eastern Region
    "North Tongu",   # Mepe / Battor / Sogakope corridor, Volta Region
    "Central Tongu", # Adidome, Volta Region
    "South Tongu",   # Sogakope, Volta Region
    "Ada East",      # Ada Foah, Greater Accra Region
    "Ada West",      # Greater Accra Region
]


def build_assemblies() -> gpd.GeoDataFrame:
    """Pull the 7 target districts out of the cached national OCHA COD-AB
    ADM2 boundary file (already confirmed present under these exact
    adm2_name values) and save them as this basin's own assemblies file --
    mirrors extended_district_assemblies.geojson's structure."""
    admin = gpd.read_file(ADMIN_SOURCE)
    sub = admin[admin["adm2_name"].isin(DISTRICTS)].copy()
    missing = set(DISTRICTS) - set(sub["adm2_name"])
    if missing:
        raise RuntimeError(f"Districts not found in {ADMIN_SOURCE.name}: {missing}")
    out = gpd.GeoDataFrame({
        "name": sub["adm2_name"].values,
        "region": sub["adm1_name"].values,
        "source": "OCHA COD-AB GHA ADM2",
        "in_original_pilot": False,
    }, geometry=sub.geometry.values, crs=sub.crs)
    out.to_file(ASSEMBLIES_PATH, driver="GeoJSON")
    log.info("Saved -> %s (%d districts)", ASSEMBLIES_PATH, len(out))

    boundary_geom = unary_union(out.geometry)
    BOUNDARY_PATH.write_text(json.dumps({
        "type": "Feature",
        "properties": {"name": "Lower Volta extended coverage"},
        "geometry": mapping(boundary_geom),
    }, indent=2))
    log.info("Saved -> %s", BOUNDARY_PATH)
    return out


def run(cell_m: float = CELL_M_DEFAULT, max_scenes: int = 40, dry_run: bool = False):
    gdf = build_assemblies()
    names = list(gdf["name"])
    log.info("Lower Volta basin: %d districts, single connected cluster: %s",
              len(gdf), ", ".join(names))

    boundary_geom = unary_union(gdf.geometry)
    minlon, minlat, maxlon, maxlat = boundary_geom.bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape_ = _grid_shape(bbox, PIXEL_DEG)
    log.info("Basin bbox: %s, raster %dx%d (~%.0fm pixels)", bbox, shape_[0], shape_[1], PIXEL_DEG * 111_000)

    if dry_run:
        log.info("Dry-run - config OK, exiting")
        return

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    transform = _make_transform(bbox, shape_)

    water_occ, elev, wc_int, scenes_used = fetch_pilot_rasters(bbox, shape_, catalog, max_scenes)

    district_results: dict = {}
    for _, row in gdf.iterrows():
        name = str(row["name"])
        r = score_geometry(row["geometry"], transform, shape_, water_occ, elev, wc_int, scenes_used)
        if r is None:
            log.warning("  %s: zero-pixel mask, skipping", name)
            continue
        r["region"] = str(row["region"])
        district_results[name] = r
        log.info("  %-15s (%-14s) score=%5.1f %-10s water=%5.1f%% elev<=5m=%5.1f%%",
                  name, r["region"], r["score"], r["level"], r["water_occ_pct"], r["low_elev_frac_pct"])

    DISTRICT_SCORES_OUTPUT.write_text(json.dumps(district_results, indent=2))
    log.info("Saved -> %s", DISTRICT_SCORES_OUTPUT)

    cells = build_grid(boundary_geom, cell_m / 111_000)
    log.info("Basin grid: %d cells", len(cells))
    grid_features, thresholds = [], {}
    for c in cells:
        c["assembly"] = assign_assembly(c["geometry"], gdf)
        c["zone_id"] = f"lv_r{c['row']}_c{c['col']}"
        r = score_geometry(c["geometry"], transform, shape_, water_occ, elev, wc_int, scenes_used)
        if r is None:
            continue
        props = {"zone_id": c["zone_id"], "assembly": c["assembly"],
                  "boundary_overlap_frac": c["boundary_overlap_frac"], **r}
        props.pop("lulc_breakdown_pct", None)
        grid_features.append({"type": "Feature", "properties": props, "geometry": mapping(c["geometry"])})
        thresholds[c["zone_id"]] = {
            "zone_id": c["zone_id"], "assembly": c["assembly"],
            "vulnerability_score": r["score"], **derive_thresholds(r["score"]),
        }

    GRID_OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": grid_features}, indent=2))
    log.info("Saved -> %s (%d scored cells)", GRID_OUTPUT, len(grid_features))

    THRESHOLDS_OUTPUT.write_text(json.dumps(thresholds, indent=2))
    log.info("Saved -> %s", THRESHOLDS_OUTPUT)

    ranked = sorted(district_results.items(), key=lambda x: -x[1]["score"])
    log.info("All %d Lower Volta districts ranked by score:", len(ranked))
    for name, r in ranked:
        log.info("  %-15s (%-14s) score=%5.1f %-10s", name, r["region"], r["score"], r["level"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lower Volta basin vulnerability scoring (full pilot-grade)")
    parser.add_argument("--cell-m", type=float, default=CELL_M_DEFAULT)
    parser.add_argument("--scenes", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(cell_m=args.cell_m, max_scenes=args.scenes, dry_run=args.dry_run)
