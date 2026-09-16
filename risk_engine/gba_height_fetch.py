"""
gba_height_fetch.py — fetch GlobalBuildingAtlas (GBA.Height, via the
GBA.LoD1 product) building-height points for a bbox, without downloading
the whole ~1GB per-country-region tile.

GlobalBuildingAtlas (Zhu-xlab/DLR-TUM, Sun et al. 2025) is a global,
machine-learning-derived building height product at 3m-class resolution,
built from PlanetScope imagery -- see building_obstruction_height.py's
docstring for how this fits alongside the free CopDEM-FABDEM obstruction
proxy, and project chat history for the full comparison against
Φsat-2/PHDataset and HTC-DC Net/GBH (this is the only one of the three
that's an actual precomputed global product rather than a training
benchmark).

GBA.LoD1 (used here as the height source, since GBA.Height's only listed
host -- mediaTUM -- sits behind an Anubis proof-of-work bot wall this
project doesn't attempt to solve) is distributed on HuggingFace as one
JSON object per 5x5-degree region, keyed by
"google<PlusCode><ISO3-country-code>" -> {"height": meters, "var": ...}.
Confirmed empirically: values are dense enough (~2-3m spacing) to be the
same underlying raster GBA.Height describes, just keyed by Open Location
Code (Plus Code) instead of pixel row/col. -999.0 is the "no data"
sentinel.

A region tile is ~1GB -- far too big to download whole for one small AOI.
Instead this streams the HTTP response through ijson (never holding the
full file in memory) and keeps only keys ending in the requested
country's ISO3 code whose decoded Plus Code falls inside bbox. Checkpoints
every 4M entries scanned so a network hiccup partway through a ~14M-entry
region doesn't lose the whole run.

License: CC BY-NC 4.0 (Sun et al. 2025, TUM/DLR) -- non-commercial,
compatible with this project's current status. The authors' own stated
caveat: "limited availability of height data in Africa for training and
validation" -- i.e. no African LiDAR ground truth backed this model.
Validate before trusting, same as everywhere else in this project (see
gba_building_height.py).

Usage
─────
    from gba_height_fetch import fetch_gba_heights
    points = fetch_gba_heights(bbox, country_iso3="GHA", region_tile="africa/w005_n10_e000_n05")
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import ijson
import requests
from openlocationcode import openlocationcode as olc

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "gba"  # ephemeral, gitignored (see risk_engine/cache/)
BASE_URL = "https://huggingface.co/datasets/zhu-xlab/GBA.LoD1/resolve/main/LoD1"
LICENSE_NOTE = "GlobalBuildingAtlas GBA.LoD1 (Sun et al. 2025, TUM/DLR), CC BY-NC 4.0 -- non-commercial use only."

CHECKPOINT_EVERY = 4_000_000


def _in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    minlon, minlat, maxlon, maxlat = bbox
    return minlon <= lon <= maxlon and minlat <= lat <= maxlat


def fetch_gba_heights(
    bbox: tuple[float, float, float, float],
    country_iso3: str,
    region_tile: str,
    cache_name: str | None = None,
) -> dict:
    """Stream one GBA.LoD1 region tile (e.g. "africa/w005_n10_e000_n05"),
    keep only country_iso3-suffixed keys whose decoded Plus Code falls in
    bbox. Returns {key: {"lat", "lon", "height", "var"}}. Cached to disk
    (cache_name, default derived from bbox+country) so a repeat call for
    the same AOI doesn't re-hit the network for ~10+ minutes.

    Finding the right region_tile: siblings of the zhu-xlab/GBA.LoD1
    HuggingFace dataset are named "<continent>/<w|e><lon0>_<n|s><lat0>_
    <w|e><lon1>_<n|s><lat1>.json" on a 5-degree grid -- list the dataset's
    file index (HF API: /api/datasets/zhu-xlab/GBA.LoD1) to find the tile
    covering a new AOI outside Ghana."""
    cache_name = cache_name or f"{country_iso3}_{'_'.join(f'{b:.4f}' for b in bbox)}.json"
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists():
        log.info("Using cached GBA extraction -> %s", cache_path)
        return json.loads(cache_path.read_text())

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{region_tile}.json"
    log.info("Streaming %s (region tile, ~1GB -- NOT downloaded whole; filtering to %s inside bbox)",
              url, country_iso3)

    matches: dict = {}
    n_total = n_country = 0
    with requests.get(url, stream=True, timeout=1800) as r:
        r.raise_for_status()
        r.raw.decode_content = True
        for key, value in ijson.kvitems(r.raw, ""):
            n_total += 1
            if n_total % 2_000_000 == 0:
                log.info("  ...%s entries scanned, %d %s so far, %d in bbox",
                          f"{n_total:,}", n_country, country_iso3, len(matches))
            if n_total % CHECKPOINT_EVERY == 0:
                tmp = cache_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(matches))
                os.replace(tmp, cache_path)

            if not key.endswith(country_iso3):
                continue
            n_country += 1
            code = key[len("google"):-len(country_iso3)] if key.startswith("google") else key[:-len(country_iso3)]
            try:
                if not olc.isValid(code):
                    continue
                d = olc.decode(code)
            except Exception:
                continue
            if _in_bbox(d.latitudeCenter, d.longitudeCenter, bbox):
                h = value.get("height")
                v = value.get("var")
                matches[key] = {
                    "lat": float(d.latitudeCenter), "lon": float(d.longitudeCenter),
                    "height": float(h) if h is not None else None,
                    "var": float(v) if v is not None else None,
                }

    log.info("Done: %s entries scanned, %d %s-suffixed, %d in bbox", f"{n_total:,}", n_country, country_iso3, len(matches))
    cache_path.write_text(json.dumps(matches))
    log.info("Saved -> %s", cache_path)
    return matches


def fetch_osm_building_centroids(bbox: tuple[float, float, float, float]) -> dict:
    """OSM building way-id -> (lat, lon) centroid for a bbox, via one bulk
    Overpass call -- same pattern as channel_encroachment_index.py. Needed
    because GBA.LoD1 keys buildings by real OSM way id (not a Plus Code
    raster point) in well-OSM-mapped regions -- confirmed empirically:
    Ghana's tile uses "google<PlusCode>GHA" keys (raster points, patchy
    local OSM building coverage), but the US tile uses "osm<wayID>USA"
    keys (real building footprints, comprehensive local OSM coverage).
    GBA appears to fall back to a Plus-Code raster only where OSM
    building data is too sparse to anchor to -- itself informative about
    which of the two is the "real" per-building product."""
    import time as _time
    import requests as _requests
    minlon, minlat, maxlon, maxlat = bbox
    query = (f'[out:json][timeout:120];(way["building"]({minlat},{minlon},{maxlat},{maxlon}););'
             f'out center;')
    headers = {"User-Agent": "ThirdWave-research/1.0"}
    elements = []
    for attempt in range(4):
        try:
            r = _requests.post("https://overpass-api.de/api/interpreter", data=query,
                                headers=headers, timeout=180)
            r.raise_for_status()
            elements = r.json().get("elements", [])
            break
        except Exception as exc:
            log.warning("Overpass query failed (attempt %d/4): %s", attempt + 1, exc)
            _time.sleep(5 * (attempt + 1))
    out = {}
    for el in elements:
        if el.get("type") != "way":
            continue
        center = el.get("center")
        if not center:
            continue
        out[el["id"]] = (center["lat"], center["lon"])
    log.info("Fetched %d OSM building centroids for bbox %s", len(out), bbox)
    return out


def fetch_gba_heights_osmid(
    bbox: tuple[float, float, float, float],
    country_iso3: str,
    region_tile: str,
    osm_centroids: dict,
    cache_name: str | None = None,
) -> dict:
    """Same streaming/filtering approach as fetch_gba_heights, but for
    regions where GBA.LoD1 keys buildings by OSM way id ("osm<id><ISO3>")
    instead of a Plus Code -- resolves each id's location via a
    pre-fetched {way_id: (lat, lon)} map (see fetch_osm_building_centroids)
    rather than decoding a geocode."""
    cache_name = cache_name or f"{country_iso3}_osmid_{'_'.join(f'{b:.4f}' for b in bbox)}.json"
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists():
        log.info("Using cached GBA extraction -> %s", cache_path)
        return json.loads(cache_path.read_text())

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{region_tile}.json"
    log.info("Streaming %s (region tile, ~1GB -- NOT downloaded whole; filtering to %s osm-id keys "
              "matching %d known OSM building centroids)", url, country_iso3, len(osm_centroids))

    matches: dict = {}
    n_total = n_country = n_joined = 0
    with requests.get(url, stream=True, timeout=1800) as r:
        r.raise_for_status()
        r.raw.decode_content = True
        for key, value in ijson.kvitems(r.raw, ""):
            n_total += 1
            if n_total % 2_000_000 == 0:
                log.info("  ...%s entries scanned, %d %s so far, %d joined to a known building",
                          f"{n_total:,}", n_country, country_iso3, n_joined)
            if n_total % CHECKPOINT_EVERY == 0:
                tmp = cache_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(matches))
                os.replace(tmp, cache_path)

            if not (key.startswith("osm") and key.endswith(country_iso3)):
                continue
            n_country += 1
            id_str = key[len("osm"):-len(country_iso3)]
            try:
                way_id = int(id_str)
            except ValueError:
                continue
            if way_id not in osm_centroids:
                continue
            n_joined += 1
            lat, lon = osm_centroids[way_id]
            h = value.get("height")
            v = value.get("var")
            matches[key] = {
                "lat": lat, "lon": lon,
                "height": float(h) if h is not None else None,
                "var": float(v) if v is not None else None,
            }

    log.info("Done: %s entries scanned, %d %s-suffixed, %d joined to a known building",
              f"{n_total:,}", n_total, country_iso3, len(matches))
    cache_path.write_text(json.dumps(matches))
    log.info("Saved -> %s", cache_path)
    return matches
