"""
auth.py — Phase 3 (minimal): gate the district-officer endpoints behind a
single shared API key, since every endpoint was open to anyone who could
reach the backend until now. This is NOT real production auth -- one
shared key means `verified_by` is a free-text claim an officer types in,
not something cryptographically tied to a specific person. Per-officer
accounts are a real gap, deliberately deferred, not an oversight: this
phase's job is closing "anyone can verify/reject/resolve incidents with
zero access control," not building a full identity system.

Citizen-facing endpoints (submit a report, register a device, check
nearby incidents) stay open -- no key, no login. Adding friction there
would cut against the whole point of a low-barrier reporting pipeline.
"""

import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

load_dotenv(__file__.rsplit("auth.py", 1)[0] + ".env")

_officer_key_header = APIKeyHeader(name="X-Officer-Key", auto_error=False)


def require_officer(key: str | None = Depends(_officer_key_header)) -> None:
    expected = os.environ.get("OFFICER_API_KEY")
    if not expected:
        raise HTTPException(500, "OFFICER_API_KEY not configured (backend/.env)")
    if key != expected:
        raise HTTPException(401, "Missing or invalid X-Officer-Key header")
