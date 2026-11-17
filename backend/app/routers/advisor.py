"""AI Advisor (#20): chat, cash flow, credit, tax, loan readiness, expansion, business plan."""

from __future__ import annotations

from typing import Literal

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
from app.services import copilot, finance

router = APIRouter(prefix="/advisor", tags=["advisor (#20)"])


@router.post("/chat", response_model=ChatOut)
def advisor_chat(body: ChatIn, db: DbDep, company: CompanyDep, lang: LangDep) -> ChatOut:
    """Copilot: intent router → Python tool → typed blocks + chips; a ≤2-sentence answer in the user's language."""
    ctx = copilot.context_from_ids(db, company, body.context.model_dump() if body.context else {})
    out = copilot.answer(db, company, body.question, [h.model_dump() for h in body.history], ctx, lang)
    out["used_data"] = sorted({*out["used_data"], *USED_DATA.get(out["intent"], [])})
    return ChatOut(**out)


#: legacy `used_data` keys per intent (v1 clients read these)
USED_DATA = {"credit": ["loan_readiness", "max_affordable_loan_uzs"], "tax": ["tax"], "budget": ["budget"],
             "audit": ["audit"], "cashflow": ["cashflow"], "price": ["market"], "stock": ["inventory"],
             "loan_readiness": ["loan_readiness"], "overview": ["cashflow", "audit", "loan_readiness"]}


@router.get("/cashflow", response_model=CashflowOut)
def advisor_cashflow(db: DbDep, company: CompanyDep, months: int = Query(6, ge=1, le=24)) -> CashflowOut:
    return CashflowOut(months=finance.cashflow(db, company.id, months),
                       avg_monthly_net_uzs=round(finance.avg_net(db, company.id)))


@router.post("/credit", response_model=CreditOut)
def advisor_credit(body: CreditIn, db: DbDep, company: CompanyDep, lang: LangDep) -> CreditOut:
    """Annuity payment, total interest, affordability and the max loan."""
    return CreditOut(**finance.credit(db, company, body.principal_uzs, body.months, body.annual_rate_pct, lang,
                                      body.product, body.down_payment_pct, body.asset_value_uzs))


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


@router.get("/business-plan", response_class=HTMLResponse,
            responses={200: {"content": {"text/html": {}, "application/pdf": {}}}})
def advisor_business_plan_get(db: DbDep, company: CompanyDep, lang: LangDep,
                              loan_amount_uzs: float = Query(gt=0), loan_months: int = Query(24, ge=1, le=120),
                              purpose: str = Query("Aylanma mablag'", min_length=3),
                              format: Literal["html", "pdf"] = "html") -> Response:
    """Same plan as POST, as a linkable URL (used by copilot `file` blocks)."""
    plan = finance.business_plan(db, company, loan_amount_uzs, loan_months, purpose, None, lang)
    doc = finance.render_plan_html(plan)
    if format == "pdf" and (pdf := finance.render_pdf(doc)) is not None:
        return Response(pdf, media_type="application/pdf")
    return HTMLResponse(doc)


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
