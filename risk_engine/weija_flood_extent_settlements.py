"""
weija_flood_extent_settlements.py — the March 2017 Weija Dam spillage flood
extent (MNDWI, the richest/cleanest result of any Weija event studied in
this project -- see dam_spillage_s2_mndwi.py) overlaid on a real Sentinel-2
true-color basemap, with surrounding named settlements labelled, so the
flood extent can be read against real places rather than just a bbox.

Wider bbox than the Tetegu-only crops (weija_s2_truecolor.py etc.) --
several communities named in the historical flood reports (Oblogo, Weija
town, Bojo Beach, Pambros Salt) sit outside that tighter crop and outside
the SAR/MNDWI analysis bbox used elsewhere in this project, so this uses
its own wider window built specifically to include them.

Usage
─────
    python3 weija_flood_extent_settlements.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

import pystac_client
import planetary_computer

from weija_s2_truecolor import fetch_truecolor
from dam_spillage_s2_mndwi import _load_scene, _water, _despeckle, _pixel_area_km2

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "weija_flood_extent_settlements.png"

# Wide enough to include Weija town/reservoir, Oblogo and Pambros Salt,
# none of which fit in the tighter Tetegu-only crop. Stops at lat 5.513,
# just north of the open coastline -- MNDWI is unreliable over open
# seawater (sun glint makes it swing between "water" and "land" scene to
# scene, confirmed empirically: one scene read the ocean as 99.8% land,
# another as 90% water), so the Gulf of Guinea itself is deliberately
# excluded rather than numerically patched around.
BBOX = (-0.345, 5.513, -0.270, 5.585)

SETTLEMENTS = {
    "Tetegu": (-0.3061774, 5.5483218),
    "Oblogo": (-0.3220404, 5.5673816),
    "Weija": (-0.3306792, 5.5792263),
    "Pambros Salt": (-0.2835777, 5.5407071),
    "Lower McCarthy Hill / Lower Weija": (-0.2968358, 5.5556316),
    # Bojo Beach (5.5079002N) excluded -- sits in/right at the open-coast
    # strip this bbox now cuts off, for the MNDWI sun-glint reason above.
}

# Re-checked for THIS wider, ocean-excluded bbox specifically -- the narrow
# Tetegu-crop dates (Jan 27 / May 1) aren't as clean once the area covers
# Weija town, Oblogo and Pambros Salt too; these are the actual best
# AOI-checked options for this specific extent (~20% invalid each).
FLOOD_SCENES = {"baseline": "2017-01-04", "peak": "2017-04-17"}


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    log.info("Fetching true-color basemap over the wide AOI...")
    rgb, basemap_date, basemap_cc = fetch_truecolor(BBOX, catalog)

    log.info("Recomputing the March 2017 flood extent (MNDWI) over this wider bbox...")
    mndwi_base, date_base, cloud_base = _load_scene(catalog, BBOX, FLOOD_SCENES["baseline"], search_days=2)
    mndwi_peak, date_peak, cloud_peak = _load_scene(catalog, BBOX, FLOOD_SCENES["peak"], search_days=2)
    w_base, w_peak = _water(mndwi_base), _water(mndwi_peak)
    both = np.isfinite(mndwi_base) & np.isfinite(mndwi_peak)
    new_flood = _despeckle(w_peak & ~w_base & both)
    px_km2 = _pixel_area_km2(BBOX, new_flood.shape)
    log.info("Flood extent over wide AOI: %.1f km2 (baseline %s, peak %s)",
              new_flood.sum() * px_km2, date_base, date_peak)

    minlon, minlat, maxlon, maxlat = BBOX
    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(rgb, extent=(minlon, maxlon, minlat, maxlat), origin="upper")

    flood_rgba = np.zeros((*new_flood.shape, 4))
    flood_rgba[new_flood] = [1.0, 0.1, 0.1, 0.55]
    ax.imshow(flood_rgba, extent=(minlon, maxlon, minlat, maxlat), origin="upper")

    for name, (lon, lat) in SETTLEMENTS.items():
        ax.scatter([lon], [lat], s=70, facecolor="yellow", edgecolor="black", linewidth=1.2, zorder=6)
        ax.annotate(name, (lon, lat), xytext=(7, 7), textcoords="offset points",
                    fontsize=9, color="white", fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=2.5, foreground="black")], zorder=7)

    ax.set_xlim(minlon, maxlon); ax.set_ylim(minlat, maxlat)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_title(
        f"Weija Dam spillage flood extent (March 2017 event) over real Sentinel-2 imagery\n"
        f"basemap: {basemap_date} ({basemap_cc:.0f}% cloud)  ·  flood: MNDWI new-water {date_base}→{date_peak} "
        f"({new_flood.sum() * px_km2:.1f} km², lower bound)\n"
        "Red = new flood extent  ·  yellow = named settlement from historical flood reports\n"
        "(Bojo Beach excluded -- MNDWI unreliable over open seawater due to sun glint)",
        fontsize=10,
    )
    fig.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    main()
