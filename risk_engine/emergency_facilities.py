"""
emergency_facilities.py — Real fire station and hospital locations for the
pilot area, from free OSM vector data (Overpass API). Feature #4 of the
govt dashboard (Emergency Resource Allocation) was 100% fabricated demo
data; this gives it one real layer to sit on top of.

Coverage checked before building on it (see project chat history):
6 real, named fire stations and 53 real, named hospitals/clinics turned
up in and around the pilot bbox. Only 4 of the 6 fire stations sit
inside a pilot assembly's own boundary -- but that's the wrong question
for a response-distance use case (real responders aren't limited to
their own assembly). The one that matters: every one of the 7 pilot
assemblies has a real fire station within 0.6-4.6km of its centroid, and
a real hospital within each assembly too (thinnest: Ayawaso Central
Municipal, 1). Good enough to use as a real nearest-facility distance
layer.

NOT attempted here, and not claimed as coverable: NADMO offices, flood-
response boats, and emergency shelters are not reliably mapped anywhere
in Ghana OSM data. govt_resource_allocation.py keeps those as explicitly
labeled fabricated demo data -- this script only covers what OSM can
actually answer.

Usage
─────
    python3 emergency_facilities.py
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
PILOT_BOUNDARY = HERE / "data" / "pilot_district_boundary.geojson"
OUTPUT = HERE / "data" / "emergency_facilities.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PAD_DEG = 0.02  # ~2km -- a responder near the pilot edge may be based just outside it


def query_overpass(bbox: tuple[float, float, float, float], retries: int = 3) -> dict:
    minlon, minlat, maxlon, maxlat = bbox
    query = f"""
    [out:json][timeout:60];
    (
      node["amenity"="fire_station"]({minlat},{minlon},{maxlat},{maxlon});
      way["amenity"="fire_station"]({minlat},{minlon},{maxlat},{maxlon});
      node["amenity"="hospital"]({minlat},{minlon},{maxlat},{maxlon});
      way["amenity"="hospital"]({minlat},{minlon},{maxlat},{maxlon});
    );
    out center tags;
    """
    headers = {"User-Agent": "ThirdWave-risk-engine/1.0 (research prototype)"}
    for attempt in range(retries):
        try:
            resp = requests.post(OVERPASS_URL, data=query, headers=headers, timeout=65)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("Overpass query failed (attempt %d/%d): %s", attempt + 1, retries, exc)
            time.sleep(2 * (attempt + 1))
    return {"elements": []}


def run():
    boundary = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = boundary.total_bounds
    bbox = (minlon - PAD_DEG, minlat - PAD_DEG, maxlon + PAD_DEG, maxlat + PAD_DEG)
    log.info("Querying Overpass for fire stations + hospitals in bbox %s ...", bbox)

    data = query_overpass(bbox)
    elements = data.get("elements", [])
    log.info("Got %d element(s)", len(elements))

    fire_stations, hospitals = [], []
    for e in elements:
        tags = e.get("tags", {})
        amenity = tags.get("amenity")
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        entry = {"name": tags.get("name", "(unnamed)"), "lat": lat, "lon": lon}
        if amenity == "fire_station":
            fire_stations.append(entry)
        elif amenity == "hospital":
            hospitals.append(entry)

    log.info("fire_station: %d, hospital: %d", len(fire_stations), len(hospitals))

    OUTPUT.write_text(json.dumps({
        "source": "OSM Overpass, amenity=fire_station/hospital",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "bbox": list(bbox),
        "fire_stations": fire_stations,
        "hospitals": hospitals,
    }, indent=2))
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    run()
