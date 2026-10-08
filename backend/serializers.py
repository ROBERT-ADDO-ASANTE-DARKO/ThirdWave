"""serializers.py — Report row -> JSON-ready dict, shared by both routers
so a client (Swagger UI today, Flutter later) sees the same shape whether
it hit /reports/pending or /incidents/active."""

import geo_data
from models import Report


def serialize_report(r: Report, include_zone: bool = True) -> dict:
    out = {
        "id": r.id,
        "reporter_ref": r.reporter_ref,
        "hazard_type": r.hazard_type,
        "description": r.description,
        "has_photo": r.has_photo,
        "photo_url": f"/uploads/{r.photo_path}" if r.photo_path else None,
        "annotated_photo_url": f"/uploads/{r.annotated_photo_path}" if r.annotated_photo_path else None,
        "ai_assisted": r.ai_assisted,
        "synthetic": r.synthetic,
        "lon": r.lon,
        "lat": r.lat,
        "location_label": r.location_label,
        "district": r.district,
        "depth_lo_m": r.depth_lo_m,
        "depth_hi_m": r.depth_hi_m,
        "status": r.status,
        "submitted_at": r.submitted_at.isoformat(),
        "verified_at": r.verified_at.isoformat() if r.verified_at else None,
        "verified_by": r.verified_by,
        "assigned_responder": r.assigned_responder,
        "eta_minutes": r.eta_minutes,
        "response_status": r.response_status,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
    }
    if include_zone:
        zone = geo_data.zone_for_point(r.lon, r.lat)
        out["zone"] = {"id": zone["id"], "score": zone["score"], "level": zone["level"]} if zone else None
    return out
