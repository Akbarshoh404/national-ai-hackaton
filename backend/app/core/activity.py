"""Activity log: who did what, written by every state-changing endpoint."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.models import ActivityLog, Company


def log(db: Session, company: Company, action: str, entity: str, entity_id: int | None, summary: str,
        commit: bool = True) -> ActivityLog:
    """Record an action by the current caller (user id comes from the auth dependency)."""
    row = ActivityLog(company_id=company.id, user_id=getattr(company, "actor_user_id", None), action=action,
                      entity=entity, entity_id=entity_id, summary=summary[:1000])
    db.add(row)
    if commit:
        db.commit()
    return row
