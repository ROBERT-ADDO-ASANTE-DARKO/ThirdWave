"""
analytics.py — Feature #7, Analytics Dashboard. Three real, computable-
today views over the live Report table, each honest about what thin
real data can and can't support yet:

  response_time_stats(): verification latency (submitted_at ->
  verified_at) and resolution latency (verified_at -> resolved_at) --
  real for every report that has reached that stage, n explicitly
  reported alongside each mean/median so a 2-report average is never
  mistaken for a stable statistic.

  reports_by_district(): a straight count by district x status. No
  derived signal, just a group-by -- always honest regardless of volume.

  recurring_hotspots(): clusters VERIFIED + RESOLVED reports only (not
  pending/rejected -- a rejected report wasn't a real flood) with
  clustering.py's same 300m complete-linkage grouping used everywhere
  else reports get grouped, then flags clusters with >=2 reports as a
  repeat-incident candidate. Paired with each cluster's existing static
  vulnerability score (geo_data.zone_for_point()) -- the same
  distinction govt_drain_priority.py already draws: multi-year SAR
  water-occurrence is a persistent signal this project has always had;
  verified repeat-incident history is a live signal still accumulating,
  and with only a handful of real verified reports so far, this view
  says so explicitly rather than dressing up n=2 as a trend.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

import clustering
import geo_data
from models import Report
from serializers import serialize_report

MIN_HOTSPOT_REPORTS = 2


def _minutes_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60.0


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean_min": None, "median_min": None, "min_min": None, "max_min": None}
    values = sorted(values)
    n = len(values)
    mid = n // 2
    median = values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2
    return {
        "n": n, "mean_min": round(sum(values) / n, 1), "median_min": round(median, 1),
        "min_min": round(values[0], 1), "max_min": round(values[-1], 1),
    }


def response_time_stats(session: Session) -> dict:
    reports = session.exec(select(Report)).all()
    verification_min = [
        _minutes_between(r.submitted_at, r.verified_at) for r in reports if r.verified_at is not None
    ]
    resolution_min = [
        _minutes_between(r.verified_at, r.resolved_at) for r in reports
        if r.verified_at is not None and r.resolved_at is not None
    ]
    return {
        "verification_latency": _stats(verification_min),
        "resolution_latency": _stats(resolution_min),
        "total_reports": len(reports),
    }


def reports_by_district(session: Session) -> list[dict]:
    reports = session.exec(select(Report)).all()
    by_district: dict[str, dict] = {}
    for r in reports:
        d = r.district or "outside pilot district"
        row = by_district.setdefault(d, {"district": d, "total": 0, "pending": 0, "verified": 0, "rejected": 0, "resolved": 0})
        row["total"] += 1
        row[r.status] += 1
    return sorted(by_district.values(), key=lambda row: -row["total"])


def recurring_hotspots(session: Session) -> dict:
    reports = session.exec(
        select(Report).where(Report.status.in_(["verified", "resolved"]))
    ).all()
    serialized = [serialize_report(r, include_zone=False) for r in reports]
    clusters = clustering.cluster_reports(serialized)

    hotspots = []
    for c in clusters:
        if c["n_reports"] < MIN_HOTSPOT_REPORTS:
            continue
        zone = geo_data.zone_for_point(c["centroid"]["lon"], c["centroid"]["lat"])
        hotspots.append({
            "centroid": c["centroid"], "district": c["district"], "n_reports": c["n_reports"],
            "hazard_types": c["hazard_types"], "any_synthetic": c["any_synthetic"],
            "static_zone": {"id": zone["id"], "score": zone["score"], "level": zone["level"]} if zone else None,
        })

    return {
        "hotspots": hotspots,
        "n_verified_or_resolved_reports_considered": len(reports),
        "note": (
            f"Based on only {len(reports)} verified/resolved report(s) total -- a repeat-incident "
            "signal this thin is a candidate worth watching, not a confirmed hotspot the way the "
            "multi-year SAR water-occurrence score is. It will get more reliable as more real "
            "reports accumulate."
        ),
    }
