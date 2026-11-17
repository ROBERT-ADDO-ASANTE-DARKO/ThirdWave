"""routers/analytics.py — Feature #7 (Analytics Dashboard), officer-gated
read-only views over the live Report table. See analytics.py's module
docstring for what each one actually computes and its honesty caveats."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

import analytics
from auth import require_officer
from db import get_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/response-times", dependencies=[Depends(require_officer)])
def response_times(session: Session = Depends(get_session)):
    return analytics.response_time_stats(session)


@router.get("/by-district", dependencies=[Depends(require_officer)])
def by_district(session: Session = Depends(get_session)):
    return analytics.reports_by_district(session)


@router.get("/hotspots", dependencies=[Depends(require_officer)])
def hotspots(session: Session = Depends(get_session)):
    return analytics.recurring_hotspots(session)
