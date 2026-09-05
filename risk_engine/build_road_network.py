"""
build_road_network.py — Precompute a routable road graph for the pilot
district, with risk-weighted edge costs, for the Streamlit "Safer Routing"
feature.

Building an OSMnx graph live per Streamlit session would be slow and hit
Overpass repeatedly for the same data -- same reasoning as every other
heavy geospatial step in this project: compute once here, ship a small
serialized result to the app.

Risk weighting: each edge's midpoint is looked up against the 319-cell risk
grid (pilot_risk_grid.geojson); its vulnerability score scales a penalty
multiplier on top of physical distance. Edges outside the grid (or where
the grid has no data) get no penalty -- absence of data must not look like
absence of risk, so the safer path shouldn't be biased to avoid areas we
simply didn't score.

Usage
─────
    python3 build_road_network.py
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import shape, LineString
from shapely.strtree import STRtree

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
BOUNDARY_PATH = HERE / "data" / "pilot_district_boundary.geojson"
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
OUTPUT_GRAPH = HERE / "data" / "pilot_road_network.gpickle"

# How strongly vulnerability score penalizes an edge's effective length.
# score=0 -> no penalty (weight = length); score=100 -> length x (1+MAX_PENALTY).
MAX_PENALTY = 3.0


def run():
    boundary_gdf = gpd.read_file(BOUNDARY_PATH)
    boundary_geom = boundary_gdf.union_all()
    # Small buffer so routes near the edge aren't artificially cut off
    buffered = boundary_geom.buffer(0.01)

    log.info("Downloading OSM road network for the pilot district (this hits Overpass -- one call)...")
    G = ox.graph_from_polygon(buffered, network_type="drive", simplify=True)
    log.info("Graph: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())

    grid = json.loads(GRID_PATH.read_text())
    zone_polys = [shape(f["geometry"]) for f in grid["features"]]
    zone_scores = [f["properties"]["score"] for f in grid["features"]]
    zone_tree = STRtree(zone_polys)

    log.info("Assigning risk-weighted costs to edges (spatial-indexed lookup)...")
    n_scored = 0
    for u, v, k, data in G.edges(keys=True, data=True):
        length_m = data.get("length", 1.0)
        # Edge midpoint in lon/lat
        x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
        x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
        mid = LineString([(x1, y1), (x2, y2)]).interpolate(0.5, normalized=True)

        score = None
        for idx in zone_tree.query(mid):
            if zone_polys[idx].contains(mid):
                score = zone_scores[idx]
                break

        if score is not None:
            penalty = 1 + (score / 100) * MAX_PENALTY
            n_scored += 1
        else:
            penalty = 1.0  # no data -- no penalty, not treated as safe or risky

        data["risk_weight"] = length_m * penalty
        data["zone_score"] = score

    log.info("Scored %d of %d edges against the risk grid (%.1f%%)",
              n_scored, G.number_of_edges(), 100 * n_scored / G.number_of_edges())

    OUTPUT_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_GRAPH, "wb") as f:
        pickle.dump(G, f)
    log.info("Saved -> %s", OUTPUT_GRAPH)


if __name__ == "__main__":
    run()
