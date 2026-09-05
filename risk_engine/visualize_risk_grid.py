"""
visualize_risk_grid.py — Choropleth of the fine-grained pilot risk grid
(risk_grid.py output), with known ground-truth points overlaid for a visual
sanity check: Kwame Nkrumah Circle (2015 disaster epicenter) and Kaneshie
Market (also flood-affected in 2015, per Wikipedia).

Output: data/pilot_risk_grid_diagnostic.png
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "pilot_risk_grid.geojson"
ASSEMBLIES_PATH = HERE / "data" / "pilot_district_assemblies.geojson"
EVENTS_PATH = HERE / "data" / "historical_flood_events.json"
OUTPUT = HERE / "data" / "pilot_risk_grid_diagnostic.png"

DARK, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, GOLD = "#e6edf3", "#8b949e", "#d4a017"

GROUND_TRUTH = {
    "Kaneshie Market\n(2015 flood-affected)": (-0.2342995, 5.5644409),
}


def load_historical_events() -> tuple[dict, list[dict]]:
    """Group geocoded historical events by (lon, lat) so a recurring site
    (Circle flooded in both 2015 and 2023) gets one marker with both years
    listed, not two overlapping ones. Returns (grouped_points, unlocated)."""
    events = json.loads(EVENTS_PATH.read_text())["events"]
    grouped: dict[tuple[float, float], list[dict]] = {}
    unlocated = []
    for ev in events:
        if ev.get("lon") is None:
            unlocated.append(ev)
            continue
        key = (ev["lon"], ev["lat"])
        grouped.setdefault(key, []).append(ev)
    return grouped, unlocated


def main() -> None:
    grid = gpd.read_file(GRID_PATH)
    assemblies = gpd.read_file(ASSEMBLIES_PATH)
    assemblies["lon"] = assemblies.geometry.centroid.x
    assemblies["lat"] = assemblies.geometry.centroid.y

    historical_grouped, unlocated = load_historical_events()

    fig, axes = plt.subplots(1, 2, figsize=(20, 9), facecolor=DARK)
    fig.subplots_adjust(left=0.04, right=0.97, top=0.87, bottom=0.08, wspace=0.14)
    fig.suptitle(
        "ThirdWave Pilot District — Fine-Grained Risk Grid (500m cells)\n"
        f"{len(grid)} cells · Sentinel-1 SAR + Copernicus DEM + ESA WorldCover · "
        "vs. assembly-level scoring, with all documented Accra flood events overlaid",
        color=TEXT, fontsize=13, fontweight="bold", y=0.97,
    )

    for ax in axes:
        ax.set_facecolor(CARD)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.tick_params(colors=MUTED, labelsize=7)

    cmap = matplotlib.colormaps["RdYlGn_r"]
    norm = mcolors.Normalize(vmin=grid["score"].min(), vmax=grid["score"].max())

    # Panel 1 — full grid choropleth
    ax1 = axes[0]
    grid.plot(column="score", ax=ax1, cmap=cmap, norm=norm, edgecolor=BORDER, linewidth=0.3)
    assemblies.boundary.plot(ax=ax1, color=GOLD, linewidth=1.3, alpha=0.9)
    for _, row in assemblies.iterrows():
        short = row["name"].replace(" Municipal", "")
        ax1.text(row["lon"], row["lat"], short, ha="center", va="center", fontsize=7,
                  color=TEXT, fontweight="bold", alpha=0.85,
                  path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])
    for label, (lon, lat) in GROUND_TRUTH.items():
        ax1.scatter([lon], [lat], s=140, facecolor="none", edgecolor="white", linewidth=2, zorder=5)
        ax1.scatter([lon], [lat], s=30, color="white", zorder=5)
        ax1.annotate(label, (lon, lat), xytext=(8, 8), textcoords="offset points",
                     fontsize=7, color="white", fontweight="bold",
                     path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])
    # Documented historical flood events (grouped by site — a recurring site
    # like Circle gets one marker listing every year it flooded, not a stack
    # of overlapping duplicate markers).
    for (lon, lat), evs in historical_grouped.items():
        years = ", ".join(sorted(e["date"][:4] for e in evs))
        site = evs[0]["location_name"].split(",")[0]
        label = f"{site}\n(flooded: {years})"
        ax1.scatter([lon], [lat], s=180, facecolor="none", edgecolor="#ff5555", linewidth=2.5, zorder=6)
        ax1.scatter([lon], [lat], s=35, color="#ff5555", zorder=6)
        ax1.annotate(label, (lon, lat), xytext=(10, -18), textcoords="offset points",
                     fontsize=7.5, color="#ff5555", fontweight="bold",
                     path_effects=[pe.withStroke(linewidth=2.2, foreground=DARK)])
    if unlocated:
        note_lines = [f"{e['date']} {e['name']} — no specific site in source" for e in unlocated]
        ax1.text(0.02, 0.02, "Documented but unlocated:\n" + "\n".join(note_lines),
                  transform=ax1.transAxes, fontsize=6.5, color=MUTED, va="bottom", ha="left",
                  bbox=dict(boxstyle="round", facecolor=CARD, edgecolor=BORDER, alpha=0.9))
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb1 = plt.colorbar(sm, ax=ax1, fraction=0.036, pad=0.02)
    cb1.set_label("Vulnerability score (grid cell)", color=MUTED, fontsize=8)
    cb1.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(cb1.ax.yaxis.get_ticklabels(), color=MUTED, fontsize=7)
    ax1.set_title(f"500m Grid Choropleth\nscore range {grid['score'].min():.1f}-{grid['score'].max():.1f} "
                  f"(assembly-level was 23.1-31.0)", color=TEXT, fontsize=10, pad=8)
    ax1.set_xlabel("Longitude", color=MUTED, fontsize=8)
    ax1.set_ylabel("Latitude", color=MUTED, fontsize=8)

    # Panel 2 — zoomed inset around the recurring hotspot (Kwame Nkrumah Circle,
    # flooded in both documented events with a precise location: 2015 and 2023)
    ax2 = axes[1]
    circle_key = max(historical_grouped, key=lambda k: len(historical_grouped[k]))
    clon, clat = circle_key
    circle_years = ", ".join(sorted(e["date"][:4] for e in historical_grouped[circle_key]))
    zoom_pad = 0.02
    zoom_bounds = (clon - zoom_pad, clat - zoom_pad, clon + zoom_pad, clat + zoom_pad)
    grid.plot(column="score", ax=ax2, cmap=cmap, norm=norm, edgecolor=BORDER, linewidth=0.6)
    assemblies.boundary.plot(ax=ax2, color=GOLD, linewidth=1.3, alpha=0.9)
    for _, row in grid.iterrows():
        c = row["geometry"].centroid
        if zoom_bounds[0] <= c.x <= zoom_bounds[2] and zoom_bounds[1] <= c.y <= zoom_bounds[3]:
            ax2.text(c.x, c.y, f"{row['score']:.0f}", ha="center", va="center", fontsize=7,
                      color=TEXT, fontweight="bold",
                      path_effects=[pe.withStroke(linewidth=1.8, foreground=DARK)])
    ax2.scatter([clon], [clat], s=200, facecolor="none", edgecolor="#ff5555", linewidth=2.5, zorder=5)
    ax2.scatter([clon], [clat], s=40, color="#ff5555", zorder=5)
    ax2.annotate(f"Kwame Nkrumah Circle\n(flooded: {circle_years})", (clon, clat), xytext=(10, 10),
                 textcoords="offset points", fontsize=8, color="#ff5555", fontweight="bold",
                 path_effects=[pe.withStroke(linewidth=2.5, foreground=DARK)])
    ax2.set_xlim(zoom_bounds[0], zoom_bounds[2])
    ax2.set_ylim(zoom_bounds[1], zoom_bounds[3])
    ax2.set_title(f"Zoomed: cells around Kwame Nkrumah Circle\nflooded in {circle_years} — assembly avg is 23.1 (rank 6/6), this cell is 33.0",
                  color=TEXT, fontsize=10, pad=8)
    ax2.set_xlabel("Longitude", color=MUTED, fontsize=8)
    ax2.set_ylabel("Latitude", color=MUTED, fontsize=8)

    fig.text(0.5, 0.01,
              "Source: Sentinel-1 GRD (Planetary Computer) · Copernicus DEM 30m · ESA WorldCover 2021 · "
              "Ground-truth points geocoded via OpenStreetMap Nominatim",
              ha="center", color=MUTED, fontsize=7)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=DARK)
    print(f"Saved -> {OUTPUT}")


if __name__ == "__main__":
    main()
