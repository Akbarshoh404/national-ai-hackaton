"""Books (#26 auditor, #25 budget) schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.api.schemas.common import ORM, Category, Severity, UTCDateTime
from app.core.catalog import EXPENSE_CATEGORIES, INCOME_CATEGORIES

TxType = Literal["income", "expense"]


class TransactionIn(BaseModel):
    date: date
    type: TxType
    category: str = Field(description="Expense or income category (see /meta)")
    item_category: Category | None = None
    brand: str | None = None
    model: str | None = None
    condition: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    qty: float = Field(1, gt=0)
    unit_price: float | None = Field(None, ge=0)
    total: float = Field(gt=0)
    counterparty: str | None = None
    note: str | None = None
    store_id: int | None = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in EXPENSE_CATEGORIES and v not in INCOME_CATEGORIES:
            raise ValueError("unknown category")
        return v


class TransactionOut(ORM):
    id: int
    date: date
    type: str
    category: str
    item_category: str | None
    brand: str | None
    model: str | None
    condition: str | None
    attrs: dict[str, Any]
    qty: float
    unit_price: float | None
    total: float
    counterparty: str | None
    note: str | None
    origin: str
    deal_id: int | None
    store_id: int | None = None
    created_at: UTCDateTime


class UploadError(BaseModel):
    row: int
    error: str


class UploadResult(BaseModel):
    created: int
    errors: list[UploadError]


class ColumnMapping(BaseModel):
    field: str | None
    confidence: float


class UploadPreview(BaseModel):
    columns: list[str]
    mapping: dict[str, ColumnMapping] = Field(description="Proposed {source column: field} with confidence")
    fields: list[str] = Field(description="Allowed target fields")
    total_rows: int
    rows: list[TransactionIn] = Field(description="First 10 parsed rows")
    errors: list[UploadError]


class InvoiceResult(BaseModel):
    committed: bool
    extracted: list[TransactionIn]
    created_ids: list[int]


class AuditFlag(BaseModel):
    type: Literal["duplicate", "qty_mismatch", "extra_zero", "price_spread", "cost_spike", "overpayment",
                  "no_counterparty"]
    severity: Severity
    message: str
    transaction_ids: list[int]
    amount_at_risk_uzs: float
    fair_buy_price_uzs: float | None = None


class AuditSummary(BaseModel):
    issues: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    amount_at_risk_uzs: float


class AuditOut(BaseModel):
    summary: AuditSummary
    flags: list[AuditFlag]
    recommendations: list[str]
    recommendations_source: Literal["llm", "rules"]


class BenchmarkCategory(BaseModel):
    category: str
    mine_uzs: float
    peer_median_uzs: float
    diff_pct: float | None
    percentile: float


class BenchmarkOut(BaseModel):
    role: str
    peers: int
    enough_peers: bool = Field(description="Comparison needs at least 3 peers")
    my_monthly_opex_uzs: float | None
    percentile: float | None = Field(None, description="% of peers spending less than you (lower is better)")
    peer_median_uzs: float | None
    peer_p25_uzs: float | None
    peer_p75_uzs: float | None
    categories: list[BenchmarkCategory]


class BudgetIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    items: dict[str, float]


class BudgetTx(BaseModel):
    id: int
    date: date
    total_uzs: float
    counterparty: str | None
    note: str | None


class BudgetItem(BaseModel):
    category: str
    planned_uzs: float | None
    fact_uzs: float
    used_pct: float | None
    forecast_uzs: float
    status: Literal["ok", "at_risk", "over", "no_plan"]
    explanation: str | None
    top_transactions: list[BudgetTx]


class BudgetOut(BaseModel):
    month: str
    days_elapsed: int
    days_in_month: int
    items: list[BudgetItem]
    planned_total_uzs: float
    fact_total_uzs: float
    forecast_total_uzs: float
    used_pct: float | None
    explanations: list[str]


class InventoryIn(BaseModel):
    category: Category
    brand: str | None = None
    model: str
    condition: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    district: str | None = None
    qty: int = Field(1, ge=1)
    unit_cost: float = Field(gt=0)
    acquired_at: date | None = None
    list_price_uzs: float | None = Field(None, gt=0)
    identifier: str | None = Field(None, description="IMEI or VIN (unique per company)")
    store_id: int | None = None


class InventoryOut(ORM):
    id: int
    category: str
    brand: str | None
    model: str
    condition: str | None
    attrs: dict[str, Any]
    district: str | None
    qty: int
    unit_cost: float
    acquired_at: date
    status: str
    list_price_uzs: float | None = None
    identifier: str | None = None
    store_id: int | None = None


class SlowStockItem(BaseModel):
    inventory_id: int
    category: str
    brand: str | None
    model: str
    condition: str | None
    attrs: dict[str, Any]
    qty: int
    age_days: int
    unit_cost_uzs: float
    cash_tied_uzs: float
    fair_price_uzs: float | None
    suggested_surplus_price_uzs: float | None
    loss_vs_cost_uzs: float
    advice: str


class SlowStockOut(BaseModel):
    threshold_days: int
    units: int
    cash_tied_uzs: float
    items: list[SlowStockItem]


class RevaluationItem(BaseModel):
    inventory_id: int
    category: str
    brand: str | None
    model: str
    condition: str | None
    qty: int
    unit_cost_uzs: float
    market_value_per_unit_uzs: float | None
    market_value_uzs: float | None
    unrealized_margin_uzs: float | None
    margin_pct: float | None
    basis: str | None
    advice: str


class RevaluationOut(BaseModel):
    total_cost_uzs: float
    market_value_uzs: float
    unrealized_margin_uzs: float
    items: list[RevaluationItem]
