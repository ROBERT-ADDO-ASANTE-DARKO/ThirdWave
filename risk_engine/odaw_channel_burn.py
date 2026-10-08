"""
odaw_channel_burn.py — hydro-enforcement (stream burning) for the pilot
grid's Copernicus DEM, so the pluvial CA proxy (inundation_model.py)
routes water toward the real Odaw/drainage channel network instead of
spreading as uniform sheet flow.

Real, well-known technique (the "AGREE"/stream-burning method, same family
as WhiteboxTools' FillBurn or GRASS r.carve) -- but a real caveat: this
grid is ~100m/pixel (PIXEL_DEG in geospatial_vulnerability.py), so this is
a coarse correction to the EXISTING proxy, not a survey-grade channel
cross-section. It fixes "the model doesn't know the Odaw exists at all",
not "the model knows the Odaw's true depth/width".

Channel geometry: OSM waterway ways (river/canal/drain/stream) via
Overpass -- same free source already used elsewhere in this project
(channel_encroachment_index.py), not a new dependency.

Usage
─────
    python3 odaw_channel_burn.py          # standalone sanity check / diagnostic plot
    (normally imported by precompute_inundation_inputs.py)
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import rasterio.features
import requests

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
WATERWAY_TAGS = ["river", "canal", "drain", "stream"]
BURN_DEPTH_M = 2.0  # lower the DEM this much along the channel path -- see module docstring on why this
                     # is a coarse hydro-enforcement nudge, not a surveyed channel depth


def fetch_waterways(bbox):
    """OSM waterway ways (river/canal/drain/stream) within bbox, as a list
    of [(lon, lat), ...] polylines. Returns [] on any failure -- the caller
    treats that as 'no burn, keep the original DEM', not a hard error,
    matching every other free-data fetch in this project."""
    minlon, minlat, maxlon, maxlat = bbox
    tag_filter = "".join(f'way["waterway"="{t}"]({minlat},{minlon},{maxlat},{maxlon});' for t in WATERWAY_TAGS)
    query = f"[out:json][timeout:60];({tag_filter});out geom;"
    elements = []
    for attempt in range(3):
        try:
            resp = requests.post(OVERPASS_URL, data=query,
                                  headers={"User-Agent": "ThirdWave-risk-engine/1.0 (research prototype)"}, timeout=70)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except Exception as exc:
            log.warning("Overpass waterway fetch failed (attempt %d/3: %s)", attempt + 1, exc)
    else:
        log.warning("Overpass waterway fetch failed after 3 attempts -- skipping channel burn")
        return []

    lines = []
    for e in elements:
        geom = e.get("geometry")
        if not geom or len(geom) < 2:
            continue
        lines.append([(pt["lon"], pt["lat"]) for pt in geom])
    log.info("Fetched %d waterway segments (river/canal/drain/stream) from OSM", len(lines))
    return lines


def channel_mask(lines, transform, shape):
    """Rasterize waterway polylines onto the grid -- True where a channel
    passes through. all_touched=True so a channel isn't lost between pixel
    centers at this coarse (~100m) resolution."""
    if not lines:
        return np.zeros(shape, dtype=bool)
    shapes = [{"type": "LineString", "coordinates": line} for line in lines if len(line) >= 2]
    if not shapes:
        return np.zeros(shape, dtype=bool)
    burned = rasterio.features.rasterize(
        [(s, 1) for s in shapes], out_shape=shape, transform=transform,
        all_touched=True, fill=0, dtype=np.uint8,
    )
    return burned.astype(bool)


def burn_channel(dem: np.ndarray, bbox, transform) -> tuple[np.ndarray, np.ndarray]:
    """Returns (dem_burned, mask). On fetch failure, dem_burned is just a
    copy of dem and mask is all-False -- callers don't need a separate
    failure path."""
    lines = fetch_waterways(bbox)
    mask = channel_mask(lines, transform, dem.shape)
    dem_burned = dem.copy()
    dem_burned[mask] -= BURN_DEPTH_M
    log.info("Channel burn: %d/%d pixels (%.1f%%) lowered by %.1fm", mask.sum(), mask.size,
              100 * mask.sum() / mask.size, BURN_DEPTH_M)
    return dem_burned, mask


if __name__ == "__main__":
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from geospatial_vulnerability import PILOT_BOUNDARY, PIXEL_DEG, _grid_shape, _make_transform

    bounds_gdf = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = bounds_gdf.total_bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)
    transform = _make_transform(bbox, shape)

    lines = fetch_waterways(bbox)
    mask = channel_mask(lines, transform, shape)
    minlon, minlat, maxlon, maxlat = bbox
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.imshow(mask, extent=(minlon, maxlon, minlat, maxlat), origin="upper", cmap="Blues")
    ax.set_title(f"Channel-burn mask: {mask.sum()} pixels ({len(lines)} OSM waterway segments)")
    fig.savefig("data/odaw_channel_burn_mask.png", dpi=130, bbox_inches="tight")
    log.info("Saved -> data/odaw_channel_burn_mask.png")
