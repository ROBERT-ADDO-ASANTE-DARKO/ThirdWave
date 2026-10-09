# push_test_stub

A throwaway Flutter app -- NOT the real Phase 4 citizen app. Its only job is
to get a real FCM token onto a real Android phone, register it with the
ThirdWave backend (`backend/push.py` / `routers/devices.py`), and show
notifications as they arrive, so a `verify_report`/`verify_bulk` call can be
proven to actually reach a device instead of just reaching Google's servers
(which `backend/`'s own test already confirmed -- see its commit history).

## One-time setup (your side -- needs your Firebase login, can't be scripted)

1. In the Firebase console (the same `first-firebase-project-c2ccf` project
   the backend's service-account credential belongs to): **Project settings
   -> Add app -> Android**.
2. Android package name: **`com.thirdwave.push_test_stub`** -- must match
   exactly, it's already set in `android/app/build.gradle.kts`.
3. Download the generated `google-services.json` and place it at
   `mobile/android/app/google-services.json`. It's gitignored (see
   `mobile/.gitignore`) -- this file is project-specific and never committed.
4. Find this PC's LAN IP (`ipconfig` on Windows, look for IPv4 Address) --
   the phone can't reach the backend via `localhost`, it needs this
   machine's address on the same WiFi network.

## Running it

```
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000   # --host 0.0.0.0, not the default
                                                # 127.0.0.1, so the phone can reach it
```

```
cd mobile
flutter run   # pick your connected phone when prompted (enable USB debugging first)
```

In the app:
1. Wait for the FCM token to appear (grant the notification permission
   prompt first).
2. Set the "Backend base URL" field to `http://<this PC's LAN IP>:8000`.
3. Tap **Register device with backend** -- lon/lat default to Kwame Nkrumah
   Circle, edit them to test whether a report falls inside or outside
   `push.py`'s `DEVICE_NOTIFY_RADIUS_KM` (1.5km default).
4. From Swagger UI (`http://localhost:8000/docs` on the PC) or the
   Streamlit sandbox, verify a report near that point.
5. Watch the phone -- a system notification should arrive if the app is
   backgrounded, or show up in the "Received while app is open" list if
   it's in the foreground.

## What this app deliberately doesn't do

No login, no report submission, no map, no district assignment -- none of
the real citizen-app features. It exists to answer exactly one question:
does a push notification sent by `backend/push.py` actually reach a real
phone. Phase 4 (the real citizen app) is separate, later work.
