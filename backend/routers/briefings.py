"""
routers/briefings.py — district assembly briefing lifecycle (draft stored
-> human review -> approved/rejected). See
.claude/plans/temporal-waddling-trinket.md.

Deliberate scope boundary: this router only stores and transitions
Briefing rows. It does NOT call the Claude API to draft text (that's
streamlit_app/geo_tools.py's draft_briefing(), which needs the same
tool-calling setup ai_assistant.py already has) and does NOT publish to
Claude Docs (that connector is only reachable from a Claude Code/claude.ai
agentic session, not from arbitrary backend Python -- there is no public
API for it). POST /briefings/draft therefore takes the already-drafted
sections as input rather than generating them itself; approving a
briefing accepts a doc_url the client already obtained, rather than this
router trying to produce one.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi import Depends
from sqlmodel import Session, select

from db import get_session
from models import Briefing
from schemas import DraftBriefingBody, ReviewBriefingBody, UpdateBriefingSectionsBody

router = APIRouter(prefix="/briefings", tags=["briefings"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return f"BRF-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"


def _serialize(b: Briefing) -> dict:
    return {
        "id": b.id, "district": b.district, "trigger_reason": b.trigger_reason,
        "source_finding": b.source_finding, "status": b.status,
        "sections": json.loads(b.draft_sections), "doc_url": b.doc_url,
        "created_at": b.created_at.isoformat(),
        "reviewed_at": b.reviewed_at.isoformat() if b.reviewed_at else None,
        "reviewed_by": b.reviewed_by,
    }


@router.post("/draft")
def create_draft(body: DraftBriefingBody, session: Session = Depends(get_session)):
    """Store an already-drafted briefing. `body.sections` is produced by
    streamlit_app/geo_tools.py's draft_briefing() -- this endpoint just
    persists it so it survives past one Streamlit session and can be
    reviewed/edited."""
    briefing = Briefing(
        id=_new_id(), district=body.district, trigger_reason=body.trigger_reason,
        source_finding=body.source_finding, status="drafted",
        draft_sections=json.dumps(body.sections), created_at=_now(),
    )
    session.add(briefing)
    session.commit()
    session.refresh(briefing)
    return _serialize(briefing)


@router.get("/pending")
def list_pending(district: str | None = None, session: Session = Depends(get_session)):
    stmt = select(Briefing).where(Briefing.status == "drafted")
    if district:
        stmt = stmt.where(Briefing.district == district)
    rows = list(session.exec(stmt).all())
    rows.sort(key=lambda b: b.created_at, reverse=True)
    return [_serialize(b) for b in rows]


@router.get("/{briefing_id}")
def get_briefing(briefing_id: str, session: Session = Depends(get_session)):
    briefing = session.get(Briefing, briefing_id)
    if briefing is None:
        raise HTTPException(404, "briefing not found")
    return _serialize(briefing)


@router.patch("/{briefing_id}/sections")
def update_sections(briefing_id: str, body: UpdateBriefingSectionsBody, session: Session = Depends(get_session)):
    """An officer editing the draft before publishing -- see
    UpdateBriefingSectionsBody's docstring: the edited text is what gets
    published, not the original AI draft."""
    briefing = session.get(Briefing, briefing_id)
    if briefing is None or briefing.status != "drafted":
        raise HTTPException(404, "drafted briefing not found")
    current = json.loads(briefing.draft_sections)
    current.update(body.sections)
    briefing.draft_sections = json.dumps(current)
    session.add(briefing)
    session.commit()
    session.refresh(briefing)
    return _serialize(briefing)


@router.post("/{briefing_id}/review")
def review_briefing(briefing_id: str, body: ReviewBriefingBody, session: Session = Depends(get_session)):
    briefing = session.get(Briefing, briefing_id)
    if briefing is None or briefing.status != "drafted":
        raise HTTPException(404, "drafted briefing not found")
    if body.approve and not body.doc_url:
        raise HTTPException(400, "doc_url is required to approve a briefing -- publish it first")
    briefing.status = "approved" if body.approve else "rejected"
    briefing.reviewed_at = _now()
    briefing.reviewed_by = body.reviewed_by
    if body.approve:
        briefing.doc_url = body.doc_url
    session.add(briefing)
    session.commit()
    session.refresh(briefing)
    return _serialize(briefing)
