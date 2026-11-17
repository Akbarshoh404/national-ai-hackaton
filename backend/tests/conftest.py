"""Test setup: temporary SQLite DB, no LLM, no Telegram, seeded demo data."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="bozorpilot-test-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "AUTO_MIGRATE": "false",
    "WORKERS_TELEGRAM": "false",
    "WORKERS_EXTRACTOR": "false",
    "BOT_ENABLED": "false",
    "GEMINI_API_KEY": "",
    "TG_BOT_TOKEN": "",
    "ADMIN_KEY": "test-admin",
    "DEMO_MODE": "true",
    "USD_UZS": "12700",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    db.drop_all()
    db.create_all()
    try:
        from app import seed
    except ImportError:
        seed = None
    if seed is not None:
        seed.run(reset=False)
    yield


@pytest.fixture(scope="session")
def client(_database):
    from app.main import app

    with TestClient(app) as c:
        yield c


def _key(slug: str) -> dict[str, str]:
    return {"X-API-Key": f"demo-{slug}"}


@pytest.fixture(scope="session")
def chilonzor() -> dict[str, str]:
    return _key("chilonzor-phone")


@pytest.fixture(scope="session")
def techopt() -> dict[str, str]:
    return _key("techopt")


@pytest.fixture(scope="session")
def sergeli() -> dict[str, str]:
    return _key("sergeli-avto")


@pytest.fixture(scope="session")
def realty() -> dict[str, str]:
    return _key("yunusobod-realty")


@pytest.fixture(scope="session")
def admin() -> dict[str, str]:
    return {"X-Admin-Key": "test-admin"}
