"""AI Advisor (#20): chat, cash flow, credit, tax, loan readiness, expansion, business plan."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, Response

from app.deps import CompanyDep, DbDep, LangDep
from app.schemas.advisor import (
    BusinessPlanIn,
    BusinessPlanOut,
    CashflowOut,
    ChatIn,
    ChatOut,
    CreditIn,
    CreditOut,
    ExpansionIn,
    ExpansionOut,
    LoanReadinessOut,
    TaxOut,
)
from app.services import finance

router = APIRouter(prefix="/advisor", tags=["advisor (#20)"])


@router.post("/chat", response_model=ChatOut)
def advisor_chat(body: ChatIn, db: DbDep, company: CompanyDep, lang: LangDep) -> ChatOut:
    """Answers from the company's own numbers, in the user's language (uz/ru/en)."""
    return ChatOut(**finance.chat(db, company, body.question, [h.model_dump() for h in body.history], lang))


@router.get("/cashflow", response_model=CashflowOut)
def advisor_cashflow(db: DbDep, company: CompanyDep, months: int = Query(6, ge=1, le=24)) -> CashflowOut:
    return CashflowOut(months=finance.cashflow(db, company.id, months),
                       avg_monthly_net_uzs=round(finance.avg_net(db, company.id)))


@router.post("/credit", response_model=CreditOut)
def advisor_credit(body: CreditIn, db: DbDep, company: CompanyDep, lang: LangDep) -> CreditOut:
    """Annuity payment, total interest, affordability and the max loan."""
    return CreditOut(**finance.credit(db, company, body.principal_uzs, body.months, body.annual_rate_pct, lang))


@router.get("/tax", response_model=TaxOut)
def advisor_tax(db: DbDep, company: CompanyDep, lang: LangDep) -> TaxOut:
    """Turnover tax vs VAT + profit tax for the last 3 months (rates: VERIFY with soliq.uz)."""
    return TaxOut(**finance.tax(db, company, lang))


@router.get("/loan-readiness", response_model=LoanReadinessOut)
def advisor_loan_readiness(db: DbDep, company: CompanyDep, lang: LangDep) -> LoanReadinessOut:
    return LoanReadinessOut(**finance.loan_readiness(db, company, lang))


@router.post("/expansion", response_model=ExpansionOut)
def advisor_expansion(body: ExpansionIn, db: DbDep, company: CompanyDep, lang: LangDep) -> ExpansionOut:
    """Expansion planner: stock plan (goods) or best rental yields (house/rent)."""
    return ExpansionOut(**finance.expansion(db, company, body.category, body.budget_uzs, body.district, lang))


@router.post("/business-plan", response_model=BusinessPlanOut,
             responses={200: {"content": {"text/html": {}, "application/pdf": {}},
                              "description": "JSON, HTML or PDF depending on `format`"}})
def advisor_business_plan(body: BusinessPlanIn, db: DbDep, company: CompanyDep, lang: LangDep):
    """Bank-ready business plan. `format`: html (default), pdf (falls back to HTML) or json."""
    plan = finance.business_plan(db, company, body.loan_amount_uzs, body.loan_months, body.purpose,
                                 body.expansion.model_dump() if body.expansion else None, lang)
    if body.format == "json":
        return BusinessPlanOut(**plan)
    doc = finance.render_plan_html(plan)
    if body.format == "pdf":
        pdf = finance.render_pdf(doc)
        if pdf is not None:
            return Response(pdf, media_type="application/pdf",
                            headers={"Content-Disposition": 'attachment; filename="business_plan.pdf"'})
        return HTMLResponse(doc, headers={"X-PDF-Fallback": "weasyprint-not-installed"})
    return HTMLResponse(doc)
