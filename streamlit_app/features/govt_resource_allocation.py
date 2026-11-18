"""
Feature 6 / #4 — Government: Emergency Resource Allocation.

Restructured around how NADMO actually coordinates and dispatches (see
project chat history -- researched via nadmo.gov.gh and a Citi News
interview with a NADMO Inspectorate officer, not assumed):

- District Directors, stationed at the local Assembly, are NADMO's own
  stated first responders/liaison officers for district-level
  emergencies -- so each incident below defaults to ITS OWN district's
  NADMO team, not a flat statewide pool with no geographic logic (the
  old "Unit A/B/C/D" model).
- NADMO's Operations department lists "deployment of response teams"
  AND "liaison with military and police" as core functions, and for
  larger floods NADMO has pooled Fire Service, Police, Red Cross, and
  military resources alongside its own teams -- not one responder per
  incident. So an incident here can have MULTIPLE responders assigned
  at once (NADMO team + Fire + Medical + liaison), not a single pick.
- No official step-by-step dispatch protocol or internal SOP was found
  anywhere public -- this mirrors the publicly confirmed SHAPE of the
  real structure (district-first, multi-agency pooling for bigger
  events), not a claimed replica of an internal NADMO procedure.

Verification itself happens on the Incident Verification page
(govt_verification_sandbox.py) -- this page consumes that shared
incident_store as its live incident source, merged with the seeded
historical incidents (demo_seed_incidents.json) so the queue isn't
empty on first load.

Real vs. fabricated, stated plainly per category:
- NADMO District Teams, Police/Military liaison: fabricated demo
  rosters (no real roster exists for either) -- one NADMO team per
  pilot assembly (mirrors the real one-office-per-assembly structure),
  two generic liaison slots (mirrors the real liaison FUNCTION, not a
  real liaison roster).
- Fire Service, Medical/Ambulance: REAL OSM data (checked, not assumed
  -- see project chat history) -- 7 real, named fire stations and 63
  real, named hospitals turned up in/near the pilot area
  (risk_engine/emergency_facilities.py, one-time Overpass fetch, same
  pattern as every other Overpass dataset here); every one of the 7
  pilot assemblies has a real fire station within ~0.6-4.6km of its
  centroid and at least one real hospital. "Available/dispatched" for
  these is still OUR OWN session-local bookkeeping, not a real-time
  feed from the actual fire service/hospital -- OSM has no such feed;
  only the station/hospital's identity and location are real.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

from data_loader import load_demo_seed_incidents
import incident_store as store

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env", override=True)
BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")

NADMO_ASSEMBLIES = [
    "Ablekuma Central Municipal", "Ablekuma North Municipal", "Ablekuma West Municipal",
    "Accra Metropolis", "Ayawaso Central Municipal", "Korle Klottey Municipal", "Weija Gbawe Municipal",
]

# One fabricated NADMO district team per pilot assembly -- mirrors the
# real one-office-per-assembly structure, not a real roster. Korle
# Klottey starts deployed so "the incident's own district team isn't
# free" is a real state the UI has to handle, not just the happy path.
DEMO_NADMO_TEAMS = [
    {"name": f"NADMO District Team — {a}", "available": a != "Korle Klottey Municipal"}
    for a in NADMO_ASSEMBLIES
]

# NADMO Operations' own stated "liaison with military and police"
# function -- no real roster exists for either, so these stay generic
# and explicitly fabricated, same discipline as the old DEMO_RESPONDERS.
DEMO_LIAISON_UNITS = [
    {"name": "Police Liaison", "available": True},
    {"name": "Military Liaison (on request)", "available": True},
]


def _nearest_facilities(lon: float, lat: float, officer_key: str) -> dict | None:
    """Real nearest fire station + hospital for one incident -- see this
    module's docstring for the OSM coverage check behind this. None on
    any error; a missing real-data layer should never break the page's
    actual job (coordinating a response)."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/resource-allocation/nearest-facilities",
            params={"lat": lat, "lon": lon}, headers={"X-Officer-Key": officer_key}, timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _sync_verified_incidents():
    """Pulls newly-verified incidents from the shared incident_store (real
    submissions verified on Incident Verification, or synthetic ones from
    its sandbox) into this page's incident pool, in the shape this page's
    coordination UI expects. Idempotent -- skips ids already synced.
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
            "responders": [],
            "response_notes": f"Verified from citizen report {inc['source_report_id']}"
                               f"{' (synthetic demo scenario)' if inc.get('synthetic') else ''} by {inc['verified_by']}.",
            "created_at": inc["verified_at"], "resolved_at": None,
            "synthetic": inc.get("synthetic", False),
        })


def render():
    st.subheader("Emergency Resource Allocation")
    st.caption(
        "Modeled on how NADMO itself coordinates a response (see module docstring): each incident "
        "defaults to its OWN district's NADMO team, can pool multiple agencies at once (NADMO + Fire + "
        "Medical + Police/Military liaison), and Fire/Medical show the REAL nearest OSM station/hospital. "
        "NADMO teams and liaison units are still fabricated demo rosters, not a real roster."
    )

    officer_key = os.environ.get("OFFICER_API_KEY")

    if "incidents" not in st.session_state:
        seed = load_demo_seed_incidents()
        st.session_state.incidents = [{**inc, "responders": []} for inc in seed["incidents"]]
    if "nadmo_teams" not in st.session_state:
        st.session_state.nadmo_teams = {t["name"]: t["available"] for t in DEMO_NADMO_TEAMS}
    if "liaison_units" not in st.session_state:
        st.session_state.liaison_units = {u["name"]: u["available"] for u in DEMO_LIAISON_UNITS}
    if "facility_dispatch" not in st.session_state:
        st.session_state.facility_dispatch = {}  # real facility name -> available bool, populated lazily

    store.init_store()
    _sync_verified_incidents()

    n_pending = len(store.list_pending())
    if n_pending:
        st.info(f"{n_pending} report(s) awaiting verification on the **Incident Verification** page -- "
                "verify them there to see them appear below for response coordination.")

    # ---- Active incidents + coordination ----
    st.markdown("### Active Incidents -- Resource Coordination")
    active = [i for i in st.session_state.incidents if i["status"] != "closed"]
    severity_rank = {"emergency": 0, "very_high": 0, "warning": 1, "high": 1, "moderate": 2, "low": 3}
    active.sort(key=lambda i: severity_rank.get(i["severity"], 2))

    if not active:
        st.info("No active incidents.")

    for inc in active:
        inc.setdefault("responders", [])
        lon, lat = inc["location"]["coordinates"]
        district = store.assign_district(lon, lat)
        facilities = _nearest_facilities(lon, lat, officer_key) if officer_key else None
        fire = facilities.get("fire_station") if facilities else None
        hosp = facilities.get("hospital") if facilities else None

        with st.container(border=True):
            badge = " 🧪" if inc.get("synthetic") else ""
            st.markdown(f"**{inc['id']}**{badge} · {district or 'Outside pilot coverage'}")
            st.caption(inc.get("response_notes", "")[:140])
            st.caption(f"Severity: {inc['severity'].replace('_', ' ').title()} | Status: {inc['status'].title()}")

            if inc["responders"]:
                st.success("Responding: " + " · ".join(f"{r['type']}: {r['name']}" for r in inc["responders"]))

            with st.expander("Coordinate response", expanded=not inc["responders"]):
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.markdown("**NADMO District Team**")
                    team_names = [n for n, a in st.session_state.nadmo_teams.items() if a]
                    own_team = f"NADMO District Team — {district}" if district else None
                    if team_names:
                        default_idx = team_names.index(own_team) if own_team in team_names else 0
                        choice = st.selectbox("Team", team_names, index=default_idx,
                                               key=f"team_{inc['id']}", label_visibility="collapsed")
                        eta = st.number_input("ETA (min)", min_value=1, max_value=180, value=15, step=1,
                                               key=f"team_eta_{inc['id']}")
                        if st.button("Dispatch team", key=f"team_btn_{inc['id']}"):
                            inc["responders"].append({"type": "NADMO", "name": choice, "eta_minutes": int(eta)})
                            st.session_state.nadmo_teams[choice] = False
                            inc["status"] = "responding"
                            store.assign_responder(inc["id"], choice, int(eta))
                            st.rerun()
                        if own_team and own_team not in team_names:
                            st.caption(f"⚠ {district}'s own team is deployed elsewhere.")
                    else:
                        st.warning("No NADMO team available.")

                with c2:
                    st.markdown("**Fire Service** (real)")
                    if fire:
                        st.caption(f"{fire['name']} ({fire['distance_km']:.1f}km)")
                        busy = not st.session_state.facility_dispatch.get(fire["name"], True)
                        if busy:
                            st.caption("Dispatched elsewhere.")
                        elif st.button("Dispatch fire", key=f"fire_btn_{inc['id']}"):
                            inc["responders"].append({"type": "Fire", "name": fire["name"], "eta_minutes": None})
                            st.session_state.facility_dispatch[fire["name"]] = False
                            st.rerun()
                    else:
                        st.caption("No real fire station data for this location.")

                with c3:
                    st.markdown("**Medical** (real)")
                    if hosp:
                        st.caption(f"{hosp['name']} ({hosp['distance_km']:.1f}km)")
                        busy = not st.session_state.facility_dispatch.get(hosp["name"], True)
                        if busy:
                            st.caption("Dispatched elsewhere.")
                        elif st.button("Dispatch medical", key=f"med_btn_{inc['id']}"):
                            inc["responders"].append({"type": "Medical", "name": hosp["name"], "eta_minutes": None})
                            st.session_state.facility_dispatch[hosp["name"]] = False
                            st.rerun()
                    else:
                        st.caption("No real hospital data for this location.")

                st.markdown("**Police / Military liaison** (for larger events)")
                liaison_names = [n for n, a in st.session_state.liaison_units.items() if a]
                if liaison_names:
                    picked = st.multiselect("Liaison", liaison_names, key=f"liaison_{inc['id']}",
                                             label_visibility="collapsed")
                    if picked and st.button("Request liaison", key=f"liaison_btn_{inc['id']}"):
                        for name in picked:
                            inc["responders"].append({"type": "Liaison", "name": name, "eta_minutes": None})
                            st.session_state.liaison_units[name] = False
                        st.rerun()
                else:
                    st.caption("No liaison units available.")

            if inc["responders"] and inc["status"] != "closed":
                if st.button("Mark Resolved", key=f"resolve_{inc['id']}"):
                    inc["status"] = "closed"
                    inc["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    for r in inc["responders"]:
                        if r["type"] == "NADMO":
                            st.session_state.nadmo_teams[r["name"]] = True
                        elif r["type"] == "Liaison":
                            st.session_state.liaison_units[r["name"]] = True
                        elif r["type"] in ("Fire", "Medical"):
                            st.session_state.facility_dispatch[r["name"]] = True
                    store.resolve_incident(inc["id"])  # no-op for seeded historical incidents
                    st.rerun()

    st.divider()
    st.markdown("### NADMO District Team Availability")
    cols = st.columns(len(st.session_state.nadmo_teams))
    for col, (name, avail) in zip(cols, st.session_state.nadmo_teams.items()):
        col.metric(name.replace("NADMO District Team — ", ""), "Available" if avail else "Deployed")

    st.markdown("### Police / Military Liaison Availability")
    cols2 = st.columns(len(st.session_state.liaison_units))
    for col, (name, avail) in zip(cols2, st.session_state.liaison_units.items()):
        col.metric(name, "Available" if avail else "Requested")
