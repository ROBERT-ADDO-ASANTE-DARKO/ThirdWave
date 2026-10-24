"""
routers/geocode.py — plain address -> (lat, lon) lookup, no zone/score
attached. Citizen-facing, no officer key needed.

A separate, deliberately thin endpoint from /zones/lookup rather than
having the Flutter report-location search reuse that one: /zones/lookup
always also computes a zone score + historical-events join, work the
reporting flow's "where is this" step doesn't need yet (the report itself
carries a raw lat/lon; zone lookup is a different feature, #1, not this
one). Both call geo_data.geocode_address() underneath, so there's no
duplicated geocoding logic either way.
"""

from fastapi import APIRouter

import geo_data

router = APIRouter(tags=["geocode"])


@router.get("/geocode")
def geocode(address: str):
    return geo_data.geocode_address(address)
