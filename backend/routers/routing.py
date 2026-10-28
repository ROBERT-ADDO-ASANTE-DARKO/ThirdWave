"""
routers/routing.py — GET /routing/safer-route, Phase 4 feature #5 (Safer
Routing). Citizen-facing, no officer key needed.

Coordinates in, not addresses -- same split as every other citizen-facing
lookup in this backend (zones.lookup-by-point, forecast.rainfall): the
Flutter client geocodes via GET /geocode (or uses a live GPS fix) itself,
then passes lat/lon here, rather than this endpoint re-implementing address
resolution.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

import route_engine
from db import get_session

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/safer-route")
def safer_route(
    olat: float, olon: float, dlat: float, dlon: float,
    session: Session = Depends(get_session),
) -> dict:
    return route_engine.compute_routes(session, olat, olon, dlat, dlon)
