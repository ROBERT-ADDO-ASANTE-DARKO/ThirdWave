
"""
amsterdam_terrain.py — the 1 m surface-flooding grid for the Amsterdam AOI,
from real open data, plus an INDEPENDENT consistency check of it.

  bed elevation ... AHN 0.5 m bare-earth DTM (CC0, PDOK), block-averaged to 1 m
  buildings ....... BGT `pand` polygons -> WALLS. AHN's DTM has buildings
                    removed (ground interpolated underneath), so without walls
                    water would flow straight through them.
  canals .......... BGT `waterdeel` -> SINKS at the managed canal level. Cells
                    under bridge decks (`overbruggingsdeel`) are NOT sinks:
                    the deck is a street surface that water can flow on.

Independent check (why it is here): the sewer dataset records a ground level
(maaiveldniveau, m NAP) for each manhole -- a different agency, a different
survey, a different method from AHN's airborne LiDAR. If the two disagree
systematically the sewer network and the terrain are not on the same
vertical footing and any pipe->surface coupling is suspect. The comparison
is computed and stored, not assumed.

AHN tile note: the AOI straddles two 5 x 6.25 km sheets (the northern edge
is beyond y = 487,500), so windows are mosaicked from whichever sheets the
kaartbladindex says intersect. AHN's nodata is float32-max, not negative
(see explore_ahn_amsterdam_rotterdam.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import rasterio.windows
import requests
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape

import build_amsterdam_swmm as bm
from amsterdam_bgt_fetch import fetch_bgt

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
CACHE = HERE / "cache" / "amsterdam_terrain"
TILE_BASE = "https://service.pdok.nl/rws/ahn/atom/downloads/dtm_05m"
HALF = 850.0                       # AOI square half-width (matches the cached BGT extent)
CELL = 1.0                         # m, flood-grid resolution
CANAL_Z = bm.CANAL_LEVEL_NAP
X0, Y1 = bm.CENTER[0] - HALF, bm.CENTER[1] + HALF   # top-left corner (RD)
N = int(2 * HALF / CELL)
TRANSFORM = from_origin(X0, Y1, CELL, CELL)


def _tile_index() -> list[dict]:
    f = CACHE / "kaartbladindex_dtm05.json"
    CACHE.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text(requests.get(f"{TILE_BASE}/kaartbladindex.json", timeout=60).text)
    return json.loads(f.read_text())["features"]


def read_dtm_05m() -> np.ndarray:
    """AOI-square DTM at 0.5 m (NaN = no data), mosaicked across AHN sheets."""
    cache = CACHE / "dtm05_aoi.npy"
    if cache.exists():
        return np.load(cache)
    n05 = int(2 * HALF / 0.5)
    out = np.full((n05, n05), np.nan, dtype=np.float32)
    left, right, bottom, top = X0, X0 + 2 * HALF, Y1 - 2 * HALF, Y1
    for f in _tile_index():
        xs = [c[0] for c in f["geometry"]["coordinates"][0]]
        ys = [c[1] for c in f["geometry"]["coordinates"][0]]
        tl, tr, tb, tt = min(xs), max(xs), min(ys), max(ys)
        if tr <= left or tl >= right or tt <= bottom or tb >= top:
            continue
        name = f["properties"]["kaartbladNr"]
        log.info("  reading AHN sheet %s", name)
        with rasterio.open(f"/vsicurl/{TILE_BASE}/{name}.tif") as src:
            # overlap of the AOI square with this sheet, in RD metres
            ol, orr, ob, ot = max(left, tl), min(right, tr), max(bottom, tb), min(top, tt)
            win = rasterio.windows.from_bounds(ol, ob, orr, ot, src.transform)
            win = win.round_offsets().round_lengths()
            arr = src.read(1, window=win).astype(np.float32)
            if src.nodata is not None:
                arr[np.isclose(arr, src.nodata, rtol=1e-3)] = np.nan
        r0 = int(round((top - ot) / 0.5)); c0 = int(round((ol - left) / 0.5))
        h, w = arr.shape
        out[r0:r0 + h, c0:c0 + w] = arr[: n05 - r0, : n05 - c0][: out.shape[0] - r0, : out.shape[1] - c0]
    np.save(cache, out)
    return out


def build_grid() -> dict:
    """1 m grid: z, walls, sinks, plus bookkeeping masks."""
    dtm05 = read_dtm_05m()
    blk = dtm05.reshape(N, 2, N, 2)
    valid_frac = np.isfinite(blk).mean(axis=(1, 3))
    z = np.nanmean(np.where(np.isfinite(blk), blk, np.nan), axis=(1, 3)).astype(np.float64)
    z[valid_frac < 0.5] = np.nan

    bgt = fetch_bgt(bm.CENTER[0], bm.CENTER[1], HALF)

    def raster(layer: str) -> np.ndarray:
        geoms = []
        for f in bgt[layer]:
            try:
                g = shape(f["geometry"])
            except Exception:
                continue
            if not g.is_empty:
                geoms.append((g, 1))
        if not geoms:
            return np.zeros((N, N), bool)
        return rasterio.features.rasterize(geoms, out_shape=(N, N), transform=TRANSFORM, fill=0, dtype="uint8").astype(bool)

    buildings = raster("pand")
    water = raster("waterdeel")
    bridge = raster("overbruggingsdeel")
    sinks = water & ~bridge & ~buildings
    walls = buildings

    # fill DTM holes (not water, not building) from the nearest valid ground;
    # water cells sit at the canal level
    land_hole = np.isnan(z) & ~sinks & ~walls
    valid = np.isfinite(z) & ~sinks & ~walls
    if valid.any() and land_hole.any():
        idx = distance_transform_edt(~valid, return_distances=False, return_indices=True)
        filled = z[tuple(idx)]
        z = np.where(land_hole, filled, z)
    z[sinks] = CANAL_Z
    z[walls & np.isnan(z)] = 0.0
    z[np.isnan(z)] = 0.0
    return {"z": z, "walls": walls, "sinks": sinks, "bridge": bridge, "n_land_holes_filled": int(land_hole.sum()),
            "dtm05": dtm05, "bgt": bgt}


def xy_to_cell(x: float, y: float) -> tuple[int, int]:
    return int((Y1 - y) / CELL), int((x - X0) / CELL)


def cell_center(j: int, i: int) -> tuple[float, float]:
    return X0 + (i + 0.5) * CELL, Y1 - (j + 0.5) * CELL


def ground_level_check(dtm05: np.ndarray) -> dict:
    """Sewer maaiveldniveau vs AHN DTM at the same manhole (independent surveys)."""
    nodes = json.loads((HERE / "data" / "amsterdam_swmm" / "network.json").read_text())["nodes"]
    diffs = []
    for nd in nodes.values():
        if nd["synthetic"] or nd.get("suspect_cover") or nd["ground"] is None:
            continue
        x, y = nd["xy"]
        r, c = int((Y1 - y) / 0.5), int((x - X0) / 0.5)
        if 0 <= r < dtm05.shape[0] and 0 <= c < dtm05.shape[1]:
            v = dtm05[r, c]
            if np.isfinite(v):
                diffs.append(nd["ground"] - float(v))
    d = np.array(diffs)
    return {"n": int(len(d)), "median_m": round(float(np.median(d)), 3), "mean_m": round(float(d.mean()), 3),
            "p05_m": round(float(np.percentile(d, 5)), 3), "p95_m": round(float(np.percentile(d, 95)), 3),
            "pct_within_10cm": round(100 * float((np.abs(d) <= 0.10).mean()), 1),
            "pct_within_25cm": round(100 * float((np.abs(d) <= 0.25).mean()), 1),
            "note": "sewer maaiveldniveau minus AHN DTM at the same manhole; independent surveys"}


if __name__ == "__main__":
    g = build_grid()
    print("grid", g["z"].shape, "| walls %.1f%% | sinks %.1f%% | DTM holes filled: %d" % (
        100 * g["walls"].mean(), 100 * g["sinks"].mean(), g["n_land_holes_filled"]))
    print("z (land) range: %.2f .. %.2f m NAP" % (g["z"][~g["sinks"] & ~g["walls"]].min(), g["z"][~g["sinks"] & ~g["walls"]].max()))
    print(json.dumps(ground_level_check(g["dtm05"]), indent=1))
