"""Free-hosting readiness: /ping, Neon pool settings, PORT, lazy heavy imports, workers off without secrets."""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import db as dbm
from app.core import workers
from app.core.config import Settings, settings
from app.data_pipeline import telegram_ingest

NEON = "postgresql://u:p@ep-quiet-1234.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


def test_ping_needs_no_auth_and_no_database(client, monkeypatch):
    def boom():
        raise AssertionError("ping must not open a database session")

    monkeypatch.setattr(dbm, "SessionLocal", boom)
    r = client.get("/api/v1/ping")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_neon_engine_options():
    eng = dbm.make_engine(NEON)
    assert eng.dialect.driver == "psycopg"
    assert eng.pool.size() == 3 and eng.pool._max_overflow == 2 and eng.pool._recycle == 300
    assert eng.pool._pre_ping and eng.url.query["sslmode"] == "require"
    opts = dbm.postgres_engine_options(NEON.replace("ep-quiet-1234.", "ep-quiet-1234-pooler."))
    assert opts["connect_args"]["prepare_threshold"] is None
    assert "prepare_threshold" not in dbm.postgres_engine_options(NEON)["connect_args"]
    assert dbm.make_engine("postgres://u:p@h/db").dialect.driver == "psycopg"


def test_port_env(monkeypatch):
    monkeypatch.setenv("PORT", "9123")
    assert Settings().PORT == 9123


def test_heavy_libraries_are_lazy():
    code = ("import sys, app.main; "
            "print(','.join(m for m in ('pandas', 'openpyxl', 'weasyprint') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=Path(__file__).resolve().parents[1], check=True)
    assert out.stdout.strip() == "", f"loaded at import time: {out.stdout}"


def test_workers_stay_off_without_secrets(monkeypatch, caplog):
    from app import main

    monkeypatch.setattr(workers, "STATUS", dict(workers.STATUS))  # restored after the test
    for k, v in {"WORKERS_TELEGRAM": True, "WORKERS_EXTRACTOR": False, "WORKERS_DECISIONS": False,
                 "BOT_ENABLED": True, "TG_API_ID": 12345, "TG_API_HASH": "hash", "TG_SESSION": "",
                 "TG_BOT_TOKEN": "", "GEMINI_API_KEY": ""}.items():
        monkeypatch.setattr(settings, k, v)

    async def start():
        return main._start_workers()

    with caplog.at_level("WARNING", logger="bozorpilot"):
        tasks = asyncio.run(start())
    assert tasks == []
    assert workers.STATUS["telegram"][0] == "not_configured" and "TG_SESSION" in workers.STATUS["telegram"][1]
    assert workers.STATUS["bot"][0] == "not_configured"
    text = caplog.text
    assert "TG_SESSION" in text and "TG_BOT_TOKEN" in text and "GEMINI_API_KEY" in text


def test_server_client_requires_string_session(monkeypatch):
    monkeypatch.setattr(settings, "TG_SESSION", "")
    with pytest.raises(RuntimeError, match="TG_SESSION"):
        telegram_ingest.make_client()


def test_memory_reading():
    from app.core.memory import rss_mb

    mb = rss_mb()
    if sys.platform.startswith("linux") or sys.platform == "win32":
        assert mb is not None and 10 < mb < 4096
