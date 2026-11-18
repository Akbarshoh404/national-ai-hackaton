"""Command line: `python -m app.cli <command>`.

Commands: init-db, seed [--reset], tg-login, tg-resolve, tg-history [--limit N] [--days N], extract-once [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.config import settings
from app.core.logging_setup import setup_logging


def cmd_init_db(_: argparse.Namespace) -> None:
    from app.core import db
    from app.data_pipeline.sources import sync_sources_from_yaml

    db.migrate()
    print(f"database ready; {sync_sources_from_yaml()} new sources from sources.yaml")


def cmd_seed(args: argparse.Namespace) -> None:
    from app import seed
    from app.core import db

    if not args.reset:
        db.migrate()
    print(json.dumps(seed.run(reset=args.reset)))
    from app import seed_v2

    slugs = [*seed.DEMO_COMPANIES, *seed_v2.PARTNERS, *(u[1] for u in seed_v2.DEMO_USERS)]
    print("demo API keys: " + ", ".join(f"demo-{s}" for s in slugs))


def _require_tg() -> None:
    if not settings.telegram_configured:
        sys.exit("Set TG_API_ID and TG_API_HASH first (https://my.telegram.org → API development tools).")


def cmd_tg_login(_: argparse.Namespace) -> None:
    """Interactive login; prints a StringSession for TG_SESSION (servers) and saves a local session file."""
    _require_tg()
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    async def run() -> None:
        client = TelegramClient(settings.TG_SESSION_FILE, settings.TG_API_ID, settings.TG_API_HASH)
        await client.start()  # prompts for phone, login code and 2FA password in the terminal
        me = await client.get_me()
        session = StringSession.save(client.session)
        await client.disconnect()
        print(f"\nLogged in as {me.first_name}. Local session saved to {settings.TG_SESSION_FILE}.session")
        print("For servers (Railway), set this env variable (keep it secret!):\n")
        print(f"TG_SESSION={session}\n")

    asyncio.run(run())


def cmd_tg_resolve(_: argparse.Namespace) -> None:
    """Search Telegram for each unresolved title and confirm the username interactively."""
    _require_tg()
    from telethon.tl.functions.contacts import SearchRequest

    from app.data_pipeline import sources
    from app.data_pipeline import telegram_ingest as tg

    async def run() -> None:
        client = tg.make_client(allow_file=True)
        await client.connect()
        if not await client.is_user_authorized():
            sys.exit("Not logged in. Run `python -m app.cli tg-login` first.")
        entries = sources.load_sources_yaml()
        for e in entries:
            if str(e.get("username", "TODO")).upper() != "TODO":
                continue
            print(f"\n=== {e['title']}  (hint: {e['category_hint']})")
            res = await client(SearchRequest(q=e["title"], limit=10))
            cands = [c for c in res.chats if getattr(c, "username", None)]
            if not cands:
                print("  no public matches")
                continue
            for i, c in enumerate(cands, 1):
                last = await client.get_messages(c, limit=1)
                when = last[0].date.strftime("%Y-%m-%d") if last else "—"
                subs = getattr(c, "participants_count", None) or "?"
                print(f"  [{i}] @{c.username:<32} {c.title[:40]:<40} subs={subs:<8} last={when}")
            choice = input("  pick number (Enter = skip, or type a username): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(cands):
                e["username"] = cands[int(choice) - 1].username
            elif choice:
                e["username"] = choice.lstrip("@")
            if str(e.get("username")).upper() != "TODO":
                sources.write_sources_yaml(entries)
                print(f"  saved @{e['username']}")
        await client.disconnect()
        print(f"\n{sources.sync_sources_from_yaml()} sources added to the database")

    asyncio.run(run())


def cmd_tg_history(args: argparse.Namespace) -> None:
    _require_tg()
    from app.data_pipeline import sources
    from app.data_pipeline import telegram_ingest as tg

    sources.sync_sources_from_yaml()
    window = f"last {args.days} days" if args.days else "new messages only"
    print(f"Importing history ({window}{f', limit {args.limit}/source' if args.limit else ''}) ...")
    stats = asyncio.run(tg.run_history(args.limit, allow_file=True, days=args.days, progress=print))
    print("Summary:", tg.history_summary(stats))


def cmd_extract_once(args: argparse.Namespace) -> None:
    from app.core import db
    from app.data_pipeline import extractor

    with db.SessionLocal() as s:
        print(json.dumps(extractor.run_once(s, args.limit)))


def cmd_reextract(args: argparse.Namespace) -> None:
    """Re-run one provider on already-processed posts and count fields that differ from the stored listing."""
    from app.core import db
    from app.data_pipeline import extractor

    with db.SessionLocal() as s:
        r = extractor.reextract(s, args.provider, args.limit)
    print(f"provider={r['provider']}  compared={r['compared']}  posts_with_changes={r['with_changes']}  "
          f"fields_changed={r['fields_changed']}")
    for field, n in sorted(r["by_field"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {field}")
    for p in r["posts"]:
        if p["changed"]:
            print(f"  raw_post {p['raw_post_id']}: was {p['was']} -> {p['now']}: {', '.join(p['changed'])}")


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="python -m app.cli", description="Raft backend tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="run migrations and load sources.yaml").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("seed", help="load synthetic demo data")
    s.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    s.set_defaults(fn=cmd_seed)
    sub.add_parser("tg-login", help="log in to Telegram and print TG_SESSION").set_defaults(fn=cmd_tg_login)
    sub.add_parser("tg-resolve", help="find @usernames for sources.yaml titles").set_defaults(fn=cmd_tg_resolve)
    h = sub.add_parser("tg-history", help="import channel history")
    h.add_argument("--limit", type=int, default=None, help="max messages per source")
    h.add_argument("--days", type=int, default=None, help="every message from the last N days (UTC)")
    h.set_defaults(fn=cmd_tg_history)
    e = sub.add_parser("extract-once", help="process pending raw posts")
    e.add_argument("--limit", type=int, default=None)
    e.set_defaults(fn=cmd_extract_once)
    r = sub.add_parser("reextract", help="re-run one provider on processed posts and diff against stored listings")
    r.add_argument("--provider", choices=["local", "gemini", "rules"], default="local")
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(fn=cmd_reextract)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
