"""
Feature 5 — Road Closure Recommendations (Government).

route_engine.py (Safer Routing) already treats every edge within ~200m
of an active incident as "near it" and steers citizens away via a heavy
weight penalty (build_incident_aware_weight/incidents_near_path). This
page summarizes that same existing avoidance data two ways:

  1. A weighted closure score per unique road segment
     (backend/road_closure_score.py) -- the headline table/map below.
     Combines this event's own water depth, how many independent
     verified reports back it, the road's OSM class (faster/busier
     roads are more dangerous flooded, not more flood-prone), documented
     flood history nearby, and the near-term rainfall forecast. See that
     module's docstring for the exact weights and why each one is what
     it is. Bucketed with this app's existing Low/Moderate/High/Very
     High breakpoints and colors -- a road's closure urgency is the same
     kind of severity axis as a zone's flood-vulnerability score.
  2. The simpler by-incident view (route_engine.road_closure_
     recommendations()) in the expander at the bottom, for anyone who
     wants "what roads does THIS incident touch" instead of "what's this
     road's overall score."

Advisory only, in both views: an officer decides whether to actually
close a segment to traffic.
"""

from __future__ import annotations

import os
from pathlib import Path

import folium
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from data_loader import LEVEL_COLOR
import map_tiles

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")


def _get(path: str, officer_key: str, **params):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, headers={"X-Officer-Key": officer_key}, timeout=30)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _signal_detail_lines(row: dict) -> list[str]:
    sig = row["signals"]
    lines = [
        f"Water depth: {row['max_depth_hi_m']:.1f}m reported (signal {sig['water_depth']})"
        if row["max_depth_hi_m"] is not None else f"Water depth: not estimated (signal {sig['water_depth']})",
        f"Verified reports here: {row['n_verified_reports']} (signal {sig['report_count']})",
        f"Road classification: {row['highway'] or 'unknown'} (signal {sig['road_classification']})",
        f"Documented flood history nearby: {row['n_nearby_historical_events']} event(s) (signal {sig['historical_frequency']})",
    ]
    if row["near_term_rainfall_mm"] is not None:
        lines.append(f"Near-term (6h) rainfall forecast: {row['near_term_rainfall_mm']:.1f}mm (signal {sig['rainfall_forecast']})")
    else:
        lines.append("Near-term rainfall forecast: unavailable (signal 0.00)")
    if row["action_basis"] == "depth":
        lines.append(f"Action decided by: the {row['max_depth_hi_m']:.1f}m depth reading above, not the closure score.")
    else:
        lines.append("Action decided by: the closure score (no depth estimate was available from any report here).")
    return lines


def render():
    st.subheader("Road Closure Recommendations")
    st.caption(
        "Weighted closure score per real road segment (0.35 water depth + 0.25 verified reports + "
        "0.15 road classification + 0.15 historical flood frequency + 0.10 rainfall forecast), paired "
        "with an action recommendation decided primarily by reported water depth: Full closure / "
        "Emergency vehicles only / Pedestrians only / Monitor / No action. (\"One lane restricted\" "
        "was considered and dropped -- it would need real lane-count data this road network mostly "
        "doesn't have, see road_closure_score.py's docstring.) Advisory only -- an officer decides "
        "whether to actually close anything."
    )

    officer_key = os.environ.get("OFFICER_API_KEY")
    if not officer_key:
        st.error("OFFICER_API_KEY not found in backend/.env -- cannot reach officer-gated endpoints.")
        return

    scored, err = _get("/routing/road-closure-scores", officer_key)
    if err:
        st.error(f"Could not load road closure scores: {err}")
        return

    k1, k2, k3 = st.columns(3)
    k1.metric("Road segments flagged", len(scored))
    k2.metric("Full closure recommended", sum(1 for r in scored if r["action"] == "Full closure"))
    k3.metric("No action needed", sum(1 for r in scored if r["action"] == "No action"))

    if not scored:
        st.info("No active incidents right now -- nothing to flag for closure.")
        return

    st.divider()
    st.markdown("**Recommendation**")
    st.dataframe(
        [{
            "Road": r["name"],
            "Recommendation": f"{r['emoji']} {r['action']}",
            "Score": r["closure_score"],
            "Depth": f"{r['max_depth_hi_m']:.1f}m" if r["max_depth_hi_m"] is not None else "not estimated",
            "Reports": r["n_verified_reports"],
            "Road type": r["highway"] or "unknown",
        } for r in scored],
        width="stretch", hide_index=True,
    )

    for r in scored:
        with st.expander(f"{r['emoji']} {r['name']} -- why this score?", expanded=False):
            for line in _signal_detail_lines(r):
                st.caption(f"• {line}")

    st.divider()
    st.markdown("**Map**")
    all_points = [pt for r in scored for pt in r["coords"][0]]
    center = [sum(p[0] for p in all_points) / len(all_points), sum(p[1] for p in all_points) / len(all_points)]
    m = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")
    for r in scored:
        color = LEVEL_COLOR.get(r["level"], "#6B7280")
        for coords in r["coords"]:
            folium.PolyLine(
                coords, color=color, weight=6, opacity=0.85,
                tooltip=f"{r['emoji']} {r['name']} ({r['highway'] or 'unknown road type'}) -- {r['action']}",
            ).add_to(m)
    map_tiles.add_style_layers(m)
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, height=460, use_container_width=True, returned_objects=[])
    legend_html = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:0.82rem;'>"
        f"<span style='width:12px;height:4px;background:{c};display:inline-block;'></span>{lv}</span>"
        for lv, c in LEVEL_COLOR.items()
    )
    st.markdown(legend_html, unsafe_allow_html=True)

    st.divider()
    with st.expander("Detail: by incident instead of by road", expanded=False):
        by_incident, err2 = _get("/routing/road-closures", officer_key)
        if err2:
            st.error(f"Could not load by-incident view: {err2}")
        else:
            for d in by_incident:
                badge = " \U0001F9EA SYNTHETIC" if d.get("synthetic") else ""
                st.markdown(
                    f"`{d['id']}`{badge} — **{d['hazard_type'].replace('_', ' ').title()}** — "
                    f"{d['district'] or 'outside pilot district'}"
                )
                st.caption(d.get("location_label") or f"{d['lat']:.4f}, {d['lon']:.4f}")
                if not d["affected_segments"]:
                    st.caption("No mapped road segment found within the avoidance radius of this point.")
                    continue
                for seg in d["affected_segments"]:
                    st.markdown(f"- **{seg['name']}** ({seg['highway'] or 'unknown road type'}) — {seg['n_edges']} edge(s)")
                st.markdown("---")
