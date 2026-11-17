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
| 4 | Resource allocation (NADMO/fire/ambulance/boats/shelters) | Not started -- **open data gap, see below** | -- |
| 5 | Road closure recommendations | **Done** | -- (uncommitted) |
| 6 | Flood/incident timeline | **Done** | -- (uncommitted) |
| 7 | Analytics dashboard | **Done** | -- (uncommitted) |
| 8 | Multi-year encroachment trend view | Not started | -- |
| 9 | District briefing workflow | Partially built already | -- |

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

## 4 — Resource allocation — OPEN DATA GAP

**Grounding:** `govt_resource_allocation.py`'s own docstring says its
responder list is **100% fabricated demo data**, explicitly labeled as
such. No real NADMO/fire/ambulance/boat/shelter location data exists
anywhere in this project. OSM Overpass can get real fire stations and
hospitals (`amenity=fire_station`/`hospital`), but NADMO offices, boats,
and shelters aren't reliably mapped in Ghana OSM data.
**Decision needed before building this one:** stay honestly-labeled
synthetic for the pilot (consistent with the rest of the project's
honesty discipline), or invest time sourcing what real data is gettable
(OSM for fire/hospital at minimum) and clearly caveat the rest.

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

## 8 — Multi-year encroachment trend view

**Grounding:** `risk_engine/channel_encroachment_timeseries.py` already
computes NDBI-based "is this channel edge getting more built-up over
time" per cell, pilot-grid only. Never surfaced in any UI (Streamlit or
backend) yet. **Needed:** a loader + endpoint (same pattern as every
other `geo_data.py` loader) and a chart, pairing naturally with feature
#7's hotspot analytics as an "is it getting worse" view rather than a
single snapshot.

## 9 — District briefing workflow

**Grounding:** furthest along of everything on this list.
`backend/routers/briefings.py` already has a draft -> review -> approve/
reject lifecycle (see `.claude/plans/temporal-waddling-trinket.md`), and
`govt_briefing_review.py` is a working Streamlit prototype of it, already
talking to the backend over HTTP rather than session state. Known
architectural limit (stated in both places): actually publishing
approved text as a real Claude Doc isn't reachable from arbitrary backend
Python, only from a Claude Code/claude.ai agentic session.
