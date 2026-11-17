"""`/meta` (dropdowns and labels) and `/health`."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select, text

from app import catalog
from app.config import settings
from app.deps import DbDep
from app.models import Company
from app.schemas.auth import (
    AttrField,
    CodeLabel,
    ComponentStatus,
    CurrencyFormat,
    DemoCompany,
    HealthResponse,
    LabelSet,
    MetaResponse,
)
from app.services import fx, llm, workers

router = APIRouter(tags=["meta"])
VERSION = "1.0.0"


def _cl(table: dict[str, dict[str, str]], codes: list[str]) -> list[CodeLabel]:
    return [CodeLabel(code=c, label=LabelSet(**table[c])) for c in codes]


@router.get("/meta", response_model=MetaResponse)
def meta_get(db: DbDep) -> MetaResponse:
    """Everything the frontend needs for dropdowns, labels and formatting."""
    demo = []
    if settings.DEMO_MODE:
        demo = [DemoCompany(slug=c.slug, name=c.name, role=c.role)
                for c in db.scalars(select(Company).where(Company.slug.is_not(None)).order_by(Company.id))
                if c.slug]
    return MetaResponse(
        categories=_cl(catalog.CATEGORY_LABELS, catalog.CATEGORIES),
        conditions={cat: _cl(catalog.CONDITION_LABELS, conds) for cat, conds in catalog.CONDITIONS.items()},
        attributes={cat: [AttrField(**f) for f in fields] for cat, fields in catalog.ATTR_FIELDS.items()},
        expense_categories=_cl(catalog.TXN_CATEGORY_LABELS, catalog.EXPENSE_CATEGORIES),
        income_categories=_cl(catalog.TXN_CATEGORY_LABELS, catalog.INCOME_CATEGORIES),
        districts=catalog.DISTRICTS,
        roles=_cl(catalog.ROLE_LABELS, catalog.ROLES),
        offer_kinds=_cl(catalog.OFFER_KIND_LABELS, catalog.OFFER_KINDS),
        category_hints=catalog.CATEGORY_HINTS,
        fx_usd_uzs=fx.rate(),
        fx_updated_at=fx.updated_at(),
        currencies=[
            CurrencyFormat(code="UZS", symbol="so'm", decimals=0, thousands_separator=" ", symbol_position="after"),
            CurrencyFormat(code="USD", symbol="$", decimals=0, thousands_separator=",", symbol_position="before"),
        ],
        demo_companies=demo,
    )


@router.get("/health", response_model=HealthResponse)
def health(db: DbDep) -> HealthResponse:
    """Status of the DB, LLM, Telegram listener, extractor and bot."""
    try:
        db.execute(text("SELECT 1"))
        db_status = ComponentStatus(status="ok")
    except Exception as exc:  # pragma: no cover - db down
        db_status = ComponentStatus(status="error", detail=type(exc).__name__)
    llm_s, llm_d = llm.status()
    comps = {name: ComponentStatus(status=s, detail=d) for name, (s, d) in workers.STATUS.items()}
    overall = "ok" if db_status.status == "ok" and all(c.status != "error" for c in comps.values()) else "degraded"
    return HealthResponse(status=overall, db=db_status, llm=ComponentStatus(status=llm_s, detail=llm_d),
                          telegram=comps["telegram"], extractor=comps["extractor"], bot=comps["bot"],
                          version=VERSION)
