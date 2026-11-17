"""
road_closure_score.py — per-ROAD-SEGMENT closure score, aggregating
route_engine.segments_near_point()'s per-incident view (one row per
active incident) into one row per unique named road -- several incidents,
or several reports at one incident, can all point at the same street, and
an officer deciding whether to close "Ring Road Central" wants one answer
for that road, not one per report.

Closure score = weighted sum of five signals, each normalized to [0, 1]
before weighting, documented here so the weights can be judged rather
than taken on faith (same discipline as report_confidence.py's and
risk_engine/geospatial_vulnerability.py's own weighted composites):

  0.35 x water depth          this event's own evidence -- the worst
                               depth_hi_m among the verified reports
                               touching this segment, capped at 1.5m
                               (roughly top-of-car-window; the upper end
                               of what this project's real citizen photos
                               have actually shown -- see vlm_checks.json).
  0.25 x verified report count independent witnesses at this segment
                               (same diminishing 1/2/3+ scale
                               report_confidence.py uses for cluster size).
  0.15 x road classification  OSM highway tag -- faster/busier road
                               classes score higher because floodwater on
                               a fast road is more dangerous (hydroplaning,
                               a car being swept off a trunk/primary road
                               moving at speed), not because they flood
                               more often.
  0.15 x historical frequency documented past flood events
                               (geo_data.nearby_historical_events) near
                               this segment -- the past, deliberately
                               separate from this event's own depth.
  0.10 x rainfall forecast    near-term (next ~6h) Open-Meteo forecast at
                               this segment, relative to THIS zone's own
                               rainfall_6h_critical_mm threshold (same
                               comparison routers/forecast.py already
                               makes) -- is it about to get worse.

The composite is scaled to 0-100 and bucketed with the SAME 65/45/25
breakpoints and LEVEL_COLOR palette geo_data._score_to_level() and every
area-vulnerability score in this app already use (Low/Moderate/High/Very
High) -- a road's closure urgency is the same KIND of severity axis as a
zone's flood-vulnerability score, unlike report_confidence.py's "how much
evidence backs this report" bands, which are deliberately a different
vocabulary. `level` stays in the output for map coloring.

The officer-facing ACTION (separate from `level`) is a 5-tier set --
Full closure / Emergency vehicles only / Pedestrians only / Monitor / No
action -- chosen by water depth, the only one of the five signals that's
actually a physical passability measurement, not a proxy for one.
Thresholds (DEPTH_MONITOR_M/DEPTH_EMERGENCY_ONLY_M/DEPTH_PEDESTRIAN_ONLY_M/
DEPTH_FULL_CLOSURE_M) extend incident_store.py's existing shallow/moderate/
severe depth bands (0.15m/0.4m) with two more cuts for the two extra tiers
this action set needs beyond that. A sixth action, "One lane restricted,"
was considered and deliberately dropped: it needs real lane-count or
partial-road-width data, and only ~3% of this graph's edges carry OSM's
`lanes` tag -- guessing it for the other 97% would mean fabricating a
recommendation, not deriving one. When no report at this segment has a
depth estimate at all, action falls back to the closure-score `level`
instead (a coarser, 4-tier version of the same mapping, documented in
_ACTION_FROM_LEVEL) -- still real data (report count/road class/history/
rainfall), just without the one signal that would otherwise decide
between "emergency vehicles only" and "pedestrians only."

Advisory only, same "report, don't auto-decide" discipline as everything
else this project derives: an officer still decides whether to actually
close a segment.
"""

from __future__ import annotations

import time

import geo_data
import open_meteo
import route_engine

RAINFALL_CACHE_TTL_S = 1800  # same TTL convention as news_corroboration.py's module-level cache
_rainfall_cache: dict[tuple[float, float], tuple[float, float]] = {}

DEFAULT_CRITICAL_RAINFALL_6H_MM = 50.0  # used only when this point has no zone-specific threshold (extended coverage, or outside all grids)
DEPTH_CAP_M = 1.5

_ROAD_CLASS_SCORE = {
    "motorway": 1.0, "motorway_link": 1.0,
    "trunk": 0.9, "trunk_link": 0.9,
    "primary": 0.75, "primary_link": 0.75,
    "secondary": 0.55, "secondary_link": 0.55,
    "tertiary": 0.4, "tertiary_link": 0.4,
    "unclassified": 0.25, "residential": 0.2, "living_street": 0.15,
    "service": 0.1, "path": 0.05, "footway": 0.05, "pedestrian": 0.05,
}
_DEFAULT_ROAD_CLASS_SCORE = 0.3

# incident_store.py's own shallow/moderate/severe depth bands are 0.15m
# and 0.4m -- reused here, extended with two more cuts (0.6m/1.0m) for
# the two extra action tiers this feature needs beyond those three.
DEPTH_MONITOR_M = 0.15
DEPTH_EMERGENCY_ONLY_M = 0.4
DEPTH_PEDESTRIAN_ONLY_M = 0.6
DEPTH_FULL_CLOSURE_M = 1.0

_NO_ACTION = ("✅", "No action")
_MONITOR = ("⚠️", "Monitor")
_EMERGENCY_ONLY = ("\U0001F691", "Emergency vehicles only")
_PEDESTRIAN_ONLY = ("\U0001F6B6", "Pedestrians only")
_FULL_CLOSURE = ("\U0001F6A7", "Full closure")

# Fallback when no report at this segment has a depth estimate -- coarser
# (4-tier, from the closure_score's own level) since there's no depth
# signal left to separate "emergency vehicles only" from "pedestrians
# only." Still real data, just less of it.
_ACTION_FROM_LEVEL = {
    "Very High": _FULL_CLOSURE,
    "High": _EMERGENCY_ONLY,
    "Moderate": _MONITOR,
    "Low": _NO_ACTION,
}


def _recommended_action(max_depth_hi_m: float | None, level: str) -> tuple[str, str, str]:
    """-> (emoji, action, basis). basis is "depth" when a real depth
    estimate decided it, "score" when it fell back to the composite
    level instead -- surfaced so the UI can say which one it was,
    rather than implying every action came from a hard depth reading."""
    if max_depth_hi_m is None:
        emoji, action = _ACTION_FROM_LEVEL[level]
        return emoji, action, "score"
    if max_depth_hi_m < DEPTH_MONITOR_M:
        emoji, action = _NO_ACTION
    elif max_depth_hi_m < DEPTH_EMERGENCY_ONLY_M:
        emoji, action = _MONITOR
    elif max_depth_hi_m < DEPTH_PEDESTRIAN_ONLY_M:
        emoji, action = _EMERGENCY_ONLY
    elif max_depth_hi_m < DEPTH_FULL_CLOSURE_M:
        emoji, action = _PEDESTRIAN_ONLY
    else:
        emoji, action = _FULL_CLOSURE
    return emoji, action, "depth"


def _road_class_score(highway) -> float:
    if isinstance(highway, list):
        highway = highway[0] if highway else None
    return _ROAD_CLASS_SCORE.get(highway, _DEFAULT_ROAD_CLASS_SCORE)


def _depth_score(depth_hi_m: float | None) -> float:
    if not depth_hi_m:
        return 0.0
    return min(depth_hi_m / DEPTH_CAP_M, 1.0)


def _count_score(n: int) -> float:
    return min(n / 3, 1.0)


def _near_term_rainfall_mm(lat: float, lon: float) -> float | None:
    key = (round(lat, 3), round(lon, 3))
    now = time.time()
    cached = _rainfall_cache.get(key)
    if cached and (now - cached[0]) < RAINFALL_CACHE_TTL_S:
        return cached[1]
    try:
        hourly = open_meteo.fetch_rainfall_forecast(lat, lon)
        near_term = max((h["rolling_6h_mm"] for h in hourly[:6]), default=0.0)
    except Exception:
        return None
    _rainfall_cache[key] = (now, near_term)
    return near_term


def _rainfall_score(lat: float, lon: float) -> tuple[float, float | None]:
    """-> (normalized score, raw near-term mm or None if the forecast
    call failed -- the caller shows the raw figure, the score silently
    contributes 0 on failure rather than erroring the whole row)."""
    near_term_mm = _near_term_rainfall_mm(lat, lon)
    if near_term_mm is None:
        return 0.0, None
    crit_mm = DEFAULT_CRITICAL_RAINFALL_6H_MM
    zone = geo_data.zone_for_point(lon, lat)
    if zone and not zone.get("extended"):
        thresh = geo_data.grid_thresholds().get(zone["id"].replace("RZ-", ""))
        if thresh:
            crit_mm = thresh["rainfall_6h_critical_mm"]
    return min(near_term_mm / crit_mm, 1.0), near_term_mm


def compute(session) -> list[dict]:
    G = route_engine.load_graph()
    incidents = route_engine._active_incidents(session)

    segments: dict[str, dict] = {}
    for inc in incidents:
        for seg in route_engine.segments_near_point(G, inc["lon"], inc["lat"]):
            g = segments.setdefault(seg["name"], {
                "name": seg["name"], "highway": seg["highway"],
                "coords": seg["coords"], "n_edges": seg["n_edges"], "incidents": [],
            })
            g["incidents"].append(inc)

    out = []
    for seg in segments.values():
        incs = seg["incidents"]
        depths = [i["depth_hi_m"] for i in incs if i.get("depth_hi_m") is not None]
        max_depth = max(depths) if depths else None
        rep_lat = sum(i["lat"] for i in incs) / len(incs)
        rep_lon = sum(i["lon"] for i in incs) / len(incs)
        n_historical = len(geo_data.nearby_historical_events(rep_lat, rep_lon))

        depth_s = _depth_score(max_depth)
        report_s = _count_score(len(incs))
        road_s = _road_class_score(seg["highway"])
        hist_s = _count_score(n_historical)
        rain_s, rain_mm = _rainfall_score(rep_lat, rep_lon)

        score_0_100 = round(100 * (
            0.35 * depth_s + 0.25 * report_s + 0.15 * road_s + 0.15 * hist_s + 0.10 * rain_s
        ), 1)
        level = geo_data._score_to_level(score_0_100)
        emoji, action, action_basis = _recommended_action(max_depth, level)

        out.append({
            "name": seg["name"], "highway": seg["highway"], "n_edges": seg["n_edges"], "coords": seg["coords"],
            "closure_score": score_0_100, "level": level,
            "emoji": emoji, "action": action, "action_basis": action_basis,
            "n_verified_reports": len(incs), "incident_ids": [i["id"] for i in incs],
            "max_depth_hi_m": max_depth, "n_nearby_historical_events": n_historical,
            "near_term_rainfall_mm": round(rain_mm, 1) if rain_mm is not None else None,
            "signals": {
                "water_depth": round(depth_s, 2), "report_count": round(report_s, 2),
                "road_classification": round(road_s, 2), "historical_frequency": round(hist_s, 2),
                "rainfall_forecast": round(rain_s, 2),
            },
        })
    return sorted(out, key=lambda r: -r["closure_score"])
