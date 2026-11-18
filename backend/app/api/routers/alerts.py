"""Alerts: list, read state, live SSE stream (polling via `since_id` as fallback)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.schemas.alerts import AlertOut, ReadAllResult
from app.api.schemas.common import OkResponse, Page
from app.core import alerts as svc
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.errors import not_found
from app.core.models import Alert, Company
from app.core.sse import sse_response

router = APIRouter(prefix="/alerts", tags=["alerts"])


def alert_out(db: DbDep, company: Company, a: Alert, lang: str) -> AlertOut:
    title, message = svc.localized(a, lang)
    payload = {k: v for k, v in (a.payload or {}).items() if k != "i18n"}
    return AlertOut(id=a.id, type=a.type, category=a.category, severity=a.severity, title=title, message=message,
                    payload=payload, read=svc.is_read(db, company, a), broadcast=a.company_id is None,
                    created_at=a.created_at)


@router.get("", response_model=Page[AlertOut])
def alerts_list(db: DbDep, company: CompanyDep, lang: LangDep, unread_only: bool = False,
                since_id: int | None = Query(None, description="Polling fallback: alerts with id > since_id"),
                cursor: str | None = None, limit: int = Query(50, ge=1, le=200)) -> Page[AlertOut]:
    q = select(Alert).where(svc.visible_filter(company))
    if unread_only:
        q = q.where(svc.unread_filter(company))
    if since_id is not None:
        q = q.where(Alert.id > since_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(Alert.id < int(cursor))
    rows = list(db.scalars(q.order_by(Alert.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[alert_out(db, company, a, lang) for a in rows[:limit]], next_cursor=nxt, total=total)


@router.get("/stream", response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}})
async def alerts_stream(request: Request, company: CompanyDep) -> StreamingResponse:
    """Live SSE stream of `alert.created` events for this company (15 s heartbeat)."""
    return sse_response(request, company, {"alert.created"})


@router.post("/{alert_id}/read", response_model=OkResponse)
def alerts_mark_read(alert_id: int, db: DbDep, company: CompanyDep) -> OkResponse:
    a = db.get(Alert, alert_id)
    if a is None or db.scalar(select(Alert.id).where(Alert.id == alert_id, svc.visible_filter(company))) is None:
        raise not_found("alert", alert_id)
    svc.mark_read(db, company, a)
    db.commit()
    return OkResponse()


@router.post("/read-all", response_model=ReadAllResult)
def alerts_read_all(db: DbDep, company: CompanyDep) -> ReadAllResult:
    rows = list(db.scalars(select(Alert).where(svc.visible_filter(company), svc.unread_filter(company))))
    for a in rows:
        svc.mark_read(db, company, a)
    db.commit()
    return ReadAllResult(marked=len(rows))
