# citizen_app

The real Phase 4 citizen app (see repo-root `MOBILE_APP_PHASES.md`) --
replaces `mobile/push_test_stub`, which stays as a throwaway push-testing
tool, not something this app builds on.

## Status

App shell (identity -- persistent anonymous `reporter_ref`, push
registration lifted from `push_test_stub`) plus all six citizen features
from `streamlit_app`'s README table, now real screens: Current
Vulnerability by Address, Crowdsourced Flood Reporting, Rainfall
Forecast, High-Risk Zone Alert, Safer Routing, and the AI Assistant. See
`MOBILE_APP_PHASES.md`'s Phase 4 checklist for what was ported as-is vs.
deliberately scoped down (mostly: pilot district only, no Lower
Volta/Ayawaso West/Madina extended coverage). Not build/run-tested on a
real device -- see that file's hardware-blocker note.

## One-time setup (your side -- needs your Firebase login, can't be scripted)

Same Firebase project as `push_test_stub` (`first-firebase-project-c2ccf`),
a **separate** Android app registration since the package name differs:

1. Firebase console -> Project settings -> Add app -> Android.
2. Package name: **`com.thirdwave.citizen`** -- must match exactly,
   already set in `android/app/build.gradle.kts`.
3. Download the generated `google-services.json` -> place at
   `citizen_app/android/app/google-services.json`. Gitignored, same
   treatment as the backend's service-account credential and
   `push_test_stub`'s copy -- project-specific, never committed.

(If you register this app in the same Firebase project as `push_test_stub`,
re-downloading `google-services.json` from either app's settings page
gives you one file with both apps' configs in it -- safe to reuse the
same file in both `mobile/android/app/` and here, the Google Services
Gradle plugin picks the matching entry by package name at build time.)

## Running it

```
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

```
cd citizen_app
flutter run
```

Officer-gated backend endpoints (verify, pending/clusters, active
incidents, assign-responder, resolve) need `X-Officer-Key` -- not
relevant to this app, which only ever calls the citizen-facing endpoints
(submit, register device, nearby incidents, and whatever Phase 4's
remaining features add).

## A real bug found building just the app shell, worth knowing about

`flutter analyze` flagged `getToken()` as deprecated in favor of
`register()`/`onRegistered`. Checked before "fixing" it (see
`lib/services/push_service.dart`'s comment): `onRegistered` yields a
Firebase **Installation ID**, not an FCM token -- the same fid-vs-token
confusion Phase 2's backend work hit, from the client side this time.
Switching would need `backend/push.py` migrated to FID-based direct-send
too; deliberately deferred, not fixed blindly.

Also: `flutter build apk` crashed the Gradle daemon outright (JVM
`OutOfMemoryError`, native mmap failure) on this machine -- it has 5 GB
total RAM, and Flutter's default `org.gradle.jvmargs` (`-Xmx8G`) asks for
more heap than physically exists. Fixed in `android/gradle.properties`
(here and in `mobile/`, same inherited template default) by lowering it
to `-Xmx1536m`. Worth raising again if a future machine has more RAM and
builds feel memory-starved.
