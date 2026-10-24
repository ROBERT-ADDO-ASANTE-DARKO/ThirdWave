"""
routers/reports.py — citizen report intake + district-officer queue.

Mirrors streamlit_app/incident_store.py's submit_report/list_pending/
verify_report, with two adaptations: district is still assigned
server-side from the GPS point (a client never sends one, same as
today), and photos land on disk under uploads/ with a path column instead
of raw bytes in memory (see models.py's module docstring for why).
"""

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

import clustering
import geo_data
import news_corroboration as news
import push
import vlm_client
from auth import require_officer
from db import get_session
from models import Report
from schemas import BulkVerifyBody, VerifyBody
from serializers import serialize_report

router = APIRouter(prefix="/reports", tags=["reports"])

UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("")
def submit_report(
    lon: float = Form(...),
    lat: float = Form(...),
    hazard_type: str = Form(...),
    description: str = Form(...),
    location_label: Optional[str] = Form(None),
    depth_lo_m: Optional[float] = Form(None),
    depth_hi_m: Optional[float] = Form(None),
    reporter_ref: str = Form(..., description="Client-generated, persisted identifier -- not a login (see auth.py)"),
    ai_assisted: bool = Form(False),
    synthetic: bool = Form(False),
    photo: Optional[UploadFile] = File(None),
    annotated_photo: Optional[UploadFile] = File(None, description="The AI-annotated version from POST /reports/draft, if the citizen used one"),
    session: Session = Depends(get_session),
):
    district = geo_data.assign_district(lon, lat)
    photo_path = None
    if photo is not None and photo.filename:
        ext = Path(photo.filename).suffix or ".jpg"
        photo_path = f"{_new_id('PHOTO')}{ext}"
        (UPLOADS_DIR / photo_path).write_bytes(photo.file.read())

    annotated_photo_path = None
    if annotated_photo is not None and annotated_photo.filename:
        annotated_photo_path = f"{_new_id('APHOTO')}.jpg"
        (UPLOADS_DIR / annotated_photo_path).write_bytes(annotated_photo.file.read())

    report = Report(
        id=_new_id("RPT"), reporter_ref=reporter_ref, hazard_type=hazard_type,
        description=description, has_photo=photo_path is not None, photo_path=photo_path,
        annotated_photo_path=annotated_photo_path,
        ai_assisted=ai_assisted, synthetic=synthetic, lon=lon, lat=lat,
        location_label=location_label, district=district,
        depth_lo_m=depth_lo_m, depth_hi_m=depth_hi_m,
        status="pending", submitted_at=_now(),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return serialize_report(report)


@router.post("/draft")
def draft_from_photo(photo: UploadFile = File(...)):
    """AI-drafted description + depth estimate + annotated image from a
    photo, for the citizen to review/edit before ever calling POST
    /reports -- see vlm_client.py's module docstring: this never
    auto-submits anything. Nothing is persisted here; the client re-sends
    whatever it wants to keep (edited description, the annotated image if
    it wants one attached) to POST /reports itself.

    Mirrors citizen_report.py's "AI description unavailable, you can
    still describe it yourself" behavior -- a VLM failure returns
    {"error": ...} at 200, not an HTTP error, since the client should
    degrade to manual entry inline rather than treat this as a hard
    failure."""
    image_bytes = photo.file.read()
    try:
        result = vlm_client.describe_flood_photo(image_bytes, media_type=photo.content_type or "image/jpeg")
    except vlm_client.VLMError as exc:
        return {"error": str(exc)}

    annotated = vlm_client.annotate_image(image_bytes, result)
    result["annotated_image_base64"] = base64.b64encode(annotated).decode("ascii") if annotated else None
    return result


@router.get("/pending", dependencies=[Depends(require_officer)])
def list_pending(district: Optional[str] = None, session: Session = Depends(get_session)):
    stmt = select(Report).where(Report.status == "pending")
    if district:
        stmt = stmt.where(Report.district == district)
    reports = list(session.exec(stmt).all())
    reports.sort(key=lambda r: r.submitted_at, reverse=True)
    return [serialize_report(r) for r in reports]


@router.get("/clusters", dependencies=[Depends(require_officer)])
def list_clusters(district: Optional[str] = None, session: Session = Depends(get_session)):
    """Same clustering an officer sees in the Streamlit sandbox, plus
    per-cluster news corroboration -- see clustering.py / news_corroboration.py."""
    stmt = select(Report).where(Report.status == "pending")
    if district:
        stmt = stmt.where(Report.district == district)
    reports = list(session.exec(stmt).all())
    serialized = [serialize_report(r, include_zone=True) for r in reports]
    clusters = clustering.cluster_reports(serialized)

    recent_news = news.fetch_flood_news()
    out = []
    for c in clusters:
        hits = news.corroborating_news(
            recent_news, c["district"], *[r["location_label"] for r in c["reports"]],
        )
        out.append({**c, "corroborating_news": hits})
    return out


def _notify(session: Session, lon: float, lat: float, hazard_types: list[str], location_label: str | None) -> dict:
    """Push is a side effect of verification, never a precondition for
    it -- a missing/misconfigured Firebase credential or an FCM outage
    must not turn a successful verify into a failed request."""
    hz = ", ".join(h.replace("_", " ") for h in hazard_types)
    body = f"Verified {hz} report near {location_label}" if location_label else f"Verified {hz} report nearby"
    try:
        return push.notify_nearby_devices(session, lon, lat, title="Flood incident verified", body=body)
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/{report_id}/verify", dependencies=[Depends(require_officer)])
def verify_report(report_id: str, body: VerifyBody, session: Session = Depends(get_session)):
    report = session.get(Report, report_id)
    if report is None or report.status != "pending":
        raise HTTPException(404, "pending report not found")
    report.status = "verified" if body.approve else "rejected"
    report.verified_at = _now()
    report.verified_by = body.verified_by
    if body.approve:
        report.response_status = "reported"
    session.add(report)
    session.commit()
    session.refresh(report)

    push_result = None
    if body.approve:
        push_result = _notify(session, report.lon, report.lat, [report.hazard_type], report.location_label)
    return {**serialize_report(report), "push": push_result}


@router.post("/verify-bulk", dependencies=[Depends(require_officer)])
def verify_bulk(body: BulkVerifyBody, session: Session = Depends(get_session)):
    out = []
    for rid in body.report_ids:
        report = session.get(Report, rid)
        if report is None or report.status != "pending":
            continue
        report.status = "verified" if body.approve else "rejected"
        report.verified_at = _now()
        report.verified_by = body.verified_by
        if body.approve:
            report.response_status = "reported"
        session.add(report)
        out.append(report)
    session.commit()
    for r in out:
        session.refresh(r)

    # One push for the whole bulk action, not one per report (see
    # push.py's module docstring) -- centroid of whichever reports were
    # actually approved.
    push_result = None
    if body.approve and out:
        lons = [r.lon for r in out]; lats = [r.lat for r in out]
        cx, cy = sum(lons) / len(lons), sum(lats) / len(lats)
        hazard_types = sorted({r.hazard_type for r in out})
        label = out[0].location_label
        push_result = _notify(session, cx, cy, hazard_types, label)
    return {"reports": [serialize_report(r) for r in out], "push": push_result}
