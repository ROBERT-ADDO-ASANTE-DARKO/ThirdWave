# ThirdWave

A flood early-warning system for Accra, Ghana. ThirdWave fuses free satellite
data into an explainable flood-vulnerability score for a 7-assembly pilot
district, and puts it in front of the two people who need it during a
storm: the government officer deciding where to send a pump crew, and the
resident deciding whether to leave.

There is no dense rain-gauge network here, no calibrated hydraulic model of
the drainage system, and no shared picture between officials and residents
today. Every piece of this project is built around that constraint — free,
global data sources, an explainable (not black-box) scoring formula, and
tools that say plainly what they are and aren't.

## What it is

```
Sentinel-1 SAR ──┐
Copernicus DEM ──┼──► Fusion engine ──► Risk zones (1013 cells) ──┬──► Government console
ESA WorldCover ──┤     (offline,          score + factors        │      dashboard · simulators · AI chat
OSM ─────────────┘      precomputed)                             └──► Citizen app
                                                                        alerts · routing · reporting
                              ▲
                              └── geotagged citizen reports feed back in, once verified
```

- **Composite score** = `0.45 × SAR water occurrence + 0.35 × low-elevation fraction + 0.20 × impervious land cover` — a transparent formula an officer can audit, not a trained model. (Land cover is disclosed as context but not weighted further; weighting it in flattened the score's discrimination — see `geospatial_vulnerability.py`.)
- **Heavy geospatial work runs offline.** The Streamlit app only ever reads small, precomputed results — no query waits on a live satellite API.
- **A citizen report doesn't become an "incident" by itself.** It's district-routed, a government officer verifies it, and only then does it become something Safer Routing detours around or Resource Allocation dispatches a responder to.

## Features

**Government**
| Page | What it does |
|---|---|
| District Vulnerability Dashboard | Composite score per assembly, with a live toggle onto the raw SAR/DEM/WorldCover evidence beneath it |
| Drain Maintenance Prioritization | Ranks zones by encroachment (OSM building-to-waterway distance) |
| Population / Infrastructure Exposure | WorldPop-based population and building counts per zone |
| Emergency Resource Allocation | Assign a responder + ETA to a verified incident |
| Before/After Scenario Simulator | What-if sensitivity of the score to hypothetical drainage/paving changes |
| Pluvial Flood Simulator | Rainfall-driven ponding proxy over real terrain (a cellular-automaton model, not a hydraulic solver) |
| 3D Flood View | Real OSM buildings/roads with true-scale simulated water, playable as a rise-over-time animation |
| Incident Verification | The district officer's queue — approve/reject reports (with the submitted photo, AI annotation, and the zone's existing static score as context), plus a scripted scenario sandbox for demoing without live flood data |
| AI Assistant | Claude with tool-calling, grounded in the real computed data |

**Citizen**
| Page | What it does |
|---|---|
| Current Vulnerability by Address | Look up any address's zone score |
| Crowdsourced Flood Reporting | Photo + GPS report, with a vision-language model drafting a description, depth estimate, and annotated image for the citizen to review before submitting |
| Rainfall Forecast | Live 6-hour precipitation outlook per zone |
| High-Risk Zone Alert | Combines zone vulnerability, live rainfall, and nearby verified incidents into one on-demand check, with a map showing distance to active flooding |
| Safer Routing | Fastest vs. vulnerability-weighted route, dynamically penalizing roads near currently active incidents (typed address or live location) |
| AI Assistant | Same assistant as the government console |

## Honest limitations

- **Not a hydraulic model.** No drain/culvert capacity data exists for Accra's informal drainage network. The Pluvial Simulator and 3D Flood View are disclosed proxies, not calibrated engineering models.
- **Not real push notifications.** Streamlit can't do background geolocation or push — every "alert" here is an on-demand check, not something that reaches a phone unprompted.
- **Session-only storage.** Reports, incidents, and responder assignments live in `st.session_state` for this proof of concept, not a persisted backend.
- **AI drafts, humans decide.** The VLM's photo description/depth estimate is always a draft the citizen edits, and a report only becomes an active incident after a district officer verifies it.

See `pitch/ThirdWave_Field_Report.pptx` (or `pitch/pitch.html`) for the full pitch deck, including where AI is doing real work versus where a transparent rule-based approach was the deliberate choice.

## Roadmap

**Drain capacity data (GARID) — noted future direction, not current work.** The single biggest gap above (no drain/culvert capacity data) has a concrete path to closing it: the [Greater Accra Resilient and Integrated Development Project (GARID)](https://garid-accra.com/), a World Bank-funded program, has already produced drainage system maps for the Odaw River Basin — the exact corridor this pilot's historical flood events cluster around. That's a data-sharing conversation for a real deployment, not something built here.

In the meantime, `risk_engine/prototype_drain_capacity_integration.py` rehearses the integration pattern against a real, openly-licensed drainage network (Auckland Council's stormwater pipe data, CC BY 4.0) as a stand-in — proving the pipeline can consume real pipe-capacity data (diameter, distance) and fold it into a composite score, so only the data source needs to change once GARID access comes through. It runs entirely against Auckland, NZ — not a claim about Accra.

**Historical flood events.** `risk_engine/data/historical_flood_events.json` is a growing, hand-curated (not scraped) set of real, sourced flood events from Ghanaian and international news coverage (GhanaWeb, Ghana News Agency, Citi Newsroom, floodlist.com), each geocoded and district-assigned against this project's own pilot boundaries. It backs the historical-event option in the Incident Verification sandbox and is meant to be extended as more documented events are found — it is not, and doesn't claim to be, a complete flood record for the city.

**SAR flood verification for the dam-spillage events.** `risk_engine/dam_spillage_sar_comparison.py` produces a before/during/after Sentinel-1 view of the two dam-spillage events in that record — the 2023 Akosombo/Lower Volta spillage and the May 2026 Weija spillage — using calibrated RTC gamma0 change detection (standard single-event flood-mapping method, not the multi-year percentile approach the composite score uses). It confirms free radar imagery does capture both floods: ~8 km² of new floodplain inundation for Akosombo at peak (mostly receded 5 weeks later), ~5 km² for Weija the day after the gates opened (mostly receded within 2 weeks). Evidence-only — it changes no score. Copernicus EMS also published a formal flood-extent map for Akosombo (activation EMSR705); no equivalent exists for Weija.

**Optical cross-check (Akosombo only).** `risk_engine/dam_spillage_s2_mndwi.py` maps the same Akosombo flood with Sentinel-2 MNDWI. It only works for Akosombo — the 2026 Weija event was too short and too cloudy (its peak date is 92% cloud), which is exactly why the pilot uses radar. Even for Akosombo there is no usable rainy-season pre-flood scene, so the baseline is a near-cloud-free dry-season reference (Dec 2022). Two independent sensors and methods agree on the headline: **+7.9 km² new flood (Sentinel-2)** vs **+8.0 km² (Sentinel-1)** at peak. The optical margins are cleaner; the caveat is that ~10% of the peak scene is cloud-masked, so the optical figure is a lower bound.

**Hydrological-modelling rehearsal (Amsterdam — not Accra).** Accra has no open drain-network or high-resolution terrain data, so `risk_engine/build_amsterdam_swmm.py` and `surface_flood_amsterdam.py` rehearse what a real pipe-network + surface-flood model looks like in a city that *does* publish both, built entirely from open data: Waternet's sewer network (5,434 pipes, 4,368 nodes), BGT land cover, AHN 0.5 m LiDAR, the Dutch standard design storms (Bui08 / Bui10) and EPA SWMM. Phase 1 (pipes): no flooding at Bui08 (T=2 yr), ~1,100 m³ at Bui10 (T=10 yr, 1.9% of sewer inflow) — consistent with the Dutch design standard, but **not calibrated or validated against any observed flooding**. Phase 2 spreads that overflow over the real streets with a local-inertial 2D solver (`inertial2d.py`, tested against known solutions in `test_inertial2d.py`): ~1,700 m² of street ≥10 cm deep (extent robust to ±8% across roughness and grid resolution; the ≥50 cm tail is *not* — it doubles on a 2 m grid). It is one-way coupled (no sewer re-entry, no direct street rainfall), several assumptions are optimistic and one pessimistic (net direction unknown), and SWMM's routing does not fully converge on this flat network (34–53% of steps) — see `data/amsterdam_swmm/*.png` and each script's docstring for the full list. Data defects found along the way (unusable node-ID links, missing inverts, retired BGT objects, dead-end sinks) and how each was handled are documented in the commit history. Sewer-data licence is ambiguous (CC BY per the API spec, "unknown" per the catalogue) — attribute Gemeente Amsterdam / Waternet.

## Getting started

```bash
git clone https://github.com/ROBERT-ADDO-ASANTE-DARKO/ThirdWave.git
cd ThirdWave
pip install -r requirements.txt
```

Create `.env` in the project root (used by the AI Assistant and the
crowdsourced-reporting VLM feature):

```
ANTHROPIC_API_KEY=your-key-here
ANTHROPIC_WORKSPACE_ID=your-workspace-id   # only needed for identity-linked API keys
```

Run the app:

```bash
cd streamlit_app
streamlit run app.py
```

All of `risk_engine/data/` is already computed and checked in, so the app
runs immediately — no satellite API calls happen at runtime.

### Regenerating the data (optional)

The `risk_engine/` scripts that produced `risk_engine/data/*.json`/`*.geojson`
pull from Microsoft Planetary Computer (Sentinel-1, Copernicus DEM, ESA
WorldCover) and OpenStreetMap/Overpass. They're not needed to run the app,
only to recompute it. They need a few extra packages not in
`requirements.txt`: `pystac-client`, `planetary-computer`, `torch` (for the
SAR2SAR despeckling step), `matplotlib` (diagnostics), and for the Amsterdam rehearsal
`pyswmm`, `swmm-toolkit`, `pyproj`, `scipy`. Entry points:
`geospatial_vulnerability.py` (assembly-level scoring), `risk_grid.py`
(fine 500m grid), `build_road_network.py` (routing graph),
`precompute_inundation_inputs.py` (pluvial simulator inputs),
`extended_coverage.py` / `lower_volta_coverage.py` (the two extended-coverage
regions described above).

## Project structure

```
risk_engine/          Offline geospatial pipeline: fetch, score, validate
  data/                Precomputed outputs the app reads (checked in)
streamlit_app/         The Streamlit POC
  features/            One file per page, listed above
  incident_store.py    Shared report/incident/verification state
  inundation_model.py  The pluvial CA proxy
  vlm_client.py        Anthropic vision calls for photo-report drafting
  geo_tools.py         Tool functions for the AI Assistant
  demo_screenshots/    Screenshots of the incident-reporting pipeline in action
pitch/                 Pitch deck (.pptx + web version) and its source assets
ui_prototype/          An earlier static HTML mockup of the risk map
```

## Pilot scope

7 assemblies: Accra Metropolis, Korle Klottey, Ablekuma Central/North/West,
Ayawaso Central, and Weija Gbawe (added after 3 documented dam-release
floods there in 2022, 2025, and 2026 — see `historical_flood_events.json`)
— 1013 scored zones on a ~500m grid. Extended-coverage scoring for 3
further districts with documented flood history (Ga South, Tema, Ashaiman)
is included for regional context, not as part of the MVP pilot deliverable.

**Lower Volta basin (separate extended coverage, full pilot-grade depth).**
`risk_engine/lower_volta_coverage.py` scores 7 more districts across 3
regions — Asuogyaman (Akosombo/Kpong dam), Lower Manya (Akuse), North/
Central/South Tongu (Mepe, Battor, Adidome, Sogakope), and Ada East/West
(Ada Foah) — added for the 2023 Akosombo/Kpong dam-spillage flood (35,857
displaced at Mepe alone). It's ~150km from Accra, a different flood
mechanism (dam-release/riverine, not urban pluvial), and non-contiguous
with the pilot, so it's kept as its own dataset rather than folded into
either `pilot_*` or `extended_*`. Unlike the lighter extended-coverage set
above, it gets the *same depth as the pilot*: a 16,941-cell fine grid,
a risk-weighted road network, WorldPop population exposure (~695,000
people, 93,000 buildings), and OSM channel-encroachment scoring (sparse by
design here — only 364 waterway features are mapped basin-wide, so ~98% of
cells are flagged `insufficient_data` rather than guessed at). Every
district scores Low/Moderate on the composite formula, which is the
correct and expected result, not a gap: SAR/DEM/land-cover water occurrence
is a multi-year statistical measure and structurally can't see a one-off
dam release — that's exactly why the dam-spillage SAR/S2 evidence below and
`historical_flood_events.json` exist as separate, un-blended context. Wired
into the District Dashboard (a third "Coverage" option), the AI Assistant
(`geo_tools.find_zone_by_address` falls back to this grid and flags it),
and the Incident Verification sandbox (dam-release reports here are
district/zone-tagged for real instead of showing "outside pilot district").
