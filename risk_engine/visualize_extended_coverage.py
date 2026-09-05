"""
visualize_extended_coverage.py — Choropleth of the extended-coverage risk
grid (extended_coverage.py output: 10 districts, 2 disjoint clusters, 2024
cells), with all documented Greater Accra flood events overlaid.

Two side-by-side panels, one per cluster, since they're geographically
disjoint (western block vs. Tema/Ashaiman) and plotting them on one shared
axis would mean a huge empty gap in the middle.

Output: data/extended_coverage_diagnostic.png
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
GRID_PATH = HERE / "data" / "extended_risk_grid.geojson"
ASSEMBLIES_PATH = HERE / "data" / "extended_district_assemblies.geojson"
EVENTS_PATH = HERE / "data" / "historical_flood_events.json"
OUTPUT = HERE / "data" / "extended_coverage_diagnostic.png"

DARK, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, GOLD = "#e6edf3", "#8b949e", "#d4a017"
RED = "#ff5555"


def load_events_by_cluster():
    events = json.loads(EVENTS_PATH.read_text())["events"]
    located = [e for e in events if e.get("lon") is not None]
    unlocated = [e for e in events if e.get("lon") is None]
    return located, unlocated


def main() -> None:
    grid = gpd.read_file(GRID_PATH)
    assemblies = gpd.read_file(ASSEMBLIES_PATH)
    assemblies["lon"] = assemblies.geometry.centroid.x
    assemblies["lat"] = assemblies.geometry.centroid.y
    located_events, unlocated_events = load_events_by_cluster()

    cmap = matplotlib.colormaps["RdYlGn_r"]
    norm = mcolors.Normalize(vmin=grid["score"].min(), vmax=grid["score"].max())

    fig, axes = plt.subplots(1, 2, figsize=(22, 9), facecolor=DARK,
                              gridspec_kw={"width_ratios": [1.6, 1]})
    fig.subplots_adjust(left=0.04, right=0.96, top=0.87, bottom=0.1, wspace=0.15)
    fig.suptitle(
        "ThirdWave Extended Coverage — 10 Districts, 2 Disjoint Clusters (500m grid)\n"
        f"{len(grid)} cells · score range {grid['score'].min():.1f}-{grid['score'].max():.1f} · "
        "documented Greater Accra flood events overlaid",
        color=TEXT, fontsize=13, fontweight="bold", y=0.97,
    )

    for ax in axes:
        ax.set_facecolor(CARD)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.tick_params(colors=MUTED, labelsize=7)

    cluster_bounds = {}
    for c in grid["cluster"].unique():
        sub = grid[grid["cluster"] == c]
        cluster_bounds[c] = sub.total_bounds  # minx, miny, maxx, maxy

    # Panel 0: cluster 0 (western block — existing pilot + Weija Gbawe + Ga South)
    ax0 = axes[0]
    grid0 = grid[grid["cluster"] == 0]
    grid0.plot(column="score", ax=ax0, cmap=cmap, norm=norm, edgecolor=BORDER, linewidth=0.25)
    assemblies[assemblies["name"].isin(grid0["assembly"].unique())].boundary.plot(
        ax=ax0, color=GOLD, linewidth=1.2, alpha=0.9)
    for _, row in assemblies.iterrows():
        if row["name"] not in grid0["assembly"].unique():
            continue
        short = row["name"].replace(" Municipal", "")
        ax0.text(row["lon"], row["lat"], short, ha="center", va="center", fontsize=6.5,
                  color=TEXT, fontweight="bold", alpha=0.8,
                  path_effects=[pe.withStroke(linewidth=1.8, foreground=DARK)])
    ax0.set_title("Cluster 0: Western block\n(Ablekuma x3, Accra Metro, Ayawaso Central, "
                  "Korle Klottey, Weija Gbawe, Ga South)", color=TEXT, fontsize=9.5, pad=8)

    # Panel 1: cluster 1 (Tema/Ashaiman)
    ax1 = axes[1]
    grid1 = grid[grid["cluster"] == 1]
    grid1.plot(column="score", ax=ax1, cmap=cmap, norm=norm, edgecolor=BORDER, linewidth=0.4)
    assemblies[assemblies["name"].isin(grid1["assembly"].unique())].boundary.plot(
        ax=ax1, color=GOLD, linewidth=1.4, alpha=0.9)
    for _, row in assemblies.iterrows():
        if row["name"] not in grid1["assembly"].unique():
            continue
        short = row["name"].replace(" Municipal", "").replace(" Metropolitan", "")
        ax1.text(row["lon"], row["lat"], short, ha="center", va="center", fontsize=7.5,
                  color=TEXT, fontweight="bold", alpha=0.85,
                  path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])
    ax1.set_title("Cluster 1: Tema / Ashaiman\n(disjoint from western block — ~10-15km gap, no shared boundary)",
                  color=TEXT, fontsize=9.5, pad=8)

    # Overlay historical events on whichever panel their cluster belongs to
    for ev in located_events:
        lon, lat = ev["lon"], ev["lat"]
        target_ax = None
        for c, bounds in cluster_bounds.items():
            if bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]:
                target_ax = ax0 if c == 0 else ax1
                break
        if target_ax is None:
            continue
        year = ev["date"][:4]
        site = ev["location_name"].split(",")[0].split("(")[0].strip()
        target_ax.scatter([lon], [lat], s=160, facecolor="none", edgecolor=RED, linewidth=2.2, zorder=6)
        target_ax.scatter([lon], [lat], s=32, color=RED, zorder=6)
        target_ax.annotate(f"{site}\n({year})", (lon, lat), xytext=(8, 8), textcoords="offset points",
                     fontsize=6.8, color=RED, fontweight="bold",
                     path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])

    for ax in axes:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cb = plt.colorbar(sm, ax=ax, fraction=0.04, pad=0.02)
        cb.set_label("Vulnerability score", color=MUTED, fontsize=7.5)
        cb.ax.yaxis.set_tick_params(color=MUTED)
        plt.setp(cb.ax.yaxis.get_ticklabels(), color=MUTED, fontsize=6.5)
        ax.set_xlabel("Longitude", color=MUTED, fontsize=8)
        ax.set_ylabel("Latitude", color=MUTED, fontsize=8)

    if unlocated_events:
        note = "Documented but unlocated (not plotted):\n" + "\n".join(
            f"{e['date']} — {e['name']}" for e in unlocated_events)
        fig.text(0.02, 0.015, note, fontsize=6.5, color=MUTED, va="bottom", ha="left")

    fig.text(0.62, 0.015,
              "Source: Sentinel-1 GRD (Planetary Computer) · Copernicus DEM 30m · ESA WorldCover 2021 · "
              "Boundaries: OCHA COD-AB · Events geocoded via OSM Nominatim",
              ha="left", color=MUTED, fontsize=6.5)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=DARK)
    print(f"Saved -> {OUTPUT}")


if __name__ == "__main__":
    main()
