"""
airbus_coverage_cross_reference.py — what to actually DO with an Airbus
OneAtlas "coverage export" before any pixel is purchased.

That export (Ghana_GHA_Country_Coverage_2026.zip, from a free coverage-
availability inquiry, not a data order) is two shapefiles of ARCHIVE STRIP
FOOTPRINTS with acquisition metadata (date, cloud cover, incidence angle,
processing level) -- no pixels. It's a catalog index, but the index alone
is directly useful for three things done here:

1. Cross-reference every documented historical flood event (see
   historical_flood_events.json) against the strip catalog: is there an
   archive scene captured close to a real flood date? A hit turns "we'd
   like imagery of this event" into "this specific already-existing scene,
   ACQ_ID X, dated Y, Z% cloud" -- a concrete, cheap, orderable ask instead
   of a speculative one.

2. Coverage-count and freshness per pilot/extended-coverage grid cell: how
   much VHR archive already exists over the project's actual study area,
   and how recent/cloud-free is the best of it.

3. A small diagnostic figure illustrating the best real find.

Data handling: the two shapefiles are Airbus's proprietary catalog export
(cached locally at cache/airbus_coverage/, gitignored -- never committed,
same treatment as every other Airbus-branded asset in this project). Only
DERIVED facts (event name, matched date, cloud %, ACQ_ID, delta-days) are
written to data/ and committed -- not the underlying footprint geometries
or the full 901-strip table.

Usage
─────
    python3 airbus_coverage_cross_reference.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
COVERAGE_DIR = HERE / "cache" / "airbus_coverage"  # gitignored -- proprietary Airbus export
OUTPUT = HERE / "data" / "airbus_coverage_summary.json"
DIAGNOSTIC_PNG = HERE / "data" / "airbus_coverage_march2023_match.png"

EVENT_MATCH_WINDOW_DAYS = 90  # flag a strip as a usable "near-event" match within this window


def _load_strips() -> gpd.GeoDataFrame:
    frames = []
    for path, sensor in ((COVERAGE_DIR / "Ghana_PHR_Strips.shp", "Pleiades_50cm"),
                          (COVERAGE_DIR / "Ghana_PNeo_Strips.shp", "PleiadesNeo_30cm")):
        gdf = gpd.read_file(path)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        gdf["sensor"] = sensor
        gdf["acq_dt"] = pd.to_datetime(gdf["ACQ_DATE"]).dt.tz_localize(None)
        frames.append(gdf)
    strips = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(strips, geometry="geometry", crs=frames[0].crs)


def cross_reference_events(strips: gpd.GeoDataFrame) -> list[dict]:
    events = json.loads((HERE / "data" / "historical_flood_events.json").read_text())["events"]
    events = [e for e in events if e.get("lon") is not None]
    results = []
    for e in events:
        pt = Point(e["lon"], e["lat"])
        edate = pd.Timestamp(e["date"])
        hit = strips[strips.contains(pt)].copy()
        if hit.empty:
            results.append({"event": e["name"], "date": e["date"], "coverage": "none"})
            continue
        hit["delta_days"] = (hit["acq_dt"] - edate).dt.days
        best = hit.reindex(hit["delta_days"].abs().sort_values().index).iloc[0]
        results.append({
            "event": e["name"], "date": e["date"], "location": e.get("location_name"),
            "coverage": "match", "n_strips_covering_point": int(len(hit)),
            "nearest_strip": {
                "sensor": best["sensor"], "acq_date": str(best["acq_dt"].date()),
                "cloud_pct": round(float(best["CLOUDCOVER"]), 1), "incidence_angle_deg": round(float(best["INC_ANGLE"]), 1),
                "proc_level": best["PROC_LEVEL"], "objectid": int(best["OBJECTID"]),
                "acq_id": best.get("ACQ_ID"), "delta_days": int(best["delta_days"]),
                "near_event_match": bool(abs(best["delta_days"]) <= EVENT_MATCH_WINDOW_DAYS),
            },
        })
    return results


def coverage_over_grid(strips: gpd.GeoDataFrame, grid_path: Path) -> dict:
    grid = gpd.read_file(grid_path)
    if grid.crs and grid.crs.to_epsg() != 4326:
        grid = grid.to_crs(4326)
    minx, miny, maxx, maxy = grid.total_bounds
    sub = strips.cx[minx:maxx, miny:maxy]
    n_cells_covered = 0
    best_cloud = []
    grid_sindex = sub.sindex
    for geom in grid.geometry:
        cand = list(grid_sindex.query(geom, predicate="intersects"))
        if not cand:
            continue
        n_cells_covered += 1
        best_cloud.append(float(sub.iloc[cand]["CLOUDCOVER"].min()))
    return {
        "grid": grid_path.name, "n_cells_total": len(grid), "n_cells_with_any_coverage": n_cells_covered,
        "pct_cells_covered": round(100 * n_cells_covered / len(grid), 1) if len(grid) else 0,
        "median_best_cloud_pct": round(float(pd.Series(best_cloud).median()), 1) if best_cloud else None,
        "n_strips_in_bbox": int(len(sub)),
    }


def main():
    strips = _load_strips()
    log.info("Loaded %d archive strips (%d Pleiades, %d Pleiades Neo)", len(strips),
              (strips["sensor"] == "Pleiades_50cm").sum(), (strips["sensor"] == "PleiadesNeo_30cm").sum())

    event_matches = cross_reference_events(strips)
    near_matches = [r for r in event_matches if r.get("nearest_strip", {}).get("near_event_match")]
    log.info("%d/%d documented events have an archive strip within %d days:", len(near_matches), len(event_matches),
              EVENT_MATCH_WINDOW_DAYS)
    for r in near_matches:
        ns = r["nearest_strip"]
        log.info("  %s (%s): %s scene, %s, %.1f%% cloud, %+dd",
                  r["event"], r["date"], ns["sensor"], ns["acq_date"], ns["cloud_pct"], ns["delta_days"])

    grid_coverage = {}
    for name, path in (("pilot", HERE / "data" / "pilot_risk_grid.geojson"),
                        ("lower_volta", HERE / "data" / "lower_volta_risk_grid.geojson")):
        if path.exists():
            grid_coverage[name] = coverage_over_grid(strips, path)
            log.info("%s grid: %s", name, grid_coverage[name])

    OUTPUT.write_text(json.dumps({
        "source": "Airbus OneAtlas coverage-availability export (Ghana_GHA_Country_Coverage_2026.zip), "
                  "NOT a data order -- catalog index only, no pixels. Footprint geometries are proprietary "
                  "and not included here, only derived facts.",
        "total_strips": len(strips), "date_range": [str(strips["acq_dt"].min().date()), str(strips["acq_dt"].max().date())],
        "event_cross_reference": event_matches, "grid_coverage": grid_coverage,
    }, indent=2))
    log.info("Saved -> %s", OUTPUT)

    # diagnostic: the strongest find (March 2023 Accra flood, 1-day-after match)
    best = next((r for r in near_matches if r["event"] == "March 2023 Accra flood"), None)
    if best:
        _plot_match(strips, best)


def _plot_match(strips: gpd.GeoDataFrame, match: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    events = json.loads((HERE / "data" / "historical_flood_events.json").read_text())["events"]
    e = next(e for e in events if e["name"] == match["event"])
    row = strips[strips["OBJECTID"] == match["nearest_strip"]["objectid"]].iloc[0]

    fig, ax = plt.subplots(figsize=(8, 7))
    gpd.GeoSeries([row.geometry], crs=4326).boundary.plot(ax=ax, color="#1f5fbf", linewidth=1.8)
    ax.fill(*row.geometry.exterior.xy, color="#1f5fbf", alpha=0.06)
    ax.scatter([e["lon"]], [e["lat"]], color="#c1121f", s=60, zorder=5, label=e["location_name"])
    ax.annotate(e["location_name"], (e["lon"], e["lat"]), xytext=(8, 8), textcoords="offset points", color="#c1121f")
    ns = match["nearest_strip"]
    ax.set_title(f"{match['event']} ({match['date']})\nreal archive scene: {ns['acq_date']} "
                 f"({ns['sensor']}, {ns['cloud_pct']}% cloud, {ns['delta_days']:+d}d from the flood)\n"
                 "Footprint outline only -- Airbus proprietary catalog data, not redistributed", fontsize=10)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    fig.tight_layout()
    fig.savefig(DIAGNOSTIC_PNG, dpi=140)
    plt.close(fig)
    log.info("Saved -> %s", DIAGNOSTIC_PNG)


if __name__ == "__main__":
    main()
