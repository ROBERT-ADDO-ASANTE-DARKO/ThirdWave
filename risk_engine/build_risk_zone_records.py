"""
build_risk_zone_records.py — Assemble the actual RiskZone records (spec
Section 9: id, district_id, hazard_type, geometry, level, confidence,
contributing_factors[], valid_from, valid_to, model_version) that the
Backend Engineer's GET /risk/zones/{id} endpoint would serve and the
Frontend Engineer's Risk Detail Drawer would render.

Merges three independently-computed layers, each already validated on its
own in this project:
  - pilot_risk_grid.geojson       -- SAR/DEM/LULC composite score (weighted)
  - channel_encroachment_index.json -- OSM building-to-waterway distance (reported, not weighted)

Design choices carried forward from earlier decisions in this project,
not reinvented here:
  - contributing_factors are DISCLOSED, not silently folded into the score.
    The composite score/level still comes only from geospatial_vulnerability.py's
    weighted formula (SAR 0.45 + elevation 0.35 + impervious 0.20) -- same
    discipline as LULC and the Sentinel-2 cross-validation: report what
    free data supports, never let it silently reweight the number a
    district officer already trusts.
  - Missing data is disclosed, never silently dropped or defaulted to
    "Low" (spec's fail-safe rule, Section 8.4) -- a cell with
    insufficient_data OSM coverage gets an explicit factor saying so, and
    confidence is reduced accordingly, not left looking as certain as a
    cell with real encroachment data.
  - Confidence disclosure follows the same is_degraded / reduced-confidence
    pattern already used in thresholds.py's live rule engine, applied here
    to the static layer.

Usage
─────
    python3 build_risk_zone_records.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
ENCROACHMENT_PATH = HERE / "data" / "channel_encroachment_index.json"
OUTPUT = HERE / "data" / "risk_zones.json"

MODEL_VERSION = "rule-based-v1+encroachment-v1"
# Static layer revalidation cadence -- unlike the live engine's 15-minute
# recompute (thresholds.py), this is a slow-changing structural layer.
# Revisit if a new SAR/DEM/LULC pipeline run or a fresh OSM pull happens.
VALIDITY_WINDOW = timedelta(days=90)

DISTRICT_ID = "thirdwave-pilot-district"  # union of the 6 assemblies, see project memory


def sar_factor(props: dict) -> dict:
    return {
        "type": "sar_water_occurrence",
        "source": "sentinel-1-grd (Planetary Computer), 2020-2024, 40-scene sample",
        "text": f"SAR water occurrence: {props['water_occ_pct']:.1f}% of scenes flagged this area as water-like "
                f"(2020-2024).",
        "value": props["water_occ_pct"],
    }


def elevation_factor(props: dict) -> dict:
    return {
        "type": "low_elevation",
        "source": "cop-dem-glo-30 (Copernicus DEM 30m)",
        "text": f"{props['low_elev_frac_pct']:.1f}% of this zone sits at or below 5m elevation "
                f"(median elevation {props['median_elev_m']:.1f}m).",
        "value": props["low_elev_frac_pct"],
    }


def lulc_factor(props: dict) -> dict:
    return {
        "type": "land_cover_context",
        "source": "esa-worldcover 2021",
        "text": f"{props['impervious_pct']:.1f}% impervious (built-up), {props['wetland_water_pct']:.1f}% "
                f"permanent water/wetland, {props['vegetation_pct']:.1f}% vegetated. Reported for context -- "
                "not weighted into the composite score (tried once, flattened the score's discrimination; "
                "see project notes).",
        "value": None,
    }


def encroachment_factor(enc: dict | None) -> dict:
    if enc is None or enc.get("status") != "ok":
        note = (enc or {}).get("note", "No OSM building/waterway data available for this cell.")
        return {
            "type": "channel_encroachment",
            "source": "OpenStreetMap (Overpass API)",
            "text": f"Channel-encroachment data unavailable for this zone: {note}",
            "value": None,
            "data_insufficient": True,
        }
    # min_building_to_waterway_m drives the encroachment_level band (<=10m
    # Very High / <=30m High / <=75m Moderate); n_buildings_within_20m is a
    # separate, fixed-threshold count. Keep them in separate clauses --
    # stating both about the same distance in one sentence read as
    # self-contradictory (e.g. "23.5m... 0 within 20m -- High").
    return {
        "type": "channel_encroachment",
        "source": "OpenStreetMap (Overpass API)",
        "text": f"Nearest building sits {enc['min_building_to_waterway_m']:.1f}m from a mapped waterway/drain "
                f"-- {enc['encroachment_level'].lower()} encroachment. "
                f"{enc['n_buildings_within_20m']} of {enc['n_buildings']} buildings in this zone are within 20m "
                "of a waterway/drain.",
        "value": enc["min_building_to_waterway_m"],
        "data_insufficient": False,
    }


def compute_confidence(props: dict, enc: dict | None) -> float:
    """0-1 confidence, reduced when supporting data is thin -- mirrors the
    is_degraded pattern in thresholds.py's live engine, applied to this
    static layer. Not a formal statistical confidence interval; an
    explainable, tunable signal for the 'reduced confidence' fail-safe UI
    state the frontend needs (spec references this directly)."""
    confidence = 1.0
    if props.get("boundary_overlap_frac", 1.0) < 0.5:
        confidence -= 0.15  # cell mostly outside the pilot boundary
    if enc is None or enc.get("status") != "ok":
        confidence -= 0.25  # no encroachment evidence -- real gap, not "no risk"
    if props.get("s2_comparison_label") == "no_s2_coverage":
        confidence -= 0.05  # minor -- S2 was already established as unreliable for floods
    return round(max(0.3, confidence), 2)


def run():
    grid = json.loads(GRID_PATH.read_text())
    encroachment = json.loads(ENCROACHMENT_PATH.read_text())
    log.info("Loaded %d grid cells, %d encroachment records", len(grid["features"]), len(encroachment))

    now = datetime.now(timezone.utc)
    zones = []
    n_insufficient = 0

    for f in grid["features"]:
        props = f["properties"]
        zone_id = props["zone_id"]
        enc = encroachment.get(zone_id)
        if enc is None or enc.get("status") != "ok":
            n_insufficient += 1

        factors = [sar_factor(props), elevation_factor(props), lulc_factor(props), encroachment_factor(enc)]
        confidence = compute_confidence(props, enc)

        zones.append({
            "id": f"RZ-{zone_id}",
            "district_id": DISTRICT_ID,
            "hazard_type": "flood",
            "geometry": f["geometry"],
            "level": props["level"],
            "score": props["score"],
            "confidence": confidence,
            "contributing_factors": factors,
            "assembly": props["assembly"],
            "valid_from": now.isoformat(),
            "valid_to": (now + VALIDITY_WINDOW).isoformat(),
            "model_version": MODEL_VERSION,
        })

    log.info("Built %d RiskZone records (%d with reduced confidence from missing encroachment data)",
              len(zones), n_insufficient)

    by_confidence = sorted(zones, key=lambda z: z["confidence"])
    log.info("Lowest-confidence zones (sample):")
    for z in by_confidence[:3]:
        log.info("  %-16s confidence=%.2f  score=%.1f (%s)", z["id"], z["confidence"], z["score"], z["level"])

    OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "count": len(zones), "zones": zones}, indent=2))
    log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    run()
