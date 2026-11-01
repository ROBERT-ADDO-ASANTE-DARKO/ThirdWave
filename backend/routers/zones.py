"""
routers/zones.py — zone vulnerability lookup, address-based (Phase 4
feature #1) and point-based (feature #4, for a GPS fix with no address
text to look up). Citizen-facing, no officer key needed -- same tier as
/incidents/nearby.

Both endpoints now also join in nearby verified citizen reports (feature
#7's My Zone upgrade) -- same principle the AI Assistant's
find_zone_by_address tool already follows: a computed score should never
be shown without also surfacing live ground-truth evidence nearby, not
just curated historical events. zone_info_for_point() echoes lon/lat back
in its result specifically so this join (and the Flutter client's inline
map) have coordinates to work with without a second geocode.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

import geo_data
from db import get_session
from report_queries import summarize, verified_reports_near

router = APIRouter(prefix="/zones", tags=["zones"])


def _attach_nearby_reports(result: dict, session: Session) -> dict:
    if "lon" in result and "lat" in result:
        hits = verified_reports_near(session, result["lon"], result["lat"])
        result["nearby_verified_citizen_reports"] = [summarize(r, d) for r, d in hits]
    return result


@router.get("/lookup")
def lookup(address: str, session: Session = Depends(get_session)):
    return _attach_nearby_reports(geo_data.find_zone_by_address(address), session)


@router.get("/lookup-by-point")
def lookup_by_point(lat: float, lon: float, session: Session = Depends(get_session)):
    return _attach_nearby_reports(geo_data.zone_info_for_point(lon, lat), session)
