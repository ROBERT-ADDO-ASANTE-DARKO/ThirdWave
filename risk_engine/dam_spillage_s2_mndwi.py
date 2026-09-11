"""
dam_spillage_s2_mndwi.py — Sentinel-2 optical (MNDWI) before / during / after
water mapping for the 2023 Akosombo / Lower Volta dam-spillage flood.

Companion to dam_spillage_sar_comparison.py. That script uses Sentinel-1
radar because radar sees through cloud; this one uses Sentinel-2 optical,
which is cloudier but -- when a clear-enough scene exists -- gives a
sharper, speckle-free water map via MNDWI (Modified Normalized Difference
Water Index):

    MNDWI = (Green_B03 - SWIR_B11) / (Green_B03 + SWIR_B11)      water: MNDWI > MNDWI_THR

Only Akosombo is done here. Checked scene-by-scene: the 2026 Weija spillage
has no usable low-cloud Sentinel-2 scene near its (short, flashy) peak --
2026-05-27 itself is 92% cloud -- so radar is the only option there.

For Akosombo, the peak and recession windows have near-clear passes, but
the immediate pre-flood period (Aug-Sep 2023) is uniformly ~85-99% cloud
over this AOI -- there is NO usable rainy-season baseline. So the baseline
here is a DRY-SEASON REFERENCE: a near-cloud-free scene from ~9 months
before the flood, representing the Volta's normal (dam-regulated, stable)
extent. Standard practice when no clean pre-event scene exists; the
tradeoff is that seasonal-not-flood differences also show up and should be
read as noise near the margins.

    baseline (dry-season ref)  2022-12-29   ~1%  cloud
    peak                       2023-10-15   ~14% cloud   (6 days into the flood, in the peak window)
    recession                  2023-11-29   ~5%  cloud   (one day off the SAR script's recession date)

Cloud honesty: every scene has SOME cloud. Cloudy / cloud-shadow pixels
(from the L2A SCL band) are masked to NaN and excluded, and the
cloud-masked fraction of the AOI is reported per scene. Where cloud
obscured part of the AOI at peak, the detected new-flood area is a LOWER
BOUND, not a full extent -- stated in the output.

Usage
-----
    python3 dam_spillage_s2_mndwi.py
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import numpy as np
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import odc.stac
import pystac_client
import planetary_computer

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "dam_spillage_s2"

BBOX = (0.35, 6.00, 0.50, 6.15)      # Mepe / lower Volta reach -- same as the SAR script
RES_DEG = 0.00045                    # ~50 m; finer than the SAR grid, to use S2's resolution
MNDWI_THR = 0.0                      # standard MNDWI open-water cutoff
MIN_BLOB_PX = 12                     # optical is cleaner than SAR; small blob filter still helps
SCL_BAD = {0, 1, 3, 8, 9, 10}        # no-data, saturated, cloud shadow, cloud (med/high), thin cirrus

SCENES = {
    "baseline": "2022-12-29",   # dry-season reference -- no usable rainy-season pre-flood scene (see docstring)
    "peak": "2023-10-15",
    "recession": "2023-11-29",
}


def _pixel_area_km2(bbox, shape_rc) -> float:
    minlon, minlat, maxlon, maxlat = bbox
    rows, cols = shape_rc
    lat0 = (minlat + maxlat) / 2
    dlon_m = (maxlon - minlon) / cols * 111_320.0 * np.cos(np.radians(lat0))
    dlat_m = (maxlat - minlat) / rows * 110_574.0
    return (dlon_m * dlat_m) / 1e6


def _load_scene(catalog, date: str):
    """MNDWI + validity mask for the least-cloudy S2 L2A scene within +/-3
    days of `date`, on a common EPSG:4326 grid."""
    from datetime import datetime, timedelta
    d = datetime.strptime(date, "%Y-%m-%d")
    lo = (d - timedelta(days=3)).strftime("%Y-%m-%d")
    hi = (d + timedelta(days=3)).strftime("%Y-%m-%d")
    items = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(BBOX), datetime=f"{lo}/{hi}",
    ).item_collection())
    if not items:
        raise RuntimeError(f"no Sentinel-2 scene near {date}")
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
    item = items[0]

    minlon, minlat, maxlon, maxlat = BBOX
    ds = odc.stac.load(
        [item], bands=["B03", "B11", "SCL"], crs="EPSG:4326", resolution=RES_DEG,
        x=(minlon, maxlon), y=(minlat, maxlat), chunks={},
        resampling={"B03": "bilinear", "B11": "bilinear", "SCL": "nearest"},
    ).isel(time=0)

    green = ds["B03"].values.astype(np.float64)
    swir = ds["B11"].values.astype(np.float64)
    scl = ds["SCL"].values

    # L2A processing baseline >= 04.00 stores reflectance as DN with a
    # -1000 offset; ratios don't cancel an additive offset, so undo it.
    if np.nanmax(green) > 100:
        green = (green - 1000.0) / 10000.0
        swir = (swir - 1000.0) / 10000.0

    denom = green + swir
    mndwi = np.where(np.abs(denom) > 1e-6, (green - swir) / denom, np.nan)

    bad = np.isin(scl, list(SCL_BAD)) | ~np.isfinite(mndwi)
    mndwi[bad] = np.nan
    cloud_frac = float(bad.mean())
    log.info("  %s -> scene %s, AOI cloud/invalid %.0f%%",
             date, item.properties["datetime"][:10], cloud_frac * 100)
    return mndwi, item.properties["datetime"][:10], cloud_frac


def _water(mndwi: np.ndarray) -> np.ndarray:
    return np.isfinite(mndwi) & (mndwi > MNDWI_THR)


def _despeckle(mask: np.ndarray) -> np.ndarray:
    labels, n = ndimage.label(mask)
    if not n:
        return mask
    sizes = ndimage.sum(np.ones_like(labels), labels, index=np.arange(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_BLOB_PX]
    return np.isin(labels, keep) if keep else np.zeros_like(mask)


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    mndwi, dates, cloud = {}, {}, {}
    for phase, date in SCENES.items():
        mndwi[phase], dates[phase], cloud[phase] = _load_scene(catalog, date)

    shape_rc = mndwi["baseline"].shape
    px_km2 = _pixel_area_km2(BBOX, shape_rc)

    w = {p: _water(mndwi[p]) for p in SCENES}
    both_bp = np.isfinite(mndwi["baseline"]) & np.isfinite(mndwi["peak"])
    both_pr = np.isfinite(mndwi["peak"]) & np.isfinite(mndwi["recession"])

    new_flood = _despeckle(w["peak"] & ~w["baseline"] & both_bp)
    receded = new_flood & both_pr & ~w["recession"]
    still_flooded = new_flood & both_pr & w["recession"]

    summary = {
        "event_id": "AKOSOMBO-DAM-SPILLAGE-2023-09-15",
        "sensor": "Sentinel-2 L2A, MNDWI = (B03-B11)/(B03+B11), water > %.2f" % MNDWI_THR,
        "bbox": list(BBOX), "resolution_deg": RES_DEG,
        "scene_dates": dates,
        "aoi_cloud_masked_pct": {p: round(cloud[p] * 100, 1) for p in SCENES},
        "baseline_open_water_km2": round(float(w["baseline"].sum()) * px_km2, 2),
        "new_flood_at_peak_km2": round(float(new_flood.sum()) * px_km2, 2),
        "receded_by_recession_km2": round(float(receded.sum()) * px_km2, 2),
        "still_flooded_at_recession_km2": round(float(still_flooded.sum()) * px_km2, 2),
        "note": f"new_flood is a LOWER BOUND: {cloud['peak']*100:.0f}% of the AOI was cloud-masked "
                "in the peak scene, so flooding under those clouds is not counted. "
                "Optical complements the SAR result in dam_spillage_sar/ (radar had no cloud issue "
                "but noisier margins); where both are clear they should broadly agree.",
    }

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for ax, phase in zip(axes[0], ("baseline", "peak", "recession")):
        im = ax.imshow(mndwi[phase], cmap="BrBG", vmin=-0.6, vmax=0.6, interpolation="nearest")
        ax.set_title(f"{phase}: {dates[phase]}  (MNDWI, {cloud[phase]*100:.0f}% cloud-masked)")
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=axes[0].tolist(), fraction=0.02, label="MNDWI (blue-green = water)")

    axes[1][0].imshow(w["baseline"], cmap="Blues", interpolation="nearest")
    axes[1][0].set_title(f"dry-season reference water ({dates['baseline']})\n{w['baseline'].sum() * px_km2:.1f} km2")
    axes[1][1].imshow(new_flood, cmap="Reds", interpolation="nearest")
    axes[1][1].set_title(f"NEW flood at peak (MNDWI)\n{new_flood.sum() * px_km2:.1f} km2  (lower bound)")
    from matplotlib.colors import ListedColormap
    rec_map = np.zeros(new_flood.shape, dtype=int)
    rec_map[receded] = 1
    rec_map[still_flooded] = 2
    axes[1][2].imshow(rec_map, cmap=ListedColormap(["#f0f0f0", "#27ae60", "#c0392b"]),
                      interpolation="nearest", vmin=0, vmax=2)
    axes[1][2].set_title(f"green = receded by {dates['recession']} ({receded.sum() * px_km2:.1f} km2)\n"
                          f"red = still flooded ({still_flooded.sum() * px_km2:.1f} km2)")
    for ax in axes[1]:
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Akosombo/Kpong Dam spillage (Lower Volta)  --  Sentinel-2 MNDWI, before / during / after",
                 fontsize=13)
    fig.tight_layout()
    out_png = OUT_DIR / "AKOSOMBO-DAM-SPILLAGE-2023-09-15_S2_MNDWI.png"
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    log.info("saved -> %s", out_png)
    log.info("saved -> %s", OUT_DIR / "summary.json")
    log.info("Akosombo S2: +%.1f km2 new flood at peak (%.0f%% AOI cloud-masked -> lower bound), "
             "%.1f km2 still flooded by %s",
             summary["new_flood_at_peak_km2"], cloud["peak"] * 100,
             summary["still_flooded_at_recession_km2"], dates["recession"])


if __name__ == "__main__":
    run()
