# ESA Pléiades Neo Research/Application-Development Access — Proposal Draft

Submitted via ESA EO Sign In → Project Proposal form (Earth Online). This
draft is organized to match the fields that form typically asks for —
paste each section into the corresponding field. Evaluation takes ESA
~9 weeks per their published guidance.

---

## Project Title

ThirdWave: Free/Open-Data Flood Early-Warning Scoring for Accra, Ghana —
Closing the Built-Environment Resolution Gap with Pléiades Neo

## Applicant / Institution

[Your name: Robert Addo-Asante-Darko]
[Affiliation/institution — enter your own or "Independent / civic-tech
project" if unaffiliated]
[Institutional or personal email — ESA recommends an institutional
address if you have one]
[Country: Ghana]

## Abstract (short summary)

ThirdWave is an open-source flood early-warning pilot for a 7-assembly
district in Accra, Ghana (github.com/ROBERT-ADDO-ASANTE-DARKO/ThirdWave),
built entirely on free Earth observation data: Sentinel-1 SAR water
occurrence, Copernicus DEM elevation, and ESA WorldCover land cover,
fused into an explainable composite vulnerability score. The project's
own historical-flood backtesting has identified a specific, resolution-
driven gap: WorldCover's 10m land-cover classification and our current
imagery cannot resolve individual buildings, informal drainage channels,
or recent urban changes (new roads, infill construction, blocked gutters)
that determine whether a specific street floods at a specific rainfall
threshold — this is documented in the project's own literature review
(Trepekli et al. 2022 found 10m terrain data overestimates runoff by up
to 65% in flat terrain because it misses exactly these features). We
request Pléiades Neo (30cm) **stereo or tri-stereo** archive and/or
tasked imagery over our pilot area — stereo specifically, not a single
mono scene, so real photogrammetric building-height reconstruction is
possible, not just 2D visual inspection — to test whether VHR optical
imagery can close this gap at the project's known highest-priority flood
hotspots.

## Background & Motivation

Accra has no dense rain-gauge network, no calibrated hydraulic model of
its drainage system, and (until this request) no access to very-high-
resolution imagery — the same resolution gap that Auckland Council's own
flood-viewer program addresses with LiDAR-grade terrain data. ThirdWave
has already backtested its scoring pipeline against real, sourced
historical flood events (2015 and 2023 Kwame Nkrumah Circle flooding —
200+ deaths in the 2015 event; 2026 Kaneshie and Alajo flooding; three
documented Weija Gbawe dam-release floods in 2022, 2025 and 2026), and
found that assembly-level and even 500m-grid-level scoring, while useful,
cannot explain *why* a specific location floods when the driving factor
is a recent, small-scale built-environment change rather than a
persistent terrain/water-occurrence signal. Pléiades Neo's 30cm
resolution is fine enough to plausibly identify individual buildings
encroaching on drainage channels, blocked or informal gutters, and new
impervious surfaces not yet reflected in WorldCover's 2021 land-cover
release — complementing (not replacing) the free Sentinel/Copernicus data
already driving the project.

We have already tested how far a free-data-only approach to building
height can go, before requesting VHR imagery: subtracting FABDEM
(bare-earth) from Copernicus DEM (a surface model that already includes
building/canopy height bias) gives a real, validated height-above-ground
proxy over our dense Accra pilot grid (r=0.83 correlation with independently-
computed impervious land cover, 1013 cells) — but the same technique
breaks down over hillier, more forested terrain (r=0.14 over a second,
16,941-cell grid we maintain for the Lower Volta basin), where DEM/canopy
noise dominates any real building signal. That result is the direct
motivation for this request: free 30m-class elevation data has a real,
now-quantified ceiling, and stereo/tri-stereo VHR imagery is the next
concrete step past it, not a redundant one.

## Study Area / AOI

Primary AOI: ThirdWave's pilot district, Accra, Ghana — a union of 7
metropolitan/municipal assemblies (Accra Metropolis, Korle Klottey,
Ablekuma Central/North/West, Ayawaso Central, Weija Gbawe), approx.
75 km², bounding box:
  minLon -0.4276, minLat 5.4697, maxLon -0.1751, maxLat 5.6127
(exact polygon available as GeoJSON on request / can be uploaded as AOI
file — repo path `risk_engine/data/pilot_district_boundary.geojson`).

Given quota limits, we would prioritize sub-AOIs at our documented
highest-priority flood hotspots rather than requesting full-district
coverage, specifically:
  1. Kwame Nkrumah Circle / Odawna, -0.2153, 5.5692 (site of the 2015
     flood, 200+ deaths, and recurring flooding through 2026)
  2. Kaneshie Market, -0.2345, 5.5666 (May 2026 flood)
  3. Alajo, -0.2169, 5.5937 (June 2026 flood, fatalities)
  4. Weija Gbawe / Tetegu, -0.3062 to -0.3307, 5.548-5.579 (three
     documented dam-release floods: 2022, 2025, 2026)

A 1-2 km² tasked or archive scene around each of these four points would
cover the project's real documented flood history at native 30cm
resolution.

## Data Requested

- Product: Pléiades Neo, 30cm pansharpened, **stereo or tri-stereo
  acquisition mode** (two or three overlapping views per AOI, not a
  single nadir scene) — required for genuine photogrammetric DSM/building-
  height generation via dense image matching, as opposed to 2D visual
  inspection only. (30cm Pan + 1.2m 6-band multispectral welcome in
  addition, if available under the program, for the land-cover comparison
  in Methodology step 1 below.)
- Preference: recent archive stereo imagery if a sufficiently cloud-free
  (<20%) pair/triplet exists within the last 12 months for each sub-AOI;
  new tasking only if no usable archive stereo scene exists, given
  Accra's persistent rainy-season cloud cover (documented in our own
  Sentinel-2 cross-validation work: 0 of 40 sampled scenes in June/July
  had <20% cloud cover at this location)
- Estimated total area: ~10 km² across the four sub-AOIs above (small,
  deliberately scoped to the project's actual documented hotspots rather
  than the full 75km² pilot district)
- Secondary/stretch AOI if quota allows: ~2 km² around the Akosombo dam
  (0.427, 6.079), the one location in our free-data obstruction-height
  test (see Background) where the terrain is complex enough that free
  30m DEM data demonstrably fails — the clearest single case for why VHR
  stereo would add real value beyond what we can already get for free.

## Methodology

1. Visually and computationally compare Pléiades Neo imagery against the
   existing WorldCover/OSM building layer at each hotspot to identify
   buildings, drainage encroachment, and impervious surfaces not
   reflected in current inputs (extending the methodology already used
   in `channel_encroachment_index.py`, which currently relies on
   OSM-mapped waterways/buildings of uneven completeness).
2. Generate a real photogrammetric DSM from the stereo/tri-stereo pair(s)
   via dense image matching (open-source tooling: NASA Ames Stereo
   Pipeline or MicMac), then compute building/canopy height as
   DSM − FABDEM at native VHR resolution — the same subtraction already
   validated at 30m (see Background), now at building-level resolution
   instead of a coarse per-cell average.
3. Where discrepancies are found (against either the land-cover layer or
   the free obstruction-height proxy), quantify how much they would move
   the existing composite vulnerability score if incorporated as a new
   input term (same "drop-in weighted term" pattern already demonstrated
   in `prototype_drain_capacity_integration.py` for drain-capacity data).
4. Publish findings (methodology, code, and score deltas — not the raw
   imagery, per standard licensing) openly in the same GitHub repository,
   with full attribution to ESA/Airbus as the imagery source.

## Expected Outcomes / Deliverables

- A documented, reproducible comparison of VHR-imagery-informed vs.
  10m-WorldCover-only vulnerability scores at 4 real, historically
  flooded locations in Accra.
- An open-source methodology (not just a one-off result) for folding VHR
  imagery into a free-data-first flood-scoring pipeline, usable by other
  under-resourced pilot projects facing the same data gap.
- Public credit to ESA and Airbus as data providers in the project
  README and any resulting write-up.

## Relevance to ESA / Copernicus Objectives

Directly supports Copernicus's stated goal of Contributing Missions
extending Sentinel data for applications Sentinel's own resolution can't
serve — here, urban flood risk in a West African megacity with no
existing VHR coverage, no hydraulic model, and no commercial budget for
satellite imagery. Advances a fully open, reproducible civil
(non-commercial, non-operational) EO research pipeline consistent with
the program's eligibility criteria.

## Relevant Prior Work / Track Record

- Live pilot repository: github.com/ROBERT-ADDO-ASANTE-DARKO/ThirdWave
- Existing free-data pipeline already fuses Sentinel-1 GRD, Copernicus
  DEM, and ESA WorldCover into a validated, backtested composite score
  covering 7 Accra assemblies (1013 scored 500m grid cells) plus an
  extended-coverage region for the Lower Volta basin (16,941 cells,
  7 further districts).
- Sentinel-1/Sentinel-2 SAR and MNDWI change-detection analysis already
  performed for two real documented dam-release flood events (2023
  Akosombo/Kpong, 2026 Weija), confirming the project's ability to work
  correctly with real EO data end-to-end.
- Free-data building/canopy obstruction-height layer already built and
  validated (`building_obstruction_height.py`) -- CopDEM minus FABDEM,
  cross-checked against independently-computed land cover rather than
  taken on faith, with the resulting confirmed-good (pilot) vs.
  confirmed-unreliable (Lower Volta) result directly motivating this
  proposal's stereo/tri-stereo request.

---

### Notes before submitting
- Create/log in at ESA's "EO Sign In" first (earth.esa.int) — register
  with an institutional email if you have one, personal email otherwise.
- The portal form may ask you to choose between "Standard PNEO
  provision" and "OneAtlas Living Library subscription" — for a
  one-off, scoped research use like this, Standard PNEO provision is
  almost certainly the right choice (Living Library is more of a
  recurring-monitoring subscription model).
- If the form has a separate acquisition-mode field, select stereo or
  tri-stereo explicitly — don't let it default to mono. That choice is
  the whole point of this version of the request (see Data Requested).
- Keep the requested area small and specifically justified (as above) —
  quota is limited and ESA evaluates proposals partly on scope
  discipline, not just merit.
- Expect ~9 weeks for an evaluation decision per ESA's published
  guidance; nothing in the pipeline currently depends on this landing on
  a particular timeline, so it's a parallel track, not a blocker.
