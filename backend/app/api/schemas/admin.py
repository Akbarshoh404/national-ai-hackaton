"""Admin schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import ORM, UTCDateTime


class WorkerState(BaseModel):
    status: str
    detail: str | None


class AdminStatus(BaseModel):
    raw_posts: dict[str, int]
    listings: int
    sources_active: int
    workers: dict[str, WorkerState]
    fx_usd_uzs: float
    fx_source: str


SellerType = Literal["shop", "private"]
Hint = Literal["phone", "laptop", "car", "house", "rent", "mixed_tech", "mixed_realty", "mixed"]


class SourceIn(BaseModel):
    title: str
    username: str = Field(description="Channel/group @username (without @)")
    category_hint: Hint
    seller_type_default: SellerType = "shop"
    active: bool = True


class SourcePatch(BaseModel):
    title: str | None = None
    category_hint: Hint | None = None
    seller_type_default: SellerType | None = None
    active: bool | None = None


class SourceOut(ORM):
    id: int
    title: str
    username: str
    category_hint: str
    seller_type_default: str
    active: bool
    last_msg_id: int
    created_at: UTCDateTime


class RawPostOut(ORM):
    id: int
    source: str
    msg_id: int
    posted_at: UTCDateTime
    text: str
    has_photo: bool
    processed: int
    error: str | None


class JobStarted(BaseModel):
    started: bool
    detail: str


class ExtractResult(BaseModel):
    processed: int
    created: int
    failed: int
    skipped: int


class FxOut(BaseModel):
    usd_uzs: float
    source: str
    updated_at: UTCDateTime | None
