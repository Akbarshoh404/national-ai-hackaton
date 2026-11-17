"""FastAPI application: routers, CORS, unified errors and background workers.

One process runs the REST API, the Telegram listener, the extractor loop and the
Telegram bot. Each worker is behind an env flag and supervised so a crash never
affects the API.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import errors
from app.config import settings
from app.logging_setup import setup_logging
from app.routers import ROUTERS
from app.services import workers
from app.services.events import bus

log = logging.getLogger("bozorpilot")


def _start_workers() -> list[asyncio.Task]:
    """Start enabled background workers as supervised tasks."""
    tasks: list[asyncio.Task] = []
    if settings.WORKERS_TELEGRAM:
        if settings.telegram_configured:
            from app.services import telegram_ingest

            tasks.append(asyncio.create_task(workers.supervise("telegram", telegram_ingest.run_listener)))
        else:
            workers.set_status("telegram", "not_configured", "TG_API_ID/TG_API_HASH not set")
    if settings.WORKERS_EXTRACTOR:
        from app.services import extractor

        tasks.append(asyncio.create_task(workers.supervise("extractor", extractor.run_loop)))
    if settings.BOT_ENABLED:
        if settings.TG_BOT_TOKEN:
            from app.services import bot

            tasks.append(asyncio.create_task(workers.supervise("bot", bot.run_bot)))
        else:
            workers.set_status("bot", "not_configured", "TG_BOT_TOKEN not set")
    return tasks


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    bus.bind_loop(asyncio.get_running_loop())
    if settings.AUTO_MIGRATE:
        try:
            from app import db

            await asyncio.to_thread(db.migrate)
            from app.services.telegram_ingest import sync_sources_from_yaml

            await asyncio.to_thread(sync_sources_from_yaml)
        except Exception:
            log.exception("startup migration failed")
    tasks = _start_workers()
    log.info("BozorPilot API started (%d workers)", len(tasks))
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title="BozorPilot AI API",
        version="1.0.0",
        description="B2B market intelligence, AI auditor, budget control and financial advisor for "
                    "Uzbek phone, laptop, car and real-estate businesses.",
        lifespan=lifespan,
        generate_unique_id_function=lambda route: route.name,
        responses=errors.ERROR_RESPONSES,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name
    return app


app = create_app()
