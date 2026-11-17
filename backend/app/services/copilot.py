"""Copilot (Maslahat + side panel): intent router → Python tool → answer blocks → ≤2-sentence answer.

1. A keyword router (uz/ru/en) plus the screen context picks one tool. The LLM is asked only when the rules
   fail, and it returns an intent *name*, never numbers.
2. The tool runs in Python and builds typed blocks and next-step chips.
3. The LLM may rephrase a template answer into ≤ 2 sentences from the block data. Blocks are built before the
   LLM call and returned unchanged.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import TXN_CATEGORY_LABELS, label, norm_model
from app.config import settings
from app.i18n import detect_lang, fmt_uzs
from app.models import Company, InventoryItem, Transaction
from app.services import books, exchange, finance, llm, market, pricing, stock

INTENTS = ["price", "stock", "audit", "budget", "cashflow", "credit", "tax", "loan_readiness", "expansion",
           "business_plan", "demand", "overview"]

# order matters: the first matching intent wins
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("business_plan", ("biznes-reja", "biznes reja", "бизнес-план", "бизнес план", "business plan")),
    ("loan_readiness", ("tayyorlik", "готовност", "readiness", "kredit reyting", "кредитный рейтинг", "score")),
    ("expansion", ("kengay", "filial", "расшир", "филиал", "expand", "expansion", "new store", "yangi do'kon",
                   "yangi nuqta", "новый магазин")),
    ("credit", ("kredit", "кредит", "loan", "qarz", "займ", "lizing", "лизинг", "ipoteka", "ипотек", "mortgage",
                "leasing")),
    ("tax", ("soliq", "налог", "tax", "qqs", "ндс", "vat")),
    ("budget", ("byudjet", "бюджет", "budget", "limit", "лимит")),
    ("audit", ("audit", "аудит", "xato", "ошиб", "error", "dublikat", "дублик", "duplicate", "typo", "опечат")),
    ("demand", ("talab", "спрос", "demand", "nima sotiladi", "ko'p so'ral", "популяр", "most requested",
                "what sells")),
    ("stock", ("ombor", "склад", "stock", "zaxira", "запас", "inventory", "overpriced", "qimmat", "дорог",
               "sotilmay", "не продаёт", "не продает", "aging", "eskir")),
    ("price", ("narx", "цен", "price", "qancha turadi", "сколько стоит", "baho", "оцен", "worth")),
    ("cashflow", ("pul oqimi", "cash", "foyda", "прибыл", "profit", "daromad", "доход", "income", "оборот",
                  "xarajat", "расход", "expense")),
]
_SCREEN_DEFAULT = {"stock": "stock", "books": "audit", "budget": "budget", "exchange": "demand",
                   "advisor": "overview"}

_L: dict[str, tuple[str, str, str]] = {
    "fair": ("Bozor narxi", "Рыночная цена", "Market price"),
    "your": ("Sizning narx", "Ваша цена", "Your price"),
    "buy": ("Xarid narxi", "Закупочная цена", "Buy price"),
    "range": ("Narx oralig'i", "Ценовой диапазон", "Price range"),
    "comps": ("O'xshash e'lonlar", "Похожие объявления", "Comparable listings"),
    "stock_kpi": ("Ombor", "Склад", "Stock"),
    "units": ("Dona", "Единиц", "Units"),
    "overpriced": ("Qimmat", "Дороже рынка", "Overpriced"),
    "at_market": ("Bozor qiymati", "По рынку", "At market"),
    "at_risk": ("Xavf ostida", "Под риском", "At risk"),
    "model": ("Model", "Модель", "Model"),
    "rating": ("Baho", "Оценка", "Rating"),
    "suggested": ("Tavsiya", "Рекомендация", "Suggested"),
    "issues": ("Muammolar", "Проблемы", "Issues"),
    "audit": ("AI Auditor", "AI-аудитор", "AI Auditor"),
    "type": ("Turi", "Тип", "Type"),
    "message": ("Izoh", "Описание", "Message"),
    "amount": ("Summa", "Сумма", "Amount"),
    "budget": ("Byudjet", "Бюджет", "Budget"),
    "plan": ("Reja", "План", "Plan"),
    "fact": ("Fakt", "Факт", "Actual"),
    "forecast": ("Prognoz", "Прогноз", "Forecast"),
    "used": ("Ishlatilgan %", "Использовано %", "Used %"),
    "cashflow": ("Pul oqimi", "Денежный поток", "Cash flow"),
    "income": ("Tushum", "Доходы", "Income"),
    "expense": ("Xarajat", "Расходы", "Expenses"),
    "net": ("Sof", "Чистыми", "Net"),
    "avg_net": ("O'rtacha sof", "Средний чистый", "Avg net"),
    "loan": ("Kredit", "Кредит", "Loan"),
    "payment": ("Oylik to'lov", "Ежемесячный платёж", "Monthly payment"),
    "interest": ("Foizlar", "Проценты", "Total interest"),
    "max_loan": ("Maks. kredit", "Макс. кредит", "Max loan"),
    "tax": ("Soliq", "Налог", "Tax"),
    "turnover_tax": ("Aylanma soliq", "Налог с оборота", "Turnover tax"),
    "vat_total": ("QQS + foyda", "НДС + прибыль", "VAT + profit tax"),
    "saving": ("Tejash", "Экономия", "Saving"),
    "readiness": ("Kreditga tayyorlik", "Готовность к кредиту", "Loan readiness"),
    "score": ("Ball", "Балл", "Score"),
    "improve": ("Qanday yaxshilash", "Как улучшить", "How to improve"),
    "expansion": ("Kengayish rejasi", "План расширения", "Expansion plan"),
    "units_buy": ("Dona", "Шт.", "Units"),
    "monthly_net": ("Oylik sof foyda", "Чистая прибыль/мес", "Net profit / month"),
    "break_even": ("Qoplash (oy)", "Окупаемость (мес)", "Break-even (months)"),
    "plan_doc": ("Biznes-reja", "Бизнес-план", "Business plan"),
    "demand": ("Talab", "Спрос", "Demand"),
    "requests": ("So'rovlar", "Запросы", "Requests"),
    "listings": ("E'lonlar", "Объявления", "Listings"),
    "kpis": ("Asosiy ko'rsatkichlar", "Ключевые показатели", "Key numbers"),
    "chip_reprice": ("Tavsiya narxga o'tkazish", "Применить рекомендованные цены", "Apply suggested prices"),
    "chip_list": ("Birjaga chiqarish", "Выставить на биржу", "List on exchange"),
    "chip_trend": ("Narx tendensiyasi", "Динамика цен", "Price trend"),
    "chip_overpriced": ("Barcha qimmat mahsulotlar", "Все дорогие товары", "All overpriced units"),
    "chip_export": ("Excelga yuklash", "Выгрузить в Excel", "Export to Excel"),
    "chip_decisions": ("Bugungi qarorlar", "Решения на сегодня", "Today's decisions"),
    "chip_audit": ("To'liq audit", "Полный аудит", "Full audit"),
    "chip_budget": ("Byudjetni ochish", "Открыть бюджет", "Open budget"),
    "chip_cashflow": ("12 oylik oqim", "Поток за 12 мес", "12-month cash flow"),
    "chip_credit_36": ("36 oyga hisoblash", "Рассчитать на 36 мес", "Calculate for 36 months"),
    "chip_readiness": ("Kreditga tayyorlik", "Готовность к кредиту", "Loan readiness"),
    "chip_plan": ("Biznes-reja tuzish", "Создать бизнес-план", "Build a business plan"),
    "chip_tax": ("Soliq taqqoslash", "Сравнение налогов", "Tax comparison"),
    "chip_expansion": ("Kengayish rejasi", "План расширения", "Expansion plan"),
    "chip_rfqs": ("Kelgan so'rovlar", "Входящие запросы", "Incoming RFQs"),
    "chip_stock": ("Ombor holati", "Состояние склада", "Stock overview"),
}


def L(key: str, lang: str) -> str:
    return _L[key][{"uz": 0, "ru": 1, "en": 2}[lang]]


def chip(key: str, lang: str, endpoint: str, method: str = "GET", body: dict | None = None) -> dict[str, Any]:
    return {"label": L(key, lang), "action": {"endpoint": endpoint, "method": method, "body": body}}


# --------------------------------------------------------------------------- #
# Intent routing                                                                #
# --------------------------------------------------------------------------- #

def route_intent(question: str, context: dict[str, Any] | None) -> tuple[str, str]:
    """(intent, how). Keyword rules first, then screen context, then the LLM (intent name only)."""
    q = question.lower()
    ctx = context or {}
    for intent, words in _RULES:
        if any(w in q for w in words):
            if intent == "price" and ctx.get("inventory_ids"):
                return "stock", "rules"
            return intent, "rules"
    if ctx.get("inventory_ids"):
        return "stock", "context"
    if ctx.get("transaction_ids"):
        return "audit", "context"
    if ctx.get("screen") in _SCREEN_DEFAULT and ctx["screen"] != "advisor":
        return _SCREEN_DEFAULT[ctx["screen"]], "context"
    if llm.available():
        out = llm.generate_json(
            f"Classify the business question into one intent from {json.dumps(INTENTS)}. "
            f'Return JSON {{"intent": "<name>"}}. Question: {question}', timeout=settings.LLM_TIMEOUT_S)
        if isinstance(out, dict) and out.get("intent") in INTENTS:
            return out["intent"], "llm"
    return "overview", "default"


_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mlrd|млрд|mln|млн|million|ming|тыс)", re.I)
_MONTHS = re.compile(r"(\d{1,3})\s*(oy|мес|month)", re.I)


def parse_money(text: str) -> float | None:
    m = _AMOUNT.search(text)
    if not m:
        return None
    mult = {"mlrd": 1e9, "млрд": 1e9, "ming": 1e3, "тыс": 1e3}.get(m.group(2).lower(), 1e6)
    return float(m.group(1).replace(",", ".")) * mult


# --------------------------------------------------------------------------- #
# Tools: each returns (blocks, chips, facts-for-the-answer)                     #
# --------------------------------------------------------------------------- #

def _price_blocks(est: pricing.Estimate, title: str, lang: str, your: float | None = None) -> list[dict[str, Any]]:
    return [
        {"type": "price_range", "title": f"{L('range', lang)}: {title}", "fair_uzs": est.fair_price_uzs,
         "p25_uzs": est.range_uzs[0], "p75_uzs": est.range_uzs[1], "your_price_uzs": your,
         "buy_price_uzs": est.fair_buy_price_uzs, "currency": "UZS", "basis": est.basis,
         "comparables": est.comparables, "confidence": est.confidence},
        {"type": "comparables", "title": L("comps", lang),
         "samples": [{"title": s["title"], "price_uzs": s["price_uzs"], "condition": s["condition"],
                      "district": s["district"], "seller_type": s["seller_type"],
                      "posted_at": s["posted_at"].isoformat() + "Z" if hasattr(s["posted_at"], "isoformat")
                      else s["posted_at"], "source_url": s["source_url"]} for s in est.samples[:5]]},
    ]


def tool_price(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    cats = company.categories or ["phone"]
    q = norm_model(question)
    best = None
    for cat in cats:
        for m in market.models(db, cat, None, 50):
            hit = m["model_norm"] and re.search(r"\b" + re.escape(m["model_norm"]) + r"\b", q)
            if hit and (best is None or len(m["model_norm"]) > len(best[1]["model_norm"])):
                best = (cat, m)
    if best is None:
        return tool_overview(db, company, question, ctx, lang)
    cat, m = best
    typ = finance._typical(db, cat, m["model_norm"])
    attrs = dict(typ["attrs"])
    sm = re.search(r"\b(64|128|256|512)\s*(gb|гб)?\b", question, re.I)
    if sm and cat == "phone":
        attrs["storage_gb"] = int(sm.group(1))
    est = pricing.estimate(db, cat, typ["model"], typ["condition"], attrs=attrs, brand=typ["brand"], lang=lang)
    title = " ".join(x for x in (typ["brand"], typ["model"], f"{attrs.get('storage_gb')}GB" if attrs.get(
        "storage_gb") else None, typ["condition"]) if x)
    chips = [chip("chip_trend", lang, f"/api/v1/market/trend?category={cat}&model={typ['model']}"),
             chip("chip_stock", lang, "/api/v1/stock/summary")]
    return _price_blocks(est, title, lang), chips, {"title": title, "fair": est.fair_price_uzs,
                                                     "p25": est.range_uzs[0], "p75": est.range_uzs[1],
                                                     "n": est.comparables}


def tool_stock(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    ids = ctx.get("inventory_ids") or None
    rows = stock.units(db, company, lang, ids=ids)
    if ids:
        sel = rows
    else:
        sel = sorted([r for r in rows if r["rating"] == "overpriced" or r["suggested_action"] == "list_on_exchange"],
                     key=lambda r: -(r["vs_market_pct"] or 0))[:8]
    blocks: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}
    if ids and sel and sel[0]["fair_price_uzs"]:
        r0 = sel[0]
        est = pricing.try_estimate(db, category=r0["category"], model=r0["model"], brand=r0["brand"],
                                   condition=r0["condition"], attrs=r0["attrs"], lang=lang)
        if est:
            blocks += _price_blocks(est, f"{r0['brand'] or ''} {r0['model']}".strip(), lang,
                                    r0["list_price_uzs"])[:1]
        facts.update(title=r0["model"], vs=r0["vs_market_pct"], suggested=r0["suggested_price_uzs"],
                     reason=r0["reasons"][0] if r0["reasons"] else "")
    else:
        s = stock.summary(rows)
        blocks.append({"type": "kpi_row", "title": L("stock_kpi", lang), "items": [
            {"label": L("units", lang), "value": s["units_total"]},
            {"label": L("overpriced", lang), "value": s["units_overpriced"]},
            {"label": L("at_market", lang), "value_uzs": s["stock_value_market_uzs"]},
            {"label": L("at_risk", lang), "value_uzs": s["margin_at_risk_uzs"]}]})
        facts.update(units=s["units_total"], over=s["units_overpriced"], risk=s["margin_at_risk_uzs"])
    blocks.append({"type": "table", "title": L("stock_kpi", lang),
                   "columns": [L("model", lang), L("your", lang), L("fair", lang), L("rating", lang),
                               L("suggested", lang)],
                   "rows": [[f"{r['brand'] or ''} {r['model']}".strip(), r["list_price_uzs"], r["fair_price_uzs"],
                             r["rating"], r["suggested_price_uzs"]] for r in sel],
                   "row_ids": [r["inventory_id"] for r in sel]})
    target = [r["inventory_id"] for r in sel if r["suggested_action"] in ("reprice_down", "reprice_up")]
    chips = []
    if target:
        chips.append(chip("chip_reprice", lang, "/api/v1/stock/reprice", "POST",
                          {"inventory_ids": target, "use_suggested": True}))
    aging = [r["inventory_id"] for r in sel if r["suggested_action"] == "list_on_exchange"]
    if aging:
        chips.append(chip("chip_list", lang, "/api/v1/stock/list-on-exchange", "POST", {"inventory_ids": aging}))
    chips.append(chip("chip_overpriced", lang, "/api/v1/stock/units?rating=overpriced"))
    return blocks[:2], chips[:3], facts


def tool_audit(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    flags = books.audit_flags(db, company.id, lang)
    sel_ids = set(ctx.get("transaction_ids") or [])
    shown = [f for f in flags if sel_ids & set(f["transaction_ids"])] if sel_ids else flags
    s = books.audit_summary(flags)
    blocks = [{"type": "kpi_row", "title": L("audit", lang), "items": [
                  {"label": L("issues", lang), "value": s["issues"]},
                  {"label": L("at_risk", lang), "value_uzs": s["amount_at_risk_uzs"]}]},
              {"type": "table", "title": L("issues", lang),
               "columns": [L("type", lang), L("message", lang), L("amount", lang)],
               "rows": [[f["type"], f["message"], f["amount_at_risk_uzs"]] for f in shown[:6]],
               "row_ids": [f["transaction_ids"][0] for f in shown[:6]]}]
    chips = [chip("chip_decisions", lang, "/api/v1/decisions"), chip("chip_audit", lang, "/api/v1/books/audit")]
    return blocks, chips, {"issues": s["issues"], "risk": s["amount_at_risk_uzs"],
                           "top": shown[0]["message"] if shown else ""}


def tool_budget(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    b = books.budget_status(db, company, date.today().strftime("%Y-%m"), lang, create_alerts=False)
    items = [i for i in b["items"] if i["planned_uzs"]]
    blocks = [{"type": "bar_chart", "title": f"{L('budget', lang)} {b['month']}",
               "x": [label(TXN_CATEGORY_LABELS, i["category"], lang) for i in items],
               "series": [{"name": L("plan", lang), "values": [i["planned_uzs"] for i in items]},
                          {"name": L("fact", lang), "values": [i["fact_uzs"] for i in items]},
                          {"name": L("forecast", lang), "values": [i["forecast_uzs"] for i in items]}]},
              {"type": "kpi_row", "title": L("budget", lang), "items": [
                  {"label": L("plan", lang), "value_uzs": b["planned_total_uzs"]},
                  {"label": L("fact", lang), "value_uzs": b["fact_total_uzs"]},
                  {"label": L("forecast", lang), "value_uzs": b["forecast_total_uzs"]},
                  {"label": L("used", lang), "value": b["used_pct"]}]}]
    chips = [chip("chip_budget", lang, "/api/v1/books/budget"), chip("chip_decisions", lang, "/api/v1/decisions")]
    problems = [i for i in b["items"] if i["status"] in ("over", "at_risk")]
    return blocks, chips, {"used": b["used_pct"], "problems": len(problems),
                           "first": problems[0]["explanation"] if problems else ""}


def tool_cashflow(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    cf = finance.cashflow(db, company.id, 6)
    avg = finance.avg_net(db, company.id)
    last = [r for r in cf if not r["partial"]][-1] if len(cf) > 1 else cf[-1]
    blocks = [{"type": "line_chart", "title": L("cashflow", lang), "x": [r["month"] for r in cf],
               "series": [{"name": L("income", lang), "values": [r["income_uzs"] for r in cf]},
                          {"name": L("expense", lang), "values": [r["expense_uzs"] for r in cf]},
                          {"name": L("net", lang), "values": [r["net_uzs"] for r in cf]}]},
              {"type": "kpi_row", "title": last["month"], "items": [
                  {"label": L("income", lang), "value_uzs": last["income_uzs"]},
                  {"label": L("expense", lang), "value_uzs": last["expense_uzs"]},
                  {"label": L("net", lang), "value_uzs": last["net_uzs"]},
                  {"label": L("avg_net", lang), "value_uzs": round(avg)}]}]
    chips = [chip("chip_cashflow", lang, "/api/v1/advisor/cashflow?months=12"),
             chip("chip_readiness", lang, "/api/v1/advisor/loan-readiness")]
    return blocks, chips, {"month": last["month"], "net": last["net_uzs"], "avg": round(avg)}


def tool_credit(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    months_m = _MONTHS.search(question)
    months = int(months_m.group(1)) if months_m else 24
    months = max(1, min(months, 36))
    principal = parse_money(question)
    if principal is None:
        capacity = max(finance.avg_net(db, company.id), 0) * settings.MAX_DEBT_SERVICE_RATIO
        principal = round(finance.max_principal(capacity, months, settings.DEFAULT_LOAN_RATE), -6) or 50_000_000
    c = finance.credit(db, company, principal, months, None, lang)
    blocks = [{"type": "loan_schedule", "title": L("loan", lang), "principal_uzs": c["principal_uzs"],
               "months": months, "annual_rate_pct": c["annual_rate_pct"],
               "monthly_payment_uzs": c["monthly_payment_uzs"], "total_interest_uzs": c["total_interest_uzs"],
               "rows": c["schedule"][:12]},
              {"type": "kpi_row", "title": L("loan", lang), "items": [
                  {"label": L("payment", lang), "value_uzs": c["monthly_payment_uzs"]},
                  {"label": L("avg_net", lang), "value_uzs": c["avg_monthly_net_uzs"]},
                  {"label": L("max_loan", lang), "value_uzs": c["max_loan_uzs"]}]}]
    chips = [chip("chip_credit_36", lang, "/api/v1/advisor/credit", "POST",
                  {"principal_uzs": c["principal_uzs"], "months": 36}),
             chip("chip_readiness", lang, "/api/v1/advisor/loan-readiness"),
             chip("chip_plan", lang, "/api/v1/advisor/business-plan", "POST",
                  {"loan_amount_uzs": c["principal_uzs"], "loan_months": months, "purpose": "Aylanma mablag'",
                   "format": "html"})]
    return blocks, chips, {"principal": c["principal_uzs"], "months": months, "payment": c["monthly_payment_uzs"],
                           "affordable": c["affordable"], "max": c["max_loan_uzs"]}


def tool_tax(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    tx = finance.tax(db, company, lang)
    blocks = [{"type": "kpi_row", "title": f"{L('tax', lang)} ({', '.join(tx['months'])})", "items": [
                  {"label": L("turnover_tax", lang), "value_uzs": tx["turnover_regime"]["tax_uzs"]},
                  {"label": L("vat_total", lang), "value_uzs": tx["vat_regime"]["total_uzs"]},
                  {"label": L("saving", lang), "value_uzs": tx["saving_uzs"]}]},
              {"type": "bar_chart", "title": L("tax", lang), "x": [L("turnover_tax", lang), L("vat_total", lang)],
               "series": [{"name": L("tax", lang), "values": [tx["turnover_regime"]["tax_uzs"],
                                                              tx["vat_regime"]["total_uzs"]]}]}]
    chips = [chip("chip_tax", lang, "/api/v1/advisor/tax"), chip("chip_cashflow", lang, "/api/v1/advisor/cashflow")]
    return blocks, chips, {"explanation": tx["explanation"], "disclaimer": tx["disclaimer"]}


def tool_loan_readiness(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    lr = finance.loan_readiness(db, company, lang)
    blocks = [{"type": "kpi_row", "title": L("readiness", lang), "items": [
                  {"label": L("score", lang), "value": lr["score"]}, {"label": "Grade", "value": lr["grade"]}]},
              {"type": "steps", "title": L("improve", lang), "steps": [
                  {"label": f["label"], "status": "done" if f["points"] >= 0.7 * f["max_points"] else "todo",
                   "detail": f"{f['points']}/{f['max_points']} — {f['explanation']}"} for f in lr["factors"]]}]
    chips = [chip("chip_audit", lang, "/api/v1/books/audit"),
             chip("chip_plan", lang, "/api/v1/advisor/business-plan", "POST",
                  {"loan_amount_uzs": 100_000_000, "loan_months": 24, "purpose": "Aylanma mablag'", "format": "html"})]
    return blocks, chips, {"score": lr["score"], "grade": lr["grade"],
                           "tip": lr["how_to_improve"][0] if lr["how_to_improve"] else ""}


def tool_expansion(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    budget = parse_money(question) or 300_000_000
    cat = next((c for c in company.categories or [] if c in ("phone", "laptop", "car", "house", "rent")), "phone")
    x = finance.expansion(db, company, cat, budget, None, lang)
    blocks = [{"type": "kpi_row", "title": L("expansion", lang), "items": [
                  {"label": L("monthly_net", lang), "value_uzs": x["monthly_net_profit_uzs"]},
                  {"label": L("break_even", lang), "value": x["break_even_months"]}]}]
    if x["lines"]:
        blocks.append({"type": "table", "title": L("expansion", lang),
                       "columns": [L("model", lang), L("units_buy", lang), L("buy", lang), L("fair", lang)],
                       "rows": [[li["model"], li["units"], li["buy_price_uzs"], li["sell_price_uzs"]]
                                for li in x["lines"]]})
    else:
        blocks.append({"type": "table", "title": L("expansion", lang), "columns": ["", L("fair", lang), "%"],
                       "rows": [[f"{y['district']}, {y['rooms']}", y["apartment_price_uzs"], y["net_yield_pct"]]
                                for y in x["yield_options"]]})
    chips = [chip("chip_plan", lang, "/api/v1/advisor/business-plan", "POST",
                  {"loan_amount_uzs": round(budget * 0.5), "loan_months": 24, "purpose": "Kengayish",
                   "expansion": {"category": cat, "budget_uzs": budget}, "format": "html"}),
             chip("chip_expansion", lang, "/api/v1/advisor/expansion", "POST", {"category": cat, "budget_uzs": budget})]
    return blocks, chips, {"budget": budget, "net": x["monthly_net_profit_uzs"], "be": x["break_even_months"]}


def tool_business_plan(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    amount = parse_money(question) or 100_000_000
    months_m = _MONTHS.search(question)
    months = int(months_m.group(1)) if months_m else 24
    url = (f"/api/v1/advisor/business-plan?loan_amount_uzs={round(amount)}&loan_months={months}"
           f"&purpose=Aylanma+mablag%27&format=html")
    c = finance.credit(db, company, amount, min(months, 36), None, lang)
    blocks = [{"type": "file", "title": L("plan_doc", lang), "url": url, "mime": "text/html"},
              {"type": "kpi_row", "title": L("loan", lang), "items": [
                  {"label": L("loan", lang), "value_uzs": c["principal_uzs"]},
                  {"label": L("payment", lang), "value_uzs": c["monthly_payment_uzs"]}]}]
    chips = [chip("chip_readiness", lang, "/api/v1/advisor/loan-readiness"),
             chip("chip_plan", lang, "/api/v1/advisor/business-plan", "POST",
                  {"loan_amount_uzs": round(amount), "loan_months": months, "purpose": "Aylanma mablag'",
                   "format": "pdf"})]
    return blocks, chips, {"amount": amount, "months": months}


def tool_demand(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    cat = (company.categories or [None])[0]
    d = exchange.demand(db, 30, cat)
    listed = d["most_listed"][:6]
    blocks = [{"type": "bar_chart", "title": L("listings", lang), "x": [x["model"] for x in listed],
               "series": [{"name": L("listings", lang), "values": [x["listings"] for x in listed]}], "unit": "count"},
              {"type": "table", "title": L("requests", lang), "columns": [L("model", lang), L("requests", lang),
                                                                          L("units", lang)],
               "rows": [[x["model"], x["requests"], x["units"]] for x in d["most_requested"][:6]]}]
    chips = [chip("chip_rfqs", lang, "/api/v1/exchange/rfqs?scope=incoming"),
             chip("chip_stock", lang, "/api/v1/stock/summary")]
    return blocks, chips, {"top": listed[0]["model"] if listed else "", "n": listed[0]["listings"] if listed else 0}


def tool_overview(db: Session, company: Company, question: str, ctx: dict[str, Any], lang: str) -> tuple:
    cf = finance.cashflow(db, company.id, 6)[-1]
    s = books.audit_summary(books.audit_flags(db, company.id, lang))
    lr = finance.loan_readiness(db, company, lang)
    blocks = [{"type": "kpi_row", "title": L("kpis", lang), "items": [
        {"label": L("net", lang), "value_uzs": cf["net_uzs"]},
        {"label": L("issues", lang), "value": s["issues"]},
        {"label": L("at_risk", lang), "value_uzs": s["amount_at_risk_uzs"]},
        {"label": L("readiness", lang), "value": lr["score"]}]}]
    chips = [chip("chip_decisions", lang, "/api/v1/decisions"), chip("chip_stock", lang, "/api/v1/stock/summary"),
             chip("chip_readiness", lang, "/api/v1/advisor/loan-readiness")]
    return blocks, chips, {"net": cf["net_uzs"], "issues": s["issues"], "score": lr["score"]}


TOOLS = {"price": tool_price, "stock": tool_stock, "audit": tool_audit, "budget": tool_budget,
         "cashflow": tool_cashflow, "credit": tool_credit, "tax": tool_tax, "loan_readiness": tool_loan_readiness,
         "expansion": tool_expansion, "business_plan": tool_business_plan, "demand": tool_demand,
         "overview": tool_overview}


def template_answer(intent: str, f: dict[str, Any], lang: str) -> str:
    """Deterministic ≤ 2-sentence answer per intent (also the LLM fallback)."""
    m = lambda v: fmt_uzs(v, lang)  # noqa: E731
    T = {
        "price": (f"{f.get('title')}: bozor narxi {m(f.get('fair'))} (oraliq {m(f.get('p25'))} – {m(f.get('p75'))}).",
                  f"{f.get('title')}: рыночная цена {m(f.get('fair'))} (диапазон {m(f.get('p25'))} – "
                  f"{m(f.get('p75'))}).",
                  f"{f.get('title')}: market price {m(f.get('fair'))} (range {m(f.get('p25'))} – {m(f.get('p75'))})."),
        "stock_one": (f"{f.get('title')} bozordan {f.get('vs')}% farq qiladi. {f.get('reason')}.",
                      f"{f.get('title')}: отклонение от рынка {f.get('vs')}%. {f.get('reason')}.",
                      f"{f.get('title')} is {f.get('vs')}% vs market. {f.get('reason')}."),
        "stock": (f"Omborda {f.get('units')} dona, {f.get('over')} tasi bozordan qimmat. "
                  f"Xavf ostida {m(f.get('risk'))}.",
                  f"На складе {f.get('units')} ед., {f.get('over')} дороже рынка. Под риском {m(f.get('risk'))}.",
                  f"{f.get('units')} units in stock, {f.get('over')} overpriced. {m(f.get('risk'))} at risk."),
        "audit": (f"Auditor {f.get('issues')} ta muammo topdi, xavf ostida {m(f.get('risk'))}. {f.get('top')}",
                  f"Аудитор нашёл {f.get('issues')} проблем, под риском {m(f.get('risk'))}. {f.get('top')}",
                  f"The auditor found {f.get('issues')} issues with {m(f.get('risk'))} at risk. {f.get('top')}"),
        "budget": (f"Byudjet {f.get('used')}% ishlatilgan, {f.get('problems')} ta toifada muammo. {f.get('first')}",
                   f"Бюджет использован на {f.get('used')}%, проблемных статей: {f.get('problems')}. {f.get('first')}",
                   f"Budget is {f.get('used')}% used with {f.get('problems')} problem categories. {f.get('first')}"),
        "cashflow": (f"{f.get('month')} sof natija {m(f.get('net'))}; o'rtacha oylik sof {m(f.get('avg'))}.",
                     f"Чистый результат за {f.get('month')}: {m(f.get('net'))}; в среднем {m(f.get('avg'))} в месяц.",
                     f"Net result for {f.get('month')}: {m(f.get('net'))}; average {m(f.get('avg'))} per month."),
        "credit": (f"{m(f.get('principal'))} {f.get('months')} oyga: oylik to'lov {m(f.get('payment'))}. "
                   f"{'Ko‘tara olasiz' if f.get('affordable') else 'Yuklama yuqori'}, "
                   f"maksimal kredit {m(f.get('max'))}.",
                   f"{m(f.get('principal'))} на {f.get('months')} мес.: платёж {m(f.get('payment'))}. "
                   f"{'По силам' if f.get('affordable') else 'Нагрузка высокая'}, максимум {m(f.get('max'))}.",
                   f"{m(f.get('principal'))} over {f.get('months')} months: {m(f.get('payment'))} per month. "
                   f"{'Affordable' if f.get('affordable') else 'Too heavy'}; max loan {m(f.get('max'))}."),
        "tax": (f"{f.get('explanation')} {f.get('disclaimer')}",) * 3,
        "loan_readiness": (f"Kreditga tayyorlik {f.get('score')}/100 ({f.get('grade')}). {f.get('tip')}",
                           f"Готовность к кредиту {f.get('score')}/100 ({f.get('grade')}). {f.get('tip')}",
                           f"Loan readiness is {f.get('score')}/100 ({f.get('grade')}). {f.get('tip')}"),
        "expansion": (f"{m(f.get('budget'))} byudjet bilan oylik sof foyda {m(f.get('net'))}, "
                      f"qoplash {f.get('be')} oy.",
                      f"С бюджетом {m(f.get('budget'))} чистая прибыль {m(f.get('net'))} в месяц, окупаемость "
                      f"{f.get('be')} мес.",
                      f"With a {m(f.get('budget'))} budget: {m(f.get('net'))} net profit per month, break-even in "
                      f"{f.get('be')} months."),
        "business_plan": (f"{m(f.get('amount'))} kredit uchun biznes-reja tayyor.",
                          f"Бизнес-план на кредит {m(f.get('amount'))} готов.",
                          f"Your business plan for a {m(f.get('amount'))} loan is ready."),
        "demand": (f"Eng ko'p e'lon qilingan model: {f.get('top')} ({f.get('n')} ta).",
                   f"Больше всего объявлений: {f.get('top')} ({f.get('n')}).",
                   f"Most listed model: {f.get('top')} ({f.get('n')} listings)."),
        "overview": (f"Bu oy sof natija {m(f.get('net'))}, audit muammolari {f.get('issues')}, kreditga tayyorlik "
                     f"{f.get('score')}/100.",
                     f"Чистыми в этом месяце {m(f.get('net'))}, проблем аудита {f.get('issues')}, готовность "
                     f"{f.get('score')}/100.",
                     f"This month's net is {m(f.get('net'))}, {f.get('issues')} audit issues, loan readiness "
                     f"{f.get('score')}/100."),
    }
    key = "stock_one" if intent == "stock" and "vs" in f else intent
    return T[key][{"uz": 0, "ru": 1, "en": 2}[lang]].strip()


def _two_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:2])


def answer(db: Session, company: Company, question: str, history: list[dict[str, str]],
           context: dict[str, Any] | None, header_lang: str) -> dict[str, Any]:
    """Run the copilot: route → tool → blocks → answer (LLM phrasing optional)."""
    lang = detect_lang(question, header_lang)
    intent, how = route_intent(question, context)
    blocks, chips, facts = TOOLS[intent](db, company, question, context or {}, lang)
    if facts.get("_intent"):
        intent = facts["_intent"]
    if intent == "price" and "fair" not in facts:  # price fell back to overview
        intent = "overview"
    text = template_answer(intent, facts, lang)
    source = "rules"
    if llm.available():
        lang_name = {"uz": "Uzbek (Latin)", "ru": "Russian", "en": "English"}[lang]
        out = llm.generate_text(
            f"Rewrite this answer for a shop owner in {lang_name} in at most 2 short sentences. Keep every number "
            f"exactly; do not add numbers. Answer: {text}\nQuestion: {question}", timeout=settings.LLM_TIMEOUT_S)
        if out:
            text, source = _two_sentences(out), "llm"
    return {"answer": _two_sentences(text), "used_data": [intent], "language": lang, "source": source,
            "intent": intent, "intent_source": how, "blocks": blocks, "chips": chips}


def context_from_ids(db: Session, company: Company, ctx: dict[str, Any]) -> dict[str, Any]:
    """Drop ids that do not belong to the company."""
    out = dict(ctx or {})
    if out.get("inventory_ids"):
        out["inventory_ids"] = list(db.scalars(select(InventoryItem.id).where(
            InventoryItem.company_id == company.id, InventoryItem.id.in_(out["inventory_ids"]))))
    if out.get("transaction_ids"):
        out["transaction_ids"] = list(db.scalars(select(Transaction.id).where(
            Transaction.company_id == company.id, Transaction.id.in_(out["transaction_ids"]))))
    return out
