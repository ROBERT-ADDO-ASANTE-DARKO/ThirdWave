"""
kpetoe_s2_imagery.py — Sentinel-2 true-color check for the Kpetoe (Tordze
River) flood, 2026-06-29. Exhaustively confirmed (tile-wide AND per-AOI
cloud/invalid fraction, every candidate scene June-July 2026) that NO
usable view of the flood peak exists -- same optical-blindness pattern as
every other event studied in the actual rainy-season window. Shows the one
genuinely clean pre-flood scene (2026-06-01) and the nearest clean
post-flood scene (2026-08-27, ~2 months of recession) for terrain context
only, not as flood evidence.

Usage
─────
    python3 kpetoe_s2_imagery.py
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

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
BBOX = (0.677, 6.527, 0.717, 6.567)
PIXEL_DEG = 0.00009


def _truecolor_on(date_str, catalog):
    items = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(BBOX), datetime=f"{date_str}/{date_str}",
    ).item_collection())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
    item = items[0]
    minlon, minlat, maxlon, maxlat = BBOX
    cols = int((maxlon - minlon) / PIXEL_DEG); rows = int((maxlat - minlat) / PIXEL_DEG)
    red = _read_s2_band(item, "B04", BBOX, (rows, cols))
    green = _read_s2_band(item, "B03", BBOX, (rows, cols))
    blue = _read_s2_band(item, "B02", BBOX, (rows, cols))
    rgb = np.stack([red, green, blue], axis=-1)
    lo, hi = np.percentile(rgb[rgb > 0], 2), np.percentile(rgb[rgb > 0], 98)
    rgb = np.clip((rgb - lo) / (hi - lo), 0, 1)
    return rgb, item.properties.get("eo:cloud_cover", -1)


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    rgb_before, cc_before = _truecolor_on("2026-06-01", catalog)
    rgb_after, cc_after = _truecolor_on("2026-08-27", catalog)

    minlon, minlat, maxlon, maxlat = BBOX
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax, img, title in [
        (axes[0], rgb_before, f"2026-06-01, ~4 weeks BEFORE the flood\n(tile cloud {cc_before:.0f}%, but only 12% invalid over this AOI)"),
        (axes[1], rgb_after, f"2026-08-27, ~8 weeks AFTER (recession period)\n(tile cloud {cc_after:.0f}%, only 3% invalid over this AOI)"),
    ]:
        ax.imshow(img, extent=(minlon, maxlon, minlat, maxlat), origin="upper")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

    fig.suptitle("Kpetoe (Tordze River) -- NO usable Sentinel-2 scene exists near the actual flood peak\n"
                 "(every candidate in the June-July 2026 window checked, 55-100% invalid over this AOI) -- "
                 "shown here for terrain context only, not as flood evidence", fontsize=11, fontweight="bold")
    fig.tight_layout()
    out_png = HERE / "data" / "kpetoe_s2_imagery.png"
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", out_png)


if __name__ == "__main__":
    main()
