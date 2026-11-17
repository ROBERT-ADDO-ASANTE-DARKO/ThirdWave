"""
routers/incidents.py — verified, active incidents: the half of
incident_store.py's lifecycle that sits downstream of verify_report().
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import geo_data
import photo_validation
import report_confidence
import report_events
import sar_corroboration
from auth import require_officer
from db import get_session
from models import Report
from report_queries import verified_reports_near
from schemas import AssignResponderBody
from serializers import serialize_report

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _with_confidence(serialized: dict) -> dict:
    """Attaches feature #3's composite confidence score -- SAR
    corroboration is read from cache only here (never computed live; see
    sar_corroboration.py's docstring for why), so this stays cheap enough
    to run for every row in a list response."""
    vlm_check = photo_validation.get_or_check(serialized)
    sar_check = sar_corroboration.get_cached(serialized["id"])
    n_historical = len(geo_data.nearby_historical_events(serialized["lat"], serialized["lon"]))
    serialized["confidence"] = report_confidence.compute(
        serialized, vlm_check=vlm_check, sar_check=sar_check,
        n_reports_in_cluster=1, news_hit_count=0, n_nearby_historical_events=n_historical,
    )
    return serialized


@router.get("/active", dependencies=[Depends(require_officer)])
def list_active(district: Optional[str] = None, session: Session = Depends(get_session)):
    stmt = select(Report).where(Report.status == "verified")
    if district:
        stmt = stmt.where(Report.district == district)
    reports = list(session.exec(stmt).all())
    reports.sort(key=lambda r: r.verified_at, reverse=True)
    return [_with_confidence(serialize_report(r)) for r in reports]


@router.get("/resolved", dependencies=[Depends(require_officer)])
def list_resolved(district: Optional[str] = None, limit: int = 50, session: Session = Depends(get_session)):
    """The third list endpoint alongside /reports/pending and /active --
    completes the full Pending/Verified/Responding/Resolved lifecycle for
    the government dashboard's reports queue (govt_reports_queue.py)."""
    stmt = select(Report).where(Report.status == "resolved")
    if district:
        stmt = stmt.where(Report.district == district)
    reports = list(session.exec(stmt).all())
    reports.sort(key=lambda r: r.resolved_at, reverse=True)
    return [_with_confidence(serialize_report(r)) for r in reports[:limit]]


@router.post("/{incident_id}/sar-check", dependencies=[Depends(require_officer)])
def sar_check(incident_id: str, session: Session = Depends(get_session)):
    """Explicit, officer-triggered Sentinel-1 corroboration check for one
    verified/resolved incident -- see sar_corroboration.py's docstring for
    why this is a deliberate action, not something list endpoints compute
    automatically. Can take real wall-clock time (a live satellite-catalog
    query), so this request is expected to block for it."""
    report = session.get(Report, incident_id)
    if report is None or report.status not in ("verified", "resolved"):
        raise HTTPException(404, "verified or resolved incident not found")
    serialized = serialize_report(report)
    sar_corroboration.run_check(serialized)  # writes to the shared cache; _with_confidence below reads it back
    return _with_confidence(serialized)


@router.get("/nearby")
def nearby(lat: float, lon: float, radius_km: float = 1.5, session: Session = Depends(get_session)):
    """Active incidents within radius_km of a point -- for a citizen near
    a flood, not traveling through it (same persona distinction as
    incident_store.nearby_active_incidents()). This is the query a push
    notification (Phase 2) would run against newly-registered device
    locations instead of a client-initiated request."""
    hits = verified_reports_near(session, lon, lat, radius_km=radius_km)
    return [{**serialize_report(r), "distance_km": d} for r, d in hits]


@router.post("/{incident_id}/assign-responder", dependencies=[Depends(require_officer)])
def assign_responder(incident_id: str, body: AssignResponderBody, session: Session = Depends(get_session)):
    report = session.get(Report, incident_id)
    if report is None or report.status != "verified":
        raise HTTPException(404, "active incident not found")
    report.assigned_responder = body.responder_name
    report.eta_minutes = body.eta_minutes
    report.response_status = "responding"
    session.add(report)
    session.commit()
    session.refresh(report)
    report_events.record_event(session, report.id, "responder_assigned",
                                detail=f"{body.responder_name}, ETA {body.eta_minutes} min")
    return serialize_report(report)


@router.post("/{incident_id}/resolve", dependencies=[Depends(require_officer)])
def resolve(incident_id: str, session: Session = Depends(get_session)):
    report = session.get(Report, incident_id)
    if report is None or report.status != "verified":
        raise HTTPException(404, "active incident not found")
    report.status = "resolved"
    report.response_status = "resolved"
    report.resolved_at = datetime.now(timezone.utc)
    session.add(report)
    session.commit()
    session.refresh(report)
    report_events.record_event(session, report.id, "resolved")
    return serialize_report(report)
