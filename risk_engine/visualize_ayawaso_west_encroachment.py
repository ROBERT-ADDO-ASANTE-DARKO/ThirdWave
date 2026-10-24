"""
visualize_ayawaso_west_encroachment.py — diagnostic for the Ayawaso West
Municipal addition (East Legon / East Legon Hills): the generic SAR/DEM/LULC
vulnerability score side by side with the channel-encroachment index, to
show visually why the first misses the hazard and the second catches it.

Output: data/ayawaso_west_encroachment_diagnostic.png
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
from matplotlib.colors import ListedColormap, BoundaryNorm

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "ayawaso_west_risk_grid.geojson"
ENCROACH_PATH = HERE / "data" / "ayawaso_west_channel_encroachment_index.json"
ASSEMBLIES_PATH = HERE / "data" / "extended_district_assemblies.geojson"
EVENTS_PATH = HERE / "data" / "historical_flood_events.json"
OUTPUT = HERE / "data" / "ayawaso_west_encroachment_diagnostic.png"

DARK, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, GOLD = "#e6edf3", "#8b949e", "#d4a017"
RED = "#ff5555"

LEVEL_ORDER = ["insufficient_data", "Low", "Moderate", "High", "Very High"]
LEVEL_COLORS = ["#30363d", "#1E8A4C", "#B8860B", "#C1621B", "#B0241D"]


def main() -> None:
    grid = gpd.read_file(GRID_PATH)
    encroach = json.loads(ENCROACH_PATH.read_text())
    assembly = gpd.read_file(ASSEMBLIES_PATH)
    assembly = assembly[assembly["name"] == "Ayawaso West Municipal"]

    grid["encroach_level"] = grid["zone_id"].map(
        lambda z: encroach.get(z, {}).get("encroachment_level", "insufficient_data")
        if encroach.get(z, {}).get("status") == "ok" else "insufficient_data"
    )
    grid["encroach_rank"] = grid["encroach_level"].map(LEVEL_ORDER.index)
    n_ok = int((grid["encroach_level"] != "insufficient_data").sum())
    n_very_high = int((grid["encroach_level"] == "Very High").sum())

    events = json.loads(EVENTS_PATH.read_text())["events"]
    minx, miny, maxx, maxy = grid.total_bounds
    local_events = [e for e in events if e.get("lon") is not None
                     and minx <= e["lon"] <= maxx and miny <= e["lat"] <= maxy]

    fig, axes = plt.subplots(1, 2, figsize=(16, 8.5), facecolor=DARK)
    fig.subplots_adjust(left=0.05, right=0.95, top=0.85, bottom=0.08, wspace=0.18)
    fig.suptitle(
        "Ayawaso West Municipal (East Legon / East Legon Hills) — score vs. encroachment\n"
        f"{len(grid)} cells, 500m grid · generic vulnerability score misses this area; "
        f"channel-encroachment index doesn't ({n_ok} cells scored, {n_very_high} Very High)",
        color=TEXT, fontsize=12, fontweight="bold", y=0.97,
    )

    for ax in axes:
        ax.set_facecolor(CARD)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.tick_params(colors=MUTED, labelsize=7)
        assembly.boundary.plot(ax=ax, color=GOLD, linewidth=1.4, alpha=0.9)

    # Panel 0: generic SAR/DEM/LULC score
    ax0 = axes[0]
    cmap0 = matplotlib.colormaps["RdYlGn_r"]
    norm0 = mcolors.Normalize(vmin=grid["score"].min(), vmax=grid["score"].max())
    grid.plot(column="score", ax=ax0, cmap=cmap0, norm=norm0, edgecolor=BORDER, linewidth=0.3)
    ax0.set_title(f"Generic score (SAR/DEM/LULC)\nrange {grid['score'].min():.1f}-{grid['score'].max():.1f} -- "
                  f"all \"Low\"/\"Moderate\", no standing-water signal", color=TEXT, fontsize=9.5, pad=8)
    sm0 = plt.cm.ScalarMappable(cmap=cmap0, norm=norm0); sm0.set_array([])
    cb0 = plt.colorbar(sm0, ax=ax0, fraction=0.045, pad=0.02)
    cb0.set_label("Vulnerability score", color=MUTED, fontsize=7.5)
    cb0.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(cb0.ax.yaxis.get_ticklabels(), color=MUTED, fontsize=6.5)

    # Panel 1: channel-encroachment level (categorical)
    ax1 = axes[1]
    cmap1 = ListedColormap(LEVEL_COLORS)
    norm1 = BoundaryNorm(range(len(LEVEL_ORDER) + 1), cmap1.N)
    grid.plot(column="encroach_rank", ax=ax1, cmap=cmap1, norm=norm1, edgecolor=BORDER, linewidth=0.3)
    ax1.set_title("Channel-encroachment index (OSM building-to-waterway distance)\n"
                  f"{n_ok}/{len(grid)} cells computable, {n_very_high} \"Very High\" "
                  "(building within 10m of a mapped waterway)", color=TEXT, fontsize=9.5, pad=8)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in LEVEL_COLORS]
    ax1.legend(handles, LEVEL_ORDER, loc="lower left", fontsize=7, framealpha=0.9,
               facecolor=CARD, edgecolor=BORDER, labelcolor=TEXT)

    for ax in axes:
        for ev in local_events:
            lon, lat = ev["lon"], ev["lat"]
            site = ev["location_name"].split(",")[0].split("(")[0].strip()
            year = ev["date"][:4]
            ax.scatter([lon], [lat], s=160, facecolor="none", edgecolor=RED, linewidth=2.2, zorder=6)
            ax.scatter([lon], [lat], s=32, color=RED, zorder=6)
            ax.annotate(f"{site}\n({year})", (lon, lat), xytext=(8, 8), textcoords="offset points",
                        fontsize=6.8, color=RED, fontweight="bold",
                        path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])
        ax.set_xlabel("Longitude", color=MUTED, fontsize=8)
        ax.set_ylabel("Latitude", color=MUTED, fontsize=8)

    fig.text(0.02, 0.015,
              "Source: Sentinel-1 GRD/Copernicus DEM/ESA WorldCover (Planetary Computer) · OCHA COD-AB boundary · "
              "OSM Overpass buildings/waterways · Events geocoded via OSM Nominatim",
              ha="left", color=MUTED, fontsize=6.5)
    fig.text(0.98, 0.015,
              "Grey = insufficient OSM data (< 5 buildings or no mapped waterway in that cell), not \"Low risk\"",
              ha="right", color=MUTED, fontsize=6.5)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=DARK)
    print(f"Saved -> {OUTPUT}")


if __name__ == "__main__":
    main()
