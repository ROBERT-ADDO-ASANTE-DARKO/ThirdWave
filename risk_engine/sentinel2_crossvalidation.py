"""
sentinel2_crossvalidation.py — Cross-validate the pilot grid's SAR-derived
water occurrence against Sentinel-2 optical water indices (MNDWI).

Why: SAR (Sentinel-1) sees through cloud cover but its urban backscatter is
ambiguous (double-bounce off buildings can look like other surfaces).
Optical (Sentinel-2) gives an unambiguous spectral water signal but is
blind on cloudy days -- often exactly when a flood is happening. Neither
sensor is trusted alone in the literature; fusion catches what either one
misses. See the literature discussion in this project's chat history for
citations (multi-sensor fusion studies report ~96% urban accuracy vs. lower
single-sensor baselines).

Design choice, consistent with how LULC was handled earlier in this
project: Sentinel-2 water occurrence is added as a REPORTED, cross-checked
field (s2_water_occ_pct, sar_s2_agreement) -- it does NOT change the
composite vulnerability score or its weights. Silently reweighting the
score again after the LULC lesson (where doing that flattened every zone
to "Low") would repeat the same mistake. This is a confidence/QA layer on
top of the existing score, not a new score.

Scope: the original 6-assembly / 319-cell pilot grid only (not the 10-
district extended coverage -- held for later per team decision).

Usage
─────
    python3 sentinel2_crossvalidation.py
    python3 sentinel2_crossvalidation.py --scenes 20
    python3 sentinel2_crossvalidation.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
import rasterio.windows
import rasterio.enums
from rasterio.transform import from_bounds as rio_from_bounds
from rasterio.vrt import WarpedVRT
from shapely.geometry import shape as shapely_shape

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    _grid_shape, _make_transform, _zone_mask,
    PIXEL_DEG, PILOT_BOUNDARY, WATER_PCT_THR,
)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
ASSEMBLY_SCORES_PATH = HERE / "data" / "pilot_zone_vulnerability.json"
CROSSVAL_REPORT_PATH = HERE / "data" / "sentinel2_crossvalidation_report.json"

START_DATE = "2020-01-01"
END_DATE = "2024-12-31"
MAX_CLOUD_COVER_PCT = 20
# NOTE: a fixed MNDWI > 0 threshold (Xu 2006) was tried first and produced a
# ~zero correlation (r=-0.057) against the SAR water occurrence -- turned
# out to be an apples-to-oranges comparison, not a real disagreement: SAR
# water classification uses an adaptive per-scene percentile (bottom 8% of
# backscatter power, WATER_PCT_THR in geospatial_vulnerability.py), while a
# fixed global MNDWI cutoff has no such per-scene calibration. Switched to
# the same adaptive-percentile approach here (top WATER_PCT_THR% of MNDWI
# per scene) so the two sensors are being classified the same way.

# SCL (Scene Classification Layer) codes to exclude as invalid/unreliable
SCL_EXCLUDE = {0, 1, 3, 8, 9, 10, 11}  # no-data, saturated, cloud shadow, cloud med/high, cirrus, snow


def _read_s2_band(item, asset_name: str, bbox, out_shape, resampling=rasterio.enums.Resampling.bilinear):
    """Sentinel-2 assets are stored in each scene's native UTM zone, not
    EPSG:4326 -- unlike the DEM/WorldCover COGs used elsewhere in this
    project, which are already lon/lat. Reproject via WarpedVRT before
    windowing, or a lon/lat bbox gets interpreted as UTM coordinates and
    produces a degenerate out-of-range window (the bug this replaced)."""
    minlon, minlat, maxlon, maxlat = bbox
    rows, cols = out_shape
    href = item.assets[asset_name].href
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs="EPSG:4326", resampling=resampling) as vrt:
            win = rasterio.windows.from_bounds(minlon, minlat, maxlon, maxlat, vrt.transform)
            arr = vrt.read(1, window=win, out_shape=(rows, cols), resampling=resampling, fill_value=0)
    return arr.astype(np.float32)


def fetch_s2_water_occurrence(bbox, shape, catalog, max_scenes: int = 40):
    """Fetch Sentinel-2 L2A scenes, compute per-pixel MNDWI, mask clouds via
    SCL, and return (s2_water_occ, scenes_used)."""
    items = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(bbox), datetime=f"{START_DATE}/{END_DATE}",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER_PCT}},
    ).item_collection())
    log.info("Found %d cloud-filtered (<%d%%) S2 scenes", len(items), MAX_CLOUD_COVER_PCT)

    rng = np.random.default_rng(42)
    n = min(len(items), max_scenes)
    chosen = list(rng.choice(len(items), n, replace=False))
    selected = [items[i] for i in chosen]
    log.info("Processing %d S2 scenes", len(selected))

    water_count = np.zeros(shape, dtype=np.int32)
    valid_count = np.zeros(shape, dtype=np.int32)
    for i, item in enumerate(selected):
        date = item.properties["datetime"][:10]
        cc = item.properties.get("eo:cloud_cover", -1)
        log.info("  [%d/%d] %s (cloud=%.1f%%)", i + 1, len(selected), date, cc)
        try:
            green = _read_s2_band(item, "B03", bbox, shape)
            swir = _read_s2_band(item, "B11", bbox, shape)
            scl = _read_s2_band(item, "SCL", bbox, shape, resampling=rasterio.enums.Resampling.nearest)
        except Exception as exc:
            log.debug("  skip %s: %s", item.id[:44], exc)
            continue

        denom = green + swir
        with np.errstate(invalid="ignore", divide="ignore"):
            mndwi = np.where(denom > 0, (green - swir) / denom, np.nan)

        valid_pixel = np.isfinite(mndwi) & ~np.isin(scl.astype(int), list(SCL_EXCLUDE))

        # Adaptive per-scene threshold, mirroring _classify_water() for SAR:
        # water is HIGH MNDWI (opposite polarity from SAR power, where water
        # is LOW backscatter), so keep the top WATER_PCT_THR% of this scene's
        # valid MNDWI values rather than a fixed global cutoff.
        valid_mndwi = mndwi[valid_pixel]
        if len(valid_mndwi) == 0:
            continue
        threshold = float(np.percentile(valid_mndwi, 100 - WATER_PCT_THR))
        water_mask = valid_pixel & (mndwi >= threshold)

        water_count += water_mask.astype(np.int32)
        valid_count += valid_pixel.astype(np.int32)

    with np.errstate(invalid="ignore"):
        s2_water_occ = np.where(valid_count > 0, water_count.astype(float) / valid_count, np.nan)
    log.info("S2 MNDWI water occurrence computed (mean=%.3f, valid coverage=%.1f%%)",
              np.nanmean(s2_water_occ), 100 * np.mean(valid_count > 0))

    return s2_water_occ, len(selected)


def agreement_label(sar_pct: float, s2_pct: float) -> str:
    """Simple qualitative agreement flag between the two sensors, both on a
    0-100 occurrence-percent scale. Not a formal statistical test -- a
    quick, explainable QA signal for the Risk Detail Drawer / team review."""
    diff = abs(sar_pct - s2_pct)
    if diff <= 5:
        return "agree"
    if diff <= 15:
        return "minor_disagreement"
    return "major_disagreement"


def run(max_scenes: int = 40, dry_run: bool = False):
    bounds_gdf = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = bounds_gdf.total_bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)
    transform = _make_transform(bbox, shape)
    log.info("Pilot bbox: %s, raster %dx%d", bbox, shape[0], shape[1])

    if dry_run:
        log.info("Dry-run - config OK, exiting")
        return

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    s2_water_occ, s2_scenes_used = fetch_s2_water_occurrence(bbox, shape, catalog, max_scenes)

    # ── Update the 319-cell grid ─────────────────────────────────────────────
    grid = json.loads(GRID_PATH.read_text())
    grid_report = []
    for f in grid["features"]:
        geom_shape = shapely_shape(f["geometry"])
        zmask = _zone_mask(geom_shape, transform, shape)
        vals = s2_water_occ[zmask]
        valid = vals[np.isfinite(vals)]
        s2_pct = round(float(np.mean(valid)) * 100, 2) if len(valid) > 0 else None
        sar_pct = f["properties"]["water_occ_pct"]
        agreement = agreement_label(sar_pct, s2_pct) if s2_pct is not None else "no_s2_coverage"
        f["properties"]["s2_water_occ_pct"] = s2_pct
        f["properties"]["s2_scenes_used"] = s2_scenes_used
        f["properties"]["sar_s2_agreement"] = agreement
        grid_report.append({
            "zone_id": f["properties"]["zone_id"], "sar_water_occ_pct": sar_pct,
            "s2_water_occ_pct": s2_pct, "agreement": agreement,
        })
    GRID_PATH.write_text(json.dumps(grid, indent=2))
    log.info("Updated -> %s", GRID_PATH)

    # ── Update the 6-assembly scores ─────────────────────────────────────────
    assembly_scores = json.loads(ASSEMBLY_SCORES_PATH.read_text())
    assemblies_gdf = gpd.read_file(HERE / "data" / "pilot_district_assemblies.geojson")
    for _, row in assemblies_gdf.iterrows():
        name = row["name"]
        if name not in assembly_scores:
            continue
        zmask = _zone_mask(row["geometry"], transform, shape)
        vals = s2_water_occ[zmask]
        valid = vals[np.isfinite(vals)]
        s2_pct = round(float(np.mean(valid)) * 100, 2) if len(valid) > 0 else None
        sar_pct = assembly_scores[name]["water_occ_pct"]
        assembly_scores[name]["s2_water_occ_pct"] = s2_pct
        assembly_scores[name]["s2_scenes_used"] = s2_scenes_used
        assembly_scores[name]["sar_s2_agreement"] = agreement_label(sar_pct, s2_pct) if s2_pct is not None else "no_s2_coverage"
    ASSEMBLY_SCORES_PATH.write_text(json.dumps(assembly_scores, indent=2))
    log.info("Updated -> %s", ASSEMBLY_SCORES_PATH)

    # ── Report ────────────────────────────────────────────────────────────────
    sar_vals = np.array([g["sar_water_occ_pct"] for g in grid_report if g["s2_water_occ_pct"] is not None])
    s2_vals = np.array([g["s2_water_occ_pct"] for g in grid_report if g["s2_water_occ_pct"] is not None])
    n_no_coverage = sum(1 for g in grid_report if g["s2_water_occ_pct"] is None)
    corr = float(np.corrcoef(sar_vals, s2_vals)[0, 1]) if len(sar_vals) > 1 else None

    counts = {}
    for g in grid_report:
        counts[g["agreement"]] = counts.get(g["agreement"], 0) + 1

    summary = {
        "n_cells": len(grid_report), "n_no_s2_coverage": n_no_coverage,
        "sar_s2_correlation": round(corr, 3) if corr is not None else None,
        "agreement_counts": counts,
        "major_disagreements": [g for g in grid_report if g["agreement"] == "major_disagreement"],
    }
    CROSSVAL_REPORT_PATH.write_text(json.dumps(summary, indent=2))
    log.info("Saved -> %s", CROSSVAL_REPORT_PATH)

    log.info("=== Cross-validation summary ===")
    log.info("SAR-S2 correlation across %d cells: r=%s", len(sar_vals), summary["sar_s2_correlation"])
    log.info("Agreement counts: %s", counts)
    log.info("Cells with no cloud-free S2 coverage: %d", n_no_coverage)
    if summary["major_disagreements"]:
        log.info("Major disagreement cells (SAR vs S2 diff > 15pp):")
        for g in summary["major_disagreements"]:
            log.info("  %-16s SAR=%.1f%% S2=%.1f%%", g["zone_id"], g["sar_water_occ_pct"], g["s2_water_occ_pct"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel-2 MNDWI cross-validation of the pilot risk grid")
    parser.add_argument("--scenes", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(max_scenes=args.scenes, dry_run=args.dry_run)
