"""Registration, demo login and the company directory."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.schemas.auth import (
    CompanyOut,
    CompanyPublic,
    CompanyRegister,
    CompanyUpdate,
    DemoLoginRequest,
    RegisterResponse,
    Reputation,
)
from app.api.schemas.common import Category, Page, Role
from app.core.config import settings
from app.core.deps import CompanyDep, DbDep, actor_role, hash_key, new_api_key
from app.core.errors import AppError, conflict, not_found
from app.core.models import Company, Store
from app.intelligence.b2b.exchange import reputation

router = APIRouter(tags=["auth & companies"])

#: Deterministic demo keys (DEMO_MODE only). Real companies get random keys.
DEMO_KEY_PREFIX = "demo-"


def demo_key(slug: str) -> str:
    return f"{DEMO_KEY_PREFIX}{slug}"


def company_out(c: Company) -> CompanyOut:
    out = CompanyOut.model_validate(c)
    out.telegram_linked = c.telegram_chat_id is not None
    out.my_role = actor_role(c)
    return out


@router.post("/auth/register", response_model=RegisterResponse, status_code=201)
def auth_register(body: CompanyRegister, db: DbDep) -> RegisterResponse:
    """Register a business. The API key is returned once and stored hashed."""
    if db.scalar(select(Company.id).where(Company.stir == body.stir)):
        raise conflict("stir_taken", "A company with this STIR is already registered")
    key = new_api_key()
    company = Company(name=body.name, stir=body.stir, role=body.role, categories=list(body.categories),
                      city=body.city, district=body.district, tax_regime=body.tax_regime, api_key=hash_key(key))
    db.add(company)
    try:
        db.flush()
        db.add(Store(company_id=company.id, name="Asosiy do'kon", district=company.district))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("stir_taken", "A company with this STIR is already registered") from exc
    return RegisterResponse(api_key=key, company=company_out(company))


@router.post("/auth/demo-login", response_model=RegisterResponse)
def auth_demo_login(body: DemoLoginRequest, db: DbDep) -> RegisterResponse:
    """Return the API key of a seeded demo company (only when DEMO_MODE=true)."""
    if not settings.DEMO_MODE:
        raise AppError("demo_disabled", "Demo login is disabled", 403)
    company = db.scalar(select(Company).where(Company.slug == body.company_slug))
    if company is None or company.api_key != hash_key(demo_key(body.company_slug)):
        raise not_found("company", body.company_slug)
    return RegisterResponse(api_key=demo_key(body.company_slug), company=company_out(company))


@router.get("/companies/me", response_model=CompanyOut)
def companies_me(company: CompanyDep) -> CompanyOut:
    return company_out(company)


@router.patch("/companies/me", response_model=CompanyOut)
def companies_update_me(body: CompanyUpdate, company: CompanyDep, db: DbDep) -> CompanyOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(company, field, list(value) if field == "categories" else value)
    db.commit()
    return company_out(company)


def _public(db: DbDep, c: Company) -> CompanyPublic:
    return CompanyPublic(id=c.id, name=c.name, role=c.role, categories=c.categories, city=c.city,
                         district=c.district, reputation=Reputation(**reputation(db, c.id)))


@router.get("/companies", response_model=Page[CompanyPublic])
def companies_list(db: DbDep, _: CompanyDep, role: Role | None = None, category: Category | None = None,
                   cursor: str | None = None, limit: int = Query(50, ge=1, le=200)) -> Page[CompanyPublic]:
    """Directory of registered businesses with reputation."""
    q = select(Company).order_by(Company.id)
    if role:
        q = q.where(Company.role == role)
    rows = [c for c in db.scalars(q) if not category or category in (c.categories or [])]
    start = int(cursor) if cursor else 0
    page = rows[start:start + limit]
    nxt = str(start + limit) if start + limit < len(rows) else None
    return Page(items=[_public(db, c) for c in page], next_cursor=nxt, total=len(rows))


@router.get("/companies/{company_id}", response_model=CompanyPublic)
def companies_get(company_id: int, db: DbDep, _: CompanyDep) -> CompanyPublic:
    c = db.get(Company, company_id)
    if c is None:
        raise not_found("company", company_id)
    return _public(db, c)
