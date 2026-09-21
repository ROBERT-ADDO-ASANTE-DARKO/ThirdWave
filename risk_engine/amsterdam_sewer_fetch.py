"""
amsterdam_sewer_fetch.py — pull the real Waternet sewer network (pipes +
nodes) for an AOI from the Amsterdam open-data API, for Phase 1 of the
Amsterdam hydrological-modelling rehearsal (see build_amsterdam_swmm.py).

Source: Gemeente Amsterdam / Waternet "Kabels en leidingen ondergrond"
API, collections waternet_rioolleidingen (pipes) and waternet_rioolknopen
(nodes):
  https://api.data.amsterdam.nl/v1/leidingeninfrastructuur/

Query: geometrie[within]=x,y,radius (RD/EPSG:28992 metres), paged 1000 at
a time (the server's hard page limit -- confirmed: both collections
returned exactly 1000 on the first page for a 800m-radius circle, i.e.
more exist; this paginates until a short page).

Pipe attributes actually used by the SWMM builder: diameter (mm), vorm
(shape), breedte/hoogte (mm, for non-round pipes), bobBeginpunt /
bobEindpunt (invert levels, m vs NAP), typeLeiding + stelselType (foul /
storm / combined), status. Node attributes: maaiveld (ground level, m vs
NAP) etc. -- see the printed schema on first fetch.

License caveat, stated honestly: the API's own OpenAPI spec says
"Creative Commons, Naamsvermelding" (CC BY, attribution), but the
data.overheid.nl catalog entry for the same dataset says "Onbekende
licentie" (unknown). Treated here as CC BY with attribution to Gemeente
Amsterdam / Waternet; verify before any redistribution beyond this
research repo.

Usage
─────
    from amsterdam_sewer_fetch import fetch_sewer
    pipes, nodes = fetch_sewer(121205, 486795, 800)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "amsterdam_sewer"  # ephemeral, gitignored (risk_engine/cache/)
BASE = "https://api.data.amsterdam.nl/v1/leidingeninfrastructuur"
PAGE_SIZE = 1000
ATTRIBUTION = "Gemeente Amsterdam / Waternet, Kabels en leidingen ondergrond (rioolnetwerk)"


def _fetch_collection(name: str, x: float, y: float, radius: float) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{name}_{int(x)}_{int(y)}_{int(radius)}.json"
    if cache.exists():
        log.info("Using cached %s -> %s", name, cache.name)
        return json.loads(cache.read_text())

    features: list[dict] = []
    page = 1
    while True:
        params = {"_format": "geojson", "_pageSize": PAGE_SIZE, "page": page,
                  "geometrie[within]": f"{x},{y},{radius}"}
        for attempt in range(4):
            try:
                r = requests.get(f"{BASE}/{name}/", params=params, headers={"Accept-Crs": "EPSG:28992"}, timeout=90)
                r.raise_for_status()
                break
            except Exception as exc:
                log.warning("  %s page %d failed (attempt %d/4): %s", name, page, attempt + 1, exc)
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"{name}: page {page} failed after retries")
        batch = r.json().get("features", [])
        features.extend(batch)
        log.info("  %s page %d: %d features (total %d)", name, page, len(batch), len(features))
        if len(batch) < PAGE_SIZE:
            break
        page += 1

    cache.write_text(json.dumps(features))
    return features


def fetch_sewer(x: float, y: float, radius: float) -> tuple[list[dict], list[dict]]:
    """(pipes, nodes) GeoJSON features within `radius` m of RD point (x, y)."""
    pipes = _fetch_collection("waternet_rioolleidingen", x, y, radius)
    nodes = _fetch_collection("waternet_rioolknopen", x, y, radius)
    log.info("Fetched %d pipes, %d nodes within %dm of RD (%d, %d)", len(pipes), len(nodes), radius, x, y)
    return pipes, nodes


if __name__ == "__main__":
    from collections import Counter
    pipes, nodes = fetch_sewer(121205, 486795, 800)
    print("\nPIPE property keys:", sorted(pipes[0]["properties"].keys()))
    print("NODE property keys:", sorted(nodes[0]["properties"].keys()))
    print("\nstelselType:", Counter(p["properties"]["stelselType"] for p in pipes))
    print("typeLeiding:", Counter(p["properties"]["typeLeiding"] for p in pipes))
    print("vorm:", Counter(p["properties"]["vorm"] for p in pipes))
    print("status:", Counter(p["properties"]["status"] for p in pipes))
    print("soort:", Counter(p["properties"]["soort"] for p in pipes))
