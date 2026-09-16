"""
building_obstruction_height.py — a free, zero-new-imagery height-above-ground
layer per risk-grid cell: Copernicus DEM (a surface model -- includes
building/canopy height bias) minus FABDEM (the same terrain with that bias
ML-corrected away) = a real, physically grounded obstruction-height proxy.

Genesis: discussed monocular/stereo depth estimation fused with FABDEM to
approximate building heights where no LiDAR exists (see project chat
history). FABDEM is bare-earth BY DESIGN -- it's the complement you
subtract building heights AWAY FROM, not a source of them. But the
pipeline already fetches raw Copernicus DEM (a DSM) as its elevation
input; subtracting FABDEM from that is the standard DTM/DSM-differencing
technique (same math as any canopy-height model) and needs no new
imagery, no ML model, and no training data this project doesn't have.

Resolution honesty: both rasters are ~30m-class. In a dense informal
settlement (Agbogbloshie, Old Fadama) one pixel blends dozens of small
structures and alleyways into a single averaged bump -- this is NOT a
building-level layer, and it will not tell you which specific building
encroaches on a channel (channel_encroachment_index.py's OSM-based
approach, despite its own uneven-coverage caveats, is still the right
tool for that). What this DOES give: a real per-grid-cell "how much
vertical obstruction sits here" signal, complementary to (not blended
into) the composite score -- same "report, don't blend" discipline as
the LULC breakdown.

Validated, not assumed: cross-checked against impervious_pct (already
computed per cell) as an independent sanity check, since CopDEM and
FABDEM could plausibly diverge on terrain-slope/forest-canopy noise
rather than real building structure. Result: r=0.83 over the dense-urban
Accra pilot grid (1013 cells) -- a real signal. But r=0.14 over the Lower
Volta basin grid (16,941 cells) -- NOT a real signal there. Every
top-ranked Lower Volta cell had 0% impervious land cover but sat in
forested, hilly terrain near the Akosombo reservoir (Asuogyaman); CopDEM
and FABDEM diverge there for reasons that have nothing to do with
buildings (forest-canopy correction residuals, DEM noise on steep
slopes) -- a real, confirmed, basin-specific limitation of this
technique, not a bug. Trust this layer's numbers where the run's own
validation correlation is reported strong; treat it as unreliable where
weak, per-AOI, not just for the whole project.

For genuine building-level heights, the honest next steps (not built
here) are photogrammetric stereo/tri-stereo from VHR imagery (real 3D
from parallax -- see the ESA Pléiades Neo proposal draft) or shadow-length
estimation from a single well-metadata'd VHR image. Generic monocular
depth-estimation models were deliberately NOT pursued: they're trained on
oblique/eye-level scenes and are badly out-of-distribution for a nadir
satellite view (see project chat history for the full reasoning).

License: FABDEM is CC BY-NC-SA 4.0 (Hawker et al. 2022, University of
Bristol / Fathom) -- non-commercial, share-alike. Compatible with this
project's current non-commercial pilot status; this script's output
carries the same attribution + license note. Do not use commercially
without contacting fabdem@fathom.global.

Usage
─────
    python3 building_obstruction_height.py                    # pilot district
    python3 building_obstruction_height.py --grid data/lower_volta_risk_grid.geojson \
        --out data/lower_volta_building_obstruction_height.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import shape as shp_shape

import pystac_client
import planetary_computer

from geospatial_vulnerability import _grid_shape, _make_transform, _zone_mask, _read_dem_window, PIXEL_DEG
from fabdem_fetch import read_fabdem_window, LICENSE_NOTE

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
DEFAULT_GRID = HERE / "data" / "pilot_risk_grid.geojson"
DEFAULT_OUTPUT = HERE / "data" / "building_obstruction_height.json"

# Both rasters have their own independent noise; a small negative
# "obstruction" (FABDEM slightly above CopDEM at a pixel) is measurement
# noise, not a below-ground building -- clip at zero rather than report it.
MIN_OBSTRUCTION_M = 0.0
# Implausible spikes (data artifacts, tile-edge effects) shouldn't silently
# distort a zone's mean -- cap and flag rather than let one bad pixel skew it.
MAX_PLAUSIBLE_M = 60.0


def run(grid_path: Path = DEFAULT_GRID, output: Path = DEFAULT_OUTPUT):
    grid = gpd.read_file(grid_path)
    log.info("Computing building/canopy obstruction height for %d cells (grid: %s)", len(grid), grid_path.name)

    bbox = tuple(grid.total_bounds)
    minlon, minlat, maxlon, maxlat = bbox
    pad = 0.01
    bbox = (minlon - pad, minlat - pad, maxlon + pad, maxlat + pad)
    shape_ = _grid_shape(bbox, PIXEL_DEG)
    transform = _make_transform(bbox, shape_)
    log.info("Raster grid: %dx%d (~%.0fm pixels)", shape_[0], shape_[1], PIXEL_DEG * 111_000)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    log.info("Fetching Copernicus DEM (surface model, includes building/canopy bias)...")
    copdem = _read_dem_window(catalog, bbox, shape_)
    if copdem is None:
        raise RuntimeError("No Copernicus DEM data for this bbox")

    log.info("Fetching FABDEM (bare-earth, same terrain with that bias ML-corrected away)...")
    fabdem = read_fabdem_window(bbox, shape_)
    if fabdem is None:
        raise RuntimeError("No FABDEM data for this bbox")

    obstruction = np.clip(copdem - fabdem, MIN_OBSTRUCTION_M, None)
    n_implausible = int(np.sum(obstruction > MAX_PLAUSIBLE_M))
    if n_implausible:
        log.warning("%d pixel(s) (%.2f%%) exceed %.0fm -- likely tile-edge/data artifacts, capped for zone means",
                     n_implausible, 100 * n_implausible / obstruction.size, MAX_PLAUSIBLE_M)
    obstruction_capped = np.clip(obstruction, MIN_OBSTRUCTION_M, MAX_PLAUSIBLE_M)

    log.info("Basin-wide obstruction height: mean=%.2fm, p90=%.2fm, max=%.1fm",
              float(np.mean(obstruction_capped)), float(np.percentile(obstruction_capped, 90)),
              float(np.max(obstruction)))

    results = {}
    for _, row in grid.iterrows():
        zone_id = row["zone_id"]
        geom = shp_shape(row["geometry"])
        mask = _zone_mask(geom, transform, shape_)
        vals = obstruction_capped[mask]
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            continue
        results[zone_id] = {
            "mean_obstruction_m": round(float(np.mean(vals)), 2),
            "max_obstruction_m": round(float(np.max(vals)), 2),
            "p90_obstruction_m": round(float(np.percentile(vals, 90)), 2),
            "pixel_count": int(len(vals)),
        }

    ranked = sorted(results.items(), key=lambda x: -x[1]["mean_obstruction_m"])
    log.info("Top 5 cells by mean obstruction height:")
    for zid, r in ranked[:5]:
        log.info("  %-16s mean=%.2fm  p90=%.2fm  max=%.2fm", zid, r["mean_obstruction_m"],
                  r["p90_obstruction_m"], r["max_obstruction_m"])

    # Sanity check before trusting this: the CopDEM/FABDEM difference could
    # plausibly be slope/terrain-edge noise rather than a real urban-structure
    # signal (both are ~30m-class DEMs from related processing chains). If
    # it's real, obstruction height should track built-up land cover, not be
    # scattered independent of it -- cross-check against impervious_pct,
    # already computed per cell in the grid this script reads.
    validation = {}
    if "impervious_pct" in grid.columns:
        common = [(results[z]["mean_obstruction_m"], row["impervious_pct"])
                   for z, row in zip(grid["zone_id"], grid.to_dict("records")) if z in results]
        if len(common) > 10:
            obs_vals, imp_vals = zip(*common)
            corr = float(np.corrcoef(obs_vals, imp_vals)[0, 1])
            validation = {"correlation_with_impervious_pct": round(corr, 3), "n_cells": len(common)}
            log.info("Validation: corr(mean_obstruction_m, impervious_pct) = %.3f over %d cells (%s)",
                      corr, len(common),
                      "strong positive, consistent with a real built-structure signal" if corr > 0.5
                      else "weak/absent -- DO NOT TRUST this layer's numbers here. Confirmed failure "
                           "mode (Lower Volta basin, r=0.14): every top-ranked cell had 0% impervious "
                           "land cover but high water occurrence near forested/hilly reservoir terrain "
                           "(Asuogyaman/Akosombo) -- CopDEM and FABDEM diverge on steep, forested slopes "
                           "for reasons unrelated to buildings (forest-canopy correction residuals, "
                           "DEM noise on slopes), which this basin has far more of than the flat Accra "
                           "coastal plain the pilot validated against. This is a real, basin-specific "
                           "limitation of the technique, not a bug -- see docstring.")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "method": "Copernicus DEM (surface model) minus FABDEM (bare-earth) -- a per-cell "
                  "height-above-ground proxy, NOT a building-level layer (both rasters are "
                  "~30m-class; a dense informal settlement blends many small structures into "
                  "one averaged bump per pixel). Reported alongside the composite vulnerability "
                  "score for context, not blended into it -- same discipline as the LULC breakdown.",
        "source_note": f"Copernicus DEM GLO-30 (Planetary Computer) minus {LICENSE_NOTE}",
        "min_obstruction_m": MIN_OBSTRUCTION_M, "max_plausible_m": MAX_PLAUSIBLE_M,
        "n_implausible_pixels_capped": n_implausible,
        "validation": validation,
        "zones": results,
    }, indent=2))
    log.info("Saved -> %s", output)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 8))
        im = ax.imshow(obstruction_capped, cmap="inferno", vmin=0, vmax=np.percentile(obstruction_capped, 98))
        ax.set_title(f"Building/canopy obstruction height (CopDEM - FABDEM)\n{grid_path.name}, "
                      f"mean={np.mean(obstruction_capped):.1f}m")
        plt.colorbar(im, ax=ax, label="meters", fraction=0.04)
        ax.set_xticks([]); ax.set_yticks([])
        diagnostic_png = output.with_name(output.stem + "_diagnostic.png")
        diagnostic_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(diagnostic_png, dpi=130, bbox_inches="tight")
        plt.close(fig)
        log.info("Saved -> %s", diagnostic_png)
    except ImportError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CopDEM-minus-FABDEM obstruction-height layer per risk-grid cell")
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(grid_path=args.grid, output=args.out)
