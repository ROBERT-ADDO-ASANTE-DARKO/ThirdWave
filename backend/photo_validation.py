"""
photo_validation.py — independent AI re-check of a report's OWN submitted
photo, for the confidence score (report_confidence.py). Separate from
vlm_client.py's draft flow: that one helps the citizen WRITE a report
before submission (routers/reports.py's POST /reports/draft) and nothing
it returns is persisted. This module re-runs the same describe_flood_photo()
AFTER submission, against the photo that actually landed in the row, to
answer a different question -- "does this submitted photo itself look
like flooding to an independent check" -- not "what should the citizen
write."

Cached by report id in vlm_checks.json (one real Anthropic vision call
per report, not per page load) -- same discipline sar_corroboration.py
and risk_engine/citizen_report_sar_check.py already use for their own
checks, just with a cheap/fast signal instead of an expensive/slow one,
so this one runs automatically and synchronously rather than needing an
explicit officer-triggered button.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "vlm_checks.json"
UPLOADS_DIR = Path(__file__).parent / "uploads"


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def get_or_check(report: dict) -> dict | None:
    """report: a serialized report dict (serializers.serialize_report()'s
    shape -- uses id/photo_url). Returns None if there's no photo to check
    at all (not cached as a result -- a report submitted without a photo
    stays uncheckable forever, not "not yet checked"). Returns
    {"status": ...} otherwise, cached after the first call."""
    photo_url = report.get("photo_url")
    if not photo_url:
        return None
    photo_path = photo_url.removeprefix("/uploads/")

    cache = _load_cache()
    cached = cache.get(report["id"])
    if cached:
        return cached

    import vlm_client  # lazy: avoid pulling in the anthropic SDK for callers that only read the cache

    image_path = UPLOADS_DIR / photo_path
    if not image_path.exists():
        result = {"status": "check_failed", "detail": "stored photo file missing on disk"}
    else:
        try:
            vlm_result = vlm_client.describe_flood_photo(image_path.read_bytes())
            result = {
                "status": "checked",
                "shows_flooding": vlm_result["shows_flooding"],
                "suggested_hazard_type": vlm_result.get("suggested_hazard_type"),
                "note": vlm_result.get("note"),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except vlm_client.VLMError as exc:
            result = {"status": "check_failed", "detail": str(exc)}

    cache[report["id"]] = result
    _save_cache(cache)
    return result
