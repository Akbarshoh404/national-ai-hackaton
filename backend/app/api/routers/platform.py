"""Platform: stores, users (roles), activity log."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.schemas.common import OkResponse, Page
from app.api.schemas.platform import (
    ActivityOut,
    IntegrationOut,
    StoreIn,
    StoreOut,
    StorePatch,
    SyncResult,
    UserCreated,
    UserIn,
    UserOut,
)
from app.channels import integrations
from app.core import activity
from app.core.catalog import normalize_district
from app.core.deps import CompanyDep, DbDep, LangDep, OwnerDep, hash_key, new_api_key
from app.core.errors import not_found
from app.core.models import ActivityLog, Store, User

router = APIRouter(tags=["platform"])


@router.get("/stores", response_model=Page[StoreOut])
def stores_list(db: DbDep, company: CompanyDep) -> Page[StoreOut]:
    rows = list(db.scalars(select(Store).where(Store.company_id == company.id).order_by(Store.id)))
    return Page(items=[StoreOut.model_validate(s) for s in rows], next_cursor=None, total=len(rows))


@router.post("/stores", response_model=StoreOut, status_code=201)
def stores_create(body: StoreIn, db: DbDep, company: CompanyDep) -> StoreOut:
    s = Store(company_id=company.id, name=body.name, district=normalize_district(body.district) or body.district,
              area_m2=body.area_m2)
    db.add(s)
    db.flush()
    activity.log(db, company, "store.create", "store", s.id, f"Store '{s.name}' created")
    return StoreOut.model_validate(s)


@router.patch("/stores/{store_id}", response_model=StoreOut)
def stores_update(store_id: int, body: StorePatch, db: DbDep, company: CompanyDep) -> StoreOut:
    s = db.get(Store, store_id)
    if s is None or s.company_id != company.id:
        raise not_found("store", store_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, normalize_district(v) or v if k == "district" and v else v)
    activity.log(db, company, "store.update", "store", s.id, f"Store '{s.name}' updated")
    return StoreOut.model_validate(s)


@router.get("/users", response_model=Page[UserOut])
def users_list(db: DbDep, company: OwnerDep) -> Page[UserOut]:
    rows = list(db.scalars(select(User).where(User.company_id == company.id).order_by(User.id)))
    return Page(items=[UserOut.model_validate(u) for u in rows], next_cursor=None, total=len(rows))


@router.post("/users", response_model=UserCreated, status_code=201)
def users_create(body: UserIn, db: DbDep, company: OwnerDep) -> UserCreated:
    """Create a user with a role. The API key is returned once."""
    key = new_api_key()
    u = User(company_id=company.id, name=body.name, role=body.role, api_key=hash_key(key))
    db.add(u)
    db.flush()
    activity.log(db, company, "user.create", "user", u.id, f"User '{u.name}' ({u.role}) created")
    return UserCreated(api_key=key, user=UserOut.model_validate(u))


@router.delete("/users/{user_id}", response_model=OkResponse)
def users_delete(user_id: int, db: DbDep, company: OwnerDep) -> OkResponse:
    u = db.get(User, user_id)
    if u is None or u.company_id != company.id:
        raise not_found("user", user_id)
    name = u.name
    db.delete(u)
    activity.log(db, company, "user.delete", "user", user_id, f"User '{name}' removed")
    return OkResponse()


@router.get("/activity", response_model=Page[ActivityOut])
def activity_list(db: DbDep, company: CompanyDep, entity: str | None = None, cursor: str | None = None,
                  limit: int = Query(50, ge=1, le=200)) -> Page[ActivityOut]:
    """Who did what: deals, reprices, decisions, uploads, budget changes, offers, quotes."""
    q = select(ActivityLog).where(ActivityLog.company_id == company.id)
    if entity:
        q = q.where(ActivityLog.entity == entity)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(ActivityLog.id < int(cursor))
    rows = list(db.scalars(q.order_by(ActivityLog.id.desc()).limit(limit + 1)))
    names = {u.id: u.name for u in db.scalars(select(User).where(User.company_id == company.id))}
    items = []
    for r in rows[:limit]:
        out = ActivityOut.model_validate(r)
        out.user_name = names.get(r.user_id) if r.user_id else "owner"
        items.append(out)
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=items, next_cursor=nxt, total=total)


@router.get("/integrations", response_model=list[IntegrationOut])
def integrations_list(db: DbDep, company: CompanyDep, lang: LangDep) -> list[IntegrationOut]:
    """Integration status cards. Telegram is live; Didox/Soliq/BILLZ/1C/bank are mock adapters."""
    return [IntegrationOut(**c) for c in integrations.cards(db, company, lang)]


@router.post("/integrations/{kind}/sync", response_model=SyncResult)
def integrations_sync(kind: str, db: DbDep, company: CompanyDep, lang: LangDep) -> SyncResult:
    """Import from an integration (mock sample) through the normal upload + audit path."""
    out = integrations.sync(db, company, kind, lang)
    activity.log(db, company, f"integration.sync.{kind}", "integration", None,
                 f"{kind} sync ({out['mode']}): {out['created']} records, {len(out['audit_flags'])} audit flags")
    return SyncResult(**out)
