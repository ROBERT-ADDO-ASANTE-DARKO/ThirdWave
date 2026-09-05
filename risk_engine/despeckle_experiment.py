"""
despeckle_experiment.py — Quick test: does SAR2SAR despeckling (via the
`deepdespeckling` package, pretrained weights, no training needed) change
our water classification on the actual pilot Sentinel-1 scenes?

Unlike the Amieva/Ayala/Galar Stripmap-based super-resolution approach
(blocked by unknown/unlikely Ghana Stripmap coverage), SAR2SAR is
self-supervised and works directly on standard Sentinel-1 GRD data --
no region-specific training or special acquisition mode needed.

This does NOT test super-resolution (SAR2SAR doesn't change pixel
dimensions) -- only whether despeckling changes the water/no-water
classification our vulnerability score depends on.

Usage
─────
    python3 despeckle_experiment.py --scenes 5
"""

from __future__ import annotations

import argparse
import logging
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pystac_client
import planetary_computer

# deepdespeckling.utils.load_cosar unconditionally imports osgeo/gdal for
# reading TerraSAR-X .cos files -- a code path we never touch since we pass
# our own numpy array from Planetary Computer directly to denoise_image().
# No system GDAL dev headers are installed here (rasterio bundles its own
# GDAL without exposing the osgeo bindings), so stub the module rather than
# install a heavy system package for an import we don't use.
import sys
import types
_osgeo_stub = types.ModuleType("osgeo")
_osgeo_stub.gdal = types.ModuleType("osgeo.gdal")
sys.modules.setdefault("osgeo", _osgeo_stub)
sys.modules.setdefault("osgeo.gdal", _osgeo_stub.gdal)

from deepdespeckling.sar2sar.sar2sar_denoiser import Sar2SarDenoiser

# PyTorch 2.6+ defaults torch.load to weights_only=True, which blocks the
# pretrained sar2sar.pth checkpoint (pickled with an older numpy scalar
# global whose safe-globals path doesn't line up across numpy 1.x/2.x
# module layouts). This is the exact weight file shipped in the official
# deepdespeckling PyPI package we just installed -- trusted at the same
# level as the package's own code, unlike an arbitrary/untrusted checkpoint
# -- so force weights_only=False for this one load rather than chase the
# numpy-version-specific safe-globals path.
import torch
_torch_load_orig = torch.load
def _torch_load_trusted(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _torch_load_orig(*args, **kwargs)
torch.load = _torch_load_trusted

from geospatial_vulnerability import (
    _grid_shape, _make_transform, _read_vv_window, _classify_water,
    PIXEL_DEG, WATER_PCT_THR, PILOT_BOUNDARY, START_DATE, END_DATE,
)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
OUTPUT = HERE / "data" / "despeckle_experiment_diagnostic.png"

PATCH_SIZE = 256
STRIDE_SIZE = 254
# Pad well beyond the pilot bbox so the padded raster is comfortably larger
# than PATCH_SIZE in both dimensions -- the first attempt at patch_size=64
# on our small 122x142 pilot raster produced visible tiling/blocking
# artifacts (boundary effects dominate a tiny image), and those seams
# directly contaminated the water mask. Despeckle at the model's intended
# scale on a larger extent, then crop back to the actual pilot bbox.
EXTRA_PAD_DEG = 0.15

DARK, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED = "#e6edf3", "#8b949e"


def run(n_scenes: int = 5):
    import geopandas as gpd
    bounds_gdf = gpd.read_file(PILOT_BOUNDARY)
    minlon, minlat, maxlon, maxlat = bounds_gdf.total_bounds
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape = _grid_shape(bbox, PIXEL_DEG)

    # Padded extent used only for despeckling, so the model runs at its
    # intended patch_size=256 with several patches per axis instead of ~2 --
    # boundary/tiling artifacts become a small fraction of the image instead
    # of dominating it.
    padded_bbox = (minlon - EXTRA_PAD_DEG, minlat - EXTRA_PAD_DEG, maxlon + EXTRA_PAD_DEG, maxlat + EXTRA_PAD_DEG)
    padded_shape = _grid_shape(padded_bbox, PIXEL_DEG)
    # Pixel offset of the pilot bbox within the padded raster, for cropping back
    row_off = int(round((padded_bbox[3] - bbox[3]) / PIXEL_DEG))
    col_off = int(round((bbox[0] - padded_bbox[0]) / PIXEL_DEG))
    log.info("Pilot bbox raster: %dx%d | padded raster for despeckling: %dx%d (patch=%d, stride=%d)",
             shape[0], shape[1], padded_shape[0], padded_shape[1], PATCH_SIZE, STRIDE_SIZE)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    all_items = list(catalog.search(
        collections=["sentinel-1-grd"], bbox=list(bbox), datetime=f"{START_DATE}/{END_DATE}",
    ).item_collection())
    rng = np.random.default_rng(7)
    chosen = list(rng.choice(len(all_items), n_scenes, replace=False))
    selected = [all_items[i] for i in chosen]
    log.info("Testing %d scenes", len(selected))

    denoiser = Sar2SarDenoiser()

    results = []
    example_pair = None
    for i, item in enumerate(selected):
        date = item.properties["datetime"][:10]
        log.info("[%d/%d] %s", i + 1, len(selected), date)

        power_padded = _read_vv_window(item, padded_bbox, padded_shape)
        if power_padded is None:
            continue
        power_padded_filled = np.nan_to_num(power_padded, nan=0.0)

        despeckled = denoiser.denoise_image(power_padded_filled, patch_size=PATCH_SIZE, stride_size=STRIDE_SIZE)
        denoised_padded = despeckled["denoised"]

        # Crop both the original-resolution power array and the despeckled
        # result back down to the actual pilot bbox for a fair comparison.
        power = power_padded[row_off:row_off + shape[0], col_off:col_off + shape[1]]
        denoised_img = denoised_padded[row_off:row_off + shape[0], col_off:col_off + shape[1]]

        water_before = _classify_water(power, WATER_PCT_THR)
        # classify on the despeckled image using the same percentile logic
        valid = denoised_img[np.isfinite(denoised_img)]
        threshold = np.percentile(valid, WATER_PCT_THR) if len(valid) else 0
        water_after = np.isfinite(denoised_img) & (denoised_img <= threshold)

        pct_before = float(np.mean(water_before)) * 100
        pct_after = float(np.mean(water_after)) * 100
        agreement = float(np.mean(water_before == water_after)) * 100

        results.append({"date": date, "pct_water_before": pct_before, "pct_water_after": pct_after,
                         "pixel_agreement_pct": agreement})
        log.info("  water%%: before=%.2f after=%.2f  pixel-agreement=%.1f%%", pct_before, pct_after, agreement)

        if example_pair is None:
            example_pair = (date, np.nan_to_num(power, nan=0.0), denoised_img, water_before, water_after)

    log.info("=== Summary across %d scenes ===", len(results))
    mean_before = np.mean([r["pct_water_before"] for r in results])
    mean_after = np.mean([r["pct_water_after"] for r in results])
    mean_agreement = np.mean([r["pixel_agreement_pct"] for r in results])
    log.info("Mean water%%: before=%.2f after=%.2f | mean pixel-level agreement=%.1f%%",
              mean_before, mean_after, mean_agreement)

    if example_pair:
        date, noisy, denoised, wb, wa = example_pair
        fig, axes = plt.subplots(2, 2, figsize=(14, 12), facecolor=DARK)
        fig.suptitle(f"SAR2SAR despeckling test — scene {date}", color=TEXT, fontsize=13, fontweight="bold")
        titles = ["Raw SAR (power)", "Despeckled (SAR2SAR)", "Water mask — before", "Water mask — after"]
        imgs = [np.log1p(noisy), np.log1p(np.clip(denoised, 0, None)), wb, wa]
        cmaps = ["gray", "gray", "Blues", "Blues"]
        for ax, im, title, cmap in zip(axes.flat, imgs, titles, cmaps):
            ax.set_facecolor(CARD)
            ax.imshow(im, cmap=cmap)
            ax.set_title(title, color=TEXT, fontsize=10)
            ax.axis("off")
        fig.text(0.5, 0.01, "Source: Sentinel-1 GRD (Planetary Computer) · SAR2SAR pretrained weights (deepdespeckling)",
                  ha="center", color=MUTED, fontsize=8)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(OUTPUT, dpi=130, bbox_inches="tight", facecolor=DARK)
        log.info("Saved -> %s", OUTPUT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=5)
    args = parser.parse_args()
    run(n_scenes=args.scenes)
