"""
amsterdam_bgt_fetch.py — real land-cover polygons (buildings, roads, paving,
vegetation, water) from the Dutch BGT (Basisregistratie Grootschalige
Topografie) for an RD-coordinate AOI, via the PDOK OGC API. Used to give
each SWMM subcatchment a physically grounded impervious fraction instead
of a guess.

Source: https://api.pdok.nl/lv/bgt/ogc/v1  (CC0, PDOK / Kadaster)

Two things that matter and were confirmed empirically rather than assumed:
  1. BGT keeps HISTORICAL objects alongside current ones (a footpath
     polygon retired in 2019 still comes back from a plain bbox query,
     with eind_registratie set). Counting those double-counts surface
     area, so only rows with eind_registratie IS NULL and
     status == "bestaand" are kept.
  2. Elevated objects (viaducts, decks) overlap ground-level ones in plan
     view; relatieve_hoogteligging != 0 objects are dropped for ground
     layers so surface area isn't counted twice. Bridge decks
     (overbruggingsdeel) are the deliberate exception: rain falls on them
     and they sit over water polygons that are excluded anyway.

Geometry is requested directly in RD (EPSG:28992, metres) so areas are
true areas, not degrees.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests
from pyproj import Transformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "amsterdam_bgt"
BASE = "https://api.pdok.nl/lv/bgt/ogc/v1"
RD_CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"
ATTRIBUTION = "BGT, Kadaster / PDOK (CC0)"

# collection -> role in the runoff model
LAYERS = ["pand", "wegdeel", "ondersteunendwegdeel", "onbegroeidterreindeel",
          "begroeidterreindeel", "waterdeel", "overbruggingsdeel"]

_to_wgs = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)


def _fetch_layer(layer: str, x: float, y: float, half: float) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{layer}_{int(x)}_{int(y)}_{int(half)}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    lon0, lat0 = _to_wgs.transform(x - half, y - half)
    lon1, lat1 = _to_wgs.transform(x + half, y + half)
    url = f"{BASE}/collections/{layer}/items"
    params = {"f": "json", "limit": 1000, "bbox": f"{lon0},{lat0},{lon1},{lat1}", "crs": RD_CRS_URI}

    kept: list[dict] = []
    n_raw = 0
    while url:
        for attempt in range(4):
            try:
                r = requests.get(url, params=params, timeout=90)
                r.raise_for_status()
                break
            except Exception as exc:
                log.warning("  %s failed (attempt %d/4): %s", layer, attempt + 1, exc)
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"{layer}: fetch failed after retries")
        data = r.json()
        for f in data.get("features", []):
            n_raw += 1
            p = f["properties"]
            if p.get("eind_registratie") is not None:
                continue  # historical object
            if p.get("status") not in (None, "bestaand"):
                continue
            if layer != "overbruggingsdeel" and p.get("relatieve_hoogteligging") not in (None, 0):
                continue  # elevated -- would double count plan-view area
            kept.append(f)
        nxt = next((l["href"] for l in data.get("links", []) if l.get("rel") == "next"), None)
        url, params = nxt, None  # 'next' href already carries all query params
    log.info("  %-24s raw %5d -> kept %5d (current, ground-level)", layer, n_raw, len(kept))
    cache.write_text(json.dumps(kept))
    return kept


def fetch_bgt(x: float, y: float, half: float) -> dict[str, list[dict]]:
    """{layer: [GeoJSON features in RD]} for the (2*half)-m square around (x, y)."""
    return {layer: _fetch_layer(layer, x, y, half) for layer in LAYERS}


if __name__ == "__main__":
    from collections import Counter
    out = fetch_bgt(121205, 486795, 850)
    for layer, feats in out.items():
        fv = Counter(f["properties"].get("fysiek_voorkomen") or f["properties"].get("plus_fysiek_voorkomen")
                     for f in feats)
        print(layer, len(feats), dict(fv.most_common(6)))
