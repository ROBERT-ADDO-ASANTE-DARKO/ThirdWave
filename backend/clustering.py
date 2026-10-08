"""
clustering.py — group pending reports into spatial clusters so an officer
reviews "23 reports at one flooded junction" as one unit instead of 23
separate decisions.

Ported from streamlit_app/incident_store.py's cluster_pending() /
_severity_rank(), adapted to take an already-fetched list[dict] of reports
(the backend fetches from the DB; the Streamlit version pulled from
st.session_state internally) rather than re-implemented logic -- same
complete-linkage algorithm, same 300m threshold, same reasoning for both
(see incident_store.py's module comment for why complete linkage and why
300m). Duplicated rather than imported: this package must stay
installable/runnable without a Streamlit dependency. Worth collapsing into
one shared module once streamlit_app is repointed at this backend instead
of its own session state (see project's phased mobile-app plan) and
incident_store.py's copy is retired rather than kept in sync by hand.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

CLUSTER_RADIUS_KM = 0.3

_HAZARD_SEVERITY = {"river_flood": 1.0, "flash_flood": 0.7, "urban_flood": 0.3}


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def _severity_rank(report: dict) -> float:
    if report.get("depth_hi_m") is not None:
        return report["depth_hi_m"]
    return _HAZARD_SEVERITY.get(report["hazard_type"], 0.0)


def cluster_reports(reports: list[dict]) -> list[dict]:
    """reports: dicts with at least id/lon/lat/district/hazard_type/
    depth_hi_m/synthetic/submitted_at (the shape routers/reports.py
    serializes a Report row into). Returns clusters worst-first, each:
    reports, n_reports, centroid, district, max_severity, hazard_types,
    any_synthetic."""
    if not reports:
        return []
    if len(reports) == 1:
        labels = [1]
    else:
        n = len(reports)
        dist = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = haversine_km(reports[i]["lon"], reports[i]["lat"], reports[j]["lon"], reports[j]["lat"])
                dist[i, j] = dist[j, i] = d
        labels = fcluster(linkage(squareform(dist, checks=False), method="complete"),
                           t=CLUSTER_RADIUS_KM, criterion="distance")

    groups: dict[int, list[dict]] = {}
    for r, lab in zip(reports, labels):
        groups.setdefault(int(lab), []).append(r)

    clusters = []
    for members in groups.values():
        lons = [m["lon"] for m in members]
        lats = [m["lat"] for m in members]
        clusters.append({
            "reports": sorted(members, key=lambda r: r["submitted_at"], reverse=True),
            "n_reports": len(members),
            "centroid": {"lon": sum(lons) / len(lons), "lat": sum(lats) / len(lats)},
            "district": members[0]["district"],
            "max_severity": max(_severity_rank(m) for m in members),
            "hazard_types": sorted({m["hazard_type"] for m in members}),
            "any_synthetic": any(m.get("synthetic") for m in members),
        })
    return sorted(clusters, key=lambda c: (-c["n_reports"], -c["max_severity"]))
