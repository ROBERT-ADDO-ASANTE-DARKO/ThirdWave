"""
Government — District Briefing Review.

See .claude/plans/temporal-waddling-trinket.md for the full design. This
is the first integration point between the Streamlit prototype and the
FastAPI backend (backend/) -- every other Streamlit government feature
reads risk_engine/data/*.json directly or uses incident_store.py's
session-state store; this page instead talks to the backend's new
/briefings endpoints over HTTP, because a Briefing needs to survive past
one browser session (an officer may draft today, review tomorrow).

Honest architectural limit, stated here and in the UI itself: actually
PUBLISHING the approved text as a real Claude Doc is NOT something this
Streamlit page can do on its own -- the Claude Docs connector this
project has used all session is only reachable from a Claude Code/
claude.ai agentic session, not from arbitrary backend Python, and there is
no public API for it. So "Approve" here means "this text is final, ready
to hand to the AI Engineer to publish" -- the officer pastes the resulting
link back in once it exists. This mirrors vlm_client.py's established
"AI drafts, human finalizes before anything leaves the system" discipline,
just with an extra manual handoff step this specific capability requires.
"""

from __future__ import annotations

import os

import requests
import streamlit as st

from data_loader import DATA_DIR
from geo_tools import BRIEFING_SECTION_KEYS, draft_briefing

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")
SECTION_TITLES = {
    "purpose": "Purpose", "context": "Context", "finding": "Finding",
    "implications": "What this means for the Assembly", "sources": "Sources",
}

KNOWN_DISTRICTS = [
    "Ablekuma Central Municipal", "Ablekuma North Municipal", "Ablekuma West Municipal",
    "Accra Metropolis", "Ayawaso Central Municipal", "Korle Klottey Municipal",
    "Weija Gbawe Municipal", "Ayawaso West Municipal",
    "South Tongu", "North Tongu", "Central Tongu", "Lower Manya", "Asuogyaman",
    "Ada East", "Ada West",
]


def _backend_get(path: str, **params):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _backend_post(path: str, json_body: dict):
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", json=json_body, timeout=15)
        if resp.status_code >= 400:
            return None, resp.json().get("detail", resp.text)
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _backend_patch(path: str, json_body: dict):
    try:
        resp = requests.patch(f"{BACKEND_URL}{path}", json=json_body, timeout=10)
        if resp.status_code >= 400:
            return None, resp.json().get("detail", resp.text)
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _render_draft_form():
    st.markdown("**Draft a new briefing**")
    col1, col2 = st.columns([2, 1])
    with col1:
        district = st.selectbox("District", KNOWN_DISTRICTS, key="brf_district")
    with col2:
        trigger_reason = st.selectbox("Reason", ["manual", "new_encroachment_finding", "new_historical_event"], key="brf_reason")
    source_finding = st.text_input("Source finding (optional note on what prompted this)", key="brf_source")

    if st.button("🪄 Draft with AI", type="primary"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY not set -- see ThirdWave/.env")
            return
        with st.spinner(f"Drafting a briefing for {district} (looking up real findings)..."):
            result = draft_briefing(district, trigger_reason=trigger_reason, source_finding=source_finding or None)
        if "error" in result:
            st.error(f"Drafting failed: {result['error']}")
            if result.get("raw"):
                with st.expander("Model's raw output"):
                    st.code(result["raw"])
            return
        saved, err = _backend_post("/briefings/draft", {
            "district": district, "trigger_reason": trigger_reason,
            "source_finding": source_finding or None, "sections": result["sections"],
        })
        if err:
            st.error(f"Drafted successfully but couldn't save to the backend: {err}")
            st.caption(f"Is the backend running at {BACKEND_URL}? (cd backend && uvicorn main:app --reload)")
            return
        st.success(f"Drafted and saved — {saved['id']}. Scroll down to review it.")
        st.rerun()


def _render_briefing_card(b: dict):
    with st.container(border=True):
        st.markdown(f"`{b['id']}` — **{b['district']}** — reason: {b['trigger_reason']}")
        if b.get("source_finding"):
            st.caption(b["source_finding"])

        edited = {}
        for key in BRIEFING_SECTION_KEYS:
            st.markdown(f"**{SECTION_TITLES[key]}**")
            edited[key] = st.text_area(
                SECTION_TITLES[key], value=b["sections"].get(key, ""), key=f"edit_{b['id']}_{key}",
                label_visibility="collapsed", height=120 if key in ("context", "finding", "implications") else 70,
            )

        images = []
        from geo_tools import get_satellite_evidence_paths_for_district
        evidence = get_satellite_evidence_paths_for_district(b["district"])
        for img in evidence["images"]:
            if img["present_on_this_checkout"]:
                images.append(img["filename"])
        if images:
            st.caption(f"📷 Satellite evidence available to attach when publishing: {', '.join(images)}")

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("💾 Save edits", key=f"save_{b['id']}"):
                _, err = _backend_patch(f"/briefings/{b['id']}/sections", {"sections": edited})
                if err:
                    st.error(err)
                else:
                    st.success("Saved.")
                    st.rerun()
        with c2:
            if st.button("❌ Reject", key=f"reject_{b['id']}"):
                _, err = _backend_post(f"/briefings/{b['id']}/review", {"approve": False, "reviewed_by": "Demo Officer"})
                if err:
                    st.error(err)
                else:
                    st.rerun()

        st.caption(
            "Publishing creates a real, shareable document (same as the Weija Gbawe/East Legon/South Tongu "
            "briefings already produced this session) — the AI Engineer does this using the saved text above, "
            "then the resulting link is pasted in here to finalize the record. This page can't call the Claude "
            "Docs connector itself (it isn't reachable from a standalone Streamlit app)."
        )
        doc_url = st.text_input("Published doc URL (paste in once available)", key=f"url_{b['id']}")
        with c3:
            if st.button("✅ Approve & record publish link", key=f"approve_{b['id']}", disabled=not doc_url):
                _, err = _backend_post(f"/briefings/{b['id']}/review", {
                    "approve": True, "reviewed_by": "Demo Officer", "doc_url": doc_url,
                })
                if err:
                    st.error(err)
                else:
                    st.success("Approved and recorded.")
                    st.rerun()


def render():
    st.subheader("District Briefing Review")
    st.caption(
        "AI-drafted, human-reviewed briefing documents for district assemblies — grounded in the same risk "
        "engine data as the rest of this app (channel-encroachment index, historical flood events, verified "
        "satellite imagery). A draft is never sent anywhere without an officer reviewing and editing it first."
    )

    pending, err = _backend_get("/briefings/pending")
    if err:
        st.warning(f"Can't reach the backend at {BACKEND_URL} ({err}) — start it with `cd backend && uvicorn main:app --reload`.")
        pending = []

    st.metric("Pending review", len(pending or []))

    with st.expander("➕ Draft a new briefing", expanded=not pending):
        _render_draft_form()

    st.divider()
    st.markdown("**Pending briefings**")
    if not pending:
        st.info("No briefings pending review.")
    for b in pending:
        _render_briefing_card(b)
