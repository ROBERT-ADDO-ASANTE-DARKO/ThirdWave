"""routers/encroachment_trend.py — Feature #8 (govt dashboard), officer-
gated. Surfaces risk_engine/channel_encroachment_timeseries.py's
multi-year NDBI-near-channel data for the first time in any UI -- see
geo_data.py's encroachment_trend_cells()/encroachment_trend_by_assembly()
docstrings for what it actually measures and its honesty caveats."""

from typing import Optional

from fastapi import APIRouter, Depends

import geo_data
from auth import require_officer

router = APIRouter(prefix="/encroachment-trend", tags=["encroachment-trend"])


@router.get("/by-assembly", dependencies=[Depends(require_officer)])
def by_assembly():
    return geo_data.encroachment_trend_by_assembly()


@router.get("/cells", dependencies=[Depends(require_officer)])
def cells(assembly: Optional[str] = None):
    return geo_data.encroachment_trend_cells(assembly)
