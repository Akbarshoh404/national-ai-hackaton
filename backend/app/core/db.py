"""Database engine, session factory and declarative base.

SQLite is used locally (WAL mode, foreign keys on); setting `DATABASE_URL` to a
PostgreSQL URL switches the backend without code changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def utcnow() -> datetime:
    """Naive UTC timestamp (all datetimes are stored as naive UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    """Create an engine; SQLite gets WAL + FK pragmas and thread-sharing."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _rec) -> None:  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        return eng
    return create_engine(url, **postgres_engine_options(url))


def postgres_engine_options(url: str) -> dict[str, Any]:
    """Pool settings for PostgreSQL, tuned for Neon's free tier.

    Neon suspends compute after ~5 min idle and drops connections, so: ping before use, a small pool,
    and recycle connections every 5 minutes. Neon `-pooler` hosts run PgBouncer in transaction mode,
    where psycopg's automatic prepared statements break, so they are switched off there.
    `?sslmode=require` (and `channel_binding`) in the URL are passed straight to libpq.
    """
    connect_args: dict[str, Any] = {"connect_timeout": 15}
    if "-pooler." in url:
        connect_args["prepare_threshold"] = None
    return {"pool_pre_ping": True, "pool_size": 3, "max_overflow": 2, "pool_recycle": 300,
            "connect_args": connect_args}


engine = make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configure(url: str) -> None:
    """Rebind the global engine/session factory (used by tests and the CLI)."""
    global engine
    engine = make_engine(url)
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Create all tables directly from the models (tests / quick start)."""
    from app.core import models  # noqa: F401  (register models)

    Base.metadata.create_all(engine)


def drop_all() -> None:
    """Drop all tables, including Alembic's version table."""
    from sqlalchemy import text

    from app.core import models  # noqa: F401  (register models)

    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def migrate() -> None:
    """Run Alembic migrations up to head."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]  # backend/
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
