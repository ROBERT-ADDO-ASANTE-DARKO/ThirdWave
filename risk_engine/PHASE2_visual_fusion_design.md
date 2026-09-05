# Phase 2 Design Note — Spatial-Visual Multimodal Fusion

**Status:** design sketch, not implemented. Captured 2026-08-29 so the reasoning survives until this gets picked up.

## Motivation

The static vulnerability grid (`risk_grid.py`, SAR + DEM + LULC at 500m cells) has two documented blind spots that a geotagged street-level photo can fix, cheaply, at the exact point it was taken:

1. **Hidden drainage bottlenecks.** Kwame Nkrumah Circle's own grid cell scored 33 while its immediate neighbor scored 44 (see `historical_backtest.py` results) — plausibly because a specific culvert/underpass structure drives the real risk there and isn't resolvable at 100m raster resolution. The Trepekli et al. 2022 UAV-LiDAR paper on Accra found the same thing: archways, bridges and boundary walls determine actual flow paths and are invisible below ~1m resolution. A photo standing at that exact spot sees what the satellite can't.
2. **Canopy occlusion.** Dense tree cover degrades Sentinel-2 (fully blocked) and partially attenuates Sentinel-1 backscatter. A street-level photo isn't affected by what's overhead.

Ground photos are a free, already-available proxy for what a targeted LiDAR survey would give at specific hotspots — see the LiDAR discussion in project chat history — without the acquisition cost.

## Architecture

Spatial-join citizen report photos (via `CitizenReport.gps_point`, already in the spec's data model §9) to their containing `risk_grid.py` cell.

- **Cell with no photo evidence:** score is the satellite+topographic baseline, unchanged. This is the default and will be true for most cells for a long time.
- **Cell with verified photo evidence:** the VLM-derived depth/severity estimate (see `image_depth_estimation_poc.json` for the underlying technique — zero-shot reasoning against known object dimensions, no training/hosting required) corrects the baseline for that cell.

## Two distinct consumers — do not conflate them

A citizen photo is inherently a **lagging** signal (it only exists after someone stood in the flood), which means it serves two different purposes with two different update rules:

| | Static vulnerability grid | Live incident severity |
|---|---|---|
| Purpose | Pre-event risk, calibrates `ZoneThresholdConfig` | In-progress incident, drives `Incident.severity` / responder dispatch |
| Update cadence | Accumulate over a season, like `incident_outcome_link`/`risk_prediction_log` already do | Immediate, single-photo weight is appropriate |
| A single fresh photo should... | NOT swing the baseline on its own | Directly inform current severity |

Designing one fusion rule to serve both would either make the live response too slow (waiting for accumulated evidence) or make the baseline too noisy (one photo permanently distorting a cell's score).

## Non-negotiable: route through the existing verification gate

Spec §2.2 states citizen-report human verification is non-deferrable, "no shortcuts, even in a small pilot." A photo's VLM-derived severity must **only** feed the correction pathway after an Operations Officer has verified the report — never before. An unverified submission can still surface in the officer's queue, e.g. sorted by AI-estimated severity to help triage, but must not touch any live-facing score pre-verification. This is the one place a naive implementation could accidentally violate a rule the spec calls non-deferrable, so it's worth stating explicitly rather than assuming it'll be obvious at implementation time.

## Correction mechanism — keep it legible

Every design choice that's worked in this project so far has been the transparent option over the black-box one (rule-based thresholds over ML; LULC reported-not-weighted rather than folded into the score). Same principle here: a confidence-weighted, inspectable correction, not a fused model score nobody can explain to a district officer.

Sketch:

```
corrected_score = baseline_score + adjustment

adjustment = f(n_verified_photos_recent, mean_photo_severity, baseline_score)
```

Displayed in the Risk Detail Drawer as something like:
> "Baseline: 33 (satellite/terrain). +2 verified citizen photos in the last 14 days → adjusted to 41."

Exact functional form (linear blend vs. Bayesian update vs. simple override) is undecided — worth prototyping against real pilot data once it exists rather than designing blind now.

## Staleness / decay

Same fail-safe discipline already enforced in `thresholds.py` (§8.4: never silently show stale data) applies here. A photo from a year ago should not still be propping up today's score. Needs an explicit decay window, analogous to `valid_from`/`valid_to`/`computed_at` already used elsewhere in the risk engine.

## Known caveat: GPS accuracy

Phone GPS in dense urban canyons (e.g. around Circle's tall buildings) can be off by tens of meters, sometimes more. Probably tolerable against 500m cells, but this is an assumption to state explicitly, not something to discover later when a photo lands in the wrong cell.

## Data model — mostly already there

- `CitizenReport.gps_point` (spec §9) — already sufficient for the spatial join.
- `RiskZone.contributing_factors` (spec §9) — already the right place to disclose "corrected by N verified photos."
- New, not yet in spec: something like `RiskZone.ground_photo_corrected: bool` and a confidence/count field, plus whatever table tracks the correction's decay window.

## Open questions (not decided — flag before implementing)

1. Exact correction formula (linear/Bayesian/override) — needs real pilot data to tune sensibly.
2. Decay window length for photo evidence.
3. Whether AI-estimated severity should be visible to the Operations Officer pre-verification as a triage aid (probably yes) vs. only post-verification (definitely, for anything score-affecting).
4. Which VLM API actually gets called in production — this session's estimates were produced by Claude reasoning interactively in chat, not by any code in `risk_engine/`. Needs a real integration (Anthropic Messages API with image content blocks is the natural fit given everything demonstrated here) before this is more than a design sketch.
