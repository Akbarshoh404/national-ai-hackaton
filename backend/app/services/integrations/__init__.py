"""Integration adapters (Telegram is live; Didox, Soliq, BILLZ, 1C and bank are mock adapters).

Real API access to Didox / Soliq / BILLZ / 1C / banks needs partner agreements. Until then each adapter
has only a `mock` implementation that imports sample files from `data/samples/`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import INTEGRATION_KINDS
from app.models import Company, Integration


def ensure_rows(db: Session, company: Company) -> list[Integration]:
    """Make sure the company has one integration row per kind."""
    have = {i.kind: i for i in db.scalars(select(Integration).where(Integration.company_id == company.id))}
    for kind in INTEGRATION_KINDS:
        if kind not in have:
            row = Integration(company_id=company.id, kind=kind, status="not_connected",
                              details={"mode": "live" if kind == "telegram" else "mock"})
            db.add(row)
            have[kind] = row
    return [have[k] for k in INTEGRATION_KINDS]
