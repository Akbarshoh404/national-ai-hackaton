"""Market (#19) schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import ORM, ItemSpec, UTCDateTime


class ListingOut(ORM):
    id: int
    category: str
    brand: str | None
    model: str
    title: str = ""
    condition: str | None
    price: float
    currency: str
    price_uzs: float
    price_usd: float
    city: str | None
    district: str | None
    attrs: dict[str, Any]
    seller_type: str
    posted_at: UTCDateTime
    source_url: str | None
    origin: str
    fair_price_uzs: float | None = None
    discount_pct: float | None = Field(None, description="Positive = below fair price")
    expected_resale_margin_uzs: float | None = Field(None, description="Radar only: fair − price − handling")
    expected_days_to_sell: float | None = Field(None, description="Radar only: from your sales history")


class PriceSample(BaseModel):
    listing_id: int
    title: str
    price_uzs: float
    price_usd: float
    condition: str | None
    district: str | None
    seller_type: str | None
    posted_at: UTCDateTime
    source_url: str | None
    attrs: dict[str, Any]


class PriceRequest(ItemSpec):
    asking_price_uzs: float | None = Field(None, gt=0, description="Optional: compare a price to the market")


class AskingComparison(BaseModel):
    asking_price_uzs: float
    diff_pct: float = Field(description="Negative = below market")
    badge: str


class PriceEstimateOut(BaseModel):
    category: str
    fair_price_uzs: float
    fair_price_usd: float
    range_uzs: tuple[float, float] = Field(description="p25–p75 of comparables")
    fair_buy_price_uzs: float = Field(description="Trade-in / wholesale reference = fair × (1 − dealer margin)")
    fair_buy_price_usd: float
    comparables: int
    basis: str
    confidence: Literal["high", "medium", "low"]
    samples: list[PriceSample]
    price_by_seller_type: dict[str, float] | None = None
    per_m2_uzs: float | None = None
    asking: AskingComparison | None = None


class MarketStats(BaseModel):
    listings_per_category: dict[str, int]
    new_last_hour: dict[str, int]
    total_listings: int
    raw_pending: int
    raw_failed: int
    raw_done: int
    raw_skipped: int
    latest_post_at: UTCDateTime | None
    latest_telegram_post_at: UTCDateTime | None
    fx_usd_uzs: float


class TrendPoint(BaseModel):
    week_start: date
    median_price_uzs: float
    median_price_usd: float
    listings: int


class TrendOut(BaseModel):
    category: str
    model: str | None
    points: list[TrendPoint]
    change_pct: float | None = Field(None, description="Last week median vs first week median")


class ModelSuggestion(BaseModel):
    model_norm: str
    brand: str | None
    model: str
    listings: int


class RentalYieldRequest(BaseModel):
    district: str
    rooms: int = Field(ge=1, le=10)
    area_m2: float = Field(gt=10, le=1000)
    furnished: bool | None = None


class RentalYieldOut(BaseModel):
    district: str
    rooms: int
    area_m2: float
    apartment_price_uzs: float
    apartment_price_usd: float
    monthly_rent_uzs: float
    monthly_rent_usd: float
    gross_yield_pct: float
    net_yield_pct: float
    payback_years: float | None
    opex_ratio: float
    price_basis: str
    rent_basis: str
    price_comparables: int
    rent_comparables: int
    confidence: str
    assumptions: list[str]


class HeatmapCell(BaseModel):
    district: str
    listings: int
    median_uzs: float | None
    median_usd: float | None
    median_per_m2_uzs: float | None
    median_per_m2_usd: float | None


class HeatmapOut(BaseModel):
    category: Literal["house", "rent"]
    cells: list[HeatmapCell]
