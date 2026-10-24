"""
visualize_lower_volta_encroachment.py — diagnostic for
data/lower_volta_channel_encroachment_index.json, computed when
lower_volta_coverage.py was first built but never visualized until now.

Only 348/16,941 cells (2%) have enough OSM data to compute anything --
expected and consistent with the Ablekuma West finding documented
elsewhere in this project (rural/small-town Ghana has much thinner OSM
waterway tagging than Accra). What IS computable concentrates in real,
identifiable towns directly on the Volta: Sogakope, Lolonyo (near Akuse),
Juapong, and the Ada Foah area -- reverse-geocoded, not guessed.

Output: data/lower_volta_encroachment_diagnostic.png
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import ListedColormap

HERE = Path(__file__).parent
GRID_PATH = HERE / "data" / "lower_volta_risk_grid.geojson"
ENCROACH_PATH = HERE / "data" / "lower_volta_channel_encroachment_index.json"
ASSEMBLIES_PATH = HERE / "data" / "lower_volta_district_assemblies.geojson"
OUTPUT = HERE / "data" / "lower_volta_encroachment_diagnostic.png"

DARK, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, GOLD = "#e6edf3", "#8b949e", "#d4a017"

LEVEL_ORDER = ["Low", "Moderate", "High", "Very High"]
LEVEL_COLORS = ["#1E8A4C", "#B8860B", "#C1621B", "#B0241D"]

# Reverse-geocoded, not assumed -- the 4 clusters where "Very High" cells landed
HOTSPOT_LABELS = {
    "Sogakope\n(South Tongu)": (0.5882, 6.0005),
    "Lolonyo / Akuse area\n(Lower Manya)": (0.0612, 6.1581),
    "Juapong\n(North Tongu)": (0.1378, 6.2617),
    "Ada Foah area\n(Ada East)": (0.6152, 5.8068),
}


def main():
    grid = gpd.read_file(GRID_PATH)
    encroach = json.loads(ENCROACH_PATH.read_text())
    assemblies = gpd.read_file(ASSEMBLIES_PATH)

    grid["encroach_level"] = grid["zone_id"].map(
        lambda z: encroach.get(z, {}).get("encroachment_level")
        if encroach.get(z, {}).get("status") == "ok" else None
    )
    computable = grid[grid["encroach_level"].notna()].copy()
    computable["rank"] = computable["encroach_level"].map(LEVEL_ORDER.index)
    n_ok = len(computable)
    n_very_high = int((computable["encroach_level"] == "Very High").sum())

    fig, ax = plt.subplots(figsize=(13, 11), facecolor=DARK)
    ax.set_facecolor(CARD)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
    ax.tick_params(colors=MUTED, labelsize=8)

    assemblies.boundary.plot(ax=ax, color=GOLD, linewidth=1.0, alpha=0.8)
    for _, row in assemblies.iterrows():
        c = row.geometry.centroid
        ax.text(c.x, c.y, row["name"], ha="center", va="center", fontsize=8,
                 color=TEXT, alpha=0.55, path_effects=[pe.withStroke(linewidth=2, foreground=DARK)])

    cmap = ListedColormap(LEVEL_COLORS)
    # buffer so a single 500m cell is visible at basin scale
    computable_buffered = computable.copy()
    computable_buffered["geometry"] = computable.geometry.centroid.buffer(0.012)
    for lvl, color in zip(LEVEL_ORDER, LEVEL_COLORS):
        sub = computable_buffered[computable["encroach_level"] == lvl]
        if len(sub):
            sub.plot(ax=ax, color=color, alpha=0.85, edgecolor="none",
                      zorder=3 + LEVEL_ORDER.index(lvl))

    for label, (lon, lat) in HOTSPOT_LABELS.items():
        ax.scatter([lon], [lat], s=40, facecolor="none", edgecolor="yellow", linewidth=1.5, zorder=10)
        ax.annotate(label, (lon, lat), xytext=(10, 10), textcoords="offset points",
                    fontsize=8, color="yellow", fontweight="bold",
                    path_effects=[pe.withStroke(linewidth=2, foreground=DARK)], zorder=11)

    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=c, markersize=10)
               for c in LEVEL_COLORS]
    ax.legend(handles, LEVEL_ORDER, loc="lower left", fontsize=9, framealpha=0.9,
               facecolor=CARD, edgecolor=BORDER, labelcolor=TEXT, title="Channel-encroachment level",
               title_fontsize=9)

    ax.set_title(
        f"Lower Volta basin -- channel-encroachment index (OSM building-to-waterway distance)\n"
        f"{n_ok}/{len(grid)} cells computable ({100*n_ok/len(grid):.1f}% -- thin rural OSM waterway "
        f"tagging, same limitation as Ablekuma West), {n_very_high} \"Very High\"\n"
        "Computed cells shown as 1.3km markers (buffered from their real 500m footprint for basin-scale visibility)",
        color=TEXT, fontsize=10.5, pad=12,
    )
    ax.set_xlabel("Longitude", color=MUTED, fontsize=9)
    ax.set_ylabel("Latitude", color=MUTED, fontsize=9)
    fig.text(0.02, 0.01,
              "Source: OSM Overpass buildings/waterways · OCHA COD-AB district boundaries · "
              "hotspot labels reverse-geocoded via OSM Nominatim",
              ha="left", color=MUTED, fontsize=7)

    fig.tight_layout()
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=DARK)
    print(f"Saved -> {OUTPUT}")


if __name__ == "__main__":
    main()
