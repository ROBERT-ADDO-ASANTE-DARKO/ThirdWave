"""
explore_usgs_lpc_boston.py — real USGS 3DEP LiDAR (raw classified point
cloud, QL1, ~17.7 pts/m2 -- comparable density to AHN) for downtown
Boston, rasterized into DTM (ground-classified points) and a building
height layer (building-classified points minus local ground), as the US
counterpart to explore_ahn_amsterdam_rotterdam.py's Netherlands test.

Unlike AHN (which ships precomputed DTM/DSM rasters), USGS 3DEP's staged
1m product here is DTM-only -- no DSM raster exists for this project, so
this script rasterizes the actual classified point cloud itself instead.
That turns out to be an advantage, not a workaround: LAS standard
classification (class 2 = ground, class 6 = building -- ASPRS codes)
lets building height be computed directly from points explicitly
classified as buildings, rather than AHN's simple "highest return"
DSM-minus-DTM, which can't distinguish a building roof from a tall tree.

Tile discovery: USGS 3DEP LPC tiles use MGRS-style ids ("19TCG330690"),
a completely different numbering scheme from the same project's 1km DEM
grid ("x33y469") -- confirmed the hard way (first download grabbed a
tile ~100km south of Boston by wrongly assuming the two schemes lined
up). The reliable way: each project publishes a .vpc (STAC-like virtual
point cloud index, one Feature per tile with a real bbox) -- filter that
for the tile whose bbox actually contains the target point, don't guess
from filename substrings.

  https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/LPC/Projects/<project>/<subproject>/<subproject>.vpc

Also note: rockyweb.usgs.gov resets HTTP/2 connections mid-transfer on
large files (hit a real "curl: (92) HTTP/2 stream" error on the first
attempt) -- downloads here use --http1.1.

License: USGS 3DEP data is public domain (no restriction at all, same
as AHN's CC0 -- unlike FABDEM's CC BY-NC-SA or GBA's CC BY-NC).

Usage
─────
    python3 explore_usgs_lpc_boston.py --laz /tmp/boston_downtown.laz
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import laspy

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "usgs_lpc_explore"

# ASPRS LAS classification codes
CLASS_GROUND = 2
CLASS_BUILDING = 6

CELL_M = 1.0  # rasterize at 1m -- still 900x finer per-pixel than CopDEM-FABDEM's 30m


def _bin_max(x, y, z, cell_m, x0, y0, ncols, nrows):
    """Grid-bin points, keeping the max Z per cell (highest return /
    highest ground point) -- fine for a quick raster, not a substitute
    for a proper point-cloud rasterizer (e.g. PDAL) for real work."""
    col = ((x - x0) / cell_m).astype(int)
    row = ((y0 - y) / cell_m).astype(int)  # y0 = top, row increases downward
    valid = (col >= 0) & (col < ncols) & (row >= 0) & (row < nrows)
    col, row, z = col[valid], row[valid], z[valid]
    grid = np.full((nrows, ncols), np.nan)
    # Sort by z ascending so the last write per cell is the max
    order = np.argsort(z)
    grid[row[order], col[order]] = z[order]
    return grid


def run(laz_path: Path, half_extent_m: float = 400):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Reading %s ...", laz_path)
    las = laspy.read(str(laz_path))
    log.info("%s points, classes present: %s", f"{len(las.points):,}",
              sorted(set(las.classification.tolist())))

    cx = (las.header.x_min + las.header.x_max) / 2
    cy = (las.header.y_min + las.header.y_max) / 2
    x0, x1 = cx - half_extent_m, cx + half_extent_m
    y0, y1 = cy + half_extent_m, cy - half_extent_m  # y0 = top (max), y1 = bottom (min)

    ncols = nrows = int(2 * half_extent_m / CELL_M)
    log.info("AOI: %dx%dm around (%.0f, %.0f), raster %dx%d @ %.1fm", 2 * half_extent_m, 2 * half_extent_m,
              cx, cy, ncols, nrows, CELL_M)

    x, y, z, cls = las.x, las.y, las.z, las.classification
    in_aoi = (x >= x0) & (x <= x1) & (y >= y1) & (y <= y0)
    x, y, z, cls = np.asarray(x)[in_aoi], np.asarray(y)[in_aoi], np.asarray(z)[in_aoi], np.asarray(cls)[in_aoi]
    log.info("%s points in %dx%dm AOI -> %.1f pts/m2", f"{len(x):,}", 2 * half_extent_m, 2 * half_extent_m,
              len(x) / (2 * half_extent_m) ** 2)

    ground_mask = cls == CLASS_GROUND
    building_mask = cls == CLASS_BUILDING
    log.info("%s ground points, %s building points in AOI", f"{ground_mask.sum():,}", f"{building_mask.sum():,}")

    dtm = _bin_max(x[ground_mask], y[ground_mask], z[ground_mask], CELL_M, x0, y0, ncols, nrows)
    all_highest = _bin_max(x, y, z, CELL_M, x0, y0, ncols, nrows)  # all-returns DSM, AHN-style comparison

    # Fill DTM gaps (no ground point in that 1m cell -- common right under
    # a building footprint) via nearest-neighbor so building heights can
    # still be computed there; flagged, not hidden.
    from scipy.ndimage import distance_transform_edt
    dtm_valid = np.isfinite(dtm)
    log.info("DTM valid in %.0f%% of cells (rest: no ground return, e.g. under building footprints) -- "
              "filled via nearest-neighbor for the height calc", 100 * dtm_valid.mean())
    if dtm_valid.any():
        idx = distance_transform_edt(~dtm_valid, return_distances=False, return_indices=True)
        dtm_filled = dtm[tuple(idx)]
    else:
        dtm_filled = dtm

    building_height = _bin_max(x[building_mask], y[building_mask], z[building_mask], CELL_M, x0, y0, ncols, nrows)
    building_height = building_height - dtm_filled
    building_height = np.clip(building_height, 0, None)

    all_ndsm = np.clip(all_highest - dtm_filled, 0, None)  # AHN-style: any highest return, incl. trees

    valid_bh = np.isfinite(building_height) & (building_height > 0)
    log.info("Building-classified height: mean=%.2fm p90=%.2fm max=%.2fm over %d cells with a building point",
              np.nanmean(building_height[valid_bh]), np.nanpercentile(building_height[valid_bh], 90),
              np.nanmax(building_height[valid_bh]), int(valid_bh.sum()))
    log.info("Pixel area: 1 m2/px (1m native) vs CopDEM-FABDEM's 30m pixels -- 900x finer")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
        im0 = axes[0].imshow(dtm, cmap="terrain")
        axes[0].set_title("Boston: DTM (ground-classified points, 1m)")
        plt.colorbar(im0, ax=axes[0], fraction=0.04, label="m")

        im1 = axes[1].imshow(all_ndsm, cmap="inferno", vmin=0, vmax=np.nanpercentile(all_ndsm, 98))
        axes[1].set_title("Boston: nDSM, all returns\n(AHN-style -- incl. trees)")
        plt.colorbar(im1, ax=axes[1], fraction=0.04, label="m")

        im2 = axes[2].imshow(building_height, cmap="inferno", vmin=0, vmax=np.nanpercentile(building_height[valid_bh], 98))
        axes[2].set_title("Boston: building height\n(class=Building points only)")
        plt.colorbar(im2, ax=axes[2], fraction=0.04, label="m")

        for ax in axes:
            ax.set_xticks([]); ax.set_yticks([])
        fig.suptitle(f"USGS 3DEP QL1 LiDAR, downtown Boston -- {len(x)/(2*half_extent_m)**2:.1f} pts/m2, "
                     "raw classified point cloud rasterized directly (public domain)", fontsize=12)
        fig.tight_layout()
        out_png = OUT_DIR / "usgs_lpc_boston_diagnostic.png"
        fig.savefig(out_png, dpi=140, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved -> %s", out_png)
    except ImportError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--laz", type=Path, required=True)
    parser.add_argument("--half-extent-m", type=float, default=400)
    args = parser.parse_args()
    run(args.laz, args.half_extent_m)
