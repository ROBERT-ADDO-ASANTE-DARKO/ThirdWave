"""
routers/config.py — small client-config endpoint so the Flutter app never
hardcodes third-party keys into its source tree. MAPBOX_API_KEY lives in
ThirdWave/.env like the other keys (see vlm_client.py/auth.py); this just
hands the app's already-public (pk.*) Mapbox token to the client at
runtime so it can be rotated in .env without an app rebuild.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter

load_dotenv(Path(__file__).parent.parent.parent / ".env")

router = APIRouter(tags=["config"])


@router.get("/config/map-tiles")
def map_tiles() -> dict:
    return {"mapbox_token": os.environ.get("MAPBOX_API_KEY")}
