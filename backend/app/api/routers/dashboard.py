"""`/dashboard`: everything the home screen needs in one call."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
from fastapi import APIRouter
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routers.alerts import alert_out
from app.api.routers.decisions import decision_out
from app.api.routers.exchange import deal_out, rfq_out
from app.api.routers.market import listing_out
from app.api.schemas.advisor import DashboardKpis
from app.api.schemas.dashboard import (
    BudgetSummary,
    CreditSummary,
    PriceIndex,
    RfqQuotesSummary,
    SalesSummary,
    TodayDashboardOut,
)
from app.core import alerts as alert_svc
from app.core import fx
from app.core.config import settings
from app.core.db import utcnow
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.i18n import fmt_uzs, register, t
from app.core.models import Alert, Company, Deal, Listing, Quote, Rfq, Transaction
from app.intelligence.advisor import finance
from app.intelligence.books import books, decisions
from app.intelligence.market import market, stock

router = APIRouter(tags=["dashboard"])

SALES_DAYS = 90
INDEX_WEEKS = 8

register({
    "dash.insight.decision": {
        "uz": "{n} ta qaror kutmoqda. Eng kattasi: {title} ({amount}).",
        "ru": "Ждут решения: {n}. Самое крупное: {title} ({amount}).",
        "en": "{n} decisions are waiting. The largest: {title} ({amount}).",
    },
    "dash.insight.sales": {
        "uz": "Bugungi savdo {today}, 30 kunlik o'rtacha {avg} kuniga.",
        "ru": "Продажи сегодня {today}, среднее за 30 дней {avg} в день.",
        "en": "Sales today {today}; the 30-day average is {avg} a day.",
    },
})


def sales_summary(db: Session, company_id: int, today: date) -> dict[str, Any]:
    """Daily `sale` income for the last SALES_DAYS days plus today-vs-yesterday and a 30-day average."""
    start = today - timedelta(days=SALES_DAYS - 1)
    rows = db.execute(select(Transaction.date, func.sum(Transaction.total))
                      .where(Transaction.company_id == company_id, Transaction.type == "income",
                             Transaction.category == "sale", Transaction.date >= start, Transaction.date <= today)
                      .group_by(Transaction.date)).all()
    by_day = {d: float(v or 0) for d, v in rows}
    days = [start + timedelta(days=i) for i in range(SALES_DAYS)]
    series = [{"date": d, "total_uzs": round(by_day.get(d, 0.0))} for d in days]
    today_v = by_day.get(today, 0.0)
    yday_v = by_day.get(today - timedelta(days=1), 0.0)
    prev30 = [by_day.get(today - timedelta(days=i), 0.0) for i in range(1, 31)]
    return {"today_uzs": round(today_v), "yesterday_uzs": round(yday_v), "delta_uzs": round(today_v - yday_v),
            "delta_pct": round((today_v / yday_v - 1) * 100, 1) if yday_v else None,
            "avg_daily_uzs": round(sum(prev30) / 30), "days": series}


def price_index(db: Session, company: Company) -> dict[str, Any] | None:
    """Weekly median / p25 / p75 (USD) of the most-listed model in the company's categories."""
    cats = company.categories or []
    if not cats:
        return None
    since = utcnow() - timedelta(days=settings.MARKET_WINDOW_DAYS)
    base = (Listing.category.in_(cats), Listing.is_duplicate.is_(False), Listing.model_norm != "")
    top = db.execute(select(Listing.category, Listing.model_norm, func.max(Listing.model), func.count())
                     .where(*base, Listing.posted_at >= since)
                     .group_by(Listing.category, Listing.model_norm)
                     .order_by(func.count().desc()).limit(1)).first()
    if top is None:
        return None
    category, model_norm, model, _ = top
    first_week = date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=INDEX_WEEKS - 1)
    rows = db.execute(select(Listing.posted_at, Listing.price_usd)
                      .where(*base, Listing.category == category, Listing.model_norm == model_norm,
                             Listing.posted_at >= first_week, Listing.price_usd > 0)).all()
    weeks: dict[date, list[float]] = {}
    for posted, usd in rows:
        d = posted.date()
        weeks.setdefault(d - timedelta(days=d.weekday()), []).append(float(usd))
    points = []
    for wk in sorted(weeks):
        arr = np.array(weeks[wk])
        points.append({"week_start": wk, "median_usd": round(float(np.median(arr)), 2),
                       "p25_usd": round(float(np.percentile(arr, 25)), 2),
                       "p75_usd": round(float(np.percentile(arr, 75)), 2), "listings": len(arr)})
    if len(points) < 2:
        return None
    prev, last = points[-2]["median_usd"], points[-1]["median_usd"]
    return {"category": category, "model": model, "points": points,
            "change_pct": round((last / prev - 1) * 100, 1) if prev else None}


def rfq_quotes(db: Session, company: Company) -> dict[str, Any] | None:
    """The company's own open RFQ with the most quotes, quotes sorted by unit price (lowest = best)."""
    row = db.execute(select(Rfq, func.count(Quote.id).label("n")).join(Quote, Quote.rfq_id == Rfq.id)
                     .where(Rfq.company_id == company.id, Rfq.status == "open")
                     .group_by(Rfq.id).order_by(func.count(Quote.id).desc(), Rfq.id.desc()).limit(1)).first()
    if row is None:
        return None
    rfq = row[0]
    quotes = list(db.scalars(select(Quote).where(Quote.rfq_id == rfq.id).order_by(Quote.unit_price)))
    names = {c.id: c.name for c in db.scalars(select(Company).where(Company.id.in_([q.supplier_id for q in quotes])))}
    return {"rfq_id": rfq.id, "title": " ".join(x for x in (rfq.brand, rfq.model) if x), "qty": rfq.qty,
            "quotes": [{"quote_id": q.id, "supplier_name": names.get(q.supplier_id, f"#{q.supplier_id}"),
                        "unit_price_uzs": q.unit_price, "delivery_days": q.delivery_days, "best": i == 0}
                       for i, q in enumerate(quotes)]}


@router.get("/dashboard", response_model=TodayDashboardOut)
def dashboard_get(db: DbDep, company: CompanyDep, lang: LangDep) -> TodayDashboardOut:
    """KPIs, top alerts, sourcing deals, open RFQs, recent deals, a 6-month cash-flow series and the home-screen
    tiles (daily sales, budget, credit readiness, price index, own RFQ quotes). Every number is computed here."""
    today = date.today()
    month = today.strftime("%Y-%m")
    decisions.ensure_built(db, company)
    pending = decisions.pending(db, company)
    cf = finance.cashflow(db, company.id, 6)
    cur = cf[-1]
    flags = books.audit_flags(db, company.id, lang)
    summary = books.audit_summary(flags)
    budget = books.budget_status(db, company, month, lang, create_alerts=False)
    reval = books.revaluation(db, company, lang)
    readiness = finance.loan_readiness(db, company, lang, flags)
    sales = sales_summary(db, company.id, today)

    unread = list(db.scalars(select(Alert).where(alert_svc.visible_filter(company), alert_svc.unread_filter(company))
                             .order_by(Alert.id.desc()).limit(3)))
    if len(unread) < 3:
        seen = {a.id for a in unread}
        unread += [a for a in db.scalars(select(Alert).where(alert_svc.visible_filter(company))
                                         .order_by(Alert.id.desc()).limit(6)) if a.id not in seen][:3 - len(unread)]
    deals = market.sourcing_radar(db, company.categories or [], 15, 7, 5)
    rfqs = list(db.scalars(select(Rfq).where(Rfq.status == "open", Rfq.company_id != company.id,
                                             Rfq.category.in_(company.categories or []))
                           .order_by(Rfq.id.desc()).limit(5)))
    recent = list(db.scalars(select(Deal).where(or_(Deal.buyer_id == company.id, Deal.seller_id == company.id))
                             .order_by(Deal.id.desc()).limit(5)))
    decision_cards = [decision_out(d, lang) for d in pending]
    if decision_cards:
        top = max(decision_cards, key=lambda d: d.amount_uzs)
        insight = t("dash.insight.decision", lang, n=len(decision_cards), title=top.title,
                    amount=fmt_uzs(top.amount_uzs, lang))
    else:
        insight = t("dash.insight.sales", lang, today=fmt_uzs(sales["today_uzs"], lang),
                    avg=fmt_uzs(sales["avg_daily_uzs"], lang))
    return TodayDashboardOut(
        kpis=DashboardKpis(month=month, income_uzs=cur["income_uzs"], expenses_uzs=cur["expense_uzs"],
                           net_uzs=cur["net_uzs"], budget_used_pct=budget["used_pct"],
                           audit_issues=summary["issues"], money_at_risk_uzs=summary["amount_at_risk_uzs"],
                           inventory_market_value_uzs=reval["market_value_uzs"],
                           loan_readiness_score=readiness["score"], loan_readiness_grade=readiness["grade"]),
        alerts=[alert_out(db, company, a, lang) for a in unread],
        sourcing_deals=[listing_out(x) for x in deals],
        open_rfqs=[rfq_out(db, r, company) for r in rfqs],
        recent_deals=[deal_out(db, d, company) for d in recent],
        cashflow=cf,
        decisions=decision_cards[:5],
        stock={**stock.summary(stock.units(db, company, lang)), "aging_days": stock.AGING_DAYS},
        today=today,
        fx_usd_uzs=fx.rate(),
        insight=insight,
        sales=SalesSummary(**sales),
        avg_net_uzs=round(finance.avg_net(db, company.id, today)),
        budget=BudgetSummary(month=month, planned_total_uzs=budget["planned_total_uzs"],
                             fact_total_uzs=budget["fact_total_uzs"], used_pct=budget["used_pct"],
                             warning=(budget["explanations"] or [None])[0]),
        credit=CreditSummary(score=readiness["score"], grade=readiness["grade"]),
        price_index=PriceIndex(**index) if (index := price_index(db, company)) else None,
        rfq_quotes=RfqQuotesSummary(**quotes) if (quotes := rfq_quotes(db, company)) else None,
    )
