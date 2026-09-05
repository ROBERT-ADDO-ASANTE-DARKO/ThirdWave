"""
Feature 1 — Ward/District-Level Vulnerability Dashboard (Government).

Shows the composite vulnerability score per assembly (SAR + DEM + LULC,
geospatial_vulnerability.py), a real interactive map (folium -- unlike the
Claude artifact, Streamlit isn't sandboxed against tile servers, so this can
show genuine basemap imagery), and the component breakdown per assembly so
an officer can see what's driving each score, not just the number.
"""

from __future__ import annotations

import json

import folium
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from data_loader import (
    DATA_DIR, load_assembly_scores, load_extended_district_scores,
    load_assembly_geometries, load_extended_assembly_geometries,
    LEVEL_COLOR, INK_NAVY,
)

OVERLAY_DIR = DATA_DIR / "overlays"


@st.cache_data
def load_overlay_manifest():
    manifest_path = OVERLAY_DIR / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text())


def _swatch(color: str, label: str) -> str:
    return (
        f"<span style='display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:0.82rem;'>"
        f"<span style='width:12px;height:12px;border-radius:2px;background:{color};"
        f"border:1px solid rgba(0,0,0,.25);display:inline-block;'></span>{label}</span>"
    )


def _render_map_legend(manifest: dict | None):
    """The map itself has no built-in legend for either the risk-zone
    colors or the raw evidence overlays -- built from the same LEVEL_COLOR
    dict and overlay manifest the map layers themselves are drawn from, so
    it can't drift out of sync with what's actually on the map."""
    st.markdown("**Map legend**")

    zone_html = "".join(_swatch(c, level) for level, c in LEVEL_COLOR.items())
    st.markdown(f"Risk zones (score): {zone_html}", unsafe_allow_html=True)

    if not manifest:
        return

    sar_grad = "linear-gradient(90deg, rgba(20,90,200,0.05), rgba(20,90,200,1))"
    st.markdown(
        f"SAR water occurrence: "
        f"<span style='display:inline-block;width:110px;height:12px;vertical-align:middle;"
        f"background:{sar_grad};border:1px solid rgba(0,0,0,.25);border-radius:2px;'></span>"
        f"<span style='font-size:0.82rem;'> &nbsp;less frequent &rarr; more frequent water</span>",
        unsafe_allow_html=True,
    )

    dem_grad = "linear-gradient(90deg, rgb(27,120,55), rgb(230,210,130), rgb(110,66,30))"
    st.markdown(
        f"Elevation: "
        f"<span style='display:inline-block;width:110px;height:12px;vertical-align:middle;"
        f"background:{dem_grad};border:1px solid rgba(0,0,0,.25);border-radius:2px;'></span>"
        f"<span style='font-size:0.82rem;'> &nbsp;low-lying &rarr; higher ground</span>",
        unsafe_allow_html=True,
    )

    wc_classes = manifest["layers"].get("worldcover", {}).get("classes_present", [])
    if wc_classes:
        wc_html = "".join(
            _swatch(f"rgb({c['color_rgb'][0]},{c['color_rgb'][1]},{c['color_rgb'][2]})", c["name"].replace("_", " "))
            for c in wc_classes
        )
        st.markdown(f"Land cover: {wc_html}", unsafe_allow_html=True)


def render():
    st.subheader("Ward / District Vulnerability Dashboard")
    st.caption(
        "Composite score = 0.45 x SAR water occurrence (2020-2024) + 0.35 x low-elevation fraction "
        "+ 0.20 x impervious land cover. Land cover components are reported for context, not weighted "
        "further -- weighting them in once flattened the score's discrimination (see project notes)."
    )

    scope = st.radio(
        "Coverage",
        ["Pilot district (6 assemblies)", "Extended coverage (10 districts)"],
        horizontal=True,
        help="Pilot district is the MVP's actual scope (spec Section 2.1). Extended coverage adds "
             "4 districts with documented flood history (Weija Gbawe, Ga South, Tema, Ashaiman), "
             "added for regional context -- not part of the MVP pilot deliverable.",
    )
    is_extended = scope.startswith("Extended")

    df = load_extended_district_scores() if is_extended else load_assembly_scores()
    gdf = load_extended_assembly_geometries() if is_extended else load_assembly_geometries()

    # ---- KPI row ----
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Districts shown", len(df))
    col2.metric("Highest score", f"{df['score'].max():.1f}", df.iloc[0]["assembly"])
    col3.metric("Mean score", f"{df['score'].mean():.1f}")
    n_moderate_plus = (df["score"] >= 25).sum()
    col4.metric("Moderate or above", int(n_moderate_plus))

    st.divider()

    map_col, chart_col = st.columns([3, 2])

    with map_col:
        st.markdown("**District map**")
        merged = gdf.merge(df, left_on="name", right_on="assembly")
        centroid = merged.geometry.union_all().centroid
        # NOTE: CartoDB's free tile styles now require an API key -- "CartoDB positron"
        # renders as an "API KEY REQUIRED" watermark without one. Plain OpenStreetMap
        # tiles remain genuinely free/anonymous.
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=12, tiles="OpenStreetMap")

        zones_fg = folium.FeatureGroup(name="Risk zones (score)", show=True)
        for _, row in merged.iterrows():
            color = LEVEL_COLOR.get(row["level"], "#999999")
            folium.GeoJson(
                row["geometry"].__geo_interface__,
                style_function=lambda feat, c=color: {
                    "fillColor": c, "color": INK_NAVY, "weight": 1.2, "fillOpacity": 0.55,
                },
                tooltip=folium.Tooltip(
                    f"<b>{row['name']}</b><br>Score: {row['score']:.1f} ({row['level']})<br>"
                    f"Water occurrence: {row['water_occ_pct']:.1f}%"
                ),
            ).add_to(zones_fg)
        zones_fg.add_to(m)

        # Raw geospatial evidence layers -- exported once by
        # export_raster_overlays.py (see risk_engine/), not fetched live.
        # Pilot-district scope only: the extended-coverage districts weren't
        # rasterized for this overlay. Off by default so the map opens on
        # the score view; an officer opts into the underlying evidence.
        manifest = load_overlay_manifest() if not is_extended else None
        if manifest:
            bounds = manifest["bounds"]
            layer_specs = [
                ("sar_water_occurrence", "SAR water occurrence (Sentinel-1)"),
                ("dem_elevation", "Elevation (Copernicus DEM)"),
                ("worldcover", "Land cover (ESA WorldCover)"),
            ]
            for key, label in layer_specs:
                layer = manifest["layers"].get(key)
                if not layer:
                    continue
                folium.raster_layers.ImageOverlay(
                    image=str(OVERLAY_DIR / layer["file"]),
                    bounds=bounds,
                    name=label,
                    opacity=1.0,
                    show=False,
                ).add_to(m)
            folium.LayerControl(collapsed=False).add_to(m)

        st_folium(m, height=430, use_container_width=True, returned_objects=[])
        if manifest:
            st.caption(
                "Layer toggle (top-right of map) switches between the composite score and the raw "
                "satellite/terrain evidence it's built from -- SAR water occurrence, DEM elevation, "
                "ESA WorldCover land cover. Static export from a %d-scene SAR sample, not a live feed."
                % manifest["scenes_used"]
            )
        elif not is_extended:
            st.caption(
                "Raw SAR/DEM/WorldCover overlays not exported yet -- run "
                "risk_engine/export_raster_overlays.py to enable the evidence-layer toggle."
            )

        _render_map_legend(manifest)

    with chart_col:
        st.markdown("**Score by district**")
        fig = px.bar(
            df, x="score", y="assembly", orientation="h", color="level",
            color_discrete_map=LEVEL_COLOR,
            category_orders={"assembly": df["assembly"].tolist()[::-1]},
            labels={"score": "Vulnerability score", "assembly": "", "level": "Level"},
        )
        fig.update_layout(height=430, margin=dict(l=0, r=10, t=10, b=0), legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.markdown("**Component breakdown**")
    st.caption("Only relevant for the pilot district's 6 assemblies -- the extended-coverage set uses "
               "the same formula but wasn't re-audited for component-level display.")
    if not is_extended:
        display_df = df[["assembly", "score", "level", "water_occ_pct", "low_elev_frac_pct",
                          "median_elev_m", "impervious_pct", "wetland_water_pct"]].copy()
        display_df.columns = ["Assembly", "Score", "Level", "SAR Water Occ. %", "Low Elev. %",
                               "Median Elev. (m)", "Impervious %", "Wetland/Water %"]
        st.dataframe(display_df, width="stretch", hide_index=True)
    else:
        st.dataframe(df, width="stretch", hide_index=True)
