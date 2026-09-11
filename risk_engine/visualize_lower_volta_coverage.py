"""
visualize_lower_volta_coverage.py — Choropleth of the Lower Volta basin
risk grid (lower_volta_coverage.py output: 7 districts, 1 connected
cluster, 16,941 cells), with the documented Akosombo/Kpong dam-spillage
event overlaid.

Single panel, unlike visualize_extended_coverage.py's two -- all 7 Lower
Volta districts form one connected component (North Tongu borders every
other district in the set), so there's no disjoint-cluster gap to avoid.

Output: data/lower_volta_coverage_diagnostic.png
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "lower_volta_risk_grid.geojson"
ASSEMBLIES_PATH = HERE / "data" / "lower_volta_district_assemblies.geojson"
EVENTS_PATH = HERE / "data" / "historical_flood_events.json"
OUTPUT = HERE / "data" / "lower_volta_coverage_diagnostic.png"

DARK, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, GOLD = "#e6edf3", "#8b949e", "#d4a017"
RED = "#ff5555"


def main() -> None:
    grid = gpd.read_file(GRID_PATH)
    assemblies = gpd.read_file(ASSEMBLIES_PATH)
    assemblies["lon"] = assemblies.geometry.centroid.x
    assemblies["lat"] = assemblies.geometry.centroid.y

    events = json.loads(EVENTS_PATH.read_text())["events"]
    minx, miny, maxx, maxy = grid.total_bounds
    located_in_bbox = [
        e for e in events
        if e.get("lon") is not None and minx <= e["lon"] <= maxx and miny <= e["lat"] <= maxy
    ]

    cmap = matplotlib.colormaps["RdYlGn_r"]
    norm = mcolors.Normalize(vmin=grid["score"].min(), vmax=grid["score"].max())

    fig, ax = plt.subplots(1, 1, figsize=(14, 12), facecolor=DARK)
    fig.subplots_adjust(left=0.06, right=0.94, top=0.88, bottom=0.08)
    fig.suptitle(
        "ThirdWave Lower Volta Basin Coverage — 7 Districts, 1 Connected Cluster (500m grid)\n"
        f"{len(grid)} cells · score range {grid['score'].min():.1f}-{grid['score'].max():.1f} "
        "(all Low/Moderate — statistical SAR/DEM/land-cover score, structurally blind to the "
        "one-off dam-release event marked below)",
        color=TEXT, fontsize=12.5, fontweight="bold", y=0.97,
    )

    ax.set_facecolor(CARD)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
    ax.tick_params(colors=MUTED, labelsize=8)

    grid.plot(column="score", ax=ax, cmap=cmap, norm=norm, edgecolor=BORDER, linewidth=0.15)
    assemblies.boundary.plot(ax=ax, color=GOLD, linewidth=1.4, alpha=0.9)
    for _, row in assemblies.iterrows():
        short = row["name"]
        ax.text(row["lon"], row["lat"], f"{short}\n({row['region']})", ha="center", va="center",
                 fontsize=8, color=TEXT, fontweight="bold", alpha=0.85,
                 path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])

    for ev in located_in_bbox:
        lon, lat = ev["lon"], ev["lat"]
        year = ev["date"][:4]
        site = ev["location_name"].split(",")[0].split("(")[0].strip()
        ax.scatter([lon], [lat], s=260, facecolor="none", edgecolor=RED, linewidth=2.6, zorder=6)
        ax.scatter([lon], [lat], s=50, color=RED, zorder=6)
        ax.annotate(f"{site} ({year})\n{ev['name']}", (lon, lat), xytext=(10, 10),
                     textcoords="offset points", fontsize=8, color=RED, fontweight="bold",
                     path_effects=[pe.withStroke(linewidth=2.2, foreground=DARK)])

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("Vulnerability score", color=MUTED, fontsize=8.5)
    cb.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(cb.ax.yaxis.get_ticklabels(), color=MUTED, fontsize=7.5)
    ax.set_xlabel("Longitude", color=MUTED, fontsize=9)
    ax.set_ylabel("Latitude", color=MUTED, fontsize=9)

    fig.text(
        0.06, 0.02,
        "Source: Sentinel-1 GRD (Planetary Computer) · Copernicus DEM 30m · ESA WorldCover 2021 · "
        "Boundaries: OCHA COD-AB.\n"
        "This is extended coverage, not the MVP pilot -- see risk_engine/lower_volta_coverage.py. "
        "Dam-spillage flood extent itself is mapped separately via SAR/S2 change detection "
        "(dam_spillage_sar_comparison.py, dam_spillage_s2_mndwi.py), not this composite score.",
        ha="left", va="bottom", color=MUTED, fontsize=7.2,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=DARK)
    print(f"Saved -> {OUTPUT}")


if __name__ == "__main__":
    main()
