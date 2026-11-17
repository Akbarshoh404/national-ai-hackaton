"""Auth and request-context dependencies."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, Header, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import AppError
from app.i18n import lang_from_header, t
from app.models import Company

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


def company_by_key(db: Session, key: str) -> Company | None:
    return db.scalar(select(Company).where(Company.api_key == hash_key(key)))


def get_company(db: DbDep, lang: LangDep,
                api_key: Annotated[str | None, Security(_api_key_header)] = None) -> Company:
    """Resolve the calling company from `X-API-Key` (401 if missing or invalid)."""
    if not api_key:
        raise AppError("missing_api_key", t("err.missing_api_key", lang), 401)
    company = company_by_key(db, api_key)
    if company is None:
        raise AppError("invalid_api_key", t("err.invalid_api_key", lang), 401)
    return company


def require_admin(lang: LangDep, admin_key: Annotated[str | None, Security(_admin_key_header)] = None) -> None:
    """401 without `X-Admin-Key`, 403 with a wrong one."""
    if not admin_key:
        raise AppError("missing_admin_key", t("err.missing_admin_key", lang), 401)
    if not hmac.compare_digest(admin_key, settings.ADMIN_KEY):
        raise AppError("invalid_admin_key", t("err.invalid_admin_key", lang), 403)


CompanyDep = Annotated[Company, Depends(get_company)]
