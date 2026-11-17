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

import road_closure_score
import route_engine
from auth import require_officer
from db import get_session

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/safer-route")
def safer_route(
    olat: float, olon: float, dlat: float, dlon: float,
    session: Session = Depends(get_session),
) -> dict:
    return route_engine.compute_routes(session, olat, olon, dlat, dlon)


@router.get("/road-closures", dependencies=[Depends(require_officer)])
def road_closures(session: Session = Depends(get_session)) -> list[dict]:
    """Feature #5, officer-facing half: which real road segments sit
    inside the same incident-avoidance radius Safer Routing (above) is
    already steering citizens around. See route_engine.road_closure_
    recommendations()'s docstring -- this is a summary over that existing
    avoidance data, not a second routing graph."""
    return route_engine.road_closure_recommendations(session)


@router.get("/road-closure-scores", dependencies=[Depends(require_officer)])
def road_closure_scores(session: Session = Depends(get_session)) -> list[dict]:
    """One composite closure score per unique road segment (not per
    incident) -- see road_closure_score.py's docstring for the weighted
    formula and why each weight is what it is."""
    return road_closure_score.compute(session)
