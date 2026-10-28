"""
route_engine.py — Phase 4 feature #5, Safer Routing During Heavy Rainfall.

Ported from streamlit_app/features/citizen_routing.py, same precomputed
graph (risk_engine/build_road_network.py: OSMnx road network + risk-weighted
edge costs from the 1013-cell grid) and same two-shortest-paths logic
(networkx Dijkstra: fastest-by-distance vs. risk-weighted-by-vulnerability).

Named route_engine.py rather than routing.py on purpose -- routers/routing.py
(this feature's router) needs a plain `import route_engine` for its core
logic, and reusing the "routing" name for both the router and its logic
module caused real confusion last time this came up for forecast.py/
routers/forecast.py (see project history); renamed before that happened here.

Dropped from the port: OSMnx's ox.distance.nearest_nodes(), which would
pull OSMnx (and its native-dependency chain) into the backend's runtime
requirements just to snap one lat/lon to the nearest graph node. 22,552
nodes is small enough that a vectorized numpy haversine over every node,
done fresh per request, is both simpler and fast enough -- no spatial index
needed.

Active-incident avoidance (same reasoning as the Streamlit version): a
verified incident adds a heavy penalty to nearby edges AT QUERY TIME via a
weight callable, never by mutating the cached graph in place (that would
corrupt it for every other concurrent request).
"""

from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

import networkx as nx
import numpy as np
from sqlmodel import Session, select

from models import Report

GRAPH_PATH = Path(__file__).parent.parent / "risk_engine" / "data" / "pilot_road_network.gpickle"
INCIDENT_AVOID_RADIUS_DEG = 0.0018  # ~200m at this latitude
INCIDENT_PENALTY_FACTOR = 30.0
SNAP_WARNING_KM = 0.3


@lru_cache(maxsize=1)
def load_graph() -> nx.MultiDiGraph:
    with open(GRAPH_PATH, "rb") as f:
        return pickle.load(f)


@lru_cache(maxsize=1)
def _node_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parallel numpy arrays (ids, lons, lats) over every graph node, built
    once -- nearest_node() below vectorizes the haversine search over these
    instead of looping in Python per request."""
    G = load_graph()
    ids, lons, lats = zip(*((n, d["x"], d["y"]) for n, d in G.nodes(data=True)))
    return np.array(ids), np.array(lons), np.array(lats)


def _haversine_km_vec(lon1: float, lat1: float, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    lon1r, lat1r = np.radians(lon1), np.radians(lat1)
    lon2r, lat2r = np.radians(lon2), np.radians(lat2)
    dlon, dlat = lon2r - lon1r, lat2r - lat1r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


def nearest_node(lon: float, lat: float) -> tuple[int, float]:
    """-> (node_id, snap_distance_km). Same "nearest_nodes always returns
    SOMETHING, however far" caveat as the Streamlit version: a point well
    outside the pilot district's mapped roads still snaps to whatever's
    closest, so the caller must surface snap distance, not hide it."""
    ids, lons, lats = _node_arrays()
    d_km = _haversine_km_vec(lon, lat, lons, lats)
    i = int(np.argmin(d_km))
    return int(ids[i]), float(d_km[i])


def _min_weight_edge_data(G, u, v, weight_key):
    """G is a MultiDiGraph -- there can be several parallel edges between u
    and v under different keys. nx.shortest_path(weight=...) picks whichever
    parallel edge is cheapest at each hop, not necessarily key 0, so stats
    must do the same lookup or they'll silently read the wrong edge."""
    edge_dict = G.get_edge_data(u, v)
    if not edge_dict:
        return {}
    return min(edge_dict.values(), key=lambda d: d.get(weight_key, float("inf")))


def route_stats(G, path, weight_key) -> tuple[float, float | None]:
    total_len = 0.0
    scores = []
    for i in range(len(path) - 1):
        data = _min_weight_edge_data(G, path[i], path[i + 1], weight_key)
        total_len += data.get("length", 0)
        if data.get("zone_score") is not None:
            scores.append(data["zone_score"])
    avg_score = sum(scores) / len(scores) if scores else None
    return total_len, avg_score


def _edge_midpoint(G, u, v) -> tuple[float, float]:
    x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
    x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
    return (x1 + x2) / 2, (y1 + y2) / 2


def build_incident_aware_weight(G, incidents: list[dict]):
    """A weight function for nx.shortest_path -- computed fresh per query,
    never mutates G (see module docstring)."""
    incident_xy = [(inc["lon"], inc["lat"]) for inc in incidents]

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


def incidents_near_path(G, path, incidents: list[dict]) -> list[dict]:
    near = []
    for inc in incidents:
        ix, iy = inc["lon"], inc["lat"]
        min_d = min(
            ((_edge_midpoint(G, u, v)[0] - ix) ** 2 + (_edge_midpoint(G, u, v)[1] - iy) ** 2) ** 0.5
            for u, v in zip(path[:-1], path[1:])
        )
        if min_d <= INCIDENT_AVOID_RADIUS_DEG:
            near.append(inc)
    return near


def _path_latlon(G, path) -> list[list[float]]:
    return [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in path]


def _active_incidents(session: Session) -> list[dict]:
    reports = session.exec(select(Report).where(Report.status == "verified")).all()
    return [
        {
            "id": r.id, "lon": r.lon, "lat": r.lat, "hazard_type": r.hazard_type,
            "location_label": r.location_label, "synthetic": r.synthetic,
        }
        for r in reports
    ]


def compute_routes(session: Session, olat: float, olon: float, dlat: float, dlon: float) -> dict:
    G = load_graph()
    orig_node, origin_snap_km = nearest_node(olon, olat)
    dest_node, dest_snap_km = nearest_node(dlon, dlat)
    active_incidents = _active_incidents(session)

    try:
        fast_path = nx.shortest_path(G, orig_node, dest_node, weight="length")
        safe_weight = build_incident_aware_weight(G, active_incidents) if active_incidents else "risk_weight"
        safe_path = nx.shortest_path(G, orig_node, dest_node, weight=safe_weight)
    except nx.NetworkXNoPath:
        return {"error": "No route found between these two points on the pilot district's road network."}

    fast_len, fast_avg_score = route_stats(G, fast_path, "length")
    safe_len, safe_avg_score = route_stats(G, safe_path, "risk_weight")

    return {
        "fast_route": {
            "distance_km": round(fast_len / 1000, 3),
            "avg_zone_score": round(fast_avg_score, 1) if fast_avg_score is not None else None,
            "path": _path_latlon(G, fast_path),
            "incidents_near": incidents_near_path(G, fast_path, active_incidents),
        },
        "safe_route": {
            "distance_km": round(safe_len / 1000, 3),
            "avg_zone_score": round(safe_avg_score, 1) if safe_avg_score is not None else None,
            "path": _path_latlon(G, safe_path),
            "incidents_near": incidents_near_path(G, safe_path, active_incidents),
        },
        "extra_km": round((safe_len - fast_len) / 1000, 3),
        "same_route": fast_path == safe_path,
        "origin_snap_km": round(origin_snap_km, 3),
        "dest_snap_km": round(dest_snap_km, 3),
        "snap_warning": origin_snap_km > SNAP_WARNING_KM or dest_snap_km > SNAP_WARNING_KM,
        "active_incidents": active_incidents,
    }
