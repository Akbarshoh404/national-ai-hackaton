"""Telegram source registry: `sources.yaml` ⇄ the `sources` table.

`sources_version` is bumped on every change so the live listener reloads sources without a restart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import db as dbm
from app.core.config import settings
from app.core.models import Source

#: bumped whenever sources change, so the listener reloads without a restart
sources_version = 0


def sources_path() -> Path:
    p = Path(settings.SOURCES_FILE)
    return p if p.is_absolute() else Path(__file__).resolve().parents[2] / p


def load_sources_yaml() -> list[dict[str, Any]]:
    path = sources_path()
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("sources", []))


def write_sources_yaml(entries: list[dict[str, Any]]) -> None:
    path = sources_path()
    header = ("# Telegram sources. username: TODO = not resolved yet (run `python -m app.cli tg-resolve`).\n"
              "# category_hint: phone | laptop | car | house | rent | mixed_tech | mixed_realty | mixed\n")
    path.write_text(header + yaml.safe_dump({"sources": entries}, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def sync_sources_from_yaml(db: Session | None = None) -> int:
    """Upsert resolved entries of sources.yaml into the `sources` table."""
    own = db is None
    db = db or dbm.SessionLocal()
    n = 0
    try:
        for e in load_sources_yaml():
            username = str(e.get("username") or "").lstrip("@").strip()
            if not username or username.upper() == "TODO":
                continue
            src = db.scalar(select(Source).where(Source.username == username))
            if src is None:
                db.add(Source(title=e.get("title", username), username=username,
                              category_hint=e.get("category_hint", "mixed"),
                              seller_type_default=e.get("seller_type_default", "shop"),
                              active=bool(e.get("active", True))))
                n += 1
        db.commit()
    finally:
        if own:
            db.close()
    if n:
        bump_sources()
    return n


def bump_sources() -> None:
    global sources_version
    sources_version += 1


def active_sources(db: Session) -> dict[str, Source]:
    return {s.username.lower(): s for s in db.scalars(select(Source).where(Source.active.is_(True)))}
