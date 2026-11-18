"""Alert schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.api.schemas.common import UTCDateTime


class AlertOut(BaseModel):
    id: int
    type: str
    category: str | None
    severity: str
    title: str
    message: str
    payload: dict[str, Any]
    read: bool
    broadcast: bool
    created_at: UTCDateTime


class ReadAllResult(BaseModel):
    marked: int
