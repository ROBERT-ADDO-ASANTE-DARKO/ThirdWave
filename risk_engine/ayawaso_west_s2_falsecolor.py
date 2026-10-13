"""
ayawaso_west_s2_falsecolor.py — NIR-Red-Green false-color Sentinel-2
composite over the same Ayawaso West hotspot as ayawaso_west_s2_truecolor.py
(ext_c2_r11_c13 / ext_c2_r12_c13), to test whether riparian vegetation along
the mapped waterway resolves more clearly than it did in true color.

NIR -> R, Red -> G, Green -> B: healthy vegetation (strong NIR reflectance)
renders bright red/pink, water/moisture renders near-black. Same free
source/method as the true-color script, same clean-scene selection (skip
any candidate scene with a real no-data gap over this AOI).

Usage
─────
    python3 ayawaso_west_s2_falsecolor.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pystac_client
import planetary_computer

from sentinel2_crossvalidation import _read_s2_band
from ayawaso_west_s2_truecolor import BBOX, PIXEL_DEG, MAX_CLOUD, fetch_osm_overlay

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "ayawaso_west_encroachment_falsecolor.png"


def fetch_falsecolor(bbox, catalog):
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

    nir = _read_s2_band(item, "B08", bbox, (rows, cols))
    red = _read_s2_band(item, "B04", bbox, (rows, cols))
    green = _read_s2_band(item, "B03", bbox, (rows, cols))

    rgb = np.stack([nir, red, green], axis=-1)
    lo, hi = np.percentile(rgb[rgb > 0], 2), np.percentile(rgb[rgb > 0], 98)
    rgb = np.clip((rgb - lo) / (hi - lo), 0, 1)
    return rgb, date, cc


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    rgb, date, cc = fetch_falsecolor(BBOX, catalog)
    waterways, buildings = fetch_osm_overlay(BBOX)

    minlon, minlat, maxlon, maxlat = BBOX
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2))

    for ax in axes:
        ax.imshow(rgb, extent=(minlon, maxlon, minlat, maxlat), origin="upper")
        ax.set_xlim(minlon, maxlon); ax.set_ylim(minlat, maxlat)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

    axes[0].set_title(f"Sentinel-2 false color (NIR-Red-Green), {date} ({cc:.0f}% cloud)\n"
                       "vegetation = bright red/pink, water/moisture = dark", fontsize=10)

    for coords in buildings:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#39ff6a", linewidth=0.5, alpha=0.7)
    for coords in waterways:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#00d4ff", linewidth=2.2, alpha=0.95)
    axes[1].set_title("Same image + OSM overlay\ngreen = building footprints, cyan = mapped waterway", fontsize=10)

    fig.suptitle("Ayawaso West (East Legon Hills area) -- NIR false color vs. the same true-color/SAR crops\n"
                 f"cells ext_c2_r11_c13 / ext_c2_r12_c13, bbox {BBOX}", fontsize=11, fontweight="bold")
    fig.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    main()
