"""
dam_spillage_sar_comparison.py — before / during / after Sentinel-1 SAR
water-extent comparison for the two dam-spillage flood events now in
historical_flood_events.json:

  AKOSOMBO-DAM-SPILLAGE-2023-09-15  (Lower Volta -- Mepe area)
  WEIJA-DAM-FLOOD-2026-05-27        (Weija Gbawe -- Tetegu area)

Neither location is scored by the composite pipeline (Akosombo is outside
coverage entirely; Weija Gbawe's dam-release risk is a hazard the
SAR/DEM/land-cover score structurally can't see, per project notes). This
script does NOT change any score -- it's a standalone, evidence-only view:
does free Sentinel-1 radar actually show the flood these events caused?

Method: SAR change detection, the standard approach for mapping a single
flood event (UN-SPIDER recommended practice / Copernicus GFM style), not
the multi-year percentile-occurrence method the composite score uses --
that method normalises each scene to its own 8th percentile and so
structurally cannot see a one-off area increase. Here instead:

    log_ratio_dB = 10 * log10(power_peak / power_baseline)
    new_flood    = (log_ratio_dB < DROP_DB)          # backscatter collapsed = new smooth water
                   AND (baseline was NOT already dark)   # exclude permanent water/reservoir
    then remove connected blobs smaller than MIN_BLOB_PX   # kill speckle

VV backscatter over calm standing water is much lower than over land, so a
pixel that goes sharply darker between the baseline and the peak date is a
strong flood signal. Reads use the same _read_vv_window as the rest of the
pipeline.

Caveat kept in the output: the scenes are not guaranteed to be the same
Sentinel-1 relative orbit / look geometry, and rain-wetted soil also
lowers backscatter -- so the margins should be read as indicative, not a
surveyed flood line, same discipline as the rest of this project's SAR work.

Usage
-----
    python3 dam_spillage_sar_comparison.py
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

from geospatial_vulnerability import _grid_shape, PIXEL_DEG

# sentinel-1-rtc = radiometrically terrain-corrected gamma0 -- calibrated
# and comparable ACROSS dates (unlike raw GRD DN, which the composite-score
# pipeline gets away with only because its percentile classifier is
# self-normalising per scene). Change detection needs the calibrated
# version.
S1_COLLECTION = "sentinel-1-rtc"
DROP_DB = -3.0        # VV gamma0 must fall by >3 dB baseline->peak to count as new open water
PERM_WATER_DB = -17.0  # absolute floor: baseline pixels below this are always treated as pre-existing water
PERM_WATER_PCTL = 8    # ...and so is anything darker than the baseline's 8th percentile (adapts to the scene:
                       # catches the Volta channel, which sits ~-15 dB, not below the absolute floor)
MIN_BLOB_PX = 8       # drop connected flood blobs smaller than this (speckle rejection)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUT_DIR = HERE / "data" / "dam_spillage_sar"

EVENTS = [
    {
        "event_id": "AKOSOMBO-DAM-SPILLAGE-2023-09-15",
        "name": "Akosombo/Kpong Dam spillage (Lower Volta)",
        "bbox": (0.35, 6.00, 0.50, 6.15),  # Mepe / lower Volta reach
        "baseline": "2023-09-05",   # pre-spillage (spillage began ~Sept 15)
        "peak": "2023-10-23",       # ~2 weeks into peak flooding (began Oct 9)
        "recession": "2023-11-28",  # ~5 weeks later
    },
    {
        "event_id": "WEIJA-DAM-FLOOD-2026-05-27",
        "name": "Weija Dam spillage (Tetegu / Weija Gbawe)",
        "bbox": (-0.325, 5.518, -0.283, 5.560),  # downstream floodplain, reservoir body mostly excluded
        "baseline": "2026-05-21",   # 6 days before the gates opened
        "peak": "2026-05-28",       # day after all spill gates opened (2026-05-27)
        "recession": "2026-06-09",  # ~2 weeks later
    },
]


def _pixel_area_km2(bbox, shape_rc) -> float:
    minlon, minlat, maxlon, maxlat = bbox
    rows, cols = shape_rc
    lat0 = (minlat + maxlat) / 2
    m_per_deg_lat = 110_574.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat0))
    dlon_m = (maxlon - minlon) / cols * m_per_deg_lon
    dlat_m = (maxlat - minlat) / rows * m_per_deg_lat
    return (dlon_m * dlat_m) / 1e6


def _read_db(catalog, bbox, date: str):
    """VV gamma0 in dB for the RTC scene nearest `date`, reprojected onto a
    common EPSG:4326 grid at PIXEL_DEG so every date lines up pixel-for-pixel."""
    from datetime import datetime, timedelta
    d = datetime.strptime(date, "%Y-%m-%d")
    start = (d - timedelta(days=2)).strftime("%Y-%m-%d")
    end = (d + timedelta(days=2)).strftime("%Y-%m-%d")
    items = list(catalog.search(
        collections=[S1_COLLECTION], bbox=list(bbox), datetime=f"{start}/{end}",
    ).item_collection())
    if not items:
        raise RuntimeError(f"no {S1_COLLECTION} scene near {date}")
    items.sort(key=lambda it: abs(
        (datetime.strptime(it.properties["datetime"][:10], "%Y-%m-%d") - d).days))
    item = items[0]

    minlon, minlat, maxlon, maxlat = bbox
    ds = odc.stac.load(
        [item], bands=["vv"], crs="EPSG:4326", resolution=PIXEL_DEG,
        x=(minlon, maxlon), y=(minlat, maxlat), chunks={},
    )
    gamma0 = ds["vv"].isel(time=0).values.astype(np.float64)
    db = np.full(gamma0.shape, np.nan, dtype=np.float64)
    good = np.isfinite(gamma0) & (gamma0 > 0)
    db[good] = 10.0 * np.log10(gamma0[good])
    log.info("  %s -> scene %s (%s orbit), median VV %.1f dB",
             date, item.properties["datetime"][:10],
             item.properties.get("sat:orbit_state", "?"), float(np.nanmedian(db)))
    return db, item.properties["datetime"][:10]


def _perm_water_db(db_before: np.ndarray) -> float:
    """Adaptive pre-existing-water cutoff: the less-negative (more inclusive)
    of the absolute floor and the baseline's low percentile."""
    valid = np.isfinite(db_before)
    if not valid.any():
        return PERM_WATER_DB
    return max(PERM_WATER_DB, float(np.percentile(db_before[valid], PERM_WATER_PCTL)))


def _new_flood_mask(db_before: np.ndarray, db_after: np.ndarray) -> np.ndarray:
    """Pixels that dropped >|DROP_DB| dB in calibrated VV between the two
    dates AND were not already open water in the 'before' scene, then
    speckle-filtered by connected-blob size."""
    valid = np.isfinite(db_before) & np.isfinite(db_after)
    perm = _perm_water_db(db_before)
    darkened = np.zeros(db_before.shape, dtype=bool)
    darkened[valid] = ((db_after[valid] - db_before[valid]) < DROP_DB) & (db_before[valid] > perm)

    labels, n = ndimage.label(darkened)
    if n:
        sizes = ndimage.sum(np.ones_like(labels), labels, index=np.arange(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_BLOB_PX]
        darkened = np.isin(labels, keep) if keep else np.zeros_like(darkened)
    return darkened


def _prewater_mask(db: np.ndarray) -> np.ndarray:
    """Pre-existing open water in the baseline (same adaptive cutoff the
    change detection uses to exclude it). Context panel only."""
    return np.isfinite(db) & (db <= _perm_water_db(db))


def run_event(catalog, ev: dict) -> dict:
    bbox = ev["bbox"]
    shape_rc = _grid_shape(bbox, PIXEL_DEG)
    px_km2 = _pixel_area_km2(bbox, shape_rc)
    log.info("%s -- grid %dx%d, pixel ~%.3f km2", ev["event_id"], *shape_rc, px_km2)

    db, scene_dates = {}, {}
    for phase in ("baseline", "peak", "recession"):
        db[phase], scene_dates[phase] = _read_db(catalog, bbox, ev[phase])

    new_at_peak = _new_flood_mask(db["baseline"], db["peak"])
    receded = new_at_peak & ~_new_flood_mask(db["baseline"], db["recession"])
    still_flooded = new_at_peak & ~receded
    baseline_water = _prewater_mask(db["baseline"])

    summary = {
        "event_id": ev["event_id"], "name": ev["name"], "bbox": list(bbox),
        "scene_dates": scene_dates,
        "baseline_open_water_km2": round(float(baseline_water.sum()) * px_km2, 2),
        "new_flood_at_peak_km2": round(float(new_at_peak.sum()) * px_km2, 2),
        "receded_by_recession_km2": round(float(receded.sum()) * px_km2, 2),
        "still_flooded_at_recession_km2": round(float(still_flooded.sum()) * px_km2, 2),
        "method": f"Sentinel-1 RTC (calibrated gamma0) VV change detection: >|{-DROP_DB:.0f}|dB drop "
                  f"baseline->peak, pre-existing water excluded (adaptive: max of {PERM_WATER_DB:.0f} dB and "
                  f"the baseline's {PERM_WATER_PCTL}th percentile), blobs <{MIN_BLOB_PX}px removed. "
                  "Rain-wetted soil also darkens VV -- read margins as indicative, not a surveyed flood line.",
    }

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for ax, phase in zip(axes[0], ("baseline", "peak", "recession")):
        d = db[phase]
        ax.imshow(d, cmap="gray", interpolation="nearest",
                  vmin=np.nanpercentile(d, 5), vmax=np.nanpercentile(d, 95))
        ax.set_title(f"{phase}: {scene_dates[phase]}  (VV gamma0, dB)")
        ax.set_xticks([]); ax.set_yticks([])
    axes[1][0].imshow(baseline_water, cmap="Blues", interpolation="nearest")
    axes[1][0].set_title(f"baseline open water\n{baseline_water.sum() * px_km2:.1f} km2")
    axes[1][1].imshow(new_at_peak, cmap="Reds", interpolation="nearest")
    axes[1][1].set_title(f"NEW flood at peak (change detection)\n{new_at_peak.sum() * px_km2:.1f} km2")
    from matplotlib.colors import ListedColormap
    rec_map = np.zeros(new_at_peak.shape, dtype=int)
    rec_map[receded] = 1
    rec_map[still_flooded] = 2
    axes[1][2].imshow(rec_map, cmap=ListedColormap(["#f0f0f0", "#27ae60", "#c0392b"]),
                      interpolation="nearest", vmin=0, vmax=2)
    axes[1][2].set_title(f"green = receded by {scene_dates['recession']} ({receded.sum() * px_km2:.1f} km2)\n"
                          f"red = still flooded ({still_flooded.sum() * px_km2:.1f} km2)")
    for ax in axes[1]:
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"{ev['name']}  --  Sentinel-1 SAR change detection, before / during / after", fontsize=13)
    fig.tight_layout()
    out_png = OUT_DIR / f"{ev['event_id']}.png"
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    log.info("  saved -> %s", out_png)
    return summary


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    summaries = [run_event(catalog, ev) for ev in EVENTS]
    (OUT_DIR / "summary.json").write_text(json.dumps({"events": summaries}, indent=2))
    log.info("saved -> %s", OUT_DIR / "summary.json")
    for s in summaries:
        log.info("%s: +%.1f km2 new flood at peak (%s), %.1f km2 still flooded by %s, %.1f km2 receded",
                 s["event_id"], s["new_flood_at_peak_km2"], s["scene_dates"]["peak"],
                 s["still_flooded_at_recession_km2"], s["scene_dates"]["recession"],
                 s["receded_by_recession_km2"])


if __name__ == "__main__":
    run()
