"""
Feature 10 — Citizen: Safer Routing During Heavy Rainfall.

The heaviest-lift feature on the original checklist, flagged as such from
the start. Precomputed in build_road_network.py (OSMnx road graph +
risk-weighted edge costs from the 319-cell grid) -- this page only loads
the ~5.5MB result and runs two shortest-path searches (networkx Dijkstra),
not a live OSMnx build, which would be slow per session.

Two routes are always shown side by side: fastest (by distance) and safer
(by risk-weighted cost) -- never just the "safer" one alone, so a citizen
can see what they're trading off, matching the same "disclose, don't just
decide for the user" principle used throughout this project's provenance
work.

Active-incident avoidance (see project chat history "connecting the dots" /
sandbox discussion): this is the piece that makes the citizen-reporting ->
district-verification loop actually change routing outcomes, not just the
static composite score. Verified active incidents (incident_store.py) add a
heavy penalty to nearby edges AT QUERY TIME via a weight callable -- the
cached graph (st.cache_resource, shared across reruns/sessions) is never
mutated in place, since doing that would corrupt it for every other query.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import folium
import networkx as nx
import osmnx as ox
import requests
import streamlit as st
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation

from data_loader import DATA_DIR, LEVEL_COLOR
import incident_store as store

GRAPH_PATH = Path(DATA_DIR) / "pilot_road_network.gpickle"
INCIDENT_AVOID_RADIUS_DEG = 0.0018  # ~200m at this latitude
INCIDENT_PENALTY_FACTOR = 30.0


@st.cache_resource
def load_graph():
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


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


def _min_weight_edge_data(G, u, v, weight_key):
    """G is a MultiDiGraph -- there can be several parallel edges between u
    and v under different keys. nx.shortest_path(weight=...) picks whichever
    parallel edge is cheapest at each hop, not necessarily key 0, so stats
    must do the same lookup or they'll silently read the wrong edge."""
    edge_dict = G.get_edge_data(u, v)
    if not edge_dict:
        return {}
    return min(edge_dict.values(), key=lambda d: d.get(weight_key, float("inf")))


def route_stats(G, path, weight_key):
    total_len = 0.0
    scores = []
    for i in range(len(path) - 1):
        data = _min_weight_edge_data(G, path[i], path[i + 1], weight_key)
        total_len += data.get("length", 0)
        if data.get("zone_score") is not None:
            scores.append(data["zone_score"])
    avg_score = sum(scores) / len(scores) if scores else None
    return total_len, avg_score


def _haversine_km(lon1, lat1, lon2, lat2) -> float:
    from math import radians, sin, cos, asin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def _edge_midpoint(G, u, v):
    x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
    x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
    return (x1 + x2) / 2, (y1 + y2) / 2


def build_incident_aware_weight(G, incidents):
    """A weight function for nx.shortest_path -- computed fresh per query,
    never mutates G. For a MultiDiGraph, networkx passes a callable weight
    fn the full keydict of parallel edges and expects IT to reduce them to
    one number (same reason _min_weight_edge_data exists above), so this
    does the same min-over-parallel-edges as the static case, then adds a
    heavy multiplier if the edge sits within INCIDENT_AVOID_RADIUS_DEG of
    any currently active, verified incident."""
    incident_xy = [(inc["gps_point"]["lon"], inc["gps_point"]["lat"]) for inc in incidents]

    def weight(u, v, keydict):
        if not keydict:
            return None
        base = min(d.get("risk_weight", d.get("length", 1.0)) for d in keydict.values())
        if incident_xy:
            mx, my = _edge_midpoint(G, u, v)
            near = any((mx - ix) ** 2 + (my - iy) ** 2 <= INCIDENT_AVOID_RADIUS_DEG ** 2
                       for ix, iy in incident_xy)
            if near:
                base *= INCIDENT_PENALTY_FACTOR
        return base

    return weight


def incidents_near_path(G, path, incidents):
    near = []
    for inc in incidents:
        ix, iy = inc["gps_point"]["lon"], inc["gps_point"]["lat"]
        min_d = min(
            ((_edge_midpoint(G, u, v)[0] - ix) ** 2 + (_edge_midpoint(G, u, v)[1] - iy) ** 2) ** 0.5
            for u, v in zip(path[:-1], path[1:])
        )
        if min_d <= INCIDENT_AVOID_RADIUS_DEG:
            near.append(inc)
    return near


def render():
    st.subheader("Safer Routing")
    st.caption(
        "Compares the fastest route against a risk-weighted route that prefers lower-vulnerability zones "
        "(precomputed in build_road_network.py -- OSMnx road graph, edges weighted by the same 319-cell "
        "vulnerability score used throughout this project). Always shown side by side, not just the 'safer' "
        "route alone, so you can see the tradeoff yourself."
    )

    if "route_origin" not in st.session_state:
        st.session_state.route_origin = None
    if "route_dest" not in st.session_state:
        st.session_state.route_dest = None

    col1, col2 = st.columns(2)
    with col1:
        origin_mode = st.radio(
            "From", ["Type an address", "Use my current location"], horizontal=True,
            label_visibility="visible", key="route_origin_mode",
        )
        if origin_mode == "Type an address":
            origin_addr = st.text_input("From address", placeholder="e.g. Kwame Nkrumah Circle",
                                         key="route_origin_addr", label_visibility="collapsed")
            live_loc = None
        else:
            origin_addr = None
            live_loc = streamlit_geolocation()
            if live_loc and live_loc.get("latitude") is not None:
                st.caption(f"📍 Using detected location ({live_loc['latitude']:.4f}, {live_loc['longitude']:.4f})")
            else:
                st.caption("Click the location button above to detect where you are.")
    with col2:
        dest_addr = st.text_input("To", placeholder="e.g. Kaneshie Market", key="route_dest_addr")

    if st.button("Find routes", type="primary"):
        if origin_mode == "Use my current location":
            o = (live_loc["latitude"], live_loc["longitude"], "My current location") if live_loc and live_loc.get("latitude") is not None else None
        else:
            o = geocode(origin_addr) if origin_addr else None
        d = geocode(dest_addr) if dest_addr else None
        if not o:
            st.error("Couldn't get the 'From' location -- detect your location or type an address.")
        elif not d:
            st.error("Couldn't find the 'To' address.")
        else:
            st.session_state.route_origin = o
            st.session_state.route_dest = d

    if not st.session_state.route_origin or not st.session_state.route_dest:
        st.info("Enter both a starting point and destination to compare routes.")
        return

    store.init_store()
    active_incidents = [
        inc for inc in store.list_active_incidents() if inc["gps_point"]["lon"] is not None
    ]

    with st.spinner("Loading road network and computing routes..."):
        G = load_graph()
        olat, olon, olabel = st.session_state.route_origin
        dlat, dlon, dlabel = st.session_state.route_dest

        try:
            orig_node = ox.distance.nearest_nodes(G, olon, olat)
            dest_node = ox.distance.nearest_nodes(G, dlon, dlat)
        except Exception as exc:
            st.error(f"Couldn't snap to the road network: {exc}")
            return

        # nearest_nodes always returns SOMETHING, however far -- if the
        # input point isn't actually near the pilot district's mapped
        # roads (e.g. a live GPS reading from outside the district, or
        # just off-road), the route silently starts from wherever the
        # closest node happens to be, which can look like "the route
        # doesn't start from my location." Surface that instead of hiding it.
        onode_lat, onode_lon = G.nodes[orig_node]["y"], G.nodes[orig_node]["x"]
        origin_snap_km = _haversine_km(olon, olat, onode_lon, onode_lat)

        try:
            fast_path = nx.shortest_path(G, orig_node, dest_node, weight="length")
            safe_weight = build_incident_aware_weight(G, active_incidents) if active_incidents else "risk_weight"
            safe_path = nx.shortest_path(G, orig_node, dest_node, weight=safe_weight)
        except nx.NetworkXNoPath:
            st.error("No route found between these two points on the pilot district's road network.")
            return

    fast_len, fast_avg_score = route_stats(G, fast_path, "length")
    safe_len, safe_avg_score = route_stats(G, safe_path, "risk_weight")

    col1, col2, col3 = st.columns(3)
    col1.metric("Fastest route", f"{fast_len/1000:.2f} km",
                f"avg zone score {fast_avg_score:.1f}" if fast_avg_score is not None else "no zone data")
    col2.metric("Safer route", f"{safe_len/1000:.2f} km",
                f"avg zone score {safe_avg_score:.1f}" if safe_avg_score is not None else "no zone data")
    extra_km = (safe_len - fast_len) / 1000
    col3.metric("Extra distance for the safer route", f"{extra_km:+.2f} km")

    if fast_path == safe_path:
        st.success("The fastest route and the safer route are the same road here -- no lower-risk alternative exists.")

    if origin_snap_km > 0.3:
        st.warning(
            f"⚠️ Your 'From' point is ~{origin_snap_km:.1f}km from the nearest road in the pilot district's "
            "mapped network -- both routes below actually start from that nearest road (dashed line on the "
            "map), not from the pin itself. This usually means the detected/typed location falls outside the "
            "pilot district's coverage area."
        )

    center_lat = (olat + dlat) / 2
    center_lon = (olon + dlon) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles="OpenStreetMap")

    def path_coords(path):
        return [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path]

    folium.PolyLine(path_coords(fast_path), color="#C1621B", weight=5, opacity=0.85, tooltip="Fastest route").add_to(m)
    folium.PolyLine(path_coords(safe_path), color="#1B7A9E", weight=5, opacity=0.85, tooltip="Safer route").add_to(m)
    folium.Marker([olat, olon], tooltip=f"From: {olabel}", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker([dlat, dlon], tooltip=f"To: {dlabel}", icon=folium.Icon(color="red")).add_to(m)
    if origin_snap_km > 0.05:
        folium.PolyLine(
            [(olat, olon), (onode_lat, onode_lon)], color="#555555", weight=2, opacity=0.7, dash_array="6,6",
            tooltip=f"{origin_snap_km*1000:.0f}m from pin to nearest mapped road",
        ).add_to(m)
    for inc in active_incidents:
        badge = " (demo)" if inc.get("synthetic") else ""
        folium.Marker(
            [inc["gps_point"]["lat"], inc["gps_point"]["lon"]],
            tooltip=f"Active incident{badge}: {inc['hazard_type'].replace('_', ' ').title()}",
            icon=folium.Icon(color="darkred", icon="exclamation-triangle", prefix="fa"),
        ).add_to(m)

    st_folium(m, height=460, use_container_width=True, returned_objects=[])
    st.caption("🟠 Fastest route (by distance) · 🔵 Safer route (by vulnerability-weighted cost) · 🚩 Active verified incident")

    if active_incidents:
        fast_hits = incidents_near_path(G, fast_path, active_incidents)
        safe_hits = incidents_near_path(G, safe_path, active_incidents)
        st.divider()
        st.markdown("**Active incidents along these routes**")
        st.caption(
            f"{len(active_incidents)} currently verified active incident(s) in the pilot district. "
            "The safer route's cost includes a heavy penalty for road segments within ~200m of any of "
            "them -- this is what turns a verified citizen report into an actual detour, not just a marker "
            "on a map."
        )
        c1, c2 = st.columns(2)
        with c1:
            if fast_hits:
                st.warning(f"🟠 Fastest route passes within ~200m of **{len(fast_hits)}** active incident(s).")
            else:
                st.success("🟠 Fastest route doesn't pass near any active incident.")
        with c2:
            if safe_hits:
                st.warning(f"🔵 Safer route still passes within ~200m of **{len(safe_hits)}** active incident(s) -- no clear alternative avoids it.")
            else:
                st.success("🔵 Safer route avoids all currently active incidents.")
    else:
        st.caption(
            "No currently active, verified incidents -- the safer route above reflects only the static "
            "vulnerability grid. Verify a report in Incident Verification to see routing react to it live."
        )
