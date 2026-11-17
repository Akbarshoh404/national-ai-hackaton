"""B2B exchange: requests for quotes, quotes ranking, offers, deals, ratings, demand."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Deal, Rating


def reputation(db: Session, company_id: int) -> dict:
    """Average rating, number of ratings and completed deals for a company."""
    avg, cnt = db.execute(
        select(func.avg(Rating.score), func.count(Rating.id)).where(Rating.ratee_id == company_id)
    ).one()
    deals = db.scalar(
        select(func.count(Deal.id)).where(or_(Deal.buyer_id == company_id, Deal.seller_id == company_id))
    ) or 0
    return {"rating": round(float(avg), 2) if avg is not None else None, "ratings_count": int(cnt),
            "deals_count": int(deals)}
