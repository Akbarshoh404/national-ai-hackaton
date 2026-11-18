"""Fast-input schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import Category
from app.api.schemas.market import ListingOut, PriceEstimateOut


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000, examples=["iphone 13 pro 256 87% korobka bor"])
    category_hint: Category | None = None


class ParsedItem(BaseModel):
    category: Category | None
    brand: str | None
    model: str | None
    condition: str | None
    district: str | None
    attrs: dict[str, Any]
    price: float | None = Field(None, description="Only when the text contains one")
    currency: Literal["USD", "UZS"] | None
    missing_fields: list[str]
    confidence: Literal["high", "medium", "low"]
    source: Literal["llm", "rules"]


class VoiceOut(BaseModel):
    transcript: str
    parsed: ParsedItem


class ImeiIn(BaseModel):
    imei: str = Field(min_length=8, max_length=20)


class ImeiOut(BaseModel):
    imei: str
    valid: bool = Field(description="15 digits with a correct Luhn check digit")
    tac: str | None
    brand: str | None
    model: str | None
    storage_options: list[int]
    category: str | None
    source: str = Field(description="demo_tac_table: a small local demo table, not a licensed TAC database")


class LinkIn(BaseModel):
    url: str = Field(examples=["https://t.me/mixmobiles/12345"])


class LinkPriceOut(BaseModel):
    listing: ListingOut
    estimate: PriceEstimateOut
    diff_pct: float = Field(description="Listing price vs market; negative = below")
    badge: str
    fetched: Literal["database", "telegram"]
