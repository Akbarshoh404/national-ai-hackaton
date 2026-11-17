"""Admin endpoints (X-Admin-Key): status, sources, Telegram history, extractor, FX."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.deps import DbDep, require_admin
from app.models import Listing, RawPost, Source
from app.schemas.admin import AdminStatus
from app.services import fx, workers

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/status", response_model=AdminStatus)
def admin_status(db: DbDep) -> AdminStatus:
    """Ingestion counters, worker states and FX."""
    by_state = dict(db.execute(select(RawPost.processed, func.count()).group_by(RawPost.processed)).all())
    return AdminStatus(
        raw_posts={"new": by_state.get(0, 0), "done": by_state.get(1, 0), "failed": by_state.get(2, 0),
                   "skipped": by_state.get(3, 0)},
        listings=db.scalar(select(func.count(Listing.id))) or 0,
        sources_active=db.scalar(select(func.count(Source.id)).where(Source.active.is_(True))) or 0,
        workers={k: {"status": s, "detail": d} for k, (s, d) in workers.STATUS.items()},
        fx_usd_uzs=fx.rate(), fx_source=fx.source(),
    )
