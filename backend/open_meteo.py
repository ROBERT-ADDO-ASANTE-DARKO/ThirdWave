"""
open_meteo.py — real numerical weather forecast (Open-Meteo, free, no key),
backend port of streamlit_app/features/citizen_forecast.py's
fetch_rainfall_forecast(). Same choice of tool for the same reason: a
numerical forecast needs no historical risk time series to train against,
unlike Prophet (see that module's docstring for the full reasoning this
project already settled on).

The 6h rolling sum is computed in plain Python rather than pulling in
pandas as a new backend dependency for one sliding-window sum -- same
"don't add a dependency for a small thing" judgment call as elsewhere in
this backend.
"""

from __future__ import annotations

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_rainfall_forecast(lat: float, lon: float) -> list[dict]:
    """[{time, precip_mm, rolling_6h_mm}, ...] for the next 7 days,
    hourly. Raises on a request failure -- caller decides how to degrade
    (see routers/forecast.py)."""
    resp = requests.get(
        OPEN_METEO_URL,
        params={"latitude": lat, "longitude": lon, "hourly": "precipitation",
                "forecast_days": 7, "timezone": "Africa/Accra"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()["hourly"]
    times, precip = data["time"], data["precipitation"]

    out = []
    window: list[float] = []
    for t, p in zip(times, precip):
        window.append(p)
        if len(window) > 6:
            window.pop(0)
        out.append({"time": t, "precip_mm": p, "rolling_6h_mm": round(sum(window), 2)})
    return out
