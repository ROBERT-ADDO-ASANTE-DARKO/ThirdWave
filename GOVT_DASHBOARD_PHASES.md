# Government dashboard — feature tracker

Built on `streamlit_app/`'s existing `govt_*` prototypes and the FastAPI
`backend/` first, not a from-scratch build -- see each feature's
"Grounding" note for what already exists. Update this file as each
feature lands: status, what actually got built, what's still deferred,
and the commit(s) that did it. Same convention as `MOBILE_APP_PHASES.md`.

## Architecture decision

**Streamlit now, React later.** Flutter Web was considered and ruled
out for this specific audience: office/government use leans on things
standard HTML gets for free (copy-pasting table data into reports,
browser Ctrl+F, printing, screen-reader accessibility, lighter load on
older office hardware) that Flutter Web's canvas-based rendering
(CanvasKit) sacrifices -- a tradeoff worth making for the citizen app's
map/voice UI, not for a tables/forms/charts-heavy dashboard. Plan: get
every feature below working in Streamlit first (fastest iteration,
already has most of the groundwork), then migrate to a production-grade
React/Next.js app once the feature set is proven out, not before.

## Cross-cutting: map tile style picker — Done

`streamlit_app/map_tiles.py` (new, shared) adds Satellite/Dark/Terrain as
selectable base layers (Mapbox Styles API, same `MAPBOX_API_KEY` and
style IDs `citizen_app/lib/widgets/map_style_control.dart` already uses)
alongside every government folium map's existing Streets default,
switchable via folium's own in-map `LayerControl` -- no Streamlit rerun,
no lost pan/zoom, same reason the Flutter picker lives in the map widget
itself. Wired into `govt_incident_map.py`, `govt_road_closures.py`, and
`govt_district_dashboard.py` (whose existing SAR/DEM/WorldCover overlay
toggle now always gets a `LayerControl`, not only when that manifest
exists). Degrades to Streets-only, not an error, if `MAPBOX_API_KEY`
isn't set. Verified directly (`add_style_layers()` against a real map
object with the real token -- confirmed exactly 3 layers added, named
Satellite/Dark/Terrain) and via AppTest across all three pages (no
exceptions).

**Real bug found and fixed after initial build:** the live app showed
Streets only, no Satellite/Dark/Terrain, even though every isolated
test above passed. Root cause (confirmed by a temporary debug line
printed into the live running page, not guessed): Streamlit's own
`streamlit/web/bootstrap.py` runs
`os.environ.setdefault("MAPBOX_API_KEY", "")` at startup -- unrelated
to this feature, it's there so Streamlit's own `st.map()`/PyDeck
widgets don't throw when no token is configured -- which pre-sets the
exact same env var name this module reuses to an empty string before
any app code runs. `load_dotenv()`'s default (never override an
already-present key) then silently discarded the real token from
`.env` on every run, with no error. Fixed by passing `override=True` to
`load_dotenv()` in `map_tiles.py`, documented there. Reproduced the
collision standalone (`os.environ.setdefault(...)` then `import
map_tiles`) to confirm the fix before redeploying.

## Status at a glance

| # | Feature | Status | Commit(s) |
|---|---------|--------|-----------|
| 0 | AI Assistant extended-coverage wiring (`ai_tools.py`) | **Done** | -- (uncommitted) |
| 1 | Live incident map (clustering + severity colors) | **Done** | -- (uncommitted) |
| 2 | Incoming reports queue (Pending/Verified/Responding/Resolved) | **Done** | -- (uncommitted) |
| 3 | Report confidence score | **Done** | -- (uncommitted) |
| 4 | Resource allocation (NADMO/fire/ambulance/boats/shelters) | **Done** | -- (uncommitted) |
| 5 | Road closure recommendations | **Done** | -- (uncommitted) |
| 6 | Flood/incident timeline | **Done** | -- (uncommitted) |
| 7 | Analytics dashboard | **Done** | -- (uncommitted) |
| 8 | Multi-year encroachment trend view | **Done** | -- (uncommitted) |
| 9 | District briefing workflow | **Done** | -- (uncommitted) |

## 0 — AI Assistant extended-coverage wiring — Done

Not a dashboard feature itself, but foundational: the Assistant's tool
functions (`backend/ai_tools.py`) were pilot-district-only even after
`geo_data.py` gained Ayawaso West/Madina/Lower Volta extended coverage.
A government-facing chat assistant would otherwise have inherited that
gap on day one.

**Built:** `find_zone_by_address` already worked via `zone_info_for_point()`'s
existing fallback chain -- the gap was `SYSTEM_PROMPT` telling Claude to
reject anything outside the pilot district. `get_assembly_comparison`
now merges all 16 assemblies (7 pilot + Madina + Lower Volta's 7, each
independently computed, plus Ayawaso West derived as the mean of its 156
grid cells since no independently-computed file exists for it, tagged
`derived: true`). `get_drain_priority` merges all 4 grids' channel-
encroachment data (761 zones, 489 extended). Every merged result is
tagged `coverage: "pilot"|"extended"`. `get_population_exposure_summary`
deliberately stays pilot-only and says so in its own tool description --
Lower Volta has real population data but Madina/Ayawaso West don't, so
partial extension would misrepresent coverage.

**Verified:** live through Tide's actual chat responses (not just unit
tests) -- asked it to compare Asuogyaman against the pilot district, and
to list drain priorities pilot + extended-wide; both correctly labeled
coverage tiers and surfaced the dam-spillage blind spot unprompted.

## 1 — Live incident map (clustering + severity colors) — Done

**Built:** `streamlit_app/features/govt_incident_map.py`, new page, now
first in the Government nav. Folium map (matching
`govt_district_dashboard.py`'s approach) talking to the live backend
over HTTP rather than `incident_store.py`'s session state -- same
integration pattern `govt_briefing_review.py` established, with the
officer-gated endpoints' `X-Officer-Key` header loaded from
`backend/.env`. Pulls `GET /reports/clusters` (pending, already
complete-linkage clustered by `clustering.py`) as colored/sized
CircleMarkers, and `GET /incidents/active` (verified, not yet resolved)
as pin Markers distinguishing "awaiting responder" vs "responder
assigned." Severity coloring deliberately reuses `LEVEL_COLOR` (the same
Low/Moderate/High/Very High convention as everywhere else, matching
`citizen_app/lib/risk_colors.dart`'s palette) keyed off the worst
vulnerability-zone level among a cluster's member reports' locations --
not a second depth-based severity scale, which is a noisier, unverified
citizen estimate. KPI row, popups (hazard types, depth estimates, news
corroboration, synthetic badge), legend, and a worst-first table round
it out. Read-only by design: verify/assign/resolve stays in Incident
Verification.

**Verified:** live against the real backend and real (non-synthetic)
citizen-submitted data via `streamlit.testing.v1.AppTest` (no browser
available in this environment) -- confirmed no exceptions, and the KPI
row correctly reflects actual DB state: 1 pending cluster / 3 pending
reports (real reports near Kwame Nkrumah Circle from this project's
earlier on-device testing session) / 0 active incidents, with the
cluster table and legend rendering real content, not placeholders.

## 2 — Incoming reports queue (Pending/Verified/Responding/Resolved) — Done

**Built:** `streamlit_app/features/govt_reports_queue.py`, new page,
second in the Government nav (after Live Incident Map). Deliberately
kept separate from `govt_verification_sandbox.py` rather than retrofit
it in place: the sandbox's job is seeding synthetic demo data into
`incident_store.py`'s isolated session state when no live flood is
happening, and that's still a real, distinct need -- this page instead
drives the real backend DB over HTTP (`/reports/clusters`,
`/reports/{id}/verify`, `/reports/verify-bulk`,
`/incidents/active`, `/incidents/{id}/assign-responder`,
`/incidents/{id}/resolve`), one section per lifecycle stage, with a
report card UI adapted from the sandbox's (photo, description, depth,
verification-context zone badge, news corroboration).

One small backend gap closed along the way: there was no endpoint to
list *resolved* reports (only `/reports/pending` and `/incidents/active`
existed) -- added `GET /incidents/resolved` to `routers/incidents.py`,
same shape as the other two. Also found and fixed a real parity gap this
page's zone badges exposed: `geo_data.zone_for_point()` (what
`serializers.py` uses for every report's "verification context" score)
was pilot-grid-only, unlike `zone_info_for_point()`'s address/point
lookups which already fall back through Ayawaso West/Madina/Lower Volta.
A report from any extended-coverage region was silently showing "outside
all scored coverage" even where `geo_data.py` has long since had real
data. Extended `zone_for_point()` with the same fallback chain (boundary-
decided Ayawaso West vs. Madina, then Lower Volta, each
`_confirm_extended_assembly()`-checked), tagged `extended: true`; threaded
that flag through `serializers.serialize_report()`.

**Verified:** `streamlit.testing.v1.AppTest` against the live backend and
real data (no browser available in this environment) -- no exceptions;
KPI row matched DB state (3 pending / 0 verified-awaiting / 0
responding); the 3 pending reports correctly clustered into one group
with working bulk + per-report Verify/Reject buttons; zone badges
rendered with the right color/score; the Resolved section correctly
listed 2 real historical resolved incidents. Also unit-verified
`zone_for_point()`'s new fallback directly: a pilot point still returns
its pilot zone unchanged, an Asuogyaman (Lower Volta) point now returns
`{'id': 'lv_r117_c32', 'score': 11.6, 'level': 'Low', 'assembly':
'Asuogyaman', 'extended': True}` instead of `None`, and a point with no
coverage anywhere still correctly returns `None`. Did not click
Verify/Reject/Assign/Resolve in testing -- these would mutate real,
non-synthetic citizen report data.

## 3 — Report confidence score — Done

**Built:** `backend/report_confidence.py`, a composite 0-100 score (own
Weak/Some corroboration/Well-corroborated/Strongly corroborated bands,
deliberately not the Low/Moderate/High/Very High vocabulary used for
area flood-risk elsewhere, to avoid conflating the two axes) combining:

- `backend/photo_validation.py` (new) -- re-runs `vlm_client.py`'s
  describe_flood_photo() against the report's OWN submitted photo
  (independent of whatever the citizen's AI-assisted draft said),
  cached per report id (`backend/vlm_checks.json`) so it's one real
  Claude vision call per report, not per page load. Runs automatically
  (fast, cheap) -- `shows_flooding` true/false moves the score +25/-15.
- Cluster size (`clustering.py`, already wired into `/reports/clusters`):
  +15/+25 for 2 / 3+ independent reports nearby.
- `news_corroboration.py` (already live): +20 for any 72h news hit.
- `geo_data.nearby_historical_events()`: +10 if this location has
  documented flood history.
- `backend/sar_corroboration.py` (new) -- ported
  `risk_engine/citizen_report_sar_check.py`'s core Sentinel-1 logic as an
  importable function reading/writing the SAME cache file the offline
  script does (`risk_engine/data/dam_spillage_sar/citizen_report_checks.json`),
  so neither copy drifts. Unlike the photo check, this is deliberately
  NOT automatic (public, rate-limited STAC API + real raster compute) --
  new `POST /incidents/{id}/sar-check` endpoint triggers it explicitly
  for one verified/resolved incident; +25/-10 once checked, 0 while
  "not yet checked." Lazy-imported so the rest of the backend doesn't
  need risk_engine's heavy deps (pystac-client/planetary-computer/
  odc-stac/rasterio -- added to `backend/requirements.txt`, gated to
  that one code path).

Wired into `/reports/clusters`, `/incidents/active`, and
`/incidents/resolved` (each report gets a `confidence` field); rendered
in `govt_reports_queue.py` as a badge + "why this score" expander on
every card, plus a "Run satellite (SAR) check" button on verified/
responding cards.

**Verified:** live against the real backend with real (non-synthetic)
citizen photos -- first fetch of `/reports/clusters` triggered 3 real
Claude vision calls (confirmed in `vlm_checks.json`), scored all 3 at
75/100 (Well-corroborated: base 15 + photo +25 + cluster-of-3 +25 +
historical +10); second fetch was ~150x faster (0.19s vs. ~30s),
confirming the cache. `POST /incidents/{id}/sar-check` exercised against
a real (synthetic-test) resolved incident -- caught and fixed a real gap
along the way (`odc-stac` was missing from `.venv` entirely, even though
`risk_engine/dam_spillage_sar_comparison.py` had produced real output
before; installed it and added it + its STAC/raster siblings to
`backend/requirements.txt`), then correctly returned and cached a
`check_failed` result (no Sentinel-1 scene near the computed baseline
date) without crashing, confidence score unchanged as designed.
AppTest confirmed the Streamlit page renders the badges/expanders with
no exceptions.

## 4 — Resource allocation — Done

**Grounding:** `govt_resource_allocation.py`'s responder list was 100%
fabricated demo data. Checked OSM Overpass coverage before deciding
whether real data was gettable at all (not assumed): NADMO offices,
flood-response boats, and shelters confirmed NOT reliably mapped
anywhere in Ghana OSM data, but fire stations and hospitals
(`amenity=fire_station`/`hospital`) are -- 7 real, named fire stations
and 63 real, named hospitals turned up in/near the pilot bbox. Checked
distance, not just presence, before trusting it: every one of the 7
pilot assemblies has a real fire station within ~0.6-4.6km of its
centroid and at least one real hospital (thinnest: Ayawaso Central
Municipal). Went with the middle path -- real data where OSM actually
supports it, explicitly-labeled synthetic where it doesn't -- rather
than either staying 100% fabricated or pretending full coverage exists.

**Built:** `risk_engine/emergency_facilities.py` (one-time Overpass
fetch, same pattern as every other Overpass dataset here) ->
`risk_engine/data/emergency_facilities.json`. `geo_data.emergency_facilities()`
(loader) + `nearest_facility(lat, lon, kind)` (nearest real fire_station
or hospital by haversine_km -- straight-line distance, not a road-
network ETA, stated as such). New `GET /resource-allocation/nearest-facilities`.
`govt_resource_allocation.py` now shows each active incident's real
nearest fire station + hospital (name, distance) alongside the still-
fabricated responder-unit assignment dropdown -- the two are visually
distinct (one labeled "real," the other left exactly as fabricated as
it always was). NADMO/boats/shelters untouched -- still `DEMO_RESPONDERS`,
now with the reasoning for why documented rather than just asserted.

**Verified:** live `GET /resource-allocation/nearest-facilities` against
real coordinates -- correctly returned Ghana Fire Service (0.11km) and
Atta Quarshie Merton Memorial Hospital (0.88km) for a point near Ghana
Fire Service's own real OSM location. AppTest (with an injected active
incident, since the seed data's own 2 incidents are both historical/
closed on a fresh session) confirmed the page renders the real nearest-
facility caption with no exceptions.

**Restructured around how NADMO actually coordinates, not just skinned:**
researched NADMO's real dispatch structure (nadmo.gov.gh + a Citi News
interview with a NADMO Inspectorate officer -- no official step-by-step
protocol found anywhere public, so this mirrors the publicly confirmed
SHAPE, not a claimed replica of an internal SOP). Two confirmed facts
drove the redesign: (1) District Directors stationed at the local
Assembly are NADMO's own stated first responders for district-level
emergencies, and (2) NADMO's Operations department lists "deployment of
response teams" AND "liaison with military and police" as core
functions, and pools Fire Service/Police/Red Cross/military alongside
its own teams for larger floods -- i.e. one incident can have MULTIPLE
responders, not a single pick from one flat list.

Replaced the old flat `DEMO_RESPONDERS` (4 arbitrarily-named units) with
four distinct categories: `DEMO_NADMO_TEAMS` (one fabricated team per
pilot assembly -- mirrors the real one-office-per-assembly structure),
`DEMO_LIAISON_UNITS` (Police/Military, fabricated -- mirrors the real
liaison FUNCTION, not a real roster), and Fire Service/Medical, which
now dispatch the REAL nearest station/hospital from feature #4's data
instead of a separate fabricated entry. An incident's NADMO-team picker
defaults to ITS OWN district's team (falls back with a visible warning
if that team is already deployed elsewhere) rather than a flat
statewide list with no geographic logic. Each incident can now
accumulate any combination of NADMO/Fire/Medical/Liaison responders
(`inc["responders"]` list) inside a "Coordinate response" expander;
resolving an incident frees every responder type it picked up, not just
one. `store.assign_responder()` (the one field the shared store/citizen-
facing ETA can represent) is still called for the NADMO-team dispatch,
same as before -- Fire/Medical/Liaison dispatch is page-local
bookkeeping only, since OSM has no real availability feed to begin with.

**Verified:** AppTest end-to-end -- dispatched NADMO team (correctly
defaulted to the test incident's own assembly), Fire, and Medical, then
multiselected and requested Police Liaison; the success banner listed
all four (`NADMO: ... · Fire: Ghana Fire Service · Medical: Atta
Quarshie Merton Memorial Hospital · Liaison: Police Liaison`); Mark
Resolved correctly freed all four responder slots and returned the
queue to "No active incidents." No exceptions at any step.

## 5 — Road closure recommendations — Done

**Built:** Two layers, both reusing `INCIDENT_AVOID_RADIUS_DEG` (the
EXACT ~200m radius `build_incident_aware_weight()`/`incidents_near_path()`
already use to steer citizens around active incidents, so "flagged for
closure" can never diverge from "already being avoided"):

- `route_engine.segments_near_point()`/`road_closure_recommendations()`
  -- per-INCIDENT view, grouping the graph's real OSM edges (actual
  street names -- "Ring Road Central," "Nsawam Road," confirmed against
  the live pilot graph's 58,962 edges) by name. `GET /routing/road-closures`.
- `road_closure_score.py` (new) -- per-SEGMENT weighted closure score
  (0-100, same Low/Moderate/High/Very High breakpoints/colors as every
  other area score in this app, since closure urgency is that same kind
  of severity axis): 0.35 water depth (this event's own verified-report
  depth_hi_m, capped 1.5m) + 0.25 verified report count (diminishing
  1/2/3+, same scale as feature #3's cluster-size signal) + 0.15 road
  classification (OSM highway tag -- faster/busier roads score higher
  because floodwater there is more dangerous, not more flood-prone) +
  0.15 historical flood frequency (`geo_data.nearby_historical_events()`)
  + 0.10 near-term rainfall forecast (`open_meteo.py`, relative to this
  zone's own `rainfall_6h_critical_mm`, same comparison
  `routers/forecast.py` already makes). `GET /routing/road-closure-scores`.
  Found and fixed along the way: `route_engine._active_incidents()`
  never included `district` or `depth_lo_m`/`depth_hi_m` -- added both,
  the first a real crash (`KeyError: 'district'`) the user hit live
  while verifying real reports to test this feature.

New Streamlit page `govt_road_closures.py`, fourth in the Government
nav: KPI row, the weighted score table (Road / Recommendation / Score /
Reports / Road type -- the exact shape asked for), a "why this score"
expander per road, a folium map colored by the same Low/Moderate/High/
Very High palette, and a collapsed by-incident view underneath for the
simpler framing. Advisory only -- an officer still decides whether to
actually close anything.

**Verified:** live against the user's own real verified incidents (3
real reports at Kwame Nkrumah Circle, verified while testing this
feature) -- `GET /routing/road-closure-scores` returned 10 real road
segments with real, differentiated scores (86.2 for Nsawam Road/trunk
down to 75.7 for Tip Toe Lane/residential -- same incident, same depth/
reports/history, correctly separated only by road classification and
rainfall), all real OSM names, real depth (1.4m from the actual citizen
photo), real historical count (3), real near-term rainfall (0.0mm).
AppTest confirmed the Streamlit page renders the table/map/expanders
with no exceptions against this live data.

**Action recommendation (added after the initial build):** the 4-tier
Low/Moderate/High/Very High `level` above now feeds a separate, richer
officer-facing ACTION, decided primarily by reported water depth, not
the composite score -- Full closure (depth >= 1.0m) / Pedestrians only
(0.6-1.0m) / Emergency vehicles only (0.4-0.6m) / Monitor (0.15-0.4m) /
No action (< 0.15m), extending incident_store.py's existing shallow/
moderate/severe depth bands (0.15m/0.4m) with two more cuts. A sixth
action, "One lane restricted," was proposed, researched, and explicitly
dropped: only ~3% of this graph's 58,962 edges carry OSM's `lanes` tag,
so it couldn't be data-driven for the other 97% without guessing --
documented as a deliberate gap in `road_closure_score.py`'s docstring
rather than faked. When no report at a segment has a depth estimate,
action falls back to the coarser 4-tier level instead (`action_basis:
"score"` vs. `"depth"`, surfaced to the officer so they know which).
Verified directly (`_recommended_action()` called with depths spanning
all 5 bands) and live (`GET /routing/road-closure-scores` against the
same 3 real verified reports, correctly returned `🚧 Full closure` for
all 10 segments at their real 1.4m depth, `basis: "depth"`).

**Future improvement, deliberately not done now:** `road_closure_score.py`'s
five weights (0.35/0.25/0.15/0.15/0.10) are a reasoned starting point, not
empirically validated -- there's no historical "was closing this road the
right call" outcome data to validate or train against, and won't be until
real verified incidents + real closure decisions accumulate over a real
pilot deployment. Training an ML model now was considered and rejected:
with zero labeled outcomes, a model would just fit noise while losing the
transparency an officer needs to trust a specific recommendation (same
"aid, not a verdict" discipline as the confidence score and every area
score in this app). The recommended next step, if these weights are ever
revisited, is NOT ML either -- it's eliciting better-justified weights from
domain experts (NADMO/transport engineers) via AHP (Analytic Hierarchy
Process, pairwise comparison of the 5 factors), which produces defensible
weights without needing any training data. Only once real outcome data
exists would a simple, auditable calibration (e.g. logistic regression on
these same 5 signals against actual closure/outcome records) be worth
doing -- and even then, not a black-box model, for the same trust reason.

## 6 — Flood/incident timeline — Done

**Built:** `ReportEvent` (`backend/models.py`), a new append-only table
-- not new `Report` columns, so the live `thirdwave.db`'s existing
`Report` rows needed no migration, just `SQLModel.metadata.create_all()`
adding the new table alongside it. `backend/report_events.py`'s
`record_event()` is now called from every status-changing endpoint
(`submit_report`, `verify_report`/`verify_bulk`, `assign_responder`,
`resolve`), so every report gets a complete, real, timestamped event
log going forward. For anything that happened before this table
existed, `timeline_for_report()` reconstructs a best-effort timeline
from the report's own `submitted_at`/`verified_at`/`verified_by`/
`resolved_at` columns, each entry explicitly tagged
`reconstructed: true` with a note -- never presented as a real logged
event. One real gap even reconstruction can't close: there's no column
anywhere recording *when* a responder was assigned, so an old report
with `assigned_responder` set but no matching real event surfaces as
an "untimed note" instead of a fabricated timestamp. New
`GET /reports/{id}/timeline`. New Streamlit page `govt_timeline.py`,
fifth in the Government nav: pick a report (dropdown of recent pending/
verified/responding/resolved, or type an ID), see its event-by-event
history with icons, timestamps, and reconstruction warnings where they
apply.

**Verified:** against real data both directions. Backward: fetched the
timeline for 2 real reports that predate this feature (one verified,
one resolved) -- correctly reconstructed `submitted`/`verified`/
`resolved` entries, each marked `reconstructed: true` with the
explanatory note, correctly ordered. Forward: submitted a new tagged-
synthetic test report through the real API end-to-end (submit -> verify
-> assign-responder -> resolve), then fetched its timeline -- all 4
events logged in real time, `reconstructed: false`, correct detail
strings (`verified_by`, `responder name + ETA`), correctly ordered by
actual timestamp. AppTest confirmed the Streamlit page renders both the
picker (populated with real report IDs) and the full 4-event timeline
with no exceptions.

## 7 — Analytics dashboard — Done

**Built:** `backend/analytics.py`, three honest views over the live
`Report` table: `response_time_stats()` (verification latency
submitted->verified, resolution latency verified->resolved, n always
reported alongside mean/median/min/max so a thin sample is never read
as a stable number), `reports_by_district()` (plain count by district x
status), `recurring_hotspots()` (clusters only VERIFIED/RESOLVED reports
-- not pending/rejected -- with `clustering.py`'s same 300m grouping,
flags >=2-report clusters as a repeat-incident candidate, pairs each
with its location's existing static vulnerability score via
`geo_data.zone_for_point()`, and always states the real n behind the
claim rather than dressing up thin data as a trend -- the same
persistent-signal-vs-still-accumulating distinction
`govt_drain_priority.py` already draws). Three new endpoints under
`GET /analytics/{response-times,by-district,hotspots}`. New Streamlit
page `govt_analytics.py`, sixth in the Government nav: response-time
KPIs, a stacked bar chart + table of reports by district, and a
hotspots map/card view with the honesty caveat shown inline, not buried.

**Verified:** live against the real backend with the real reports
remaining after deleting the one synthetic test report from feature #6
-- 5 total reports (3 verified, 2 resolved, all in Ablekuma North
Municipal), 45.4h median verification time (n=5), 0min median
resolution time (n=2, the two test incidents that were resolved
instantly in an earlier session), and one real recurring-hotspot
candidate (4 of the 5 reports clustered at Kwame Nkrumah Circle, paired
with that zone's real static score of 29.8/Moderate), correctly
labeled with its n=5-report caveat. AppTest confirmed the Streamlit
page renders the KPIs, chart, table, and hotspot cards with no
exceptions.

## 8 — Multi-year encroachment trend view — Done

**Built:** `geo_data.channel_encroachment_timeseries()` (loader, same
pattern as every other loader there), `encroachment_trend_cells()`
(per-cell rows with a centroid joined in from `risk_zones()`'s geometry
-- the timeseries file itself has no geometry, just `zone_id`), and
`encroachment_trend_by_assembly()` (rollup). A 3-way Worsening/Stable/
Improving label on top of each cell's real linear-fit `slope_per_year`
(threshold +-0.01 NDBI/year, picked from this project's own real
distribution -- median -0.019, only 14 of 272 cells positive at all --
documented as a judgment call, not a validated cutoff). New
`GET /encroachment-trend/{by-assembly,cells}`. New Streamlit page
`govt_encroachment_trend.py`, seventh in the Government nav: KPI row,
an assembly rollup table, and a per-assembly map (colored by trend
direction) + a line chart of the 5 worst-trending cells' real 2019-2026
NDBI values. Pairs with feature #7's hotspots as the "is it getting
worse" independent-of-citizen-reports view.

**Verified:** live against the real backend and the real, already-
computed dataset (272 of 1013 pilot cells sit near a mapped waterway;
all 272 have the full 8 requested years, no thin-sample issue) --
`/encroachment-trend/by-assembly` correctly broke down all 7 pilot
assemblies (Weija Gbawe Municipal has the most channel-adjacent cells,
160, mean slope -0.0244), `/encroachment-trend/cells?assembly=...`
returned real per-cell centroids and directions. AppTest confirmed the
Streamlit page's KPIs (272 tracked, 5 worsening, 237 improving --
exactly matching a direct check of the raw JSON), table, map, and chart
all render with no exceptions.

**Real finding, investigated and flagged, not just noticed:** asked to
interpret the chart, inspected the actual year-by-year NDBI values (not
just the slopes) for the steepest "Worsening" and "Improving" cells.
The 5 steepest-improving cells turned out all in Weija Gbawe Municipal
and spatially adjacent (rows 12-15, cols 3-6 -- one cluster, not 5
independent samples), sharing one shape: moderate-positive NDBI in
2019-2021, a sharp drop to strongly negative across 2022-2025, partial
recovery in 2026. Cross-checked against `historical_flood_events.json`:
this lines up with real documented Weija Gbawe dam-release/storm floods
in 2020-10-11, 2022-10-04 (the sharp drop year, biggest documented
event of the group), and 2025-05-22 -- standing floodwater reads as
non-built-up in NDBI, same as any water body, so "Improving" for these
cells most likely means recurring flooding near the channel, not
reduced construction. (2026 had two more documented Weija floods yet
recovers in the data anyway -- most likely the annual composite's
cloud-free scenes didn't land during either flood week; noted as the
one point that doesn't fit cleanly, not treated as disproving the rest.)

Added `geo_data._documented_flood_years()` and a
`possible_flood_contamination` flag on every cell/assembly row (any
"Improving" cell in an assembly with a documented flood year inside its
tracked window) -- explicitly documented as a coarse, assembly-level
overlap check, not a verified per-cell match the way the 5 Weija cells
above were hand-checked. Surfaced in `govt_encroachment_trend.py` as a
dynamic warning banner (154 cells flagged: 147 Weija Gbawe, 7 Accra
Metropolis), a table column, map-tooltip flags, and a second trend
chart specifically for the steepest "Improving" cells. AppTest confirmed
the warning renders with the real counts and both charts render with no
exceptions.

**Second dataset-wide finding, and a fix for it:** checked whether the
2019-high pattern seen while reviewing individual assemblies was
universal. It is: across all 272 channel-adjacent cells, 2019 is the
single highest year of the 8-year series in 76.5% of them, higher than
2020 in 87.1%, present in every one of the 7 assemblies (78.6%-100%
each) -- too consistent to be independent real construction-clearing.
Checked and ruled out as the cause: the known Sentinel-2
baseline>=04.00 radiometric-offset bug (`channel_encroachment_timeseries.py`
already compensates for it correctly) and annual rainfall as a moisture
confound (pulled real Accra rainfall history: 2019 wasn't the driest
year on record -- drier years read LOWER in NDBI, the opposite of what
that would predict). Leading unconfirmed hypothesis: a scene-selection/
seasonal skew specific to 2019's thinner early Sentinel-2 archive --
not verifiable from the saved JSON, which only keeps a scene count per
year, not dates. Refitting every cell's slope on 2020-2026 alone (2019
dropped) flips the Worsening/Stable/Improving label for 22.1% of all
272 cells (60 of them) -- large enough to surface rather than silently
trust the 2019-inclusive slope alone.

Added `geo_data._linear_slope()` and a second slope per cell,
`slope_per_year_excl_2019`/`direction_excl_2019`, plus a
`sensitive_to_2019` flag wherever the label depends on which slope you
trust. Surfaced in `govt_encroachment_trend.py`: a 4th KPI ("Sensitive
to 2019"), a warning banner, a table column, map-tooltip detail, and a
🗓️ marker in the trend-chart legend (distinct from the ⚠️ flood-
contamination marker). Verified directly (`n sensitive: 60`, matching
the dataset-wide check) and via AppTest (no exception, both warnings
render with the real counts).

**Weija Gbawe flood-contamination finding, upgraded from possible to
confirmed for 5 cells:** re-fetched a single clean, low-cloud Sentinel-2
scene for the 5 hand-checked cells from a dry-season window far from
each flood date (2022-02-10, cloud 26%; 2025-02-04, cloud 0.8%) instead
of the flood-blended annual composite. Every cell's NDBI snapped back up
to its 2019-2021 baseline on that clean day -- e.g. `grid_r14_c3`'s 2025
composite of -0.379 becomes +0.180 on a clean day, at/above its own 2019
value of +0.169. This rules out the competing "floods discouraged
construction, so there's genuinely less built-up area" explanation for
these 5 cells: the built-up signal is still there, just submerged on
the days the annual composite happened to sample, not reduced. Updated
the CONFIRMED language in `geo_data.py`'s comment and
`govt_encroachment_trend.py`'s docstring/warning banner to reflect this
stronger evidence; left the assembly-level `possible_flood_contamination`
mechanism itself as a "lead to check," since only these 5 cells have
been hand-verified against a clean-day scene.

## 9 — District briefing workflow — gaps closed

**Grounding:** furthest along of everything on this list.
`backend/routers/briefings.py` already has a draft -> review -> approve/
reject lifecycle (see `.claude/plans/temporal-waddling-trinket.md`), and
`govt_briefing_review.py` is a working Streamlit prototype of it, already
talking to the backend over HTTP rather than session state. Known
architectural limit (stated in both places): actually publishing
approved text as a real Claude Doc isn't reachable from arbitrary backend
Python, only from a Claude Code/claude.ai agentic session.

**Checked and confirmed "partially built" with three concrete gaps,
all now closed:**

1. `risk_engine/briefing_queue.py`'s `clear_district()` was defined but
   never called anywhere -- a flagged district stayed flagged forever,
   even after a briefing was drafted and approved for it. Wired into
   `backend/routers/briefings.py`'s `create_draft()`, matching the
   module's own documented contract ("called once a Briefing for this
   district has been drafted"). Imported from `risk_engine/` via a
   `sys.path` insert rather than re-implemented, so the two can't drift
   apart.
2. `govt_district_dashboard.py`'s briefing-queue banner was pure text --
   an officer had to manually re-type the district/reason on a separate
   page. Each flag now gets its own "Draft ->" button that stores the
   district/reason/source_finding in `st.session_state["brf_prefill"]`;
   `govt_briefing_review.py`'s draft form picks it up and pre-fills all
   three fields (consumed once via `.pop`, so it doesn't keep stomping
   on manual edits). Streamlit's radio-based nav can't jump pages
   itself, so the officer still switches tabs manually -- stated
   plainly in the banner's own text rather than overclaiming.
3. A real flag had been sitting in the queue since 2026-10-15 for
   `"La-Nkwantanang-Madina"` (missing the "Municipal" suffix every other
   file in this project uses for that assembly) and couldn't be
   selected in the draft form's dropdown at all. Added the correct
   `"La-Nkwantanang-Madina Municipal"` to `KNOWN_DISTRICTS`, and -- the
   real fix -- the dropdown now always unions `KNOWN_DISTRICTS` with
   whatever district names are actually sitting in the queue, so any
   future naming mismatch stays selectable instead of silently stuck.

**Verified:** live against the real backend and the real queue file
(not a mock) -- added a disposable `"TEST-District-DoNotUse"` flag,
drafted a briefing for it via `POST /briefings/draft`, confirmed the
queue file afterward had that entry removed while the real, untouched
`La-Nkwantanang-Madina` entry was still present (proving `clear_district`
matches by exact district name and doesn't over-clear); deleted the
test Briefing row directly from `thirdwave.db` afterward (no DELETE
endpoint exists). AppTest confirmed the full UI loop end-to-end: clicking
"Draft ->" on the District Dashboard's real queue entry set the prefill,
switching pages (Operations -> District Briefing Review) picked it up,
and all three fields (district, reason, source finding) matched the
real queue entry exactly -- no exceptions anywhere, and the dropdown
confirmed to contain both the real queue's exact string and the
corrected canonical name.
