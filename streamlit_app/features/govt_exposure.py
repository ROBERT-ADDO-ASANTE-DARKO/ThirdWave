"""
Feature 4 — Government: Population / Infrastructure Exposure.

Population: WorldPop Ghana 2020 gridded estimate, zonal-summed per cell
(population_exposure.py). Infrastructure: clean, non-double-counted OSM
building footprint count per cell (same script -- see its SOURCE_NOTE for
why this needed fixing before shipping: a naive reuse of
channel_encroachment_index.py's per-cell counts overstated the district
total by ~85,000 buildings due to boundary double-counting).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from data_loader import DATA_DIR, LEVEL_COLOR


@st.cache_data
def load_exposure():
    raw = json.loads((Path(DATA_DIR) / "population_exposure.json").read_text())
    rows = []
    for zone_id, r in raw["zones"].items():
        rows.append({"zone_id": zone_id, **r})
    return pd.DataFrame(rows), raw["source_note"]


def render():
    st.subheader("Population / Infrastructure Exposure")
    df, source_note = load_exposure()
    st.caption(source_note)

    total_pop = df["estimated_population"].sum()
    total_buildings = df["n_buildings"].sum()
    high_risk = df[df["level"].isin(["High", "Very High"])]
    high_risk_pop = high_risk["estimated_population"].sum()
    high_risk_buildings = high_risk["n_buildings"].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Estimated population", f"{total_pop:,.0f}")
    col2.metric("Buildings", f"{total_buildings:,.0f}")
    col3.metric("Population in High+ zones", f"{high_risk_pop:,.0f}", f"{100*high_risk_pop/total_pop:.1f}% of total")
    col4.metric("Buildings in High+ zones", f"{high_risk_buildings:,.0f}", f"{100*high_risk_buildings/total_buildings:.1f}% of total")

    st.divider()

    by_assembly = df.groupby("assembly").agg(
        population=("estimated_population", "sum"),
        buildings=("n_buildings", "sum"),
        mean_score=("score", "mean"),
    ).reset_index().sort_values("population", ascending=False)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Population by assembly**")
        fig = px.bar(by_assembly, x="population", y="assembly", orientation="h",
                     labels={"population": "Estimated population", "assembly": ""})
        fig.update_traces(marker_color="#1B7A9E")
        fig.update_layout(height=340, margin=dict(l=0, r=10, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
    with col_b:
        st.markdown("**Buildings by assembly**")
        fig2 = px.bar(by_assembly, x="buildings", y="assembly", orientation="h",
                      labels={"buildings": "Building count", "assembly": ""})
        fig2.update_traces(marker_color="#1E4E6B")
        fig2.update_layout(height=340, margin=dict(l=0, r=10, t=10, b=0))
        st.plotly_chart(fig2, width="stretch")

    st.divider()
    st.markdown("**Exposure vs. risk -- which zones carry the most people at the highest risk?**")
    df_sorted = df.sort_values(["level", "estimated_population"],
                                key=lambda s: s.map({"Very High": 0, "High": 1, "Moderate": 2, "Low": 3}) if s.name == "level" else s,
                                ascending=[True, False])
    top20 = df_sorted.head(20)
    display = top20[["zone_id", "assembly", "level", "score", "estimated_population", "n_buildings"]].copy()
    display.columns = ["Zone", "Assembly", "Level", "Score", "Est. Population", "Buildings"]
    st.dataframe(display, width="stretch", hide_index=True)
    st.caption(
        "Sorted by risk level (Very High first), then population within each level. "
        "Not a formal exposure model (that would combine hazard probability x exposure x vulnerability) -- "
        "a simple ranking to help prioritize outreach."
    )
