"""B2B exchange schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import ORM, Category, UTCDateTime
from app.api.schemas.market import PriceEstimateOut

OfferKind = Literal["wholesale", "surplus", "car_trade", "cobroker"]


class RfqIn(BaseModel):
    category: Category
    brand: str | None = None
    model: str | None = Field(None, description="Required for phone/laptop/car")
    condition: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    qty: int = Field(ge=1, le=100000)
    target_unit_price: float | None = Field(None, gt=0, description="UZS")
    district: str | None = None
    deadline: date | None = None
    note: str | None = None


class RfqOut(ORM):
    id: int
    company_id: int
    company_name: str = ""
    category: str
    brand: str | None
    model: str
    condition: str | None
    attrs: dict[str, Any]
    qty: int
    target_unit_price: float | None
    district: str | None
    deadline: date | None
    note: str | None
    status: str
    created_at: UTCDateTime
    quotes_count: int = 0
    my_quote_id: int | None = None


class RfqCreated(BaseModel):
    rfq: RfqOut
    market: PriceEstimateOut | None
    notified_companies: int


class QuoteIn(BaseModel):
    unit_price: float = Field(gt=0, description="UZS per unit")
    qty: int = Field(ge=1)
    delivery_days: int = Field(ge=0, le=365)
    note: str | None = None


class QuoteOut(ORM):
    id: int
    rfq_id: int
    supplier_id: int
    unit_price: float
    qty: int
    delivery_days: int
    note: str | None
    status: str
    counter_unit_price: float | None = None
    counter_note: str | None = None
    created_at: UTCDateTime


class SupplierRef(BaseModel):
    id: int
    name: str
    rating: float | None
    ratings_count: int
    deals_count: int


class ScoreBreakdown(BaseModel):
    price: float
    rating: float
    delivery: float
    quantity: float
    penalty: float


class RankedQuote(BaseModel):
    id: int
    rfq_id: int
    rank: int
    supplier: SupplierRef
    unit_price_uzs: float
    qty: int
    delivery_days: int
    note: str | None
    status: str
    counter_unit_price: float | None = None
    counter_note: str | None = None
    score: float
    score_breakdown: ScoreBreakdown
    vs_fair_purchase_pct: float | None = Field(None, description="vs market fair purchase price; negative = cheaper")
    reasons: list[str]


class Recommendation(BaseModel):
    quote_id: int
    supplier_name: str
    score: float
    saving_vs_worst_uzs: float
    text: str


class RankedQuotes(BaseModel):
    rfq_id: int
    fair_price_uzs: float | None
    fair_buy_price_uzs: float | None
    quotes: list[RankedQuote]
    recommendation: Recommendation | None


class DealOut(ORM):
    id: int
    buyer_id: int
    seller_id: int
    buyer_name: str = ""
    seller_name: str = ""
    rfq_id: int | None
    quote_id: int | None
    offer_id: int | None
    category: str
    brand: str | None
    model: str
    condition: str | None
    attrs: dict[str, Any]
    qty: int
    unit_price: float
    total: float
    status: str
    created_at: UTCDateTime
    my_rating: int | None = None


class OfferIn(BaseModel):
    kind: OfferKind
    category: Category
    brand: str | None = None
    model: str | None = None
    condition: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    qty: int = Field(1, ge=1)
    unit_price: float = Field(gt=0, description="UZS per unit")
    district: str | None = None
    commission_split: float | None = Field(None, ge=0, le=1, description="Share of commission offered to partner")
    note: str | None = None


class OfferOut(BaseModel):
    id: int
    company: SupplierRef
    kind: str
    category: str
    brand: str | None
    model: str
    title: str
    condition: str | None
    attrs: dict[str, Any]
    qty: int
    unit_price_uzs: float
    district: str | None
    commission_split: float | None
    note: str | None
    status: str
    created_at: UTCDateTime
    market_fair_price_uzs: float | None
    market_diff_pct: float | None = Field(None, description="Negative = below market")
    market_badge: str | None


class OfferMatch(OfferOut):
    match_reasons: list[str]


class BuyIn(BaseModel):
    qty: int = Field(ge=1)


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class RatingOut(ORM):
    id: int
    deal_id: int
    rater_id: int
    ratee_id: int
    score: int
    comment: str | None


class DemandRequested(BaseModel):
    category: str
    model: str
    requests: int
    units: int


class DemandListed(BaseModel):
    category: str
    model: str
    listings: int
    avg_price_uzs: float


class DemandDistrict(BaseModel):
    district: str
    category: str
    model: str
    requests: int
    units: int


class DemandOut(BaseModel):
    days: int
    most_requested: list[DemandRequested]
    most_listed: list[DemandListed]
    by_district: list[DemandDistrict] = []


class CounterIn(BaseModel):
    unit_price: float = Field(gt=0, description="Buyer's counter price (UZS per unit)")
    note: str | None = None


class RespondIn(BaseModel):
    accept: bool
    unit_price: float | None = Field(None, gt=0, description="When not accepting: the supplier's final price")
