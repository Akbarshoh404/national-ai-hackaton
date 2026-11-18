"""`/dashboard`: everything the home screen needs in one call."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from sqlalchemy import or_, select

from app.api.routers.alerts import alert_out
from app.api.routers.decisions import decision_out
from app.api.routers.exchange import deal_out, rfq_out
from app.api.routers.market import listing_out
from app.api.schemas.advisor import DashboardKpis, DashboardOut
from app.core import alerts as alert_svc
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.models import Alert, Deal, Rfq
from app.intelligence.advisor import finance
from app.intelligence.books import books, decisions
from app.intelligence.market import market, stock

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard_get(db: DbDep, company: CompanyDep, lang: LangDep) -> DashboardOut:
    """KPIs, top alerts, sourcing deals, open RFQs, recent deals and a 6-month cash-flow series."""
    month = date.today().strftime("%Y-%m")
    decisions.ensure_built(db, company)
    pending = decisions.pending(db, company)
    cf = finance.cashflow(db, company.id, 6)
    cur = cf[-1]
    flags = books.audit_flags(db, company.id, lang)
    summary = books.audit_summary(flags)
    budget = books.budget_status(db, company, month, lang, create_alerts=False)
    reval = books.revaluation(db, company, lang)
    readiness = finance.loan_readiness(db, company, lang, flags)

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
    return DashboardOut(
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
        decisions=[decision_out(d, lang) for d in pending[:5]],
        stock=stock.summary(stock.units(db, company, lang)),
    )
