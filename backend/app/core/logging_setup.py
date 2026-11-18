"""Structured (key=value) logging that never prints secrets."""

from __future__ import annotations

import logging
import re

from app.core.config import settings

_SECRET = re.compile(r"(bp_[A-Za-z0-9_\-]{10,}|AIza[0-9A-Za-z_\-]{20,}|\d{8,10}:[A-Za-z0-9_\-]{30,})")


class RedactFilter(logging.Filter):
    """Mask API keys, Gemini keys and bot tokens in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if _SECRET.search(msg):
            record.msg = _SECRET.sub("***", msg)
            record.args = ()
        return True


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_bozorpilot", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("ts=%(asctime)s level=%(levelname)s logger=%(name)s msg=\"%(message)s\""))
    handler.addFilter(RedactFilter())
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    for noisy in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._bozorpilot = True  # type: ignore[attr-defined]
