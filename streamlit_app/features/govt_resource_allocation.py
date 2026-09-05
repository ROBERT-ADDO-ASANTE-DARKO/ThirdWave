"""
Feature 6 — Government: Emergency Resource Allocation.

Mirrors the spec's actual workflow (Section 4.2, 9): a verified Incident
gets an available responder assigned. Verification itself now happens on
the Incident Verification page (govt_verification_sandbox.py, added for
the district-officer / routing-avoidance loop -- see project chat history)
rather than duplicating a second verification queue here; this page
consumes that shared incident_store as its live incident source, merged
with the seeded historical incidents (demo_seed_incidents.json) so the
queue isn't empty on first load.

Responder list is fabricated demo data (not from any real dataset) --
labeled as such. Everything else here (report content, incident IDs,
zone risk lookups) is either live session state or previously-validated
project data.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from data_loader import load_demo_seed_incidents, LEVEL_COLOR
import incident_store as store

DEMO_RESPONDERS = [
    {"name": "Unit A - Ablekuma North", "available": True},
    {"name": "Unit B - Accra Central", "available": True},
    {"name": "Unit C - Korle Klottey", "available": False},
    {"name": "Unit D - Ablekuma West", "available": True},
]


def _sync_verified_incidents():
    """Pulls newly-verified incidents from the shared incident_store (real
    submissions verified on Incident Verification, or synthetic ones from
    its sandbox) into this page's incident pool, in the shape this page's
    assignment UI already expects. Idempotent -- skips ids already synced.
    Zone lookup is the same shared incident_store.zone_for_point() the
    verification queue shows officers before they approve a report, so the
    severity shown here can't drift from that context."""
    existing_ids = {i["id"] for i in st.session_state.incidents}
    for inc in store.list_active_incidents():
        if inc["id"] in existing_ids:
            continue
        zone = store.zone_for_point(inc["gps_point"]["lon"], inc["gps_point"]["lat"])
        level = zone["level"] if zone else "Unknown"
        st.session_state.incidents.append({
            "id": inc["id"], "report_id": inc["source_report_id"], "hazard_type": inc["hazard_type"],
            "location": {"type": "Point", "coordinates": [inc["gps_point"]["lon"], inc["gps_point"]["lat"]]},
            "severity": level.lower().replace(" ", "_"), "status": "reported",
            "assigned_responder": None,
            "response_notes": f"Verified from citizen report {inc['source_report_id']}"
                               f"{' (synthetic demo scenario)' if inc.get('synthetic') else ''} by {inc['verified_by']}.",
            "created_at": inc["verified_at"], "resolved_at": None,
            "synthetic": inc.get("synthetic", False),
        })


def render():
    st.subheader("Emergency Resource Allocation")
    st.caption(
        "A verified Incident gets an available responder assigned (spec Section 4.2/9). Verification "
        "itself happens on the Incident Verification page -- this page picks up whatever's been verified "
        "there. Responder names are fabricated demo data, not a real roster."
    )

    if "incidents" not in st.session_state:
        seed = load_demo_seed_incidents()
        st.session_state.incidents = [
            {**inc, "assigned_responder": None}
            for inc in seed["incidents"]
        ]
    if "responder_availability" not in st.session_state:
        st.session_state.responder_availability = {r["name"]: r["available"] for r in DEMO_RESPONDERS}

    store.init_store()
    _sync_verified_incidents()

    n_pending = len(store.list_pending())
    if n_pending:
        st.info(f"{n_pending} report(s) awaiting verification on the **Incident Verification** page -- "
                "verify them there to see them appear below for responder assignment.")

    # ---- Active incidents + assignment ----
    st.markdown("### Active Incidents -- Resource Allocation")
    active = [i for i in st.session_state.incidents if i["status"] != "closed"]
    severity_rank = {"emergency": 0, "very_high": 0, "warning": 1, "high": 1, "moderate": 2, "low": 3}
    active.sort(key=lambda i: severity_rank.get(i["severity"], 2))

    if not active:
        st.info("No active incidents.")

    for inc in active:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                badge = " 🧪" if inc.get("synthetic") else ""
                st.markdown(f"**{inc['id']}**{badge}")
                st.caption(inc.get("response_notes", "")[:120])
                st.caption(f"Severity: {inc['severity'].replace('_', ' ').title()} | Status: {inc['status'].title()}")
            with c2:
                if inc.get("assigned_responder"):
                    eta_note = f" · ETA {inc['eta_minutes']}min" if inc.get("eta_minutes") is not None else ""
                    st.success(f"Assigned: {inc['assigned_responder']}{eta_note}")
                else:
                    available = [n for n, a in st.session_state.responder_availability.items() if a]
                    if available:
                        choice = st.selectbox("Assign responder", available, key=f"assign_select_{inc['id']}", label_visibility="collapsed")
                        eta = st.number_input(
                            "ETA (minutes)", min_value=1, max_value=180, value=15, step=1,
                            key=f"eta_{inc['id']}", help="Officer-entered estimate, not a real dispatch system.",
                        )
                        if st.button("Assign", key=f"assign_btn_{inc['id']}"):
                            inc["assigned_responder"] = choice
                            inc["eta_minutes"] = int(eta)
                            inc["status"] = "responding"
                            st.session_state.responder_availability[choice] = False
                            store.assign_responder(inc["id"], choice, int(eta))
                            st.rerun()
                    else:
                        st.warning("No responders available.")
            with c3:
                if inc.get("assigned_responder") and inc["status"] != "closed":
                    if st.button("Mark Resolved", key=f"resolve_{inc['id']}"):
                        inc["status"] = "closed"
                        inc["resolved_at"] = datetime.now(timezone.utc).isoformat()
                        st.session_state.responder_availability[inc["assigned_responder"]] = True
                        store.resolve_incident(inc["id"])  # no-op for seeded historical incidents
                        st.rerun()

    st.divider()
    st.markdown("### Responder Availability")
    cols = st.columns(len(DEMO_RESPONDERS))
    for col, (name, avail) in zip(cols, st.session_state.responder_availability.items()):
        col.metric(name, "Available" if avail else "Deployed")
