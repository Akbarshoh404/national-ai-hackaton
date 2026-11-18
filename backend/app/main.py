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
from fastapi.responses import RedirectResponse
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
    if settings.WORKERS_DECISIONS:
        from app.services import decisions

        tasks.append(asyncio.create_task(workers.supervise("decisions", decisions.run_loop)))
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


API_DESCRIPTION = """
B2B market intelligence and finance co-pilot for Uzbek businesses that trade **phones, laptops, cars, apartments
(sale) and apartment rent**. The LLM reads and explains; Python calculates every number.

### How to try it here
1. Click **Authorize** and paste a demo key into **ApiKey** (`X-API-Key`):

| Key | Who |
|---|---|
| `demo-chilonzor-phone` | Chilonzor Phone Market — retailer, owner (main demo shop) |
| `demo-chilonzor-manager` | the same shop, manager user |
| `demo-chilonzor-appraiser` | the same shop, read-only appraiser |
| `demo-techopt` | TechOpt Wholesale — supplier |
| `demo-sergeli-avto` | Sergeli Avto — car dealer |
| `demo-yunusobod-realty` | Yunusobod Realty — realtor |
| `demo-demo-bank` | Demo Lizing Bank — lender console |
| `demo-bozor-admin` | Malika Bozori Ma'muriyati — market admin |

   Admin endpoints use **AdminKey** (`X-Admin-Key`, the `ADMIN_KEY` env value; `change-me` by default).
   Demo keys exist after `python -m app.cli seed --reset`.
2. Good first calls: `GET /api/v1/dashboard`, `GET /api/v1/stock/summary`, `GET /api/v1/decisions`,
   `POST /api/v1/market/price`, `POST /api/v1/advisor/chat`.
3. Send `Accept-Language: uz | ru | en` to switch the language of generated text.

Errors always look like `{"error": {"code", "message", "details"}}`; lists are `{items, next_cursor, total}`.
Alternative docs: [ReDoc](/redoc) · raw spec: [/openapi.json](/openapi.json).
"""

OPENAPI_TAGS = [
    {"name": "auth & companies", "description": "Register, demo login, company profile and directory"},
    {"name": "meta", "description": "Dropdowns, labels, formats and service health"},
    {"name": "dashboard", "description": "Home screen (Bugun) in one call"},
    {"name": "decisions (#25, #26, #19)", "description": "Today's prepared actions with Approve / Ignore"},
    {"name": "market (#19)", "description": "Telegram market feed, pricing desk, radar, trends, heatmap, yield"},
    {"name": "fast inputs (#19, #26)", "description": "Free text, voice and IMEI into a priceable item"},
    {"name": "stock command center (#19, #26)", "description": "Every unit rated against the market; bulk reprice"},
    {"name": "books (#25, #26)", "description": "Import, AI auditor, budget control, inventory, exports"},
    {"name": "B2B exchange (#19)", "description": "RFQs, ranked quotes, counter-offers, offers, deals, ratings"},
    {"name": "advisor (#20)", "description": "Copilot with answer blocks, credit, tax, loan readiness, plans"},
    {"name": "lender & bazaar console (#20, #19)", "description": "Valuations, collateral LTV, loan applications"},
    {"name": "alerts", "description": "Alerts list, read state and SSE stream"},
    {"name": "platform", "description": "Stores, users and roles, activity log, integrations"},
    {"name": "admin", "description": "Telegram sources, extractor, raw posts, FX (X-Admin-Key)"},
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="BozorPilot AI API",
        version="2.0.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        generate_unique_id_function=lambda route: route.name,
        responses=errors.ERROR_RESPONSES,
        swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True, "filter": True,
                               "tryItOutEnabled": True, "docExpansion": "none", "defaultModelsExpandDepth": 0},
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    errors.install(app)
    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Open Swagger UI at the site root."""
        return RedirectResponse("/docs")

    return app


app = create_app()
