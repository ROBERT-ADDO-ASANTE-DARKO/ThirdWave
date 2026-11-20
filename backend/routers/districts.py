"""
routers/districts.py — per-assembly composite vulnerability score +
geometry, for the government dashboard's District Vulnerability
Dashboard (Planning). Citizen-facing read, no officer key needed -- same
tier as /zones/* (a static, already-public score, not an internal
workflow).

Three coverage scopes, all backed by real risk_engine/ output, nothing
fabricated to fill a gap:
  - /pilot: the 7-assembly MVP pilot scope (geo_data.py's
    assembly_scores()/assembly_geometries()), full component breakdown.
  - /extended: 11 districts (7 pilot + Ayawaso West, Ga South, Tema,
    Ashaiman), added for regional context, not part of the MVP pilot
    deliverable. Minimal field set -- see
    geo_data.extended_assembly_scores()'s docstring.
  - /lower-volta: 7 Lower Volta basin districts, a separate,
    non-contiguous region added for the 2023 Akosombo/Kpong dam-spillage
    flood history -- see geo_data.lower_volta_assembly_scores()'s
    docstring for the honest caveat about what this score can and can't
    see.

Still a real gap, not faked here: the raw SAR/DEM/WorldCover
evidence-layer raster overlay toggle (risk_engine/data/overlays/,
pilot-scope only in the Streamlit prototype) isn't ported to this
backend yet -- serving georeferenced raster tiles is a separate piece
of work from this composite-score view.
"""

import geopandas as gpd
from fastapi import APIRouter

import geo_data

router = APIRouter(prefix="/districts", tags=["districts"])


def _geojson_response(scores: list[dict], geometries: gpd.GeoDataFrame) -> dict:
    score_by_name = {s["assembly"]: s for s in scores}
    features = []
    for _, row in geometries.iterrows():
        s = score_by_name.get(row["name"])
        if not s:
            continue
        features.append({"type": "Feature", "geometry": row.geometry.__geo_interface__, "properties": s})
    return {"scores": scores, "geojson": {"type": "FeatureCollection", "features": features}}


@router.get("/pilot")
def pilot_districts():
    scores = sorted(geo_data.assembly_scores(), key=lambda r: -r["score"])
    return _geojson_response(scores, geo_data.assembly_geometries())


@router.get("/extended")
def extended_districts():
    return _geojson_response(geo_data.extended_assembly_scores(), geo_data.extended_assembly_geometries())


@router.get("/lower-volta")
def lower_volta_districts():
    return _geojson_response(geo_data.lower_volta_assembly_scores(), geo_data.lower_volta_assembly_geometries())
