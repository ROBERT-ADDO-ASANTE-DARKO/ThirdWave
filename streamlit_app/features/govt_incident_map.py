"""
Feature 1 — Live Incident Map (Government).

Pulls pending report clusters (backend/clustering.py, via GET /reports/clusters)
and active verified incidents (GET /incidents/active) straight from the
FastAPI backend over HTTP -- same integration pattern govt_briefing_review.py
established (this page talks to live backend/DB state, not
incident_store.py's session-state copy, because an officer needs to see
what citizens are actually reporting right now, not a demo replay). Both
endpoints are officer-gated (auth.py's require_officer), so this needs
OFFICER_API_KEY -- loaded from backend/.env, same secret the backend itself
uses, not a separate one.

Severity coloring reuses the same score/level convention used everywhere
else in the app (data_loader.LEVEL_COLOR / citizen_app/lib/risk_colors.dart's
palette) rather than inventing a second "severity" scale: a cluster is
colored by the worst vulnerability-zone level among its member reports'
locations, not by self-reported flood depth, which is a much noisier
signal (unverified citizen estimates -- see clustering.py's docstring).
Read-only: verify/assign/resolve stays in Incident Verification.
"""

from __future__ import annotations

import os
from pathlib import Path

import folium
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from data_loader import LEVEL_COLOR, INK_NAVY

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")
ACCRA_FALLBACK_CENTER = [5.6037, -0.1870]

_LEVEL_RANK = {"Very High": 3, "High": 2, "Moderate": 1, "Low": 0}


def _backend_get(path: str, officer_key: str | None, **params):
    try:
        resp = requests.get(
            f"{BACKEND_URL}{path}", params=params, timeout=10,
            headers={"X-Officer-Key": officer_key} if officer_key else {},
        )
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _worst_level(reports: list[dict]) -> str | None:
    levels = [r["zone"]["level"] for r in reports if r.get("zone")]
    if not levels:
        return None
    return max(levels, key=lambda lv: _LEVEL_RANK.get(lv, -1))


def _cluster_popup(cluster: dict) -> str:
    badge = " \U0001F9EA" if cluster["any_synthetic"] else ""
    lines = [f"<b>{cluster['n_reports']} report(s){badge} &mdash; {cluster['district'] or 'outside pilot district'}</b>"]
    lines.append(f"Hazards: {', '.join(h.replace('_', ' ') for h in cluster['hazard_types'])}")
    if cluster.get("corroborating_news"):
        lines.append(f"\U0001F4F0 {len(cluster['corroborating_news'])} corroborating news hit(s)")
    for r in cluster["reports"][:5]:
        depth = f" ({r['depth_lo_m']}-{r['depth_hi_m']}m)" if r.get("depth_hi_m") else ""
        lines.append(f"&bull; {r['hazard_type'].replace('_', ' ')}{depth} &mdash; {r['submitted_at'][:16].replace('T', ' ')}")
    if cluster["n_reports"] > 5:
        lines.append(f"&bull; +{cluster['n_reports'] - 5} more")
    return "<br>".join(lines)


def _incident_popup(inc: dict) -> str:
    badge = " \U0001F9EA" if inc.get("synthetic") else ""
    lines = [f"<b>{inc['id']}{badge} &mdash; {inc['hazard_type'].replace('_', ' ').title()}</b>"]
    lines.append(inc["district"] or "outside pilot district")
    lines.append(f"Status: {(inc['response_status'] or 'reported').title()}")
    if inc.get("assigned_responder"):
        eta = f", ETA {inc['eta_minutes']} min" if inc.get("eta_minutes") is not None else ""
        lines.append(f"Responder: {inc['assigned_responder']}{eta}")
    return "<br>".join(lines)


def render():
    st.subheader("Live Incident Map")
    st.caption(
        "Pending report clusters (backend/clustering.py, 300m complete-linkage) and active "
        "verified incidents, pulled live from the backend -- not a replay of demo data. "
        "Read-only: verify/assign/resolve actions stay in Incident Verification."
    )

    officer_key = os.environ.get("OFFICER_API_KEY")
    if not officer_key:
        st.error("OFFICER_API_KEY not found in backend/.env -- cannot reach officer-gated endpoints.")
        return

    clusters, c_err = _backend_get("/reports/clusters", officer_key)
    incidents, i_err = _backend_get("/incidents/active", officer_key)

    if c_err:
        st.error(f"Could not load pending reports: {c_err}")
        clusters = []
    if i_err:
        st.error(f"Could not load active incidents: {i_err}")
        incidents = []

    n_pending = sum(c["n_reports"] for c in clusters)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pending clusters", len(clusters))
    col2.metric("Pending reports", n_pending)
    col3.metric("Active incidents", len(incidents))
    n_responding = sum(1 for i in incidents if i.get("response_status") == "responding")
    col4.metric("Responder assigned", n_responding)

    st.divider()

    all_points = [(c["centroid"]["lat"], c["centroid"]["lon"]) for c in clusters] + \
                 [(i["lat"], i["lon"]) for i in incidents]
    if all_points:
        center = [sum(p[0] for p in all_points) / len(all_points), sum(p[1] for p in all_points) / len(all_points)]
    else:
        center = ACCRA_FALLBACK_CENTER  # no live data yet -- just center on Accra

    m = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap")

    for c in clusters:
        level = _worst_level(c["reports"])
        color = LEVEL_COLOR.get(level, "#6B7280")
        radius = 8 + 3 * min(c["n_reports"], 8)
        folium.CircleMarker(
            [c["centroid"]["lat"], c["centroid"]["lon"]], radius=radius,
            color=INK_NAVY, weight=1.5, fill=True, fill_color=color, fill_opacity=0.75,
            popup=folium.Popup(_cluster_popup(c), max_width=280),
            tooltip=f"{c['n_reports']} pending report(s)",
        ).add_to(m)

    for i in incidents:
        responding = i.get("response_status") == "responding"
        folium.Marker(
            [i["lat"], i["lon"]],
            icon=folium.Icon(color="blue" if responding else "orange", icon="exclamation-triangle", prefix="fa"),
            popup=folium.Popup(_incident_popup(i), max_width=280),
            tooltip=f"Active: {i['hazard_type'].replace('_', ' ')}",
        ).add_to(m)

    st_folium(m, height=480, use_container_width=True, returned_objects=[])

    st.markdown("**Map legend**")
    zone_html = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:5px;margin-right:14px;font-size:0.82rem;'>"
        f"<span style='width:12px;height:12px;border-radius:50%;background:{c};border:1px solid rgba(0,0,0,.25);"
        f"display:inline-block;'></span>{lv}</span>"
        for lv, c in LEVEL_COLOR.items()
    )
    st.markdown(
        f"Pending cluster (circle size = report count, color = worst vulnerability-zone level there): {zone_html}",
        unsafe_allow_html=True,
    )
    st.markdown(
        "Active incident (pin): <span style='color:#d4820a;'>&#9888;</span> awaiting responder &nbsp;&nbsp; "
        "<span style='color:#1e5fa8;'>&#9888;</span> responder assigned",
        unsafe_allow_html=True,
    )

    if clusters:
        st.divider()
        st.markdown("**Pending clusters, worst first**")
        rows = [{
            "Reports": c["n_reports"], "District": c["district"] or "outside pilot district",
            "Hazards": ", ".join(h.replace("_", " ") for h in c["hazard_types"]),
            "Zone level": _worst_level(c["reports"]) or "Unknown",
            "News corroboration": len(c.get("corroborating_news", [])),
            "Synthetic": "\U0001F9EA" if c["any_synthetic"] else "",
        } for c in clusters]
        st.dataframe(rows, width="stretch", hide_index=True)
