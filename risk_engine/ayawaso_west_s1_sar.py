"""
ayawaso_west_s1_sar.py — Sentinel-1 SAR look at the same "0.0m" encroachment
hotspot (ext_c2_r11_c13 / ext_c2_r12_c13) the true-color Sentinel-2 crop
already covered (ayawaso_west_s2_truecolor.py), with the same OSM waterway/
building overlay, so the two free imagery sources can be compared directly
on whether either one resolves a street-level drain.

Single calibrated RTC VV scene at near-native (~10m) resolution, converted
to dB -- same source/method as dam_spillage_sar_comparison.py, just a
static look instead of change detection, and at a far tighter crop than
that script's ~100m analysis grid.

Usage
─────
    python3 ayawaso_west_s1_sar.py
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import odc.stac
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pystac_client
import planetary_computer

from ayawaso_west_s2_truecolor import BBOX, fetch_osm_overlay
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "ayawaso_west_encroachment_sar.png"
S1_COLLECTION = "sentinel-1-rtc"
PIXEL_DEG = 0.0001  # ~11m, near S1 RTC native resolution


def fetch_s1_db(bbox):
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    minlon, minlat, maxlon, maxlat = bbox
    items = list(catalog.search(
        collections=[S1_COLLECTION], bbox=list(bbox), datetime="2026-01-01/2026-10-13",
    ).item_collection())
    if not items:
        raise RuntimeError("no Sentinel-1 RTC scene found over this AOI/date range")
    items.sort(key=lambda it: it.properties["datetime"], reverse=True)
    item = items[0]
    date = item.properties["datetime"][:10]
    log.info("Using S1 RTC scene %s (%s orbit)", date, item.properties.get("sat:orbit_state", "?"))

    ds = odc.stac.load(
        [item], bands=["vv"], crs="EPSG:4326", resolution=PIXEL_DEG,
        x=(minlon, maxlon), y=(minlat, maxlat), chunks={},
    )
    gamma0 = ds["vv"].isel(time=0).values.astype(np.float64)
    db = np.full(gamma0.shape, np.nan, dtype=np.float64)
    good = np.isfinite(gamma0) & (gamma0 > 0)
    db[good] = 10.0 * np.log10(gamma0[good])
    return db, date


def main():
    db, date = fetch_s1_db(BBOX)
    waterways, buildings = fetch_osm_overlay(BBOX)

    minlon, minlat, maxlon, maxlat = BBOX
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2))

    vmin, vmax = np.nanpercentile(db, 2), np.nanpercentile(db, 98)
    for ax in axes:
        ax.imshow(db, extent=(minlon, maxlon, minlat, maxlat), origin="upper",
                   cmap="gray", vmin=vmin, vmax=vmax)
        ax.set_xlim(minlon, maxlon); ax.set_ylim(minlat, maxlat)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

    axes[0].set_title(f"Sentinel-1 RTC VV, {date} (dB)\n(no overlay -- see for yourself first)", fontsize=10)

    for coords in buildings:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#39ff6a", linewidth=0.6, alpha=0.8)
    for coords in waterways:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#ff3399", linewidth=2.2, alpha=0.95)
    axes[1].set_title("Same SAR image + OSM overlay\ngreen = building footprints, magenta = mapped waterway", fontsize=10)

    fig.suptitle("Ayawaso West (East Legon Hills area) -- Sentinel-1 SAR look at the same hotspot\n"
                 f"cells ext_c2_r11_c13 / ext_c2_r12_c13, bbox {BBOX} -- compare against the Sentinel-2 true-color crop",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    main()
