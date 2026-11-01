"""
channel_encroachment_timeseries.py — Multi-year, NDBI-based built-up extent
near mapped waterways, to track whether drainage-channel encroachment is
GETTING WORSE over time. channel_encroachment_index.py answers "how
encroached is this cell right now" from a single OSM building-footprint
snapshot; this answers "is the built-up edge near this channel creeping
closer, year over year" from Sentinel-2's multi-year optical archive --
the same NDVI/NDWI-style spectral-index-over-time idea, applied to
built-up extent instead of vegetation/water (see project chat history).

NDBI = (SWIR_B11 - NIR_B08) / (SWIR_B11 + NIR_B08)   higher = more built-up-like

Resolution honesty, stated once here rather than re-litigated per metric:
Sentinel-2 at this project's ~100m analysis grid (PIXEL_DEG, same as
geospatial_vulnerability.py) cannot reproduce OSM's sub-meter building-to-
waterway distances -- channel_encroachment_index.py's "2.0m" is a real
building-polygon measurement; nothing here should be read at that
precision. So this script does NOT try to re-derive a comparable "minimum
distance in meters" per year. Instead, for each cell it tracks
mean_ndbi_near_channel: the mean NDBI value of pixels within a fixed
~100m buffer of the nearest mapped waterway (one buffer per cell, one
Overpass fetch for the whole pilot extent, same discipline as
channel_encroachment_index.py). A rising mean over the years is the
"channel margin is trending more built-up-like" signal -- a pixel-
resolution, continuous proxy for encroachment, not a sub-meter distance.

NOT a binary built/not-built classification -- tried first, dropped
after validation. A fixed NDBI>threshold cutoff was checked against both
OSM building count and ESA WorldCover's own built-up class (per-pixel,
same grid) across a range of thresholds: best correlation achieved was
r=0.245 (vs WorldCover, threshold +0.15), with mean absolute disagreement
never below 0.32 at ANY threshold. That's a real, landscape-level
limitation, not a tuning problem to solve harder -- NDBI is known to
confuse bare/dry soil with built-up surface, and Accra's lateritic,
sparsely-vegetated dry-season ground cover apparently does exactly that
at this resolution. Tracking the raw continuous index instead (standard
practice for NDVI/NDWI time series generally -- trend the index itself,
don't binarize it first) sidesteps the whole threshold-calibration
problem rather than chasing a cutoff that may not exist for this
landscape. run() still reports a calibration sanity-check (continuous
mean NDBI vs. WorldCover's per-cell built fraction, correlation only,
never auto-tuned) -- same "report, don't silently re-tune" discipline
the LULC weights already follow.

Sentinel-2 L2A coverage note: this project's own prior S2 work
(geospatial_vulnerability.py, sentinel2_crossvalidation.py) starts no
earlier than 2020-01-01 for reliable cloud-filtered coverage over this
AOI; the default year range here starts in 2019 rather than reaching back
to the 2015 launch, for the same reason. June 2015 (Circle disaster) has
no usable Sentinel-2 imagery at all -- Sentinel-2A launched three weeks
after that event.

Usage
─────
    python3 channel_encroachment_timeseries.py --dry-run
    python3 channel_encroachment_timeseries.py --cell-limit 5 --year-start 2023 --year-end 2024 --max-scenes-per-year 4
    python3 channel_encroachment_timeseries.py
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
from shapely.geometry import shape as shapely_shape, LineString
from shapely.ops import unary_union

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    _grid_shape, _make_transform, _zone_mask, PIXEL_DEG, PILOT_BOUNDARY,
    _read_worldcover, WC_BUILDUP,
)
from sentinel2_crossvalidation import _read_s2_band
from channel_encroachment_index import query_overpass, DEG_TO_M

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
OUTPUT = HERE / "data" / "channel_encroachment_timeseries.json"

DEFAULT_YEAR_START = 2019
DEFAULT_YEAR_END = 2026
DEFAULT_MAX_SCENES_PER_YEAR = 10
DEFAULT_MAX_CLOUD_PCT = 30  # looser than sentinel2_crossvalidation.py's 20% -- some years/seasons need it to find ANY scenes

SCL_EXCLUDE = {0, 1, 3, 8, 9, 10, 11}  # no-data, saturated, cloud shadow, cloud med/high, cirrus, snow -- same set used elsewhere in this project

BUFFER_M = 100.0  # ~1 pixel at PIXEL_DEG resolution -- deliberately coarse, see module docstring


def fetch_annual_ndbi(catalog, bbox, shape, year: int, max_scenes: int, max_cloud_pct: float):
    """One annual NDBI composite: per-pixel MEDIAN across up to max_scenes
    cloud-filtered L2A scenes within the calendar year, cloud/invalid
    pixels masked via SCL first. Median (not mean) so a residual cloud-
    shadow sliver in one scene doesn't drag the whole year's value."""
    items = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(bbox),
        datetime=f"{year}-01-01/{year}-12-31",
        query={"eo:cloud_cover": {"lt": max_cloud_pct}},
    ).item_collection())
    if not items:
        return None, 0

    rng = np.random.default_rng(42)
    n = min(len(items), max_scenes)
    chosen = sorted(rng.choice(len(items), n, replace=False))
    selected = [items[i] for i in chosen]

    stack = []
    for item in selected:
        date = item.properties["datetime"][:10]
        try:
            nir = _read_s2_band(item, "B08", bbox, shape)
            swir = _read_s2_band(item, "B11", bbox, shape)
            scl = _read_s2_band(item, "SCL", bbox, shape, resampling=rasterio.enums.Resampling.nearest)
        except Exception as exc:
            log.debug("  skip %s: %s", date, exc)
            continue

        # L2A processing baseline >= 04.00 stores reflectance as DN with a
        # -1000 offset; a ratio's numerator cancels that (both bands shift
        # the same way) but the denominator does not, so undo it before
        # dividing -- same fix dam_spillage_s2_mndwi.py applies, missed here
        # at first because _read_s2_band (reused from sentinel2_crossvalidation.py)
        # just returns raw DN and that sibling script also skips this step.
        if np.nanmax(swir) > 100:
            nir = (nir - 1000.0) / 10000.0
            swir = (swir - 1000.0) / 10000.0

        denom = nir + swir
        with np.errstate(invalid="ignore", divide="ignore"):
            ndbi = np.where(denom > 0, (swir - nir) / denom, np.nan)
        invalid = np.isin(scl.astype(int), list(SCL_EXCLUDE)) | ~np.isfinite(ndbi) | (np.abs(ndbi) > 1.0)
        ndbi[invalid] = np.nan
        stack.append(ndbi)

    if not stack:
        return None, 0
    composite = np.nanmedian(np.stack(stack), axis=0)
    return composite, len(stack)


def _fetch_waterway_union(bbox):
    minlon, minlat, maxlon, maxlat = bbox
    pad = 0.001
    osm = query_overpass((minlon - pad, minlat - pad, maxlon + pad, maxlat + pad))
    waterways = []
    for e in osm.get("elements", []):
        tags = e.get("tags", {})
        if tags.get("waterway") and e.get("geometry"):
            coords = [(pt["lon"], pt["lat"]) for pt in e["geometry"]]
            if len(coords) >= 2:
                waterways.append(LineString(coords))
    log.info("Fetched %d waterway features from OSM", len(waterways))
    return unary_union(waterways) if waterways else None


def _trend(yearly: dict) -> dict:
    ok = sorted((int(y), v["mean_ndbi_near_channel"]) for y, v in yearly.items() if v["status"] == "ok")
    if len(ok) < 2:
        return {"status": "insufficient_years", "n_years_used": len(ok)}
    xs = np.array([y for y, _ in ok], dtype=float)
    ys = np.array([v for _, v in ok], dtype=float)
    slope, _ = np.polyfit(xs, ys, 1)
    return {
        "status": "ok", "slope_per_year": round(float(slope), 4), "n_years_used": len(ok),
        "note": ("Simple linear fit across available cloud-clear years -- a direction, not a forecast; "
                  "unreliable with so few points." if len(ok) < 4 else
                  "Simple linear fit across available cloud-clear years -- a direction, not a forecast."),
    }


def run(year_start: int, year_end: int, max_scenes_per_year: int, max_cloud_pct: float,
        dry_run: bool = False, cell_limit: int | None = None):
    boundary_gdf = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = boundary_gdf.total_bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)
    transform = _make_transform(bbox, shape)
    years = list(range(year_start, year_end + 1))
    log.info("Pilot bbox: %s, raster %dx%d, years %s", bbox, shape[0], shape[1], years)

    grid = json.loads(GRID_PATH.read_text())
    features = grid["features"][:cell_limit] if cell_limit else grid["features"]
    log.info("%d cell(s) to process", len(features))

    if dry_run:
        log.info("Dry-run - config OK, exiting")
        return

    log.info("Fetching OSM waterways for the whole pilot extent (one Overpass call)...")
    waterway_union = _fetch_waterway_union(bbox)
    if waterway_union is None:
        log.warning("No waterways returned from OSM at all -- every cell will be insufficient_data.")
        global_buffer_mask = None
    else:
        # Buffered and rasterized ONCE here, over the whole extent -- same
        # "compute once, slice per cell with a boolean mask" pattern the
        # NDBI composites already use. An earlier version of this script
        # ran shapely .buffer()/.intersection() inside the per-cell loop
        # (1013x instead of once) and hung; this is the fix.
        log.info("Buffering (%.0fm) and rasterizing the waterway geometry once...", BUFFER_M)
        waterway_buffer = waterway_union.buffer(BUFFER_M / DEG_TO_M)
        global_buffer_mask = _zone_mask(waterway_buffer, transform, shape)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    annual_ndbi: dict[int, np.ndarray | None] = {}
    annual_scenes_used: dict[int, int] = {}
    for year in years:
        log.info("Fetching Sentinel-2 L2A for %d...", year)
        composite, n_scenes = fetch_annual_ndbi(catalog, bbox, shape, year, max_scenes_per_year, max_cloud_pct)
        annual_ndbi[year] = composite
        annual_scenes_used[year] = n_scenes
        if composite is None:
            log.warning("  no usable scenes for %d -- this year is skipped everywhere", year)
        else:
            log.info("  %d scene(s) used", n_scenes)

    results = {}
    whole_cell_mean_ndbi_latest: dict[str, float] = {}
    latest_year_with_data = max((y for y in years if annual_ndbi.get(y) is not None), default=None)

    for f in features:
        zone_id = f["properties"]["zone_id"]
        assembly = f["properties"].get("assembly")
        cell_geom = shapely_shape(f["geometry"])
        zmask = _zone_mask(cell_geom, transform, shape)

        if latest_year_with_data is not None:
            vals = annual_ndbi[latest_year_with_data][zmask]
            valid = vals[np.isfinite(vals)]
            if len(valid):
                whole_cell_mean_ndbi_latest[zone_id] = float(np.mean(valid))

        if global_buffer_mask is None:
            results[zone_id] = {"status": "insufficient_data", "assembly": assembly, "note": "No OSM waterway data at all."}
            continue

        buffer_mask = global_buffer_mask & zmask
        if not buffer_mask.any():
            results[zone_id] = {"status": "no_waterway_nearby", "assembly": assembly}
            continue

        yearly = {}
        for year in years:
            composite = annual_ndbi.get(year)
            if composite is None:
                yearly[str(year)] = {"status": "no_scenes"}
                continue
            cell_vals = composite[buffer_mask]
            valid = cell_vals[np.isfinite(cell_vals)]
            if len(valid) == 0:
                yearly[str(year)] = {"status": "cloud_obscured"}
                continue
            yearly[str(year)] = {
                "status": "ok", "mean_ndbi_near_channel": round(float(np.mean(valid)), 4),
                "n_buffer_pixels_valid": int(len(valid)), "scenes_used": annual_scenes_used[year],
            }

        results[zone_id] = {"status": "ok", "assembly": assembly, "years": yearly, "trend": _trend(yearly)}

    # Calibration sanity check: whole-cell mean NDBI in the latest available
    # year vs. ESA WorldCover's own per-cell built-up fraction (same grid,
    # already used elsewhere in this project for impervious_pct) -- a fair
    # continuous-vs-continuous comparison. Correlation only, reported, never
    # auto-tuned -- same discipline as the LULC weighting lesson elsewhere
    # in this project. An OSM-building-count version of this check and a
    # binary NDBI>threshold version were both tried first and dropped (see
    # module docstring) -- neither validated well at any threshold.
    calibration = {"status": "skipped", "reason": "no latest-year data"}
    if latest_year_with_data is not None:
        log.info("Fetching ESA WorldCover 2021 for the calibration check...")
        worldcover = _read_worldcover(catalog, bbox, shape)
        if worldcover is not None:
            wc_built = (worldcover.astype(int) == WC_BUILDUP)
            pairs = []
            for f in features:
                zid = f["properties"]["zone_id"]
                if zid not in whole_cell_mean_ndbi_latest:
                    continue
                zmask = _zone_mask(shapely_shape(f["geometry"]), transform, shape)
                pairs.append((whole_cell_mean_ndbi_latest[zid], float(wc_built[zmask].mean())))
            if len(pairs) > 2:
                ndbi_vals, wc_fracs = zip(*pairs)
                corr = float(np.corrcoef(ndbi_vals, wc_fracs)[0, 1])
                calibration = {
                    "status": "ok", "reference_year": latest_year_with_data, "n_cells_compared": len(pairs),
                    "correlation_with_worldcover_built_fraction": round(corr, 3),
                    "note": "Sanity check only, not a tuned calibration: a positive correlation here means "
                            "whole-cell mean NDBI tracks WorldCover's own built-up classification sensibly; "
                            "it does not validate the per-year trend itself. See module docstring for the "
                            "earlier (dropped) binary-threshold calibration attempts and why they failed.",
                }
            else:
                calibration = {"status": "insufficient_overlap", "n_pairs": len(pairs)}
        else:
            calibration = {"status": "no_worldcover_coverage"}

    OUTPUT.write_text(json.dumps({
        "methodology": "NDBI = (SWIR_B11 - NIR_B08) / (SWIR_B11 + NIR_B08); mean_ndbi_near_channel is the "
                       "mean NDBI of valid pixels within a fixed buffer of mapped waterways, tracked as a "
                       "continuous value (not a built/not-built fraction) -- see module docstring for why "
                       "a binary threshold was tried and dropped.",
        "buffer_m": BUFFER_M, "pixel_deg": PIXEL_DEG,
        "years_requested": years, "scenes_used_by_year": annual_scenes_used,
        "calibration_check": calibration,
        "zones": results,
    }, indent=2))
    log.info("Saved -> %s", OUTPUT)

    n_ok = sum(1 for r in results.values() if r["status"] == "ok")
    log.info("Done: %d/%d cells with a computable time series", n_ok, len(results))
    worsening = sorted(
        ((zid, r["trend"]["slope_per_year"]) for zid, r in results.items()
         if r["status"] == "ok" and r["trend"]["status"] == "ok"),
        key=lambda x: -x[1],
    )[:5]
    if worsening:
        log.info("Fastest-worsening cells (mean_ndbi_near_channel slope/year):")
        for zid, slope in worsening:
            log.info("  %-16s %+.4f/year", zid, slope)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NDBI-based channel-encroachment time series for the pilot grid")
    parser.add_argument("--year-start", type=int, default=DEFAULT_YEAR_START)
    parser.add_argument("--year-end", type=int, default=DEFAULT_YEAR_END)
    parser.add_argument("--max-scenes-per-year", type=int, default=DEFAULT_MAX_SCENES_PER_YEAR)
    parser.add_argument("--max-cloud-pct", type=float, default=DEFAULT_MAX_CLOUD_PCT)
    parser.add_argument("--cell-limit", type=int, default=None, help="Process only the first N cells (testing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.year_start, args.year_end, args.max_scenes_per_year, args.max_cloud_pct,
        dry_run=args.dry_run, cell_limit=args.cell_limit)
