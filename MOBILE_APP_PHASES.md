# Mobile app rehearsal — phase tracker

A FastAPI + Flutter rebuild of the reporting/verification/notification
loop that `streamlit_app/` currently only simulates in-process (session
state, no real push). Six phases, scoped to close the README's stated
honest limitations ("Session-only storage", "Not real push
notifications") incrementally rather than as one rewrite. Update this
file as each phase lands -- status, what actually got built, what's
still deferred, and the commit(s) that did it.

## Status at a glance

| # | Phase | Status | Commit(s) |
|---|-------|--------|-----------|
| 0 | Scope the walking skeleton | Done (planning only) | -- |
| 1 | FastAPI backend + database | **Done** | `4454566` |
| 2 | FCM push notifications | **Done** | `ee41efe`, `07d02f8` |
| 3 | Minimal auth | **Done** | `da6c347` |
| 4 | Real Flutter citizen app | **In progress** | -- |
| 5 | Port Streamlit features onto the new backend | Not started | -- |

## Phase 0 — scope the walking skeleton

Deliberately narrow first milestone instead of porting every Streamlit
feature at once: *submit a report → it lands in the backend → an
officer verifies it → the phone gets a real push.* Everything else
(routing, AI assistant, dashboards) deferred to Phase 5. No code; this
was a planning decision.

## Phase 1 — FastAPI backend + database — `4454566`

Reports and incidents moved from `incident_store.py`'s three in-memory
`st.session_state` lists (pending/active/resolved) into one SQLite-backed
`Report` table with a `status` field, since a database shouldn't need to
move rows between tables for a status change the way session state did.

**Built:** `backend/models.py` (Report, Device), `db.py` (SQLite engine),
`geo_data.py` (district/zone lookups, ported from `data_loader.py` minus
the Streamlit cache decorators), `clustering.py` and
`news_corroboration.py` (ported from the equivalents just added to
`streamlit_app/`, deliberately duplicated rather than imported so this
service stays runnable without a Streamlit dependency), `routers/reports.py`
and `routers/incidents.py` (10 endpoints: submit, pending, clusters,
verify, verify-bulk, active, nearby, assign-responder, resolve, health).

**Verified:** full submit→verify→resolve flow via FastAPI's `TestClient`,
then the actual `uvicorn main:app` entry point separately, to confirm
routes register correctly outside the test harness.

**Deferred:** Lower Volta extended-coverage district/zone fallback isn't
ported (noted in `geo_data.py`).

## Phase 2 — FCM push notifications — `ee41efe`, `07d02f8`

`backend/push.py`: haversine-filters registered devices by last-known
location (option A from the Phase 2 design discussion -- consistent with
how `/incidents/nearby` already works, vs. FCM topic subscriptions per
district, the coarser but staler-location-proof alternative). One push
per verify *action*, not per report, so a bulk-verified storm cluster
doesn't spam one phone N times. `routers/devices.py`: device registration,
upserted by FCM token.

**The two real bugs this phase's debugging actually found** (both only
catchable against a real device, not firebase-admin's local API surface):
1. `Message.fid` is a Firebase **Installation ID**, not a renamed
   registration token, despite the SDK's deprecation warning on
   `Message.token` reading like a drop-in rename. Every real device token
   sent via `fid=` came back `NotRegistered` no matter how many fresh
   tokens were generated -- found by reading `_messaging_encoder.py`'s
   own field docs after exhausting every project-config explanation (API
   enablement, key restrictions, App Check, device clock, GMS state,
   build staleness). `token=` is correct for an actual FCM token.
2. A long-running `uvicorn` process (no `--reload`) doesn't pick up an
   edited `push.py` -- the first post-fix test ran against stale
   in-memory code and wrongly pruned every device row, including a
   confirmed-working one.

**`mobile/push_test_stub`:** a throwaway Flutter app (Android-only, no
Apple Developer account needed) whose only job is obtaining a real FCM
token and registering it, built specifically because this class of bug
is invisible to a same-process test with a hand-built fake token.

**Verified:** real notification displayed on a real phone (Infinix Hot
60 Pro+ / Infinix X6886), through the actual `/reports/{id}/verify`
endpoint, not a bypass script.

**Deferred:** no notification de-dup/cooldown beyond per-verify-call
batching, no delivery confirmation (FCM accepting a send isn't the same
as the phone displaying it), iOS untested (needs its own APNs
configuration in the Firebase console).

## Phase 3 — minimal auth — `da6c347`

Every endpoint was open to anyone who could reach the backend until this
phase -- fine for localhost-only testing, a real gap once a phone on the
LAN is a legitimate client.

- **Citizens:** `reporter_ref` is now required on submission (no more
  `"unknown"` default), meant to be a UUID the client generates once and
  persists locally. Still no login.
- **Officers:** a single shared API key (`X-Officer-Key` header,
  `backend/auth.py`) gates the privileged endpoints -- pending/clusters
  queues, verify/verify-bulk, active incidents, assign-responder,
  resolve. Citizen-facing endpoints (submit, register device, nearby
  incidents) stay open.

**Explicitly not real production security:** one shared key means
`verified_by` is a free-text claim, not cryptographically tied to a
specific officer. Per-officer accounts are a stated gap, not an
oversight.

**Verified:** via `TestClient` -- citizen endpoints work key-less,
officer endpoints 401 with no/wrong key and succeed with the right one,
a wrong-key verify attempt correctly leaves the report `pending`.

## Phase 4 — real Flutter citizen app — in progress

The real citizen-facing app, replacing `push_test_stub` rather than
building on it (that app is explicitly throwaway, see its own README).
Feature list mirrors `streamlit_app`'s six citizen pages exactly (see
README.md's feature table) -- each needs a backend endpoint and a
Flutter screen, checked separately since several need backend work that
doesn't exist yet: only `reports`/`incidents`/`devices` routers exist as
of Phase 3. Zones, historical events, rainfall, routing, and the AI
assistant have no backend endpoint at all yet.

### App shell (shared groundwork, not one of the six features) — done

- [x] Project scaffold (`flutter create`, real app -- not `push_test_stub`)
      -> `citizen_app/`, package `com.thirdwave.citizen`
- [x] Persistent anonymous `reporter_ref` (UUID generated once, stored
      locally via `shared_preferences`) -- `lib/services/identity_service.dart`
- [x] FCM token registration + foreground notification handling, lifted
      from `push_test_stub` -- `lib/services/push_service.dart`.
      Background/terminated notifications need no extra code (handled by
      the OS from the `notification` payload), same as `push_test_stub`
      found.
- [x] Navigation shell -- bottom nav, Home (shell status) + 6 feature
      tabs, 5 still `PlaceholderScreen`. Shared location-permission
      plumbing deliberately NOT added yet -- deferred to the first
      feature that actually needs GPS (`lib/screens/`).

**Two real findings while building only the shell** (recorded, not
skipped past):
1. `flutter build apk` crashed the Gradle daemon with a native OOM --
   this dev machine has 5 GB total RAM, and Flutter's default
   `org.gradle.jvmargs` (`-Xmx8G`) asks for more heap than exists on the
   machine, let alone what's left after the OS/IDEs. Fixed in both
   `citizen_app/android/gradle.properties` and (same inherited default)
   `mobile/android/gradle.properties`, down to `-Xmx1536m`.
2. A second instance of Phase 2's fid-vs-token trap, from the client
   side this time: `firebase_messaging` 17.0.0 deprecates `getToken()` in
   favor of `register()`/`onRegistered` -- but `onRegistered` yields a
   Firebase **Installation ID**, not an FCM token, per the package's own
   doc comments. Switching would need `backend/push.py` migrated to
   FID-based direct-send too; deliberately kept `getToken()` instead,
   documented in `push_service.dart` rather than silently "fixed".

**Hardware blocker, as of 2026-10-24: `flutter build apk` crashed/froze
this dev machine twice**, the second time requiring a hard restart, even
after lowering the Gradle heap (down to 1536MB), disabling the daemon,
and capping workers at 1 -- a live memory watchdog never saw free RAM
drop below 250MB either time, so the failure is a genuine capacity
ceiling, not a tunable setting. Root cause: the board (HP Laptop
14-dk1xxx, AMD 3020e) has a free second SODIMM slot and supports up to
32GB, but only 8GB is installed today, and the integrated Radeon
graphics carve a further chunk out of what Windows reports as usable
(~6GB visible). **On-device Android/Flutter builds are paused on this
machine until RAM is upgraded** -- a second 8GB+ SODIMM in the empty
slot is the concrete fix. Work that doesn't need the Android toolchain
(backend endpoints, `flutter analyze`-only Dart code) can continue in
the meantime; `flutter build`/`flutter run` should not be attempted
again until the upgrade lands.

### 1. Current Vulnerability by Address

- [x] Backend: `GET /zones/lookup?address=` -- `routers/zones.py` +
      `geo_data.find_zone_by_address()`/`_geocode()`/`nearby_historical_events()`,
      ported faithfully from `streamlit_app/geo_tools.py`'s function of the
      same name (geocode retry fallback, zone containment, the
      score+historical-events join). Lower Volta fallback not ported, same
      documented Phase 1 gap. Citizen-facing, no officer key.
- [x] Flutter: `lib/screens/address_vulnerability_screen.dart` -- address
      search, zone score/level card (same color palette as
      `data_loader.LEVEL_COLOR`), contributing factors, historical
      events. `flutter analyze` clean. **Not build/run-tested on a real
      device** -- blocked by the hardware issue above, same as everything
      else in `citizen_app/` past the app shell.

**Testing note, not a bug:** the very first geocode request against a
freshly-started `TestClient` instance failed consistently (silently
swallowed by `_geocode()`'s bare `except: pass`, same as the original
Streamlit code), while the identical query against a real, already-warm
`uvicorn` process succeeded every time -- almost certainly a cold-start
networking hiccup right after `geo_data`'s heavy `geopandas` import
during app startup, not a defect in the endpoint. Verified against a
real persistent server instead: correct zone, score, contributing
factors, and all 3 relevant historical events (2015/2023/2026 Circle-area
floods) for Kwame Nkrumah Circle; correct out-of-coverage response for
Kumasi; correct error for an unresolvable address.

### 2. Crowdsourced Flood Reporting

- [ ] Backend: VLM drafting endpoint (photo in -> draft description +
      depth estimate + annotated image out), porting `vlm_client.py`'s
      Claude vision call -- new work, not yet planned as an endpoint
- [x] Backend: `POST /reports` itself (Phase 1)
- [ ] Flutter: camera/gallery picker + GPS capture + draft review/edit
      screen + submit

### 3. Rainfall Forecast

- [ ] Backend: `GET /forecast/rainfall?lat=&lon=` (proxy to Open-Meteo,
      same as `citizen_forecast.fetch_rainfall_forecast`)
- [ ] Flutter: location picker + 6h precipitation chart

### 4. High-Risk Zone Alert

- [ ] Backend: none beyond #1 + #3 + the existing `GET /incidents/nearby`
      -- combine client-side rather than adding a new aggregating
      endpoint, unless that proves awkward in practice
- [ ] Flutter: map combining zone score, rainfall, and nearby verified
      incidents with distance

### 5. Safer Routing

- [ ] Backend: `GET /routing/safer-route?origin=&dest=` -- the biggest
      backend gap, porting `citizen_routing.py`'s graph-based
      fastest-vs-vulnerability-weighted routing (`pilot_road_network.gpickle`
      + networkx) with dynamic incident-based edge penalties
- [ ] Flutter: origin/destination input (typed address or live GPS) +
      dual-route map

### 6. AI Assistant

- [ ] Backend: chat endpoint wrapping `geo_tools.py`'s Claude tool-calling
      loop (same assistant as the government console)
- [ ] Flutter: chat UI

**Known scope note:** items marked "Backend: none beyond..." assume
client-side composition is good enough; revisit if that turns out to
need real server-side aggregation (e.g. for caching or to keep the
Flutter client thin).

## Phase 5 — port Streamlit features onto the new backend — not started

Government-side features (district dashboard, drain priority, resource
allocation, incident verification sandbox) repointed at the FastAPI
backend instead of `incident_store.py`'s session state, so Streamlit
becomes one more client of the same backend Phase 4's app talks to,
rather than two disconnected systems. `incident_store.py`'s clustering/
news-corroboration copies get retired in favor of the backend's once
this lands (see Phase 1's "deliberately duplicated" note).
