"""
briefing_queue.py — shared helper for the "semi-automatic flagging" trigger
described in .claude/plans/temporal-waddling-trinket.md: when a risk_engine
script finds something district-briefing-worthy (a new Very High
channel-encroachment cell, a new historical flood event), it calls
flag_district() here instead of the project building a real scheduler.
This just appends a deduplicated line to data/briefing_queue.json; the
Streamlit government dashboard reads that file and shows a banner so an
Operations Officer can manually trigger drafting (see
streamlit_app/features/govt_briefing_review.py). No automatic drafting or
sending happens from this module -- it only raises a flag for a human.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

QUEUE_PATH = Path(__file__).parent / "data" / "briefing_queue.json"


def flag_district(district: str, reason: str, source_finding: str) -> None:
    """Append a flag for `district` unless an un-reviewed flag with the same
    (district, reason) already exists -- re-running a script shouldn't pile
    up duplicate banner entries for the same finding."""
    queue = []
    if QUEUE_PATH.exists():
        queue = json.loads(QUEUE_PATH.read_text())

    for entry in queue:
        if entry["district"] == district and entry["reason"] == reason:
            entry["source_finding"] = source_finding
            entry["flagged_at"] = datetime.now(timezone.utc).isoformat()
            QUEUE_PATH.write_text(json.dumps(queue, indent=2))
            return

    queue.append({
        "district": district, "reason": reason, "source_finding": source_finding,
        "flagged_at": datetime.now(timezone.utc).isoformat(),
    })
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def clear_district(district: str) -> None:
    """Called once a Briefing for this district has been drafted, so the
    dashboard banner doesn't keep nagging about a finding that's already
    being acted on."""
    if not QUEUE_PATH.exists():
        return
    queue = json.loads(QUEUE_PATH.read_text())
    queue = [e for e in queue if e["district"] != district]
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
