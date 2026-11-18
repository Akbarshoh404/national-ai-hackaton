"""Copilot answer blocks: a discriminated union on `type`. Every number inside is computed by a Python tool."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class PriceRangeBlock(BaseModel):
    type: Literal["price_range"] = "price_range"
    title: str
    fair_uzs: float
    p25_uzs: float
    p75_uzs: float
    your_price_uzs: float | None = None
    buy_price_uzs: float | None = None
    currency: str = "UZS"
    basis: str
    comparables: int
    confidence: str


class Sample(BaseModel):
    title: str
    price_uzs: float
    condition: str | None = None
    district: str | None = None
    seller_type: str | None = None
    posted_at: str | None = None
    source_url: str | None = None


class ComparablesBlock(BaseModel):
    type: Literal["comparables"] = "comparables"
    title: str
    samples: list[Sample]


class Kpi(BaseModel):
    label: str
    value_uzs: float | None = None
    value: float | str | None = None
    delta_pct: float | None = None


class KpiRowBlock(BaseModel):
    type: Literal["kpi_row"] = "kpi_row"
    title: str
    items: list[Kpi] = Field(min_length=1, max_length=4)


class Series(BaseModel):
    name: str
    values: list[float | None]


class BarChartBlock(BaseModel):
    type: Literal["bar_chart"] = "bar_chart"
    title: str
    x: list[str]
    series: list[Series]
    unit: str = "UZS"


class LineChartBlock(BaseModel):
    type: Literal["line_chart"] = "line_chart"
    title: str
    x: list[str]
    series: list[Series]
    unit: str = "UZS"


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str
    columns: list[str]
    rows: list[list[Any]]
    row_ids: list[int] | None = Field(None, description="inventory/transaction/quote ids, row-aligned")


class Step(BaseModel):
    label: str
    status: Literal["done", "todo"]
    detail: str | None = None


class StepsBlock(BaseModel):
    type: Literal["steps"] = "steps"
    title: str
    steps: list[Step]


class ScheduleItem(BaseModel):
    month: int
    payment_uzs: float
    principal_uzs: float
    interest_uzs: float
    balance_uzs: float


class LoanScheduleBlock(BaseModel):
    type: Literal["loan_schedule"] = "loan_schedule"
    title: str
    principal_uzs: float
    months: int
    annual_rate_pct: float
    monthly_payment_uzs: float
    total_interest_uzs: float
    rows: list[ScheduleItem] = Field(description="First 12 months")


class FileBlock(BaseModel):
    type: Literal["file"] = "file"
    title: str
    url: str
    mime: str


Block = Annotated[PriceRangeBlock | ComparablesBlock | KpiRowBlock | BarChartBlock | LineChartBlock | TableBlock
                  | StepsBlock | LoanScheduleBlock | FileBlock, Field(discriminator="type")]


class ChipAction(BaseModel):
    endpoint: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    body: dict[str, Any] | None = None


class Chip(BaseModel):
    label: str
    action: ChipAction
