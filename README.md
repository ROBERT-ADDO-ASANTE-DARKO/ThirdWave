# ThirdWave

A flood early-warning system for Accra, Ghana. ThirdWave fuses free satellite
data into an explainable flood-vulnerability score for a 6-assembly pilot
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
Copernicus DEM ──┼──► Fusion engine ──► Risk zones (319 cells) ──┬──► Government console
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
SAR2SAR despeckling step), and `matplotlib` (diagnostics). Entry points:
`geospatial_vulnerability.py` (assembly-level scoring), `risk_grid.py`
(fine 500m grid), `build_road_network.py` (routing graph),
`precompute_inundation_inputs.py` (pluvial simulator inputs).

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

6 assemblies: Accra Metropolis, Korle Klottey, Ablekuma Central/North/West,
Ayawaso Central — 319 scored zones on a ~500m grid. Extended-coverage
scoring for 4 additional districts with documented flood history (Weija
Gbawe, Ga South, Tema, Ashaiman) is included for regional context, not as
part of the MVP pilot deliverable.
