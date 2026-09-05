"""
Feature 9 — Government: Before/After Scenario Simulator.

Per the feasibility discussion earlier in this project: no real before/after
data exists for any actual completed drainage or road project in the pilot
district, so a genuine "compare vulnerability before and after a project"
feature can't be built truthfully. This is the honest substitute: a
what-if simulator using the EXACT SAME weighted formula from
geospatial_vulnerability.py (0.45 x SAR water occurrence + 0.35 x low
elevation + 0.20 x impervious cover), letting an officer see how sensitive
a zone's score is to a hypothetical change -- not a hydraulic model of any
specific intervention, and not a claim that a real project was measured.

Elevation is NOT adjustable: it's a physical terrain property a drainage
project doesn't change. Water occurrence and impervious cover are, since
those plausibly shift with drainage maintenance / permeable surfaces.
"""

from __future__ import annotations

import streamlit as st

from data_loader import load_risk_grid_gdf, LEVEL_COLOR

W_WATER, W_ELEV, W_IMPERVIOUS = 0.45, 0.35, 0.20


def score_and_level(water_pct: float, low_elev_pct: float, impervious_pct: float) -> tuple[float, str]:
    raw = W_WATER * (water_pct / 100) + W_ELEV * (low_elev_pct / 100) + W_IMPERVIOUS * (impervious_pct / 100)
    score = round(max(0.0, min(100.0, raw * 100)), 1)
    level = ("Very High" if score >= 65 else "High" if score >= 45
             else "Moderate" if score >= 25 else "Low")
    return score, level


def render():
    st.subheader("Before / After Scenario Simulator")
    st.warning(
        "⚠️ **This is a what-if tool, not a measured comparison.** No real before/after data exists for any "
        "completed drainage or road project in the pilot district. This uses the exact same formula as the "
        "real vulnerability score (geospatial_vulnerability.py) to show sensitivity to hypothetical changes -- "
        "it does not model the actual hydraulic effect of any specific intervention."
    )

    grid_gdf = load_risk_grid_gdf()
    zone_ids = sorted(grid_gdf["zone_id"].tolist())
    default_idx = zone_ids.index("grid_r11_c14") if "grid_r11_c14" in zone_ids else 0
    zone_id = st.selectbox("Select a zone", zone_ids, index=default_idx)

    row = grid_gdf[grid_gdf["zone_id"] == zone_id].iloc[0]
    current_water = row["water_occ_pct"]
    current_elev = row["low_elev_frac_pct"]
    current_impervious = row["impervious_pct"]
    current_score, current_level = row["score"], row["level"]

    st.caption(f"Zone {zone_id} · {row['assembly']} · current score {current_score:.1f} ({current_level})")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Current (real, from geospatial_vulnerability.py)**")
        st.metric("SAR water occurrence", f"{current_water:.1f}%")
        st.metric("Low elevation fraction", f"{current_elev:.1f}%")
        st.caption("Not adjustable in the scenario -- terrain doesn't change with a drainage project.")
        st.metric("Impervious cover", f"{current_impervious:.1f}%")
        st.metric("Score", f"{current_score:.1f}", current_level)

    with col2:
        st.markdown("**Hypothetical scenario**")
        sim_water = st.slider("SAR water occurrence (simulating drainage maintenance)", 0.0, 100.0, float(current_water), 0.5)
        sim_impervious = st.slider("Impervious cover (simulating permeable surfaces/green infrastructure)", 0.0, 100.0, float(current_impervious), 0.5)
        sim_score, sim_level = score_and_level(sim_water, current_elev, sim_impervious)
        delta = sim_score - current_score
        st.metric("Simulated score", f"{sim_score:.1f}", f"{delta:+.1f}", delta_color="inverse")
        st.markdown(f"Simulated level: **:{'red' if sim_level in ('High','Very High') else 'orange' if sim_level=='Moderate' else 'green'}[{sim_level}]**")

    st.divider()
    st.markdown("**What this does and doesn't show**")
    st.markdown(
        "- ✅ Shows exactly how much the *score* (not real-world flood risk) would shift if the two adjustable "
        "inputs changed by the amounts you set.\n"
        "- ✅ Uses the identical weighted formula as the real pipeline -- no separate/invented model.\n"
        "- ❌ Does NOT simulate the actual hydraulic effect of a specific drain upgrade, culvert size, or paving change.\n"
        "- ❌ Does NOT mean a real project has been measured -- elevation stays fixed because it's terrain, not "
        "an input a project could plausibly move."
    )
