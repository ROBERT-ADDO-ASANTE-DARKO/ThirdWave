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

## Status at a glance

| # | Feature | Status | Commit(s) |
|---|---------|--------|-----------|
| 0 | AI Assistant extended-coverage wiring (`ai_tools.py`) | **Done** | -- (uncommitted) |
| 1 | Live incident map (clustering + severity colors) | **Done** | -- (uncommitted) |
| 2 | Incoming reports queue (Pending/Verified/Responding/Resolved) | **Done** | -- (uncommitted) |
| 3 | Report confidence score | Not started | -- |
| 4 | Resource allocation (NADMO/fire/ambulance/boats/shelters) | Not started -- **open data gap, see below** | -- |
| 5 | Road closure recommendations | Not started | -- |
| 6 | Flood/incident timeline | Not started | -- |
| 7 | Analytics dashboard | Not started | -- |
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

## 3 — Report confidence score

**Grounding:** three real signals exist, two already backend-ported and
one not: `vlm_client.py` (Claude-vision photo validation -- has a
validated test fixture), `news_corroboration.py` (backend port exists,
checks live MyJoyOnline/3News), and `citizen_report_sar_check.py`
(Sentinel-1 SAR cross-check -- exists only as an offline `risk_engine`
script, never ported to the backend). Plus "multiple reports from the
same area" is exactly what `clustering.py` already groups.
**Needed:** port `citizen_report_sar_check.py`'s logic to the backend,
then a composite score combining all three signals + cluster size +
nearby historical events.

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

## 5 — Road closure recommendations

**Grounding:** `backend/route_engine.py` already has a precomputed
risk-weighted road graph for the pilot district (OSMnx + per-edge
vulnerability cost), ported from `streamlit_app/features/citizen_routing.py`.
**Needed:** flag edges passing through verified/responding incidents and
feed that back into the existing risk-weighted routing, rather than
building a second graph -- an officer-facing "recommend closing this
segment" view on top of data that's already there.

## 6 — Flood/incident timeline

**Grounding:** `Report` has `submitted_at`/`verified_at` timestamps, but
no full state-change audit log -- there's no record of *when* a report
moved from pending to verified to responding to resolved, only the
current state. **Needed:** a new event-log table (or a simple append-only
history on the Report row) before this feature can show real evolution
over time, not just current snapshots.

## 7 — Analytics dashboard

**Grounding:** response-time stats (`verified_at - submitted_at`, etc.)
are computable today from existing timestamps. "Recurring hotspots"
needs the same honest distinction `govt_drain_priority.py` already draws
between multi-year SAR water-occurrence (persistent signal, have it) and
verified repeat-incident history (needs live pilot data to accumulate,
don't have it yet).

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
