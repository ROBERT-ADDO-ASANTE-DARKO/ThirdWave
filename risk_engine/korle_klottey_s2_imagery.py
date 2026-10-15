"""
korle_klottey_s2_imagery.py — real Sentinel-2 true-color AND NIR
false-color crops over the two strongest channel-encroachment clusters in
Korle Klottey Municipal: Christiansborg/La (0.0m minimum building-to-
waterway distance, up to 980 buildings in one cell -- the worst numeric
finding) and Adabraka (0.3m, up to 1,070 buildings, and just 0.35km from
three documented historical events: the 2015 Kwame Nkrumah Circle flood +
explosion, the March 2023 Accra flood, and the June 2026 Accra floods --
the strongest historical-record match of this district's clusters).

Korle Klottey has the highest encroachment ratio of any district checked
this session: 25 of 26 computable cells (96%) rate "Very High", spread
across four distinct areas (Christiansborg/La, Kanda, Adabraka,
Osu/Ringway) -- Kanda and Osu/Ringway are left as index-only for now, same
discipline as other districts' lower-priority clusters.

Same template as ablekuma_central_s2_imagery.py (one bbox per site, run
in sequence).

Usage
─────
    python3 korle_klottey_s2_imagery.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import requests
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
MAX_CLOUD = 10.0
PIXEL_DEG = 0.00009

SITES = [
    {
        "key": "christiansborg", "out_name": "korle_klottey_christiansborg_s2_imagery.png",
        "bbox": (-0.1824, 5.5438, -0.1729, 5.5668),
        "title": "Christiansborg/La cluster (Korle Klottey Municipal) -- worst encroachment finding in the district\n"
                 "up to 980 buildings/cell, min distance 0.0m; no documented historical flood event nearby",
    },
    {
        "key": "adabraka", "out_name": "korle_klottey_adabraka_s2_imagery.png",
        "bbox": (-0.2184, 5.5618, -0.2044, 5.5758),
        "title": "Adabraka cluster (Korle Klottey Municipal) -- 0.3m min distance, up to 1,070 buildings\n"
                 "0.35km from the 2015 Circle flood+explosion, March 2023, and June 2026 Accra floods",
    },
]


def fetch_osm_overlay(bbox):
    """OSM building footprints + waterway lines for this bbox -- same
    query/parsing pattern used for every other ground-truth check in this
    project."""
    minlon, minlat, maxlon, maxlat = bbox
    query = f"""
    [out:json][timeout:60];
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


def _pick_clean_scene(bbox, catalog):
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
    for candidate in items[:6]:
        red_check = _read_s2_band(candidate, "B04", bbox, (rows, cols))
        nodata_frac = float((red_check == 0).mean())
        if nodata_frac < 0.01:
            return candidate, (rows, cols)
        log.info("  %s has %.0f%% no-data, trying next", candidate.properties["datetime"][:10], nodata_frac * 100)
    return items[0], (rows, cols)


def _composite(item, bbox, shape, bands):
    arrs = [_read_s2_band(item, b, bbox, shape) for b in bands]
    rgb = np.stack(arrs, axis=-1)
    lo, hi = np.percentile(rgb[rgb > 0], 2), np.percentile(rgb[rgb > 0], 98)
    return np.clip((rgb - lo) / (hi - lo), 0, 1)


def run_site(catalog, site):
    bbox = site["bbox"]
    item, shape = _pick_clean_scene(bbox, catalog)
    date = item.properties["datetime"][:10]
    cc = item.properties.get("eo:cloud_cover", -1)
    log.info("%s: using scene %s (cloud=%.1f%%)", site["key"], date, cc)

    truecolor = _composite(item, bbox, shape, ["B04", "B03", "B02"])
    falsecolor = _composite(item, bbox, shape, ["B08", "B04", "B03"])
    waterways, buildings = fetch_osm_overlay(bbox)

    minlon, minlat, maxlon, maxlat = bbox
    fig, axes = plt.subplots(2, 2, figsize=(14, 13))

    for ax, img, title in [
        (axes[0][0], truecolor, f"True color, {date} ({cc:.0f}% cloud)"),
        (axes[0][1], truecolor, "True color + OSM overlay"),
        (axes[1][0], falsecolor, "False color (NIR-Red-Green)\nvegetation=red/pink, water/moisture=dark"),
        (axes[1][1], falsecolor, "False color + OSM overlay"),
    ]:
        ax.imshow(img, extent=(minlon, maxlon, minlat, maxlat), origin="upper")
        ax.set_xlim(minlon, maxlon); ax.set_ylim(minlat, maxlat)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")

    for ax in (axes[0][1], axes[1][1]):
        for coords in buildings:
            xs, ys = zip(*coords)
            ax.plot(xs, ys, color="#39ff6a", linewidth=0.5, alpha=0.75)
        for coords in waterways:
            xs, ys = zip(*coords)
            ax.plot(xs, ys, color="#00d4ff", linewidth=2.2, alpha=0.95)

    fig.suptitle(site["title"], fontsize=12, fontweight="bold")
    fig.tight_layout()
    out_png = HERE / "data" / site["out_name"]
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", out_png)


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    for site in SITES:
        run_site(catalog, site)


if __name__ == "__main__":
    main()
