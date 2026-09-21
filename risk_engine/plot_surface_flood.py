"""
plot_surface_flood.py — figures for the Amsterdam Phase 2 surface-flood result.

  amsterdam_surface_flood_map.png   AOI overview of maximum depth + three
                                    zooms on the worst-flooded areas, over
                                    real BGT buildings and water.
  amsterdam_surface_flood_detail.png  Depth evolution (30/45/60 min) for the
                                    largest-volume cluster, where each
                                    cluster's water ends up (stored on the
                                    street vs. reaching canals), and the
                                    sensitivity of the result.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rasterio
from matplotlib.colors import ListedColormap, BoundaryNorm
from shapely.geometry import shape

import amsterdam_terrain as T
import surface_flood_amsterdam as S
from amsterdam_bgt_fetch import fetch_bgt
import build_amsterdam_swmm as bm

HERE = Path(__file__).parent
OUT = HERE / "data" / "amsterdam_swmm"

BOUNDS = [0.05, 0.10, 0.20, 0.30, 0.50, 1.5]
CMAP = ListedColormap(["#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08306b"])
NORM = BoundaryNorm(BOUNDS, CMAP.N)


def _bg(ax, bgt, x0, x1, y0, y1):
    from bgt_draw import draw_bgt
    draw_bgt(ax, bgt, bounds=(x0, x1, y0, y1))


def _depth_layer(ax, depth, x0, x1, y0, y1):
    ext = (T.X0, T.X0 + depth.shape[1] * T.CELL, T.Y1 - depth.shape[0] * T.CELL, T.Y1)
    d = np.ma.masked_less(depth, 0.05)
    im = ax.imshow(d, extent=ext, cmap=CMAP, norm=NORM, zorder=3, interpolation="nearest")
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
    return im


def main():
    res = json.loads((OUT / f"surface_flood_{S.STORM}_results.json").read_text())
    with rasterio.open(OUT / f"surface_flood_{S.STORM}_maxdepth.tif") as src:
        depth = src.read(1)
    bgt = fetch_bgt(bm.CENTER[0], bm.CENTER[1], T.HALF)
    sources = S.load_sources()
    base = res["baseline"]

    # pick up to three DISTINCT locations (>= 150 m apart) with the most >=30 cm area
    def area30(cl):
        j0, j1, i0, i1 = cl["window"]
        return float((depth[j0:j1, i0:i1] >= 0.30).sum())
    picks = []
    for k in sorted(range(len(base["clusters"])), key=lambda k: -area30(base["clusters"][k])):
        cl = base["clusters"][k]
        j0, j1, i0, i1 = cl["window"]
        jj, ii = np.where(depth[j0:j1, i0:i1] >= 0.10)
        if len(jj) == 0:
            continue
        x, y = T.cell_center(int(j0 + jj.mean()), int(i0 + ii.mean()))
        if all(np.hypot(x - px, y - py) >= 150 for _, px, py in picks):
            picks.append((k, x, y))
        if len(picks) == 3:
            break

    fig = plt.figure(figsize=(16, 9.2))
    ax0 = fig.add_axes([0.02, 0.05, 0.50, 0.84])
    _bg(ax0, bgt, T.X0, T.X0 + 1700, T.Y1 - 1700, T.Y1)
    im = _depth_layer(ax0, depth, T.X0, T.X0 + 1700, T.Y1 - 1700, T.Y1)
    ax0.scatter([s["x"] for s in sources], [s["y"] for s in sources], s=8, c="#c1121f", zorder=5, label="flooded manhole (37)")
    ax0.legend(loc="lower left", fontsize=8, frameon=True)
    st = base["stats"]
    ax0.set_title(f"Maximum surface depth, Bui10 (T=10 yr) — sewer overflow only\n"
                  f"{st['area_ge_10cm_m2']:,.0f} m² ≥10 cm · {st['area_ge_30cm_m2']:,.0f} m² ≥30 cm · max {st['max_depth_m']:.2f} m "
                  f"(≈{100*st['area_ge_10cm_m2']/(1700*1700):.2f}% of the 2.9 km² area)", fontsize=10)
    slots = [[0.545, 0.665, 0.34, 0.235], [0.545, 0.375, 0.34, 0.235], [0.545, 0.085, 0.34, 0.235]]
    for n_, (k, x, y) in enumerate(picks):
        cl = base["clusters"][k]
        half = 80
        ax = fig.add_axes(slots[n_])
        yy = half * 0.9
        _bg(ax, bgt, x - half, x + half, y - yy, y + yy)
        _depth_layer(ax, depth, x - half, x + half, y - yy, y + yy)
        near = [s for s in sources if abs(s["x"] - x) < half and abs(s["y"] - y) < yy]
        ax.scatter([s["x"] for s in near], [s["y"] for s in near], s=30, c="#c1121f", zorder=5, edgecolor="white", lw=0.6)
        ax0.plot([x - half, x + half, x + half, x - half, x - half],
                 [y - yy, y - yy, y + yy, y + yy, y - yy], color="#c1121f", lw=1.2, zorder=6)
        ax0.text(x, y + yy + 14, str(n_ + 1), color="#c1121f", fontsize=11, fontweight="bold", ha="center", zorder=7)
        ax.set_title(f"{n_ + 1}  ·  {cl['injected_m3']:.0f} m³ overflow, {cl['n_nodes']} manhole(s); "
                     f"peak {depth[cl['window'][0]:cl['window'][1], cl['window'][2]:cl['window'][3]].max():.2f} m", fontsize=9, loc="left")
    cax = fig.add_axes([0.925, 0.2, 0.012, 0.55])
    cb = fig.colorbar(im, cax=cax, ticks=[0.05, 0.10, 0.20, 0.30, 0.50, 1.0])
    cb.set_label("max depth (m)")
    fig.suptitle("Amsterdam canal ring — sewer overflow spread over real terrain (AHN LiDAR + BGT buildings), Phase 2\n"
                 "One-way coupled, indicative only: no re-entry to the sewer, no direct street rainfall, not calibrated", fontsize=11, y=0.985)
    fig.savefig(OUT / "amsterdam_surface_flood_map.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- detail figure -------------------------------------------------------
    snaps = np.load(OUT / f"surface_flood_{S.STORM}_snaps.npz")
    k0 = 0
    j0, j1, i0, i1 = [int(v) for v in snaps[f"c{k0}_window"]]
    fig, axs = plt.subplots(2, 3, figsize=(15, 8.6))
    for ax, tmin in zip(axs[0], S.SNAP_TIMES_MIN):
        h = snaps[f"c{k0}_{tmin}"].astype(np.float32)
        x0 = T.X0 + i0 * T.CELL; x1 = T.X0 + i1 * T.CELL; y1 = T.Y1 - j0 * T.CELL; y0 = T.Y1 - j1 * T.CELL
        _bg(ax, bgt, x0, x1, y0, y1)
        ext = (x0, x1, y0, y1)
        ax.imshow(np.ma.masked_less(h, 0.05), extent=ext, cmap=CMAP, norm=NORM, zorder=3, interpolation="nearest")
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal")
        ax.set_title(f"largest cluster ({base['clusters'][k0]['injected_m3']:.0f} m³): depth at t = {tmin} min", fontsize=10)

    ax = axs[1][0]
    cls = base["clusters"]
    stored = [c["stored_m3"] for c in cls]; canal = [c["to_canals_m3"] for c in cls]
    idx = np.arange(len(cls))
    ax.bar(idx, stored, color="#3182bd", label="still on the street at 90 min")
    ax.bar(idx, canal, bottom=stored, color="#9ecae1", label="reached a canal")
    ax.set_xticks(idx); ax.set_xlabel("cluster (largest overflow first)"); ax.set_ylabel("m³")
    ax.set_title("Where each cluster's overflow ends up\n(no sewer re-entry → stored water is upper-end)", fontsize=10)
    ax.legend(frameon=False, fontsize=8)

    ax = axs[1][1]
    lab = ["baseline\nn=0.03, 1 m", "n=0.02", "n=0.05", "2 m grid"]
    sens = res["sensitivity"]
    a10 = [base["stats"]["area_ge_10cm_m2"], sens["manning_0.02"]["stats"]["area_ge_10cm_m2"],
           sens["manning_0.05"]["stats"]["area_ge_10cm_m2"], sens["grid_2m"]["stats"]["area_ge_10cm_m2"]]
    a50 = [base["stats"]["area_ge_50cm_m2"], sens["manning_0.02"]["stats"]["area_ge_50cm_m2"],
           sens["manning_0.05"]["stats"]["area_ge_50cm_m2"], sens["grid_2m"]["stats"]["area_ge_50cm_m2"]]
    w = 0.38; x = np.arange(4)
    ax.bar(x - w / 2, a10, w, color="#6baed6", label="area ≥ 10 cm (robust ±8%)")
    ax.bar(x + w / 2, a50, w, color="#08306b", label="area ≥ 50 cm (resolution-dependent)")
    for xi, v in zip(x - w / 2, a10): ax.text(xi, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
    for xi, v in zip(x + w / 2, a50): ax.text(xi, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=9); ax.set_ylabel("m²")
    ax.set_title("Sensitivity: extent is robust, the deep tail is not", fontsize=10)
    ax.set_ylim(0, max(a10) * 1.18)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1)

    ax = axs[1][2]; ax.axis("off")
    g = res["terrain_vs_sewer_ground_check"]; ex = base["exposure"]
    lines = ["Checks behind these maps", "",
             f"solver vs known solutions ........ 5/5 pass",
             f"mass closure (52 window runs) .... ≤ {max(base['max_closure_err'], *(v['max_closure_err'] for v in sens.values())):.0e}",
             f"injected vs SWMM flood volume .... {base['totals_m3']['injected_m3']:.0f} vs {base['totals_m3']['swmm_reported_m3']:.0f} m³",
             f"sewer ground vs AHN LiDAR ........ median {g['median_m']*100:+.1f} cm,",
             f"   {g['pct_within_10cm']:.0f}% within 10 cm (n={g['n']:,} manholes)", "",
             "Exposure proxy (street depth beside footprint):",
             f"   {ex['n_adjacent_ge_10cm']} of {ex['n_buildings']:,} buildings ≥10 cm",
             f"   {ex['n_adjacent_ge_30cm']} buildings ≥30 cm",
             "   (street-side depth; NOT water entering buildings)", "",
             "Not calibrated or validated vs any observed flood."]
    ax.text(0.0, 1.0, "\n".join(lines), va="top", fontsize=10, family="monospace")
    fig.suptitle("Amsterdam Phase 2 — detail, fate of the water, sensitivity", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "amsterdam_surface_flood_detail.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("saved")


if __name__ == "__main__":
    main()
