"""
push.py — Phase 2: push a notification to nearby registered devices when a
report is verified, via Firebase Cloud Messaging (FCM).

Uses the modern FCM v1 API through the official firebase-admin SDK (a
service-account credential + automatic OAuth2 token refresh), not the
legacy server-key HTTP API Google has been retiring -- hand-rolling that
older API would mean building on a method already being phased out.

Targeting: option (A) from the project's Phase 2 discussion -- each
device's LAST-KNOWN lat/lon (sent at registration), filtered by the same
haversine distance used elsewhere (clustering.py, routers/incidents.py's
/nearby). Not continuous location tracking: a device's position is only as
fresh as its last registration call. Option (B) (FCM topic subscriptions
per district) would avoid that staleness but trades away radius precision
for district-level granularity -- noted as the production-grade
alternative, not built here.

One notification per verify ACTION, not per report: verify_bulk calls this
once for the whole cluster (centroid of the approved reports), so a
20-report storm cluster doesn't fire 20 pushes at the same nearby phone.

Dead tokens: FCM tells us per-message which tokens are unregistered/
invalid. Those rows are deleted from the devices table on the spot --
leaving them in would mean silently-failing sends accumulate forever.
"""

from __future__ import annotations

import os
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, exceptions, messaging
from sqlmodel import Session, select

from clustering import haversine_km
from models import Device

load_dotenv(Path(__file__).parent / ".env")

DEVICE_NOTIFY_RADIUS_KM = 1.5  # same default as incident_store.nearby_active_incidents

_app: firebase_admin.App | None = None


def _get_app() -> firebase_admin.App:
    """Lazy init -- most of this backend's test suite/TestClient runs never
    touch push notifications at all, so there's no reason to require a
    valid credential just to import this module or start the server."""
    global _app
    if _app is None:
        cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
        if not cred_path:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_PATH not set (backend/.env) -- "
                "push notifications need a Firebase service-account credential."
            )
        full_path = Path(__file__).parent / cred_path
        _app = firebase_admin.initialize_app(credentials.Certificate(str(full_path)))
    return _app


def notify_nearby_devices(
    session: Session, lon: float, lat: float, title: str, body: str,
    radius_km: float = DEVICE_NOTIFY_RADIUS_KM,
) -> dict:
    """Send one push to every device within radius_km of (lon, lat).
    Returns a summary dict; never raises on an individual send failure --
    a bad token for one citizen's phone shouldn't block the others or the
    verify request that triggered this."""
    devices = list(session.exec(select(Device)).all())
    targets = [
        d for d in devices
        if d.last_lon is not None and d.last_lat is not None
        and haversine_km(lon, lat, d.last_lon, d.last_lat) <= radius_km
    ]
    if not targets:
        return {"targeted": 0, "sent": 0, "failed": 0, "pruned": []}

    app = _get_app()
    messages = [
        messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            # NOT `fid=` despite the SDK's deprecation warning on `token=` --
            # fid is a Firebase INSTALLATION ID (a different identifier type),
            # not a renamed FCM registration token. Confirmed by reading
            # _messaging_encoder.py directly after every real device token
            # came back NotRegistered with fid=: an FCM token in the fid
            # field matches no real installation, so it fails deterministically
            # regardless of how valid the token itself is. token= is still
            # the correct field for an actual FCM registration token.
            token=d.fcm_token,
        )
        for d in targets
    ]
    responses = messaging.send_each(messages, app=app).responses

    sent = failed = 0
    pruned: list[str] = []
    for device, resp in zip(targets, responses):
        if resp.success:
            sent += 1
            continue
        failed += 1
        # UnregisteredError: a once-valid token the app/user has since
        # revoked (uninstall, etc). InvalidArgumentError can ALSO mean the
        # token is just malformed garbage that will never succeed -- confirmed
        # empirically (see commit), not assumed: a fake token in testing came
        # back as InvalidArgumentError with this exact message, not
        # UnregisteredError. Both are genuinely dead rows, not transient
        # failures (unlike e.g. QuotaExceededError), so both get pruned.
        dead = isinstance(resp.exception, messaging.UnregisteredError) or (
            isinstance(resp.exception, exceptions.InvalidArgumentError)
            and "registration token" in str(resp.exception).lower()
        )
        if dead:
            session.delete(device)
            pruned.append(device.id)
    if pruned:
        session.commit()

    return {"targeted": len(targets), "sent": sent, "failed": failed, "pruned": pruned}
