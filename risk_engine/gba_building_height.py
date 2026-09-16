"""
gba_building_height.py — per-grid-cell building height from
GlobalBuildingAtlas (GBA.LoD1 height points, ~2-3m spacing), aggregated
and validated the same way as building_obstruction_height.py's free
CopDEM-FABDEM proxy: cross-checked against independently-computed
impervious_pct before any number from it is trusted, not assumed good
because the source is "real" imagery-derived data. The authors' own
stated caveat -- "limited availability of height data in Africa for
training and validation" -- means this needs that check more, not less.

Unlike the CopDEM-FABDEM layer (30m, correlated at r=0.83 in the pilot),
this is a genuinely finer-resolution source (~2-3m spacing between
points) -- if it validates, it's a real step toward building-level detail
without needing the ESA Pléiades Neo stereo imagery request at all, at
least for the districts GlobalBuildingAtlas actually has data for.

See gba_height_fetch.py for how the raw points are pulled (streamed and
filtered from a ~1GB per-region archive, not downloaded whole) and its
docstring for the license (CC BY-NC 4.0, non-commercial).

Usage
─────
    python3 gba_building_height.py                    # pilot district
    python3 gba_building_height.py --grid data/lower_volta_risk_grid.geojson \
        --out data/lower_volta_gba_building_height.json --region-tile africa/w005_n10_e000_n05
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from shapely.strtree import STRtree

from gba_height_fetch import fetch_gba_heights, LICENSE_NOTE

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
DEFAULT_GRID = HERE / "data" / "pilot_risk_grid.geojson"
DEFAULT_OUTPUT = HERE / "data" / "gba_building_height.json"
DEFAULT_REGION_TILE = "africa/w005_n10_e000_n05"  # covers Ghana + neighbors, 5-deg grid
DEFAULT_COUNTRY = "GHA"

MAX_PLAUSIBLE_M = 200.0  # cap implausible outliers rather than let them skew a zone's mean


def run(grid_path: Path = DEFAULT_GRID, output: Path = DEFAULT_OUTPUT,
        region_tile: str = DEFAULT_REGION_TILE, country: str = DEFAULT_COUNTRY):
    grid = gpd.read_file(grid_path)
    log.info("Computing GBA building height for %d cells (grid: %s)", len(grid), grid_path.name)

    bbox = tuple(grid.total_bounds)
    points = fetch_gba_heights(bbox, country_iso3=country, region_tile=region_tile)
    log.info("%d GBA height points in grid bbox", len(points))

    lats = np.array([p["lat"] for p in points.values()])
    lons = np.array([p["lon"] for p in points.values()])
    heights = np.array([p["height"] if p["height"] is not None else np.nan for p in points.values()])
    valid = np.isfinite(heights) & (heights > -900)
    n_nodata = int((~valid).sum())
    log.info("%d/%d points have a real height value (%d are the -999 nodata sentinel)",
              int(valid.sum()), len(heights), n_nodata)

    pts_geom = [Point(lon, lat) for lon, lat in zip(lons[valid], lats[valid])]
    heights_valid = heights[valid]
    tree = STRtree(pts_geom)

    results = {}
    for _, row in grid.iterrows():
        zone_id = row["zone_id"]
        geom = row["geometry"]
        idx = tree.query(geom)
        if len(idx) == 0:
            continue
        in_zone = [i for i in idx if geom.contains(pts_geom[i])]
        if not in_zone:
            continue
        h = np.clip(heights_valid[in_zone], 0, MAX_PLAUSIBLE_M)
        results[zone_id] = {
            "mean_height_m": round(float(np.mean(h)), 2),
            "median_height_m": round(float(np.median(h)), 2),
            "p90_height_m": round(float(np.percentile(h, 90)), 2),
            "max_height_m": round(float(np.max(h)), 2),
            "n_points": int(len(in_zone)),
        }

    ranked = sorted(results.items(), key=lambda x: -x[1]["mean_height_m"])
    log.info("Top 5 cells by mean GBA building height:")
    for zid, r in ranked[:5]:
        log.info("  %-16s mean=%.2fm  median=%.2fm  max=%.2fm  n=%d",
                  zid, r["mean_height_m"], r["median_height_m"], r["max_height_m"], r["n_points"])

    validation = {}
    if "impervious_pct" in grid.columns:
        common = [(results[z]["mean_height_m"], row["impervious_pct"])
                   for z, row in zip(grid["zone_id"], grid.to_dict("records")) if z in results]
        if len(common) > 10:
            h_vals, imp_vals = zip(*common)
            corr = float(np.corrcoef(h_vals, imp_vals)[0, 1])
            validation = {"correlation_with_impervious_pct": round(corr, 3), "n_cells": len(common)}
            log.info("Validation: corr(mean_height_m, impervious_pct) = %.3f over %d cells (%s)",
                      corr, len(common),
                      "consistent with a real built-structure signal" if corr > 0.5
                      else "weak/absent -- do not trust this layer's numbers without further checking; "
                           "the authors' own stated gap (no African LiDAR ground truth) may be showing here")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "method": "GlobalBuildingAtlas GBA.LoD1 height points aggregated per grid cell "
                  "(mean/median/p90/max, point count) -- ~2-3m native point spacing, genuinely "
                  "finer than the 30m CopDEM-FABDEM obstruction-height layer, IF it validates.",
        "source_note": LICENSE_NOTE,
        "region_tile": region_tile, "country_filter": country,
        "n_points_total": len(points), "n_points_with_valid_height": int(valid.sum()),
        "n_points_nodata_sentinel": n_nodata,
        "max_plausible_m": MAX_PLAUSIBLE_M,
        "validation": validation,
        "zones": results,
    }, indent=2))
    log.info("Saved -> %s", output)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 8))
        sc = ax.scatter(lons[valid], lats[valid], c=np.clip(heights_valid, 0, MAX_PLAUSIBLE_M),
                         cmap="inferno", s=2, vmin=0, vmax=np.percentile(heights_valid, 98))
        ax.set_title(f"GBA.LoD1 building height points\n{grid_path.name}, "
                      f"{int(valid.sum()):,} valid points, mean={np.mean(np.clip(heights_valid,0,MAX_PLAUSIBLE_M)):.1f}m")
        plt.colorbar(sc, ax=ax, label="meters", fraction=0.04)
        ax.set_aspect("equal")
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        diagnostic_png = output.with_name(output.stem + "_diagnostic.png")
        fig.savefig(diagnostic_png, dpi=130, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved -> %s", diagnostic_png)
    except ImportError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GlobalBuildingAtlas building height per risk-grid cell")
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--region-tile", default=DEFAULT_REGION_TILE)
    parser.add_argument("--country", default=DEFAULT_COUNTRY)
    args = parser.parse_args()
    run(grid_path=args.grid, output=args.out, region_tile=args.region_tile, country=args.country)
