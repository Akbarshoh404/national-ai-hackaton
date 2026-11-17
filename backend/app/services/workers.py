"""Background worker supervision and status registry.

Each worker runs as an asyncio task inside the API process. A crashing worker is
logged and restarted with backoff; it never takes the API down.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger("bozorpilot.workers")

#: name -> (status, detail). Status: ok | disabled | error | not_configured | starting
STATUS: dict[str, tuple[str, str | None]] = {
    "telegram": ("disabled", None),
    "extractor": ("disabled", None),
    "bot": ("disabled", None),
}


def set_status(name: str, status: str, detail: str | None = None) -> None:
    STATUS[name] = (status, detail)


async def supervise(name: str, factory: Callable[[], Awaitable[None]], max_backoff: float = 300) -> None:
    """Run `factory()` forever, restarting with exponential backoff on errors."""
    backoff = 5.0
    while True:
        try:
            set_status(name, "starting")
            await factory()
            set_status(name, "disabled", "stopped")
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("worker %s crashed", name)
            set_status(name, "error", f"{type(exc).__name__}: {str(exc)[:200]}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
