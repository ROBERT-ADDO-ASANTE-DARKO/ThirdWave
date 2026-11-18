"""
ThirdWave Streamlit POC — entry point.

Scope decision (see chat history): Streamlit is a genuine fit for the
Government/Operations Officer persona (desktop, deliberate, data-tool
shaped) and a poor one for Citizen/Responder (mobile-first, needs
offline/native capabilities Streamlit can't provide). Government features
are built as first-class; Citizen features are included but each one states
its own honest limitations inline rather than pretending Streamlit proves
out that UX.

Run: streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="ThirdWave",
    page_icon="\U0001F30A",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.6rem; }
    [data-testid="stMetricValue"] { font-family: "IBM Plex Mono", monospace; }
    </style>
    """,
    unsafe_allow_html=True,
)

FEATURES = {
    # Note: labels avoid leading "N. " -- Streamlit radio labels render as
    # Markdown, and "N. " at the start of a line is ordered-list syntax,
    # which silently eats the literal number. Checklist numbering is
    # tracked in conversation, not duplicated into the UI.
    # Split by institutional mandate, not just grouped for tidiness (see
    # project chat history): Operations is NADMO's day-to-day live-incident
    # tempo (verify -> allocate -> close roads -> brief), Planning is the
    # Assembly's longer-term infrastructure/enforcement cycle (encroachment,
    # drain budget, exposure, what-if simulators). In practice a district
    # NADMO coordinator sits on the Assembly's security committee, so one
    # officer may use both sections -- this split documents the mandate
    # each feature actually serves, not a hard access restriction.
    "Government": {
        "Operations": {
            "Live Incident Map": "govt_incident_map",
            "Incoming Reports Queue": "govt_reports_queue",
            "Incident Verification": "govt_verification_sandbox",
            "Emergency Resource Allocation": "govt_resource_allocation",
            "Road Closure Recommendations": "govt_road_closures",
            "Flood/Incident Timeline": "govt_timeline",
            "Analytics Dashboard": "govt_analytics",
            "District Briefing Review": "govt_briefing_review",
        },
        "Planning": {
            "District Vulnerability Dashboard": "govt_district_dashboard",
            "Multi-Year Encroachment Trend": "govt_encroachment_trend",
            "Drain Maintenance Prioritization": "govt_drain_priority",
            "Population / Infrastructure Exposure": "govt_exposure",
            "Before/After Scenario Simulator": "govt_scenario_simulator",
            "Pluvial Flood Simulator": "govt_inundation_simulator",
            "3D Flood View": "govt_3d_flood_view",
        },
        "AI Assistant": "ai_assistant",
    },
    "Citizen": {
        "Current Vulnerability by Address": "citizen_vulnerability",
        "Crowdsourced Flood Reporting": "citizen_report",
        "Rainfall Forecast": "citizen_forecast",
        "High-Risk Zone Alert": "citizen_alert",
        "Safer Routing": "citizen_routing",
        "AI Assistant": "ai_assistant",
    },
}

with st.sidebar:
    st.markdown("### \U0001F30A ThirdWave")
    st.caption("Streamlit proof of concept")
    role = st.radio("Role", list(FEATURES.keys()))
    available = FEATURES[role]
    if not available:
        st.info(f"No {role} features built yet -- next up per the checklist.")
        st.stop()

    # Government nests Operations/Planning sections; Citizen stays flat --
    # handle both without duplicating the sidebar logic per role.
    if any(isinstance(v, dict) for v in available.values()):
        section_label = st.radio("Section", list(available.keys()))
        section_value = available[section_label]
        if isinstance(section_value, dict):
            feature_label = st.radio("Feature", list(section_value.keys()))
            module_name = section_value[feature_label]
        else:
            feature_label, module_name = section_label, section_value
    else:
        feature_label = st.radio("Feature", list(available.keys()))
        module_name = available[feature_label]

    st.divider()
    st.caption(
        "Data: Sentinel-1 SAR, Copernicus DEM, ESA WorldCover, OpenStreetMap. "
        "Computed 2026-09-01, not live pilot data."
    )

module = __import__(f"features.{module_name}", fromlist=["render"])
module.render()
