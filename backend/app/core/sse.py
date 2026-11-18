"""Server-Sent Events response with per-company filtering and a 15 s heartbeat."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.core.events import Event, bus, sse_format
from app.core.models import Company

HEARTBEAT_S = 15.0


def visible(ev: Event, company_id: int, categories: set[str]) -> bool:
    """Whether an event is meant for this company."""
    if ev.company_id is not None:
        return ev.company_id == company_id
    return ev.category is None or ev.category in categories


def sse_response(request: Request, company: Company, names: set[str]) -> StreamingResponse:
    company_id, categories = company.id, set(company.categories or [])

    async def gen() -> AsyncIterator[str]:
        sub = bus.subscribe()
        try:
            yield "retry: 5000\n: connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_S)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if ev.name in names and visible(ev, company_id, categories):
                    yield sse_format(ev)
        finally:
            bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
