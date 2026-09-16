"""
fabdem_fetch.py — fetch FABDEM (Forest And Buildings removed Copernicus
DEM, Hawker et al. 2022, University of Bristol / Fathom) tiles for a bbox,
via HTTP Range requests against Bristol's regional zip archives -- NOT a
full-archive download.

FABDEM is a bare-earth DEM: it starts from Copernicus GLO-30 and uses a
trained ML correction to strip out forest canopy and building height bias.
That's the opposite of a building-height source -- it's the terrain you
subtract building/canopy heights AWAY FROM. See building_obstruction_height.py
for what this is actually used for: CopDEM (a surface model, includes
building/canopy bias) minus FABDEM (bare earth) = a real, physically
grounded height-above-ground layer, at CopDEM's native 30m.

Why range-requests instead of the `fabdem` PyPI package or a plain
download: Bristol hosts FABDEM as 10x10-degree zip archives (~1.2GB each)
containing one .tif per 1x1-degree cell; a project's actual AOI is
usually a small fraction of one archive. HTTP Range requests let
zipfile.ZipFile parse the central directory and pull out only the needed
member(s) without fetching the whole archive. (The `fabdem` PyPI package
attempts something similar but derives a stale URL for tiles that
straddle the prime meridian/equator -- confirmed by testing: it requests
".../N00W010-N10W000_FABDEM_V1-2.zip", which 404s; the real hosted file is
".../N00W010-N10E000_FABDEM_V1-2.zip". Confirmed against the official
tile index (see TILES_GEOJSON_URL) and Bristol's own dataset page.)

License: FABDEM is CC BY-NC-SA 4.0 (non-commercial, share-alike) --
compatible with this project's current non-commercial pilot status, but
NOT freely redistributable/commercial. Any output derived from it must
carry the same attribution + license disclosure (done in
building_obstruction_height.py's output). Commercial use requires
contacting fabdem@fathom.global.

Usage
─────
    from fabdem_fetch import read_fabdem_window
    fabdem_elev = read_fabdem_window(bbox, (rows, cols))
"""

from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
import rasterio.merge
import rasterio.windows
import rasterio.enums
from rasterio.io import MemoryFile
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DATASET_BASE = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn"
TILES_GEOJSON_URL = f"{DATASET_BASE}/FABDEM_v1-2_tiles.geojson"
LICENSE_NOTE = ("FABDEM V1-2 (Hawker et al. 2022, University of Bristol / Fathom), "
                 "CC BY-NC-SA 4.0 -- non-commercial use only, share-alike.")

HERE = Path(__file__).parent
CACHE_DIR = HERE / "cache" / "fabdem"  # ephemeral, gitignored (see risk_engine/cache/)


class _HTTPRangeFile(io.RawIOBase):
    """Minimal seekable file-like object backed by HTTP Range requests --
    just enough for zipfile.ZipFile to read a remote archive's central
    directory and extract one member, without downloading the whole file."""

    def __init__(self, url: str, session: requests.Session):
        self.url = url
        self.session = session
        self.pos = 0
        r = session.head(url)
        r.raise_for_status()
        self.length = int(r.headers["Content-Length"])

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.length + offset
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        n = len(b)
        end = min(self.pos + n, self.length) - 1
        if end < self.pos:
            return 0
        r = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        r.raise_for_status()
        data = r.content
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def _tile_name(lat_deg: int, lon_deg: int) -> str:
    ns = "N" if lat_deg >= 0 else "S"
    ew = "E" if lon_deg >= 0 else "W"
    return f"{ns}{abs(lat_deg):02d}{ew}{abs(lon_deg):03d}"


def _regional_zip_url(lat_deg: int, lon_deg: int) -> str:
    """10x10-degree archive containing this 1x1 tile. Bristol's own naming
    is inconsistent exactly at the prime-meridian/equator boundary (an
    archive spanning W010..W001 is named with an "E000" upper bound, not
    "W000", even though it contains no E-side tiles) -- confirmed by
    listing a real archive's contents. Handled by trying the straightforward
    name first, then the flipped boundary-token variant."""
    lat0 = (lat_deg // 10) * 10
    lat1 = lat0 + 10
    lon0 = (lon_deg // 10) * 10
    lon1 = lon0 + 10

    def fmt(lat, lon):
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        return f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"

    candidates = [f"{fmt(lat0, lon0)}-{fmt(lat1, lon1)}_FABDEM_V1-2.zip"]
    # Boundary-crossing quirk: the upper-bound token can be recorded as
    # E000 even when lon1 == 0 (i.e. the archive's west edge), or N00 as
    # S00 at the equator -- try the flipped variant too.
    if lon1 == 0:
        candidates.append(f"{fmt(lat0, lon0)}-{fmt(lat1, lon1).replace('W000', 'E000')}_FABDEM_V1-2.zip")
    if lat1 == 0:
        candidates.append(f"{fmt(lat0, lon0)}-{fmt(lat1, lon1).replace('S00', 'N00')}_FABDEM_V1-2.zip")
    return candidates


def _fetch_tile(lat_deg: int, lon_deg: int, session: requests.Session) -> Path | None:
    """Range-fetch one 1x1-degree FABDEM tile, cached to disk so repeat
    calls (e.g. re-running a script, or overlapping AOIs) don't re-hit the
    network."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    name = _tile_name(lat_deg, lon_deg)
    cached = CACHE_DIR / f"{name}_FABDEM_V1-2.tif"
    if cached.exists():
        return cached

    member = f"{name}_FABDEM_V1-2.tif"
    last_exc = None
    for zip_name in _regional_zip_url(lat_deg, lon_deg):
        url = f"{DATASET_BASE}/{zip_name}"
        try:
            f = _HTTPRangeFile(url, session)
        except requests.HTTPError as exc:
            last_exc = exc
            continue
        import zipfile
        try:
            with zipfile.ZipFile(f) as zf:
                if member not in zf.namelist():
                    continue
                log.info("  fetching %s from %s (range request, not full %.0fMB archive)",
                          member, zip_name, f.length / 1e6)
                with zf.open(member) as src, open(cached, "wb") as dst:
                    dst.write(src.read())
                return cached
        except zipfile.BadZipFile as exc:
            last_exc = exc
            continue
    log.warning("  no FABDEM tile found for %s (tried %s): %s", name,
                _regional_zip_url(lat_deg, lon_deg), last_exc)
    return None


def read_fabdem_window(bbox: tuple[float, float, float, float], out_shape: tuple[int, int]) -> np.ndarray | None:
    """FABDEM elevation resampled onto a (rows, cols) grid over bbox
    (minlon, minlat, maxlon, maxlat) -- same calling convention as
    geospatial_vulnerability._read_dem_window, so the two can be
    subtracted pixel-for-pixel once both are read at the same shape."""
    rows, cols = out_shape
    minlon, minlat, maxlon, maxlat = bbox

    lat_tiles = range(math.floor(minlat), math.floor(maxlat) + 1)
    lon_tiles = range(math.floor(minlon), math.floor(maxlon) + 1)

    session = requests.Session()
    tile_paths = []
    for lat_deg in lat_tiles:
        for lon_deg in lon_tiles:
            p = _fetch_tile(lat_deg, lon_deg, session)
            if p:
                tile_paths.append(p)

    if not tile_paths:
        log.warning("No FABDEM tiles found for bbox %s", bbox)
        return None

    datasets = [rasterio.open(p) for p in tile_paths]
    merged, merge_transform = rasterio.merge.merge(datasets)
    for ds in datasets:
        ds.close()

    with MemoryFile() as mf:
        meta = {
            "driver": "GTiff", "count": 1, "dtype": merged.dtype, "crs": "EPSG:4326",
            "transform": merge_transform, "width": merged.shape[2], "height": merged.shape[1],
        }
        with mf.open(**meta) as tmp:
            tmp.write(merged)
        with mf.open() as tmp:
            win = rasterio.windows.from_bounds(minlon, minlat, maxlon, maxlat, tmp.transform)
            elev = tmp.read(
                1, window=win, out_shape=(rows, cols),
                resampling=rasterio.enums.Resampling.bilinear, fill_value=0,
            ).astype(np.float32)
    return elev
