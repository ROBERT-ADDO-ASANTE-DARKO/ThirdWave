"""
prototype_drain_capacity_integration.py — capability demo: what would
change in this project's scoring pipeline if we had a REAL drain-capacity
dataset (like the one we're pursuing from GARID for the Odaw basin), using
a real, openly-licensed drainage network from a different country as a
stand-in while that data-sharing conversation is pending.

NOT Accra data. This runs entirely against Māngere, Auckland, New Zealand
-- chosen because (a) Auckland Council publishes its full stormwater pipe
network as genuine open data (CC BY 4.0, Healthy Waters / Auckland
Council -- see https://data-aucklandcouncil.opendata.arcgis.com), with
real per-pipe diameter/material/status attributes GARID's eventual data
would plausibly resemble, and (b) Māngere was one of the areas hit hardest
in the real January 2023 Auckland floods, so it's a genuine flood-prone
ROI, not an arbitrary test area. None of this should be read as a claim
about Auckland's actual flood risk or about Accra -- it's a rehearsal of
the integration pattern, using real engineering data because a synthetic
one would prove nothing about whether our pipeline can actually consume it.

What this demonstrates: the existing Accra pipeline
(geospatial_vulnerability.py) fuses SAR + DEM + WorldCover into a
weighted composite. This script fetches the SAME kind of DEM data (via
the same Planetary Computer / rasterio code path) for Māngere, adds a NEW
drain-capacity term computed from Auckland's real pipe network (nearest
pipe distance + that pipe's diameter), and combines them into a demo
"adjusted vulnerability" score -- showing exactly where a real GARID
capacity layer would plug into the Accra pipeline once obtained: as a
drop-in weighted term, using the same grid/scoring architecture already
built, not a redesign.

Usage
─────
    python3 prototype_drain_capacity_integration.py
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio.features
import requests
from shapely.geometry import shape, Point, box
from shapely.strtree import STRtree

import pystac_client
import planetary_computer

from geospatial_vulnerability import _grid_shape, _make_transform, _read_dem_window

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "prototype_drain_capacity"

# Māngere, Auckland, NZ -- real 2023-flood-affected suburb, used ONLY as a
# stand-in ROI to test the integration pattern (see module docstring).
BBOX = (174.7795292, -36.9907502, 174.8195292, -36.9507502)  # minlon, minlat, maxlon, maxlat
PIXEL_DEG = 0.0009  # ~100m, same resolution as the Accra pilot grid

AUCKLAND_PIPES_URL = "https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/Stormwater_Pipe/FeatureServer/0/query"

# Demo weights ONLY -- illustrative, not derived/validated the way the
# real Accra weights were. The point is the integration slot, not the
# specific numbers.
W_LOW_ELEV = 0.5
W_DRAIN_DEFICIENCY = 0.5
MAX_RELEVANT_DIST_M = 200.0   # beyond this, "far from any pipe" saturates
MAX_RELEVANT_DIAMETER_MM = 600.0  # at/above this, "undersized" saturates at 0


def fetch_auckland_pipes(bbox) -> gpd.GeoDataFrame:
    """Real Auckland Council open data (CC BY 4.0) -- pipe geometry plus
    genuine engineering attributes (diameter, material, status)."""
    minlon, minlat, maxlon, maxlat = bbox
    geom = {"xmin": minlon, "ymin": minlat, "xmax": maxlon, "ymax": maxlat,
            "spatialReference": {"wkid": 4326}}
    params = {
        "geometry": json.dumps(geom), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "SW_DIAMETER_MM,SW_MATERIAL,SW_STATUS",
        "outSR": 4326, "f": "geojson", "resultRecordCount": 2000,
    }
    resp = requests.get(AUCKLAND_PIPES_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    log.info("Fetched %d real Auckland stormwater pipe segments (CC BY 4.0, Auckland Council)",
              len(data.get("features", [])))
    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    gdf = gdf[gdf["SW_DIAMETER_MM"].notna()].reset_index(drop=True)
    return gdf


def drain_deficiency_grid(pipes_gdf: gpd.GeoDataFrame, bbox, shape_rc):
    """Per-cell drain-deficiency score in [0, 1]: 1 = far from any mapped
    pipe AND/OR that nearest pipe is small-diameter; 0 = close to a large
    pipe. This is the NEW term a real capacity dataset (GARID's, or this
    Auckland stand-in) makes possible -- the current Accra pipeline has no
    equivalent, using OSM building-to-waterway distance as a much cruder
    proxy instead (see channel_encroachment_index.py)."""
    rows, cols = shape_rc
    minlon, minlat, maxlon, maxlat = bbox
    lons = np.linspace(minlon, maxlon, cols)
    lats = np.linspace(maxlat, minlat, rows)  # north-up, row 0 = max lat

    # Project to a local metric approximation (good enough at this scale)
    lat0 = (minlat + maxlat) / 2
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat0))

    pipe_geoms = list(pipes_gdf.geometry)
    diameters = pipes_gdf["SW_DIAMETER_MM"].to_numpy()
    tree = STRtree(pipe_geoms)

    deficiency = np.zeros(shape_rc, dtype=np.float64)
    for r, lat in enumerate(lats):
        for c, lon in enumerate(lons):
            pt = Point(lon, lat)
            idx = tree.nearest(pt)
            nearest_geom = pipe_geoms[idx]
            diam_mm = diameters[idx]
            dist_deg = pt.distance(nearest_geom)
            dist_m = ((dist_deg * m_per_deg_lon) ** 2 + (dist_deg * m_per_deg_lat) ** 2) ** 0.5

            dist_term = min(dist_m / MAX_RELEVANT_DIST_M, 1.0)
            size_term = 1.0 - min(diam_mm / MAX_RELEVANT_DIAMETER_MM, 1.0)
            deficiency[r, c] = max(dist_term, size_term)  # either being far OR undersized is enough to flag
    return deficiency


def run():
    log.info("Bbox (Mangere, Auckland, NZ -- demo ROI, NOT Accra): %s", BBOX)
    shape_rc = _grid_shape(BBOX, PIXEL_DEG)
    log.info("Grid: %d rows x %d cols", *shape_rc)

    pipes_gdf = fetch_auckland_pipes(BBOX)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    log.info("Fetching real Copernicus DEM for the same ROI (same code path as the Accra pipeline)...")
    elev = _read_dem_window(catalog, BBOX, shape_rc)

    log.info("Computing drain-deficiency grid from real Auckland pipe network...")
    deficiency = drain_deficiency_grid(pipes_gdf, BBOX, shape_rc)

    low_elev_mask = (elev <= 5.0).astype(np.float64)

    adjusted_score = np.clip(
        (W_LOW_ELEV * low_elev_mask + W_DRAIN_DEFICIENCY * deficiency) * 100, 0, 100
    )

    transform = _make_transform(BBOX, shape_rc)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    features = []
    cell_deg = PIXEL_DEG
    minlon, minlat, maxlon, maxlat = BBOX
    rows, cols = shape_rc
    for r in range(rows):
        for c in range(cols):
            lat_top = maxlat - r * cell_deg
            lat_bot = lat_top - cell_deg
            lon_left = minlon + c * cell_deg
            lon_right = lon_left + cell_deg
            cell = box(lon_left, lat_bot, lon_right, lat_top)
            features.append({
                "type": "Feature",
                "geometry": cell.__geo_interface__,
                "properties": {
                    "row": r, "col": c,
                    "elevation_m": round(float(elev[r, c]), 1),
                    "low_elevation": bool(low_elev_mask[r, c]),
                    "drain_deficiency": round(float(deficiency[r, c]), 3),
                    "adjusted_score": round(float(adjusted_score[r, c]), 1),
                },
            })

    out_geojson = {"type": "FeatureCollection", "features": features}
    (OUT_DIR / "mangere_demo_grid.geojson").write_text(json.dumps(out_geojson))
    log.info("Saved -> %s", OUT_DIR / "mangere_demo_grid.geojson")

    summary = {
        "roi": "Mangere, Auckland, New Zealand -- NOT Accra, demo/prototype only",
        "purpose": "Rehearses integrating a real drain-capacity dataset into the composite scoring "
                   "pattern already used for the Accra pilot, ahead of obtaining equivalent GARID data.",
        "pipe_source": "Auckland Council Stormwater Pipe (CC BY 4.0), "
                        "https://data-aucklandcouncil.opendata.arcgis.com/datasets/stormwater-pipe",
        "n_pipes_used": len(pipes_gdf),
        "diameter_mm_range": [int(pipes_gdf["SW_DIAMETER_MM"].min()), int(pipes_gdf["SW_DIAMETER_MM"].max())],
        "grid_cells": int(rows * cols),
        "mean_adjusted_score": round(float(adjusted_score.mean()), 1),
        "max_adjusted_score": round(float(adjusted_score.max()), 1),
        "formula": f"adjusted_score = clip(({W_LOW_ELEV} x low_elevation + {W_DRAIN_DEFICIENCY} x drain_deficiency) x 100, 0, 100) "
                   "-- illustrative weights, not validated the way the real Accra weights were.",
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    log.info("Saved -> %s", OUT_DIR / "summary.json")
    log.info("Mean adjusted score: %.1f, max: %.1f", summary["mean_adjusted_score"], summary["max_adjusted_score"])


if __name__ == "__main__":
    run()
