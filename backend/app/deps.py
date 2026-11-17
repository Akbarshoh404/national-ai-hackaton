"""Auth and request-context dependencies."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.i18n import lang_from_header, t
from app.models import Company, User
from app.permissions import denial

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, scheme_name="ApiKey")
_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False, scheme_name="AdminKey")


def hash_key(key: str) -> str:
    """API keys are stored as sha256 hex digests."""
    return hashlib.sha256(key.encode()).hexdigest()


def new_api_key() -> str:
    return "bp_" + secrets.token_urlsafe(32)


def get_lang(accept_language: Annotated[str | None, Header()] = None) -> str:
    """Language for generated text from Accept-Language (uz default)."""
    return lang_from_header(accept_language)


DbDep = Annotated[Session, Depends(get_db)]
LangDep = Annotated[str, Depends(get_lang)]


def resolve_key(db: Session, key: str) -> tuple[Company, User | None] | None:
    """A company key acts as `owner`; a user key acts with that user's role."""
    h = hash_key(key)
    company = db.scalar(select(Company).where(Company.api_key == h))
    if company is not None:
        return company, None
    user = db.scalar(select(User).where(User.api_key == h))
    if user is not None:
        return db.get(Company, user.company_id), user
    return None


def company_by_key(db: Session, key: str) -> Company | None:
    found = resolve_key(db, key)
    return found[0] if found else None


def actor_role(company: Company) -> str:
    """Role of the caller behind `company` (set by `get_company`)."""
    return getattr(company, "actor_role", "owner")


def actor_user_id(company: Company) -> int | None:
    return getattr(company, "actor_user_id", None)


def get_company(request: Request, db: DbDep, lang: LangDep,
                api_key: Annotated[str | None, Security(_api_key_header)] = None) -> Company:
    """Resolve the calling company from `X-API-Key` (401 if missing/invalid, 403 if the role forbids the call).

    The caller's user role is attached to the returned instance as `actor_role` / `actor_user_id`.
    """
    if not api_key:
        raise AppError("missing_api_key", t("err.missing_api_key", lang), 401)
    found = resolve_key(db, api_key)
    if found is None:
        raise AppError("invalid_api_key", t("err.invalid_api_key", lang), 401)
    company, user = found
    company.actor_role = user.role if user else "owner"  # type: ignore[attr-defined]
    company.actor_user_id = user.id if user else None  # type: ignore[attr-defined]
    path = request.url.path.removeprefix("/api/v1")
    reason = denial(request.method, path, company.role, company.actor_role)  # type: ignore[attr-defined]
    if reason:
        raise AppError("role_forbidden", reason, 403, {"role": company.actor_role,  # type: ignore[attr-defined]
                                                       "company_role": company.role})
    return company


def optional_company(db: DbDep, api_key: Annotated[str | None, Security(_api_key_header)] = None) -> Company | None:
    """Company for an optional key (public endpoints that add detail when authenticated)."""
    return company_by_key(db, api_key) if api_key else None


def require_company_role(*roles: str):
    """Router dependency: the calling company must have one of `roles` (403 otherwise)."""

    def dep(company: Annotated[Company, Depends(get_company)]) -> Company:
        if company.role not in roles:
            raise AppError("role_forbidden", f"This endpoint is for {', '.join(roles)} accounts", 403,
                           {"company_role": company.role})
        return company

    return dep


def require_owner(company: Annotated[Company, Depends(get_company)]) -> Company:
    if actor_role(company) != "owner":
        raise AppError("role_forbidden", "Only the owner can do this", 403, {"role": actor_role(company)})
    return company


def require_admin(lang: LangDep, admin_key: Annotated[str | None, Security(_admin_key_header)] = None) -> None:
    """401 without `X-Admin-Key`, 403 with a wrong one."""
    if not admin_key:
        raise AppError("missing_admin_key", t("err.missing_admin_key", lang), 401)
    if not hmac.compare_digest(admin_key, settings.ADMIN_KEY):
        raise AppError("invalid_admin_key", t("err.invalid_admin_key", lang), 403)


CompanyDep = Annotated[Company, Depends(get_company)]

OwnerDep = Annotated[Company, Depends(require_owner)]
OptionalCompanyDep = Annotated[Company | None, Depends(optional_company)]
