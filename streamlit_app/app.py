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
    "Government": {
        "District Vulnerability Dashboard": "govt_district_dashboard",
        "Drain Maintenance Prioritization": "govt_drain_priority",
        "Population / Infrastructure Exposure": "govt_exposure",
        "Emergency Resource Allocation": "govt_resource_allocation",
        "Before/After Scenario Simulator": "govt_scenario_simulator",
        "Pluvial Flood Simulator": "govt_inundation_simulator",
        "3D Flood View": "govt_3d_flood_view",
        "Incident Verification": "govt_verification_sandbox",
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
    feature_label = st.radio("Feature", list(available.keys()))
    st.divider()
    st.caption(
        "Data: Sentinel-1 SAR, Copernicus DEM, ESA WorldCover, OpenStreetMap. "
        "Computed 2026-09-01, not live pilot data."
    )

module_name = available[feature_label]
module = __import__(f"features.{module_name}", fromlist=["render"])
module.render()
