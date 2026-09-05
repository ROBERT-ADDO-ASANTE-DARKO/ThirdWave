"""
export_raster_overlays.py — One-time export of the three raw geospatial
layers (Sentinel-1 SAR water occurrence, Copernicus DEM elevation, ESA
WorldCover land cover) as small georeferenced PNGs, so the Streamlit app
can show them as toggleable folium ImageOverlay layers under the risk-zone
polygons.

Why export instead of fetching live in the app: fetch_pilot_rasters() in
geospatial_vulnerability.py pulls straight from Microsoft Planetary
Computer into memory and discards it -- nothing is cached to disk. Re-
fetching per Streamlit session would be slow (this is the same ~40-scene
SAR fetch that takes minutes for the main scoring pipeline) and would hit
the API repeatedly for data that never changes for this static POC. Same
"compute once, ship a static result" pattern as risk_grid.py and
build_road_network.py.

Usage
─────
    python3 export_raster_overlays.py
    python3 export_raster_overlays.py --scenes 20   # faster, fewer SAR scenes
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from pathlib import Path

import numpy as np
from PIL import Image

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    PILOT_BOUNDARY, PIXEL_DEG, WC_NAMES,
    _grid_shape, fetch_pilot_rasters,
)

import geopandas as gpd

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "overlays"
UPSCALE = 4  # 122x142 -> 488x568, cheap and much less blocky as a map overlay

# ESA WorldCover 2021 official palette (RGB), per class code.
WC_PALETTE = {
    10: (0, 100, 0),      # tree cover
    20: (255, 187, 34),   # shrubland
    30: (255, 255, 76),   # grassland
    40: (240, 150, 255),  # cropland
    50: (250, 0, 0),      # built-up
    60: (180, 180, 180),  # bare / sparse vegetation
    70: (240, 240, 240),  # snow / ice
    80: (0, 100, 200),    # permanent water
    90: (0, 150, 160),    # herbaceous wetland
    95: (0, 207, 117),    # mangroves
    100: (250, 230, 160), # moss / lichen
}


def _upscale(arr: np.ndarray, order: int) -> np.ndarray:
    """order: 0 = nearest (categorical), 1 = bilinear (continuous)."""
    img = Image.fromarray(arr)
    new_size = (arr.shape[1] * UPSCALE, arr.shape[0] * UPSCALE)
    resample = Image.Resampling.NEAREST if order == 0 else Image.Resampling.BILINEAR
    return np.array(img.resize(new_size, resample))


def _save_rgba(rgba: np.ndarray, path: Path):
    # ImageOverlay/Leaflet expects north-up (row 0 = top = max lat); our
    # arrays are already north-up from rasterio's from_bounds transform.
    Image.fromarray(rgba, mode="RGBA").save(path)
    log.info("Saved -> %s", path)


def export_sar_overlay(water_occ: np.ndarray, out_dir: Path):
    """Blue overlay, alpha scaled by water occurrence -- dry ground is fully
    transparent, frequently-flooded pixels are opaque blue. This is the raw
    evidence the SAR-based part of the vulnerability score is built from."""
    occ = np.nan_to_num(water_occ, nan=0.0)
    occ_up = _upscale(occ.astype(np.float32), order=1)
    occ_up = np.clip(occ_up, 0, 1)

    rgba = np.zeros((*occ_up.shape, 4), dtype=np.uint8)
    rgba[..., 0] = 20   # R
    rgba[..., 1] = 90   # G
    rgba[..., 2] = 200  # B
    rgba[..., 3] = (occ_up * 235).astype(np.uint8)  # alpha: 0 -> fully transparent
    _save_rgba(rgba, out_dir / "sar_water_occurrence.png")
    return {"min": 0.0, "max": 1.0, "legend": "Sentinel-1 SAR water occurrence, 2020-2024 (darker blue = more frequently water-like)"}


def export_dem_overlay(elev: np.ndarray, out_dir: Path):
    """Elevation colormap: green (low, flood-prone) through tan to dark brown
    (high ground). Semi-transparent throughout so zone polygons stay readable
    underneath/above it."""
    elev = np.nan_to_num(elev, nan=0.0)
    lo, hi = float(np.percentile(elev, 2)), float(np.percentile(elev, 98))
    hi = max(hi, lo + 1.0)
    norm = np.clip((elev - lo) / (hi - lo), 0, 1)
    norm_up = _upscale(norm.astype(np.float32), order=1)

    # Simple 3-stop ramp: low-elevation green -> mid tan -> high brown.
    stops = np.array([[27, 120, 55], [230, 210, 130], [110, 66, 30]], dtype=np.float32)
    t = norm_up[..., None] * 2  # 0..2 across the 3 stops
    seg = np.clip(t, 0, 1)
    lower = stops[0] * (1 - seg) + stops[1] * seg
    seg2 = np.clip(t - 1, 0, 1)
    upper = stops[1] * (1 - seg2) + stops[2] * seg2
    rgb = np.where(t[..., :1] <= 1, lower, upper).astype(np.uint8)

    rgba = np.zeros((*norm_up.shape, 4), dtype=np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = 165
    _save_rgba(rgba, out_dir / "dem_elevation.png")
    return {"min_m": round(lo, 1), "max_m": round(hi, 1),
            "legend": "Copernicus DEM 30m elevation (green = low-lying/flood-prone, brown = higher ground)"}


def export_worldcover_overlay(wc_int: np.ndarray, out_dir: Path):
    """Categorical ESA WorldCover palette, nearest-neighbour upscaled so
    class boundaries stay crisp instead of blurring into invented colors."""
    wc_up = _upscale(wc_int.astype(np.uint8), order=0)
    rgba = np.zeros((*wc_up.shape, 4), dtype=np.uint8)
    for code, (r, g, b) in WC_PALETTE.items():
        m = wc_up == code
        rgba[..., 0][m] = r
        rgba[..., 1][m] = g
        rgba[..., 2][m] = b
        rgba[..., 3][m] = 190
    # code 0 / unmapped stays alpha=0 (fully transparent)
    _save_rgba(rgba, out_dir / "worldcover.png")
    classes_present = sorted({int(c) for c in np.unique(wc_int) if c in WC_PALETTE})
    return {
        "legend": "ESA WorldCover 2021 land cover",
        "classes_present": [{"code": c, "name": WC_NAMES[c], "color_rgb": WC_PALETTE[c]} for c in classes_present],
    }


def run(max_scenes: int = 40):
    bounds_gdf = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = bounds_gdf.total_bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)
    log.info("Analysis grid: %d rows x %d cols, bbox=%s", shape[0], shape[1], bbox)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    water_occ, elev, wc_int, scenes_used = fetch_pilot_rasters(bbox, shape, catalog, max_scenes)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sar_meta = export_sar_overlay(water_occ, OUT_DIR)
    dem_meta = export_dem_overlay(elev, OUT_DIR)
    wc_meta = export_worldcover_overlay(wc_int, OUT_DIR)

    # folium.raster_layers.ImageOverlay wants bounds as [[south, west], [north, east]].
    # Must be the PADDED bbox actually rasterized (not the unpadded boundary bounds),
    # or the overlay will be visibly offset from the risk-zone polygons on the map.
    manifest = {
        "bounds": [[bbox[1], bbox[0]], [bbox[3], bbox[2]]],
        "scenes_used": scenes_used,
        "layers": {
            "sar_water_occurrence": {"file": "sar_water_occurrence.png", **sar_meta},
            "dem_elevation": {"file": "dem_elevation.png", **dem_meta},
            "worldcover": {"file": "worldcover.png", **wc_meta},
        },
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("Saved -> %s", OUT_DIR / "manifest.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export raw geospatial layers as map overlay PNGs")
    parser.add_argument("--scenes", type=int, default=40, help="Max S1 scenes to process (default 40)")
    args = parser.parse_args()
    run(max_scenes=args.scenes)
