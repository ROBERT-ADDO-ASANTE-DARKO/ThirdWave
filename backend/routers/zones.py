"""
routers/zones.py — zone vulnerability lookup, address-based (Phase 4
feature #1) and point-based (feature #4, for a GPS fix with no address
text to look up). Citizen-facing, no officer key needed -- same tier as
/incidents/nearby.
"""

from fastapi import APIRouter

import geo_data

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("/lookup")
def lookup(address: str):
    return geo_data.find_zone_by_address(address)


@router.get("/lookup-by-point")
def lookup_by_point(lat: float, lon: float):
    return geo_data.zone_info_for_point(lon, lat)
