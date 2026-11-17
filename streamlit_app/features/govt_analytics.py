"""
Feature 7 — Analytics Dashboard (Government).

Three views over the live Report table (backend/analytics.py), each
honest about what real but still-thin pilot data can support:

  - Response times: verification latency (submitted -> verified) and
    resolution latency (verified -> resolved), real for every report
    that's reached that stage. n is always shown next to the number --
    a 2-report average is never presented as a stable statistic.
  - Reports by district: a straight count by district x status.
  - Recurring hotspots: clusters of >=2 VERIFIED/RESOLVED reports within
    ~300m (clustering.py), paired with that location's existing static
    vulnerability score for context -- the same persistent-signal-vs-
    still-accumulating-signal distinction govt_drain_priority.py already
    draws. With only a handful of real reports so far, this page says so
    explicitly rather than dressing up thin data as a trend.
"""

from __future__ import annotations

import os
from pathlib import Path

import folium
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from data_loader import LEVEL_COLOR

import map_tiles

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env", override=True)

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")


def _get(path: str, officer_key: str, **params):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, headers={"X-Officer-Key": officer_key}, timeout=20)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _fmt_minutes(stat: dict) -> str:
    if stat["n"] == 0:
        return "No data yet"
    hours = stat["median_min"] / 60
    return f"{hours:.1f}h (median, n={stat['n']})" if hours >= 1 else f"{stat['median_min']:.0f}min (median, n={stat['n']})"


def render():
    st.subheader("Analytics Dashboard")

    officer_key = os.environ.get("OFFICER_API_KEY")
    if not officer_key:
        st.error("OFFICER_API_KEY not found in backend/.env -- cannot reach officer-gated endpoints.")
        return

    rt, err1 = _get("/analytics/response-times", officer_key)
    by_dist, err2 = _get("/analytics/by-district", officer_key)
    hs, err3 = _get("/analytics/hotspots", officer_key)
    if err1 or err2 or err3:
        st.error(f"Could not load analytics: {err1 or err2 or err3}")
        return

    st.markdown("**Response times**")
    k1, k2, k3 = st.columns(3)
    k1.metric("Total reports (all time)", rt["total_reports"])
    k2.metric("Verification time", _fmt_minutes(rt["verification_latency"]))
    k3.metric("Resolution time", _fmt_minutes(rt["resolution_latency"]))
    st.caption(
        "Verification: submitted -> verified. Resolution: verified -> resolved. Medians shown, not "
        "means, so one slow outlier doesn't dominate -- n is the actual sample size behind each number."
    )

    st.divider()
    st.markdown("**Reports by district**")
    if not by_dist:
        st.info("No reports yet.")
    else:
        rows = []
        for d in by_dist:
            for status in ("pending", "verified", "rejected", "resolved"):
                if d[status]:
                    rows.append({"District": d["district"], "Status": status.title(), "Count": d[status]})
        fig = px.bar(
            rows, x="Count", y="District", color="Status", orientation="h",
            category_orders={"District": [d["district"] for d in by_dist][::-1]},
        )
        fig.update_layout(height=max(220, 60 * len(by_dist)), margin=dict(l=0, r=10, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(by_dist, width="stretch", hide_index=True)

    st.divider()
    st.markdown("**Recurring hotspots**")
    st.caption(hs["note"])
    hotspots = hs["hotspots"]
    if not hotspots:
        st.info(f"No location has 2+ verified/resolved reports yet (out of {hs['n_verified_or_resolved_reports_considered']} total) -- nothing to flag as a repeat-incident candidate.")
        return

    map_col, table_col = st.columns([3, 2])
    with map_col:
        center = [hotspots[0]["centroid"]["lat"], hotspots[0]["centroid"]["lon"]]
        m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")
        for h in hotspots:
            level = h["static_zone"]["level"] if h["static_zone"] else None
            color = LEVEL_COLOR.get(level, "#6B7280")
            badge = " \U0001F9EA" if h["any_synthetic"] else ""
            folium.CircleMarker(
                [h["centroid"]["lat"], h["centroid"]["lon"]], radius=10 + 2 * h["n_reports"],
                color="#0B2545", weight=1.5, fill=True, fill_color=color, fill_opacity=0.75,
                tooltip=f"{h['n_reports']} report(s){badge} -- {h['district'] or 'outside pilot district'}",
            ).add_to(m)
        map_tiles.add_style_layers(m)
        folium.LayerControl(collapsed=True).add_to(m)
        st_folium(m, height=380, use_container_width=True, returned_objects=[])
    with table_col:
        for h in hotspots:
            badge = " \U0001F9EA" if h["any_synthetic"] else ""
            with st.container(border=True):
                st.markdown(f"**{h['n_reports']} report(s){badge}** — {h['district'] or 'outside pilot district'}")
                st.caption(", ".join(h["hazard_types"]).replace("_", " "))
                if h["static_zone"]:
                    z = h["static_zone"]
                    color = LEVEL_COLOR.get(z["level"], "#999")
                    st.markdown(
                        f"<span style='background:{color}22;border:1px solid {color};color:{color};"
                        f"border-radius:3px;padding:1px 7px;font-size:0.82rem;'>"
                        f"Static score here: {z['score']:.1f} ({z['level']})</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("Outside all scored coverage -- no static score to compare against.")
