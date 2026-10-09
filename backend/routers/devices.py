"""
routers/devices.py — device registration for push notifications (Phase 2).

Upsert keyed by fcm_token, not a client-supplied device id: a token can
rotate (app reinstall, Firebase token refresh), and treating each token as
the identity (one row per currently-valid token, re-registering just
refreshes that row's last-known location) is simpler than asking a client
to manage its own stable id and reconcile it with a changing token.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session
from models import Device
from schemas import DeviceRegisterBody

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register")
def register(body: DeviceRegisterBody, session: Session = Depends(get_session)):
    existing = session.exec(select(Device).where(Device.fcm_token == body.fcm_token)).first()
    if existing:
        existing.platform = body.platform
        existing.last_lat = body.lat
        existing.last_lon = body.lon
        existing.registered_at = datetime.now(timezone.utc)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    device = Device(
        id=f"DEV-{uuid4().hex[:10].upper()}", fcm_token=body.fcm_token, platform=body.platform,
        last_lat=body.lat, last_lon=body.lon, registered_at=datetime.now(timezone.utc),
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.delete("/{device_id}")
def unregister(device_id: str, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "device not found")
    session.delete(device)
    session.commit()
    return {"status": "deleted"}
