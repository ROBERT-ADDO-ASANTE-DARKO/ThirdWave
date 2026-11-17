"""
Feature 8 — Multi-Year Encroachment Trend View (Government).

risk_engine/channel_encroachment_timeseries.py computed a real 2019-2026
NDBI-near-channel trend for the 272 pilot-grid cells (of 1013) that sit
near a mapped waterway at all -- never surfaced in any UI before this
page. Pairs naturally with the Analytics Dashboard's recurring-hotspot
view as the "is it getting worse" complement: that page asks whether
verified citizen reports are repeating at a location; this one asks
whether the built-up edge near a drainage channel has been creeping
closer, year over year, independent of whether anyone has reported
flooding there yet.

Honesty carried over from the script itself, not re-litigated here:
mean_ndbi_near_channel is a continuous spectral-index proxy, not a
sub-meter distance (that's channel_encroachment_index.py's job, at a
single point in time); a binary built/not-built threshold was tried and
dropped (didn't validate at any cutoff for this landscape -- NDBI
confuses bare/dry soil with built-up here); and slope_per_year is "a
direction, not a forecast." The Worsening/Stable/Improving label itself
is this page's own judgment-call threshold on top of that real slope
(+-0.01 NDBI/year), not a validated ecological cutoff -- stated plainly
rather than presented as a precise classification.

Confirmed finding worth reading before trusting any "Improving" cell:
checked against historical_flood_events.json after Weija Gbawe
Municipal's 5 steepest-improving cells turned out spatially adjacent
(not independent) and all shared one shape -- moderate-positive NDBI
2019-2021, a sharp drop to strongly negative 2022-2025, partial
recovery in 2026. That lines up with real documented Weija dam-release/
storm floods in 2020, 2022, and 2025 -- standing floodwater reads as
non-built-up in NDBI, same as any water body, so "Improving" there
most likely means recurring flooding near the channel, not reduced
construction.

CONFIRMED, not just plausible, for these 5 cells: re-fetched one clean,
low-cloud Sentinel-2 scene from a dry-season window far from each flood
date (2022-02-10, 2025-02-04) instead of the flood-blended annual
composite. Every cell's NDBI snapped back up to its 2019-2021 baseline
on that clean day -- e.g. grid_r14_c3's 2025 composite of -0.379 becomes
+0.180 on a clean day, at/above its own 2019 value. That rules out the
competing "floods discouraged construction, so there's genuinely less
built-up area" explanation for these 5 cells specifically: the built-up
signal is still there, just submerged on the days the annual composite
happened to sample, not reduced.

geo_data.encroachment_trend_cells() flags any "Improving" cell in an
assembly with a documented flood year inside its tracked window as
possible_flood_contamination -- a coarse, assembly-level overlap check.
Outside the 5 hand-verified Weija cells above, that flag is still a lead
to check, not a confirmed match -- only these 5 have been re-checked
against a clean-day scene.

Second confirmed finding, dataset-wide rather than one assembly: 2019
reads anomalously high across all 272 channel-adjacent cells -- the
single highest year of the 8-year series in 76.5% of them, higher than
2020 in 87.1%, in every one of the 7 assemblies. Checked and ruled out:
the known Sentinel-2 baseline>=04.00 radiometric-offset bug (already
correctly compensated in the source script) and annual rainfall as a
moisture confound (2019 wasn't Accra's driest year on record -- drier
years read LOWER in NDBI, the opposite of what that would predict).
Leading unconfirmed hypothesis: a scene-selection/seasonal skew specific
to 2019's thinner early Sentinel-2 archive over Ghana. Refitting every
cell's slope on 2020-2026 alone flips the Worsening/Stable/Improving
label for 22.1% of all 272 cells -- large enough that both slopes are
shown below (slope_per_year_excl_2019), with a "sensitive to 2019"
marker wherever the label depends on which one you trust.
"""

from __future__ import annotations

import os
from pathlib import Path

import folium
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

import map_tiles

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env", override=True)

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")

_DIRECTION_COLOR = {"Worsening": "#B0241D", "Stable": "#B8860B", "Improving": "#1E8A4C"}


def _get(path: str, officer_key: str, **params):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, headers={"X-Officer-Key": officer_key}, timeout=20)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def render():
    st.subheader("Multi-Year Encroachment Trend")
    st.caption(
        "Mean NDBI (built-up-like spectral index) within 100m of mapped waterways, 2019-2026, per "
        "pilot grid cell -- a continuous proxy tracked over time, not a sub-meter distance and not a "
        "forecast. Only the 272 of 1013 pilot cells that sit near a mapped waterway at all have a "
        "trend to show; the rest simply have no nearby channel."
    )

    officer_key = os.environ.get("OFFICER_API_KEY")
    if not officer_key:
        st.error("OFFICER_API_KEY not found in backend/.env -- cannot reach officer-gated endpoints.")
        return

    by_assembly, err = _get("/encroachment-trend/by-assembly", officer_key)
    if err:
        st.error(f"Could not load encroachment trend data: {err}")
        return
    if not by_assembly:
        st.info("No channel-adjacent cells with a computable trend yet.")
        return

    total_cells = sum(a["n_cells_near_channel"] for a in by_assembly)
    total_worsening = sum(a["n_worsening"] for a in by_assembly)
    total_contaminated = sum(a["n_possibly_flood_contaminated"] for a in by_assembly)
    total_sensitive = sum(a["n_sensitive_to_2019"] for a in by_assembly)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Channel-adjacent cells tracked", total_cells)
    k2.metric("Worsening", total_worsening)
    k3.metric("Improving", sum(a["n_improving"] for a in by_assembly))
    k4.metric("Sensitive to 2019", total_sensitive, help="Label flips (e.g. Improving -> Stable) once 2019 -- confirmed dataset-wide anomalous -- is dropped from the fit.")

    if total_sensitive:
        st.warning(
            f"🗓️ {total_sensitive} cell(s) only get their Worsening/Stable/Improving label from including "
            "2019 -- refit on 2020-2026 alone and the label changes. 2019 reads anomalously high basin-wide "
            "(see module docstring); treat these cells' direction as uncertain and check "
            "slope_per_year_excl_2019 below before acting on them."
        )

    if total_contaminated:
        contaminated_assemblies = ", ".join(
            f"{a['assembly']} ({a['n_possibly_flood_contaminated']})" for a in by_assembly if a["n_possibly_flood_contaminated"]
        )
        st.warning(
            f"⚠️ {total_contaminated} \"Improving\" cell(s) sit in an assembly with documented "
            f"flood history during the tracked years: {contaminated_assemblies}. Standing floodwater reads "
            "as non-built-up in NDBI too -- an improving trend there may mean recurring flooding near the "
            "channel, not reduced encroachment. CONFIRMED for Weija Gbawe's 5 steepest cells: a clean, "
            "non-flood-day scene shows the built-up signal unchanged, not reduced (see module docstring); "
            "treat the rest as a lead to check, not a verified match."
        )

    st.divider()
    st.markdown("**By assembly**")
    st.dataframe(
        [{
            "Assembly": a["assembly"], "Cells near a channel": a["n_cells_near_channel"],
            "Worsening": a["n_worsening"], "Stable": a["n_stable"], "Improving": a["n_improving"],
            "Possibly flood-contaminated": a["n_possibly_flood_contaminated"],
            "Sensitive to 2019": a["n_sensitive_to_2019"],
            "Mean slope/year": a["mean_slope_per_year"],
        } for a in by_assembly],
        width="stretch", hide_index=True,
    )

    st.divider()
    assembly = st.selectbox("Inspect one assembly", [a["assembly"] for a in by_assembly])
    cells, err2 = _get("/encroachment-trend/cells", officer_key, assembly=assembly)
    if err2:
        st.error(f"Could not load cells for {assembly}: {err2}")
        return

    map_col, chart_col = st.columns([3, 2])
    with map_col:
        st.markdown("**Map** (red = worsening, amber = stable, green = improving)")
        center = [sum(c["lat"] for c in cells) / len(cells), sum(c["lon"] for c in cells) / len(cells)]
        m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")
        for c in cells:
            flag = " ⚠️ possible flood contamination" if c["possible_flood_contamination"] else ""
            excl = c["slope_per_year_excl_2019"]
            sensitivity = (
                f" | 🗓️ excl. 2019: {excl:+.4f}/yr ({c['direction_excl_2019']})"
                if c["sensitive_to_2019"] else ""
            )
            folium.CircleMarker(
                [c["lat"], c["lon"]], radius=6, color="#0B2545", weight=1, fill=True,
                fill_color=_DIRECTION_COLOR.get(c["direction"], "#6B7280"), fill_opacity=0.8,
                tooltip=f"{c['zone_id']} -- {c['direction']} ({c['slope_per_year']:+.4f}/yr){sensitivity}{flag}",
            ).add_to(m)
        map_tiles.add_style_layers(m)
        folium.LayerControl(collapsed=True).add_to(m)
        st_folium(m, height=380, use_container_width=True, returned_objects=[])

    def _trend_chart(title: str, rows: list[dict]) -> None:
        st.markdown(f"**{title}**")
        fig = go.Figure()
        for c in rows:
            years = sorted(c["years"].keys())
            vals = [c["years"][y].get("mean_ndbi_near_channel") for y in years]
            name = c["zone_id"]
            name += " ⚠️" if c["possible_flood_contamination"] else ""
            name += " 🗓️" if c["sensitive_to_2019"] else ""
            fig.add_trace(go.Scatter(
                x=years, y=vals, mode="lines+markers", name=name,
                line=dict(color=_DIRECTION_COLOR.get(c["direction"], "#6B7280")),
            ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=10, t=10, b=0),
            yaxis_title="Mean NDBI near channel", xaxis_title=None,
            legend=dict(orientation="h", y=-0.25),
        )
        st.plotly_chart(fig, width="stretch")

    with chart_col:
        st.caption("⚠️ = possible flood contamination -- 🗓️ = label flips once 2019 is dropped from the fit")
        worst = sorted(cells, key=lambda c: -c["slope_per_year"])[:5]
        _trend_chart("Worst-trending (Worsening) cells here", worst)
        st.caption(worst[0]["trend_note"] if worst else "")

        most_improving = sorted(cells, key=lambda c: c["slope_per_year"])[:5]
        if any(c["possible_flood_contamination"] for c in most_improving):
            _trend_chart("Steepest \"Improving\" cells here (⚠️ = flood-year overlap, read skeptically)", most_improving)
