"""
adafoah_s2_imagery.py — real Sentinel-2 true-color AND NIR false-color
crops over the Ada Foah area (Ada East, lv_r8_c156 / lv_r9_c156), near
where the Volta meets the Gulf of Guinea -- same treatment as
sogakope_s2_imagery.py / akuse_s2_imagery.py / juapong_s2_imagery.py.

Usage
─────
    python3 adafoah_s2_imagery.py
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
BBOX = (0.605, 5.797, 0.625, 5.817)  # Ada Foah area, Ada East, near the Volta estuary/river mouth
MAX_CLOUD = 10.0
PIXEL_DEG = 0.00009


def fetch_osm_overlay(bbox):
    """OSM building footprints + waterway lines for this bbox -- same
    query/parsing pattern used for the Tetegu and East Legon ground-truth
    checks elsewhere in this project."""
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


def main():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    item, shape = _pick_clean_scene(BBOX, catalog)
    date = item.properties["datetime"][:10]
    cc = item.properties.get("eo:cloud_cover", -1)
    log.info("Using scene %s (cloud=%.1f%%)", date, cc)

    truecolor = _composite(item, BBOX, shape, ["B04", "B03", "B02"])
    falsecolor = _composite(item, BBOX, shape, ["B08", "B04", "B03"])
    waterways, buildings = fetch_osm_overlay(BBOX)

    minlon, minlat, maxlon, maxlat = BBOX
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

    fig.suptitle("Ada Foah area (Ada East) -- Lower Volta channel-encroachment hit, near the river mouth\n"
                 "122 + 159 buildings across two adjacent cells, min distance 9.4m to a mapped waterway", fontsize=12, fontweight="bold")
    fig.tight_layout()
    out_png = HERE / "data" / "adafoah_s2_imagery.png"
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    log.info("Saved -> %s", out_png)


if __name__ == "__main__":
    main()
