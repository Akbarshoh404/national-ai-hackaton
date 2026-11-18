"""Market feed, statistics, sourcing radar (deal alerts), trends, heatmap and rental yield."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import alerts, fx
from app.core.catalog import DISTRICTS, norm_model, normalize_district
from app.core.config import RENT_OPEX_RATIO, settings
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.i18n import fmt_uzs, register
from app.core.models import Listing, RawPost
from app.intelligence.market import pricing

register({
    "alert.deal.title": {"uz": "🔥 {title}: bozordan {pct}% arzon", "ru": "🔥 {title}: на {pct}% ниже рынка",
                         "en": "🔥 {title}: {pct}% below market"},
    "alert.deal.message": {
        "uz": "{title} — {price_uz}, bozor narxi {fair_uz}. Hudud: {district}. {url}",
        "ru": "{title} — {price_ru}, рыночная цена {fair_ru}. Район: {district}. {url}",
        "en": "{title} — {price_en}, market price {fair_en}. District: {district}. {url}"},
})


def listing_title(lst: Listing | dict[str, Any]) -> str:
    """Short human title: brand model + key attribute."""
    get = lst.get if isinstance(lst, dict) else lambda k, d=None: getattr(lst, k, d)
    a = get("attrs") or {}
    parts = [get("brand") or "", get("model") or ""]
    cat = get("category")
    if cat == "phone" and a.get("storage_gb"):
        parts.append(f"{a['storage_gb']}GB")
    elif cat == "laptop" and a.get("ram_gb") and a.get("ssd_gb"):
        parts.append(f"{a['ram_gb']}/{a['ssd_gb']}")
    elif cat == "car" and a.get("year"):
        parts.append(str(a["year"]))
    elif cat in ("house", "rent") and a.get("rooms"):
        parts = [f"{a['rooms']}-xonali", get("district") or ""]
    return " ".join(p for p in parts if p).strip()


def deal_check(db: Session, listing: Listing, est: pricing.Estimate | None = None) -> bool:
    """Create a broadcast `sourcing_deal` alert when a listing is far below its fair price.

    Requires a medium/high-confidence estimate that excludes the listing itself.
    """
    if est is None:
        est = pricing.assess_listing(db, listing)
    if est is None or est.confidence == "low" or listing.discount_pct is None:
        return False
    if listing.discount_pct < settings.DEAL_THRESHOLD * 100 or listing.is_duplicate:
        return False
    title = listing_title(listing)
    kw = {"title": title, "pct": round(listing.discount_pct), "district": listing.district or "—",
          "url": listing.source_url or ""}
    for lang in ("uz", "ru", "en"):
        kw[f"price_{lang}"] = fmt_uzs(listing.price_uzs, lang)
        kw[f"fair_{lang}"] = fmt_uzs(est.fair_price_uzs, lang)
    alerts.create(db, company_id=None, category=listing.category, type="sourcing_deal",
                  severity="high" if listing.discount_pct >= 25 else "medium",
                  i18n=alerts.texts("alert.deal.title", "alert.deal.message", **kw),
                  payload={"listing_id": listing.id, "discount_pct": listing.discount_pct,
                           "price_uzs": listing.price_uzs, "fair_price_uzs": est.fair_price_uzs,
                           "source_url": listing.source_url, "key": f"listing:{listing.id}"},
                  commit=False)
    return True


def stats(db: Session) -> dict[str, Any]:
    """Counts per category, new in the last hour, raw post backlog, FX."""
    hour_ago = utcnow() - timedelta(hours=1)
    per_cat = dict(db.execute(select(Listing.category, func.count()).where(Listing.is_duplicate.is_(False))
                              .group_by(Listing.category)).all())
    new_hour = dict(db.execute(select(Listing.category, func.count())
                               .where(Listing.created_at >= hour_ago, Listing.is_duplicate.is_(False))
                               .group_by(Listing.category)).all())
    raw = dict(db.execute(select(RawPost.processed, func.count()).group_by(RawPost.processed)).all())
    return {
        "listings_per_category": {c: int(per_cat.get(c, 0)) for c in ("phone", "laptop", "car", "house", "rent")},
        "new_last_hour": {c: int(new_hour.get(c, 0)) for c in ("phone", "laptop", "car", "house", "rent")},
        "total_listings": int(sum(per_cat.values())),
        "raw_pending": int(raw.get(0, 0)), "raw_failed": int(raw.get(2, 0)),
        "raw_done": int(raw.get(1, 0)), "raw_skipped": int(raw.get(3, 0)),
        "latest_post_at": db.scalar(select(func.max(Listing.posted_at))),
        "latest_telegram_post_at": db.scalar(select(func.max(RawPost.posted_at))),
        "fx_usd_uzs": fx.rate(),
    }


def sourcing_radar(db: Session, categories: list[str], min_discount_pct: float, days: int,
                   limit: int = 50) -> list[Listing]:
    """Recent listings priced at least `min_discount_pct` below their fair price."""
    since = utcnow() - timedelta(days=days)
    q = (select(Listing).where(Listing.category.in_(categories), Listing.posted_at >= since,
                               Listing.is_duplicate.is_(False), Listing.discount_pct >= min_discount_pct)
         .order_by(Listing.discount_pct.desc()).limit(limit))
    return list(db.scalars(q))


def trend(db: Session, category: str, model: str | None, days: int) -> list[dict[str, Any]]:
    """Weekly median price and listing count."""
    since = utcnow() - timedelta(days=days)
    q = select(Listing.posted_at, Listing.price_uzs).where(Listing.category == category,
                                                           Listing.is_duplicate.is_(False),
                                                           Listing.posted_at >= since)
    if model:
        q = q.where(Listing.model_norm == norm_model(model))
    rows = db.execute(q).all()
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=["posted_at", "price_uzs"])
    df["week"] = df["posted_at"].dt.to_period("W-SUN").dt.start_time
    g = df.groupby("week")["price_uzs"].agg(["median", "count"]).reset_index()
    rate = fx.rate()
    return [{"week_start": r.week.date(), "median_price_uzs": round(float(r["median"])),
             "median_price_usd": round(float(r["median"]) / rate, 2), "listings": int(r["count"])}
            for _, r in g.iterrows()]


def models(db: Session, category: str, q: str | None, limit: int) -> list[dict[str, Any]]:
    """Model autocomplete sorted by listing count."""
    since = utcnow() - timedelta(days=settings.MARKET_WINDOW_DAYS)
    stmt = (select(Listing.model_norm, func.max(Listing.brand), func.max(Listing.model), func.count())
            .where(Listing.category == category, Listing.posted_at >= since, Listing.model_norm != "")
            .group_by(Listing.model_norm).order_by(func.count().desc()))
    if q:
        stmt = stmt.where(Listing.model_norm.contains(norm_model(q) or q.lower()))
    return [{"model_norm": m, "brand": b, "model": d, "listings": int(n)}
            for m, b, d, n in db.execute(stmt.limit(limit)).all()]


def heatmap(db: Session, category: str) -> list[dict[str, Any]]:
    """Median price per m² (house) or monthly rent (rent) per Tashkent district."""
    df = pricing.load_frame(db, category)
    out = []
    rate = fx.rate()
    for d in DISTRICTS:
        sub = df[df["district"] == d]
        if category == "rent":
            sub = sub[sub["period"].isna() | (sub["period"] == "monthly")]
        if sub.empty:
            out.append({"district": d, "listings": 0, "median_uzs": None, "median_usd": None,
                        "median_per_m2_uzs": None, "median_per_m2_usd": None})
            continue
        area = sub["area_m2"].to_numpy(float)
        prices = sub["price_uzs"].to_numpy(float)
        ok = ~np.isnan(area) & (area > 0)
        per_m2 = float(np.median(prices[ok] / area[ok])) if ok.any() else None
        med = float(np.median(prices))
        out.append({"district": d, "listings": len(sub), "median_uzs": round(med),
                    "median_usd": round(med / rate, 2),
                    "median_per_m2_uzs": round(per_m2) if per_m2 else None,
                    "median_per_m2_usd": round(per_m2 / rate, 2) if per_m2 else None})
    return out


def rental_yield(db: Session, district: str, rooms: int, area_m2: float, furnished: bool | None,
                 lang: str) -> dict[str, Any]:
    """Apartment price, monthly rent, gross/net yield and payback for one apartment profile."""
    house = pricing.estimate(db, "house", district=district, attrs={"rooms": rooms, "area_m2": area_m2}, lang=lang)
    rent_attrs: dict[str, Any] = {"rooms": rooms}
    if furnished is not None:
        rent_attrs["furnished"] = furnished
    rent = pricing.estimate(db, "rent", district=district, attrs=rent_attrs, lang=lang)
    price, monthly = house.fair_price_uzs, rent.fair_price_uzs
    if price <= 0:
        raise AppError("invalid_estimate", "Apartment price estimate is zero", 422)
    gross_annual = monthly * 12
    net_annual = gross_annual * (1 - RENT_OPEX_RATIO)
    rate = fx.rate()
    return {
        "district": normalize_district(district) or district, "rooms": rooms,
        "area_m2": area_m2, "apartment_price_uzs": price, "apartment_price_usd": round(price / rate, 2),
        "monthly_rent_uzs": monthly, "monthly_rent_usd": round(monthly / rate, 2),
        "gross_yield_pct": round(gross_annual / price * 100, 2),
        "net_yield_pct": round(net_annual / price * 100, 2),
        "payback_years": round(price / net_annual, 1) if net_annual > 0 else None,
        "opex_ratio": RENT_OPEX_RATIO,
        "price_basis": house.basis, "rent_basis": rent.basis,
        "price_comparables": house.comparables, "rent_comparables": rent.comparables,
        "confidence": min((house.confidence, rent.confidence), key=["low", "medium", "high"].index),
        "assumptions": [f"Net yield deducts {int(RENT_OPEX_RATIO * 100)}% of rent for vacancy, maintenance "
                        "and property tax", "Rent is the monthly median for the same rooms"],
    }
