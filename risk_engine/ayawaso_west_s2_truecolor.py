"""
ayawaso_west_s2_truecolor.py — real Sentinel-2 true-color (RGB) crop over the
two adjacent "Very High" encroachment cells (ext_c2_r11_c13, ext_c2_r12_c13,
444+412 buildings, min building-to-waterway distance 0.0m per OSM), with the
actual OSM waterway line(s) and building footprints overlaid -- so the
encroachment claim can be checked against a real visible-light image, not
just a number.

Free, public, 10m native resolution (B04/B03/B02) via Planetary Computer --
same source/method as sentinel2_clearday_baseline.py's MNDWI fetch, same
clearest-scenes selection, just true-color bands instead of B03/B11.

Usage
─────
    python3 ayawaso_west_s2_truecolor.py
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import rasterio.enums
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

import pystac_client
import planetary_computer

from sentinel2_crossvalidation import _read_s2_band

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "ayawaso_west_encroachment_truecolor.png"

# Padded bbox around ext_c2_r11_c13 + ext_c2_r12_c13 (both 0.0m min-distance cells)
BBOX = (-0.1664, 5.6446, -0.1559, 5.6596)
MAX_CLOUD = 10.0
PIXEL_DEG = 0.00009  # ~10m, native S2 visible-band resolution


def fetch_truecolor(bbox, catalog):
    items = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(bbox), datetime="2023-01-01/2026-10-13",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
    ).item_collection())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
    if not items:
        raise RuntimeError("no low-cloud S2 scene found")

    minlon, minlat, maxlon, maxlat = bbox
    cols = int((maxlon - minlon) / PIXEL_DEG)
    rows = int((maxlat - minlat) / PIXEL_DEG)

    # Clearest scenes can still have a real no-data gap near their swath/tile
    # edge (confirmed on 2024-01-16: 15.8% zero pixels, not a bug) -- try a
    # few, in cloud-ascending order, until one has full coverage over this
    # small AOI instead of silently accepting a partially-empty scene.
    item = None
    for candidate in items[:6]:
        red_check = _read_s2_band(candidate, "B04", bbox, (rows, cols))
        nodata_frac = float((red_check == 0).mean())
        date_c = candidate.properties["datetime"][:10]
        if nodata_frac < 0.01:
            item = candidate
            break
        log.info("  %s has %.0f%% no-data over this AOI, trying next scene", date_c, nodata_frac * 100)
    if item is None:
        item = items[0]
        log.warning("No fully-clean scene found in the top candidates, falling back to lowest-cloud")

    date = item.properties["datetime"][:10]
    cc = item.properties.get("eo:cloud_cover", -1)
    log.info("Using scene %s (cloud=%.1f%%)", date, cc)

    red = _read_s2_band(item, "B04", bbox, (rows, cols))
    green = _read_s2_band(item, "B03", bbox, (rows, cols))
    blue = _read_s2_band(item, "B02", bbox, (rows, cols))

    rgb = np.stack([red, green, blue], axis=-1)
    # Simple percentile stretch for a viewable true-color image (raw S2 reflectance is dim)
    lo, hi = np.percentile(rgb[rgb > 0], 2), np.percentile(rgb[rgb > 0], 98)
    rgb = np.clip((rgb - lo) / (hi - lo), 0, 1)
    return rgb, date, cc


def fetch_osm_overlay(bbox):
    minlon, minlat, maxlon, maxlat = bbox
    query = f"""
    [out:json][timeout:30];
    (
      way["waterway"]({minlat},{minlon},{maxlat},{maxlon});
      way["building"]({minlat},{minlon},{maxlat},{maxlon});
    );
    out geom;
    """
    elements = []
    for attempt in range(4):
        try:
            resp = requests.post("https://overpass-api.de/api/interpreter", data=query,
                                  headers={"User-Agent": "ThirdWave-risk-engine/1.0 (research prototype)"}, timeout=60)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except Exception as exc:
            log.warning("Overpass fetch failed (attempt %d/4: %s)", attempt + 1, exc)
    else:
        log.warning("Overpass fetch failed after 4 attempts -- overlay will be empty")
    waterways, buildings = [], []
    for e in elements:
        tags = e.get("tags", {})
        geom = e.get("geometry")
        if not geom:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom]
        if tags.get("waterway") and len(coords) >= 2:
            waterways.append(coords)
        elif tags.get("building") and len(coords) >= 3:
            buildings.append(coords)
    log.info("OSM overlay: %d waterway segments, %d buildings", len(waterways), len(buildings))
    return waterways, buildings


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    rgb, date, cc = fetch_truecolor(BBOX, catalog)
    waterways, buildings = fetch_osm_overlay(BBOX)

    minlon, minlat, maxlon, maxlat = BBOX
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2))

    for ax in axes:
        ax.imshow(rgb, extent=(minlon, maxlon, minlat, maxlat), origin="upper")
        ax.set_xlim(minlon, maxlon); ax.set_ylim(minlat, maxlat)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

    axes[0].set_title(f"Sentinel-2 true color, {date} ({cc:.0f}% cloud)\n"
                       "(no overlay -- see for yourself first)", fontsize=10)

    for coords in buildings:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#39ff6a", linewidth=0.6, alpha=0.8)
    for coords in waterways:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#00d4ff", linewidth=2.2, alpha=0.95)
    axes[1].set_title("Same image + OSM overlay\ngreen = building footprints, cyan = mapped waterway", fontsize=10)

    fig.suptitle("Ayawaso West (East Legon Hills area) -- real imagery check on the \"0.0m\" encroachment cells\n"
                 f"cells ext_c2_r11_c13 / ext_c2_r12_c13, bbox {BBOX}", fontsize=11, fontweight="bold")
    fig.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    main()
