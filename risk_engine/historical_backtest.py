"""
historical_backtest.py — Replay documented historical Accra flood events
against ThirdWave's geospatial vulnerability outputs, at both granularities:
  - assembly-level (data/pilot_zone_vulnerability.json, 6 zones)
  - grid-level     (data/pilot_risk_grid.geojson, 319 cells)

This is a backtest/demo tool, not a statistical validation: n=2 geocoded
events (both at the same recurring site) is a sanity check and a
storytelling aid ("if ThirdWave had existed then, here's what it would
have shown"), not proof of model skill. Treat it that way.

Usage
─────
    python3 historical_backtest.py
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape, Point

HERE = Path(__file__).parent
EVENTS_PATH = HERE / "data" / "historical_flood_events.json"
ASSEMBLY_SCORES_PATH = HERE / "data" / "pilot_zone_vulnerability.json"
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
OUTPUT_PATH = HERE / "data" / "historical_backtest_results.json"


def main() -> None:
    events = json.loads(EVENTS_PATH.read_text())["events"]
    assembly_scores = json.loads(ASSEMBLY_SCORES_PATH.read_text())
    grid = json.loads(GRID_PATH.read_text())

    assembly_ranked = sorted(assembly_scores.items(), key=lambda x: -x[1]["score"])
    assembly_rank = {name: i + 1 for i, (name, _) in enumerate(assembly_ranked)}
    n_assemblies = len(assembly_ranked)

    grid_scores_sorted = sorted(grid["features"], key=lambda f: -f["properties"]["score"])
    n_cells = len(grid_scores_sorted)

    results = []
    print(f"{'Event':<45} {'Assembly (rank/total)':<28} {'Grid cell (percentile)':<28}")
    print("-" * 101)

    for ev in events:
        row = {"event_id": ev["event_id"], "date": ev["date"], "name": ev["name"]}

        if ev.get("lon") is None:
            row["backtest"] = "skipped - no specific geocoded location in source"
            results.append(row)
            print(f"{ev['name']:<45} {'(no location)':<28} {'(no location)':<28}")
            continue

        pt = Point(ev["lon"], ev["lat"])

        # Assembly-level match
        assembly_name = None
        assembly_gdf_path = HERE / "data" / "pilot_district_assemblies.geojson"
        assemblies = json.loads(assembly_gdf_path.read_text())
        best_dist = float("inf")
        for f in assemblies["features"]:
            poly = shape(f["geometry"])
            if poly.contains(pt):
                assembly_name = f["properties"]["name"]
                break
            d = poly.distance(pt)
            if d < best_dist:
                best_dist = d
                nearest_name = f["properties"]["name"]
        if assembly_name is None:
            assembly_name = nearest_name  # fell on a boundary seam, use nearest

        a_score = assembly_scores.get(assembly_name, {})
        a_rank = assembly_rank.get(assembly_name)

        # Grid-level match
        cell_props = None
        for f in grid["features"]:
            poly = shape(f["geometry"])
            if poly.contains(pt):
                cell_props = f["properties"]
                break
        cell_rank = None
        if cell_props is not None:
            for i, f in enumerate(grid_scores_sorted):
                if f["properties"]["zone_id"] == cell_props["zone_id"]:
                    cell_rank = i + 1
                    break

        row.update({
            "assembly": assembly_name,
            "assembly_score": a_score.get("score"),
            "assembly_level": a_score.get("level"),
            "assembly_rank": f"{a_rank} of {n_assemblies}" if a_rank else None,
            "grid_zone_id": cell_props["zone_id"] if cell_props else None,
            "grid_score": cell_props["score"] if cell_props else None,
            "grid_level": cell_props["level"] if cell_props else None,
            "grid_rank": f"{cell_rank} of {n_cells}" if cell_rank else None,
            "grid_percentile": round((1 - (cell_rank - 1) / n_cells) * 100, 1) if cell_rank else None,
        })
        results.append(row)

        a_str = f"{row['assembly_score']} ({row['assembly_rank']})"
        g_str = f"{row['grid_score']} (top {100 - row['grid_percentile']:.0f}%)" if row["grid_percentile"] else "n/a"
        print(f"{ev['name']:<45} {a_str:<28} {g_str:<28}")

    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUTPUT_PATH}")
    print("\nNote: n=2 geocoded events, both at the same recurring Circle/Odaw site "
          "(2015 and 2023). This is a sanity check and demo aid, not a statistically "
          "powered validation -- real validation comes from the live pilot's "
          "incident_outcome_link data (thresholds.py / prediction_log_schema.sql).")


if __name__ == "__main__":
    main()
