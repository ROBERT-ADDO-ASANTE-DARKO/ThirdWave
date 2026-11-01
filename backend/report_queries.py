"""
report_queries.py — shared verified-report DB queries.

Factored out once "verified reports within radius_km of a point" started
being duplicated three times: routers/incidents.py's GET /nearby,
ai_tools.py's _nearby_verified_reports (the AI Assistant's zone-lookup
join), and now routers/zones.py's citizen-report join (same feature,
feature #7 of Phase 4). Only the data access is shared here, not the
output shape -- incidents.py wants the full serialize_report() shape
plus distance, ai_tools.py/zones.py want a smaller summary -- so each
caller still formats (Report, distance_km) into whatever it needs.
"""

from __future__ import annotations

from sqlmodel import Session, select

from clustering import haversine_km
from models import Report

DEFAULT_RADIUS_KM = 2.0


def verified_reports_near(session: Session, lon: float, lat: float, radius_km: float = DEFAULT_RADIUS_KM) -> list[tuple[Report, float]]:
    """(Report, distance_km) pairs for every verified report within
    radius_km of a point, nearest first."""
    reports = session.exec(select(Report).where(Report.status == "verified")).all()
    hits = [(r, round(haversine_km(lon, lat, r.lon, r.lat), 2)) for r in reports]
    hits = [(r, d) for r, d in hits if d <= radius_km]
    return sorted(hits, key=lambda pair: pair[1])


def summarize(report: Report, distance_km: float) -> dict:
    """The small summary shape ai_tools.py and routers/zones.py both
    want -- not the full serialize_report() shape routers/incidents.py's
    /nearby uses, which also needs the computed zone for each report."""
    return {
        "report_id": report.id, "hazard_type": report.hazard_type, "description": report.description,
        "lon": report.lon, "lat": report.lat, "location_label": report.location_label,
        "distance_km": distance_km,
        "verified_at": report.verified_at.isoformat() if report.verified_at else None,
    }
