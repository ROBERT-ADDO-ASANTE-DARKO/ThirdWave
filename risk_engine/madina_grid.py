"""
madina_grid.py — build a 500m grid over La-Nkwantanang-Madina Municipal
District (Madina Market, Pantang/Dakubi River), the first new coverage
area added specifically to run a channel-encroachment check, not a full
SAR/DEM/WorldCover vulnerability score (see MADINA-MARKET-FLOOD-2023-06-21
and PANTANG-FLOOD-2026-06-07 in historical_flood_events.json for why this
district was picked).

Scope: channel_encroachment_index.py only needs a grid geojson with
zone_id/assembly/geometry -- it doesn't touch SAR/DEM at all. So this
script only builds that grid (reusing risk_grid.py's build_grid() /
assign_assembly() unchanged), not a full vulnerability-score pipeline.
No composite score exists for this district; only the encroachment index
will, once this grid is fed into channel_encroachment_index.py.

Usage
─────
    python3 madina_grid.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union

from risk_grid import build_grid, assign_assembly, DEG_PER_METER

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
ADMIN2_PATH = HERE / "data" / "gha_admin2.geojson"
OUTPUT = HERE / "data" / "madina_risk_grid.geojson"
ADMIN2_NAME = "La-Nkwantanang-Madina"  # exact match required against gha_admin2.geojson's adm2_name field
ASSEMBLY_LABEL = "La-Nkwantanang-Madina Municipal"  # "Municipal" suffix for consistency with every other
    # assembly name in this project (Weija Gbawe Municipal, Ablekuma North Municipal, ...) and with the
    # "district" field already used in historical_flood_events.json for MADINA-MARKET-FLOOD-2023-06-21 /
    # PANTANG-FLOOD-2026-06-07 -- get_channel_encroachment_for_district and
    # get_satellite_evidence_paths_for_district both need this exact string to agree.
CELL_M = 500.0


def run():
    admin2 = gpd.read_file(ADMIN2_PATH)
    district = admin2[admin2["adm2_name"] == ADMIN2_NAME]
    if district.empty:
        raise RuntimeError(f"{ADMIN2_NAME} not found in {ADMIN2_PATH}")
    boundary_geom = unary_union(district.geometry)
    log.info("%s boundary: %.2f km2 (admin2 source)", ADMIN2_NAME, district.iloc[0]["area_sqkm"])

    cell_deg = CELL_M * DEG_PER_METER
    cells = build_grid(boundary_geom, cell_deg)
    log.info("Built %d grid cells (%.0fm)", len(cells), CELL_M)

    # Single-district boundary -- assign_assembly against a 1-row gdf just
    # labels every cell with this district's own name (keeps the field
    # consistent with every other grid's "assembly" column, which
    # get_channel_encroachment_for_district already reads).
    assemblies_gdf = gpd.GeoDataFrame({"name": [ASSEMBLY_LABEL]}, geometry=[boundary_geom], crs=district.crs)

    features = []
    for c in cells:
        zone_id = f"madina_r{c['row']}_c{c['col']}"
        assembly = assign_assembly(c["geometry"], assemblies_gdf)
        features.append({
            "type": "Feature",
            "geometry": mapping(c["geometry"]),
            "properties": {
                "zone_id": zone_id, "assembly": assembly,
                "boundary_overlap_frac": c["boundary_overlap_frac"],
            },
        })

    OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))
    log.info("Saved -> %s (%d cells)", OUTPUT, len(features))


if __name__ == "__main__":
    run()
