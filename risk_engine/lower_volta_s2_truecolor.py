"""
lower_volta_s2_truecolor.py — real Sentinel-2 true-color (RGB) crops over
the worst documented channel-encroachment cell in each of the 7 Lower
Volta extended-coverage assemblies (lower_volta_channel_encroachment_index.json)
-- Asuogyaman, Lower Manya, North Tongu, South Tongu, Ada East, Ada West,
Central Tongu -- closing the same satellite-evidence gap
pilot_sites_s2_truecolor.py closed for the 3 pilot assemblies that had no
imagery yet. Same treatment, same reused fetch_truecolor()/
fetch_osm_overlay() from ayawaso_west_s2_truecolor.py rather than a
fourth copy of the same code.

Each site is the assembly's worst "ok"-status encroachment cell, EXCEPT
Central Tongu: its true worst cell (lv_r63_c122, 27.2m) reverse-geocodes
to North Tongu District, not Central Tongu -- the same buffered-grid-
edge-spillover failure mode backend/geo_data.py's _confirm_extended_assembly()
already guards point lookups against (see that function's docstring).
Rather than publish a mislabeled "Central Tongu" image, this picked the
next-worst cell that reverse-geocodes to Central Tongu itself (Adidome,
its own district capital, 37.2m -- still a real "Moderate" encroachment
score).

Free, public, 10m native resolution (B04/B03/B02) via Planetary Computer.
Picks the clearest, most complete (no no-data gap) scene available, same
discipline as the other scripts.

Usage
─────
    python3 lower_volta_s2_truecolor.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pystac_client
import planetary_computer

from ayawaso_west_s2_truecolor import fetch_osm_overlay, fetch_truecolor

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent

# Each bbox is ~0.011deg square, padded symmetrically around that
# assembly's chosen encroachment cell's centroid (from
# lower_volta_channel_encroachment_index.json + lower_volta_risk_grid.geojson
# via geo_data.lower_volta_channel_encroachment_index(), cross-checked
# against a live Nominatim reverse-geocode) -- same padding scale every
# other *_s2_truecolor.py script in this project uses.
SITES = [
    {
        "output": HERE / "data" / "asuogyaman_akosombo_truecolor.png",
        "title": "Akosombo / Asuogyaman -- worst documented encroachment cell (0.0m)",
        "zone_id": "lv_r117_c32",
        "bbox": (0.051175, 6.292273, 0.062175, 6.303273),
    },
    {
        "output": HERE / "data" / "lower_manya_akuse_truecolor.png",
        "title": "Akuse / Lower Manya Krobo Municipal -- worst documented encroachment cell (1.8m)",
        "zone_id": "lv_r77_c47",
        "bbox": (0.118742, 6.112093, 0.129742, 6.123093),
    },
    {
        "output": HERE / "data" / "north_tongu_juapong_truecolor.png",
        "title": "Juapong / North Tongu -- worst documented encroachment cell (3.6m)",
        "zone_id": "lv_r109_c50",
        "bbox": (0.132256, 6.256237, 0.143256, 6.267237),
    },
    {
        "output": HERE / "data" / "south_tongu_sokpoe_truecolor.png",
        "title": "Sokpoe / South Tongu -- worst documented encroachment cell (5.4m)",
        "zone_id": "lv_r51_c149",
        "bbox": (0.578202, 5.994976, 0.589202, 6.005976),
    },
    {
        "output": HERE / "data" / "ada_east_bigada_truecolor.png",
        "title": "Big Ada / Ada East -- worst documented encroachment cell (9.4m)",
        "zone_id": "lv_r8_c156",
        "bbox": (0.609733, 5.801282, 0.620733, 5.812282),
    },
    {
        "output": HERE / "data" / "ada_west_matsekope_truecolor.png",
        "title": "Matsekope / Ada West -- worst documented encroachment cell (17.6m)",
        "zone_id": "lv_r22_c118",
        "bbox": (0.438562, 5.864345, 0.449562, 5.875345),
    },
    {
        "output": HERE / "data" / "central_tongu_adidome_truecolor.png",
        "title": "Adidome / Central Tongu -- worst Central-Tongu-confirmed encroachment cell (37.2m)",
        "zone_id": "lv_r63_c123",
        "bbox": (0.461085, 6.049030, 0.472085, 6.060030),
    },
]


def render_site(site: dict, catalog) -> None:
    bbox = site["bbox"]
    rgb, date, cc = fetch_truecolor(bbox, catalog)
    waterways, buildings = fetch_osm_overlay(bbox)

    minlon, minlat, maxlon, maxlat = bbox
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2))
    for ax in axes:
        ax.imshow(rgb, extent=(minlon, maxlon, minlat, maxlat), origin="upper")
        ax.set_xlim(minlon, maxlon); ax.set_ylim(minlat, maxlat)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

    axes[0].set_title(f"Sentinel-2 true color, {date} ({cc:.0f}% cloud)\n(no overlay -- see for yourself first)",
                       fontsize=10)
    for coords in buildings:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#39ff6a", linewidth=0.6, alpha=0.8)
    for coords in waterways:
        xs, ys = zip(*coords)
        axes[1].plot(xs, ys, color="#00d4ff", linewidth=2.2, alpha=0.95)
    axes[1].set_title("Same image + OSM overlay\ngreen = building footprints, cyan = mapped waterway", fontsize=10)

    fig.suptitle(f"{site['title']}\ncell {site['zone_id']}, bbox {bbox}", fontsize=11, fontweight="bold")
    fig.tight_layout()
    site["output"].parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(site["output"], dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved -> %s", site["output"])


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    for site in SITES:
        log.info("Rendering %s...", site["output"].name)
        render_site(site, catalog)


if __name__ == "__main__":
    main()
