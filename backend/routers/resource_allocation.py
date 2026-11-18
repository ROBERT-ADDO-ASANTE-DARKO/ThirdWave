"""routers/resource_allocation.py — Feature #4 (govt dashboard), officer-
gated. Nearest real fire station / hospital for one point -- see
geo_data.py's emergency_facilities()/nearest_facility() docstrings for
coverage and what's deliberately NOT here (NADMO, boats, shelters)."""

from fastapi import APIRouter, Depends

import geo_data
from auth import require_officer

router = APIRouter(prefix="/resource-allocation", tags=["resource-allocation"])


@router.get("/nearest-facilities", dependencies=[Depends(require_officer)])
def nearest_facilities(lat: float, lon: float):
    return {
        "fire_station": geo_data.nearest_facility(lat, lon, "fire_stations"),
        "hospital": geo_data.nearest_facility(lat, lon, "hospitals"),
    }
