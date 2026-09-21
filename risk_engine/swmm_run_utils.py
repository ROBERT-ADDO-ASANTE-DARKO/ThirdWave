"""
swmm_run_utils.py — run a SWMM .inp headlessly and parse the .rpt for the
numbers that decide whether a run is TRUSTWORTHY (continuity errors,
non-convergence) before anyone reads its flood results.

A SWMM run that completes is not necessarily a run that's right. The
first Amsterdam build completed in 100 s with a fine-looking flood
summary but 54.7% of routing steps non-converging -- exactly the kind of
result that looks authoritative and isn't. Every run is therefore
summarised with its numerical-quality indicators alongside its
hydraulic results.
"""

from __future__ import annotations

import re
from pathlib import Path

from swmm.toolkit import solver


def run(inp: Path, rpt: Path | None = None, out: Path | None = None) -> Path:
    rpt = rpt or inp.with_suffix(".rpt")
    out = out or inp.with_suffix(".out")
    solver.swmm_run(str(inp), str(rpt), str(out))
    return rpt


def _first_float(pattern: str, text: str, group: int = 1) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(group)) if m else None


def parse_rpt(rpt: Path) -> dict:
    t = Path(rpt).read_text(errors="replace")
    res: dict = {}
    res["runoff_continuity_err_pct"] = _first_float(r"Surface Runoff.*?\n(?:.*\n){0,3}?\s*Continuity Error \(%\) \.+\s+(-?[\d.]+)", t)
    # routing continuity error is the SECOND "Continuity Error (%)" occurrence
    errs = re.findall(r"Continuity Error \(%\) \.+\s+(-?[\d.]+)", t)
    res["runoff_continuity_err_pct"] = float(errs[0]) if errs else None
    res["routing_continuity_err_pct"] = float(errs[1]) if len(errs) > 1 else None
    res["pct_steps_not_converging"] = _first_float(r"% of Steps Not Converging\s*:\s*([\d.]+)", t)
    res["min_timestep_s"] = _first_float(r"Minimum Time Step\s*:\s*([\d.]+)", t)
    res["avg_timestep_s"] = _first_float(r"Average Time Step\s*:\s*([\d.]+)", t)
    res["wet_weather_inflow_m3"] = (_first_float(r"Wet Weather Inflow \.+\s+[\d.]+\s+([\d.]+)", t) or 0) * 1e3
    res["external_outflow_m3"] = (_first_float(r"External Outflow \.+\s+[\d.]+\s+([\d.]+)", t) or 0) * 1e3
    res["flooding_loss_m3"] = (_first_float(r"Flooding Loss \.+\s+[\d.]+\s+([\d.]+)", t) or 0) * 1e3
    res["total_precip_mm"] = _first_float(r"Total Precipitation \.+\s+[\d.]+\s+([\d.]+)", t)
    res["surface_runoff_mm"] = _first_float(r"Surface Runoff \.+\s+[\d.]+\s+([\d.]+)", t)

    # Node Flooding Summary rows: Node Hours Rate Day HH:MM Volume(10^6 ltr) MaxDepth
    flood = []
    i = t.find("Node Flooding Summary")
    if i >= 0:
        for line in t[i:i + 200000].splitlines():
            parts = line.split()
            if len(parts) >= 7 and re.match(r"^[NSO]\d+$|^[A-Za-z_]+\d*$", parts[0]) and re.match(r"^[\d.]+$", parts[1]):
                try:
                    flood.append({"node": parts[0], "hours_flooded": float(parts[1]),
                                  "max_rate_cms": float(parts[2]), "volume_m3": float(parts[5]) * 1e3,
                                  "max_ponded_m": float(parts[6])})
                except ValueError:
                    continue
            if line.strip().startswith("Node Flooding Summary") is False and "Storage Volume Summary" in line:
                break
    res["flooded_nodes"] = flood
    res["n_flooded_nodes"] = len(flood)
    res["flood_volume_sum_m3"] = sum(f["volume_m3"] for f in flood)
    return res


def _table_rows(text: str, title: str, min_tokens: int, stop_titles: tuple[str, ...]) -> list[list[str]]:
    """Rows of a fixed-width SWMM report table that follows `title`."""
    i = text.find(title)
    if i < 0:
        return []
    rows: list[list[str]] = []
    for line in text[i + len(title):].splitlines()[4:]:
        s = line.strip()
        if any(s.startswith(st) for st in stop_titles):
            break
        parts = s.split()
        if len(parts) >= min_tokens and not s.startswith(("-", "*")):
            rows.append(parts)
    return rows


def parse_capacity(rpt: Path) -> dict:
    """Pipe-capacity and surcharge tables (per element)."""
    t = Path(rpt).read_text(errors="replace")
    links = {}
    for p in _table_rows(t, "Link Flow Summary", 8, ("Flow Classification", "Conduit Surcharge", "Pumping")):
        try:
            links[p[0]] = {"max_flow_cms": float(p[2]), "max_velocity": float(p[5]),
                           "max_over_full_flow": float(p[6]), "max_over_full_depth": float(p[7])}
        except ValueError:
            continue
    for p in _table_rows(t, "Conduit Surcharge Summary", 6, ("Analysis begun", "*")):
        try:
            if p[0] in links:
                links[p[0]].update({"hours_full_both": float(p[1]), "hours_above_full_normal_flow": float(p[4]),
                                    "hours_capacity_limited": float(p[5])})
        except ValueError:
            continue
    nodes = {}
    for p in _table_rows(t, "Node Surcharge Summary", 5, ("Node Flooding", "Storage Volume", "Outfall Loading")):
        try:
            nodes[p[0]] = {"hours_surcharged": float(p[2]), "max_height_above_crown_m": float(p[3]),
                           "min_freeboard_m": float(p[4])}
        except ValueError:
            continue
    return {"links": links, "surcharged_nodes": nodes}
