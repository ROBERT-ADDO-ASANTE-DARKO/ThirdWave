"""
Feature 2 — Incoming Reports Queue (Government).

The live counterpart to Incident Verification's demo sandbox: that page
(govt_verification_sandbox.py) verifies/seeds reports against
incident_store.py's in-memory session state, which exists so a live demo
can seed synthetic scenarios with no real flood happening. This page
instead drives the real backend DB over HTTP (same pattern
govt_briefing_review.py / govt_incident_map.py established), showing the
full Pending -> Verified -> Responding -> Resolved lifecycle
(backend/models.py's Report.status + response_status) and the actions
that move a report through it: verify/reject, assign a responder, mark
resolved. Deliberately does not seed synthetic data itself -- that would
mean writing fake reports into the same database real citizen submissions
land in; Incident Verification's isolated sandbox is still the right tool
for that.

Resource allocation (assigning a *specific* real responder from a real
roster) is a separate, still-open feature -- see GOVT_DASHBOARD_PHASES.md
#4. Assigning here just records a free-text responder name + ETA, same
fields AssignResponderBody already defines.

Every card also shows feature #3's composite confidence score (backend/
report_confidence.py), computed server-side and attached to each report
by the endpoints above -- this page only renders it, including a
"Run satellite (SAR) check" button for verified/responding incidents
that triggers backend/sar_corroboration.py's deliberately-manual,
cached Sentinel-1 check.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

from data_loader import LEVEL_COLOR, INK_NAVY, STEEL_BLUE, SIGNAL_TEAL

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

BACKEND_URL = os.environ.get("THIRDWAVE_BACKEND_URL", "http://localhost:8000")

# Feature #3's confidence bands get their own palette, deliberately NOT
# LEVEL_COLOR -- "how much evidence backs this one report" and "how
# flood-prone this area is in general" are different axes; reusing the
# same Low/Moderate/High/Very High colors would blur them. Reuses the
# design system's existing navy/steel-blue/teal tokens plus the same gray
# citizen_app/lib/risk_colors.dart uses for "unknown" -- new meaning,
# borrowed hues, not a second ad-hoc palette.
CONFIDENCE_COLOR = {
    "Weak": "#6B7280",
    "Some corroboration": STEEL_BLUE,
    "Well-corroborated": SIGNAL_TEAL,
    "Strongly corroborated": INK_NAVY,
}


def _headers(officer_key: str) -> dict:
    return {"X-Officer-Key": officer_key}


def _get(path: str, officer_key: str, **params):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, headers=_headers(officer_key), timeout=10)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _post(path: str, officer_key: str, json_body: dict):
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", json=json_body, headers=_headers(officer_key), timeout=15)
        if resp.status_code >= 400:
            return None, resp.json().get("detail", resp.text)
        return resp.json(), None
    except Exception as exc:
        return None, str(exc)


def _zone_badge(zone: dict | None) -> None:
    if not zone:
        st.caption("\U0001F4CD This location falls outside all scored coverage (pilot or extended) -- no pre-existing static score to cross-check against.")
        return
    color = LEVEL_COLOR.get(zone["level"], "#999")
    ext_tag = " (extended-coverage grid)" if zone.get("extended") else ""
    st.markdown(
        f"<span style='background:{color}22;border:1px solid {color};color:{color};"
        f"border-radius:3px;padding:1px 7px;font-size:0.82rem;'>"
        f"\U0001F4CD Verification context: this zone's existing static score is "
        f"<b>{zone['score']:.1f} ({zone['level']})</b>{ext_tag}</span>",
        unsafe_allow_html=True,
    )
    if zone.get("extended"):
        st.caption(
            "Extended-coverage grid, not the MVP pilot -- same statistical SAR/DEM/land-cover "
            "formula, which structurally can't see a one-off event like a dam release."
        )


def _confidence_detail_lines(signals: dict) -> list[str]:
    lines = []
    pc = signals["photo_check"]
    if pc["status"] == "no_photo":
        lines.append("No photo submitted.")
    elif pc["status"] == "checked":
        verdict = "shows flooding" if pc["shows_flooding"] else "does **not** show flooding"
        lines.append(f"Photo AI check: {verdict} -- {pc.get('note') or 'no further detail'}")
    else:
        lines.append(f"Photo AI check failed: {pc.get('detail', 'unknown error')}")

    n = signals["cluster_size"]
    lines.append(f"{n} independent report(s) within ~300m." if n > 1 else "Only 1 report at this location so far.")
    lines.append(f"{signals['news_hits']} corroborating news hit(s) (last 72h)." if signals["news_hits"]
                 else "No corroborating news found.")
    lines.append(f"{signals['nearby_historical_events']} documented flood event(s) nearby."
                 if signals["nearby_historical_events"] else "No documented flood history nearby.")

    sar = signals["sar"]
    if sar["status"] == "checked":
        lines.append(f"Satellite (SAR) check: {sar['verdict']}")
    elif sar["status"] == "not_yet_checked":
        lines.append("Satellite (SAR) check: not yet run.")
    elif sar["status"] == "not_applicable":
        lines.append("Satellite (SAR) check: only available once verified.")
    else:
        lines.append(f"Satellite (SAR) check failed: {sar.get('detail', 'unknown error')}")
    return lines


def _confidence_badge(confidence: dict | None) -> None:
    if not confidence:
        return
    color = CONFIDENCE_COLOR.get(confidence["band"], "#6B7280")
    st.markdown(
        f"<span style='background:{color}1A;border:1px solid {color};color:{color};"
        f"border-radius:3px;padding:1px 7px;font-size:0.82rem;'>"
        f"\U0001F9E0 Confidence: <b>{confidence['score']}/100 ({confidence['band']})</b></span>",
        unsafe_allow_html=True,
    )
    with st.expander("Why this score? (aid, not a verdict -- use your own judgment)", expanded=False):
        for line in _confidence_detail_lines(confidence["signals"]):
            st.caption(f"• {line}")


def _sar_check_button(report_id: str, officer_key: str) -> None:
    if st.button("\U0001F6F0️ Run satellite (SAR) check", key=f"sar_{report_id}"):
        with st.spinner("Querying Sentinel-1 -- this can take up to a minute..."):
            _, err = _post(f"/incidents/{report_id}/sar-check", officer_key, {})
        if err:
            st.error(err)
        st.rerun()


def _render_pending_card(r: dict, officer_key: str) -> None:
    badge = " \U0001F9EA SYNTHETIC" if r.get("synthetic") else ""
    district = r["district"] or "outside pilot district"
    c_img, c1, c2 = st.columns([1.4, 3.1, 1])
    with c_img:
        photo_url = r.get("annotated_photo_url") or r.get("photo_url")
        if photo_url:
            st.image(f"{BACKEND_URL}{photo_url}", use_container_width=True,
                      caption="AI-annotated" if r.get("annotated_photo_url") else "Submitted photo")
        elif r.get("has_photo"):
            st.caption("Photo submitted, but no confident AI annotation was produced.")
        else:
            st.caption("No photo submitted with this report.")
    with c1:
        st.markdown(f"`{r['id']}`{badge} — **{r['hazard_type'].replace('_', ' ').title()}** — {district}")
        st.caption(r["location_label"] or f"{r['lat']:.4f}, {r['lon']:.4f}")
        st.write(r["description"])
        if r.get("depth_hi_m") is not None:
            st.caption(f"Estimated depth: {r['depth_lo_m']:.1f}-{r['depth_hi_m']:.1f}m")
        _zone_badge(r.get("zone"))
        _confidence_badge(r.get("confidence"))
    with c2:
        if st.button("✅ Verify", key=f"verify_{r['id']}", type="primary"):
            _, err = _post(f"/reports/{r['id']}/verify", officer_key, {"approve": True})
            if err:
                st.error(err)
            st.rerun()
        if st.button("❌ Reject", key=f"reject_{r['id']}"):
            _, err = _post(f"/reports/{r['id']}/verify", officer_key, {"approve": False})
            if err:
                st.error(err)
            st.rerun()


def _render_pending_section(officer_key: str):
    st.markdown("**Pending — verify or reject**")
    st.caption(
        "Reports within ~300m of each other are grouped as one likely flood event (backend/clustering.py), "
        "worst (most reports) first -- review and act on a cluster at once instead of report by report."
    )
    clusters, err = _get("/reports/clusters", officer_key)
    if err:
        st.error(f"Could not load pending reports: {err}")
        return
    if not clusters:
        st.info("No pending reports. Citizens submit these via the mobile app's Crowdsourced Flood Reporting.")
        return

    for cluster in clusters:
        reports = cluster["reports"]
        n = cluster["n_reports"]
        with st.container(border=True):
            if n > 1:
                hz = ", ".join(h.replace("_", " ").title() for h in cluster["hazard_types"])
                syn = " · includes synthetic" if cluster["any_synthetic"] else ""
                c_hdr, c_v, c_r = st.columns([4, 1, 1])
                with c_hdr:
                    st.markdown(f"**\U0001F5C2️ Incident cluster — {n} reports** — {hz} — {cluster['district'] or 'outside pilot district'}{syn}")
                with c_v:
                    if st.button(f"✅ Verify all {n}", key=f"verify_cluster_{reports[0]['id']}", type="primary"):
                        _, err = _post("/reports/verify-bulk", officer_key,
                                       {"report_ids": [r["id"] for r in reports], "approve": True})
                        if err:
                            st.error(err)
                        st.rerun()
                with c_r:
                    if st.button(f"❌ Reject all {n}", key=f"reject_cluster_{reports[0]['id']}"):
                        _, err = _post("/reports/verify-bulk", officer_key,
                                       {"report_ids": [r["id"] for r in reports], "approve": False})
                        if err:
                            st.error(err)
                        st.rerun()
                st.markdown("---")

            hits = cluster.get("corroborating_news") or []
            if hits:
                with st.expander(f"\U0001F4F0 {len(hits)} possibly-related news report(s) (last 72h, unverified match)", expanded=False):
                    st.caption(
                        "Place-name text match on live MyJoyOnline/3News RSS feeds, not a confirmed link to "
                        "these reports -- context for your own judgment, not a substitute for it."
                    )
                    for h in hits:
                        st.markdown(f"- [{h['title']}]({h['link']}) — *{h['source']}*, {h['published'][:16].replace('T', ' ')} UTC")

            for i, r in enumerate(reports):
                if i > 0:
                    st.markdown("<hr style='margin:4px 0;opacity:0.25'>", unsafe_allow_html=True)
                _render_pending_card(r, officer_key)


def _render_verified_section(active: list[dict], officer_key: str):
    awaiting = [i for i in active if i.get("response_status") != "responding"]
    st.markdown("**Verified — awaiting a responder**")
    if not awaiting:
        st.caption("Nothing verified is waiting on a responder right now.")
    for inc in awaiting:
        badge = " \U0001F9EA SYNTHETIC" if inc.get("synthetic") else ""
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.3, 1])
            with c1:
                st.markdown(f"`{inc['id']}`{badge} — **{inc['hazard_type'].replace('_', ' ').title()}** — {inc['district'] or 'outside pilot district'}")
                st.caption(f"{inc['location_label']} · verified {inc['verified_at'][:16].replace('T', ' ')} UTC")
                _zone_badge(inc.get("zone"))
                _confidence_badge(inc.get("confidence"))
                _sar_check_button(inc["id"], officer_key)
            with c2:
                responder = st.text_input("Responder", key=f"responder_{inc['id']}", placeholder="e.g. NADMO Accra Team 3", label_visibility="collapsed")
            with c3:
                eta = st.number_input("ETA (min)", key=f"eta_{inc['id']}", min_value=1, max_value=240, value=20, step=5, label_visibility="collapsed")
            if st.button("Assign responder", key=f"assign_{inc['id']}", type="primary"):
                if not responder.strip():
                    st.error("Enter a responder name first.")
                else:
                    _, err = _post(f"/incidents/{inc['id']}/assign-responder", officer_key,
                                   {"responder_name": responder.strip(), "eta_minutes": int(eta)})
                    if err:
                        st.error(err)
                    st.rerun()


def _render_responding_section(active: list[dict], officer_key: str):
    responding = [i for i in active if i.get("response_status") == "responding"]
    st.markdown("**Responding**")
    if not responding:
        st.caption("No responder currently en route.")
    for inc in responding:
        badge = " \U0001F9EA SYNTHETIC" if inc.get("synthetic") else ""
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"`{inc['id']}`{badge} — **{inc['hazard_type'].replace('_', ' ').title()}** — {inc['district'] or 'outside pilot district'}")
                st.caption(
                    f"{inc['location_label']} · {inc['assigned_responder']}, ETA {inc['eta_minutes']} min"
                )
                _confidence_badge(inc.get("confidence"))
                _sar_check_button(inc["id"], officer_key)
            with c2:
                if st.button("Mark resolved", key=f"resolve_{inc['id']}"):
                    _, err = _post(f"/incidents/{inc['id']}/resolve", officer_key, {})
                    if err:
                        st.error(err)
                    st.rerun()


def _render_resolved_section(officer_key: str):
    resolved, err = _get("/incidents/resolved", officer_key, limit=20)
    with st.expander(f"**Resolved** — most recent {len(resolved) if resolved else 0}", expanded=False):
        if err:
            st.error(f"Could not load resolved incidents: {err}")
            return
        if not resolved:
            st.caption("No resolved incidents yet.")
            return
        for inc in resolved:
            badge = " \U0001F9EA SYNTHETIC" if inc.get("synthetic") else ""
            conf = inc.get("confidence")
            conf_txt = f" — confidence {conf['score']}/100 ({conf['band']})" if conf else ""
            st.markdown(
                f"`{inc['id']}`{badge} — {inc['hazard_type'].replace('_', ' ').title()} — "
                f"{inc['district'] or 'outside pilot district'} — "
                f"resolved {inc['resolved_at'][:16].replace('T', ' ')} UTC{conf_txt}"
            )


def render():
    st.subheader("Incoming Reports Queue")
    st.caption(
        "Live backend queue (real citizen + officer-verified data), distinct from Incident "
        "Verification's isolated demo sandbox. Tracks every report through "
        "Pending → Verified → Responding → Resolved."
    )

    officer_key = os.environ.get("OFFICER_API_KEY")
    if not officer_key:
        st.error("OFFICER_API_KEY not found in backend/.env -- cannot reach officer-gated endpoints.")
        return

    active, a_err = _get("/incidents/active", officer_key)
    if a_err:
        st.error(f"Could not load active incidents: {a_err}")
        active = []
    pending, p_err = _get("/reports/pending", officer_key)
    if p_err:
        pending = []

    n_responding = sum(1 for i in active if i.get("response_status") == "responding")
    k1, k2, k3 = st.columns(3)
    k1.metric("Pending", len(pending))
    k2.metric("Verified, awaiting responder", len(active) - n_responding)
    k3.metric("Responding", n_responding)

    st.divider()
    _render_pending_section(officer_key)
    st.divider()
    _render_verified_section(active, officer_key)
    st.divider()
    _render_responding_section(active, officer_key)
    st.divider()
    _render_resolved_section(officer_key)
