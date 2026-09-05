"""
Feature 5 — Citizen: Crowdsourced Flood Reporting (photo + GPS), with an
AI-drafted description + annotated depth-estimate image, and three ways to
set location: type an address, pin the map, or (unchanged) whichever the
citizen finds easiest.

Mirrors the spec's actual CitizenReport entity (Section 9) and the Report
Confirmation screen's non-negotiable rule (Section 5): a submitted report
shows "Under Review", never implying it's already official.

Architecture note: photo capture, the "Generate description with AI"
action, and address search all live OUTSIDE the st.form block deliberately
-- Streamlit forms only allow a single st.form_submit_button to trigger a
rerun; intermediate action buttons (as these need) cannot live inside one.
Only the final, citizen-edited submission goes through the form.

Storage: st.session_state only -- in-memory for this browser session, not
persisted to any backend (see project notes for why that's an honest POC
scope, not an oversight).
"""

from __future__ import annotations

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

from vlm_client import describe_flood_photo, annotate_image, VLMError
import incident_store as store

HAZARD_TYPES = ["flash_flood", "urban_flood", "river_flood"]


@st.cache_data(ttl=3600)
def geocode(address: str):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{address}, Accra, Ghana", "format": "json", "limit": 1},
            headers={"User-Agent": "ThirdWave-streamlit-poc/1.0"},
            timeout=10,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", address)
    except Exception:
        pass
    return None


def render():
    st.subheader("Report a Flood")
    st.caption(
        "Mirrors the spec's CitizenReport workflow (Section 9). Stored in this browser session only "
        "(st.session_state) -- a real deployment needs a persisted backend, which this POC doesn't build. "
        "Submitted reports go to the district officer's Incident Verification queue before they become an "
        "active incident anyone else's routing reacts to."
    )

    store.init_store()
    if "my_report_ids" not in st.session_state:
        st.session_state.my_report_ids = []
    if "report_location" not in st.session_state:
        st.session_state.report_location = None
    if "report_location_label" not in st.session_state:
        st.session_state.report_location_label = None
    if "ai_draft" not in st.session_state:
        st.session_state.ai_draft = None
    if "ai_annotated_image" not in st.session_state:
        st.session_state.ai_annotated_image = None

    # ---- Photo + AI draft (outside the form -- see module docstring) ----
    st.markdown("**1. Add a photo**")
    photo_mode = st.radio(
        "Photo source", ["Take a photo", "Upload a photo"], index=1,
        horizontal=True, label_visibility="collapsed", key="photo_mode",
    )
    # Only the chosen widget is rendered -- st.camera_input requests the
    # browser's camera the moment it mounts, regardless of whether the
    # citizen actually wants to use it. Mounting both at once (as this
    # used to) turns the camera on even when the citizen picked upload.
    if photo_mode == "Take a photo":
        photo = st.camera_input("Take a photo", label_visibility="collapsed")
    else:
        photo = st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png"], label_visibility="collapsed")

    if photo is None:
        # Stale AI draft from a since-removed/switched photo shouldn't linger.
        st.session_state.ai_draft = None
        st.session_state.ai_annotated_image = None

    if photo is not None:
        if st.button("✨ Draft description with AI", key="ai_draft_btn"):
            with st.spinner("Looking at the photo..."):
                try:
                    result = describe_flood_photo(photo.getvalue(), media_type=photo.type or "image/jpeg")
                    st.session_state.ai_draft = result
                    st.session_state.ai_annotated_image = annotate_image(photo.getvalue(), result)
                except VLMError as exc:
                    st.session_state.ai_draft = None
                    st.session_state.ai_annotated_image = None
                    st.error(f"AI description unavailable ({exc}). You can still describe it yourself below.")

        if st.session_state.ai_draft:
            draft = st.session_state.ai_draft
            if draft.get("shows_flooding") is False:
                st.warning(
                    f"AI couldn't confirm this photo shows flooding: *{draft.get('note', '')}* "
                    "You can still describe what you're seeing manually below."
                )
            else:
                icol1, icol2 = st.columns([3, 2])
                with icol1:
                    if st.session_state.ai_annotated_image:
                        st.image(st.session_state.ai_annotated_image,
                                  caption="AI-annotated: reference objects + waterline used for the depth estimate")
                    else:
                        st.caption("No confident reference objects found -- showing description only, no annotation.")
                with icol2:
                    st.info(
                        f"**AI-suggested description -- check it's accurate before submitting:**\n\n"
                        f"{draft['description']}\n\n*{draft.get('note', '')}*"
                    )
                    depth = draft.get("depth_estimate_m")
                    if depth:
                        st.caption(f"Estimated depth: {depth['low']:.1f}-{depth['high']:.1f}m (triage-quality estimate, not survey-grade)")
    else:
        st.caption("Add a photo above to enable AI-drafted descriptions (optional -- you can always write your own).")

    st.divider()
    st.markdown("**2. Where is this?**")
    loc_tab1, loc_tab2 = st.tabs(["Type an address", "Pick on map"])

    with loc_tab1:
        addr_col1, addr_col2 = st.columns([3, 1])
        address = addr_col1.text_input("Address or landmark", placeholder="e.g. Kwame Nkrumah Circle", label_visibility="collapsed")
        if addr_col2.button("Find it", key="report_geocode_btn"):
            result = geocode(address) if address else None
            if result:
                lat, lon, label = result
                st.session_state.report_location = (lon, lat)
                st.session_state.report_location_label = label
            else:
                st.error("Couldn't find that address. Try a more specific landmark, or pick on the map instead.")

    with loc_tab2:
        m = folium.Map(location=[5.5575, -0.2], zoom_start=12, tiles="OpenStreetMap")
        map_state = st_folium(m, height=280, use_container_width=True, key="report_map",
                               returned_objects=["last_clicked"])
        if map_state and map_state.get("last_clicked"):
            lat, lon = map_state["last_clicked"]["lat"], map_state["last_clicked"]["lng"]
            st.session_state.report_location = (lon, lat)
            st.session_state.report_location_label = f"Pinned location ({lat:.5f}, {lon:.5f})"

    if st.session_state.report_location:
        st.success(f"Location set: {st.session_state.report_location_label}")
    else:
        st.caption("No location set yet.")

    st.divider()
    st.markdown("**3. Confirm details and submit**")

    ai_draft = st.session_state.ai_draft or {}
    default_description = ai_draft.get("description", "") if ai_draft.get("shows_flooding") else ""
    default_hazard = ai_draft.get("suggested_hazard_type") or HAZARD_TYPES[0]

    with st.form("flood_report_form", clear_on_submit=True):
        hazard = st.selectbox(
            "What are you seeing?", HAZARD_TYPES,
            index=HAZARD_TYPES.index(default_hazard) if default_hazard in HAZARD_TYPES else 0,
            format_func=lambda h: h.replace("_", " ").title(),
        )
        description = st.text_area(
            "Describe what you see (edit the AI draft above if you used one, or write your own)",
            value=default_description,
            placeholder="e.g. Water rising fast near the market, cars stuck",
        )
        submitted = st.form_submit_button("Submit Report", type="primary")

    if submitted:
        if not st.session_state.report_location:
            st.error("Please set a location above (type an address or pick on the map) before submitting.")
        elif not description:
            st.error("Please describe what you're seeing.")
        else:
            lon, lat = st.session_state.report_location
            depth = ai_draft.get("depth_estimate_m")
            report = store.submit_report(
                lon=lon, lat=lat,
                location_label=st.session_state.report_location_label,
                hazard_type=hazard, description=description,
                depth_estimate_m=(depth["low"], depth["high"]) if depth else None,
                has_photo=photo is not None,
                photo_bytes=photo.getvalue() if photo is not None else None,
                annotated_image_bytes=st.session_state.ai_annotated_image,
                ai_assisted=bool(st.session_state.ai_draft),
            )
            st.session_state.my_report_ids.append(report["id"])
            st.session_state.report_location = None
            st.session_state.report_location_label = None
            st.session_state.ai_draft = None
            st.session_state.ai_annotated_image = None
            district_note = f" Routed to {report['district']}." if report["district"] else " Outside the pilot district -- no officer queue covers this point yet."
            st.success(
                f"**Report {report['id']} submitted -- Under Review.**{district_note} "
                "This is not yet an official incident. A district officer will verify it in Incident Verification."
            )

    if st.session_state.my_report_ids:
        st.divider()
        st.markdown(f"**Your reports this session ({len(st.session_state.my_report_ids)})**")
        pending_by_id = {r["id"]: r for r in store.list_pending()}
        active_by_source = {i["source_report_id"]: i for i in store.list_active_incidents()}
        for rid in reversed(st.session_state.my_report_ids):
            if rid in pending_by_id:
                r = pending_by_id[rid]; status_label = "Under Review"
            elif rid in active_by_source:
                r = active_by_source[rid]; status_label = "✅ Verified -- active incident"
            else:
                continue  # rejected reports aren't kept in any list this POC displays
            ai_tag = " \U0001F4F8✨" if r.get("ai_assisted") else ""
            st.markdown(f"`{rid}`{ai_tag} -- {r['hazard_type'].replace('_', ' ').title()} -- **{status_label}**")
            st.caption(r["description"])
            if rid in active_by_source and r.get("assigned_responder"):
                st.success(f"🚑 A responder has been assigned ({r['assigned_responder']}) -- ETA ~{r['eta_minutes']} min.")
            elif rid in active_by_source:
                st.caption("Verified -- awaiting responder assignment.")
