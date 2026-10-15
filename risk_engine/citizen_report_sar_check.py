"""
citizen_report_sar_check.py — automatic version of what new_juaben_sar_
comparison.py / volta_region_2026_sar_comparison.py did by hand for the
Lower Volta investigation: run a before/peak/recession Sentinel-1 SAR
change-detection check (dam_spillage_sar_comparison.run_event()) anchored
to a verified citizen report's exact lat/lon and submission time, instead
of a manually-researched event.

This is the first integration between live citizen reports (backend/,
Report rows with status="verified") and the SAR evidence pipeline: a
report gives us precisely what run_event() needs -- a point and a date --
that every other use of this script so far had to get from news/NADMO
research. The output is independent satellite corroboration (or an honest
"no visible change" miss, same as Kpetoe) for a SPECIFIC citizen claim,
not a general area scan.

Scope, deliberately narrow:
  - Reads verified reports from GET {BACKEND_URL}/incidents/active --
    does not touch the backend's database directly (same separation
    govt_briefing_review.py already established).
  - Only checks reports not already in checks.json (by report id) -- this
    hits a public, rate-limited STAC API and does real computation, so a
    report is checked once, not on every run.
  - Does not change any score or flag anything automatically -- the
    result is a corroboration record for a human/AI assistant to cite,
    same "report, don't auto-decide" discipline as the rest of this
    project's SAR work.

Usage
─────
    python3 citizen_report_sar_check.py
    python3 citizen_report_sar_check.py --backend http://localhost:8010
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pystac_client
import planetary_computer

from dam_spillage_sar_comparison import run_event, OUT_DIR

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

CHECKS_PATH = OUT_DIR / "citizen_report_checks.json"

# ~1.1km half-width bbox around the report point -- small enough to stay a
# targeted check (not a district-wide scan), big enough to tolerate GPS
# noise and catch flooding that spread slightly from the reported point.
BBOX_HALF_DEG = 0.01

BASELINE_DAYS_BEFORE = 10  # scene to compare against, before the report
RECESSION_DAYS_AFTER = 14  # scene to check whether it had receded by then


def _load_checks() -> dict:
    if CHECKS_PATH.exists():
        return json.loads(CHECKS_PATH.read_text())
    return {}


def _save_checks(checks: dict) -> None:
    CHECKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_PATH.write_text(json.dumps(checks, indent=2))


def _fetch_verified_reports(backend_url: str) -> list[dict]:
    resp = requests.get(f"{backend_url}/incidents/active", timeout=15)
    resp.raise_for_status()
    return resp.json()


def _event_for_report(report: dict) -> dict:
    submitted = datetime.fromisoformat(report["submitted_at"].replace("Z", "+00:00"))
    lon, lat = report["lon"], report["lat"]
    return {
        "event_id": f"CITIZEN-{report['id']}",
        "name": f"Citizen report {report['id']} ({report.get('location_label') or report.get('district') or 'unlabeled'})",
        "bbox": (lon - BBOX_HALF_DEG, lat - BBOX_HALF_DEG, lon + BBOX_HALF_DEG, lat + BBOX_HALF_DEG),
        "baseline": (submitted - timedelta(days=BASELINE_DAYS_BEFORE)).strftime("%Y-%m-%d"),
        "peak": submitted.strftime("%Y-%m-%d"),
        "recession": (submitted + timedelta(days=RECESSION_DAYS_AFTER)).strftime("%Y-%m-%d"),
    }


def run(backend_url: str) -> None:
    checks = _load_checks()
    reports = _fetch_verified_reports(backend_url)
    todo = [r for r in reports if r["id"] not in checks]
    log.info("%d verified report(s) total, %d not yet SAR-checked", len(reports), len(todo))
    if not todo:
        return

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for report in todo:
        ev = _event_for_report(report)
        log.info("Checking %s (%s, submitted %s)...", report["id"], report.get("location_label"), report["submitted_at"])
        try:
            summary = run_event(catalog, ev)
            summary["verdict"] = (
                "SAR shows new standing water consistent with this report"
                if summary["new_flood_at_peak_km2"] > 0.0
                else "No SAR-visible new water near this report -- could be a real miss (revisit timing, "
                     "vegetation canopy, or a flood too small/shallow for this method), not evidence the "
                     "report is wrong. Same ambiguity documented for Kpetoe this project."
            )
        except Exception as exc:
            summary = {"event_id": ev["event_id"], "error": str(exc)}
            log.warning("  failed: %s", exc)
        checks[report["id"]] = {
            "report_id": report["id"], "district": report.get("district"),
            "location_label": report.get("location_label"), "lon": report["lon"], "lat": report["lat"],
            "submitted_at": report["submitted_at"], "checked_at": datetime.utcnow().isoformat(),
            **summary,
        }
        _save_checks(checks)

    log.info("Done. %d report(s) now have a SAR check recorded -> %s", len(todo), CHECKS_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://localhost:8000")
    args = parser.parse_args()
    run(args.backend)
