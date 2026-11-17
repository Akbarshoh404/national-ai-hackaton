"""Advisor (#20) and dashboard schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.alerts import AlertOut
from app.schemas.common import Category
from app.schemas.decisions import DecisionOut
from app.schemas.exchange import DealOut, RfqOut
from app.schemas.market import ListingOut, RentalYieldOut
from app.schemas.stock import StockSummary


class CashflowMonth(BaseModel):
    month: str
    income_uzs: float
    expense_uzs: float
    net_uzs: float
    partial: bool = Field(description="True for the current, incomplete month")


class CashflowOut(BaseModel):
    months: list[CashflowMonth]
    avg_monthly_net_uzs: float = Field(description="Average over the last 3 complete months")


class CreditIn(BaseModel):
    principal_uzs: float = Field(gt=0)
    months: int = Field(ge=1, le=120)
    annual_rate_pct: float | None = Field(None, ge=0, le=100)


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


class ExpansionIn(BaseModel):
    category: Category
    budget_uzs: float = Field(gt=0)
    district: str | None = None


class ExpansionLine(BaseModel):
    model: str
    condition: str | None
    attrs: dict[str, Any]
    market_listings: int
    units: int
    buy_price_uzs: float
    sell_price_uzs: float
    unit_margin_uzs: float
    monthly_gross_profit_uzs: float
    basis: str
    confidence: str


class ExpansionOut(BaseModel):
    category: str
    budget_uzs: float
    setup_cost_uzs: float
    opex_reserve_uzs: float
    stock_budget_uzs: float
    stock_invested_uzs: float
    stock_turns_per_month: float
    monthly_gross_profit_uzs: float
    monthly_opex_uzs: float
    monthly_net_profit_uzs: float
    break_even_months: float | None
    lines: list[ExpansionLine]
    yield_options: list[RentalYieldOut]
    assumptions: list[str]


class BusinessPlanIn(BaseModel):
    loan_amount_uzs: float = Field(gt=0)
    loan_months: int = Field(ge=1, le=120)
    purpose: str = Field(min_length=3, max_length=1000)
    expansion: ExpansionIn | None = None
    format: Literal["html", "pdf", "json"] = "html"


class BusinessPlanOut(BaseModel):
    company: dict[str, Any]
    generated_on: date
    language: str
    purpose: str
    executive_summary: str
    summary_source: Literal["llm", "rules"]
    financials: list[CashflowMonth]
    inventory: dict[str, Any]
    loan: CreditOut
    expansion: ExpansionOut | None
    loan_readiness: LoanReadinessOut
    tax: TaxOut
    audit_summary: dict[str, Any]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)


class ChatOut(BaseModel):
    answer: str
    used_data: list[str] = Field(description="Context sections the answer is based on")
    language: Literal["uz", "ru", "en"]
    source: Literal["llm", "rules"]


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
