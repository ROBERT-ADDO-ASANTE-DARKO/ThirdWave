"""
surface_flood_amsterdam.py — Phase 2 of the Amsterdam rehearsal: take the
sewer OVERFLOW that SWMM predicted (Phase 1) and spread it over the real
street surface (AHN LiDAR terrain, BGT buildings as walls, canals as sinks)
with the validated local-inertial solver (inertial2d.py).

Coupling, stated plainly: ONE-WAY. SWMM's flood-rate hydrograph at each
flooded manhole is injected at that manhole's cell. Water that leaves the
sewer never re-enters it (no gully re-entry, no sewer recovery after the
peak), there is no infiltration, no surface-water exchange other than
canals as sinks, and every roof/street is treated the same. So:
  * maximum depths and extents are indicative, not engineering values;
  * water lingers on the surface longer than it would in reality, so
    depth-DURATION figures are upper-end;
  * only the sewer-overflow volume is simulated -- NOT direct rainfall on
    the streets, which would add to it.
Not calibrated or validated against any observed Amsterdam flood.

What was checked rather than assumed:
  * the solver against known solutions (test_inertial2d.py, 5/5 pass);
  * terrain vs sewer ground levels at 2,811 manholes (amsterdam_terrain.py:
    median +1.9 cm, 93% within 10 cm -- independent surveys agree);
  * mass closure per window: injected = stored + canal outflow + window-edge
    outflow (reported, not assumed);
  * injected volume vs SWMM's own reported flood volume;
  * sensitivity to Manning roughness and to grid resolution.

Usage
─────
    python3 surface_flood_amsterdam.py
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.ndimage import distance_transform_edt, maximum, maximum_filter
from shapely.geometry import shape

import amsterdam_terrain as T
from inertial2d import InertialSolver

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "amsterdam_swmm"

STORM = "bui10"
MANNING_N = 0.03            # paved streets (ASSUMPTION; sensitivity 0.02 / 0.05)
CLUSTER_MAX_SPAN_M = 150.0  # complete-linkage: nodes in a window are within this of each other
MARGIN_M = 130.0            # window margin beyond the cluster's flooded nodes
MIN_WINDOW_M = 260.0
T_END_S = 90 * 60
SNAP_TIMES_MIN = (30, 45, 60)
DEPTH_THRESHOLDS = (0.05, 0.10, 0.30, 0.50)


def load_sources() -> list[dict]:
    res = json.loads((OUT_DIR / "results.json").read_text())
    s = res["storms"][STORM]
    series = s["flood_series"]
    out = []
    for f in s["flooded_nodes"]:
        if f["suspect_cover"] or f["node"] not in series:
            continue
        ts = series[f["node"]]
        out.append({"node": f["node"], "x": f["x"], "y": f["y"], "swmm_m3": f["volume_m3"],
                    "t_min": np.array(ts["t_min"]), "rate": np.array(ts["rate_m3s"]),
                    "hydrograph_m3": ts["integrated_m3"]})
    return out


def make_clusters(sources: list[dict]) -> list[list[dict]]:
    if len(sources) == 1:
        return [sources]
    xy = np.array([[s["x"], s["y"]] for s in sources])
    lab = fcluster(linkage(xy, "complete"), t=CLUSTER_MAX_SPAN_M, criterion="distance")
    groups: dict[int, list[dict]] = {}
    for s, l in zip(sources, lab):
        groups.setdefault(int(l), []).append(s)
    return sorted(groups.values(), key=lambda g: -sum(s["swmm_m3"] for s in g))


def coarsen(grid: dict, f: int) -> dict:
    """Aggregate the 1 m grid by an integer factor (majority rule for masks)."""
    if f == 1:
        return {"z": grid["z"], "walls": grid["walls"], "sinks": grid["sinks"], "dx": T.CELL}
    n = grid["z"].shape[0] // f
    def blk(a): return a[: n * f, : n * f].reshape(n, f, n, f)
    z = blk(grid["z"]).mean(axis=(1, 3))
    walls = blk(grid["walls"]).mean(axis=(1, 3)) >= 0.5
    sinks = (blk(grid["sinks"]).mean(axis=(1, 3)) >= 0.5) & ~walls
    return {"z": z, "walls": walls, "sinks": sinks, "dx": T.CELL * f}


def _nearest_open(open_mask: np.ndarray, j: int, i: int, max_r: int) -> tuple[int, int] | None:
    if open_mask[j, i]:
        return j, i
    j0, j1, i0, i1 = max(0, j - max_r), j + max_r + 1, max(0, i - max_r), i + max_r + 1
    sub = open_mask[j0:j1, i0:i1]
    if not sub.any():
        return None
    jj, ii = np.where(sub)
    k = np.argmin((jj + j0 - j) ** 2 + (ii + i0 - i) ** 2)
    return int(jj[k] + j0), int(ii[k] + i0)


def run_window(g: dict, cluster: list[dict], n: float, f: int) -> dict:
    dx = g["dx"]
    ny = g["z"].shape[0]
    xs = [s["x"] for s in cluster]; ys = [s["y"] for s in cluster]
    half_x = max(MIN_WINDOW_M / 2, (max(xs) - min(xs)) / 2 + MARGIN_M)
    half_y = max(MIN_WINDOW_M / 2, (max(ys) - min(ys)) / 2 + MARGIN_M)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    # RD -> cell window, clipped to the AOI square
    jA, iA = int((T.Y1 - (cy + half_y)) / dx), int((cx - half_x - T.X0) / dx)
    jB, iB = int((T.Y1 - (cy - half_y)) / dx), int((cx + half_x - T.X0) / dx)
    j0, j1, i0, i1 = max(0, jA), min(ny, jB), max(0, iA), min(ny, iB)
    z = g["z"][j0:j1, i0:i1]; walls = g["walls"][j0:j1, i0:i1]; canals = g["sinks"][j0:j1, i0:i1]
    edge = np.zeros(z.shape, bool)
    # open window edge, except where the edge is the AOI limit (no data beyond it)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    edge &= ~walls
    open_mask = ~walls & ~canals & ~edge

    srcs = []
    relocated = []
    for s in cluster:
        j = int((T.Y1 - s["y"]) / dx) - j0; i = int((s["x"] - T.X0) / dx) - i0
        cell = _nearest_open(open_mask, j, i, max_r=int(8 / dx) + 1)
        if cell is None:
            log.warning("  node %s has no open cell nearby -- skipped", s["node"])
            continue
        if cell != (j, i):
            relocated.append(round(float(np.hypot(cell[0] - j, cell[1] - i) * dx), 1))
        srcs.append((s, cell))

    solver = InertialSolver(z, dx, n, walls=walls, sinks=canals)
    dur = {th: np.zeros(z.shape) for th in (0.10, 0.30)}
    snaps = {}
    edge_out = 0.0
    t_wall = time.time()
    steps = 0
    while solver.t < T_END_S:
        tm = solver.t / 60.0
        sources = [(c[0], c[1], float(np.interp(tm, s["t_min"], s["rate"], right=0.0))) for s, c in srcs]
        dt = solver.step(sources=sources)
        edge_out += float(solver.h[edge].sum() * dx ** 2)
        solver.h[edge] = 0.0
        for th, d in dur.items():
            d += dt * (solver.h > th)
        for tmin in SNAP_TIMES_MIN:
            if tmin not in snaps and solver.t >= tmin * 60:
                snaps[tmin] = solver.h.astype(np.float16).copy()
        steps += 1
    inj = solver.in_volume
    stored = solver.stored_volume()
    closure = abs(inj - stored - solver.out_volume - edge_out) / max(inj, 1e-9)
    pit = bool((z[open_mask] < -1.0).any())
    return {
        "window": (j0, j1, i0, i1), "n_nodes": len(srcs), "nodes": [s["node"] for s, _ in srcs],
        "injected_m3": round(inj, 2), "swmm_reported_m3": round(sum(s["swmm_m3"] for s in cluster), 1),
        "hydrograph_m3": round(sum(s["hydrograph_m3"] for s in cluster), 1),
        "stored_m3": round(stored, 2), "to_canals_m3": round(solver.out_volume, 2), "to_window_edge_m3": round(edge_out, 2),
        "closure_err": closure, "clipped_m3": solver.clipped_volume,
        "relocated_nodes_m": relocated, "window_has_pit_lt_-1m": pit,
        "steps": steps, "runtime_s": round(time.time() - t_wall, 1),
        "max_h": solver.max_h, "dur10": dur[0.10], "dur30": dur[0.30], "snaps": snaps,
    }


_G: dict | None = None


def _work(args):
    cluster, n, f = args
    return run_window(_G, cluster, n, f)


def exposure(depth_max: np.ndarray, grid: dict) -> dict:
    """Buildings adjacent to flooded street: max depth within 2 cells of each footprint."""
    bgt = grid["bgt"]
    geoms = []
    for k, f in enumerate(bgt["pand"], start=1):
        try:
            g = shape(f["geometry"])
        except Exception:
            continue
        if not g.is_empty:
            geoms.append((g, k))
    ids = rasterio.features.rasterize(geoms, out_shape=depth_max.shape, transform=T.TRANSFORM, fill=0, dtype="int32")
    adj = maximum_filter(depth_max, size=5)
    idx = np.array([k for _, k in geoms])
    mx = np.asarray(maximum(adj, labels=ids, index=idx))
    return {"n_buildings": int(len(idx)),
            **{f"n_adjacent_ge_{int(th*100)}cm": int((mx >= th).sum()) for th in (0.10, 0.30)},
            "max_adjacent_depth_m": round(float(mx.max()), 2)}


def stats(depth: np.ndarray, dx: float) -> dict:
    a = dx * dx
    wet = depth > 0.05
    out = {f"area_ge_{int(th*100)}cm_m2": round(float((depth >= th).sum() * a), 0) for th in DEPTH_THRESHOLDS}
    out["max_depth_m"] = round(float(depth.max()), 3)
    out["p99_depth_wet_m"] = round(float(np.percentile(depth[wet], 99)), 3) if wet.any() else 0.0
    return out


def run_all(grid: dict, sources: list[dict], n: float, f: int, want_maps: bool = False) -> dict:
    g = coarsen(grid, f)
    clusters = make_clusters(sources)
    log.info("[n=%.3f dx=%.0f m] %d clusters (sizes %s)", n, g["dx"], len(clusters), [len(c) for c in clusters])
    depth = np.zeros_like(g["z"]); d10 = np.zeros_like(g["z"]); d30 = np.zeros_like(g["z"])
    per, snaps = [], {}
    # clusters are independent windows -> fork a pool (grid shared copy-on-write)
    global _G
    _G = g
    with mp.get_context("fork").Pool(processes=min(4, len(clusters))) as pool:
        results = pool.map(_work, [(c, n, f) for c in clusters], chunksize=1)
    for k, (c, r) in enumerate(zip(clusters, results)):
        j0, j1, i0, i1 = r["window"]
        depth[j0:j1, i0:i1] = np.maximum(depth[j0:j1, i0:i1], r["max_h"])
        d10[j0:j1, i0:i1] = np.maximum(d10[j0:j1, i0:i1], r["dur10"])
        d30[j0:j1, i0:i1] = np.maximum(d30[j0:j1, i0:i1], r["dur30"])
        if want_maps:
            snaps[k] = {"window": r["window"], "snaps": r["snaps"]}
        log.info("  cluster %d (%d nodes): in %.1f m3 (SWMM %.1f) -> stored %.1f, canals %.1f, edge %.1f | closure %.1e | %s s | pit=%s",
                 k, r["n_nodes"], r["injected_m3"], r["swmm_reported_m3"], r["stored_m3"], r["to_canals_m3"],
                 r["to_window_edge_m3"], r["closure_err"], r["runtime_s"], r["window_has_pit_lt_-1m"])
        per.append({kk: vv for kk, vv in r.items() if kk not in ("max_h", "dur10", "dur30", "snaps")})
    tot = {k: round(sum(p[k] for p in per), 1) for k in ("injected_m3", "swmm_reported_m3", "stored_m3", "to_canals_m3", "to_window_edge_m3")}
    res = {"manning_n": n, "dx_m": g["dx"], "n_clusters": len(clusters), "totals_m3": tot,
           "max_closure_err": max(p["closure_err"] for p in per),
           "max_clipped_m3": max(p["clipped_m3"] for p in per),
           "windows_with_pit": sum(p["window_has_pit_lt_-1m"] for p in per),
           "stats": stats(depth, g["dx"]), "clusters": per}
    if f == 1:
        res["exposure"] = exposure(depth, grid)
        res["duration_area_ge10cm_over_30min_m2"] = round(float((d10 >= 1800).sum() * g["dx"] ** 2), 0)
        res["duration_area_ge10cm_over_60min_m2"] = round(float((d10 >= 3600).sum() * g["dx"] ** 2), 0)
    return res, depth, snaps


def main():
    grid = T.build_grid()
    sources = load_sources()
    log.info("%d flooded manholes, %.0f m3 (hydrograph-integrated %.0f m3)", len(sources),
             sum(s["swmm_m3"] for s in sources), sum(s["hydrograph_m3"] for s in sources))
    out = {"storm": STORM, "terrain_vs_sewer_ground_check": T.ground_level_check(grid["dtm05"]),
           "grid": {"n_cells": int(grid["z"].size), "walls_pct": round(100 * float(grid["walls"].mean()), 1),
                    "canals_pct": round(100 * float(grid["sinks"].mean()), 1), "dtm_holes_filled": grid["n_land_holes_filled"]}}
    base, depth, snaps = run_all(grid, sources, MANNING_N, 1, want_maps=True)
    out["baseline"] = base
    log.info("baseline stats: %s", base["stats"])
    log.info("exposure: %s", base["exposure"])

    # max-depth GeoTIFF (1 m, EPSG:28992)
    tif = OUT_DIR / f"surface_flood_{STORM}_maxdepth.tif"
    with rasterio.open(tif, "w", driver="GTiff", height=depth.shape[0], width=depth.shape[1], count=1, dtype="float32",
                       crs="EPSG:28992", transform=T.TRANSFORM, compress="deflate", predictor=3, nodata=-1.0) as dst:
        dst.write(depth.astype("float32"), 1)
    np.savez_compressed(OUT_DIR / f"surface_flood_{STORM}_snaps.npz",
                        **{f"c{k}_{t}": v["snaps"][t] for k, v in snaps.items() for t in v["snaps"]},
                        **{f"c{k}_window": np.array(v["window"]) for k, v in snaps.items()})

    sens = {}
    for label, n, f in (("manning_0.02", 0.02, 1), ("manning_0.05", 0.05, 1), ("grid_2m", MANNING_N, 2)):
        r, _, _ = run_all(grid, sources, n, f)
        sens[label] = {"stats": r["stats"], "max_closure_err": r["max_closure_err"], "totals_m3": r["totals_m3"]}
        log.info("sensitivity %s: %s", label, r["stats"])
    out["sensitivity"] = sens
    (OUT_DIR / f"surface_flood_{STORM}_results.json").write_text(json.dumps(out, indent=1, default=float))
    log.info("Saved results + GeoTIFF")


if __name__ == "__main__":
    main()
