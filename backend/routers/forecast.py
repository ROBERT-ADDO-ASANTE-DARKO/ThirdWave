"""
routers/forecast.py — Phase 4 feature #3 (Rainfall Forecast). Citizen-
facing, no officer key needed.

Honest scope limit carried over unchanged from citizen_forecast.py: the
live rule engine (thresholds.py) needs BOTH rainfall AND river level to
reach Warning/Critical; there's no river-level forecast source, so this
is a rainfall-only read against this zone's rainfall_6h_warning_mm/
rainfall_6h_critical_mm, not the full dual-factor engine.
"""

from fastapi import APIRouter

import geo_data
import open_meteo

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/rainfall")
def rainfall(lat: float, lon: float):
    zone = geo_data.zone_for_point(lon, lat)
    if not zone:
        return {"error": "This location is outside the pilot grid -- no zone-specific thresholds available."}

    zone_id = zone["id"].replace("RZ-", "")
    thresh = geo_data.grid_thresholds().get(zone_id)
    if not thresh:
        return {"error": "This location is outside the pilot grid -- no zone-specific thresholds available."}

    try:
        hourly = open_meteo.fetch_rainfall_forecast(lat, lon)
    except Exception as exc:
        return {"error": f"Forecast unavailable: {exc}"}

    warn_mm = thresh["rainfall_6h_warning_mm"]
    crit_mm = thresh["rainfall_6h_critical_mm"]
    peak = max(hourly, key=lambda h: h["rolling_6h_mm"])
    max_forecast = peak["rolling_6h_mm"]

    if max_forecast >= crit_mm:
        status, message = "critical", (
            f"Critical rainfall forecast: {max_forecast:.0f}mm/6h expected around {peak['time']} "
            "-- exceeds this zone's critical threshold."
        )
    elif max_forecast >= warn_mm:
        status, message = "warning", (
            f"Warning-level rainfall forecast: {max_forecast:.0f}mm/6h expected around {peak['time']} "
            "-- exceeds this zone's warning threshold."
        )
    else:
        status, message = "ok", (
            f"No rainfall in the 7-day forecast is expected to exceed this zone's warning threshold "
            f"({warn_mm:.0f}mm/6h). Peak forecast: {max_forecast:.0f}mm/6h."
        )

    return {
        "zone_id": zone_id, "vulnerability_score": thresh["vulnerability_score"],
        "warning_mm": warn_mm, "critical_mm": crit_mm,
        "hourly": hourly, "max_forecast_mm": max_forecast, "peak_time": peak["time"],
        "status": status, "message": message,
    }
