"""routers/drain_priority.py — Feature 3 (govt dashboard), officer-gated.
Ranks pilot-grid zones for drain/channel maintenance budget allocation,
combining the composite vulnerability score with OSM-derived channel-
encroachment proximity -- mirrors streamlit_app/features/govt_drain_priority.py's
priority formula exactly (simple, explainable boost: closer building-to-
waterway distance -> higher priority), computed server-side here instead
of in a pandas DataFrame.

"Persistent hotspot" in this view means multi-year SAR water occurrence
(2020-2024 aggregate), not verified repeat-incident history -- that needs
live pilot incident_outcome_link data this project doesn't have yet.

Zones with insufficient OSM coverage are returned separately as
"without_data" rather than silently dropped or ranked as low-priority --
missing data is not the same as low risk."""

from fastapi import APIRouter, Depends

import geo_data
from auth import require_officer

router = APIRouter(prefix="/drain-priority", tags=["drain-priority"])


def _priority_boost(min_dist_m: float) -> int:
    if min_dist_m <= 10:
        return 30
    if min_dist_m <= 30:
        return 15
    if min_dist_m <= 75:
        return 5
    return 0


@router.get("", dependencies=[Depends(require_officer)])
def drain_priority():
    obstruction = geo_data.obstruction_height()["zones"]

    with_data = []
    without_data = []
    for z in geo_data.risk_zones():
        zid = z["id"].replace("RZ-", "")
        enc = next((f for f in z["contributing_factors"] if f["type"] == "channel_encroachment"), None)
        has_data = enc is not None and not enc.get("data_insufficient", True)
        if has_data:
            obs = obstruction.get(zid)
            with_data.append({
                "zone_id": zid,
                "assembly": z["assembly"],
                "score": z["score"],
                "level": z["level"],
                "confidence": z["confidence"],
                "min_dist_m": enc["value"],
                "encroachment_text": enc["text"],
                "obstruction_m": obs["mean_obstruction_m"] if obs else None,
                "priority": z["score"] + _priority_boost(enc["value"]),
                "geometry": z["geometry"],
            })
        else:
            without_data.append({
                "zone_id": zid,
                "assembly": z["assembly"],
                "score": z["score"],
                "level": z["level"],
            })

    with_data.sort(key=lambda r: -r["priority"])
    without_data.sort(key=lambda r: -r["score"])
    return {"with_data": with_data, "without_data": without_data}
