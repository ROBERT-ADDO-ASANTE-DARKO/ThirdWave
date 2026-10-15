"""
volta_region_2026_sar_comparison.py — before / during / after Sentinel-1
SAR look at two real 2026 Volta Region flood events (KPETOE-TORDZE-FLOOD-
2026-06-29, VOLTA-REGION-FLOODS-2026-07-11), discovered incidentally while
trying to verify a user-recalled place name that couldn't be confirmed.

Reuses dam_spillage_sar_comparison.py's generic run_event() rather than
duplicating it (same pattern as new_juaben_sar_comparison.py).

The Keta/Azizadzi case is a genuinely different signature to look for: per
the source reporting, floodgates were opened there specifically to DRAIN
water into the sea around the event date -- so unlike every dam-spillage
event studied so far (new standing water appearing), this one might show
water DECREASING at the drainage point even while still a real flood
upstream of it. Worth checking, not assuming either direction.

Usage
─────
    python3 volta_region_2026_sar_comparison.py
"""

from __future__ import annotations

import json
import warnings

import pystac_client
import planetary_computer

from dam_spillage_sar_comparison import run_event, OUT_DIR

warnings.filterwarnings("ignore")

EVENTS = [
    {
        "event_id": "KPETOE-TORDZE-FLOOD-2026-06-29",
        "name": "Kpetoe (Tordze River) flood, Agotime Ziope",
        "bbox": (0.677, 6.527, 0.717, 6.567),
        "baseline": "2026-06-28",   # 1 day before the Monday 06-29 rain/flood
        "peak": "2026-07-04",       # nearest same-orbit scene after (5 days later -- no scene 06-30/07-01/02/03)
        "recession": "2026-07-16",  # ~2 weeks after peak
    },
    {
        "event_id": "VOLTA-REGION-FLOODS-2026-07-11",
        "name": "July 2026 Volta Region floods, Azizadzi/Keta drainage point",
        "bbox": (0.971, 5.902, 1.011, 5.942),
        "baseline": "2026-07-04",   # ~1 week before NADMO's 07-11 relief/floodgate-opening report
        "peak": "2026-07-16",       # nearest same-orbit scene after (5 days later)
        "recession": "2026-08-03",  # ~2.5 weeks after peak
        "known_limitation": "Floodgates at this location were reportedly opened to DRAIN water into the sea "
            "around the event date -- the opposite signature of every other event studied (new standing water "
            "appearing), so a flat or negative 'new flood' result here would be consistent with successful "
            "drainage, not evidence against the flood itself, which was real and documented regionally (54,000 "
            "displaced). This bbox is also just the drainage point, not the 66 affected communities as a whole, "
            "most of which are undocumented and ungeocoded.",
    },
]


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    summaries = [run_event(catalog, ev) for ev in EVENTS]
    out_path = OUT_DIR / "volta_region_2026_summary.json"
    out_path.write_text(json.dumps({"events": summaries}, indent=2))
    for s in summaries:
        print(f"{s['event_id']}: +{s['new_flood_at_peak_km2']:.1f} km2 new flood at peak "
              f"({s['scene_dates']['peak']}), {s['still_flooded_at_recession_km2']:.1f} km2 "
              f"still flooded by {s['scene_dates']['recession']}, {s['receded_by_recession_km2']:.1f} km2 receded")
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    run()
