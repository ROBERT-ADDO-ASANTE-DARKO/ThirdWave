"""
main.py — FastAPI entry point, Phase 1 of the mobile-app rehearsal (see
project chat history: FastAPI + Flutter, phased plan).

Run from this directory:
    uvicorn main:app --reload --port 8000

Then http://localhost:8000/docs gives an interactive Swagger UI -- enough
to exercise POST /reports, verify a report, and watch it appear under
/incidents/active without writing a client yet. That's the Phase 1 walking
skeleton: Flutter and push notifications are later phases, not this file.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db import init_db
from routers import analytics, assistant, briefings, config, devices, districts, drain_priority, encroachment_trend, forecast, geocode, incidents, reports, resource_allocation, routing, zones


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ThirdWave API", version="0.1.0", lifespan=lifespan)

# Permissive for local development only (a phone on the same network, or
# Streamlit, calling this). Tighten the origin list before this backend is
# ever reachable from the open internet.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Curated subset of risk_engine/data/ (real Sentinel-2 imagery of known
# encroachment hotspots, see geo_data.py's _satellite_evidence_for_assembly)
# -- a dedicated directory, not risk_engine/data/ itself, which also holds
# multi-megabyte geojson/grid files with no reason to be public.
EVIDENCE_DIR = Path(__file__).parent.parent / "risk_engine" / "data" / "evidence"
app.mount("/evidence", StaticFiles(directory=EVIDENCE_DIR), name="evidence")

app.include_router(reports.router)
app.include_router(incidents.router)
app.include_router(devices.router)
app.include_router(zones.router)
app.include_router(briefings.router)
app.include_router(geocode.router)
app.include_router(forecast.router)
app.include_router(routing.router)
app.include_router(assistant.router)
app.include_router(config.router)
app.include_router(analytics.router)
app.include_router(encroachment_trend.router)
app.include_router(resource_allocation.router)
app.include_router(districts.router)
app.include_router(drain_priority.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
