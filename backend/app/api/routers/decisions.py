"""Today's decisions queue (Bugun): prepared actions with Approve / Ignore."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.schemas.common import Page
from app.api.schemas.decisions import DecisionOut, DecisionResult
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.models import Decision
from app.intelligence.books import decisions

router = APIRouter(prefix="/decisions", tags=["decisions (#25, #26, #19)"])


def decision_out(d: Decision, lang: str) -> DecisionOut:
    p = d.payload or {}
    tr = (p.get("i18n") or {}).get(lang) or {}
    return DecisionOut(id=d.id, type=d.type, title=tr.get("title", d.title), message=tr.get("message", d.message),
                       amount_uzs=d.amount_uzs, status=d.status, reasons=[r for r in tr.get("reasons", []) if r],
                       transaction_ids=p.get("transaction_ids", []), inventory_ids=p.get("inventory_ids", []),
                       action=p.get("action", {"kind": "acknowledge", "body": {}}), created_at=d.created_at,
                       resolved_at=d.resolved_at)


@router.get("", response_model=Page[DecisionOut])
def decisions_list(db: DbDep, company: CompanyDep, lang: LangDep,
                   status: Literal["pending", "approved", "ignored", "expired"] = "pending",
                   refresh: bool = Query(False, description="Rebuild the queue now"),
                   cursor: str | None = None, limit: int = Query(20, ge=1, le=100)) -> Page[DecisionOut]:
    """Pending cards are built on the first call of the day (and every 10 min by the worker)."""
    if refresh:
        decisions.build_decisions(db, company)
    else:
        decisions.ensure_built(db, company)
    q = select(Decision).where(Decision.company_id == company.id, Decision.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = Decision.amount_uzs.desc() if status == "pending" else Decision.id.desc()
    start = int(cursor) if cursor else 0
    rows = list(db.scalars(q.order_by(order).offset(start).limit(limit)))
    nxt = str(start + limit) if start + limit < total else None
    return Page(items=[decision_out(d, lang) for d in rows], next_cursor=nxt, total=total)


@router.post("/{decision_id}/approve", response_model=DecisionResult)
def decisions_approve(decision_id: int, db: DbDep, company: CompanyDep, lang: LangDep) -> DecisionResult:
    """Execute the card's action exactly once (409 if already resolved)."""
    return DecisionResult(**decisions.approve(db, company, decision_id, lang))


@router.post("/{decision_id}/ignore", response_model=DecisionOut)
def decisions_ignore(decision_id: int, db: DbDep, company: CompanyDep, lang: LangDep) -> DecisionOut:
    return decision_out(decisions.ignore(db, company, decision_id), lang)
