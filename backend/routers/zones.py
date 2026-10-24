"""
routers/zones.py — address-based zone vulnerability lookup, the backend
half of Phase 4 feature #1 (Current Vulnerability by Address). Citizen-
facing, no officer key needed -- same tier as /incidents/nearby.
"""

from fastapi import APIRouter

import geo_data

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("/lookup")
def lookup(address: str):
    return geo_data.find_zone_by_address(address)
