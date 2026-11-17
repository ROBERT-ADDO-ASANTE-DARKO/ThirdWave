"""
Feature 6 — Flood/Incident Timeline (Government).

Report (backend/models.py) only ever held the CURRENT state --
submitted_at/verified_at/resolved_at for the first/middle/last step, no
record of when a responder was assigned, and no record at all of
intermediate history for a report's lifecycle. backend/report_events.py
closes that gap with a new, append-only ReportEvent table: every status
change going forward is logged in real time (reconstructed: false).
For anything that happened before that table existed, the backend does
its best to reconstruct a timeline from the report's own timestamp
columns (reconstructed: true, with a note saying so) -- never silently
presented as a real logged event.

Pick a report by ID (typed or from the recent-reports list below) to see
its full event-by-event history.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env", override=True)

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")

_EVENT_ICON = {
    "submitted": "\U0001F4DD",
    "verified": "✅",
    "rejected": "❌",
    "responder_assigned": "\U0001F691",
    "resolved": "\U0001F3C1",
}
_EVENT_LABEL = {
    "submitted": "Submitted",
    "verified": "Verified",
    "rejected": "Rejected",
    "responder_assigned": "Responder assigned",
    "resolved": "Resolved",
}


def _get(path: str, officer_key: str, **params):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, headers={"X-Officer-Key": officer_key}, timeout=15)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _recent_reports(officer_key: str) -> list[dict]:
    """Merges pending/active/resolved into one picker list -- same three
    endpoints govt_reports_queue.py already uses, just flattened here."""
    out = []
    pending, _ = _get("/reports/pending", officer_key)
    active, _ = _get("/incidents/active", officer_key)
    resolved, _ = _get("/incidents/resolved", officer_key, limit=30)
    for r in (pending or []):
        out.append({**r, "queue_status": "Pending"})
    for r in (active or []):
        out.append({**r, "queue_status": "Responding" if r.get("response_status") == "responding" else "Verified"})
    for r in (resolved or []):
        out.append({**r, "queue_status": "Resolved"})
    out.sort(key=lambda r: r["submitted_at"], reverse=True)
    return out


def render():
    st.subheader("Flood / Incident Timeline")
    st.caption(
        "Real, timestamped event history per report where it's been logged since this feature "
        "shipped; best-effort reconstruction from the report's own timestamps for anything older "
        "(clearly marked, never presented as a logged event)."
    )

    officer_key = os.environ.get("OFFICER_API_KEY")
    if not officer_key:
        st.error("OFFICER_API_KEY not found in backend/.env -- cannot reach officer-gated endpoints.")
        return

    reports = _recent_reports(officer_key)

    col1, col2 = st.columns([2, 1])
    with col1:
        options = ["(type an ID below instead)"] + [
            f"{r['id']} — {r['hazard_type'].replace('_', ' ').title()} — "
            f"{r['district'] or 'outside pilot district'} — {r['queue_status']}"
            for r in reports
        ]
        choice = st.selectbox("Pick a recent report", options)
    with col2:
        typed_id = st.text_input("...or enter a report ID directly", placeholder="e.g. RPT-20261115-63C86A")

    report_id = typed_id.strip() if typed_id.strip() else (
        choice.split(" — ")[0] if choice != "(type an ID below instead)" else None
    )

    if not report_id:
        st.info("Pick a report above, or type an ID, to see its timeline.")
        return

    data, err = _get(f"/reports/{report_id}/timeline", officer_key)
    if err:
        st.error(f"Could not load timeline for {report_id}: {err}")
        return

    events = data["events"]
    if not events:
        st.warning("No events at all for this report -- it may not exist.")
        return

    st.divider()
    for e in events:
        icon = _EVENT_ICON.get(e["event_type"], "•")
        label = _EVENT_LABEL.get(e["event_type"], e["event_type"])
        ts = e["occurred_at"][:19].replace("T", " ")
        with st.container(border=True):
            c1, c2 = st.columns([1, 5])
            with c1:
                st.markdown(f"### {icon}")
            with c2:
                st.markdown(f"**{label}** — {ts} UTC")
                if e.get("detail"):
                    st.caption(e["detail"])
                if e.get("reconstructed"):
                    st.caption(f"⚠️ {e['note']}")

    if data["untimed_notes"]:
        st.divider()
        for note in data["untimed_notes"]:
            st.caption(f"⚠️ {note}")
