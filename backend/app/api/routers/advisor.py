"""AI Advisor (#20): copilot chat, cash flow, credit, tax and loan readiness."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.schemas.advisor import (
    CashflowOut,
    ChatIn,
    ChatOut,
    ChatScreen,
    ChatSuggestionsOut,
    CreditIn,
    CreditOut,
    LoanReadinessOut,
    TaxOut,
)
from app.core.deps import CompanyDep, DbDep, LangDep
from app.intelligence.advisor import copilot, finance

router = APIRouter(prefix="/advisor", tags=["advisor (#20)"])


@router.post("/chat", response_model=ChatOut)
def advisor_chat(body: ChatIn, db: DbDep, company: CompanyDep, lang: LangDep) -> ChatOut:
    """Copilot: intent router → Python tool → typed blocks + chips; a ≤2-sentence answer in the user's language."""
    ctx = copilot.context_from_ids(db, company, body.context.model_dump() if body.context else {})
    out = copilot.answer(db, company, body.question, [h.model_dump() for h in body.history], ctx, lang)
    out["used_data"] = sorted({*out["used_data"], *USED_DATA.get(out["intent"], [])})
    return ChatOut(**out)


@router.get("/chat/suggestions", response_model=ChatSuggestionsOut)
def advisor_chat_suggestions(_: CompanyDep, lang: LangDep, screen: ChatScreen | None = None) -> ChatSuggestionsOut:
    """Starter questions for an empty copilot chat on a screen (each routes to a Python tool by keywords)."""
    return ChatSuggestionsOut(screen=screen, questions=copilot.suggestions(screen, lang))


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
