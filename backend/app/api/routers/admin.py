"""Admin endpoints (X-Admin-Key): status, sources, Telegram history, extractor, raw posts, FX."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.schemas.admin import (
    AdminStatus,
    ExtractResult,
    FxOut,
    JobStarted,
    RawPostOut,
    SourceIn,
    SourceOut,
    SourcePatch,
)
from app.api.schemas.common import Page
from app.core import fx, workers
from app.core.config import settings
from app.core.deps import DbDep, require_admin
from app.core.errors import AppError, conflict, not_found
from app.core.models import Listing, RawPost, Source
from app.data_pipeline import extractor, sources, telegram_ingest

log = logging.getLogger("raft.admin")
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
_jobs: set[asyncio.Task] = set()


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


@router.get("/sources", response_model=list[SourceOut])
def admin_list_sources(db: DbDep) -> list[SourceOut]:
    return [SourceOut.model_validate(s) for s in db.scalars(select(Source).order_by(Source.id))]


@router.post("/sources", response_model=SourceOut, status_code=201)
def admin_add_source(body: SourceIn, db: DbDep) -> SourceOut:
    """Add a channel/group at runtime; the listener reloads sources without a restart."""
    src = Source(**{**body.model_dump(), "username": body.username.lstrip("@").strip()})
    db.add(src)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("source_exists", "A source with this username already exists") from exc
    sources.bump_sources()
    return SourceOut.model_validate(src)


@router.patch("/sources/{source_id}", response_model=SourceOut)
def admin_update_source(source_id: int, body: SourcePatch, db: DbDep) -> SourceOut:
    src = db.get(Source, source_id)
    if src is None:
        raise not_found("source", source_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(src, k, v)
    db.commit()
    sources.bump_sources()
    return SourceOut.model_validate(src)


@router.post("/telegram/history", response_model=JobStarted, status_code=202)
async def admin_telegram_history(limit: int | None = Query(None, ge=1, le=20000)) -> JobStarted:
    """Import channel history in the background (FloodWait-aware)."""
    if not (settings.telegram_configured and settings.TG_SESSION):
        raise AppError("telegram_not_configured", "Set TG_API_ID, TG_API_HASH and TG_SESSION", 503)

    async def job() -> None:
        try:
            stats = await telegram_ingest.run_history(limit)
            log.info("history import finished: %s", stats)
        except Exception:
            log.exception("history import failed")

    task = asyncio.create_task(job())
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)
    return JobStarted(started=True, detail=f"history import started (limit={limit or settings.TG_HISTORY_LIMIT})")


@router.post("/extract/run", response_model=ExtractResult)
async def admin_extract_run(limit: int = Query(60, ge=1, le=1000)) -> ExtractResult:
    """Run the extractor once over pending raw posts."""
    from app.core import db as dbm

    def run() -> dict[str, int]:
        with dbm.SessionLocal() as db:
            return extractor.run_once(db, limit)

    return ExtractResult(**await asyncio.to_thread(run))


@router.get("/raw-posts", response_model=Page[RawPostOut])
def admin_raw_posts(db: DbDep, processed: int | None = Query(None, ge=0, le=3), cursor: str | None = None,
                    limit: int = Query(50, ge=1, le=500)) -> Page[RawPostOut]:
    q = select(RawPost)
    if processed is not None:
        q = q.where(RawPost.processed == processed)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(RawPost.id < int(cursor))
    rows = list(db.scalars(q.order_by(RawPost.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[RawPostOut.model_validate(r) for r in rows[:limit]], next_cursor=nxt, total=total)


@router.post("/fx/refresh", response_model=FxOut)
async def admin_fx_refresh() -> FxOut:
    """Pull today's USD/UZS rate from cbu.uz (env value stays as fallback)."""
    await asyncio.to_thread(fx.refresh)
    return FxOut(usd_uzs=fx.rate(), source=fx.source(), updated_at=fx.updated_at())


@router.get("/fx/refresh", response_model=FxOut)
async def admin_fx_refresh_get() -> FxOut:
    """Same as POST /admin/fx/refresh (GET kept for convenience)."""
    return await admin_fx_refresh()
