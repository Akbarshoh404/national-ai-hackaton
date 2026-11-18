"""Date-based history import (`tg-history --days`) with a mocked Telethon client — no real Telegram."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from telethon.errors import FloodWaitError

from app.core import db as dbm
from app.core.models import RawPost, Source
from app.data_pipeline import telegram_ingest as tg

NOW = datetime.now(UTC)
FAKE_CHANNELS = ("histchan", "gonechan", "albumchan")


@dataclass
class Msg:
    id: int
    date: datetime
    message: str
    grouped_id: int | None = None
    photo: object = None


def history(channel_days: int = 40) -> list[Msg]:
    """One message per day, newest first; even days carry a price, odd days are chatter."""
    msgs = []
    for day in range(channel_days):
        text = f"iPhone 13 128gb narxi {5 + day % 3} mln so'm, kun {day}" if day % 2 == 0 else "Assalomu alaykum!"
        msgs.append(Msg(id=10_000 - day, date=NOW - timedelta(days=day, hours=1), message=text))
    return msgs


class FakeClient:
    """Mimics TelegramClient.iter_messages (newest-first, limit / min_id / offset_id)."""

    def __init__(self, channels: dict[str, list[Msg] | Exception], flood_after: dict[str, int] | None = None):
        self.channels = channels
        self.flood_after = dict(flood_after or {})
        self.yielded: dict[str, int] = {}
        self.calls: list[dict] = []

    async def iter_messages(self, entity, limit=None, min_id=0, offset_id=0):
        self.calls.append({"entity": entity, "limit": limit, "min_id": min_id, "offset_id": offset_id})
        data = self.channels.get(entity, [])
        if isinstance(data, Exception):
            raise data
        n = 0
        for m in data:
            if offset_id and m.id >= offset_id:
                continue
            if m.id <= min_id or (limit is not None and n >= limit):
                return
            if self.flood_after.get(entity) == self.yielded.get(entity, 0):
                self.flood_after.pop(entity)
                raise FloodWaitError(request=None, capture=1)
            self.yielded[entity] = self.yielded.get(entity, 0) + 1
            n += 1
            yield m


@pytest.fixture()
def fake(monkeypatch):
    with dbm.SessionLocal() as db:
        before = {s.username: s.active for s in db.query(Source).all()}

    def install(channels, flood_after=None, active=("histchan",)):
        with dbm.SessionLocal() as db:
            for s in db.query(Source).all():
                s.active = s.username in active
            for name in active:
                if not db.query(Source).filter_by(username=name).first():
                    db.add(Source(title=name, username=name, category_hint="phone", seller_type_default="shop"))
            db.commit()
        client = FakeClient(channels, flood_after)
        monkeypatch.setattr(tg, "_client", client)

        async def no_sleep(_s):
            return None

        monkeypatch.setattr(tg.asyncio, "sleep", no_sleep)
        return client

    yield install
    with dbm.SessionLocal() as db:  # restore source flags, drop this module's posts (others run the extractor)
        for s in db.query(Source).all():
            s.active = before.get(s.username, False)
        db.commit()
        db.query(RawPost).filter(RawPost.source.in_(FAKE_CHANNELS)).delete(synchronize_session=False)
        db.query(Source).filter(Source.username.in_(FAKE_CHANNELS)).delete(synchronize_session=False)
        db.commit()


def _stored(source):
    with dbm.SessionLocal() as db:
        return db.query(RawPost).filter(RawPost.source == source).all()


def test_last_30_days_only_and_stops_at_cutoff(client, fake):
    c = fake({"histchan": history(40)})
    lines = []
    stats = asyncio.run(tg.run_history(days=30, progress=lines.append))
    s = stats["histchan"]
    assert c.yielded["histchan"] == 31, "iteration stops at the first message older than 30 days"
    assert s["scanned"] == 30 and s["kept"] == 15 and s["new"] == 15 and s["skipped"] == 15
    rows = _stored("histchan")
    assert len(rows) == 15 and all(NOW - r.posted_at.replace(tzinfo=UTC) < timedelta(days=30) for r in rows)
    assert s["oldest"] < NOW - timedelta(days=29) and c.calls[0]["min_id"] == 0
    assert lines and "@histchan" in lines[0] and "scanned    30" in lines[0]


def test_rerun_is_safe_and_only_adds_new(client, fake):
    fake({"histchan": history(40)})
    asyncio.run(tg.run_history(days=30))
    msgs = [Msg(id=10_500, date=NOW - timedelta(minutes=5), message="Galaxy A54 narxi 3.1 mln so'm"), *history(40)]
    fake({"histchan": msgs})
    s = asyncio.run(tg.run_history(days=30))["histchan"]
    assert s["kept"] == 16 and s["new"] == 1
    assert len(_stored("histchan")) == 16


def test_limit_and_days_whichever_first(client, fake):
    c = fake({"histchan": history(40)})
    s = asyncio.run(tg.run_history(limit=5, days=30))["histchan"]
    assert s["scanned"] == 5 and c.yielded["histchan"] == 5
    c = fake({"histchan": history(40)})
    s = asyncio.run(tg.run_history(limit=100, days=10))["histchan"]
    assert s["scanned"] == 10 and c.yielded["histchan"] == 11


def test_floodwait_resumes_without_double_counting(client, fake):
    c = fake({"histchan": history(40)}, flood_after={"histchan": 7})
    s = asyncio.run(tg.run_history(days=30))["histchan"]
    assert s["scanned"] == 30 and len(c.calls) == 2 and c.calls[1]["offset_id"] == 10_000 - 6


def test_failing_source_is_reported_and_others_continue(client, fake):
    fake({"histchan": history(12), "gonechan": ValueError("No user has \"gonechan\" as username")},
         active=("gonechan", "histchan"))
    lines = []
    stats = asyncio.run(tg.run_history(days=30, progress=lines.append))
    assert stats["gonechan"]["error"].startswith("ValueError") and stats["histchan"]["kept"] == 6
    assert any("FAILED" in x for x in lines)
    summary = tg.history_summary(stats)
    assert "failed: @gonechan" in summary and "kept 6" in summary


def test_album_caption_taken_once(client, fake):
    album = [Msg(id=20_003, date=NOW - timedelta(hours=1), message="MacBook Air M1 narxi 620$", grouped_id=77),
             Msg(id=20_002, date=NOW - timedelta(hours=1), message="MacBook Air M1 narxi 620$", grouped_id=77),
             Msg(id=20_001, date=NOW - timedelta(hours=1), message="", grouped_id=77)]
    fake({"albumchan": album}, active=("albumchan",))
    s = asyncio.run(tg.run_history(days=1))["albumchan"]
    assert s["scanned"] == 3 and s["kept"] == 1 and s["skipped"] == 2


def test_without_days_keeps_incremental_behaviour(client, fake):
    c = fake({"histchan": history(40)})
    with dbm.SessionLocal() as db:
        db.query(Source).filter_by(username="histchan").one().last_msg_id = 10_000 - 3
        db.commit()
    s = asyncio.run(tg.run_history(limit=50))["histchan"]
    assert c.calls[0]["min_id"] == 10_000 - 3 and s["scanned"] == 3


def test_api_accepts_days(client, admin, monkeypatch):
    from app.core.config import settings

    calls = {}

    async def fake_run(limit=None, allow_file=False, days=None, progress=None):
        calls.update(limit=limit, days=days)
        return {}

    monkeypatch.setattr(settings, "TG_API_ID", 1)
    monkeypatch.setattr(settings, "TG_API_HASH", "h")
    monkeypatch.setattr(settings, "TG_SESSION", "s")
    monkeypatch.setattr(tg, "run_history", fake_run)
    r = client.post("/api/v1/admin/telegram/history?days=30", headers=admin)
    assert r.status_code == 202 and "days=30" in r.json()["detail"]
    assert client.post("/api/v1/admin/telegram/history?days=0", headers=admin).status_code == 422
