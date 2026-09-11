"""
Government — Incident Verification (+ Demo Scenario Sandbox).

Two things on one page, deliberately -- see project chat history
"connecting the dots" / sandbox discussion:

1. A REAL district-officer verification queue: pending citizen reports
   (from citizen_report.py, district-assigned via incident_store.py) get
   Approve/Reject here. Approving promotes a report to an active incident,
   which citizen_routing.py then routes around. This is the missing link
   that makes the rest of the reporting/routing loop real instead of
   simulated.

2. A scenario sandbox that SEEDS the queue above with synthetic reports,
   because there's no live flood data to test this pipeline against. It
   deliberately does NOT use AI agents to play citizen/official roles (see
   chat history for why -- a scripted generator is more reliable for a live
   demo, and the pipeline's reaction is what needs testing, not a simulated
   persona's judgment). Depth comes from the same simulate_ponding() model
   used everywhere else in this project; only the report text is templated.
   Every synthetic report/incident is tagged and always shown with a
   synthetic badge -- never presented as a real submission.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import requests
import streamlit as st

from data_loader import DATA_DIR, LEVEL_COLOR
from inundation_model import simulate_ponding
import incident_store as store

INPUTS_PATH = DATA_DIR / "inundation_inputs.npz"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "demo_screenshots" / "incident_pipeline"

WALKTHROUGH = [
    ("01_sandbox_scenario_seeded.png", "1. Seed a scenario", "The sandbox above generates synthetic, tagged reports from a real simulated depth at a chosen location."),
    ("02_report_verified_active_incident.png", "2. Verify it", "Approving a pending report here promotes it to an active incident."),
    ("03_routing_no_detour_needed.png", "3a. No detour needed here", "When a route doesn't pass near any active incident, the fastest and safer routes stay the same."),
    ("04_routing_detour_around_incident.png", "3b. Detour when it matters", "When a route WOULD pass near an active incident, the safer route detours around it -- this is the payoff."),
    ("05_resource_allocation_before.png", "4a. Before verification", "Emergency Resource Allocation has nothing to assign yet."),
    ("06_resource_allocation_after.png", "4b. After verification", "The same verified incident is now assignable to a responder."),
    ("07_real_citizen_report_submitted.png", "5. A real (non-synthetic) report", "The same pipeline, but from an actual citizen submission -- district-routed automatically."),
    ("08_real_report_in_verification_queue.png", "6. ...and it lands in the same queue", "Real and synthetic reports flow through one identical pipeline."),
]


@st.cache_resource
def load_inundation_inputs():
    if not INPUTS_PATH.exists():
        return None
    d = np.load(INPUTS_PATH)
    return d["dem"], d["worldcover"], d["bbox"]


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


def _depth_at_point(dem, wc_int, bbox, rainfall_mm, lon, lat):
    """Median simulated depth over a small 3x3-pixel window around the
    point, not the single nearest pixel. This grid is coarse (~100m) and
    the CA model is genuinely heterogeneous pixel-to-pixel (a real drainage
    network has sharp local minima/maxima); a geocoded address can easily
    land one pixel off from where a different geocode of "the same place"
    would, and single-pixel readings swing from near-zero to >1m as a
    result. A small-window median is far less sensitive to that alignment
    noise while still reflecting the local terrain, not a district-wide
    average."""
    minlon, minlat, maxlon, maxlat = bbox
    rows, cols = dem.shape
    row = int((maxlat - lat) / (maxlat - minlat) * rows)
    col = int((lon - minlon) / (maxlon - minlon) * cols)
    row = min(max(row, 0), rows - 1)
    col = min(max(col, 0), cols - 1)
    depth = simulate_ponding(dem, wc_int, rainfall_mm=rainfall_mm, iterations=250)
    r0, r1 = max(row - 1, 0), min(row + 2, rows)
    c0, c1 = max(col - 1, 0), min(col + 2, cols)
    return float(np.median(depth[r0:r1, c0:c1]))


def render():
    st.subheader("Incident Verification")
    store.init_store()

    with st.expander("📸 How this works -- a walkthrough", expanded=False):
        st.caption(
            "Screenshots from a real run of this exact pipeline: seed or submit a report, verify it, "
            "and watch Safer Routing and Emergency Resource Allocation react to it."
        )
        if not SCREENSHOTS_DIR.exists():
            st.caption("(Walkthrough images not found -- see streamlit_app/demo_screenshots/incident_pipeline/)")
        else:
            cols = st.columns(2)
            for i, (fname, title, note) in enumerate(WALKTHROUGH):
                path = SCREENSHOTS_DIR / fname
                if not path.exists():
                    continue
                with cols[i % 2]:
                    st.image(str(path), caption=None, use_container_width=True)
                    st.markdown(f"**{title}**")
                    st.caption(note)

    with st.expander("🧪 Demo scenario sandbox -- seed synthetic reports (no live flood data exists)", expanded=False):
        st.caption(
            "Generates synthetic, clearly-tagged citizen reports from the same rainfall-inundation model "
            "used elsewhere in this project, so the verification queue and routing avoidance below can be "
            "demoed end-to-end. Never mixed with real submissions without the synthetic badge."
        )
        inputs = load_inundation_inputs()
        if inputs is None:
            st.error("Run risk_engine/precompute_inundation_inputs.py first.")
        else:
            dem, wc_int, bbox = inputs
            scenario_source = st.radio(
                "Scenario source", ["Historical event", "Custom location"], horizontal=True, key="sandbox_source"
            )

            is_dam_release = False
            if scenario_source == "Historical event":
                events = store.historical_scenario_points()
                labels = [f"{e['name']} ({e['date']})" for e in events]
                choice = st.selectbox("Event", labels, key="sandbox_event")
                event = events[labels.index(choice)]
                lon, lat, label = event["lon"], event["lat"], event["location_name"]
                is_dam_release = event.get("hazard_type") == "dam_release_flood"
                if is_dam_release:
                    st.info(
                        "**Dam-release event.** Rainfall ponding (the model behind the other scenarios) "
                        "doesn't represent this hazard -- `simulate_ponding()` returns ~0 for a point like "
                        "this because it isn't a local rain sink, even though the real event submerged ground "
                        "floors. Reports here are seeded from the documented event and its SAR-measured "
                        "extent (`risk_engine/dam_spillage_sar_comparison.py`) instead, with `river_flood` "
                        "hazard type and ground-floor-inundation depths."
                    )
                    rainfall_mm = 0
                else:
                    rainfall_mm = st.slider("Rainfall for this scenario (mm)", 0, 180, 110, 5, key="sandbox_rain_hist")
            else:
                addr = st.text_input("Location", placeholder="e.g. Kaneshie Market", key="sandbox_addr")
                rainfall_mm = st.slider("Rainfall for this scenario (mm)", 0, 180, 80, 5, key="sandbox_rain_custom")
                lon = lat = label = None
                if addr:
                    geo = geocode(addr)
                    if geo:
                        lat, lon, label = geo
                    else:
                        st.error(f"Couldn't find '{addr}'.")

            n_reports = st.slider("Number of synthetic reports to generate", 1, 5, 2, key="sandbox_n")

            if st.button("🌊 Seed this scenario", type="primary", key="sandbox_seed_btn"):
                if lon is None:
                    st.error("Pick a valid location first.")
                else:
                    rng = np.random.default_rng()
                    created = []
                    if is_dam_release:
                        for _ in range(n_reports):
                            jlon = lon + rng.uniform(-0.0015, 0.0015)
                            jlat = lat + rng.uniform(-0.0015, 0.0015)
                            created.append(store.generate_dam_release_report(
                                lon=jlon, lat=jlat, location_label=label, rng=rng,
                            ))
                        depths = [r["depth_estimate_m"] for r in created]
                        lo = min(d[0] for d in depths); hi = max(d[1] for d in depths)
                        st.success(
                            f"Seeded {len(created)} synthetic dam-release report(s) near **{label}** "
                            f"(ground-floor inundation, depth ≈ {lo:.1f}-{hi:.1f}m -- anchored to the "
                            "documented event, not the rainfall model). Scroll down to verify them."
                        )
                    else:
                        depth = _depth_at_point(dem, wc_int, bbox, rainfall_mm, lon, lat)
                        for _ in range(n_reports):
                            jlon = lon + rng.uniform(-0.0015, 0.0015)
                            jlat = lat + rng.uniform(-0.0015, 0.0015)
                            jdepth = max(depth + rng.uniform(-0.05, 0.05), 0.0)
                            created.append(store.generate_synthetic_report(
                                lon=jlon, lat=jlat, location_label=label, depth_m=jdepth, rng=rng,
                            ))
                        st.success(
                            f"Seeded {len(created)} synthetic report(s) near **{label}** "
                            f"(simulated depth ≈ {depth * 100:.0f}cm at {rainfall_mm}mm rainfall). "
                            "Scroll down to verify them."
                        )

    st.divider()

    pending = store.list_pending()
    active = store.list_active_incidents()

    k1, k2, k3 = st.columns(3)
    k1.metric("Pending reports", len(pending))
    k2.metric("Active incidents", len(active))
    k3.metric("Synthetic in queue", sum(1 for r in pending if r.get("synthetic")))

    st.markdown("**Pending reports -- verify before they become active incidents**")
    if not pending:
        st.info("No pending reports. Seed a scenario above, or submit one via the Citizen 'Crowdsourced Flood Reporting' page.")
    for r in pending:
        badge = " 🧪 SYNTHETIC" if r.get("synthetic") else ""
        district = r["district"] or "outside pilot district"
        zone = store.zone_for_point(r["gps_point"]["lon"], r["gps_point"]["lat"])
        with st.container(border=True):
            c_img, c1, c2 = st.columns([1.4, 3.1, 1])
            with c_img:
                image_bytes = r.get("annotated_image_bytes") or r.get("photo_bytes")
                if image_bytes:
                    st.image(image_bytes, use_container_width=True,
                             caption="AI-annotated" if r.get("annotated_image_bytes") else "Submitted photo")
                elif r.get("has_photo"):
                    st.caption("Photo submitted, but no confident AI annotation was produced.")
                else:
                    st.caption("No photo submitted with this report.")
            with c1:
                st.markdown(f"`{r['id']}`{badge} — **{r['hazard_type'].replace('_', ' ').title()}** — {district}")
                st.caption(r["location_label"] or f"{r['gps_point']['lat']:.4f}, {r['gps_point']['lon']:.4f}")
                st.write(r["description"])
                if r.get("depth_estimate_m"):
                    lo, hi = r["depth_estimate_m"]
                    st.caption(f"Estimated depth: {lo:.1f}-{hi:.1f}m")
                if zone:
                    color = LEVEL_COLOR.get(zone["level"], "#999")
                    st.markdown(
                        f"<span style='background:{color}22;border:1px solid {color};color:{color};"
                        f"border-radius:3px;padding:1px 7px;font-size:0.82rem;'>"
                        f"📍 Verification context: this zone's existing static score is "
                        f"<b>{zone['score']:.1f} ({zone['level']})</b> -- {zone['id'].replace('RZ-', '')}"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("📍 This location falls outside the 1013-cell scored grid -- no pre-existing static score to cross-check against.")
            with c2:
                if st.button("✅ Verify", key=f"verify_{r['id']}", type="primary"):
                    store.verify_report(r["id"], approve=True)
                    st.rerun()
                if st.button("❌ Reject", key=f"reject_{r['id']}"):
                    store.verify_report(r["id"], approve=False)
                    st.rerun()

    st.divider()
    st.markdown("**Active incidents -- currently routed around by Safer Routing**")
    if not active:
        st.caption("No active incidents right now.")
    for inc in active:
        badge = " 🧪 SYNTHETIC" if inc.get("synthetic") else ""
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"`{inc['id']}`{badge} — **{inc['hazard_type'].replace('_', ' ').title()}** — {inc['district'] or 'outside pilot district'}")
                st.caption(f"{inc['location_label']} · verified {inc['verified_at'][:16].replace('T', ' ')} UTC")
            with c2:
                if st.button("Mark resolved", key=f"resolve_{inc['id']}"):
                    store.resolve_incident(inc["id"])
                    st.rerun()
