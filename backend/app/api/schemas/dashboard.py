"""Home-screen ("Bugun") additions to `/dashboard`, and the `/search` result shape."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.advisor import DashboardOut


class SalesDayOut(BaseModel):
    date: dt.date
    total_uzs: float


class SalesSummary(BaseModel):
    today_uzs: float
    yesterday_uzs: float
    delta_uzs: float
    delta_pct: float | None = Field(description="None when yesterday had no sales")
    avg_daily_uzs: float = Field(description="Average daily sales over the 30 days before today (zero days count)")
    days: list[SalesDayOut] = Field(description="Daily `sale` income, last 90 days, oldest first")


class BudgetSummary(BaseModel):
    month: str
    planned_total_uzs: float
    fact_total_uzs: float
    used_pct: float | None
    warning: str | None = Field(description="First budget explanation (over / at risk), if any")


class CreditSummary(BaseModel):
    score: int
    grade: str


class PriceIndexPoint(BaseModel):
    week_start: dt.date
    median_usd: float
    p25_usd: float
    p75_usd: float
    listings: int


class PriceIndex(BaseModel):
    category: str
    model: str
    points: list[PriceIndexPoint] = Field(description="Weekly median and p25–p75 of listing prices, oldest first")
    change_pct: float | None = Field(description="Last week's median vs the week before")


class RfqQuoteRow(BaseModel):
    quote_id: int
    supplier_name: str
    unit_price_uzs: float
    delivery_days: int
    best: bool


class RfqQuotesSummary(BaseModel):
    rfq_id: int
    title: str
    qty: int
    quotes: list[RfqQuoteRow]


class TodayDashboardOut(DashboardOut):
    today: dt.date
    fx_usd_uzs: float
    insight: str = Field(description="One deterministic sentence built from the numbers below")
    sales: SalesSummary
    avg_net_uzs: float = Field(description="Average monthly net over the last 3 complete months")
    budget: BudgetSummary
    credit: CreditSummary
    price_index: PriceIndex | None
    rfq_quotes: RfqQuotesSummary | None = Field(description="The own open RFQ with the most quotes")


class SearchHit(BaseModel):
    kind: Literal["stock", "transaction", "counterparty", "decision"]
    id: int | None
    title: str
    subtitle: str


class SearchOut(BaseModel):
    q: str
    items: list[SearchHit]
