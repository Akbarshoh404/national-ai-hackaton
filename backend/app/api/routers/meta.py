"""`/meta` (dropdowns and labels) and `/health`."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select, text

from app.api.schemas.auth import (
    AttrField,
    CodeLabel,
    ComponentStatus,
    CreditProductMeta,
    CurrencyFormat,
    DemoCompany,
    HealthResponse,
    LabelSet,
    MetaResponse,
    PingOut,
    StoreRef,
)
from app.core import catalog, fx, llm, workers
from app.core.config import CREDIT_PRODUCTS, settings
from app.core.deps import DbDep, OptionalCompanyDep
from app.core.models import Company, Store

router = APIRouter(tags=["meta"])
VERSION = "1.0.0"


def _cl(table: dict[str, dict[str, str]], codes: list[str]) -> list[CodeLabel]:
    return [CodeLabel(code=c, label=LabelSet(**table[c])) for c in codes]


@router.get("/meta", response_model=MetaResponse)
def meta_get(db: DbDep, company: OptionalCompanyDep) -> MetaResponse:
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
        roles=_cl(catalog.ROLE_LABELS, catalog.ROLES_ALL),
        offer_kinds=_cl(catalog.OFFER_KIND_LABELS, catalog.OFFER_KINDS),
        category_hints=catalog.CATEGORY_HINTS,
        fx_usd_uzs=fx.rate(),
        fx_updated_at=fx.updated_at(),
        currencies=[
            CurrencyFormat(code="UZS", symbol="so'm", decimals=0, thousands_separator=" ", symbol_position="after"),
            CurrencyFormat(code="USD", symbol="$", decimals=0, thousands_separator=",", symbol_position="before"),
        ],
        demo_companies=demo,
        user_roles=_cl(catalog.USER_ROLE_LABELS, list(catalog.USER_ROLE_LABELS)),
        credit_products=[CreditProductMeta(code=k, label=LabelSet(**catalog.CREDIT_PRODUCT_LABELS[k]),
                                           rate_pct=v["rate_pct"], max_months=int(v["max_months"]),
                                           down_payment_pct=v["down_payment_pct"])
                         for k, v in CREDIT_PRODUCTS.items()],
        decision_types=_cl(catalog.DECISION_TYPE_LABELS, list(catalog.DECISION_TYPE_LABELS)),
        block_types=catalog.BLOCK_TYPES,
        integration_kinds=_cl(catalog.INTEGRATION_LABELS, catalog.INTEGRATION_KINDS),
        plans=_cl(catalog.PLAN_LABELS, catalog.PLANS),
        stores=[StoreRef(id=s.id, name=s.name, district=s.district)
                for s in db.scalars(select(Store).where(Store.company_id == company.id).order_by(Store.id))]
        if company else [],
    )


@router.get("/ping", response_model=PingOut)
def ping() -> PingOut:
    """Liveness for uptime pingers (keeps a free Render service awake). No auth, no database access."""
    return PingOut()


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
