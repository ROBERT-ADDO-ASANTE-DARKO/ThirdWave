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
from routers import devices, incidents, reports


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

app.include_router(reports.router)
app.include_router(incidents.router)
app.include_router(devices.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
