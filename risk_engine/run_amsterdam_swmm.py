"""
run_amsterdam_swmm.py — Phase 1 runner: execute the Amsterdam SWMM model
(built by build_amsterdam_swmm.py) for the Dutch standard design storms,
extract pipe-capacity / surcharge / flooding results, and stress-test
them against the assumptions that matter most.

Output: data/amsterdam_swmm/results.json  (also the hand-off for Phase 2:
per-node flood volumes AND flood-rate time series, which is what a surface
flood-spreading step needs).

What "trustworthy" means here, stated up front because the first builds
taught it the hard way:
  * A run that COMPLETES is not a run that is RIGHT. Every result carries
    its numerical-quality indicators (continuity error, % non-converging
    steps) -- non-convergence stays high (~35-55%) because the network is
    flat with many small-diameter pipes; total flood volume was shown to be
    insensitive to solver settings, the fine spatial pattern less so.
  * Node flooding is reported EXCLUDING nodes flagged suspect_cover (source
    ground level and pipe invert disagree -- data error, not hydraulics).
  * "Max flow / full flow" is NOT used as a sizing indicator: in a network
    this flat, slope-based full-flow capacity is ill-defined. Surcharge
    duration, freeboard and actual flooding are used instead.
  * Not calibrated or validated against any observed Amsterdam flooding.
    The one independent plausibility check is qualitative: Dutch sewers are
    designed to not flood at Bui08 (T=2y); the model does not (5 m3 of
    ~30,000 m3), and does begin to flood at Bui10 (T=10y).

Sensitivity runs (Bui10): solver tolerances; imperviousness of 'erf'
(private yards, the single most numerous and least certain BGT class).

Usage
─────
    python3 run_amsterdam_swmm.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import numpy as np

import build_amsterdam_swmm as bm
from swmm_run_utils import run, parse_rpt, parse_capacity

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "amsterdam_swmm"
TMP = Path("/tmp/amsterdam_sens")


def _nodes() -> dict:
    return json.loads((OUT_DIR / "network.json").read_text())["nodes"]


def summarize(inp: Path, storm: str, nodes: dict, with_series: bool = False) -> dict:
    t0 = time.time()
    rpt = run(inp)
    r = parse_rpt(rpt)
    cap = parse_capacity(rpt)
    runtime = round(time.time() - t0)

    flooded = []
    for f in r["flooded_nodes"]:
        nd = nodes.get(f["node"])
        if not nd:
            continue
        flooded.append({**f, "x": nd["xy"][0], "y": nd["xy"][1], "typeKnoop": nd["typeKnoop"],
                        "ground_nap_m": nd["ground"], "invert_nap_m": nd["invert"],
                        "suspect_cover": bool(nd.get("suspect_cover"))})
    headline = [f for f in flooded if not f["suspect_cover"]]
    vol = np.array([f["volume_m3"] for f in headline]) if headline else np.array([0.0])
    order = np.argsort(-vol)
    cum = np.cumsum(vol[order]) / max(vol.sum(), 1e-9)

    links = cap["links"]
    real = {k: v for k, v in links.items() if not k.startswith("D_")}
    hrs_full = np.array([v.get("hours_full_both", 0.0) for v in real.values()])
    sur_nodes = cap["surcharged_nodes"]
    tight = [n for n, v in sur_nodes.items() if v["min_freeboard_m"] <= 0.30]

    out = {
        "storm": storm, "runtime_s": runtime,
        "numerics": {k: r[k] for k in ("runoff_continuity_err_pct", "routing_continuity_err_pct",
                                       "pct_steps_not_converging", "min_timestep_s", "avg_timestep_s")},
        "rainfall_mm": r["total_precip_mm"], "runoff_mm": r["surface_runoff_mm"],
        "water_balance_m3": {"wet_weather_inflow": r["wet_weather_inflow_m3"],
                             "external_outflow": r["external_outflow_m3"], "flooding_loss": r["flooding_loss_m3"]},
        "flooding": {
            "n_nodes_reported": len(flooded), "n_suspect_cover_excluded": len(flooded) - len(headline),
            "headline_total_m3": round(float(vol.sum()), 1),
            "n_nodes_ge_1m3": int((vol >= 1).sum()), "n_nodes_ge_10m3": int((vol >= 10).sum()),
            "share_of_inflow_pct": round(100 * float(vol.sum()) / max(r["wet_weather_inflow_m3"], 1), 2),
            "concentration_top1_pct": round(100 * float(cum[0]), 1) if len(cum) else 0,
            "concentration_top5_pct": round(100 * float(cum[min(5, len(cum)) - 1]), 1) if len(cum) else 0,
            "concentration_top10_pct": round(100 * float(cum[min(10, len(cum)) - 1]), 1) if len(cum) else 0,
        },
        "pipes": {
            "n_conduits": len(real),
            "n_full_at_some_point": int((hrs_full > 0).sum()),
            "pct_full_at_some_point": round(100 * float((hrs_full > 0).mean()), 1),
            "n_full_over_1h": int((hrs_full > 1.0).sum()),
        },
        "nodes_surcharged": {"n_surcharged": len(sur_nodes), "n_freeboard_le_0.3m": len(tight)},
        "flooded_nodes": sorted(flooded, key=lambda f: -f["volume_m3"]),
        "conduit_capacity": real,
    }
    if with_series:
        out["flood_series"] = _flood_series(inp, [f for f in headline if f["volume_m3"] >= 1])
    return out


def _flood_series(inp: Path, node_rows: list[dict]) -> dict:
    """Flood-rate (m3/s) time series for the nodes that flooded -- the hand-off
    a surface-spreading model needs.

    SWMM only writes time series to the binary output for elements listed in
    the [REPORT] section (the model ships with NODES NONE to keep the text
    report small; the first attempt silently returned an empty output --
    'n nodes in output: 0' -- and this function swallowed the error).
    So: pass 2 re-runs the same model with NODES = the flooded nodes, then
    integrates each hydrograph and checks it against SWMM's own reported
    flood volume for that node."""
    from pyswmm import Output
    from swmm.toolkit.shared_enum import NodeAttribute
    ids = [f["node"] for f in node_rows]
    if not ids:
        return {}
    TMP.mkdir(exist_ok=True)
    txt = inp.read_text()
    lines = ["NODES " + " ".join(ids[i:i + 8]) for i in range(0, len(ids), 8)]
    assert "NODES NONE" in txt
    txt = txt.replace("NODES NONE", "\n".join(lines))
    inp2 = TMP / f"{inp.stem}_series.inp"
    inp2.write_text(txt)
    run(inp2)
    series = {}
    with Output(str(inp2.with_suffix(".out"))) as o:
        for f in node_rows:
            nid = f["node"]
            ts = o.node_series(nid, NodeAttribute.FLOODING_LOSSES)
            times = list(ts.keys())
            t_min = [(t - times[0]).total_seconds() / 60.0 for t in times]
            rate = [float(v) for v in ts.values()]
            dt = (t_min[1] - t_min[0]) * 60.0 if len(t_min) > 1 else 60.0
            series[nid] = {"t_min": t_min, "rate_m3s": rate,
                           "integrated_m3": round(sum(rate) * dt, 1), "swmm_reported_m3": f["volume_m3"]}
    return series


def sensitivity(storm: str, nodes: dict) -> dict:
    TMP.mkdir(exist_ok=True)
    base_inp = OUT_DIR / f"amsterdam_{storm}.inp"
    res = {}

    # (a) solver tolerances
    txt = base_inp.read_text()
    for k, v in {"MAX_TRIALS": "30", "HEAD_TOLERANCE": "0.005", "MIN_SURFAREA": "2.5",
                 "INERTIAL_DAMPING": "FULL", "LENGTHENING_STEP": "00:00:10"}.items():
        txt = re.sub(rf"^{k}\s+.*$", f"{k} {v}", txt, flags=re.M)
    inp = TMP / f"{storm}_solver.inp"; inp.write_text(txt)
    res["solver_tolerant"] = _brief(summarize(inp, storm, nodes))

    # (b,c) imperviousness of 'erf' (private yards)
    x, y = bm.CENTER
    pipes_raw, nodes_raw = bm.fetch_sewer(x, y, bm.RADIUS_M)
    bgt = bm.fetch_bgt(x, y, bm.RADIUS_M + 50)
    net = bm.build_network(pipes_raw, nodes_raw); bm.finalize_hydraulics(net); bm.assign_outfalls(net)
    tbl = bm.IMPERV["onbegroeidterreindeel"]; orig = tbl["erf"]
    for label, erf in (("erf_imperv_0.25", 0.25), ("erf_imperv_0.75", 0.75)):
        tbl["erf"] = erf
        subs = bm.build_subcatchments(net, bgt)
        inp = TMP / f"{storm}_{label}.inp"
        bm.write_inp(net, subs, storm, inp)
        res[label] = _brief(summarize(inp, storm, nodes))
    tbl["erf"] = orig
    return res


def _brief(s: dict) -> dict:
    return {"headline_flood_m3": s["flooding"]["headline_total_m3"], "n_nodes_ge_10m3": s["flooding"]["n_nodes_ge_10m3"],
            "share_of_inflow_pct": s["flooding"]["share_of_inflow_pct"],
            "routing_continuity_err_pct": s["numerics"]["routing_continuity_err_pct"],
            "pct_steps_not_converging": s["numerics"]["pct_steps_not_converging"],
            "pct_pipes_full": s["pipes"]["pct_full_at_some_point"]}


def main(skip_sensitivity: bool = False):
    nodes = _nodes()
    results = {"model": json.loads((OUT_DIR / "model_qa.json").read_text()), "storms": {}}
    for storm in bm.DESIGN_STORMS:
        log.info("=== %s ===", storm)
        results["storms"][storm] = summarize(OUT_DIR / f"amsterdam_{storm}.inp", storm, nodes, with_series=True)
        s = results["storms"][storm]
        log.info("  flood %.0f m3 (%.2f%% of inflow), %d nodes >=10 m3 | %.1f%% pipes full | continuity %.2f%% | non-converging %.0f%%",
                 s["flooding"]["headline_total_m3"], s["flooding"]["share_of_inflow_pct"], s["flooding"]["n_nodes_ge_10m3"],
                 s["pipes"]["pct_full_at_some_point"], s["numerics"]["routing_continuity_err_pct"],
                 s["numerics"]["pct_steps_not_converging"])
    prev = OUT_DIR / "results.json"
    if skip_sensitivity and prev.exists():
        results["sensitivity_bui10"] = json.loads(prev.read_text())["sensitivity_bui10"]
        log.info("=== sensitivity (bui10): reusing previous results ===")
    else:
        log.info("=== sensitivity (bui10) ===")
        results["sensitivity_bui10"] = sensitivity("bui10", nodes)
    results["sensitivity_bui10"]["baseline"] = _brief(results["storms"]["bui10"])
    for k, v in results["sensitivity_bui10"].items():
        log.info("  %-18s flood %.0f m3 | >=10m3 nodes %d | continuity %.2f%% | non-conv %.0f%%",
                 k, v["headline_flood_m3"], v["n_nodes_ge_10m3"], v["routing_continuity_err_pct"], v["pct_steps_not_converging"])
    results["prior_finding_closed_sinks_bui08"] = {
        "note": "First build left terminal sinks closed (no outlet): Bui08 flood volume was ~3,000 m3, 66% from ONE node "
                "(N2125, a 5 m-deep siphon-like dead end at canal level). Treated as a modelling artifact, not a flood; "
                "sinks now drain freely (an OPTIMISTIC assumption: real pumps have finite capacity).",
        "closed_sinks_bui08_flood_m3": 3001, "closed_sinks_top1_node_share_pct": 66.1}
    (OUT_DIR / "results.json").write_text(json.dumps(results, default=float))
    log.info("Saved -> %s", OUT_DIR / "results.json")


if __name__ == "__main__":
    import sys
    main(skip_sensitivity="--skip-sensitivity" in sys.argv)
