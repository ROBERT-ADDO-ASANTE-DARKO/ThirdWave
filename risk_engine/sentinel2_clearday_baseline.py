"""
sentinel2_clearday_baseline.py — Clear-day Sentinel-2 MNDWI water baseline
for the pilot grid, at near-native resolution.

Different from sentinel2_crossvalidation.py (parked): that script tried to
use S2 as flood-event evidence and found ~zero correlation with SAR,
because clouds and floods co-occur -- optical is structurally blind
exactly when it would matter for event detection. This script doesn't try
to detect flood events. It asks a narrower question: on the rare days S2
IS clear, does it sharpen the STATIC permanent-water / drainage picture
beyond what the SAR baseline (resampled to a coarse 100m analysis grid,
PIXEL_DEG in geospatial_vulnerability.py) can resolve?

So: pick the N clearest available scenes (lowest cloud%, not necessarily
recent), read them at ~20m (near S2's native 10-20m, not downsampled to
100m), take a per-pixel median MNDWI across them to reduce residual
cloud-shadow/haze noise, classify water with the same adaptive-percentile
approach as SAR (WATER_PCT_THR), and aggregate to the pilot grid cells.

Design choice, same discipline as the LULC and S2-crossvalidation work
before it: this is a REPORTED, cross-checked field
(s2_clearday_water_pct, sar_s2clearday_agreement) alongside the existing
score. It does NOT change the composite vulnerability score or weights.

Usage
─────
    python3 sentinel2_clearday_baseline.py
    python3 sentinel2_clearday_baseline.py --scenes 5 --max-cloud 8
    python3 sentinel2_clearday_baseline.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio.enums
from shapely.geometry import shape as shapely_shape

import pystac_client
import planetary_computer

from geospatial_vulnerability import _grid_shape, _make_transform, _zone_mask, PILOT_BOUNDARY, WATER_PCT_THR
from sentinel2_crossvalidation import _read_s2_band, agreement_label, SCL_EXCLUDE

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
REPORT_PATH = HERE / "data" / "sentinel2_clearday_baseline.json"
MAP_PNG = HERE / "data" / "sentinel2_clearday_water_map.png"

START_DATE = "2019-01-01"
END_DATE = "2026-09-25"
PIXEL_DEG = 0.00018  # ~20m -- near S2 native (10m B03 / 20m B11), vs. the 100m SAR analysis grid


def pick_clear_scenes(bbox, catalog, max_cloud: float, n_scenes: int):
    items = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(bbox), datetime=f"{START_DATE}/{END_DATE}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    ).item_collection())
    log.info("Found %d scenes under %.0f%% cloud", len(items), max_cloud)
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
    return items[:n_scenes]


def clearday_mndwi(items, bbox, shape):
    """Per-pixel median MNDWI + water mask across the clearest scenes."""
    stack = np.full((len(items), *shape), np.nan, dtype=np.float32)
    valid_stack = np.zeros((len(items), *shape), dtype=bool)
    used = []
    for i, item in enumerate(items):
        date = item.properties["datetime"][:10]
        cc = item.properties.get("eo:cloud_cover", -1)
        try:
            green = _read_s2_band(item, "B03", bbox, shape)
            swir = _read_s2_band(item, "B11", bbox, shape)
            scl = _read_s2_band(item, "SCL", bbox, shape, resampling=rasterio.enums.Resampling.nearest)
        except Exception as exc:
            log.warning("  skip %s: %s", item.id[:44], exc)
            continue
        denom = green + swir
        with np.errstate(invalid="ignore", divide="ignore"):
            mndwi = np.where(denom > 0, (green - swir) / denom, np.nan)
        valid = np.isfinite(mndwi) & ~np.isin(scl.astype(int), list(SCL_EXCLUDE))
        stack[i] = np.where(valid, mndwi, np.nan)
        valid_stack[i] = valid
        cov = 100 * valid.mean()
        log.info("  %s  cloud=%.1f%%  valid_coverage=%.0f%%", date, cc, cov)
        used.append({"date": date, "cloud_pct": round(float(cc), 1), "valid_coverage_pct": round(float(cov), 1)})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        composite = np.nanmedian(stack, axis=0)
    valid_any = valid_stack.any(axis=0)

    valid_vals = composite[valid_any & np.isfinite(composite)]
    threshold = float(np.percentile(valid_vals, 100 - WATER_PCT_THR)) if len(valid_vals) else np.nan
    water_mask = valid_any & np.isfinite(composite) & (composite >= threshold)
    return composite, water_mask, valid_any, used, threshold


def run(n_scenes: int = 3, max_cloud: float = 10.0, dry_run: bool = False):
    bounds_gdf = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = bounds_gdf.total_bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)
    transform = _make_transform(bbox, shape)
    log.info("Pilot bbox: %s, raster %dx%d (~%.0fm pixels)", bbox, shape[0], shape[1], PIXEL_DEG * 111_000)

    if dry_run:
        log.info("Dry-run - config OK, exiting")
        return

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    items = pick_clear_scenes(bbox, catalog, max_cloud, n_scenes)
    if not items:
        log.error("No scenes found under %.0f%% cloud over this AOI/date range -- nothing to do", max_cloud)
        return
    log.info("Using %d clearest scenes:", len(items))
    composite, water_mask, valid_any, used, threshold = clearday_mndwi(items, bbox, shape)
    log.info("Composite water fraction: %.1f%% of valid pixels (threshold MNDWI>=%.3f)",
              100 * water_mask.sum() / max(valid_any.sum(), 1), threshold)

    # ── Aggregate to the pilot grid ─────────────────────────────────────────
    grid = json.loads(GRID_PATH.read_text())
    grid_report = []
    for f in grid["features"]:
        geom_shape = shapely_shape(f["geometry"])
        zmask = _zone_mask(geom_shape, transform, shape)
        v = valid_any[zmask]
        w = water_mask[zmask]
        valid_frac = round(float(v.mean()) * 100, 1) if zmask.sum() else 0.0
        water_pct = round(float(w[v].mean()) * 100, 2) if v.sum() > 0 else None
        sar_pct = f["properties"]["water_occ_pct"]
        agreement = agreement_label(sar_pct, water_pct) if water_pct is not None else "no_s2_coverage"
        f["properties"]["s2_clearday_water_pct"] = water_pct
        f["properties"]["s2_clearday_valid_frac_pct"] = valid_frac
        f["properties"]["s2_clearday_scenes"] = [u["date"] for u in used]
        f["properties"]["sar_s2clearday_agreement"] = agreement
        grid_report.append({
            "zone_id": f["properties"]["zone_id"], "sar_water_occ_pct": sar_pct,
            "s2_clearday_water_pct": water_pct, "valid_frac_pct": valid_frac, "agreement": agreement,
        })
    GRID_PATH.write_text(json.dumps(grid, indent=2))
    log.info("Updated -> %s", GRID_PATH)

    sar_vals = np.array([g["sar_water_occ_pct"] for g in grid_report if g["s2_clearday_water_pct"] is not None])
    s2_vals = np.array([g["s2_clearday_water_pct"] for g in grid_report if g["s2_clearday_water_pct"] is not None])
    n_no_coverage = sum(1 for g in grid_report if g["s2_clearday_water_pct"] is None)
    corr = float(np.corrcoef(sar_vals, s2_vals)[0, 1]) if len(sar_vals) > 1 else None
    counts = {}
    for g in grid_report:
        counts[g["agreement"]] = counts.get(g["agreement"], 0) + 1

    summary = {
        "purpose": "Static permanent-water baseline refinement at near-native S2 resolution on the "
                   "clearest available scenes -- NOT flood-event detection (see module docstring). "
                   "Reported alongside the composite score, not blended into it.",
        "resolution_m": round(PIXEL_DEG * 111_000), "scenes_used": used,
        "mndwi_threshold": round(threshold, 3) if np.isfinite(threshold) else None,
        "n_cells": len(grid_report), "n_no_s2_coverage": n_no_coverage,
        "sar_s2clearday_correlation": round(corr, 3) if corr is not None else None,
        "agreement_counts": counts,
        "major_disagreements": [g for g in grid_report if g["agreement"] == "major_disagreement"],
    }
    REPORT_PATH.write_text(json.dumps(summary, indent=2))
    log.info("Saved -> %s", REPORT_PATH)
    log.info("=== Clear-day S2 baseline summary ===")
    log.info("SAR vs S2-clearday correlation across %d cells: r=%s", len(sar_vals), summary["sar_s2clearday_correlation"])
    log.info("Agreement counts: %s", counts)
    log.info("Cells with no clear-day S2 coverage: %d", n_no_coverage)

    _plot(composite, water_mask, valid_any, bbox, shape, used, grid)


def _plot(composite, water_mask, valid_any, bbox, shape, used, grid):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    minlon, minlat, maxlon, maxlat = bbox
    fig, axs = plt.subplots(1, 2, figsize=(13, 6.5))

    ax = axs[0]
    im = ax.imshow(np.ma.masked_invalid(composite), extent=(minlon, maxlon, minlat, maxlat),
                    origin="upper", cmap="RdYlBu", vmin=-0.6, vmax=0.6)
    ax.set_title("Clear-day median MNDWI\n(scenes: " + ", ".join(f"{u['date']} ({u['cloud_pct']:.0f}%)" for u in used) + ")",
                 fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.75, label="MNDWI")

    ax = axs[1]
    cmap = ListedColormap(["#eeeeee", "#3182bd"])
    disp = np.where(valid_any, water_mask.astype(float), np.nan)
    ax.imshow(np.ma.masked_invalid(disp), extent=(minlon, maxlon, minlat, maxlat), origin="upper", cmap=cmap)
    for f in grid["features"]:
        geom = shapely_shape(f["geometry"])
        xs, ys = geom.exterior.xy
        ax.plot(xs, ys, color="black", lw=0.15, alpha=0.4)
    ax.set_title("Classified permanent water (near-native res)\nvs. pilot grid cells", fontsize=9)

    for a in axs:
        a.set_xlabel("lon"); a.set_ylabel("lat")
    fig.suptitle("Sentinel-2 clear-day baseline — pilot districts (static water layer, not flood detection)", fontsize=11)
    fig.tight_layout()
    fig.savefig(MAP_PNG, dpi=140, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved -> %s", MAP_PNG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear-day Sentinel-2 MNDWI baseline for the pilot grid")
    parser.add_argument("--scenes", type=int, default=3, help="number of clearest scenes to median-composite")
    parser.add_argument("--max-cloud", type=float, default=10.0, help="max scene cloud cover %% to consider")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(n_scenes=args.scenes, max_cloud=args.max_cloud, dry_run=args.dry_run)
