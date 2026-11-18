"""In-process pub/sub used by the SSE endpoints.

Publishers may run in worker threads; `publish` hops onto the event loop safely.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("raft.events")


@dataclass
class Event:
    name: str
    data: dict[str, Any]
    company_id: int | None = None  # None = broadcast
    category: str | None = None
    id: int = 0


@dataclass(eq=False)  # identity hash: subscribers live in a set
class _Sub:
    queue: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(maxsize=500))


class EventBus:
    """Fan-out of events to all connected SSE subscribers."""

    def __init__(self) -> None:
        self._subs: set[_Sub] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._seq = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> _Sub:
        sub = _Sub()
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: _Sub) -> None:
        self._subs.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def _deliver(self, ev: Event) -> None:
        for sub in list(self._subs):
            try:
                sub.queue.put_nowait(ev)
            except asyncio.QueueFull:
                log.warning("dropping event for slow subscriber")

    def publish(self, name: str, data: dict[str, Any], company_id: int | None = None,
                category: str | None = None) -> None:
        """Publish from any thread. No-op when no loop is bound (CLI, tests)."""
        self._seq += 1
        ev = Event(name, data, company_id, category, self._seq)
        loop = self._loop
        if loop is None or loop.is_closed() or not self._subs:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._deliver(ev)
        else:
            loop.call_soon_threadsafe(self._deliver, ev)


bus = EventBus()


def sse_format(ev: Event) -> str:
    return f"id: {ev.id}\nevent: {ev.name}\ndata: {json.dumps(ev.data, default=str, ensure_ascii=False)}\n\n"
