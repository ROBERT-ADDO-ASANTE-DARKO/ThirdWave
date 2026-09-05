"""
Feature 7 — Citizen: Rainfall Forecast.

Per the feasibility discussion earlier in this project: Prophet was the
originally suggested tool, but it needs a historical time series with
trend/seasonality to fit against, and our vulnerability score is a static
snapshot, not a time series -- there's nothing to train Prophet on. A
numerical weather forecast (Open-Meteo, free, no key, real physics-based
precipitation forecasting) is the right tool for forecasting rain, and this
feature feeds that forecast through our OWN existing rule thresholds
(grid_zone_threshold_config.json, the same rainfall_6h_warning_mm /
rainfall_6h_critical_mm values thresholds.py's live engine uses) rather
than inventing a second forecasting method.

Honest scope limit: thresholds.py's live rule engine needs BOTH rainfall
AND river level to reach Warning/Critical (see RainfallReading +
RiverLevelReading in that file). We have no river-level forecast source, so
this view is rainfall-only -- labeled as such, not presented as the full
dual-factor engine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from shapely.geometry import Point, shape

from data_loader import DATA_DIR, load_risk_grid_gdf


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
def fetch_rainfall_forecast(lat: float, lon: float) -> pd.DataFrame:
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "hourly": "precipitation",
                "forecast_days": 7, "timezone": "Africa/Accra"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()["hourly"]
    df = pd.DataFrame({"time": pd.to_datetime(data["time"]), "precip_mm": data["precipitation"]})
    df["rolling_6h_mm"] = df["precip_mm"].rolling(window=6, min_periods=1).sum()
    return df


@st.cache_data
def load_thresholds():
    return json.loads((Path(DATA_DIR) / "grid_zone_threshold_config.json").read_text())


def render():
    st.subheader("Rainfall Forecast")
    st.caption(
        "Uses a real numerical weather forecast (Open-Meteo, free, no key) fed through this project's own "
        "rule-based thresholds -- not Prophet, which has no historical risk time series to train on here. "
        "⚠️ Rainfall-only: the live rule engine (thresholds.py) also needs a river-level forecast to reach "
        "Warning/Critical, which we don't have a source for -- this view is a simplified, rainfall-only read."
    )

    if "forecast_location" not in st.session_state:
        st.session_state.forecast_location = None

    address = st.text_input("Address or landmark", placeholder="e.g. Kwame Nkrumah Circle", key="forecast_addr")
    if st.button("Get forecast", type="primary"):
        result = geocode(address) if address else None
        if result:
            lat, lon, label = result
            st.session_state.forecast_location = (lon, lat, label)
        else:
            st.error("Couldn't find that address. Try a more specific landmark.")

    if not st.session_state.forecast_location:
        st.info("Enter a location above to see its 7-day rainfall forecast.")
        return

    lon, lat, label = st.session_state.forecast_location
    st.caption(f"Location: {label}")

    grid_gdf = load_risk_grid_gdf()
    thresholds = load_thresholds()

    pt = Point(lon, lat)
    zone_id, zone_thresh = None, None
    for _, row in grid_gdf.iterrows():
        if row.geometry.contains(pt):
            zone_id = row["zone_id"]
            zone_thresh = thresholds.get(zone_id)
            break

    if not zone_thresh:
        st.warning("This location is outside the pilot grid -- no zone-specific thresholds available.")
        return

    with st.spinner("Fetching forecast..."):
        try:
            df = fetch_rainfall_forecast(lat, lon)
        except Exception as exc:
            st.error(f"Forecast unavailable: {exc}")
            return

    warn_mm = zone_thresh["rainfall_6h_warning_mm"]
    crit_mm = zone_thresh["rainfall_6h_critical_mm"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["time"], y=df["rolling_6h_mm"], mode="lines", name="6h rolling rainfall",
                              line=dict(color="#1B7A9E", width=2)))
    fig.add_hline(y=warn_mm, line_dash="dash", line_color="#B8860B",
                  annotation_text=f"Warning threshold ({warn_mm:.0f}mm/6h) -- this zone")
    fig.add_hline(y=crit_mm, line_dash="dash", line_color="#B0241D",
                  annotation_text=f"Critical threshold ({crit_mm:.0f}mm/6h) -- this zone")
    fig.update_layout(height=380, margin=dict(l=0, r=10, t=10, b=0),
                       yaxis_title="6h rolling rainfall (mm)", xaxis_title=None)
    st.plotly_chart(fig, width="stretch")

    max_forecast = df["rolling_6h_mm"].max()
    peak_time = df.loc[df["rolling_6h_mm"].idxmax(), "time"]
    if max_forecast >= crit_mm:
        st.error(f"**Critical rainfall forecast**: {max_forecast:.0f}mm/6h expected around {peak_time:%a %d %b, %H:%M} -- exceeds this zone's critical threshold.")
    elif max_forecast >= warn_mm:
        st.warning(f"**Warning-level rainfall forecast**: {max_forecast:.0f}mm/6h expected around {peak_time:%a %d %b, %H:%M} -- exceeds this zone's warning threshold.")
    else:
        st.success(f"No rainfall in the 7-day forecast is expected to exceed this zone's warning threshold ({warn_mm:.0f}mm/6h). Peak forecast: {max_forecast:.0f}mm/6h.")

    st.caption(f"Zone: {zone_id} · thresholds derived from this zone's SAR/DEM/LULC vulnerability score "
               f"({zone_thresh['vulnerability_score']:.1f}) via geospatial_vulnerability.py's derive_thresholds().")
