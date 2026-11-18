"""AI Advisor (#20): cash flow, credit, tax, loan readiness, expansion, business plan, chat.

Every number is computed here. The LLM only phrases the executive summary and chat
answers from a context of precomputed facts, and has deterministic fallbacks.
"""

from __future__ import annotations

import html
import json
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import llm
from app.core.catalog import CATEGORY_LABELS, DISTRICTS, GOODS_CATEGORIES, OPERATING_CATEGORIES, ROLE_LABELS, label
from app.core.config import CREDIT_PRODUCTS, DEALER_MARGIN, RENT_OPEX_RATIO, STOCK_TURNS_PER_MONTH, settings
from app.core.errors import AppError
from app.core.i18n import fmt_uzs, register, t
from app.core.models import Company, Listing, Transaction
from app.intelligence.b2b import exchange
from app.intelligence.books import books
from app.intelligence.market import market, pricing

register({
    "lr.history": {"uz": "Hisob tarixi", "ru": "История учёта", "en": "Data history"},
    "lr.profit": {"uz": "Rentabellik", "ru": "Рентабельность", "en": "Profitability"},
    "lr.stability": {"uz": "Barqarorlik", "ru": "Стабильность", "en": "Stability"},
    "lr.books": {"uz": "Hisob sifati", "ru": "Качество учёта", "en": "Bookkeeping quality"},
    "lr.reputation": {"uz": "B2B obro'", "ru": "B2B-репутация", "en": "B2B reputation"},
    "lr.history.d": {"uz": "{n} oylik ma'lumot (6 oy = maksimum)", "ru": "Данные за {n} мес. (6 мес. = максимум)",
                     "en": "{n} months of records (6 = full score)"},
    "lr.profit.d": {"uz": "Sof marja {pct}% (15%+ = maksimum)", "ru": "Чистая маржа {pct}% (15%+ = максимум)",
                    "en": "Net margin {pct}% (15%+ = full score)"},
    "lr.stability.d": {"uz": "Oylik sof oqim o'zgaruvchanligi {cv}", "ru": "Вариативность чистого потока {cv}",
                       "en": "Variation of monthly net cash flow: {cv}"},
    "lr.books.d": {"uz": "{n} ta jiddiy audit xatosi ochiq", "ru": "Открыто серьёзных ошибок аудита: {n}",
                   "en": "{n} open high-severity audit flags"},
    "lr.reputation.d": {"uz": "{deals} ta bitim, reyting {rating}", "ru": "Сделок: {deals}, рейтинг {rating}",
                        "en": "{deals} deals, rating {rating}"},
    "tip.history": {"uz": "Kamida 6 oylik daromad va xarajatlarni yuklang.",
                    "ru": "Загрузите доходы и расходы минимум за 6 месяцев.",
                    "en": "Upload at least 6 months of income and expenses."},
    "tip.profit": {"uz": "Marjani oshiring: B2B birjada arzonroq xarid qiling, sekin tovarni soting.",
                   "ru": "Повышайте маржу: закупайте дешевле через B2B-биржу, распродайте залежи.",
                   "en": "Raise margin: buy cheaper via the B2B exchange and clear slow stock."},
    "tip.stability": {"uz": "Oylik tushumni tekislang: doimiy mijozlar va oldindan rejalashtirilgan xaridlar.",
                      "ru": "Сгладьте поток: постоянные клиенты и плановые закупки.",
                      "en": "Smooth monthly cash flow with repeat customers and planned purchasing."},
    "tip.books": {"uz": "AI Auditor topgan jiddiy xatolarni tuzating.",
                  "ru": "Исправьте серьёзные ошибки, найденные AI-аудитором.",
                  "en": "Fix the high-severity issues found by the AI Auditor."},
    "tip.reputation": {"uz": "B2B birjada bitimlar qiling va hamkorlardan baho oling.",
                       "ru": "Заключайте сделки на B2B-бирже и собирайте оценки.",
                       "en": "Close deals on the B2B exchange and collect ratings."},
    "credit.ok": {"uz": "Oylik to'lov {payment} — o'rtacha sof oqimning {pct}%. Kredit ko'tara olasiz.",
                  "ru": "Платёж {payment} — {pct}% среднего чистого потока. Кредит по силам.",
                  "en": "Monthly payment {payment} is {pct}% of average net cash flow. Affordable."},
    "credit.no": {"uz": "Oylik to'lov {payment} — o'rtacha sof oqimning {pct}% (chegara {limit}%). Maksimal "
                        "kredit: {max}.",
                  "ru": "Платёж {payment} — {pct}% чистого потока (лимит {limit}%). Максимальный кредит: {max}.",
                  "en": "Payment {payment} is {pct}% of net cash flow (limit {limit}%). Max loan: {max}."},
    "credit.no_cash": {"uz": "So'nggi oylarda sof pul oqimi manfiy — kredit tavsiya etilmaydi.",
                       "ru": "Чистый денежный поток отрицательный — кредит не рекомендуется.",
                       "en": "Net cash flow is negative — a loan is not recommended."},
    "tax.disclaimer": {
        "uz": "Taxminiy hisob. Stavkalar va aylanma soliq chegaralarini soliq.uz da TEKSHIRING.",
        "ru": "Оценка. ПРОВЕРЬТЕ ставки и лимиты упрощённого налога на soliq.uz.",
        "en": "Estimate only. VERIFY rates and turnover-tax eligibility limits on soliq.uz."},
    "tax.cheaper": {"uz": "{regime} rejimi 3 oyda {saving} arzonroq.", "ru": "Режим «{regime}» дешевле на {saving}"
                    " за 3 месяца.", "en": "The {regime} regime is cheaper by {saving} over 3 months."},
    "regime.turnover": {"uz": "aylanma soliq", "ru": "налог с оборота", "en": "turnover tax"},
    "regime.vat": {"uz": "QQS + foyda solig'i", "ru": "НДС + налог на прибыль", "en": "VAT + profit tax"},
})


# --------------------------------------------------------------------------- #
# Cash flow                                                                     #
# --------------------------------------------------------------------------- #

def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _months_back(today: date, n: int) -> list[str]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out[::-1]


def cashflow(db: Session, company_id: int, months: int = 6, today: date | None = None) -> list[dict[str, Any]]:
    """Monthly income / expense / net for the last `months` months (current month last)."""
    today = today or date.today()
    keys = _months_back(today, months)
    start = date(int(keys[0][:4]), int(keys[0][5:]), 1)
    agg = {k: {"month": k, "income_uzs": 0.0, "expense_uzs": 0.0} for k in keys}
    for tx in db.scalars(select(Transaction).where(Transaction.company_id == company_id, Transaction.date >= start)):
        k = _month_key(tx.date)
        if k in agg:
            agg[k]["income_uzs" if tx.type == "income" else "expense_uzs"] += tx.total
    out = []
    for k in keys:
        a = agg[k]
        out.append({"month": k, "income_uzs": round(a["income_uzs"]), "expense_uzs": round(a["expense_uzs"]),
                    "net_uzs": round(a["income_uzs"] - a["expense_uzs"]), "partial": k == _month_key(today)})
    return out


def complete_months(db: Session, company_id: int, n: int = 3, today: date | None = None) -> list[dict[str, Any]]:
    """Last `n` complete months that have any records."""
    rows = [r for r in cashflow(db, company_id, 12, today) if not r["partial"]
            and (r["income_uzs"] or r["expense_uzs"])]
    return rows[-n:]


def avg_net(db: Session, company_id: int, today: date | None = None) -> float:
    rows = complete_months(db, company_id, 3, today)
    return float(np.mean([r["net_uzs"] for r in rows])) if rows else 0.0


# --------------------------------------------------------------------------- #
# Credit                                                                        #
# --------------------------------------------------------------------------- #

def annuity_payment(principal: float, months: int, annual_rate_pct: float) -> float:
    """Annuity payment: P·r / (1 − (1 + r)^−n), r = monthly rate."""
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def max_principal(payment: float, months: int, annual_rate_pct: float) -> float:
    """Largest loan whose annuity payment equals `payment`."""
    if payment <= 0:
        return 0.0
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return payment * months
    return payment * (1 - (1 + r) ** -months) / r


def amortization(principal: float, months: int, annual_rate_pct: float) -> list[dict[str, float]]:
    """Full annuity schedule. The last row absorbs rounding so Σ principal = principal exactly."""
    pay = annuity_payment(principal, months, annual_rate_pct)
    r = annual_rate_pct / 100 / 12
    balance, rows = principal, []
    for m in range(1, months + 1):
        interest = round(balance * r, 2)
        princ = round(pay - interest, 2) if m < months else round(balance, 2)
        payment = round(princ + interest, 2)
        balance = round(balance - princ, 2)
        rows.append({"month": m, "payment_uzs": payment, "principal_uzs": princ, "interest_uzs": interest,
                     "balance_uzs": max(balance, 0.0)})
    return rows


def credit(db: Session, company: Company, principal: float | None, months: int, rate: float | None,
           lang: str, product: str = "business_loan", down_payment_pct: float | None = None,
           asset_value: float | None = None) -> dict[str, Any]:
    """Credit calculator for a product: annuity, schedule, affordability, max loan and LTV (asset loans)."""
    spec = CREDIT_PRODUCTS[product]
    if months > spec["max_months"]:
        raise AppError("term_too_long", f"{product} allows at most {int(spec['max_months'])} months", 422,
                       {"max_months": int(spec["max_months"])})
    if rate is None:
        rate = settings.DEFAULT_LOAN_RATE if product == "business_loan" else spec["rate_pct"]
    down_pct = spec["down_payment_pct"] if down_payment_pct is None else down_payment_pct
    down = ltv = None
    if asset_value:
        down = asset_value * down_pct
        if principal is None:
            principal = asset_value - down
        ltv = round(principal / asset_value, 4)
    if principal is None or principal <= 0:
        raise AppError("principal_required", "Give principal_uzs, or asset_value_uzs for asset loans", 422)
    pay = annuity_payment(principal, months, rate)
    schedule = amortization(principal, months, rate)
    net = avg_net(db, company.id)
    capacity = max(net, 0.0) * settings.MAX_DEBT_SERVICE_RATIO
    affordable = net > 0 and pay <= capacity
    max_loan = max_principal(capacity, months, rate)
    ratio = pay / net * 100 if net > 0 else None
    if net <= 0:
        verdict = t("credit.no_cash", lang)
    elif affordable:
        verdict = t("credit.ok", lang, payment=fmt_uzs(pay, lang), pct=round(ratio or 0))
    else:
        verdict = t("credit.no", lang, payment=fmt_uzs(pay, lang), pct=round(ratio or 0),
                    limit=round(settings.MAX_DEBT_SERVICE_RATIO * 100), max=fmt_uzs(max_loan, lang))
    return {"principal_uzs": round(principal), "months": months, "annual_rate_pct": rate,
            "monthly_payment_uzs": round(pay), "total_payment_uzs": round(pay * months),
            "total_interest_uzs": round(pay * months - principal), "avg_monthly_net_uzs": round(net),
            "debt_service_ratio_pct": round(ratio, 1) if ratio is not None else None,
            "max_debt_service_ratio_pct": settings.MAX_DEBT_SERVICE_RATIO * 100, "affordable": affordable,
            "max_loan_uzs": round(max_loan), "verdict": verdict,
            "max_loan_by_term": {str(n): round(max_principal(capacity, n, rate)) for n in (12, 24, 36)},
            "rate_note": "Placeholder product rate — VERIFY with partner banks",
            "product": product, "down_payment_pct": down_pct if asset_value else None,
            "down_payment_uzs": round(down) if down is not None else None,
            "asset_value_uzs": round(asset_value) if asset_value else None, "ltv": ltv,
            "schedule": schedule}


# --------------------------------------------------------------------------- #
# Tax                                                                           #
# --------------------------------------------------------------------------- #
_NON_VATABLE = {"salaries", "taxes"}


def tax(db: Session, company: Company, lang: str) -> dict[str, Any]:
    """Turnover tax vs VAT + profit tax over the last 3 complete months."""
    months = [r["month"] for r in complete_months(db, company.id, 3)]
    income = expenses = vatable = 0.0
    for tx in db.scalars(select(Transaction).where(Transaction.company_id == company.id)):
        if _month_key(tx.date) not in months:
            continue
        if tx.type == "income":
            income += tx.total
        elif tx.category != "taxes":
            expenses += tx.total
            if tx.category not in _NON_VATABLE:
                vatable += tx.total
    vat_r, tov_r, prof_r = settings.VAT_RATE, settings.TURNOVER_TAX_RATE, settings.PROFIT_TAX_RATE
    turnover_tax = income * tov_r
    out_vat = income * vat_r / (1 + vat_r)
    in_vat = vatable * vat_r / (1 + vat_r)
    vat_payable = max(out_vat - in_vat, 0.0)
    profit = (income - out_vat) - (expenses - in_vat)
    profit_tax = max(profit, 0.0) * prof_r
    vat_total = vat_payable + profit_tax
    cheaper = "turnover" if turnover_tax <= vat_total else "vat"
    saving = abs(turnover_tax - vat_total)
    return {"months": months, "turnover_uzs": round(income), "expenses_uzs": round(expenses),
            "turnover_regime": {"rate_pct": tov_r * 100, "tax_uzs": round(turnover_tax)},
            "vat_regime": {"vat_rate_pct": vat_r * 100, "profit_tax_rate_pct": prof_r * 100,
                           "output_vat_uzs": round(out_vat), "input_vat_uzs": round(in_vat),
                           "vat_payable_uzs": round(vat_payable), "taxable_profit_uzs": round(profit),
                           "profit_tax_uzs": round(profit_tax), "total_uzs": round(vat_total)},
            "current_regime": company.tax_regime, "cheaper_regime": cheaper, "saving_uzs": round(saving),
            "explanation": t("tax.cheaper", lang, regime=t(f"regime.{cheaper}", lang), saving=fmt_uzs(saving, lang)),
            "rates_verified": False, "disclaimer": t("tax.disclaimer", lang)}


# --------------------------------------------------------------------------- #
# Loan readiness                                                                #
# --------------------------------------------------------------------------- #

def loan_readiness(db: Session, company: Company, lang: str, flags: list[dict[str, Any]] | None = None
                   ) -> dict[str, Any]:
    """0–100 score: history 25, profitability 25, stability 20, books 15, reputation 15."""
    hist = [r for r in cashflow(db, company.id, 12) if r["income_uzs"] or r["expense_uzs"]]
    n_months = len(hist)
    history = min(n_months, 6) / 6 * 25
    last3 = complete_months(db, company.id, 3)
    inc = sum(r["income_uzs"] for r in last3)
    margin = sum(r["net_uzs"] for r in last3) / inc if inc else 0.0
    profit = float(np.clip(margin / 0.15, 0, 1) * 25)
    nets = [r["net_uzs"] for r in complete_months(db, company.id, 6)]
    cv = None
    stability = 0.0
    if len(nets) >= 2 and np.mean(nets) > 0:
        cv = float(np.std(nets) / np.mean(nets))
        stability = float(np.clip((1 - cv) / 0.8, 0, 1) * 20)
    flags = books.audit_flags(db, company.id, lang) if flags is None else flags
    high = sum(1 for f in flags if f["severity"] == "high")
    bookkeeping = max(0.0, 15 - 5 * high)
    rep = exchange.reputation(db, company.id)
    reputation = min(rep["deals_count"], 5) / 5 * 8 + ((rep["rating"] / 5) if rep["rating"] else 0.6) * 7
    factors = [
        ("history", history, 25, t("lr.history.d", lang, n=n_months)),
        ("profit", profit, 25, t("lr.profit.d", lang, pct=round(margin * 100, 1))),
        ("stability", stability, 20, t("lr.stability.d", lang, cv="—" if cv is None else f"{cv:.2f}")),
        ("books", bookkeeping, 15, t("lr.books.d", lang, n=high)),
        ("reputation", reputation, 15, t("lr.reputation.d", lang, deals=rep["deals_count"],
                                         rating=rep["rating"] if rep["rating"] is not None else "—")),
    ]
    score = round(min(100.0, max(0.0, sum(f[1] for f in factors))))
    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    tips = [t(f"tip.{k}", lang) for k, pts, mx, _ in sorted(factors, key=lambda f: f[1] / f[2]) if pts < 0.7 * mx]
    return {"score": score, "grade": grade,
            "factors": [{"key": k, "label": t(f"lr.{k}", lang), "points": round(p, 1), "max_points": mx,
                         "explanation": d} for k, p, mx, d in factors],
            "how_to_improve": tips}


# --------------------------------------------------------------------------- #
# Expansion planner                                                             #
# --------------------------------------------------------------------------- #

def _monthly_opex(db: Session, company_id: int) -> float:
    months = [r["month"] for r in complete_months(db, company_id, 3)]
    if not months:
        return 0.0
    total = sum(tx.total for tx in db.scalars(select(Transaction).where(
        Transaction.company_id == company_id, Transaction.type == "expense",
        Transaction.category.in_(OPERATING_CATEGORIES))) if _month_key(tx.date) in months)
    return total / len(months)


def _typical(db: Session, category: str, model_norm: str) -> dict[str, Any]:
    """Most common configuration of a model on the market."""
    since = date.today() - timedelta(days=settings.MARKET_WINDOW_DAYS)
    rows = db.execute(select(Listing.brand, Listing.model, Listing.condition, Listing.attrs).where(
        Listing.category == category, Listing.model_norm == model_norm, Listing.posted_at >= since)).all()

    def mode(vals: list[Any]) -> Any:
        vals = [v for v in vals if v is not None]
        return max(set(vals), key=vals.count) if vals else None

    attrs: dict[str, Any] = {}
    for key in {"phone": ["storage_gb"], "laptop": ["ram_gb", "ssd_gb"], "car": ["fuel"]}.get(category, []):
        attrs[key] = mode([(r.attrs or {}).get(key) for r in rows])
    if category == "car":
        years = [(r.attrs or {}).get("year") for r in rows if (r.attrs or {}).get("year")]
        attrs["year"] = int(np.median(years)) if years else None
    return {"brand": mode([r.brand for r in rows]), "model": mode([r.model for r in rows]),
            "condition": mode([r.condition for r in rows]), "attrs": {k: v for k, v in attrs.items() if v}}


def expansion(db: Session, company: Company, category: str, budget_uzs: float, district: str | None,
              lang: str) -> dict[str, Any]:
    """Expansion plan: goods → stock plan with profit and break-even; realty → best yields in budget."""
    if category in GOODS_CATEGORIES:
        return _expansion_goods(db, company, category, budget_uzs, lang)
    return _expansion_realty(db, category, budget_uzs, district, lang)


def _expansion_goods(db: Session, company: Company, category: str, budget: float, lang: str) -> dict[str, Any]:
    top = market.models(db, category, None, 5)
    setup = budget * 0.10
    opex = _monthly_opex(db, company.id) or budget * 0.025
    reserve = 2 * opex
    stock_budget = budget - setup - reserve
    if stock_budget <= 0:
        raise AppError("budget_too_small", "Budget does not cover setup cost and a 2-month opex reserve", 422,
                       {"setup_uzs": round(setup), "reserve_uzs": round(reserve)})
    picks = []
    for m in top:
        typ = _typical(db, category, m["model_norm"])
        est = pricing.try_estimate(db, category=category, model=typ["model"], brand=typ["brand"],
                                   condition=typ["condition"], attrs=typ["attrs"], lang=lang)
        if est:
            picks.append((m, typ, est))
        if len(picks) == 3:
            break
    if not picks:
        raise pricing.NotEnoughData(0, lang)
    volume = sum(p[0]["listings"] for p in picks)
    turns = STOCK_TURNS_PER_MONTH[category]
    lines, gross, invested = [], 0.0, 0.0
    for m, typ, est in picks:
        alloc = stock_budget * m["listings"] / volume
        units = int(alloc // est.fair_buy_price_uzs)
        unit_margin = est.fair_price_uzs - est.fair_buy_price_uzs
        monthly = units * turns * unit_margin
        gross += monthly
        invested += units * est.fair_buy_price_uzs
        lines.append({"model": " ".join(x for x in (typ["brand"], typ["model"]) if x), "condition": typ["condition"],
                      "attrs": typ["attrs"], "market_listings": m["listings"], "units": units,
                      "buy_price_uzs": est.fair_buy_price_uzs, "sell_price_uzs": est.fair_price_uzs,
                      "unit_margin_uzs": round(unit_margin), "monthly_gross_profit_uzs": round(monthly),
                      "basis": est.basis, "confidence": est.confidence})
    net = gross - opex
    return {"category": category, "budget_uzs": round(budget), "setup_cost_uzs": round(setup),
            "opex_reserve_uzs": round(reserve), "stock_budget_uzs": round(stock_budget),
            "stock_invested_uzs": round(invested), "stock_turns_per_month": turns,
            "monthly_gross_profit_uzs": round(gross), "monthly_opex_uzs": round(opex),
            "monthly_net_profit_uzs": round(net),
            "break_even_months": round(setup / net, 1) if net > 0 else None,
            "lines": lines, "yield_options": [],
            "assumptions": [
                f"Buy at the market fair purchase price (fair × (1 − {int(DEALER_MARGIN[category] * 100)}%)) and "
                "sell at the market fair price",
                "Setup cost = 10% of the budget", "Opex reserve = 2 months of current operating costs",
                f"Stock turns {turns}× per month for {category}",
                "Stock budget split across the top models by market listing volume",
                "Extra monthly opex of the new point = current monthly operating costs"]}


def _expansion_realty(db: Session, category: str, budget: float, district: str | None,
                      lang: str) -> dict[str, Any]:
    options = []
    districts = [district] if district else DISTRICTS
    df = pricing.load_frame(db, "house")
    for d in districts:
        for rooms in (1, 2, 3):
            sub = df[(df["district"] == d) & (df["rooms"] == rooms)]
            if sub.empty:
                continue
            area = float(sub["area_m2"].median())
            try:
                y = market.rental_yield(db, d, rooms, round(area, 1), None, lang)
            except AppError:
                continue
            if y["apartment_price_uzs"] <= budget:
                options.append(y)
    options.sort(key=lambda y: y["net_yield_pct"], reverse=True)
    best = options[:5]
    return {"category": category, "budget_uzs": round(budget), "setup_cost_uzs": 0, "opex_reserve_uzs": 0,
            "stock_budget_uzs": round(budget), "stock_invested_uzs": round(best[0]["apartment_price_uzs"]) if best
            else 0, "stock_turns_per_month": 0, "monthly_gross_profit_uzs": round(best[0]["monthly_rent_uzs"])
            if best else 0, "monthly_opex_uzs": round(best[0]["monthly_rent_uzs"] * RENT_OPEX_RATIO) if best else 0,
            "monthly_net_profit_uzs": round(best[0]["monthly_rent_uzs"] * (1 - RENT_OPEX_RATIO)) if best else 0,
            "break_even_months": round(best[0]["payback_years"] * 12, 1) if best and best[0]["payback_years"]
            else None, "lines": [], "yield_options": best,
            "assumptions": ["Typical apartment size = median area for the district and room count",
                            f"Net yield deducts {int(RENT_OPEX_RATIO * 100)}% of rent (vacancy, maintenance, tax)",
                            "Only apartments whose fair price fits the budget"]}


# --------------------------------------------------------------------------- #
# Business plan                                                                 #
# --------------------------------------------------------------------------- #

def business_plan(db: Session, company: Company, loan_amount: float, loan_months: int, purpose: str,
                  expansion_req: dict[str, Any] | None, lang: str) -> dict[str, Any]:
    """Bank-ready plan built from the company's own numbers."""
    flags = books.audit_flags(db, company.id, lang)
    cf = cashflow(db, company.id, 6)
    loan = credit(db, company, loan_amount, loan_months, None, lang)
    reval = books.revaluation(db, company, lang)
    readiness = loan_readiness(db, company, lang, flags)
    taxes = tax(db, company, lang)
    exp = None
    if expansion_req:
        exp = expansion(db, company, expansion_req["category"], expansion_req["budget_uzs"],
                        expansion_req.get("district"), lang)
    facts = {
        "company": company.name, "role": company.role, "categories": company.categories,
        "district": company.district, "income_6m_uzs": sum(r["income_uzs"] for r in cf),
        "net_6m_uzs": sum(r["net_uzs"] for r in cf), "avg_monthly_net_uzs": loan["avg_monthly_net_uzs"],
        "loan_uzs": loan["principal_uzs"], "loan_months": loan_months, "monthly_payment_uzs":
            loan["monthly_payment_uzs"], "affordable": loan["affordable"], "loan_readiness": readiness["score"],
        "grade": readiness["grade"], "inventory_market_value_uzs": reval["market_value_uzs"], "purpose": purpose,
    }
    summary, source = _exec_summary(facts, lang)
    return {"company": {"name": company.name, "stir": company.stir, "role": company.role,
                        "role_label": label(ROLE_LABELS, company.role, lang),
                        "categories": [label(CATEGORY_LABELS, c, lang) for c in company.categories],
                        "city": company.city, "district": company.district, "tax_regime": company.tax_regime},
            "generated_on": date.today(), "language": lang, "purpose": purpose,
            "executive_summary": summary, "summary_source": source,
            "financials": cf, "inventory": reval, "loan": loan, "expansion": exp,
            "loan_readiness": readiness, "tax": taxes,
            "audit_summary": books.audit_summary(flags)}


def _exec_summary(facts: dict[str, Any], lang: str) -> tuple[str, str]:
    fallback = {
        "uz": "{company} ({district}) so'nggi 6 oyda {income} tushum va {net} sof natija qayd etdi. "
              "{loan} kredit {months} oyga so'ralmoqda, oylik to'lov {payment} ({aff}). "
              "Kreditga tayyorlik bahosi {score}/100 ({grade}). Tovar zaxirasining bozor qiymati {inv}. "
              "Maqsad: {purpose}.",
        "ru": "{company} ({district}) за 6 месяцев: выручка {income}, чистый результат {net}. Запрашивается кредит "
              "{loan} на {months} мес., платёж {payment} ({aff}). Готовность к кредиту {score}/100 ({grade}). "
              "Рыночная стоимость запасов {inv}. Цель: {purpose}.",
        "en": "{company} ({district}) recorded {income} revenue and a {net} net result over 6 months. It requests "
              "a {loan} loan for {months} months with a {payment} monthly payment ({aff}). Loan readiness "
              "{score}/100 (grade {grade}). Inventory market value {inv}. Purpose: {purpose}.",
    }[lang].format(company=facts["company"], district=facts["district"] or "Toshkent",
                   income=fmt_uzs(facts["income_6m_uzs"], lang), net=fmt_uzs(facts["net_6m_uzs"], lang),
                   loan=fmt_uzs(facts["loan_uzs"], lang), months=facts["loan_months"],
                   payment=fmt_uzs(facts["monthly_payment_uzs"], lang),
                   aff={"uz": "to'lovga qodir" if facts["affordable"] else "yuklama yuqori",
                        "ru": "по силам" if facts["affordable"] else "нагрузка высокая",
                        "en": "affordable" if facts["affordable"] else "high debt load"}[lang],
                   score=facts["loan_readiness"], grade=facts["grade"],
                   inv=fmt_uzs(facts["inventory_market_value_uzs"], lang), purpose=facts["purpose"])
    if not llm.available():
        return fallback, "rules"
    lang_name = {"uz": "Uzbek (Latin)", "ru": "Russian", "en": "English"}[lang]
    text = llm.generate_text(
        f"Write a 4-5 sentence executive summary for a bank loan application in {lang_name}. Use ONLY these facts "
        f"and numbers; do not add or change numbers (amounts are UZS): {json.dumps(facts, ensure_ascii=False)}",
        timeout=settings.LLM_TIMEOUT_S)
    return (text, "llm") if text else (fallback, "rules")


_H = {
    "title": {"uz": "Biznes-reja", "ru": "Бизнес-план", "en": "Business plan"},
    "s1": {"uz": "1. Qisqacha xulosa", "ru": "1. Резюме", "en": "1. Executive summary"},
    "s2": {"uz": "2. Kompaniya", "ru": "2. Профиль компании", "en": "2. Company profile"},
    "s3": {"uz": "3. 6 oylik moliya", "ru": "3. Финансы за 6 месяцев", "en": "3. 6-month financials"},
    "s4": {"uz": "4. Zaxira bozor qiymatida", "ru": "4. Запасы по рыночной стоимости", "en": "4. Inventory at market"},
    "s5": {"uz": "5. Kredit so'rovi", "ru": "5. Запрос кредита", "en": "5. Loan request"},
    "s6": {"uz": "6. Kengayish rejasi", "ru": "6. План расширения", "en": "6. Expansion"},
    "s7": {"uz": "7. Kreditga tayyorlik", "ru": "7. Готовность к кредиту", "en": "7. Loan readiness"},
    "s8": {"uz": "8. Soliq holati", "ru": "8. Налоговая позиция", "en": "8. Tax position"},
}


_CSS = (
    "body{font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;max-width:860px;margin:24px auto;padding:0 16px;"
    "font-size:13px}h1{font-size:22px;margin-bottom:4px}h2{font-size:16px;margin-top:24px;"
    "border-bottom:2px solid #0b6e4f;padding-bottom:4px}table{width:100%;border-collapse:collapse;margin:8px 0}"
    "td,th{border:1px solid #ddd;padding:5px 7px;text-align:left}th{background:#f1f5f3}"
    ".muted{color:#666;font-size:11px}.kpi{font-size:18px;font-weight:bold}"
)


def render_plan_html(plan: dict[str, Any]) -> str:
    """Self-contained HTML (also the WeasyPrint input)."""
    lang = plan["language"]
    e = html.escape

    def h(k: str) -> str:
        return _H[k][lang]

    def m(v: Any) -> str:
        return e(fmt_uzs(v, lang)) if v is not None else "—"

    c = plan["company"]
    rows_cf = "".join(f"<tr><td>{r['month']}</td><td>{m(r['income_uzs'])}</td><td>{m(r['expense_uzs'])}</td>"
                      f"<td>{m(r['net_uzs'])}</td></tr>" for r in plan["financials"])
    inv = plan["inventory"]
    rows_inv = "".join(f"<tr><td>{e(i['model'])}</td><td>{i['qty']}</td><td>{m(i['unit_cost_uzs'])}</td>"
                       f"<td>{m(i['market_value_per_unit_uzs'])}</td><td>{m(i['unrealized_margin_uzs'])}</td></tr>"
                       for i in inv["items"])
    loan = plan["loan"]
    lr = plan["loan_readiness"]
    rows_lr = "".join(f"<tr><td>{e(f['label'])}</td><td>{f['points']}/{f['max_points']}</td>"
                      f"<td>{e(f['explanation'])}</td></tr>" for f in lr["factors"])
    tx = plan["tax"]
    exp_html = ""
    if plan["expansion"]:
        x = plan["expansion"]
        lines = "".join(f"<tr><td>{e(li['model'])}</td><td>{li['units']}</td><td>{m(li['buy_price_uzs'])}</td>"
                        f"<td>{m(li['sell_price_uzs'])}</td><td>{m(li['monthly_gross_profit_uzs'])}</td></tr>"
                        for li in x["lines"])
        yields = "".join(f"<tr><td>{e(y['district'])}, {y['rooms']}</td><td>{m(y['apartment_price_uzs'])}</td>"
                         f"<td>{m(y['monthly_rent_uzs'])}</td><td>{y['net_yield_pct']}%</td></tr>"
                         for y in x["yield_options"])
        exp_html = (f"<h2>{h('s6')}</h2><p>Budget {m(x['budget_uzs'])} · net/month {m(x['monthly_net_profit_uzs'])}"
                    f" · break-even {x['break_even_months'] or '—'} months</p>"
                    + (f"<table><tr><th>Model</th><th>Units</th><th>Buy</th><th>Sell</th><th>Gross/mo</th></tr>"
                       f"{lines}</table>" if lines else "")
                    + (f"<table><tr><th>Option</th><th>Price</th><th>Rent</th><th>Net yield</th></tr>{yields}"
                       "</table>" if yields else "")
                    + "<ul>" + "".join(f"<li>{e(a)}</li>" for a in x["assumptions"]) + "</ul>")
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{h('title')} — {e(c['name'])}
</title><style>{_CSS}</style></head><body>
<h1>{h('title')}: {e(c['name'])}</h1>
<div class="muted">STIR {e(c['stir'])} · {plan['generated_on']} · BozorPilot AI</div>
<h2>{h('s1')}</h2><p>{e(plan['executive_summary'])}</p>
<h2>{h('s2')}</h2><table><tr><th>Role</th><td>{e(c['role_label'])}</td></tr><tr><th>Categories</th>
<td>{e(', '.join(c['categories']))}</td></tr><tr><th>Location</th><td>{e(c['city'])}, {e(c['district'] or '')}</td></tr>
<tr><th>Tax regime</th><td>{e(c['tax_regime'])}</td></tr></table>
<h2>{h('s3')}</h2><table><tr><th>Month</th><th>Income</th><th>Expense</th><th>Net</th></tr>{rows_cf}</table>
<h2>{h('s4')}</h2><p class="kpi">{m(inv['market_value_uzs'])}</p><table><tr><th>Model</th><th>Qty</th>
<th>Unit cost</th><th>Market/unit</th><th>Unrealized</th></tr>{rows_inv}</table>
<h2>{h('s5')}</h2><table><tr><th>Amount</th><td>{m(loan['principal_uzs'])}</td></tr><tr><th>Term</th>
<td>{loan['months']}</td></tr><tr><th>Rate</th><td>{loan['annual_rate_pct']}% (VERIFY)</td></tr><tr><th>Payment</th>
<td>{m(loan['monthly_payment_uzs'])}</td></tr><tr><th>Avg net cash flow</th><td>{m(loan['avg_monthly_net_uzs'])}</td>
</tr><tr><th>Max loan</th><td>{m(loan['max_loan_uzs'])}</td></tr></table><p>{e(loan['verdict'])}</p>
<p>{e(plan['purpose'])}</p>
{exp_html}
<h2>{h('s7')}</h2><p class="kpi">{lr['score']}/100 ({lr['grade']})</p><table>{rows_lr}</table>
<ul>{''.join(f'<li>{e(x)}</li>' for x in lr['how_to_improve'])}</ul>
<h2>{h('s8')}</h2><table><tr><th>Turnover (3 mo)</th><td>{m(tx['turnover_uzs'])}</td></tr>
<tr><th>Turnover tax</th><td>{m(tx['turnover_regime']['tax_uzs'])}</td></tr>
<tr><th>VAT + profit tax</th><td>{m(tx['vat_regime']['total_uzs'])}</td></tr></table>
<p>{e(tx['explanation'])}</p><p class="muted">{e(tx['disclaimer'])}</p>
</body></html>"""


def render_pdf(html_doc: str) -> bytes | None:
    """PDF via WeasyPrint when installed; None otherwise (caller returns HTML)."""
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except Exception:
        return None
    return HTML(string=html_doc).write_pdf()
