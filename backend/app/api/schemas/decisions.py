"""Decisions queue schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import UTCDateTime

DecisionType = Literal["reprice", "duplicate_invoice", "typo_amount", "overpayment", "budget_limit", "deal_to_buy",
                       "slow_stock", "rfq_quote"]


class DecisionAction(BaseModel):
    kind: str = Field(description="What Approve does: reprice, list_on_exchange, delete_transactions, "
                                  "correct_total, supplier_alert, watch, acknowledge, open_quote_form")
    endpoint: str | None = Field(None, description="Related endpoint the frontend may open (informational)")
    method: str | None = None
    body: dict[str, Any]


class DecisionOut(BaseModel):
    id: int
    type: DecisionType
    title: str
    message: str
    amount_uzs: float = Field(description="Money saved, at risk or recovered (computed in Python)")
    status: Literal["pending", "approved", "ignored", "expired"]
    reasons: list[str]
    transaction_ids: list[int]
    inventory_ids: list[int]
    action: DecisionAction
    created_at: UTCDateTime
    resolved_at: UTCDateTime | None


class DecisionResult(BaseModel):
    decision_id: int
    type: str
    status: str
    result: dict[str, Any]
