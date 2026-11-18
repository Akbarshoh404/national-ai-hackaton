"""AI Advisor (#20): cash flow, credit, tax and loan readiness.

Every number is computed here. The LLM only phrases the executive summary and chat
answers from a context of precomputed facts, and has deterministic fallbacks.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import CREDIT_PRODUCTS, settings
from app.core.errors import AppError
from app.core.i18n import fmt_uzs, register, t
from app.core.models import Company, Transaction
from app.intelligence.b2b import exchange
from app.intelligence.books import books

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
