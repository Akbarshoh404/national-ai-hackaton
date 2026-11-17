"""Lender & bazaar console schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.advisor import CreditProduct
from app.schemas.common import ORM, Category, UTCDateTime
from app.schemas.market import PriceSample, TrendPoint


class ValuationIn(BaseModel):
    """One of: item parameters (as /market/price), `url` (t.me link) or `inventory_id` of an applicant."""

    category: Category | None = None
    brand: str | None = None
    model: str | None = None
    condition: str | None = None
    district: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None
    inventory_id: int | None = None


class ValuationOut(BaseModel):
    category: str
    qty: int
    fair_price_uzs: float
    fair_price_usd: float
    range_uzs: list[float]
    liquidation_value_uzs: float = Field(description="p25 × (1 − haircut)")
    haircut_pct: float
    total_market_value_uzs: float
    total_liquidation_value_uzs: float
    confidence: str
    comparables: int
    basis: str
    samples: list[PriceSample]
    source: dict[str, Any]
    valuations_this_month: int


class CollateralIn(BaseModel):
    borrower_name: str = Field(min_length=2, max_length=200)
    category: Literal["car", "house", "phone", "laptop"]
    brand: str | None = None
    model: str | None = None
    condition: str | None = None
    district: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    qty: int = Field(1, ge=1)
    loan_balance_uzs: float = Field(ge=0)
    ltv_limit: float = Field(0.7, gt=0, le=1.5)
    loan_application_id: int | None = None


class CollateralOut(BaseModel):
    id: int
    loan_application_id: int | None
    borrower_name: str
    category: str
    brand: str | None
    model: str | None
    condition: str | None
    district: str | None
    attrs: dict[str, Any]
    qty: int
    loan_balance_uzs: float
    ltv_limit: float
    market_value_uzs: float | None
    liquidation_value_uzs: float | None
    ltv: float | None
    status: Literal["ok", "watch", "breach", "no_data"]
    value_change_30d_pct: float | None
    basis: str | None
    confidence: str | None
    comparables: int
    created_at: UTCDateTime


class CollateralSummary(BaseModel):
    items: int
    total_loan_balance_uzs: float
    total_market_value_uzs: float
    total_liquidation_value_uzs: float
    portfolio_ltv: float | None
    by_status: dict[str, int]
    by_category: dict[str, float]
    valuations_this_month: int


class LoanApplicationIn(BaseModel):
    lender_id: int
    product: CreditProduct = "business_loan"
    principal_uzs: float = Field(gt=0)
    months: int = Field(ge=1, le=360)
    purpose: str = Field(min_length=3, max_length=1000)
    consent: bool = Field(description="Must be true: the borrower agrees to share the snapshot with the lender")
    collateral_inventory_ids: list[int] = Field(default_factory=list)


class LoanApplicationOut(ORM):
    id: int
    company_id: int
    company_name: str = ""
    lender_id: int
    lender_name: str = ""
    product: str
    principal_uzs: float
    months: int
    purpose: str
    status: Literal["submitted", "reviewing", "approved", "rejected"]
    decision_note: str | None
    readiness_score: int | None = None
    consent_at: UTCDateTime
    created_at: UTCDateTime


class LoanApplicationDetail(LoanApplicationOut):
    snapshot: dict[str, Any]
    business_plan_url: str


class ApplicationDecisionIn(BaseModel):
    status: Literal["reviewing", "approved", "rejected"]
    note: str | None = None


class ModelDistrictRow(BaseModel):
    model: str
    district: str
    listings: int
    median_price_uzs: float


class MarketReportOut(BaseModel):
    category: str
    district: str | None
    days: int
    total_listings: int
    by_model_district: list[ModelDistrictRow]
    weekly_trend: list[TrendPoint]
    by_seller_type: dict[str, int]


class LenderRef(BaseModel):
    id: int
    name: str
