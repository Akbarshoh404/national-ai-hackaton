"""Shared schema building blocks: UTC datetimes, cursor pages, item descriptors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")


def _iso_utc(d: datetime) -> str:
    if d.tzinfo is not None:
        d = d.astimezone(UTC).replace(tzinfo=None)
    return d.isoformat(timespec="seconds") + "Z"


#: Naive-UTC datetime serialized as ISO 8601 with a `Z` suffix.
UTCDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str, when_used="json")]

Category = Literal["phone", "laptop", "car", "house", "rent"]
Role = Literal["retailer", "supplier", "realtor", "landlord", "lender", "market_admin"]
UserRole = Literal["owner", "manager", "appraiser", "lender_officer"]
Severity = Literal["info", "low", "medium", "high"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Cursor page used by every list endpoint."""

    items: list[T]
    next_cursor: str | None = None
    total: int


class OkResponse(BaseModel):
    ok: bool = True
    detail: str | None = None


class ItemSpec(BaseModel):
    """An item to price or trade. `attrs` holds category-specific fields (see /meta)."""

    category: Category
    brand: str | None = None
    model: str | None = Field(None, description="Required for phone/laptop/car")
    condition: str | None = None
    district: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
