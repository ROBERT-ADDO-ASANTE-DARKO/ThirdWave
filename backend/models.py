"""
models.py — DB tables for the FastAPI backend (Phase 1 of the mobile-app
rehearsal, see project chat history).

Deliberate departure from streamlit_app/incident_store.py's design: that
module keeps three separate Python lists in st.session_state
(pending_reports / active_incidents / resolved_incidents) and MOVES a
record between them on verification. A database shouldn't move rows
around for a status change -- so this is ONE table with a `status` field
("pending" / "verified" / "rejected" / "resolved") instead. Everything
else (field names, the pending->active lifecycle, synthetic tagging)
mirrors incident_store.py's dict shape as closely as a typed table allows.

depth_estimate_m's (lo, hi) tuple becomes two plain float columns
(depth_lo_m/depth_hi_m) -- SQL has no native tuple type and two columns is
simpler than a JSON blob for two numbers that are always read as a pair.

Photos: incident_store.py keeps raw image bytes in session state (fine for
a single Python process that never leaves memory). A real backend needs
them on disk (or object storage later) with a path in the row instead --
see routers/reports.py's upload handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Report(SQLModel, table=True):
    id: str = Field(primary_key=True)
    reporter_ref: str
    hazard_type: str
    description: str

    has_photo: bool = False
    photo_path: Optional[str] = None
    annotated_photo_path: Optional[str] = None
    ai_assisted: bool = False
    synthetic: bool = False

    lon: float
    lat: float
    location_label: Optional[str] = None
    district: Optional[str] = None

    depth_lo_m: Optional[float] = None
    depth_hi_m: Optional[float] = None

    status: str = "pending"  # pending | verified | rejected | resolved
    submitted_at: datetime
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None

    # Populated only once status leaves "pending" -- mirrors
    # incident_store.py's active-incident fields, kept on the same row
    # instead of a separate promoted record.
    assigned_responder: Optional[str] = None
    eta_minutes: Optional[int] = None
    response_status: Optional[str] = None  # reported | responding | resolved
    resolved_at: Optional[datetime] = None


class Device(SQLModel, table=True):
    """Registered for push notifications (Phase 2) -- created now so the
    schema exists, even though nothing sends a push yet."""

    id: str = Field(primary_key=True)
    fcm_token: str
    platform: str  # "android" | "ios"
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    registered_at: datetime
