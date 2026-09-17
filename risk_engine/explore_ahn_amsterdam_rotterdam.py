"""
explore_ahn_amsterdam_rotterdam.py — pull real AHN (Actueel Hoogtebestand
Nederland) 0.5m DTM + DSM windows for small AOIs in Amsterdam and
Rotterdam, compute nDSM = DSM - DTM (a real, native-resolution building/
canopy-height layer, not a proxy), and inspect visually for the kind of
fine drainage/culvert-level detail the project set out to check for.

Context: this follows directly from testing whether CopDEM-FABDEM
(30m-class, our free proxy) or GlobalBuildingAtlas (ML-derived, validated
weak/absent in both Accra and Boston) can substitute for real high-
resolution elevation data. AHN is a genuine, best-in-class comparison
point: CC0 public domain, 0.5m native resolution, 10-20 pts/m2 source
point density (see project chat history) -- a real answer to "what would
actually be needed."

Access: PDOK hosts AHN's DTM/DSM as plain (non-COG) GeoTIFFs, one file
per ~5x6.25km "kaartblad" tile (~350MB each) -- but the PDOK server
supports HTTP Range requests, so GDAL's /vsicurl/ driver can do a
windowed read of a small AOI without downloading the whole tile (same
trick as this project's other partial-fetch scripts, just via GDAL's own
mechanism here instead of a hand-rolled HTTP range reader). Confirmed
empirically: a 206 Partial Content response, and rasterio.open() over
/vsicurl/ opens instantly and reports correct shape/transform/bounds
without pulling the full file.

Tile index: https://service.pdok.nl/rws/ahn/atom/downloads/<dtm_05m|dsm_05m>/kaartbladindex.json
(EPSG:28992 / RD New coordinates -- convert lon/lat with pyproj first.)

License: AHN is CC0 (public domain) -- no attribution required, no
non-commercial restriction, unlike FABDEM (CC BY-NC-SA) or GBA (CC BY-NC).

Usage
─────
    python3 explore_ahn_amsterdam_rotterdam.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
import rasterio.windows
from pyproj import Transformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "ahn_explore"

TILE_BASE = "https://service.pdok.nl/rws/ahn/atom/downloads"

CITIES = {
    # lon, lat center of a canal-dense area; half_extent_m = AOI half-width.
    # DTM and DSM tiles cover the same grid cell but use different sheet-
    # number prefixes ("M_" for dtm_05m, "R_" for dsm_05m) -- confirmed by
    # querying each product's own kaartbladindex.json separately rather
    # than assuming they match.
    "amsterdam": {"lonlat": (4.8910, 52.3680), "half_extent_m": 500,
                  "dtm_tile": "M_25GN1", "dsm_tile": "R_25GN1",
                  "note": "Amsterdam canal ring (Prinsengracht/Herengracht area)"},
    "rotterdam": {"lonlat": (4.4870, 51.9200), "half_extent_m": 500,
                  "dtm_tile": "M_37FZ1", "dsm_tile": "R_37FZ1",
                  "note": "Rotterdam city center, Coolsingel/Blaak area"},
}

_to_rd = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def _read_window(tile: str, product: str, cx: float, cy: float, half: float) -> tuple[np.ndarray, rasterio.Affine]:
    url = f"/vsicurl/{TILE_BASE}/{product}/{tile}.tif"
    with rasterio.open(url) as src:
        win = rasterio.windows.from_bounds(cx - half, cy - half, cx + half, cy + half, src.transform)
        arr = src.read(1, window=win)
        win_transform = src.window_transform(win)
        # AHN's nodata sentinel is float32 max (~3.4e38), not a negative
        # value -- caught for real here: an earlier `arr < -100` mask
        # missed every nodata pixel (0 filtered out of 4,000,000), silently
        # corrupting the nDSM stats with garbage values.
        if src.nodata is not None:
            arr = np.where(np.isclose(arr, src.nodata, rtol=1e-3), np.nan, arr)
    return arr, win_transform


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    for name, cfg in CITIES.items():
        lon, lat = cfg["lonlat"]
        rd_x, rd_y = _to_rd.transform(lon, lat)
        half = cfg["half_extent_m"]
        log.info("=== %s (%s) -- RD (%.0f, %.0f), %dx%dm AOI ===", name, cfg["note"], rd_x, rd_y, 2 * half, 2 * half)

        log.info("  Reading DTM window (bare earth, /vsicurl/ windowed read -- not full tile download)...")
        dtm, transform = _read_window(cfg["dtm_tile"], "dtm_05m", rd_x, rd_y, half)
        log.info("  Reading DSM window (surface model, incl. buildings/canopy)...")
        dsm, _ = _read_window(cfg["dsm_tile"], "dsm_05m", rd_x, rd_y, half)

        ndsm = np.clip(dsm - dtm, 0, None)

        valid = np.isfinite(ndsm)
        log.info("  DTM range: %.2f - %.2f m", np.nanmin(dtm), np.nanmax(dtm))
        log.info("  nDSM (building/canopy height): mean=%.2fm p90=%.2fm max=%.2fm over %d valid pixels at 0.5m native res",
                  np.nanmean(ndsm[valid]), np.nanpercentile(ndsm[valid], 90), np.nanmax(ndsm[valid]), int(valid.sum()))
        log.info("  Pixel area: 0.25 m2/px (0.5m native) vs CopDEM-FABDEM's 30m pixels (900 m2/px) -- %.0fx finer",
                  900 / 0.25)

        results[name] = {"dtm": dtm, "dsm": dsm, "ndsm": ndsm, "note": cfg["note"]}

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(16, 10))
        for row, (name, r) in enumerate(results.items()):
            im0 = axes[row][0].imshow(r["dtm"], cmap="terrain")
            axes[row][0].set_title(f"{name}: DTM (bare earth, 0.5m)")
            plt.colorbar(im0, ax=axes[row][0], fraction=0.04, label="m")

            im1 = axes[row][1].imshow(r["dsm"], cmap="terrain")
            axes[row][1].set_title(f"{name}: DSM (surface, 0.5m)")
            plt.colorbar(im1, ax=axes[row][1], fraction=0.04, label="m")

            im2 = axes[row][2].imshow(r["ndsm"], cmap="inferno", vmin=0, vmax=np.nanpercentile(r["ndsm"], 98))
            axes[row][2].set_title(f"{name}: nDSM = DSM-DTM\n({r['note']})")
            plt.colorbar(im2, ax=axes[row][2], fraction=0.04, label="m")

            for ax in axes[row]:
                ax.set_xticks([]); ax.set_yticks([])

        fig.suptitle("AHN 0.5m native-resolution DTM/DSM/nDSM -- Amsterdam & Rotterdam (CC0, PDOK)", fontsize=13)
        fig.tight_layout()
        out_png = OUT_DIR / "ahn_amsterdam_rotterdam_diagnostic.png"
        fig.savefig(out_png, dpi=140, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved -> %s", out_png)
    except ImportError:
        pass


if __name__ == "__main__":
    run()
