"""Platform schemas: stores, users, activity, integrations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.api.schemas.common import ORM, UserRole, UTCDateTime


class StoreIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    district: str | None = None
    area_m2: float | None = Field(None, gt=0)


class StorePatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    district: str | None = None
    area_m2: float | None = Field(None, gt=0)
    active: bool | None = None


class StoreOut(ORM):
    id: int
    name: str
    district: str | None
    area_m2: float | None
    active: bool


class UserIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: UserRole


class UserOut(ORM):
    id: int
    name: str
    role: str
    created_at: UTCDateTime


class UserCreated(BaseModel):
    api_key: str = Field(description="Shown once. Send as X-API-Key.")
    user: UserOut


class ActivityOut(ORM):
    id: int
    user_id: int | None
    user_name: str | None = None
    action: str
    entity: str
    entity_id: int | None
    summary: str
    created_at: UTCDateTime


class IntegrationOut(BaseModel):
    kind: str
    label: str
    status: Literal["connected", "not_connected", "error"]
    mode: Literal["live", "mock"]
    last_sync_at: UTCDateTime | None
    details: dict[str, Any]
    note: str


class SyncResult(BaseModel):
    kind: str
    mode: Literal["live", "mock"]
    created: int
    errors: list[dict[str, Any]]
    audit_flags: list[dict[str, Any]] = Field(description="Audit flags on the imported transactions")
    transaction_ids: list[int]
