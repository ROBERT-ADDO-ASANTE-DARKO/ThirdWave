"""
Feature 3 — Government: Drain Maintenance Prioritization.

Combines two independently-validated layers to rank zones for drain
maintenance: the SAR/DEM/LULC vulnerability score (geospatial_vulnerability.py)
and the OSM building-to-waterway encroachment index (channel_encroachment_index.py).

Honest caveat, stated in the UI, not just here: "persistent hotspot" in this
view means multi-year SAR water-occurrence (2020-2024 aggregate), not
verified repeat-incident history. Real incident recurrence needs live pilot
data via incident_outcome_link, which doesn't exist until the pilot runs.

Zones with insufficient OSM coverage are shown in a separate "needs field
survey" list rather than silently dropped or ranked as low-priority --
missing data is not the same as low risk (same discipline as everywhere
else in this project).
"""

from __future__ import annotations

import folium
import pandas as pd
import streamlit as st
from shapely.geometry import shape
from streamlit_folium import st_folium

from data_loader import load_risk_zones, load_obstruction_height, LEVEL_COLOR, INK_NAVY


def render():
    st.subheader("Drain Maintenance Prioritization")
    st.caption(
        "Ranks zones combining vulnerability score with OSM-derived channel encroachment. "
        "⚠️ 'Persistent hotspot' here means multi-year SAR water occurrence (2020-2024), "
        "not verified repeat-incident history -- that needs live pilot data this project doesn't have yet."
    )

    zones = load_risk_zones()
    obstruction = load_obstruction_height()["zones"]
    rows = []
    for z in zones:
        zid = z["id"].replace("RZ-", "")
        enc_factor = next((f for f in z["contributing_factors"] if f["type"] == "channel_encroachment"), None)
        has_encroachment = enc_factor is not None and not enc_factor.get("data_insufficient", True)
        rows.append({
            "zone_id": zid,
            "assembly": z["assembly"],
            "score": z["score"],
            "level": z["level"],
            "confidence": z["confidence"],
            "has_encroachment_data": has_encroachment,
            "encroachment_text": enc_factor["text"] if enc_factor else "n/a",
            "min_dist_m": enc_factor["value"] if has_encroachment else None,
            "obstruction_m": obstruction.get(zid, {}).get("mean_obstruction_m"),
            "geometry": z["geometry"],
        })
    df = pd.DataFrame(rows)

    with_data = df[df["has_encroachment_data"]].copy()
    without_data = df[~df["has_encroachment_data"]].copy()

    # Priority = vulnerability score, with a boost for close encroachment
    # (closer building-to-waterway distance = higher priority). Simple,
    # explainable, tunable -- same "legible over black-box" discipline used
    # for the composite score itself.
    with_data["priority"] = with_data["score"] + with_data["min_dist_m"].apply(
        lambda d: 30 if d <= 10 else 15 if d <= 30 else 5 if d <= 75 else 0
    )
    with_data = with_data.sort_values("priority", ascending=False)

    col1, col2, col3 = st.columns(3)
    col1.metric("Zones with encroachment data", len(with_data))
    col2.metric("Zones needing field survey", len(without_data))
    col3.metric("Top priority zone", with_data.iloc[0]["zone_id"] if len(with_data) else "n/a")

    st.divider()

    top_n = st.slider("Show top N priority zones", 5, min(50, len(with_data)), 15)
    top = with_data.head(top_n)

    map_col, list_col = st.columns([3, 2])
    with map_col:
        st.markdown("**Top priority zones**")
        centroid = shape(top.iloc[0]["geometry"]).centroid
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=13, tiles="OpenStreetMap")
        for _, row in top.iterrows():
            folium.GeoJson(
                row["geometry"],
                style_function=lambda feat, c=LEVEL_COLOR.get(row["level"], "#999"): {
                    "fillColor": c, "color": INK_NAVY, "weight": 1, "fillOpacity": 0.65,
                },
                tooltip=folium.Tooltip(
                    f"<b>{row['zone_id']}</b><br>Priority: {row['priority']:.0f}<br>{row['encroachment_text']}"
                    + (f"<br>Obstruction: {row['obstruction_m']:.1f}m" if row['obstruction_m'] is not None else "")
                ),
            ).add_to(m)
        st_folium(m, height=420, use_container_width=True, returned_objects=[])

    with list_col:
        st.markdown("**Priority list**")
        display = top[["zone_id", "assembly", "score", "min_dist_m", "obstruction_m", "priority"]].copy()
        display.columns = ["Zone", "Assembly", "Score", "Nearest waterway (m)", "Obstruction (m)", "Priority"]
        st.dataframe(display, use_container_width=True, hide_index=True, height=420)
        st.caption(
            "Obstruction (m): Copernicus DEM minus FABDEM, a free per-cell height-above-ground proxy "
            "(r=0.83 correlated with impervious land cover -- see building_obstruction_height.py). "
            "~30m-class, not a building-level layer, and not part of the Priority score above -- shown "
            "for context, same as everywhere else this project discloses without blending. "
            "FABDEM: CC BY-NC-SA 4.0, Hawker et al. 2022, Univ. of Bristol / Fathom."
        )

    if len(without_data):
        with st.expander(f"{len(without_data)} zones need a field survey (no usable OSM waterway/building data)"):
            st.caption(
                "These zones might genuinely need drain maintenance too -- there just isn't enough "
                "free vector data to compute an encroachment estimate. Don't read absence from this list "
                "as 'no risk'."
            )
            st.dataframe(
                without_data[["zone_id", "assembly", "score", "level"]].sort_values("score", ascending=False),
                use_container_width=True, hide_index=True,
            )
