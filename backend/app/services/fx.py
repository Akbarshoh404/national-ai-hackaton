"""USD/UZS exchange rate: env value as fallback, refreshed from the Central Bank (cbu.uz)."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.config import settings
from app.db import utcnow

log = logging.getLogger("bozorpilot.fx")

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"

_state: dict[str, object] = {"rate": float(settings.USD_UZS), "updated_at": None, "source": "env"}


def rate() -> float:
    """Current USD→UZS rate."""
    return float(_state["rate"])  # type: ignore[arg-type]


def updated_at() -> datetime | None:
    return _state["updated_at"]  # type: ignore[return-value]


def source() -> str:
    return str(_state["source"])


def to_uzs(amount: float, currency: str) -> float:
    return amount * rate() if currency == "USD" else amount


def to_usd(amount_uzs: float) -> float:
    return amount_uzs / rate()


def set_rate(value: float, src: str = "manual") -> None:
    _state.update(rate=float(value), updated_at=utcnow(), source=src)


def refresh(timeout: float = 10.0) -> float:
    """Pull today's official rate from cbu.uz; keep the old value on failure."""
    try:
        resp = httpx.get(CBU_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        value = float(str(data[0]["Rate"]).replace(",", "."))
        if value > 1000:
            set_rate(value, "cbu.uz")
            log.info("fx refreshed: %.2f", value)
    except Exception as exc:  # network or format error -> keep fallback
        log.warning("fx refresh failed: %s", type(exc).__name__)
    return rate()
