"""
build_amsterdam_swmm.py — Phase 1 of the Amsterdam hydrological-modelling
rehearsal: build a real EPA SWMM (1D pipe-network hydraulics) model of the
Amsterdam canal-ring sewer system from OPEN data, drive it with the Dutch
standard design storms, and write a runnable .inp file.

Framing (same as prototype_drain_capacity_integration.py): this is a
capability rehearsal on a city that publishes the data, showing what a
real dual-input (fine terrain + real pipe network) model looks like --
NOT a claim about Amsterdam's actual flood risk and NOT about Accra.

Inputs (all open):
  * Pipes + nodes ......... Gemeente Amsterdam / Waternet rioolnetwerk
                            (amsterdam_sewer_fetch.py)
  * Land cover / runoff ... BGT via PDOK, CC0 (amsterdam_bgt_fetch.py)
  * Design storms ......... Dutch standard Bui08 (T=2y) / Bui10 (T=10y)
  * Canal level ........... -0.40 m NAP (Amsterdam's managed water level)

DATA REALITY, found by inspecting rather than assuming:
  1. The API's begin/end node-ID fields are unusable -- ALL 5,434 pipes
     have globalidBeginknoop == globalidEindknoop == the pipe's OWN id.
     Topology is rebuilt geometrically: pipe endpoints are snapped to
     node points within SNAP_TOL_M (98.3% of trunk-pipe endpoints snap
     within 0.5 m; 106/112 of the rest sit on the AOI boundary).
  2. 33% of pipes lack an invert level. The line geometry's Z is the pipe
     CENTRELINE (|Z - bob - radius| < 3 cm for 99.3% of pipes that have
     both), so missing inverts are imputed as Z - radius.
  3. BGT keeps retired objects; they are filtered (see amsterdam_bgt_fetch).

ASSUMPTIONS (each one changes results; none is a measured Amsterdam value
unless stated) -- also written to the output JSON:
  * Design-storm SHAPE is approximated (official totals/durations/peaks,
    symmetric hyetograph); RIONED's official 5-min tables were unreachable.
  * No dry-weather flow: combined sewers also carry wastewater, so real
    pipes have LESS spare capacity than modelled here.
  * Boundary: the AOI cuts the network out of a larger pumped system.
    Cut ends drain freely (best case for drainage) and real pump limits
    are not modelled -- an OPTIMISTIC assumption for that element.
  * Net direction of all assumptions is UNKNOWN, not a clean bound: optimistic
    = free-drain boundary/sinks, no dry-weather flow, empty sewer at start;
    pessimistic = every roof assumed connected to the sewer (some really
    drain to canals). Probably net optimistic; not calibrated.
  * Runoff from every surface goes to the nearest receiving manhole
    (Voronoi assignment); all roofs assumed connected to the sewer.
  * Imperviousness factors per BGT surface type (table below), Horton
    infiltration, Manning n by material -- typical literature values.
  * Empty sewer at storm start (standard for design-storm checks).

Usage
─────
    python3 build_amsterdam_swmm.py
"""

from __future__ import annotations

import glob
import json
import logging
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint, Point, box, shape
from shapely.ops import unary_union, voronoi_diagram
from shapely.strtree import STRtree

from amsterdam_bgt_fetch import fetch_bgt, ATTRIBUTION as BGT_ATTR
from amsterdam_sewer_fetch import fetch_sewer, ATTRIBUTION as SEWER_ATTR

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "amsterdam_swmm"

# ── AOI / conventions ────────────────────────────────────────────────────────
CENTER = (121205.0, 486795.0)     # RD (EPSG:28992), Amsterdam canal ring
RADIUS_M = 800.0
ELEV_OFFSET = 10.0                # SWMM elevations = NAP + 10 (keeps values positive)
CANAL_LEVEL_NAP = -0.40           # Amsterdam managed canal level (verified, see chat/README)
SNAP_TOL_M = 0.5
EDGE_BAND_M = 15.0                # synthetic nodes this close to the AOI edge = boundary

KEEP_TYPES = {"Gemengd riool", "Hemelwaterriool", "Transportriool", "Overstortleiding"}
INLET_NODE_TYPES = {"Gemengde rioolput", "Hemelwaterrioolput"}   # receive surface runoff

# Manning n by material (typical published values; ASSUMPTION)
MANNING = {"PVC": 0.010, "PE": 0.010, "GVK": 0.011, "AC": 0.011, "GY": 0.012,
           "Beton": 0.013, "Metselwerk": 0.016}
MANNING_DEFAULT = 0.013

# Impervious fraction by BGT surface type (ASSUMPTION -- sensitivity-relevant)
IMPERV = {
    "pand": {None: 1.00},
    "wegdeel": {"gesloten verharding": 1.00, "open verharding": 0.85, "half verhard": 0.50,
                "onverhard": 0.00, "_default": 0.85},
    "ondersteunendwegdeel": {"gesloten verharding": 1.00, "open verharding": 0.85, "half verhard": 0.50,
                             "onverhard": 0.00, "groenvoorziening": 0.00, "_default": 0.50},
    "onbegroeidterreindeel": {"gesloten verharding": 1.00, "open verharding": 0.85, "erf": 0.50,
                              "half verhard": 0.50, "zand": 0.00, "onverhard": 0.00, "_default": 0.50},
    "begroeidterreindeel": {"_default": 0.00},
    "overbruggingsdeel": {None: 1.00, "_default": 1.00},
}

# Design storms: official totals / durations / peak intensities (from a
# municipal summary of the RIONED standard storms); SHAPE is approximated.
DESIGN_STORMS = {
    "bui08": {"T_years": 2,  "total_mm": 19.8, "duration_min": 60, "peak_mm_h": 39.6},
    "bui10": {"T_years": 10, "total_mm": 35.7, "duration_min": 45, "peak_mm_h": 75.6},
}
STEP_MIN = 5


def design_hyetograph(total_mm: float, duration_min: int, peak_mm_h: float) -> list[float]:
    """Symmetric hyetograph in mm/h per 5-min step whose total and peak
    intensity match the official values. Shape exponent p is solved so the
    depth matches exactly -- an APPROXIMATION of the true RIONED shape."""
    n = duration_min // STEP_MIN
    c = (n - 1) / 2.0
    h = n / 2.0
    target_sum = total_mm * 60.0 / STEP_MIN / peak_mm_h  # required sum of normalised weights

    def weights(p: float) -> np.ndarray:
        w = np.maximum(0.0, 1.0 - np.abs(np.arange(n) - c) / h) ** p
        return w / w.max()

    lo, hi = 0.05, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if weights(mid).sum() > target_sum:
            lo = mid
        else:
            hi = mid
    w = weights((lo + hi) / 2)
    return (w * peak_mm_h).tolist()


def _radius_m(props: dict) -> float | None:
    if props.get("diameter"):
        return props["diameter"] / 2000.0
    if props.get("hoogte"):
        return props["hoogte"] / 2000.0
    return None


def build_network(pipes_raw: list[dict], nodes_raw: list[dict]) -> dict:
    """Rebuild topology geometrically and return junction/conduit tables."""
    stats: Counter = Counter()
    pipes = [p for p in pipes_raw
             if p["properties"]["typeLeiding"] in KEEP_TYPES and p["properties"]["status"] != "Vervallen"]
    stats["pipes_raw"] = len(pipes_raw)
    stats["pipes_trunk_types"] = len(pipes)

    node_xy = np.array([n["geometry"]["coordinates"][:2] for n in nodes_raw])
    tree = cKDTree(node_xy)
    node_ground = np.array([n["properties"]["maaiveldniveau"] if n["properties"]["maaiveldniveau"] is not None
                            else np.nan for n in nodes_raw], dtype=float)

    # nodes table: real nodes keyed "N<i>", synthetic (unsnapped ends) keyed "S<i>"
    nodes: dict[str, dict] = {}
    synth_index: dict[tuple, str] = {}

    def snap(xy: tuple[float, float]) -> str:
        d, i = tree.query(xy)
        if d <= SNAP_TOL_M:
            key = f"N{i}"
            if key not in nodes:
                props = nodes_raw[i]["properties"]
                nodes[key] = {"xy": tuple(node_xy[i]), "ground": None if np.isnan(node_ground[i]) else float(node_ground[i]),
                              "typeKnoop": props["typeKnoop"], "soort": props["soort"], "synthetic": False,
                              "globalid": props["globalid"]}
            return key
        rk = (round(xy[0] / 0.5), round(xy[1] / 0.5))
        if rk not in synth_index:
            key = f"S{len(synth_index)}"
            synth_index[rk] = key
            # ground level: inverse-distance weighted from 3 nearest REAL nodes with a ground value
            dd, ii = tree.query(xy, k=12)
            vals = [(dist, node_ground[j]) for dist, j in zip(dd, ii) if not np.isnan(node_ground[j])][:3]
            g = (sum(v / max(d_, 1e-3) for d_, v in vals) / sum(1 / max(d_, 1e-3) for d_, v in vals)) if vals else None
            nodes[key] = {"xy": tuple(xy), "ground": g, "typeKnoop": None, "soort": None, "synthetic": True, "globalid": None}
        return synth_index[rk]

    conduits = []
    for p in pipes:
        pr, coords = p["properties"], p["geometry"]["coordinates"]
        if len(coords[0]) < 3:
            stats["skipped_no_z"] += 1
            continue
        rad = _radius_m(pr)
        if pr["vorm"] == "Rechthoekig" and pr.get("hoogte") and pr.get("breedte"):
            rad = pr["hoogte"] / 2000.0
        if rad is None:
            stats["skipped_no_size"] += 1
            continue
        z0, z1 = coords[0][2], coords[-1][2]
        b0, b1 = pr["bobBeginpunt"], pr["bobEindpunt"]
        if b0 is None or b1 is None:
            stats["invert_imputed_from_geometry_z"] += 1
        inv0 = b0 if b0 is not None else z0 - rad
        inv1 = b1 if b1 is not None else z1 - rad
        a = snap(tuple(coords[0][:2]))
        b = snap(tuple(coords[-1][:2]))
        if a == b:
            stats["skipped_self_loop"] += 1
            continue
        length = sum(math.dist(coords[i][:2], coords[i + 1][:2]) for i in range(len(coords) - 1))

        # cross-section
        vorm = pr["vorm"]
        if vorm == "Rechthoekig" and pr.get("hoogte") and pr.get("breedte"):
            xs = ("RECT_CLOSED", pr["hoogte"] / 1000.0, pr["breedte"] / 1000.0)
        elif vorm == "Eivormig" and pr.get("hoogte"):
            xs = ("EGG", pr["hoogte"] / 1000.0, 0.0)
        elif pr.get("diameter"):
            xs = ("CIRCULAR", pr["diameter"] / 1000.0, 0.0)
            if vorm not in ("Rond", None):
                stats["shape_fallback_circular"] += 1
        else:
            xs = ("CIRCULAR", 2 * rad, 0.0)
            stats["shape_fallback_circular"] += 1
        # orient downhill (higher invert -> lower invert); flat pipes keep digitised direction
        if inv1 > inv0:
            a, b, inv0, inv1 = b, a, inv1, inv0
        conduits.append({"id": f"P{len(conduits)}", "from": a, "to": b, "inv_from": inv0, "inv_to": inv1,
                         "length": max(length, 1.0), "xs": xs, "n": MANNING.get(pr["materiaal"], MANNING_DEFAULT),
                         "material": pr["materiaal"], "typeLeiding": pr["typeLeiding"], "globalid": pr["globalid"]})
    stats["conduits"] = len(conduits)
    stats["synthetic_nodes"] = sum(1 for n in nodes.values() if n["synthetic"])
    stats["real_nodes_used"] = sum(1 for n in nodes.values() if not n["synthetic"])
    return {"nodes": nodes, "conduits": conduits, "stats": stats}


def finalize_hydraulics(net: dict) -> None:
    """Junction inverts / depths, boundary outfalls, connectivity fixes."""
    nodes, conduits, stats = net["nodes"], net["conduits"], net["stats"]
    inv_at: dict[str, list[float]] = defaultdict(list)
    links_at: dict[str, list[str]] = defaultdict(list)
    for c in conduits:
        inv_at[c["from"]].append(c["inv_from"]); inv_at[c["to"]].append(c["inv_to"])
        links_at[c["from"]].append(c["id"]); links_at[c["to"]].append(c["id"])
    for k in list(nodes):
        if k not in inv_at:
            del nodes[k]
    for k, nd in nodes.items():
        nd["invert"] = min(inv_at[k])
        nd["n_links"] = len(links_at[k])
        g = nd["ground"]
        if g is None:
            nd["ground"] = nd["invert"] + 2.5
            stats["ground_level_defaulted"] += 1
        depth = nd["ground"] - nd["invert"]
        # A pipe cannot be taller than the soil above it: cover < largest
        # incident pipe height means the ground level and invert disagree
        # (bad data / different reference). Do NOT invent a low ceiling that
        # floods spuriously (the first build "raised" ground to invert+0.5 m
        # and one such node produced 15% of all flood volume). Instead give
        # the node a crown-based depth so the geometry is valid, and FLAG it
        # so it is excluded from headline flood metrics.
        crown = max((max(c["xs"][1], c["xs"][2]) for c in conduits
                     if c["from"] == k or c["to"] == k), default=0.3)
        nd["suspect_cover"] = bool(depth < crown + 0.05)
        if nd["suspect_cover"]:
            stats["suspect_cover_nodes"] += 1
            depth = crown + 0.30
        nd["max_depth"] = depth
    # conduit offsets (relative to junction invert)
    for c in conduits:
        c["off_from"] = max(0.0, c["inv_from"] - nodes[c["from"]]["invert"])
        c["off_to"] = max(0.0, c["inv_to"] - nodes[c["to"]]["invert"])
    net["links_at"] = links_at


def assign_outfalls(net: dict) -> None:
    """Outfalls: (a) real surface-water outlets at the canal level; (b) cut
    boundary ends drain freely; (c) any connected component left with no
    outfall gets one at its lowest node (flagged) so water can leave."""
    nodes, conduits, stats = net["nodes"], net["conduits"], net["stats"]
    cx, cy = CENTER
    for k, nd in nodes.items():
        nd["outfall"] = None
        if nd["soort"] == "Uitlaat":
            nd["outfall"] = "FIXED"
        elif nd["synthetic"] and math.hypot(nd["xy"][0] - cx, nd["xy"][1] - cy) > RADIUS_M - EDGE_BAND_M:
            nd["outfall"] = "FREE"
    # Terminal SINKS: nodes where every incident pipe slopes INTO the node
    # and nothing leaves. In this dataset those are where the gravity network
    # continues through infrastructure that is NOT in the gravity-pipe layer
    # (siphons under canals, pumping-station sumps, pressure mains -- e.g.
    # N2125, a 5 m-deep node at canal level with two 0.8 m pipes in and none
    # out, next to a combined-sewer-overflow chamber). Left closed they fill
    # up and report large unphysical "floods" (first build: 66% of all flood
    # volume from that one node). Treated like the AOI boundary: free drain,
    # which is a BEST-CASE assumption (real pumps have finite capacity), so
    # interior flooding is under-predicted BY THIS ASSUMPTION (net effect of
    # all assumptions is unknown -- see module docstring).
    FLAT = 0.05  # m; flatter than this the digitised direction is arbitrary
    out_deg = defaultdict(int)
    for c in conduits:
        out_deg[c["from"]] += 1
        if abs(c["inv_from"] - c["inv_to"]) <= FLAT:
            out_deg[c["to"]] += 1       # flat pipe: can drain either way
    n_sinks = 0
    for k, nd in nodes.items():
        if nd["outfall"] is None and out_deg[k] == 0:
            nd["outfall"] = "FREE"
            nd["sink"] = True
            n_sinks += 1
    stats["terminal_sinks_made_free_drain"] = n_sinks

    # connected components (undirected)
    adj = defaultdict(set)
    for c in conduits:
        adj[c["from"]].add(c["to"]); adj[c["to"]].add(c["from"])
    seen, comps = set(), []
    for k in nodes:
        if k in seen:
            continue
        stack, comp = [k], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x); stack.extend(adj[x] - seen)
        comps.append(comp)
    n_no_out = 0
    for comp in comps:
        if not any(nodes[k]["outfall"] for k in comp):
            low = min(comp, key=lambda k: nodes[k]["invert"])
            nodes[low]["outfall"] = "FREE"
            n_no_out += 1
    stats["components"] = len(comps)
    stats["components_needing_forced_outfall"] = n_no_out
    stats["outfalls_fixed_canal"] = sum(1 for n in nodes.values() if n["outfall"] == "FIXED")
    stats["outfalls_free"] = sum(1 for n in nodes.values() if n["outfall"] == "FREE")


def build_subcatchments(net: dict, bgt: dict) -> list[dict]:
    """Voronoi cells of receiving manholes x BGT land cover -> subcatchments."""
    nodes = net["nodes"]
    circle = Point(*CENTER).buffer(RADIUS_M)
    inlets = [(k, Point(nd["xy"])) for k, nd in nodes.items()
              if not nd["synthetic"] and nd["typeKnoop"] in INLET_NODE_TYPES and nd["outfall"] is None]
    log.info("%d receiving manholes (inlets) in the model", len(inlets))
    pts = [p for _, p in inlets]
    vor = voronoi_diagram(MultiPoint(pts), envelope=circle.envelope)
    ptree = STRtree(pts)
    cells: dict[str, object] = {}
    for cell in vor.geoms:
        cell = cell.intersection(circle)
        if cell.is_empty:
            continue
        for i in ptree.query(cell):
            if cell.contains(pts[i]) or cell.intersects(pts[i]):
                cells[inlets[i][0]] = cell
                break

    # land polygons with imperviousness weight
    land = []
    for layer, feats in bgt.items():
        if layer == "waterdeel":
            continue
        table = IMPERV[layer]
        for f in feats:
            try:
                g = shape(f["geometry"])
            except Exception:
                continue
            if g.is_empty:
                continue
            fv = f["properties"].get("fysiek_voorkomen") or f["properties"].get("plus_fysiek_voorkomen")
            land.append((g, table.get(fv, table.get("_default", 0.5))))
    ltree = STRtree([g for g, _ in land])
    log.info("%d land-cover polygons (water excluded)", len(land))

    subs = []
    for nid, cell in cells.items():
        area = imperv_area = 0.0
        for i in ltree.query(cell):
            g, w = land[i]
            a = g.intersection(cell).area
            area += a
            imperv_area += a * w
        if area < 20.0:
            continue
        subs.append({"id": f"C{len(subs)}", "outlet": nid, "area_m2": area, "imperv_pct": 100.0 * imperv_area / area})
    net["stats"]["subcatchments"] = len(subs)
    tot = sum(s["area_m2"] for s in subs)
    net["stats"]["catchment_area_ha"] = round(tot / 1e4, 2)
    net["stats"]["catchment_mean_imperv_pct"] = round(sum(s["area_m2"] * s["imperv_pct"] for s in subs) / tot, 1)
    return subs


def write_inp(net: dict, subs: list[dict], storm: str, path: Path) -> None:
    nodes, conduits = net["nodes"], net["conduits"]
    st = DESIGN_STORMS[storm]
    hyet = design_hyetograph(st["total_mm"], st["duration_min"], st["peak_mm_h"])
    end_h = 3  # storm + drain-down
    L: list[str] = []
    L += ["[TITLE]", f";; Amsterdam canal ring -- {storm.upper()} (T={st['T_years']}y) -- open-data SWMM rehearsal", ""]
    L += ["[OPTIONS]", "FLOW_UNITS CMS", "INFILTRATION HORTON", "FLOW_ROUTING DYNWAVE", "LINK_OFFSETS DEPTH",
          "START_DATE 01/01/2000", "START_TIME 00:00:00", "REPORT_START_DATE 01/01/2000", "REPORT_START_TIME 00:00:00",
          f"END_DATE 01/01/2000", f"END_TIME {end_h:02d}:00:00", "SWEEP_START 01/01", "SWEEP_END 12/31",
          "WET_STEP 00:01:00", "DRY_STEP 00:05:00", "ROUTING_STEP 00:00:05", "REPORT_STEP 00:01:00",
          "ALLOW_PONDING NO", "INERTIAL_DAMPING PARTIAL", "NORMAL_FLOW_LIMITED BOTH", "FORCE_MAIN_EQUATION H-W",
          "VARIABLE_STEP 0.75", "LENGTHENING_STEP 00:00:20", "MIN_SURFAREA 1.167", "MAX_TRIALS 8",
          "HEAD_TOLERANCE 0.0015", "MINIMUM_STEP 0.5", "THREADS 4", ""]
    L += ["[RAINGAGES]", ";;Name Format Interval SCF Source", f"RG1 INTENSITY 0:05 1.0 TIMESERIES {storm}", ""]
    L += ["[TIMESERIES]", f";; {storm}: official total/duration/peak, APPROXIMATED symmetric shape (mm/h)"]
    t = 0
    for v in [0.0] + hyet + [0.0]:
        L.append(f"{storm} {t // 60}:{t % 60:02d} {v:.3f}")
        t += STEP_MIN
    L += [f"{storm} {(t) // 60}:{t % 60:02d} 0.0", ""]
    L += ["[SUBCATCHMENTS]", ";;Name Raingage Outlet Area(ha) %Imperv Width Slope CurbLen"]
    for s in subs:
        ha = s["area_m2"] / 1e4
        width = max(s["area_m2"] / 50.0, 5.0)     # ~50 m overland flow length
        L.append(f"{s['id']} RG1 {s['outlet']} {ha:.5f} {s['imperv_pct']:.1f} {width:.2f} 0.5 0")
    L += ["", "[SUBAREAS]", ";;Sub Nimp Nperv Simp Sperv %Zero RouteTo"]
    L += [f"{s['id']} 0.015 0.15 0.5 3.0 25 OUTLET" for s in subs]
    L += ["", "[INFILTRATION]", ";;Sub MaxRate MinRate Decay DryTime MaxInfil"]
    L += [f"{s['id']} 25 5 4 7 0" for s in subs]
    # SWMM ERROR 141: an outfall may have exactly ONE inlet link and no outlet
    # link. Outfall-designated nodes that satisfy that are written directly;
    # all others (multiple links, or the upstream end of a link) stay ordinary
    # junctions and get a 1 m dummy conduit to a dedicated outfall node --
    # found by actually running SWMM on the first build (12 such nodes).
    by_id = {c["id"]: c for c in conduits}
    direct, dummy = set(), []
    for k, nd in nodes.items():
        if not nd["outfall"]:
            continue
        lk = net["links_at"][k]
        if len(lk) == 1 and by_id[lk[0]]["to"] == k:
            direct.add(k)
        else:
            dummy.append(k)
    net["stats"]["outfalls_direct"] = len(direct)
    net["stats"]["outfalls_via_dummy_conduit"] = len(dummy)

    L += ["", "[JUNCTIONS]", ";;Name Elev MaxDepth InitDepth SurDepth Aponded"]
    for k, nd in nodes.items():
        if k not in direct:
            L.append(f"{k} {nd['invert'] + ELEV_OFFSET:.3f} {nd['max_depth']:.3f} 0 0 0")
    L += ["", "[OUTFALLS]", ";;Name Elev Type Stage Gated"]

    def _outfall_line(name: str, elev: float, kind: str) -> str:
        if kind == "FIXED":
            return f"{name} {elev:.3f} FIXED {CANAL_LEVEL_NAP + ELEV_OFFSET:.3f} YES"
        return f"{name} {elev:.3f} FREE NO"

    for k in direct:
        L.append(_outfall_line(k, nodes[k]["invert"] + ELEV_OFFSET, nodes[k]["outfall"]))
    for k in dummy:
        L.append(_outfall_line(f"O_{k}", nodes[k]["invert"] + ELEV_OFFSET - 0.05, nodes[k]["outfall"]))
    L += ["", "[CONDUITS]", ";;Name From To Length Rough InOff OutOff InitFlow MaxFlow"]
    for c in conduits:
        L.append(f"{c['id']} {c['from']} {c['to']} {c['length']:.2f} {c['n']:.4f} {c['off_from']:.3f} {c['off_to']:.3f} 0 0")
    for k in dummy:
        L.append(f"D_{k} {k} O_{k} 1.0 0.013 0 0 0 0")
    L += ["", "[XSECTIONS]", ";;Link Shape Geom1 Geom2 Geom3 Geom4 Barrels"]
    for c in conduits:
        shp, g1, g2 = c["xs"]
        L.append(f"{c['id']} {shp} {g1:.3f} {g2:.3f} 0 0 1")
    for k in dummy:
        big = max((max(by_id[l]["xs"][1], by_id[l]["xs"][2]) for l in net["links_at"][k]), default=1.0)
        L.append(f"D_{k} CIRCULAR {max(big, 0.4):.3f} 0 0 0 1")
    L += ["", "[REPORT]", "INPUT NO", "CONTROLS NO", "SUBCATCHMENTS NONE", "NODES NONE", "LINKS NONE", ""]
    L += ["[COORDINATES]", ";;Node X Y"] + [f"{k} {nd['xy'][0]:.2f} {nd['xy'][1]:.2f}" for k, nd in nodes.items()]
    path.write_text("\n".join(L) + "\n")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    x, y = CENTER
    pipes_raw, nodes_raw = fetch_sewer(x, y, RADIUS_M)
    bgt = fetch_bgt(x, y, RADIUS_M + 50)

    net = build_network(pipes_raw, nodes_raw)
    finalize_hydraulics(net)
    assign_outfalls(net)
    subs = build_subcatchments(net, bgt)

    for storm in DESIGN_STORMS:
        write_inp(net, subs, storm, OUT_DIR / f"amsterdam_{storm}.inp")

    qa = {
        "aoi": {"center_rd": CENTER, "radius_m": RADIUS_M},
        "sources": {"sewer": SEWER_ATTR, "land_cover": BGT_ATTR},
        "network_stats": dict(net["stats"]),
        "design_storms": DESIGN_STORMS,
        "imperviousness_factors": IMPERV,
        "manning_n": MANNING, "manning_default": MANNING_DEFAULT,
        "canal_level_nap_m": CANAL_LEVEL_NAP, "elev_offset_m": ELEV_OFFSET,
        "assumptions": ["design-storm shape approximated", "no dry-weather flow", "cut-boundary drains freely, pumps not modelled",
                        "nearest-manhole runoff assignment, all roofs connected", "empty sewer at start"],
    }
    (OUT_DIR / "model_qa.json").write_text(json.dumps(qa, indent=2, default=str))
    (OUT_DIR / "network.json").write_text(json.dumps({
        "nodes": {k: {kk: vv for kk, vv in v.items()} for k, v in net["nodes"].items()},
        "conduits": net["conduits"], "subcatchments": subs}, default=str))
    log.info("Model stats: %s", json.dumps(dict(net["stats"]), indent=1))
    log.info("Wrote INP files + QA to %s", OUT_DIR)


if __name__ == "__main__":
    main()
