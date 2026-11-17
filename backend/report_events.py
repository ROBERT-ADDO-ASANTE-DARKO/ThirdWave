"""
report_events.py — write/read helpers for feature #6 (Flood/Incident
Timeline). See models.ReportEvent's docstring for why this is a new
table rather than new Report columns.

record_event() is called from every status-changing endpoint
(routers/reports.py's verify_report/verify_bulk, routers/incidents.py's
assign_responder/resolve, and submit_report itself) -- going forward,
every report gets a complete, real, timestamped event log.

timeline_for_report() answers for a report that predates this feature
(submitted before any ReportEvent rows existed for it): reconstruct
what it can from the Report row's own submitted_at/verified_at/
resolved_at columns, clearly marked `reconstructed: True` so an officer
never mistakes a best-effort reconstruction for a logged event -- same
"report, don't fabricate" discipline as every other derived signal in
this project. One real gap even reconstruction can't fill: there's no
column anywhere that holds *when* a responder was assigned, so an old
report with assigned_responder set but no real "responder_assigned"
event surfaces as an "untimed note" instead of a fake timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from models import Report, ReportEvent


def record_event(session: Session, report_id: str, event_type: str, detail: str | None = None) -> None:
    session.add(ReportEvent(
        report_id=report_id, event_type=event_type, detail=detail,
        occurred_at=datetime.now(timezone.utc),
    ))
    session.commit()


def timeline_for_report(session: Session, report: Report) -> dict:
    events = session.exec(
        select(ReportEvent).where(ReportEvent.report_id == report.id).order_by(ReportEvent.occurred_at)
    ).all()
    by_type: dict[str, list[ReportEvent]] = {}
    for e in events:
        by_type.setdefault(e.event_type, []).append(e)

    timed: list[dict] = []
    untimed_notes: list[str] = []

    def add(event_type: str, synth_time, synth_detail, reconstruction_note: str):
        real = by_type.get(event_type)
        if real:
            for e in real:
                timed.append({
                    "event_type": event_type, "occurred_at": e.occurred_at.isoformat(),
                    "detail": e.detail, "reconstructed": False,
                })
        elif synth_time is not None:
            timed.append({
                "event_type": event_type, "occurred_at": synth_time.isoformat(),
                "detail": synth_detail, "reconstructed": True, "note": reconstruction_note,
            })

    add("submitted", report.submitted_at, None,
        "Reconstructed from the report's own submitted_at -- predates this timeline feature.")

    if report.status in ("verified", "rejected", "resolved"):
        verified_event_type = "rejected" if report.status == "rejected" else "verified"
        add(verified_event_type, report.verified_at, report.verified_by,
            "Reconstructed from the report's own verified_at/verified_by -- predates this timeline feature.")

    if report.assigned_responder:
        detail = (f"{report.assigned_responder}, ETA {report.eta_minutes} min"
                  if report.eta_minutes is not None else report.assigned_responder)
        if "responder_assigned" in by_type:
            add("responder_assigned", None, None, "")
        else:
            untimed_notes.append(
                f"Responder assigned: {detail} -- exact time not recorded (predates this timeline feature)."
            )

    if report.status == "resolved":
        add("resolved", report.resolved_at, None,
            "Reconstructed from the report's own resolved_at -- predates this timeline feature.")

    timed.sort(key=lambda e: e["occurred_at"])
    return {"report_id": report.id, "events": timed, "untimed_notes": untimed_notes}
