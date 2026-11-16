"""
sar_corroboration.py — backend port of risk_engine/citizen_report_sar_check.py's
core logic: a Sentinel-1 SAR before/peak/recession change-detection check
anchored to one verified citizen report's exact lon/lat and submission
time (dam_spillage_sar_comparison.run_event()).

Ported, not duplicated: run_check() imports risk_engine's own
run_event()/OUT_DIR lazily (only when an actual check runs, not at
import time, since pystac_client/planetary_computer/rasterio are heavy
and this backend otherwise has no risk_engine dependency) and reads/
writes the EXACT SAME cache file the offline script does
(risk_engine/data/dam_spillage_sar/citizen_report_checks.json), so a
report checked by either one is "checked" for both -- no second,
drifting copy of this state.

Deliberately NOT run automatically on every /incidents/active or
/reports/clusters fetch, unlike photo_validation.py's VLM check: this
hits a public, rate-limited STAC API and does real raster computation
(can take real wall-clock time), the same reason the original script
only checks reports explicitly, once. get_cached() is the free, instant,
read-only join every list endpoint uses; run_check() is the slow,
explicit action behind POST /incidents/{id}/sar-check, for an officer to
trigger deliberately on a report they want independent evidence for --
never implied as a verdict on its own (a "no visible change" miss can be
a real miss, not proof the report is wrong -- see the original script's
docstring).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RISK_ENGINE_DIR = Path(__file__).parent.parent / "risk_engine"
CACHE_PATH = RISK_ENGINE_DIR / "data" / "dam_spillage_sar" / "citizen_report_checks.json"

BBOX_HALF_DEG = 0.01  # same ~1.1km half-width as the original script
BASELINE_DAYS_BEFORE = 10
RECESSION_DAYS_AFTER = 14


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def get_cached(report_id: str) -> dict | None:
    """Read-only, zero-cost join -- {"status": "not_yet_checked"} if this
    report has never been run through run_check() (by this endpoint or
    the offline script), not None, so callers don't have to special-case
    a missing entry differently from an explicit miss."""
    cached = _load_cache().get(report_id)
    if cached is None:
        return {"status": "not_yet_checked"}
    if "error" in cached:
        return {"status": "check_failed", "detail": cached["error"]}
    return {
        "status": "checked",
        "new_flood_at_peak_km2": cached["new_flood_at_peak_km2"],
        "verdict": cached["verdict"],
        "scene_dates": cached.get("scene_dates"),
        "checked_at": cached.get("checked_at"),
    }


def run_check(report: dict, force: bool = False) -> dict:
    """report: a serialized, VERIFIED report dict (id/lon/lat/submitted_at/
    location_label/district). Skips the real computation and returns the
    cached result if this report id is already checked, unless force --
    same "check once" discipline as the original script, just per-report
    instead of batch."""
    cache = _load_cache()
    if not force and report["id"] in cache:
        return get_cached(report["id"])

    sys.path.insert(0, str(RISK_ENGINE_DIR))
    import pystac_client
    import planetary_computer
    from dam_spillage_sar_comparison import run_event, OUT_DIR
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    submitted = datetime.fromisoformat(report["submitted_at"].replace("Z", "+00:00"))
    lon, lat = report["lon"], report["lat"]
    event = {
        "event_id": f"CITIZEN-{report['id']}",
        "name": f"Citizen report {report['id']} ({report.get('location_label') or report.get('district') or 'unlabeled'})",
        "bbox": (lon - BBOX_HALF_DEG, lat - BBOX_HALF_DEG, lon + BBOX_HALF_DEG, lat + BBOX_HALF_DEG),
        "baseline": (submitted - timedelta(days=BASELINE_DAYS_BEFORE)).strftime("%Y-%m-%d"),
        "peak": submitted.strftime("%Y-%m-%d"),
        "recession": (submitted + timedelta(days=RECESSION_DAYS_AFTER)).strftime("%Y-%m-%d"),
    }

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    try:
        summary = run_event(catalog, event)
        summary["verdict"] = (
            "SAR shows new standing water consistent with this report"
            if summary["new_flood_at_peak_km2"] > 0.0
            else "No SAR-visible new water near this report -- could be a real miss (revisit timing, "
                 "vegetation canopy, or a flood too small/shallow for this method), not evidence the "
                 "report is wrong."
        )
        entry = {
            "report_id": report["id"], "district": report.get("district"),
            "location_label": report.get("location_label"), "lon": lon, "lat": lat,
            "submitted_at": report["submitted_at"], "checked_at": datetime.now(timezone.utc).isoformat(),
            **summary,
        }
    except Exception as exc:
        entry = {"report_id": report["id"], "event_id": event["event_id"], "error": str(exc),
                  "checked_at": datetime.now(timezone.utc).isoformat()}

    cache[report["id"]] = entry
    _save_cache(cache)
    return get_cached(report["id"])
