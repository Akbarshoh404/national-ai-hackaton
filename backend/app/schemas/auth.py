"""Auth, company and meta schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.catalog import normalize_district
from app.schemas.common import ORM, Category, Role, UTCDateTime


class CompanyRegister(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    stir: str = Field(description="9-digit taxpayer number (STIR/INN)")
    role: Role
    categories: list[Category] = Field(min_length=1)
    city: str = "Toshkent"
    district: str | None = None
    tax_regime: Literal["turnover", "vat"] = "turnover"

    @field_validator("stir")
    @classmethod
    def _stir(cls, v: str) -> str:
        v = v.strip()
        if not (len(v) == 9 and v.isdigit()):
            raise ValueError("STIR must be exactly 9 digits")
        return v

    @field_validator("district")
    @classmethod
    def _district(cls, v: str | None) -> str | None:
        return normalize_district(v) or v if v else None


class CompanyUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    categories: list[Category] | None = None
    city: str | None = None
    district: str | None = None
    tax_regime: Literal["turnover", "vat"] | None = None


class Reputation(BaseModel):
    rating: float | None = Field(None, description="Average score 1–5, null if never rated")
    ratings_count: int
    deals_count: int


class CompanyOut(ORM):
    id: int
    slug: str | None
    name: str
    stir: str
    role: Role
    categories: list[str]
    city: str
    district: str | None
    tax_regime: str
    telegram_linked: bool = False
    created_at: UTCDateTime


class CompanyPublic(BaseModel):
    id: int
    name: str
    role: Role
    categories: list[str]
    city: str
    district: str | None
    reputation: Reputation


class RegisterResponse(BaseModel):
    api_key: str = Field(description="Shown once. Send as X-API-Key.")
    company: CompanyOut


class DemoLoginRequest(BaseModel):
    company_slug: str


class DemoCompany(BaseModel):
    slug: str
    name: str
    role: str


class LabelSet(BaseModel):
    uz: str
    ru: str
    en: str


class AttrField(BaseModel):
    name: str
    type: str
    unit: str | None
    options: list[str] | None
    label: LabelSet


class CodeLabel(BaseModel):
    code: str
    label: LabelSet


class CurrencyFormat(BaseModel):
    code: str
    symbol: str
    decimals: int
    thousands_separator: str
    symbol_position: Literal["before", "after"]


class MetaResponse(BaseModel):
    categories: list[CodeLabel]
    conditions: dict[str, list[CodeLabel]]
    attributes: dict[str, list[AttrField]]
    expense_categories: list[CodeLabel]
    income_categories: list[CodeLabel]
    districts: list[str]
    roles: list[CodeLabel]
    offer_kinds: list[CodeLabel]
    category_hints: list[str]
    fx_usd_uzs: float
    fx_updated_at: UTCDateTime | None
    currencies: list[CurrencyFormat]
    demo_companies: list[DemoCompany]


class ComponentStatus(BaseModel):
    status: Literal["ok", "disabled", "error", "not_configured", "starting"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: ComponentStatus
    llm: ComponentStatus
    telegram: ComponentStatus
    extractor: ComponentStatus
    bot: ComponentStatus
    version: str

