"""
routers/districts.py — per-assembly composite vulnerability score +
geometry, for the government dashboard's District Vulnerability
Dashboard (Planning). Citizen-facing read, no officer key needed -- same
tier as /zones/* (a static, already-public score, not an internal
workflow).

Pilot scope only (7 assemblies): geo_data.py's assembly_scores()/
assembly_geometries() only cover the MVP pilot grid. The Streamlit
version of this feature also offers "Extended coverage" (10 districts)
and "Lower Volta basin" (7 districts) via streamlit_app/data_loader.py
loaders that were never ported to this backend -- a real gap, not
something to fake here with partial data.
"""

from fastapi import APIRouter

import geo_data

router = APIRouter(prefix="/districts", tags=["districts"])


@router.get("/pilot")
def pilot_districts():
    scores = sorted(geo_data.assembly_scores(), key=lambda r: -r["score"])
    score_by_name = {s["assembly"]: s for s in scores}

    features = []
    for _, row in geo_data.assembly_geometries().iterrows():
        s = score_by_name.get(row["name"])
        if not s:
            continue
        features.append({"type": "Feature", "geometry": row.geometry.__geo_interface__, "properties": s})

    return {"scores": scores, "geojson": {"type": "FeatureCollection", "features": features}}
