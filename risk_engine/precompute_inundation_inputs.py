"""
precompute_inundation_inputs.py — One-time fetch of the DEM + WorldCover
rasters needed by the pluvial inundation approximation (see
streamlit_app/inundation_model.py), saved as a compact .npz so the
Streamlit app never needs live Planetary Computer access.

Deliberately does NOT fetch Sentinel-1 (fetch_pilot_rasters() always does,
since it's shared with geospatial_vulnerability.py's scoring pipeline) --
the inundation approximation only needs terrain (DEM) and surface type
(WorldCover, for a runoff coefficient), so this calls the DEM/WorldCover
readers directly and skips the slow SAR fetch entirely.

Usage
─────
    python3 precompute_inundation_inputs.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import geopandas as gpd

import pystac_client
import planetary_computer

from geospatial_vulnerability import (
    PILOT_BOUNDARY, PIXEL_DEG, _grid_shape, _read_dem_window, _read_worldcover,
)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "inundation_inputs.npz"


def run():
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

    log.info("Fetching Copernicus DEM ...")
    elev = _read_dem_window(catalog, bbox, shape)
    log.info("Elevation range: %.1f - %.1f m", float(np.nanmin(elev)), float(np.nanmax(elev)))

    log.info("Fetching ESA WorldCover 2021 ...")
    worldcover = _read_worldcover(catalog, bbox, shape)
    wc_int = worldcover.astype(np.uint8)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUTPUT,
        dem=elev.astype(np.float32),
        worldcover=wc_int,
        bbox=np.array(bbox, dtype=np.float64),
    )
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    run()
