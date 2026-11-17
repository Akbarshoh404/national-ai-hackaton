"""Alert creation and fan-out (SSE now, Telegram bot asynchronously).

`company_id=None` marks a broadcast alert: every company trading in `category`
sees it. Read state for broadcasts is tracked per company in `alert_reads`.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.i18n import LANGS, t
from app.models import Alert, AlertRead, Company
from app.services.events import bus


def texts(title_key: str, message_key: str, **kw: Any) -> dict[str, dict[str, str]]:
    """Render an alert title+message in every language (stored in payload.i18n)."""
    return {lang: {"title": t(title_key, lang, **kw), "message": t(message_key, lang, **kw)} for lang in LANGS}


def localized(a: Alert, lang: str) -> tuple[str, str]:
    """(title, message) of an alert in `lang`, falling back to the stored text."""
    tr = (a.payload or {}).get("i18n", {}).get(lang)
    return (tr["title"], tr["message"]) if tr else (a.title, a.message)


def alert_dict(a: Alert) -> dict[str, Any]:
    return {"id": a.id, "company_id": a.company_id, "category": a.category, "type": a.type,
            "severity": a.severity, "title": a.title, "message": a.message, "payload": a.payload,
            "created_at": a.created_at.isoformat() + "Z"}


def create(db: Session, *, company_id: int | None, type: str, i18n: dict[str, dict[str, str]],
           category: str | None = None, severity: str = "info", payload: dict[str, Any] | None = None,
           commit: bool = True) -> Alert:
    """Persist an alert (texts in uz/ru/en) and push it to SSE subscribers."""
    data = {**(payload or {}), "i18n": i18n}
    a = Alert(company_id=company_id, category=category, type=type, severity=severity, title=i18n["uz"]["title"],
              message=i18n["uz"]["message"], payload=data)
    db.add(a)
    db.flush()
    if commit:
        db.commit()
    bus.publish("alert.created", alert_dict(a), company_id=company_id, category=category)
    return a


def visible_filter(company: Company) -> Any:
    """SQL filter: alerts addressed to the company or broadcast to its categories."""
    return or_(Alert.company_id == company.id,
               Alert.company_id.is_(None) & Alert.category.in_(company.categories or []))


def is_read(db: Session, company: Company, a: Alert) -> bool:
    if a.company_id is not None:
        return a.read
    return db.scalar(select(func.count(AlertRead.id)).where(AlertRead.alert_id == a.id,
                                                            AlertRead.company_id == company.id)) > 0


def unread_filter(company: Company) -> Any:
    broadcast_read = exists().where(AlertRead.alert_id == Alert.id, AlertRead.company_id == company.id)
    return or_(Alert.company_id.is_not(None) & Alert.read.is_(False),
               Alert.company_id.is_(None) & ~broadcast_read)


def mark_read(db: Session, company: Company, a: Alert) -> None:
    if a.company_id is not None:
        a.read = True
    elif not is_read(db, company, a):
        db.add(AlertRead(alert_id=a.id, company_id=company.id))


def exists_today(db: Session, company_id: int, type_: str, key: str) -> bool:
    """True when an alert of `type_` with payload.key == key was created today (UTC)."""
    start = datetime.combine(utcnow().date(), time.min)
    rows = db.scalars(select(Alert).where(Alert.company_id == company_id, Alert.type == type_,
                                          Alert.created_at >= start))
    return any((r.payload or {}).get("key") == key for r in rows)


def notify_category(db: Session, category: str, *, exclude_company_id: int | None, type: str,
                    i18n: dict[str, dict[str, str]], severity: str = "info",
                    payload: dict[str, Any] | None = None) -> int:
    """Create one alert per company trading in `category` (except the sender)."""
    n = 0
    for c in db.scalars(select(Company)):
        if c.id != exclude_company_id and category in (c.categories or []):
            create(db, company_id=c.id, type=type, i18n=i18n, category=category,
                   severity=severity, payload=payload, commit=False)
            n += 1
    return n
