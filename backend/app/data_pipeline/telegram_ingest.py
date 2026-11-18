"""Telegram ingestion (read-only Telethon user client).

* Live: a `NewMessage` handler saves offer-like posts from active sources.
* History: imports past posts per source, respecting FloodWait, 3 s between sources.
* Personal data (phones, @usernames, links) is removed before anything is stored
  (ZRU-547). The sender of a group message is never stored.
* The account never sends or posts anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import db as dbm
from app.core import workers
from app.core.config import settings
from app.core.models import RawPost, Source
from app.data_pipeline import sources

log = logging.getLogger("raft.telegram")

PRICE_SIGNAL = re.compile(
    r"(\$|у\.?\s?е|y\.?\s?e|so['ʻ’`]?m|сум|\bmln\b|млн|\bming\b|narx|цена|\d{6,}|\d{1,3}(?:[ .,]\d{3}){2,})",
    re.IGNORECASE)
_PHONE_INTL = re.compile(r"\+?\s?998[\s\-()]*\d{2}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
_PHONE_LOCAL = re.compile(r"(?<!\d)\(?(?:20|33|50|55|71|77|88|90|91|93|94|95|97|98|99)\)?[\s\-]?\d{3}[\s\-]?\d{2}"
                          r"[\s\-]?\d{2}(?!\d)")
_USERNAME = re.compile(r"@[A-Za-z0-9_]{3,}")
_LINK = re.compile(r"(https?://\S+|t\.me/\S+|telegram\.me/\S+|www\.\S+|\b[\w\-]+\.(?:uz|com|ru|org|net|me)\b/?\S*)",
                   re.IGNORECASE)

_client: Any = None


def is_offer(text: str | None) -> bool:
    """Keep posts with ≥ 15 characters and a price signal."""
    return bool(text) and len(text.strip()) >= 15 and bool(PRICE_SIGNAL.search(text))


def strip_pii(text: str) -> str:
    """Remove phone numbers, @usernames and links."""
    text = _PHONE_INTL.sub("[tel]", text)
    text = _PHONE_LOCAL.sub("[tel]", text)
    text = _USERNAME.sub("[user]", text)
    text = _LINK.sub("[link]", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def text_hash(text: str) -> str:
    norm = re.sub(r"\s+", " ", re.sub(r"\[(tel|user|link)\]", "", text.lower())).strip()
    return hashlib.sha1(norm.encode()).hexdigest()


def save_post(db: Session, source: str, msg_id: int, posted_at: datetime, text: str,
              has_photo: bool = False) -> RawPost | None:
    """Store one offer-like post (idempotent on (source, msg_id)). Returns None when skipped."""
    if not is_offer(text):
        return None
    if db.scalar(select(RawPost.id).where(RawPost.source == source, RawPost.msg_id == msg_id)):
        return None
    if posted_at.tzinfo is not None:
        posted_at = posted_at.astimezone(UTC).replace(tzinfo=None)
    clean = strip_pii(text)
    post = RawPost(source=source, msg_id=msg_id, posted_at=posted_at, text=clean, text_hash=text_hash(clean),
                   has_photo=has_photo, processed=0)
    db.add(post)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return post


# --------------------------------------------------------------------------- #
# Telethon client                                                               #
# --------------------------------------------------------------------------- #

def make_client(allow_file: bool = False) -> Any:
    """Telethon client from the `TG_SESSION` StringSession (no file needed — works on read-only/ephemeral disks).

    Only the CLI passes `allow_file=True` to fall back to the local `TG_SESSION_FILE` created by `tg-login`.
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    if settings.TG_SESSION:
        session: Any = StringSession(settings.TG_SESSION)
    elif allow_file:
        session = settings.TG_SESSION_FILE
    else:
        raise RuntimeError("TG_SESSION is not set; run `python -m app.cli tg-login` and set the printed value")
    return TelegramClient(session, settings.TG_API_ID, settings.TG_API_HASH)


async def run_listener() -> None:
    """Live listener: saves new offer posts from active sources within seconds."""
    global _client
    from telethon import events

    client = make_client()
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        workers.set_status("telegram", "error", "not logged in: run `python -m app.cli tg-login`")
        await asyncio.Event().wait()  # stay idle; do not crash-loop
    _client = client
    state: dict[str, Any] = {"version": -1, "sources": {}}
    seen_groups: dict[int, float] = {}

    def refresh() -> None:
        with dbm.SessionLocal() as db:
            state["sources"] = {k: (s.username, s.category_hint) for k, s in sources.active_sources(db).items()}
        state["version"] = sources.sources_version

    @client.on(events.NewMessage())
    async def handler(event: Any) -> None:
        try:
            if state["version"] != sources.sources_version:
                await asyncio.to_thread(refresh)
            chat = await event.get_chat()
            username = (getattr(chat, "username", None) or "").lower()
            if username not in state["sources"]:
                return
            msg = event.message
            if msg.grouped_id:
                if msg.grouped_id in seen_groups or not msg.message:
                    return
                seen_groups[msg.grouped_id] = asyncio.get_running_loop().time()
                if len(seen_groups) > 2000:
                    seen_groups.clear()
            await asyncio.to_thread(_save_sync, state["sources"][username][0], msg.id, msg.date, msg.message or "",
                                    msg.photo is not None)
        except Exception:
            log.exception("telegram handler error")

    await asyncio.to_thread(refresh)
    workers.set_status("telegram", "ok", f"listening to {len(state['sources'])} sources")
    try:
        await client.run_until_disconnected()
    finally:
        _client = None


def _save_sync(source: str, msg_id: int, date: datetime, text: str, has_photo: bool) -> bool:
    """Store one post (filter + PII strip + dedupe). True when a new row was inserted."""
    with dbm.SessionLocal() as db:
        if save_post(db, source, msg_id, date, text, has_photo):
            src = db.scalar(select(Source).where(Source.username == source))
            if src and msg_id > src.last_msg_id:
                src.last_msg_id = msg_id
                db.commit()
            return True
    return False


def _new_stats() -> dict[str, Any]:
    return {"scanned": 0, "kept": 0, "new": 0, "skipped": 0, "oldest": None, "error": None}


async def _import_source(client: Any, src: Source, limit: int | None, cutoff: datetime | None,
                         stats: dict[str, Any]) -> None:
    """Walk one source newest-first; stop at `limit` messages or the first one older than `cutoff`.

    Without a cutoff only messages newer than `last_msg_id` are read (the original incremental mode). With a
    cutoff the whole window is walked and the unique (source, msg_id) key drops posts already stored.
    FloodWait sleeps and resumes from the last message handled, so nothing is read or counted twice.
    """
    from telethon.errors import FloodWaitError

    min_id = 0 if cutoff else (src.last_msg_id or 0)
    offset_id = 0
    seen_groups: set[int] = set()
    while True:
        try:
            remaining = None if limit is None else limit - stats["scanned"]
            if remaining is not None and remaining <= 0:
                return
            async for msg in client.iter_messages(src.username, limit=remaining, min_id=min_id,
                                                  offset_id=offset_id):
                date = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC)
                if cutoff and date < cutoff:
                    return  # newest-first: everything after this is older still
                offset_id = msg.id
                stats["scanned"] += 1
                stats["oldest"] = date
                if msg.grouped_id and (not msg.message or msg.grouped_id in seen_groups):
                    stats["skipped"] += 1  # album: the caption is taken once
                    continue
                if msg.grouped_id:
                    seen_groups.add(msg.grouped_id)
                text = msg.message or ""
                if not is_offer(text):
                    stats["skipped"] += 1
                    continue
                stats["kept"] += 1
                if await asyncio.to_thread(_save_sync, src.username, msg.id, date, text, msg.photo is not None):
                    stats["new"] += 1
            return
        except FloodWaitError as e:
            log.warning("flood wait %ss on %s; resuming after it", e.seconds, src.username)
            await asyncio.sleep(e.seconds + 1)


def format_history_line(username: str, s: dict[str, Any]) -> str:
    oldest = s["oldest"].strftime("%Y-%m-%d %H:%M") if s["oldest"] else "—"
    line = (f"@{username:<28} scanned {s['scanned']:>5}  kept {s['kept']:>4} (new {s['new']:>4})  "
            f"skipped {s['skipped']:>5}  oldest {oldest}")
    return line + (f"  FAILED: {s['error']}" if s["error"] else "")


async def run_history(limit: int | None = None, allow_file: bool = False, days: int | None = None,
                      progress: Callable[[str], None] | None = None) -> dict[str, dict[str, Any]]:
    """Import history for every active source (FloodWait-aware, 3 s pause between sources).

    `days`: every message from the last N days (UTC), newest-first, stopping at the first older one.
    `limit`: at most N messages per source. With both, whichever stops first wins; with neither,
    `TG_HISTORY_LIMIT` applies. A failing source (private, renamed …) is reported and skipped.
    Returns per-source stats: scanned, kept (has a price), new (inserted), skipped, oldest, error.
    """
    if limit is None and days is None:
        limit = settings.TG_HISTORY_LIMIT
    cutoff = datetime.now(UTC) - timedelta(days=days) if days else None
    say = progress or (lambda line: log.info("history %s", line))
    client = _client
    own = client is None
    if own:
        client = make_client(allow_file)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Telegram session is not authorized; run `python -m app.cli tg-login`")
    stats: dict[str, dict[str, Any]] = {}
    try:
        with dbm.SessionLocal() as db:
            active = list(sources.active_sources(db).values())
        for i, src in enumerate(active):
            s = stats[src.username] = _new_stats()
            try:
                await _import_source(client, src, limit, cutoff, s)
            except Exception as exc:  # private / renamed / deleted channel, network …
                s["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
                log.warning("history failed for %s: %s", src.username, s["error"])
            say(format_history_line(src.username, s))
            if i < len(active) - 1:
                await asyncio.sleep(3)
    finally:
        if own:
            await client.disconnect()
    return stats


def history_summary(stats: dict[str, dict[str, Any]]) -> str:
    failed = [u for u, s in stats.items() if s["error"]]
    tot = {k: sum(s[k] for s in stats.values()) for k in ("scanned", "kept", "new", "skipped")}
    oldest = min((s["oldest"] for s in stats.values() if s["oldest"]), default=None)
    text = (f"{len(stats)} sources: scanned {tot['scanned']}, kept {tot['kept']} (new {tot['new']}), "
            f"skipped {tot['skipped']}, oldest {oldest.strftime('%Y-%m-%d') if oldest else '—'}")
    return text + (f"; failed: {', '.join('@' + u for u in failed)}" if failed else "; failed: none")


def connected() -> bool:
    """True when the live listener holds an authorized client."""
    return _client is not None


async def fetch_message(channel: str, msg_id: int) -> tuple[str, datetime, bool] | None:
    """Read one public message (read-only) through the listener's client: (text, date, has_photo)."""
    if _client is None:
        return None
    try:
        msg = await _client.get_messages(channel, ids=msg_id)
    except Exception as exc:  # private channel, bad id, flood wait...
        log.warning("fetch_message failed for %s/%s: %s", channel, msg_id, type(exc).__name__)
        return None
    if msg is None or not getattr(msg, "message", None):
        return None
    return msg.message, msg.date, msg.photo is not None
