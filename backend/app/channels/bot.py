"""Telegram bot (Bot API over httpx long polling) + alert push.

Commands: /start, /link <API_KEY>, /budget, /audit, /deals, /rfqs. A photo of an
invoice is OCR'd into transactions. Unsent alerts are pushed every 5 seconds.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import select, update

from app.core import alerts, workers
from app.core import db as dbm
from app.core.config import settings
from app.core.db import utcnow
from app.core.deps import company_by_key
from app.core.errors import AppError
from app.core.i18n import fmt_uzs
from app.core.models import Alert, Company, Rfq
from app.intelligence.books import books
from app.intelligence.market import market

log = logging.getLogger("bozorpilot.bot")
LANG = "uz"
PUSH_INTERVAL_S = 5
PUSH_MAX_AGE = timedelta(minutes=30)

HELP = ("BozorPilot AI bot 🤖\n\n"
        "/link <API_KEY> — kompaniyani ulash / привязать компанию\n"
        "/budget — byudjet holati / бюджет\n"
        "/audit — AI auditor natijalari / аудит\n"
        "/deals — bozordan arzon takliflar / выгодные предложения\n"
        "/rfqs — sizga kelgan so'rovlar / входящие запросы\n"
        "/price <matn> — narxni baholash / оценить цену\n"
        "↪️ Kanal postini forward qiling yoki 🎙 ovozli xabar yuboring — narxini aytaman.\n\n"
        "📷 Hisob-faktura rasmini yuboring — xarajatlarga qo'shiladi.\n"
        "Отправьте фото счёта — расходы будут добавлены автоматически.")


class BotApi:
    """Minimal Bot API client."""

    def __init__(self, token: str, client: httpx.AsyncClient):
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"
        self.http = client

    async def call(self, method: str, **params: Any) -> Any:
        r = await self.http.post(f"{self.base}/{method}", json=params, timeout=40)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"bot api {method} failed: {data.get('description')}")
        return data["result"]

    async def send(self, chat_id: int, text: str) -> None:
        await self.call("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True)

    async def download(self, file_id: str) -> bytes:
        info = await self.call("getFile", file_id=file_id)
        r = await self.http.get(f"{self.file_base}/{info['file_path']}", timeout=60)
        r.raise_for_status()
        return r.content


# --------------------------------------------------------------------------- #
# Command handlers (sync, run in a thread)                                     #
# --------------------------------------------------------------------------- #

def _company_for_chat(db: Any, chat_id: int) -> Company | None:
    return db.scalar(select(Company).where(Company.telegram_chat_id == chat_id))


def handle_text(chat_id: int, text: str) -> str:
    """Return the reply for a text message."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""
    with dbm.SessionLocal() as db:
        if cmd in ("/start", "/help"):
            return HELP
        if cmd == "/link":
            company = company_by_key(db, arg) if arg else None
            if company is None:
                return "❌ API kalit noto'g'ri. /link <API_KEY>"
            company.telegram_chat_id = chat_id
            db.commit()
            return f"✅ {company.name} ulandi. Ogohlantirishlar shu chatga keladi."
        company = _company_for_chat(db, chat_id)
        if company is None:
            return "Avval kompaniyani ulang: /link <API_KEY>"
        if cmd == "/budget":
            b = books.budget_status(db, company, date.today().strftime("%Y-%m"), LANG, create_alerts=False)
            lines = [f"📊 Byudjet {b['month']}: {b['used_pct'] or 0}% ishlatilgan"]
            lines += [f"• {e}" for e in b["explanations"]] or ["✅ Hammasi reja bo'yicha"]
            return "\n".join(lines)
        if cmd == "/audit":
            flags = books.audit_flags(db, company.id, LANG)
            s = books.audit_summary(flags)
            lines = [f"🔎 AI Auditor: {s['issues']} ta muammo, xavf ostida {fmt_uzs(s['amount_at_risk_uzs'], LANG)}"]
            lines += [f"• {f['message']}" for f in flags[:5]]
            return "\n".join(lines)
        if cmd == "/deals":
            rows = market.sourcing_radar(db, company.categories or [], 15, 7, 5)
            if not rows:
                return "Hozircha bozordan arzon takliflar yo'q."
            return "🔥 Arzon takliflar:\n" + "\n".join(
                f"• {market.listing_title(r)} — {fmt_uzs(r.price_uzs, LANG)} (−{round(r.discount_pct or 0)}%) "
                f"{r.source_url or ''}" for r in rows)
        if cmd == "/price":
            return price_text(db, arg) if arg else "Masalan: /price cobalt 2021 45 ming probeg"
        if cmd == "/rfqs":
            rows = list(db.scalars(select(Rfq).where(Rfq.status == "open", Rfq.company_id != company.id,
                                                     Rfq.category.in_(company.categories or []))
                                   .order_by(Rfq.id.desc()).limit(5)))
            if not rows:
                return "Ochiq so'rovlar yo'q."
            return "📥 So'rovlar:\n" + "\n".join(
                f"• #{r.id} {r.brand or ''} {r.model} × {r.qty}"
                + (f", maqsad {fmt_uzs(r.target_unit_price, LANG)}" if r.target_unit_price else "") for r in rows)
        return HELP


def price_text(db: Any, text: str) -> str:
    """Free text → parsed item → market price (+ badge when the text has a price)."""
    from app.intelligence.market import inputs, pricing

    item = inputs.parse_text(db, text)
    if not item["category"]:
        return "Mahsulotni aniqlay olmadim. Masalan: /price iphone 13 128 ideal"
    est = pricing.try_estimate(db, category=item["category"], model=item["model"], brand=item["brand"],
                               condition=item["condition"], district=item["district"], attrs=item["attrs"],
                               lang=LANG)
    title = " ".join(x for x in (item["brand"], item["model"]) if x) or item["category"]
    if est is None:
        return f"{title}: bozor ma'lumotlari yetarli emas."
    lines = [f"💰 {title}: {fmt_uzs(est.fair_price_uzs, LANG)}",
             f"Oraliq: {fmt_uzs(est.range_uzs[0], LANG)} – {fmt_uzs(est.range_uzs[1], LANG)}",
             f"Xarid narxi: {fmt_uzs(est.fair_buy_price_uzs, LANG)} ({est.comparables} ta e'lon)"]
    if item["price"]:
        from app.core import fx

        price_uzs = fx.to_uzs(item["price"], item["currency"] or "UZS")
        lines.append(pricing.badge(price_uzs, est.fair_price_uzs, LANG)[1])
    if item["missing_fields"]:
        lines.append("Aniqroq narx uchun: " + ", ".join(item["missing_fields"]))
    return "\n".join(lines)


async def handle_forward(chat_id: int, url: str, text: str) -> str:
    """A forwarded channel post: price it from the DB/Telegram, else from its text."""
    from app.intelligence.market import inputs

    with dbm.SessionLocal() as db:
        try:
            lst, _ = await inputs.listing_for_link(db, url)
            priced = inputs.price_listing(db, lst, LANG)
            est = priced["estimate"]
            return (f"🔗 {market.listing_title(lst)}: {fmt_uzs(lst.price_uzs, LANG)}\n"
                    f"Bozor: {fmt_uzs(est.fair_price_uzs, LANG)} — {priced['badge']}")
        except AppError:
            return await asyncio.to_thread(_price_text_session, text) if text else "Postni o'qiy olmadim."


def _price_text_session(text: str) -> str:
    with dbm.SessionLocal() as db:
        return price_text(db, text)


def handle_voice(chat_id: int, audio: bytes, mime: str) -> str:
    """Voice note → transcript → priced item."""
    from app.core import llm

    if not llm.available():
        return "Ovozli xabar uchun GEMINI_API_KEY kerak. Iltimos, matn bilan yozing: /price ..."
    transcript = llm.transcribe(audio, mime)
    if not transcript:
        return "Ovozni tushuna olmadim."
    return f"🎙 {transcript}\n" + _price_text_session(transcript)


def handle_invoice(chat_id: int, image: bytes) -> str:
    with dbm.SessionLocal() as db:
        company = _company_for_chat(db, chat_id)
        if company is None:
            return "Avval kompaniyani ulang: /link <API_KEY>"
        try:
            rows = books.extract_invoice(image, "image/jpeg")
        except AppError as exc:
            return f"❌ {exc.message}"
        if not rows:
            return "Rasmdan hech narsa topilmadi."
        books.create_transactions(db, company, rows, origin="invoice_ocr")
        return "✅ Qo'shildi:\n" + "\n".join(f"• {r['date']} {r['note'] or r['model'] or r['category']}: "
                                             f"{fmt_uzs(r['total'], LANG)}" for r in rows)


def pending_pushes() -> list[tuple[int, int, str]]:
    """(alert_id, chat_id, text) for unsent alerts; old or unroutable alerts are just marked sent."""
    out: list[tuple[int, int, str]] = []
    with dbm.SessionLocal() as db:
        cutoff = utcnow() - PUSH_MAX_AGE
        db.execute(update(Alert).where(Alert.sent_telegram.is_(False), Alert.created_at < cutoff)
                   .values(sent_telegram=True))
        linked = list(db.scalars(select(Company).where(Company.telegram_chat_id.is_not(None))))
        for a in db.scalars(select(Alert).where(Alert.sent_telegram.is_(False)).order_by(Alert.id).limit(50)):
            title, message = alerts.localized(a, LANG)
            text = f"{title}\n{message}"
            if a.company_id is not None:
                out += [(a.id, c.telegram_chat_id, text) for c in linked if c.id == a.company_id]
            else:
                out += [(a.id, c.telegram_chat_id, text) for c in linked if a.category in (c.categories or [])]
            a.sent_telegram = True
        db.commit()
    return out


async def _poll(api: BotApi) -> None:
    offset = 0
    while True:
        try:
            updates = await api.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message"])
        except (httpx.HTTPError, RuntimeError) as exc:
            log.warning("getUpdates failed: %s", type(exc).__name__)
            await asyncio.sleep(5)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            if not chat_id:
                continue
            try:
                fwd = msg.get("forward_from_chat") or {}
                if fwd.get("username") and msg.get("forward_from_message_id"):
                    url = f"https://t.me/{fwd['username']}/{msg['forward_from_message_id']}"
                    reply = await handle_forward(chat_id, url, msg.get("text") or msg.get("caption") or "")
                elif msg.get("voice") or msg.get("audio"):
                    media = msg.get("voice") or msg.get("audio")
                    audio = await api.download(media["file_id"])
                    reply = await asyncio.to_thread(handle_voice, chat_id, audio, media.get("mime_type", "audio/ogg"))
                elif msg.get("photo"):
                    image = await api.download(msg["photo"][-1]["file_id"])
                    reply = await asyncio.to_thread(handle_invoice, chat_id, image)
                elif msg.get("text"):
                    reply = await asyncio.to_thread(handle_text, chat_id, msg["text"])
                else:
                    continue
                await api.send(chat_id, reply)
            except Exception:
                log.exception("bot update failed")


async def _push(api: BotApi) -> None:
    while True:
        try:
            for _, chat_id, text in await asyncio.to_thread(pending_pushes):
                try:
                    await api.send(chat_id, text)
                except Exception as exc:
                    log.warning("push failed: %s", type(exc).__name__)
        except Exception:
            log.exception("alert push failed")
        await asyncio.sleep(PUSH_INTERVAL_S)


async def run_bot() -> None:
    """Long-polling bot and alert pusher (one supervised worker)."""
    async with httpx.AsyncClient() as client:
        api = BotApi(settings.TG_BOT_TOKEN, client)
        me = await api.call("getMe")
        workers.set_status("bot", "ok", f"@{me.get('username')}")
        await asyncio.gather(_poll(api), _push(api))
