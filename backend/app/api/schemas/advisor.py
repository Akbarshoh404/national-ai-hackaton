"""Advisor (#20) and dashboard schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.alerts import AlertOut
from app.api.schemas.blocks import Block, Chip
from app.api.schemas.decisions import DecisionOut
from app.api.schemas.exchange import DealOut, RfqOut
from app.api.schemas.market import ListingOut
from app.api.schemas.stock import StockSummary


class CashflowMonth(BaseModel):
    month: str
    income_uzs: float
    expense_uzs: float
    net_uzs: float
    partial: bool = Field(description="True for the current, incomplete month")


class CashflowOut(BaseModel):
    months: list[CashflowMonth]
    avg_monthly_net_uzs: float = Field(description="Average over the last 3 complete months")


CreditProduct = Literal["business_loan", "auto_loan", "mortgage", "leasing"]


class CreditIn(BaseModel):
    principal_uzs: float | None = Field(None, gt=0, description="Required unless asset_value_uzs is given")
    months: int = Field(ge=1, le=360)
    annual_rate_pct: float | None = Field(None, ge=0, le=100, description="Default: the product rate")
    product: CreditProduct = "business_loan"
    down_payment_pct: float | None = Field(None, ge=0, lt=1, description="Asset loans (mortgage, auto_loan)")
    asset_value_uzs: float | None = Field(None, gt=0, description="Asset loans: apartment / car stock value")


class ScheduleRow(BaseModel):
    month: int
    payment_uzs: float
    principal_uzs: float
    interest_uzs: float
    balance_uzs: float


class CreditOut(BaseModel):
    principal_uzs: float
    months: int
    annual_rate_pct: float
    monthly_payment_uzs: float
    total_payment_uzs: float
    total_interest_uzs: float
    avg_monthly_net_uzs: float
    debt_service_ratio_pct: float | None
    max_debt_service_ratio_pct: float
    affordable: bool
    max_loan_uzs: float
    max_loan_by_term: dict[str, float]
    verdict: str
    rate_note: str
    product: str = "business_loan"
    down_payment_pct: float | None = None
    down_payment_uzs: float | None = None
    asset_value_uzs: float | None = None
    ltv: float | None = Field(None, description="Loan-to-value for asset loans")
    schedule: list[ScheduleRow] = []


class TurnoverRegime(BaseModel):
    rate_pct: float
    tax_uzs: float


class VatRegime(BaseModel):
    vat_rate_pct: float
    profit_tax_rate_pct: float
    output_vat_uzs: float
    input_vat_uzs: float
    vat_payable_uzs: float
    taxable_profit_uzs: float
    profit_tax_uzs: float
    total_uzs: float


class TaxOut(BaseModel):
    months: list[str]
    turnover_uzs: float
    expenses_uzs: float
    turnover_regime: TurnoverRegime
    vat_regime: VatRegime
    current_regime: str
    cheaper_regime: Literal["turnover", "vat"]
    saving_uzs: float
    explanation: str
    rates_verified: bool
    disclaimer: str


class LoanFactor(BaseModel):
    key: str
    label: str
    points: float
    max_points: int
    explanation: str


class LoanReadinessOut(BaseModel):
    score: int = Field(ge=0, le=100)
    grade: Literal["A", "B", "C", "D"]
    factors: list[LoanFactor]
    how_to_improve: list[str]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatContext(BaseModel):
    screen: Literal["stock", "books", "budget", "exchange", "advisor"] | None = None
    inventory_ids: list[int] | None = None
    transaction_ids: list[int] | None = None
    rfq_id: int | None = None


ChatScreen = Literal["stock", "books", "budget", "exchange", "advisor"]


class ChatSuggestion(BaseModel):
    question: str
    intent: str = Field(description="Tool the keyword router sends this question to")


class ChatSuggestionsOut(BaseModel):
    screen: ChatScreen | None
    questions: list[ChatSuggestion]


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)
    context: ChatContext | None = None


class ChatOut(BaseModel):
    answer: str = Field(description="At most 2 sentences")
    used_data: list[str] = Field(description="Context sections the answer is based on")
    language: Literal["uz", "ru", "en"]
    source: Literal["llm", "rules"]
    intent: str = "overview"
    intent_source: Literal["rules", "context", "local", "llm", "default"] = "rules"
    blocks: list[Block] = Field(default_factory=list, description="Typed answer blocks built by Python tools")
    chips: list[Chip] = Field(default_factory=list, description="2–3 next steps the frontend can run")


class DashboardKpis(BaseModel):
    month: str
    income_uzs: float
    expenses_uzs: float
    net_uzs: float
    budget_used_pct: float | None
    audit_issues: int
    money_at_risk_uzs: float
    inventory_market_value_uzs: float
    loan_readiness_score: int
    loan_readiness_grade: str


class DashboardOut(BaseModel):
    kpis: DashboardKpis
    alerts: list[AlertOut]
    sourcing_deals: list[ListingOut]
    open_rfqs: list[RfqOut]
    recent_deals: list[DealOut]
    cashflow: list[CashflowMonth]
    decisions: list[DecisionOut] = Field(default_factory=list, description="Top 5 pending decisions")
    stock: StockSummary | None = None
