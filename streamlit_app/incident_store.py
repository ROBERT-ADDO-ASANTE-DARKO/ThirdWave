"""
incident_store.py — shared session-state store for citizen reports and
verified active incidents, plus the synthetic scenario generator that lets
the pipeline be demoed/tested without live flood data.

Architecture (see project chat history "connecting the dots" discussion):
  citizen report (real or synthetic) --> pending queue, district-assigned
    --> district officer verifies (govt_verification_sandbox.py)
      --> promoted to active_incidents
        --> citizen_routing.py penalizes/avoids nearby road edges at query time

Same st.session_state-only storage as the rest of this POC (see
citizen_report.py's module docstring for why that's an honest scope, not an
oversight) -- this is one shared store instead of each feature keeping its
own, since reports now have to flow between a citizen page and a government
page within one demo session.

Synthetic scenario generation deliberately does NOT use AI agents to "play"
citizen/official roles -- see project chat history: the pipeline's own
verification/routing logic is what needs exercising, not a simulated
persona's judgment, and a scripted generator is more reliable for a live
demo than a handful of non-deterministic LLM round-trips. Report text is
templated from the real simulated depth, not invented independently of it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import streamlit as st
from shapely.geometry import Point

from shapely.geometry import shape

from data_loader import load_assembly_geometries, load_historical_events, load_risk_zones


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def init_store():
    if "pending_reports" not in st.session_state:
        st.session_state.pending_reports = []
    if "active_incidents" not in st.session_state:
        st.session_state.active_incidents = []
    if "resolved_incidents" not in st.session_state:
        st.session_state.resolved_incidents = []


@st.cache_resource
def _assembly_gdf():
    return load_assembly_geometries()


def assign_district(lon: float, lat: float) -> str | None:
    """Point-in-polygon against the 7 pilot assemblies -- same approach
    geo_tools.find_zone_by_address uses, factored out so both the report
    intake and the sandbox generator assign districts identically."""
    pt = Point(lon, lat)
    gdf = _assembly_gdf()
    for _, row in gdf.iterrows():
        if row.geometry.contains(pt):
            return row["name"]
    return None


@st.cache_resource
def _risk_zones():
    return load_risk_zones()


def zone_for_point(lon: float, lat: float) -> dict | None:
    """The 1013-cell fine-grained RiskZone containing this point, if any --
    lets a district officer see the pre-existing static score for a
    report's location as verification context ("this zone is already
    High-risk") instead of judging the report in isolation. Same source
    (risk_zones.json) govt_district_dashboard.py and the AI Assistant use,
    so this can't drift from the score shown everywhere else."""
    pt = Point(lon, lat)
    for z in _risk_zones():
        if shape(z["geometry"]).contains(pt):
            return z
    return None


def submit_report(
    *, lon: float, lat: float, location_label: str, hazard_type: str, description: str,
    depth_estimate_m: tuple[float, float] | None = None, has_photo: bool = False,
    photo_bytes: bytes | None = None, annotated_image_bytes: bytes | None = None,
    ai_assisted: bool = False, synthetic: bool = False, reporter_ref: str = "+233-DEMO-USER",
) -> dict:
    """Adds a report to the pending (unverified) queue, district-assigned.
    Used by both citizen_report.py (real submissions) and the sandbox
    generator (synthetic ones) so both flow through one identical pipeline.

    photo_bytes/annotated_image_bytes are the actual image data, not just
    the has_photo flag -- without these, a district officer had nothing to
    look at but a text description and a depth number when deciding
    whether to verify a report (a real gap, caught when a real officer
    reviewer asked "why can't I see the photo"). Kept as raw bytes in
    session state, same as every other in-memory store in this POC -- not
    base64/JSON, since this never leaves the Python process."""
    init_store()
    district = assign_district(lon, lat)
    report = {
        "id": _new_id("RPT"),
        "reporter_ref": reporter_ref,
        "hazard_type": hazard_type,
        "description": description,
        "has_photo": has_photo,
        "photo_bytes": photo_bytes,
        "annotated_image_bytes": annotated_image_bytes,
        "ai_assisted": ai_assisted,
        "synthetic": synthetic,
        "gps_point": {"lon": lon, "lat": lat},
        "location_label": location_label,
        "district": district,
        "depth_estimate_m": depth_estimate_m,
        "status": "pending",
        "submitted_at": _now_iso(),
    }
    st.session_state.pending_reports.append(report)
    return report


def list_pending(district: str | None = None) -> list[dict]:
    init_store()
    reports = st.session_state.pending_reports
    if district:
        reports = [r for r in reports if r["district"] == district]
    return sorted(reports, key=lambda r: r["submitted_at"], reverse=True)


def list_active_incidents(district: str | None = None) -> list[dict]:
    init_store()
    incidents = st.session_state.active_incidents
    if district:
        incidents = [i for i in incidents if i["district"] == district]
    return sorted(incidents, key=lambda i: i["verified_at"], reverse=True)


def verify_report(report_id: str, approve: bool, verified_by: str = "Demo District Officer") -> dict | None:
    """Removes a report from the pending queue. Approving promotes it to an
    active incident; rejecting drops it (kept in a short rejected log isn't
    needed for this POC's scope)."""
    init_store()
    reports = st.session_state.pending_reports
    idx = next((i for i, r in enumerate(reports) if r["id"] == report_id), None)
    if idx is None:
        return None
    report = reports.pop(idx)
    report["status"] = "verified" if approve else "rejected"
    if approve:
        incident = {
            **report,
            "id": report["id"].replace("RPT-", "INC-"),
            "source_report_id": report["id"],
            "verified_at": _now_iso(),
            "verified_by": verified_by,
            "assigned_responder": None,
            "eta_minutes": None,
            "response_status": "reported",
        }
        st.session_state.active_incidents.append(incident)
        return incident
    return report


def get_incident(incident_id: str) -> dict | None:
    init_store()
    return next((i for i in st.session_state.active_incidents if i["id"] == incident_id), None)


def assign_responder(incident_id: str, responder_name: str, eta_minutes: int) -> dict | None:
    """Writes a responder assignment back onto the shared incident record --
    this is the missing link that lets the at-scene citizen (the original
    reporter) see a real ETA once a district officer deploys someone,
    instead of the assignment only existing inside
    govt_resource_allocation.py's own page-local state. No-ops (returns
    None) if the id isn't a live incident here, e.g. a seeded historical
    demo_seed_incidents.json record that predates this store."""
    init_store()
    inc = get_incident(incident_id)
    if inc is None:
        return None
    inc["assigned_responder"] = responder_name
    inc["eta_minutes"] = eta_minutes
    inc["response_status"] = "responding"
    return inc


def resolve_incident(incident_id: str) -> None:
    init_store()
    incidents = st.session_state.active_incidents
    idx = next((i for i, inc in enumerate(incidents) if inc["id"] == incident_id), None)
    if idx is not None:
        incident = incidents.pop(idx)
        incident["resolved_at"] = _now_iso()
        incident["response_status"] = "resolved"
        st.session_state.resolved_incidents.append(incident)


# ── Proximity (for the "nearby" persona, not just "in transit") ─────────

def _haversine_km(lon1, lat1, lon2, lat2) -> float:
    from math import radians, sin, cos, asin, sqrt
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def nearby_active_incidents(lon: float, lat: float, radius_km: float = 1.5) -> list[dict]:
    """Active incidents within radius_km of a point, each annotated with
    distance_km -- for a citizen who is near a flood, not traveling
    through it (a different persona than Safer Routing's, see project chat
    history)."""
    init_store()
    out = []
    for inc in st.session_state.active_incidents:
        d = _haversine_km(lon, lat, inc["gps_point"]["lon"], inc["gps_point"]["lat"])
        if d <= radius_km:
            out.append({**inc, "distance_km": d})
    return sorted(out, key=lambda i: i["distance_km"])


# ── Synthetic scenario generation ───────────────────────────────────────

_SEVERITY_TEMPLATES = {
    "shallow": [
        "Water pooling on the road, ankle-deep in spots. Traffic slowed but still moving.",
        "Some standing water after the rain -- passable carefully, a few motorbikes stalled.",
    ],
    "moderate": [
        "Water is knee-deep near the junction. Cars are struggling, some have stopped.",
        "Flooding covering the road, water reaching car doors in places. Pedestrians rerouting.",
    ],
    "severe": [
        "Water well above knee height, a vehicle stuck and stalled in the middle of the road.",
        "Serious flooding here -- water is chest-deep in the worst spot, road effectively impassable.",
    ],
}


def _severity_band(depth_m: float) -> str:
    if depth_m < 0.15:
        return "shallow"
    if depth_m < 0.4:
        return "moderate"
    return "severe"


def generate_synthetic_report(
    *, lon: float, lat: float, location_label: str, depth_m: float, rng,
) -> dict:
    """Builds one synthetic (unverified) report from a simulated depth at a
    point -- text is templated by severity band, not independently invented,
    so it stays consistent with the same simulate_ponding() output driving
    the rest of the demo."""
    band = _severity_band(depth_m)
    description = rng.choice(_SEVERITY_TEMPLATES[band])
    hazard_type = "flash_flood" if band == "severe" else "urban_flood"
    lo = max(depth_m - 0.1, 0.0)
    hi = depth_m + 0.1
    return submit_report(
        lon=lon, lat=lat, location_label=location_label, hazard_type=hazard_type,
        description=description, depth_estimate_m=(round(lo, 2), round(hi, 2)),
        has_photo=False, ai_assisted=False, synthetic=True,
        reporter_ref=f"+233-DEMO-SYNTH-{rng.integers(1000, 9999)}",
    )


# Dam-release flooding is NOT rainfall ponding -- simulate_ponding() returns
# ~0 for a point like Tetegu because it isn't a local rain sink, even
# though the real 2026-05-27 Weija spillage submerged homes and forced
# canoe evacuations. So a dam-release scenario is seeded from the DOCUMENTED
# event (deaths/displaced/cause in historical_flood_events.json) and the
# SAR-measured extent (risk_engine/dam_spillage_sar_comparison.py) instead,
# not from the CA model. Depth range reflects "ground floors flooded", the
# consistent signature of these events.
_DAM_RELEASE_TEMPLATES = [
    "Water rising fast from the direction of the dam -- not rain, the level jumped in under an hour. "
    "Ground floors going under, people moving upstairs.",
    "The spillage has reached us. Yard and street are one sheet of water now, maybe waist to chest deep. "
    "Neighbours leaving by canoe.",
    "Downstream of the dam gates -- water is over the doorsteps and still climbing. Some houses already "
    "cut off, no road access.",
    "This is the dam release, not the rain. Water came up to the windowsills on the low side of the "
    "street. Families evacuating with what they can carry.",
]
_DAM_RELEASE_DEPTH_RANGE = (0.8, 2.2)  # metres -- ground-floor inundation typical of these events


def generate_dam_release_report(*, lon: float, lat: float, location_label: str, rng) -> dict:
    """Synthetic report for a dam-release scenario -- severity anchored to
    the documented event pattern (submerged ground floors, upstream-driven,
    canoe evacuation), NOT to simulate_ponding(), which structurally can't
    represent this hazard."""
    lo, hi = _DAM_RELEASE_DEPTH_RANGE
    depth_m = float(rng.uniform(lo, hi))
    return submit_report(
        lon=lon, lat=lat, location_label=location_label, hazard_type="river_flood",
        description=rng.choice(_DAM_RELEASE_TEMPLATES),
        depth_estimate_m=(round(depth_m - 0.2, 2), round(depth_m + 0.2, 2)),
        has_photo=False, ai_assisted=False, synthetic=True,
        reporter_ref=f"+233-DEMO-SYNTH-{rng.integers(1000, 9999)}",
    )


def historical_scenario_points() -> list[dict]:
    """Real documented events with geocoded coordinates, for grounding a
    sandbox scenario in something that actually happened rather than a
    purely invented point."""
    events = load_historical_events()
    return [e for e in events if e.get("lat") is not None and e.get("lon") is not None]
