"""
Feature 8 — Citizen: High-Risk Zone Alert.

Per the feasibility discussion earlier in this project: true "notify when
entering a high-risk zone" needs background geolocation + push
notifications, which a request/response Streamlit app architecturally
cannot do. The honest substitute here is an on-demand check -- but rather
than just duplicating Feature 2 (current vulnerability), this combines
THREE signals into one actionable alert: the zone's static vulnerability
(geospatial_vulnerability.py), the live rainfall forecast (Open-Meteo,
same source as Feature 7), and -- for the "nearby, not in transit" persona
distinct from Safer Routing's (see project chat history "connecting the
dots") -- currently active, VERIFIED incidents near this location, with
evacuation guidance. "You're in a High zone" alone isn't very actionable;
"you're in a High zone, heavy rain is forecast, AND there's a verified
flood 400m away" is.
"""

from __future__ import annotations

import json
from pathlib import Path

import folium
import requests
import streamlit as st
from shapely.geometry import Point
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation

from data_loader import DATA_DIR, load_risk_grid_gdf, LEVEL_COLOR
import incident_store as store

NEARBY_RADIUS_KM = 1.5

EVACUATION_GUIDANCE = {
    "flash_flood": "Move to higher ground immediately -- flash floods can rise faster than you can outrun on "
                   "foot in a vehicle. Avoid walking or driving through moving water.",
    "urban_flood": "Avoid the flooded area and nearby low-lying streets. If water is entering your building, "
                   "move valuables and yourself to a higher floor.",
    "river_flood": "Stay away from riverbanks and low bridges near the water. Follow any district officer "
                   "instructions if the area is being evacuated.",
}
GENERIC_GUIDANCE = "Avoid the area. Do not attempt to walk or drive through standing water -- depth and current are hard to judge from a distance."


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


@st.cache_data(ttl=1800)
def fetch_next_6h_rain(lat: float, lon: float) -> float:
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "hourly": "precipitation",
                "forecast_days": 1, "timezone": "Africa/Accra"},
        timeout=15,
    )
    resp.raise_for_status()
    precip = resp.json()["hourly"]["precipitation"][:6]
    return sum(precip)


@st.cache_data
def load_thresholds():
    return json.loads((Path(DATA_DIR) / "grid_zone_threshold_config.json").read_text())


def render():
    st.subheader("High-Risk Zone Alert")
    st.caption(
        "⚠️ Not a real push notification -- Streamlit can't do background location + push, which true "
        "'notify when entering a high-risk zone' needs. This is an on-demand check combining this zone's "
        "static vulnerability with the next 6 hours of live rainfall forecast, for a genuinely actionable read "
        "rather than just repeating Feature 2's static lookup."
    )

    if "alert_location" not in st.session_state:
        st.session_state.alert_location = None

    tab1, tab2 = st.tabs(["Auto-detect", "Search address"])
    with tab1:
        loc = streamlit_geolocation()
        if loc and loc.get("latitude") is not None:
            st.session_state.alert_location = (loc["longitude"], loc["latitude"], "Detected location")
    with tab2:
        address = st.text_input("Address or landmark", placeholder="e.g. Kwame Nkrumah Circle", key="alert_addr")
        if st.button("Check this location", type="primary"):
            result = geocode(address) if address else None
            if result:
                lat, lon, label = result
                st.session_state.alert_location = (lon, lat, label)
            else:
                st.error("Couldn't find that address. Try a more specific landmark.")

    if not st.session_state.alert_location:
        st.info("Choose a location above to check your current alert status.")
        return

    lon, lat, label = st.session_state.alert_location
    grid_gdf = load_risk_grid_gdf()
    thresholds = load_thresholds()

    pt = Point(lon, lat)
    zone_row = None
    for _, row in grid_gdf.iterrows():
        if row.geometry.contains(pt):
            zone_row = row
            break

    if zone_row is None:
        st.warning(f"**{label}** is outside the pilot district's coverage area.")
        return

    zone_id = zone_row["zone_id"]
    level = zone_row["level"]
    zone_thresh = thresholds.get(zone_id, {})
    warn_mm = zone_thresh.get("rainfall_6h_warning_mm", 60)

    with st.spinner("Checking live forecast..."):
        try:
            next_6h_rain = fetch_next_6h_rain(lat, lon)
        except Exception:
            next_6h_rain = None

    is_high_zone = level in ("High", "Very High")
    is_rain_imminent = next_6h_rain is not None and next_6h_rain >= warn_mm * 0.5  # 50% of warning threshold = "watch"

    st.divider()
    if is_high_zone and next_6h_rain is not None and next_6h_rain >= warn_mm:
        st.error(
            f"🚨 **ALERT: {label} is a {level} zone, and {next_6h_rain:.0f}mm of rain is forecast in the "
            f"next 6 hours** (exceeds this zone's {warn_mm:.0f}mm warning threshold). Avoid low-lying routes."
        )
    elif is_high_zone and is_rain_imminent:
        st.warning(
            f"⚠️ **{label} is a {level} zone**, and moderate rain ({next_6h_rain:.0f}mm) is forecast in the "
            "next 6 hours. Stay alert."
        )
    elif is_high_zone:
        st.warning(f"⚠️ **{label} is a {level} zone**, but no significant rain is forecast in the next 6 hours right now.")
    elif is_rain_imminent:
        st.info(f"ℹ️ **{label} is a {level} zone** (not high-risk), but {next_6h_rain:.0f}mm of rain is forecast in the next 6 hours.")
    else:
        st.success(f"✅ **{label} is a {level} zone**, and no significant rain is forecast in the next 6 hours.")

    col1, col2 = st.columns(2)
    col1.metric("Zone vulnerability", level)
    col2.metric("Next 6h rainfall (forecast)", f"{next_6h_rain:.0f}mm" if next_6h_rain is not None else "unavailable")

    st.divider()
    st.markdown("**Active flooding near you right now**")
    store.init_store()
    nearby = store.nearby_active_incidents(lon, lat, radius_km=NEARBY_RADIUS_KM)
    if not nearby:
        st.success(f"No verified active incidents within {NEARBY_RADIUS_KM:.1f}km of this location right now.")
    else:
        for inc in nearby:
            badge = " 🧪 (demo)" if inc.get("synthetic") else ""
            st.error(
                f"🚩 **{inc['hazard_type'].replace('_', ' ').title()}{badge} -- {inc['distance_km']*1000:.0f}m away** "
                f"({inc['location_label'] or 'unnamed location'})"
            )
            st.caption(EVACUATION_GUIDANCE.get(inc["hazard_type"], GENERIC_GUIDANCE))
        st.caption(
            "This is a same-session, on-demand check (re-run this page to refresh), not a background push "
            "alert -- see the module note on why Streamlit can't do that automatically."
        )

    m = folium.Map(location=[lat, lon], zoom_start=15, tiles="OpenStreetMap")
    folium.Circle(
        [lat, lon], radius=NEARBY_RADIUS_KM * 1000, color="#1B7A9E", weight=1.5,
        fill=True, fill_opacity=0.06, tooltip=f"{NEARBY_RADIUS_KM:.1f}km search radius",
    ).add_to(m)
    folium.Marker(
        [lat, lon], tooltip=f"You: {label}", icon=folium.Icon(color="blue", icon="user", prefix="fa"),
    ).add_to(m)

    bounds = [[lat, lon]]
    for inc in nearby:
        ilat, ilon = inc["gps_point"]["lat"], inc["gps_point"]["lon"]
        bounds.append([ilat, ilon])
        badge = " (demo)" if inc.get("synthetic") else ""
        folium.PolyLine(
            [(lat, lon), (ilat, ilon)], color="#B0241D", weight=2, opacity=0.6, dash_array="5,7",
        ).add_to(m)
        folium.Marker(
            [ilat, ilon],
            tooltip=f"{inc['hazard_type'].replace('_', ' ').title()}{badge} -- {inc['distance_km']*1000:.0f}m away",
            icon=folium.Icon(color="darkred", icon="exclamation-triangle", prefix="fa"),
        ).add_to(m)
    if len(bounds) > 1:
        m.fit_bounds(bounds, padding=(40, 40))

    st_folium(m, height=380, use_container_width=True, returned_objects=[])
    st.caption("🔵 You · 🟥 Active verified incident, distance labeled · shaded circle = the search radius above.")
