"""
report_confidence.py — composite confidence score for one citizen report,
combining the signals scattered across this project that each bear on
"how much independent evidence backs this specific report," so an
officer sees one number instead of hunting for each signal separately:

  - photo_validation.py: does the submitted photo itself look like
    flooding to an independent AI vision check (auto, cached).
  - clustering.py: how many OTHER reports landed within ~300m of this
    one (more independent witnesses = more confidence).
  - news_corroboration.py: live MyJoyOnline/3News text match (already
    computed per-cluster by routers/reports.py).
  - geo_data.nearby_historical_events(): does this exact location have
    documented flood history (weak signal -- plausible, not confirming).
  - sar_corroboration.py: Sentinel-1 change detection anchored to this
    report's point and date, verified reports only, officer-triggered.

Deliberately not named a "verdict" or "truth score" anywhere in this
module or its output -- same "report, don't auto-decide" discipline as
every signal it's built from. An officer still makes the call; this is
an aid to point attention, not a replacement for it. Bands use their own
vocabulary (Weak/Some corroboration/Well-corroborated/Strongly
corroborated), deliberately NOT the Low/Moderate/High/Very High language
used for a zone's background flood-vulnerability score everywhere else
in this app -- those are a different axis (how flood-prone an area is in
general) and reusing the same words for "how much evidence backs this
one report" would blur the two.
"""

from __future__ import annotations

BASE_SCORE = 15  # every structured, GPS-tagged report carries some baseline credibility over no report at all

BANDS = [
    (80, "Strongly corroborated"),
    (55, "Well-corroborated"),
    (30, "Some corroboration"),
    (0, "Weak"),
]


def _band(score: int) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]


def compute(
    report: dict,
    *,
    vlm_check: dict | None,
    sar_check: dict | None = None,
    n_reports_in_cluster: int = 1,
    news_hit_count: int = 0,
    n_nearby_historical_events: int = 0,
) -> dict:
    """vlm_check: photo_validation.get_or_check()'s return (None if no
    photo). sar_check: sar_corroboration.get_cached()'s return, or None
    for a report that isn't verified yet (SAR corroboration only applies
    once a report is promoted -- see that module's docstring)."""
    score = BASE_SCORE
    signals: dict = {}

    if vlm_check is None:
        signals["photo_check"] = {"status": "no_photo"}
    elif vlm_check.get("status") == "checked":
        if vlm_check["shows_flooding"]:
            score += 25
        else:
            score -= 15
        signals["photo_check"] = vlm_check
    else:
        signals["photo_check"] = vlm_check  # check_failed -- contributes nothing either way

    if n_reports_in_cluster >= 3:
        score += 25
    elif n_reports_in_cluster == 2:
        score += 15
    signals["cluster_size"] = n_reports_in_cluster

    if news_hit_count > 0:
        score += 20
    signals["news_hits"] = news_hit_count

    if n_nearby_historical_events > 0:
        score += 10
    signals["nearby_historical_events"] = n_nearby_historical_events

    if sar_check is None:
        signals["sar"] = {"status": "not_applicable", "detail": "only computed for verified reports"}
    elif sar_check.get("status") == "checked":
        if sar_check["new_flood_at_peak_km2"] > 0.0:
            score += 25
        else:
            score -= 10
        signals["sar"] = sar_check
    else:
        signals["sar"] = sar_check  # not_yet_checked / check_failed -- contributes nothing either way

    score = max(0, min(100, score))
    return {"score": score, "band": _band(score), "signals": signals}
