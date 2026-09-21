"""
plot_amsterdam_swmm.py — figures for the Phase 1 Amsterdam SWMM results
(results.json from run_amsterdam_swmm.py).

  amsterdam_swmm_maps.png     Bui08 vs Bui10: pipes coloured by how long they
                              flow full, flooded manholes sized by volume,
                              over real BGT buildings/water.
  amsterdam_swmm_summary.png  Storm hyetographs, flood/inflow by storm,
                              sensitivity of the Bui10 result, and the
                              numerical-quality indicators.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from shapely.geometry import shape

import build_amsterdam_swmm as bm
from amsterdam_bgt_fetch import fetch_bgt

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "amsterdam_swmm"


def _bgt_background(ax, bgt):
    from bgt_draw import draw_bgt
    draw_bgt(ax, bgt, offset=bm.CENTER)


def _map(ax, storm, res, net, bgt):
    x0, y0 = bm.CENTER
    nodes, cond = net["nodes"], net["conduits"]
    cap = res["storms"][storm]["conduit_capacity"]
    _bgt_background(ax, bgt)
    segs, cols = [], []
    for c in cond:
        a, b = nodes[c["from"]]["xy"], nodes[c["to"]]["xy"]
        segs.append([(a[0] - x0, a[1] - y0), (b[0] - x0, b[1] - y0)])
        cols.append(cap.get(c["id"], {}).get("hours_full_both", 0.0))
    cols = np.array(cols)
    lc = LineCollection(segs, array=np.clip(cols, 0, 2.5), cmap="YlOrRd", linewidths=1.1, zorder=2)
    lc.set_clim(0, 2.5)
    ax.add_collection(lc)
    fl = [f for f in res["storms"][storm]["flooded_nodes"] if not f["suspect_cover"] and f["volume_m3"] >= 1]
    if fl:
        ax.scatter([f["x"] - x0 for f in fl], [f["y"] - y0 for f in fl],
                   s=[30 + 6 * f["volume_m3"] ** 0.8 for f in fl], facecolor="#1f5fbf", edgecolor="white", lw=0.8,
                   alpha=0.9, zorder=4)
    s = res["storms"][storm]
    ax.set_title(f"{storm.upper()} (T={bm.DESIGN_STORMS[storm]['T_years']} yr, {bm.DESIGN_STORMS[storm]['total_mm']} mm)\n"
                 f"{s['flooding']['headline_total_m3']:.0f} m³ flooded ({s['flooding']['share_of_inflow_pct']:.2f}% of inflow) · "
                 f"{s['pipes']['pct_full_at_some_point']:.0f}% of pipes reach full", fontsize=10)
    ax.set_xlim(-800, 800); ax.set_ylim(-800, 800); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    return lc


def main():
    res = json.loads((OUT_DIR / "results.json").read_text())
    net = json.loads((OUT_DIR / "network.json").read_text())
    bgt = fetch_bgt(bm.CENTER[0], bm.CENTER[1], bm.RADIUS_M + 50)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.6))
    for ax, storm in zip(axes, ("bui08", "bui10")):
        lc = _map(ax, storm, res, net, bgt)
    cb = fig.colorbar(lc, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("hours a pipe flowed full (capped at 2.5 h)")
    fig.suptitle("Amsterdam canal ring — SWMM pipe-network rehearsal on open data\n"
                 "grey = buildings, light blue = water; blue circles = flooded manholes (size ∝ volume); "
                 "boundary & terminal sinks drain freely (optimistic: no pump limits) — see caveats", fontsize=11)
    fig.savefig(OUT_DIR / "amsterdam_swmm_maps.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # ---- summary figure -----------------------------------------------------
    fig, axs = plt.subplots(2, 2, figsize=(14, 9))
    ax = axs[0][0]
    for storm, col in (("bui08", "#2a7f62"), ("bui10", "#c1621b")):
        d = bm.DESIGN_STORMS[storm]
        h = bm.design_hyetograph(d["total_mm"], d["duration_min"], d["peak_mm_h"])
        t = np.arange(len(h)) * 5
        ax.step(t, h, where="post", color=col, label=f"{storm.upper()}: {d['total_mm']} mm, peak {d['peak_mm_h']} mm/h")
    ax.set_xlabel("minutes"); ax.set_ylabel("mm/h"); ax.set_title("Design storms (shape approximated)")
    ax.legend(frameon=False)

    ax = axs[0][1]
    st = res["storms"]
    names = [k.upper() for k in st]
    infl = [st[k]["water_balance_m3"]["wet_weather_inflow"] for k in st]
    flood = [st[k]["flooding"]["headline_total_m3"] for k in st]
    ax.bar(names, infl, color="#9fb7cf", label="sewer inflow")
    ax.bar(names, flood, color="#1f5fbf", label="flooded (headline)")
    for i, (a, b) in enumerate(zip(infl, flood)):
        ax.text(i, a, f"{a:,.0f} m³", ha="center", va="bottom", fontsize=9)
        ax.text(i, b, f"{b:,.0f} m³", ha="center", va="bottom", fontsize=9, color="#1f5fbf")
    ax.set_ylabel("m³"); ax.set_title("Inflow vs. flooding by storm"); ax.legend(frameon=False)

    ax = axs[1][0]
    sens = res["sensitivity_bui10"]
    order = ["baseline", "solver_tolerant", "erf_imperv_0.25", "erf_imperv_0.75"]
    vals = [sens[k]["headline_flood_m3"] for k in order]
    ax.barh(order[::-1], vals[::-1], color=["#c1621b" if k == "baseline" else "#d9a483" for k in order[::-1]])
    for i, v in enumerate(vals[::-1]):
        ax.text(v, i, f" {v:,.0f} m³", va="center", fontsize=9)
    ax.set_xlabel("Bui10 flood volume (m³)")
    ax.set_title("Sensitivity of the Bui10 result")

    ax = axs[1][1]; ax.axis("off")
    lines = ["Numerical quality (read before trusting any map)", ""]
    for k, s in st.items():
        n = s["numerics"]
        lines.append(f"{k.upper()}: runoff continuity {n['runoff_continuity_err_pct']:+.2f}% · routing {n['routing_continuity_err_pct']:.2f}%")
        lines.append(f"        non-converging steps {n['pct_steps_not_converging']:.0f}% · min step {n['min_timestep_s']} s")
    lines += ["", "Not calibrated or validated against observed Amsterdam",
              "flooding. Only independent check: Dutch sewers are designed",
              "not to flood at Bui08 → model floods ~0 at Bui08, some at Bui10.",
              "", "Optimistic assumptions: free-drain boundary & sinks (no pump",
              "limits), no dry-weather flow, empty sewer at start.",
              "Pessimistic: every roof assumed connected to the sewer.",
              "Net direction unknown (probably optimistic) — not a bound."]
    ax.text(0.0, 1.0, "\n".join(lines), va="top", fontsize=10, family="monospace")
    fig.suptitle("Amsterdam SWMM Phase 1 — results and how far to trust them", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "amsterdam_swmm_summary.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("saved figures")


if __name__ == "__main__":
    main()
