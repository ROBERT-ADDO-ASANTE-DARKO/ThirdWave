"""
routers/incidents.py — verified, active incidents: the half of
incident_store.py's lifecycle that sits downstream of verify_report().
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import clustering
from db import get_session
from models import Report
from schemas import AssignResponderBody
from serializers import serialize_report

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/active")
def list_active(district: Optional[str] = None, session: Session = Depends(get_session)):
    stmt = select(Report).where(Report.status == "verified")
    if district:
        stmt = stmt.where(Report.district == district)
    reports = list(session.exec(stmt).all())
    reports.sort(key=lambda r: r.verified_at, reverse=True)
    return [serialize_report(r) for r in reports]


@router.get("/nearby")
def nearby(lat: float, lon: float, radius_km: float = 1.5, session: Session = Depends(get_session)):
    """Active incidents within radius_km of a point -- for a citizen near
    a flood, not traveling through it (same persona distinction as
    incident_store.nearby_active_incidents()). This is the query a push
    notification (Phase 2) would run against newly-registered device
    locations instead of a client-initiated request."""
    reports = list(session.exec(select(Report).where(Report.status == "verified")).all())
    out = []
    for r in reports:
        d = clustering.haversine_km(lon, lat, r.lon, r.lat)
        if d <= radius_km:
            out.append({**serialize_report(r), "distance_km": round(d, 3)})
    out.sort(key=lambda x: x["distance_km"])
    return out


@router.post("/{incident_id}/assign-responder")
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
    return serialize_report(report)


@router.post("/{incident_id}/resolve")
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
    return serialize_report(report)
