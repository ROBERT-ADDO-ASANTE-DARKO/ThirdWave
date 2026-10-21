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
| 4 | Real Flutter citizen app | Not started | -- |
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

## Phase 4 — real Flutter citizen app — not started

The actual citizen-facing app: map, report submission (photo + GPS),
address-based zone lookup, safer routing, the AI assistant -- the real
counterpart to `streamlit_app/features/citizen_*.py`, replacing
`push_test_stub` rather than building on it (that app is explicitly
throwaway, see its own README).

## Phase 5 — port Streamlit features onto the new backend — not started

Government-side features (district dashboard, drain priority, resource
allocation, incident verification sandbox) repointed at the FastAPI
backend instead of `incident_store.py`'s session state, so Streamlit
becomes one more client of the same backend Phase 4's app talks to,
rather than two disconnected systems. `incident_store.py`'s clustering/
news-corroboration copies get retired in favor of the backend's once
this lands (see Phase 1's "deliberately duplicated" note).
