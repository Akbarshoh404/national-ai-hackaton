"""Today's decisions queue (Bugun): actions prepared from the existing engines, each with Approve / Ignore.

`build_decisions` is idempotent: a pending card with the same type + key is refreshed, never duplicated, and
pending cards whose condition no longer holds are expired. Every amount is computed in Python.
"""

from __future__ import annotations

import asyncio
import logging
import math
from calendar import monthrange
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import db as dbm
from app.catalog import TXN_CATEGORY_LABELS, label
from app.config import RESALE_HANDLING_PCT, settings
from app.db import utcnow
from app.errors import AppError, conflict, not_found
from app.i18n import LANGS, fmt_uzs, register, t
from app.models import Company, Decision, InventoryItem, Quote, Rfq, Transaction
from app.permissions import PARTNER_COMPANY_ROLES
from app.services import activity, alerts, books, market, stock, workers

log = logging.getLogger("bozorpilot.decisions")

register({
    "dec.reprice.t": {"uz": "{n} ta mahsulot narxi bozordan yuqori", "ru": "{n} товаров дороже рынка",
                      "en": "{n} units are priced above market"},
    "dec.reprice.m": {"uz": "Tavsiya narxlarga tushirsangiz tezroq sotiladi. Farq: {amount}.",
                      "ru": "Снизьте до рекомендуемых цен, чтобы продать быстрее. Разница: {amount}.",
                      "en": "Reprice to the suggested prices to sell faster. Difference: {amount}."},
    "dec.dup.t": {"uz": "Takroriy hisob: {category} {total}", "ru": "Дубликат счёта: {category} {total}",
                  "en": "Duplicate invoice: {category} {total}"},
    "dec.dup.m": {"uz": "Bir xil yozuv {n} marta kiritilgan. Tasdiqlasangiz ortiqchasi o'chiriladi.",
                  "ru": "Одна запись внесена {n} раза. При подтверждении лишняя будет удалена.",
                  "en": "The same entry was recorded {n} times. Approve to delete the extra one."},
    "dec.typo.t": {"uz": "Summada ortiqcha nol: {category}", "ru": "Лишний ноль в сумме: {category}",
                   "en": "Extra zero in amount: {category}"},
    "dec.typo.m": {"uz": "{total} o'rniga {fixed} bo'lishi kerak. Tasdiqlasangiz tuzatiladi.",
                   "ru": "Вместо {total} должно быть {fixed}. Подтвердите, чтобы исправить.",
                   "en": "{total} should be {fixed}. Approve to correct it."},
    "dec.over.t": {"uz": "Ortiqcha to'lov: {model}", "ru": "Переплата: {model}", "en": "Overpayment: {model}"},
    "dec.over.m": {"uz": "Bozor xarid narxidan {pct}% qimmat olingan. Yetkazib beruvchi bilan gaplashing.",
                   "ru": "Куплено на {pct}% дороже рынка. Обсудите с поставщиком.",
                   "en": "Bought {pct}% above the market purchase price. Raise it with the supplier."},
    "dec.budget.t": {"uz": "Byudjet: {category}", "ru": "Бюджет: {category}", "en": "Budget: {category}"},
    "dec.budget.m": {"uz": "Oy oxiriga {forecast} kutilmoqda (reja {planned}). Haftasiga {weekly} dan oshirmang.",
                     "ru": "Прогноз {forecast} при плане {planned}. Тратьте не более {weekly} в неделю.",
                     "en": "Forecast {forecast} vs plan {planned}. Keep spending under {weekly} per week."},
    "dec.deal.t": {"uz": "Arzon taklif: {title}", "ru": "Выгодно купить: {title}", "en": "Deal to buy: {title}"},
    "dec.deal.m": {"uz": "Bozordan {pct}% arzon. Kutilgan foyda {margin}.", "ru": "На {pct}% ниже рынка. "
                   "Ожидаемая маржа {margin}.", "en": "{pct}% below market. Expected resale margin {margin}."},
    "dec.slow.t": {"uz": "{n} ta mahsulot {days}+ kundan beri sotilmayapti",
                   "ru": "{n} товаров не продаются {days}+ дней", "en": "{n} units unsold for {days}+ days"},
    "dec.slow.m": {"uz": "{cash} pul muzlab turibdi. Birjaga 'surplus' sifatida chiqaring.",
                   "ru": "Заморожено {cash}. Выставьте излишки на бирже.",
                   "en": "{cash} is tied up. List them as surplus on the exchange."},
    "dec.rfq.t": {"uz": "So'rov: {item} × {qty}", "ru": "Запрос: {item} × {qty}", "en": "RFQ: {item} × {qty}"},
    "dec.rfq.m": {"uz": "{company} taklif kutmoqda. Bozor narxi bo'yicha hajm: {value}.",
                  "ru": "{company} ждёт предложения. Объём по рынку: {value}.",
                  "en": "{company} is waiting for quotes. Market value: {value}."},
    "dec.r.amount": {"uz": "Summa Python'da hisoblangan: {amount}", "ru": "Сумма рассчитана: {amount}",
                     "en": "Amount computed: {amount}"},
})

TYPES = ["reprice", "duplicate_invoice", "typo_amount", "overpayment", "budget_limit", "deal_to_buy", "slow_stock",
         "rfq_quote"]
MAX_CARDS = 8
_built_on: dict[int, date] = {}


def _i18n(title_key: str, msg_key: str, reasons: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    """Texts in all languages; kwargs ending in `_uzs` are formatted as money per language."""
    out = {}
    for lang in LANGS:
        k = {key.removesuffix("_uzs"): (fmt_uzs(v, lang) if key.endswith("_uzs") else
                                        (v.get(lang, v.get("en")) if isinstance(v, dict) else v))
             for key, v in kw.items()}
        out[lang] = {"title": t(title_key, lang, **k), "message": t(msg_key, lang, **k),
                     "reasons": reasons or []}
    return out


def _cat_labels(cat: str) -> dict[str, str]:
    return {lang: label(TXN_CATEGORY_LABELS, cat, lang) for lang in LANGS}


def _candidates(db: Session, company: Company) -> list[dict[str, Any]]:
    """All candidate cards from the engines (not yet persisted)."""
    lang = "en"
    out: list[dict[str, Any]] = []
    rows = stock.units(db, company, lang)
    slow_days = settings.SLOW_STOCK_DAYS

    over = [r for r in rows if r["rating"] == "overpriced" and r["days_in_stock"] <= slow_days]
    if over:
        amount = sum((r["list_price_uzs"] - r["suggested_price_uzs"]) * r["qty"] for r in over)
        ids = [r["inventory_id"] for r in over]
        out.append({"type": "reprice", "key": "reprice", "amount_uzs": amount,
                    "i18n": _i18n("dec.reprice.t", "dec.reprice.m", [r["reasons"][0] for r in over[:3]],
                                  n=sum(r["qty"] for r in over), amount_uzs=amount),
                    "inventory_ids": ids, "transaction_ids": [],
                    "action": {"kind": "reprice", "endpoint": "/api/v1/stock/reprice", "method": "POST",
                               "body": {"inventory_ids": ids, "use_suggested": True}}})

    slow = [r for r in rows if r["days_in_stock"] > slow_days]
    if slow:
        cash = sum(r["unit_cost_uzs"] * r["qty"] for r in slow)
        ids = [r["inventory_id"] for r in slow]
        out.append({"type": "slow_stock", "key": "slow_stock", "amount_uzs": cash,
                    "i18n": _i18n("dec.slow.t", "dec.slow.m", [r["reasons"][-1] for r in slow[:3]],
                                  n=sum(r["qty"] for r in slow), days=slow_days, cash_uzs=cash),
                    "inventory_ids": ids, "transaction_ids": [],
                    "action": {"kind": "list_on_exchange", "endpoint": "/api/v1/stock/list-on-exchange",
                               "method": "POST", "body": {"inventory_ids": ids}}})

    flags = books.audit_flags(db, company.id, lang)
    txs = {tx.id: tx for tx in db.scalars(select(Transaction).where(
        Transaction.id.in_([i for f in flags for i in f["transaction_ids"]])))}
    best: dict[str, dict[str, Any]] = {}
    for f in flags:
        if f["type"] in ("duplicate", "extra_zero", "overpayment") and (
                f["type"] not in best or f["amount_at_risk_uzs"] > best[f["type"]]["amount_at_risk_uzs"]):
            best[f["type"]] = f
    if "duplicate" in best:
        f = best["duplicate"]
        first = txs[f["transaction_ids"][0]]
        deletable = [i for i in f["transaction_ids"][1:] if txs[i].origin != "exchange" and not txs[i].deal_id]
        if deletable:
            out.append({"type": "duplicate_invoice", "key": "dup:" + ",".join(map(str, f["transaction_ids"])),
                        "amount_uzs": f["amount_at_risk_uzs"],
                        "i18n": _i18n("dec.dup.t", "dec.dup.m", [f["message"]], category=_cat_labels(first.category),
                                      total_uzs=first.total, n=len(f["transaction_ids"])),
                        "inventory_ids": [], "transaction_ids": f["transaction_ids"],
                        "action": {"kind": "delete_transactions", "endpoint": None, "method": None,
                                   "body": {"delete_ids": deletable}}})
    if "extra_zero" in best:
        f = best["extra_zero"]
        tx = txs[f["transaction_ids"][0]]
        fixed = round(tx.total / 10)
        out.append({"type": "typo_amount", "key": f"typo:{tx.id}", "amount_uzs": f["amount_at_risk_uzs"],
                    "i18n": _i18n("dec.typo.t", "dec.typo.m", [f["message"]], category=_cat_labels(tx.category),
                                  total_uzs=tx.total, fixed_uzs=fixed),
                    "inventory_ids": [], "transaction_ids": [tx.id],
                    "action": {"kind": "correct_total", "endpoint": None, "method": None,
                               "body": {"transaction_id": tx.id, "new_total": fixed}}})
    if "overpayment" in best:
        f = best["overpayment"]
        tx = txs[f["transaction_ids"][0]]
        pct = round((tx.unit_price / f["fair_buy_price_uzs"] - 1) * 100) if f.get("fair_buy_price_uzs") else 0
        out.append({"type": "overpayment", "key": f"overpay:{tx.id}", "amount_uzs": f["amount_at_risk_uzs"],
                    "i18n": _i18n("dec.over.t", "dec.over.m", [f["message"]], model=tx.model or "", pct=pct),
                    "inventory_ids": [], "transaction_ids": [tx.id],
                    "action": {"kind": "supplier_alert", "endpoint": None, "method": None,
                               "body": {"transaction_id": tx.id, "counterparty": tx.counterparty}}})

    today = date.today()
    month = today.strftime("%Y-%m")
    budget = books.budget_status(db, company, month, lang, create_alerts=False)
    problems = [i for i in budget["items"] if i["status"] in ("over", "at_risk") and i["planned_uzs"]]
    if problems:
        b = max(problems, key=lambda i: max(i["forecast_uzs"], i["fact_uzs"]) - i["planned_uzs"])
        excess = max(b["forecast_uzs"], b["fact_uzs"]) - b["planned_uzs"]
        days_left = monthrange(today.year, today.month)[1] - today.day + 1
        weekly = max(b["planned_uzs"] - b["fact_uzs"], 0) / max(1, math.ceil(days_left / 7))
        out.append({"type": "budget_limit", "key": f"budget:{month}:{b['category']}", "amount_uzs": excess,
                    "i18n": _i18n("dec.budget.t", "dec.budget.m", [b["explanation"] or ""],
                                  category=_cat_labels(b["category"]), forecast_uzs=b["forecast_uzs"],
                                  planned_uzs=b["planned_uzs"], weekly_uzs=weekly),
                    "inventory_ids": [], "transaction_ids": [x["id"] for x in b["top_transactions"]],
                    "action": {"kind": "acknowledge", "endpoint": None, "method": None,
                               "body": {"budget_category": b["category"], "weekly_limit_uzs": round(weekly)}}})

    radar = market.sourcing_radar(db, company.categories or [], settings.DEAL_THRESHOLD * 100, 7, 1)
    if radar:
        lst = radar[0]
        margin = (lst.fair_price_uzs or 0) * (1 - RESALE_HANDLING_PCT) - lst.price_uzs
        title = market.listing_title(lst)
        out.append({"type": "deal_to_buy", "key": f"deal:{lst.id}", "amount_uzs": max(margin, 0),
                    "i18n": _i18n("dec.deal.t", "dec.deal.m", [lst.source_url or ""], title=title,
                                  pct=round(lst.discount_pct or 0), margin_uzs=max(margin, 0)),
                    "inventory_ids": [], "transaction_ids": [], "listing_id": lst.id,
                    "action": {"kind": "watch", "endpoint": None, "method": None,
                               "body": {"listing_id": lst.id, "source_url": lst.source_url}}})

    quoted = select(Quote.rfq_id).where(Quote.supplier_id == company.id)
    rfq = db.scalar(select(Rfq).where(Rfq.status == "open", Rfq.company_id != company.id,
                                      Rfq.category.in_(company.categories or []), Rfq.id.not_in(quoted))
                    .order_by(Rfq.id.desc()).limit(1))
    if rfq is not None:
        from app.services.exchange import item_title, market_estimate

        est = market_estimate(db, rfq)
        value = (rfq.target_unit_price or (est.fair_buy_price_uzs if est else 0)) * rfq.qty
        buyer = db.get(Company, rfq.company_id)
        out.append({"type": "rfq_quote", "key": f"rfq:{rfq.id}", "amount_uzs": value,
                    "i18n": _i18n("dec.rfq.t", "dec.rfq.m", [], item=item_title(rfq), qty=rfq.qty,
                                  company=buyer.name, value_uzs=value),
                    "inventory_ids": [], "transaction_ids": [], "rfq_id": rfq.id,
                    "action": {"kind": "open_quote_form", "endpoint": f"/api/v1/exchange/rfqs/{rfq.id}/quotes",
                               "method": "POST", "body": {"unit_price": None, "qty": rfq.qty, "delivery_days": None}}})
    return out


def build_decisions(db: Session, company: Company) -> list[Decision]:
    """Create/refresh pending cards (idempotent) and expire stale ones. Returns pending cards."""
    cands = sorted(_candidates(db, company), key=lambda c: c["amount_uzs"], reverse=True)[:MAX_CARDS]
    pending = {(d.type, d.key): d for d in db.scalars(select(Decision).where(
        Decision.company_id == company.id, Decision.status == "pending"))}
    resolved_today = {(d.type, d.key) for d in db.scalars(select(Decision).where(
        Decision.company_id == company.id, Decision.status.in_(["approved", "ignored"]),
        Decision.resolved_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0)))}
    keep = set()
    for c in cands:
        k = (c["type"], c["key"])
        if k in resolved_today:
            continue
        keep.add(k)
        payload = {"i18n": c["i18n"], "reasons": c["i18n"]["en"]["reasons"], "inventory_ids": c["inventory_ids"],
                   "transaction_ids": c["transaction_ids"], "action": c["action"],
                   **{x: c[x] for x in ("listing_id", "rfq_id") if x in c}}
        d = pending.get(k)
        if d is None:
            d = Decision(company_id=company.id, type=c["type"], key=c["key"])
            db.add(d)
        d.title, d.message = c["i18n"]["uz"]["title"], c["i18n"]["uz"]["message"]
        d.amount_uzs, d.payload = round(c["amount_uzs"]), payload
    for k, d in pending.items():
        if k not in keep:
            d.status, d.resolved_at = "expired", utcnow()
    db.commit()
    _built_on[company.id] = date.today()
    return list(db.scalars(select(Decision).where(Decision.company_id == company.id, Decision.status == "pending")
                           .order_by(Decision.amount_uzs.desc())))


def ensure_built(db: Session, company: Company) -> None:
    """Build on the first call of the day."""
    if _built_on.get(company.id) != date.today():
        build_decisions(db, company)


def pending(db: Session, company: Company) -> list[Decision]:
    return list(db.scalars(select(Decision).where(Decision.company_id == company.id, Decision.status == "pending")
                           .order_by(Decision.amount_uzs.desc())))


def _claim(db: Session, company: Company, decision_id: int, status: str) -> Decision:
    d = db.get(Decision, decision_id)
    if d is None or d.company_id != company.id:
        raise not_found("decision", decision_id)
    res = db.execute(update(Decision).where(Decision.id == d.id, Decision.status == "pending")
                     .values(status=status, resolved_at=utcnow(), resolved_by=getattr(company, "actor_user_id", None)))
    if res.rowcount != 1:
        db.rollback()
        raise conflict("decision_resolved", "This decision was already resolved", {"status": d.status})
    db.refresh(d)
    return d


def approve(db: Session, company: Company, decision_id: int, lang: str) -> dict[str, Any]:
    """Execute the card's action exactly once, in one DB transaction."""
    d = _claim(db, company, decision_id, "approved")
    body = d.payload["action"]["body"]
    result: dict[str, Any] = {}
    try:
        if d.type == "reprice":
            rows = stock.units(db, company, lang, ids=body["inventory_ids"])
            prices = {r["inventory_id"]: r["suggested_price_uzs"] for r in rows
                      if r["rating"] == "overpriced" and r["suggested_price_uzs"]}
            result["updated_ids"] = stock.reprice(db, company, prices) if prices else []
        elif d.type == "slow_stock":
            in_stock = [i for i in body["inventory_ids"] if db.scalar(select(InventoryItem.id).where(
                InventoryItem.id == i, InventoryItem.status == "in_stock"))]
            offers = stock.list_on_exchange(db, company, in_stock, None, lang) if in_stock else []
            result["offer_ids"] = [o.id for o in offers]
        elif d.type == "duplicate_invoice":
            deleted = []
            for tid in body["delete_ids"]:
                tx = db.get(Transaction, tid)
                if tx and tx.company_id == company.id and tx.origin != "exchange" and not tx.deal_id:
                    db.delete(tx)
                    deleted.append(tid)
            result["deleted_transaction_ids"] = deleted
        elif d.type == "typo_amount":
            tx = db.get(Transaction, body["transaction_id"])
            if tx is None or tx.company_id != company.id:
                raise AppError("transaction_not_found", "Transaction no longer exists", 409)
            old = tx.total
            tx.total = body["new_total"]
            tx.unit_price = body["new_total"] / (tx.qty or 1)
            tx.note = ((tx.note or "") + f" [corrected from {round(old)}]").strip()
            result["transaction_id"], result["old_total_uzs"], result["new_total_uzs"] = tx.id, old, tx.total
        elif d.type == "overpayment":
            tx = db.get(Transaction, body["transaction_id"])
            if tx is not None:
                tx.note = ((tx.note or "") + " [overpayment raised with supplier]").strip()
            a = alerts.create(db, company_id=company.id, type="audit", severity="medium", category=None,
                              i18n={lg: {"title": d.payload["i18n"][lg]["title"],
                                         "message": d.payload["i18n"][lg]["message"]} for lg in LANGS},
                              payload={"decision_id": d.id, "transaction_id": body["transaction_id"],
                                       "counterparty": body.get("counterparty")}, commit=False)
            result["alert_id"] = a.id
        elif d.type == "deal_to_buy":
            d.payload = {**d.payload, "watch": True}
            result["watching_listing_id"] = body["listing_id"]
        else:  # budget_limit, rfq_quote: acknowledge
            result["acknowledged"] = True
        books._audit_cache.pop(company.id, None)
        activity.log(db, company, f"decision.approve.{d.type}", "decision", d.id, f"Approved: {d.title}",
                     commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"decision_id": d.id, "type": d.type, "status": "approved", "result": result}


def ignore(db: Session, company: Company, decision_id: int) -> Decision:
    d = _claim(db, company, decision_id, "ignored")
    activity.log(db, company, f"decision.ignore.{d.type}", "decision", d.id, f"Ignored: {d.title}", commit=False)
    db.commit()
    return d


async def run_loop(interval: float = 600) -> None:
    """Refresh every business company's queue every 10 minutes."""
    workers.set_status("decisions", "ok", "refreshing every 10 min")

    def tick() -> int:
        n = 0
        with dbm.SessionLocal() as db:
            for c in list(db.scalars(select(Company))):
                if c.role in PARTNER_COMPANY_ROLES:
                    continue
                try:
                    build_decisions(db, c)
                    n += 1
                except Exception:
                    db.rollback()
                    log.exception("decisions build failed for company %s", c.id)
        return n

    while True:
        await asyncio.to_thread(tick)
        await asyncio.sleep(interval)
