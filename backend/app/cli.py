"""Command line: `python -m app.cli <command>`.

Commands: init-db, seed [--reset], tg-login, tg-resolve, tg-history [--limit N], extract-once [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import settings
from app.logging_setup import setup_logging


def cmd_init_db(_: argparse.Namespace) -> None:
    from app import db
    from app.services.telegram_ingest import sync_sources_from_yaml

    db.migrate()
    print(f"database ready; {sync_sources_from_yaml()} new sources from sources.yaml")


def cmd_seed(args: argparse.Namespace) -> None:
    from app import db, seed

    if not args.reset:
        db.migrate()
    print(json.dumps(seed.run(reset=args.reset)))
    print("demo API keys: " + ", ".join(f"demo-{s}" for s in seed.DEMO_COMPANIES))


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

    from app.services import telegram_ingest as tg

    async def run() -> None:
        client = tg.make_client()
        await client.connect()
        if not await client.is_user_authorized():
            sys.exit("Not logged in. Run `python -m app.cli tg-login` first.")
        entries = tg.load_sources_yaml()
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
                tg.write_sources_yaml(entries)
                print(f"  saved @{e['username']}")
        await client.disconnect()
        print(f"\n{tg.sync_sources_from_yaml()} sources added to the database")

    asyncio.run(run())


def cmd_tg_history(args: argparse.Namespace) -> None:
    _require_tg()
    from app.services import telegram_ingest as tg

    tg.sync_sources_from_yaml()
    print(json.dumps(asyncio.run(tg.run_history(args.limit)), indent=2))


def cmd_extract_once(args: argparse.Namespace) -> None:
    from app import db
    from app.services import extractor

    with db.SessionLocal() as s:
        print(json.dumps(extractor.run_once(s, args.limit)))


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="python -m app.cli", description="BozorPilot AI backend tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="run migrations and load sources.yaml").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("seed", help="load synthetic demo data")
    s.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    s.set_defaults(fn=cmd_seed)
    sub.add_parser("tg-login", help="log in to Telegram and print TG_SESSION").set_defaults(fn=cmd_tg_login)
    sub.add_parser("tg-resolve", help="find @usernames for sources.yaml titles").set_defaults(fn=cmd_tg_resolve)
    h = sub.add_parser("tg-history", help="import channel history")
    h.add_argument("--limit", type=int, default=None)
    h.set_defaults(fn=cmd_tg_history)
    e = sub.add_parser("extract-once", help="process pending raw posts")
    e.add_argument("--limit", type=int, default=None)
    e.set_defaults(fn=cmd_extract_once)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
