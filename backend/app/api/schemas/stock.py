"""Stock command center schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Rating = Literal["underpriced", "fair", "overpriced", "no_data"]


class StockUnit(BaseModel):
    inventory_id: int
    store_id: int | None
    category: str
    brand: str | None
    model: str
    condition: str | None
    attrs: dict[str, Any]
    identifier: str | None
    qty: int
    list_price_uzs: float | None
    unit_cost_uzs: float
    days_in_stock: int
    fair_price_uzs: float | None
    range_uzs: list[float] | None = Field(None, description="[p25, p75]")
    fair_buy_price_uzs: float | None
    confidence: str | None
    comparables: int
    basis: str | None
    rating: Rating
    vs_market_pct: float | None
    margin_at_list_uzs: float | None
    expected_days_to_sell: float | None
    days_basis: str
    suggested_price_uzs: float | None
    suggested_action: Literal["reprice_down", "reprice_up", "list_on_exchange", "keep"]
    reasons: list[str]


class StockSummary(BaseModel):
    stock_value_cost_uzs: float
    stock_value_market_uzs: float
    units_total: int
    units_overpriced: int
    units_underpriced: int
    units_no_data: int
    units_older_30d: int
    units_older_slow: int
    slow_stock_days: int
    overpricing_at_risk_uzs: float = Field(description="Σ (list − suggested) on overpriced units")
    aging_cash_tied_uzs: float = Field(description="Cash tied up in units older than SLOW_STOCK_DAYS")
    margin_at_risk_uzs: float
    aging_days: int = Field(description="`units_older_30d` and `aging_only` count units older than this")


class RepriceItem(BaseModel):
    inventory_id: int
    new_price_uzs: float = Field(gt=0)


class RepriceIn(BaseModel):
    items: list[RepriceItem] | None = None
    inventory_ids: list[int] | None = None
    use_suggested: bool = False

    @model_validator(mode="after")
    def _one_mode(self) -> RepriceIn:
        if not self.items and not (self.inventory_ids and self.use_suggested):
            raise ValueError("send either items[] or inventory_ids[] with use_suggested=true")
        return self


class RepriceOut(BaseModel):
    updated: int
    units: list[StockUnit]


class ListOnExchangeIn(BaseModel):
    inventory_ids: list[int] = Field(min_length=1)
    unit_price_uzs: float | None = Field(None, gt=0, description="Default: each unit's suggested price")
