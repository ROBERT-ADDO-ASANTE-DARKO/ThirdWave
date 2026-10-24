"""
new_juaben_sar_comparison.py — before / during / after Sentinel-1 SAR
water-extent look at AKWADUM-DENSU-FLOOD-2022-10-02 (New Juaben North,
Eastern Region).

Reuses dam_spillage_sar_comparison.py's generic change-detection machinery
(run_event etc.) rather than duplicating it, but lives in its own file
since this is NOT a dam-release event -- it's a river (Densu) overflowing
its banks after sustained heavy rain, the upstream, same-river counterpart
to the Weija Dam spillage floods that script covers. Unlike Kwame Nkrumah
Circle's street-drainage flooding (which SAR structurally can't see), a
river overtopping its floodplain IS real open water -- a genuinely
different physical signature, worth checking rather than assuming SAR is
useless for every Ghana flood.

Same revisit-gap caveat as the September 2026 Weija event: no Sentinel-1
scene lands on the actual flood dates (heavy rain Sept 30 - Oct 3, 2022;
river overflow peaked ~Oct 2), so "peak" here is the nearest same-orbit
scene, 6 days after. Read margins as indicative.

Usage
─────
    python3 new_juaben_sar_comparison.py
"""

from __future__ import annotations

import json
import warnings

import pystac_client
import planetary_computer

from dam_spillage_sar_comparison import run_event, OUT_DIR

warnings.filterwarnings("ignore")

EVENT = {
    "event_id": "AKWADUM-DENSU-FLOOD-2022-10-02",
    "name": "New Juaben North (Akwadum) Densu River flood",
    "bbox": (-0.380, 6.120, -0.340, 6.160),  # Akwadum / Densu floodplain, Koforidua area
    "baseline": "2022-09-27",   # nearest same-orbit scene before the Sept 30 - Oct 3 rain spell
    "peak": "2022-10-09",       # nearest same-orbit scene after the Oct 2-3 peak (6 days later -- no earlier scene)
    "recession": "2022-10-21",  # ~12 days after that
}


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )
    summary = run_event(catalog, EVENT)
    out_path = OUT_DIR / "new_juaben_summary.json"
    out_path.write_text(json.dumps({"events": [summary]}, indent=2))
    print(f"{summary['event_id']}: +{summary['new_flood_at_peak_km2']:.1f} km2 new flood at peak "
          f"({summary['scene_dates']['peak']}), {summary['still_flooded_at_recession_km2']:.1f} km2 "
          f"still flooded by {summary['scene_dates']['recession']}, "
          f"{summary['receded_by_recession_km2']:.1f} km2 receded")
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    run()
