"""
inundation_model.py — Simplified pluvial (rain-on-grid) inundation
approximation, NOT a hydraulic model.

Why not a real hydraulic model: HEC-RAS/SWMM/LISFLOOD-FP style modeling
needs data this project doesn't have -- actual drain/culvert capacities,
channel cross-sections, calibrated Manning's roughness -- and our 30m
Copernicus DEM is too coarse for street-scale hydraulics to be trustworthy.
See project notes / govt_scenario_simulator.py for the same reasoning.

What this IS: a cheap, fast, explainable proxy. Rainfall (mm) is converted
to a surface water depth per pixel, scaled by a land-cover-based runoff
coefficient (impervious surfaces retain more of the rain as surface water
than vegetated ones). That water is then redistributed downhill with a
vectorized cellular-automaton diffusion step -- water moves from a cell to
any lower neighbor each iteration, proportionally to the elevation
difference, until it either drains off the (open) domain boundary or
collects in local topographic depressions. This reproduces the qualitative
behavior real ponding shows (low-lying areas collect water, hills shed it)
without claiming to model flow velocity, timing, or infrastructure
capacity.
"""

from __future__ import annotations

import numpy as np

# Runoff coefficient by ESA WorldCover 2021 class code -- fraction of the
# rainfall depth that stays as surface water available to pond/flow, rather
# than infiltrating. Built-up surfaces shed almost everything; vegetation
# and bare soil absorb more. Water/wetland classes are already saturated.
RUNOFF_COEFF = {
    10: 0.25,  # tree cover
    20: 0.35,  # shrubland
    30: 0.35,  # grassland
    40: 0.35,  # cropland
    50: 0.85,  # built-up
    60: 0.50,  # bare / sparse vegetation
    70: 0.50,  # snow / ice (unused in Accra, kept for completeness)
    80: 1.00,  # permanent water
    90: 1.00,  # herbaceous wetland
    95: 1.00,  # mangroves
    100: 0.50,  # moss / lichen
}
DEFAULT_RUNOFF_COEFF = 0.5

_SHIFTS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
_SHIFT_WEIGHT = [1.0, 1.0, 1.0, 1.0, 1 / 1.41421356, 1 / 1.41421356, 1 / 1.41421356, 1 / 1.41421356]


def runoff_coeff_array(wc_int: np.ndarray) -> np.ndarray:
    arr = np.full(wc_int.shape, DEFAULT_RUNOFF_COEFF, dtype=np.float32)
    for code, c in RUNOFF_COEFF.items():
        arr[wc_int == code] = c
    return arr


def _neighbor(arr: np.ndarray, dy: int, dx: int, fill: float) -> np.ndarray:
    """Value of `arr` shifted so index (i, j) holds arr[i+dy, j+dx].
    Out-of-domain neighbors read as `fill` -- used to make the boundary an
    open drain (fill very low for elevation so water always drains off the
    edge, or 0 for flow arrays so nothing flows in from outside)."""
    h, w = arr.shape
    padded = np.pad(arr, 1, mode="constant", constant_values=fill)
    return padded[1 + dy: 1 + dy + h, 1 + dx: 1 + dx + w]


def _ca_step(dem: np.ndarray, depth: np.ndarray, transfer_rate: float) -> np.ndarray:
    """One downhill-redistribution step. Pulled out of simulate_ponding so
    simulate_ponding_frames can snapshot depth between steps without
    duplicating the update logic."""
    surf = dem + depth
    potentials = []
    for (dy, dx), w in zip(_SHIFTS, _SHIFT_WEIGHT):
        nb_surf = _neighbor(surf, dy, dx, fill=-9999.0)
        diff = np.clip(surf - nb_surf, 0, None)
        potentials.append(transfer_rate * w * diff / 8.0)

    total_potential = sum(potentials)
    scale = np.minimum(1.0, depth / (total_potential + 1e-9))

    new_depth = depth.copy()
    for (dy, dx), potential in zip(_SHIFTS, potentials):
        actual_out = potential * scale
        new_depth -= actual_out
        new_depth += _neighbor(actual_out, -dy, -dx, fill=0.0)
    return np.maximum(new_depth, 0.0)


def simulate_ponding(
    dem: np.ndarray, wc_int: np.ndarray, rainfall_mm: float,
    iterations: int = 250, transfer_rate: float = 0.5,
) -> np.ndarray:
    """Returns a (rows, cols) array of standing-water depth in meters after
    `iterations` steps of downhill redistribution. Domain boundary is an
    open drain (water can leave, matching that this bbox is a padded crop
    of a much larger real terrain, not a closed basin)."""
    dem = dem.astype(np.float64)
    coeff = runoff_coeff_array(wc_int)
    depth = (coeff * (rainfall_mm / 1000.0)).astype(np.float64)
    for _ in range(iterations):
        depth = _ca_step(dem, depth, transfer_rate)
    return depth


def simulate_ponding_frames(
    dem: np.ndarray, wc_int: np.ndarray, rainfall_mm: float,
    iterations: int = 250, n_frames: int = 20, transfer_rate: float = 0.5,
) -> list[np.ndarray]:
    """Same model as simulate_ponding, but returns ~n_frames snapshots of
    depth at evenly spaced steps along the way -- lets the UI play back the
    water spreading/collecting rather than only showing the converged end
    state. This is still just the CA's own iteration order, not a
    physically timed animation -- there is no real-world seconds-per-frame
    correspondence, only "earlier" vs "later" in the redistribution."""
    dem = dem.astype(np.float64)
    coeff = runoff_coeff_array(wc_int)
    depth = (coeff * (rainfall_mm / 1000.0)).astype(np.float64)
    checkpoint_every = max(1, iterations // n_frames)

    frames = [depth.copy()]
    for i in range(1, iterations + 1):
        depth = _ca_step(dem, depth, transfer_rate)
        if i % checkpoint_every == 0 or i == iterations:
            frames.append(depth.copy())
    return frames


def depth_to_rgba(depth: np.ndarray, max_depth_m: float = 1.0, min_visible_m: float = 0.02) -> np.ndarray:
    """Standing water depth -> RGBA overlay: pale cyan (shallow) through
    navy to violet (deep/severe). Anything below min_visible_m is fully
    transparent so the map isn't hazed over with numerical noise."""
    d = np.clip(depth, 0, max_depth_m)
    t = d / max_depth_m  # 0..1

    stops = np.array([
        [173, 230, 244],  # pale cyan -- shallow
        [30, 110, 200],   # blue -- moderate
        [90, 30, 160],    # violet -- severe
    ], dtype=np.float32)
    tt = np.clip(t[..., None] * 2, 0, 2)
    seg1 = np.clip(tt, 0, 1)
    lower = stops[0] * (1 - seg1) + stops[1] * seg1
    seg2 = np.clip(tt - 1, 0, 1)
    upper = stops[1] * (1 - seg2) + stops[2] * seg2
    rgb = np.where(tt <= 1, lower, upper).astype(np.uint8)

    alpha = np.where(d >= min_visible_m, (120 + t * 135), 0).astype(np.uint8)

    rgba = np.zeros((*depth.shape, 4), dtype=np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = alpha
    return rgba
