"""
pilot_sites_s2_truecolor.py — real Sentinel-2 true-color (RGB) crops over
the worst documented channel-encroachment cell in each of the 3 pilot
assemblies that had a confirmed "Very High" encroachment score
(channel_encroachment_index.json) but no satellite-evidence image yet --
Ablekuma West (Gbegbeyise), Accra Metropolis (Old Fadama), and Ayawaso
Central (Kokomlemle). Same treatment as weija_s2_truecolor.py/
ayawaso_west_s2_truecolor.py, which already cover the other 6 pilot +
extended-coverage assemblies -- reuses those two scripts' fetch_truecolor()/
fetch_osm_overlay() rather than a third copy of the same code.

Free, public, 10m native resolution (B04/B03/B02) via Planetary Computer.
Picks the clearest, most complete (no no-data gap) scene available, same
discipline as the other two scripts.

Usage
─────
    python3 pilot_sites_s2_truecolor.py
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
# assembly's worst "ok"-status encroachment cell's centroid (from
# channel_encroachment_index.json via geo_data.encroachment_index()) --
# same padding scale weija_s2_truecolor.py/ayawaso_west_s2_truecolor.py
# used around their own hotspot cells.
SITES = [
    {
        "output": HERE / "data" / "ablekuma_west_gbegbeyise_truecolor.png",
        "title": "Gbegbeyise / Ablekuma West Municipal -- worst documented encroachment cell (0.1m)",
        "zone_id": "grid_r12_c38",
        "bbox": (-0.259689, 5.520533, -0.248689, 5.531533),
    },
    {
        "output": HERE / "data" / "accra_metropolis_old_fadama_truecolor.png",
        "title": "Old Fadama / Accra Metropolis -- worst documented encroachment cell (0.2m)",
        "zone_id": "grid_r16_c45",
        "bbox": (-0.228157, 5.538551, -0.217157, 5.549551),
    },
    {
        "output": HERE / "data" / "ayawaso_central_kokomlemle_truecolor.png",
        "title": "Kokomlemle / Ayawaso Central Municipal -- worst documented encroachment cell (0.0m)",
        "zone_id": "grid_r23_c49",
        "bbox": (-0.210139, 5.570082, -0.199139, 5.581082),
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
