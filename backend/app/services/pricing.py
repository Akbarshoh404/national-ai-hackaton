"""Fair-price engine.

Comparable listings from the last `MARKET_WINDOW_DAYS` are filtered in tiers from
strict to loose; the first tier with at least `MIN_COMPARABLES` matches wins. Each
comparable is normalized to the target item (condition, storage, IMEI, repairs,
model year) with the factors in `app.config`, outliers are trimmed and the median
becomes the fair price. Every number here is computed in Python, never by the LLM.
"""

from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import norm_model, normalize_district
from app.config import (
    CAR_DEPRECIATION_PER_YEAR,
    CONDITION_MULTIPLIERS,
    DEALER_MARGIN,
    PHONE_IMEI_UNREGISTERED_DEDUCTION,
    PHONE_REPAIRED_DEDUCTION,
    STORAGE_STEP_PREMIUM,
    settings,
)
from app.db import utcnow
from app.errors import AppError
from app.i18n import t
from app.models import Listing
from app.services import fx

_ATTR_KEYS = ["storage_gb", "ram_gb", "ssd_gb", "cpu", "year", "mileage_km", "fuel", "rooms", "area_m2",
              "building", "furnished", "period", "imei_registered", "repaired"]

_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_memo: dict[tuple, Estimate] = {}
_lock = threading.Lock()


class NotEnoughData(AppError):
    """Raised when fewer than 3 comparables exist in every tier."""

    def __init__(self, n: int, lang: str = "en", details: dict[str, Any] | None = None):
        super().__init__("not_enough_market_data", t("err.not_enough_market_data", lang, n=n), 422,
                         {"comparables": n, **(details or {})})


@dataclass
class Estimate:
    """Result of a fair-price estimate (all money values raw numbers)."""

    category: str
    fair_price_uzs: float
    fair_price_usd: float
    range_uzs: tuple[float, float]
    fair_buy_price_uzs: float
    fair_buy_price_usd: float
    comparables: int
    basis: str
    tier: int
    confidence: str
    samples: list[dict[str, Any]]
    price_by_seller_type: dict[str, float] | None = None
    per_m2_uzs: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def invalidate(category: str | None = None) -> None:
    """Drop cached comparables (after inserts)."""
    with _lock:
        if category is None:
            _cache.clear()
            _memo.clear()
        else:
            _cache.pop(category, None)
            for k in [k for k in _memo if k[0] == category]:
                _memo.pop(k, None)


def cpu_class(cpu: Any) -> str | None:
    """Coarse CPU class: i5, m1, ryzen 5…"""
    if not cpu or not isinstance(cpu, str):
        return None
    m = re.search(r"(i[3579]|m[1-4]|ryzen\s?\d|ultra\s?\d|celeron|pentium)", cpu.lower())
    return m.group(1).replace(" ", "") if m else None


def load_frame(db: Session, category: str) -> pd.DataFrame:
    """Comparable listings for `category` (cached for PRICE_CACHE_TTL_S)."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(category)
        if hit and now - hit[0] < settings.PRICE_CACHE_TTL_S:
            return hit[1]
    since = utcnow() - timedelta(days=settings.MARKET_WINDOW_DAYS)
    rows = db.execute(
        select(Listing.id, Listing.brand, Listing.model, Listing.model_norm, Listing.condition, Listing.price_uzs,
               Listing.price_usd, Listing.district, Listing.attrs, Listing.seller_type, Listing.posted_at,
               Listing.source_url)
        .where(Listing.category == category, Listing.is_duplicate.is_(False), Listing.posted_at >= since)
    ).all()
    records = []
    for r in rows:
        a = r.attrs or {}
        rec = {"id": r.id, "brand": r.brand, "model": r.model, "model_norm": r.model_norm,
               "condition": r.condition, "price_uzs": r.price_uzs, "price_usd": r.price_usd,
               "district": r.district, "seller_type": r.seller_type, "posted_at": r.posted_at,
               "source_url": r.source_url, "attrs": a}
        for k in _ATTR_KEYS:
            rec[k] = a.get(k)
        records.append(rec)
    df = pd.DataFrame.from_records(records, columns=["id", "brand", "model", "model_norm", "condition", "price_uzs",
                                                     "price_usd", "district", "seller_type", "posted_at",
                                                     "source_url", "attrs", *_ATTR_KEYS])
    for k in ("storage_gb", "ram_gb", "ssd_gb", "year", "mileage_km", "rooms", "area_m2"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df["cpu_class"] = df["cpu"].map(cpu_class)
    df["vf"] = _value_factor(df, category)
    with _lock:
        _cache[category] = (now, df)
        for k in [k for k in _memo if k[0] == category]:
            _memo.pop(k, None)
    return df


def _num(v: Any) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _value_factor(df: pd.DataFrame, category: str) -> np.ndarray:
    """Per-row value factor relative to a 'new, registered, unrepaired' item."""
    n = len(df)
    if category not in ("phone", "laptop"):
        return np.ones(n)
    cond = df["condition"].map(lambda c: CONDITION_MULTIPLIERS.get(c, CONDITION_MULTIPLIERS["A"])).to_numpy(float)
    if category == "phone":
        imei = np.where(df["imei_registered"].map(lambda v: v is False).to_numpy(bool),
                        1 - PHONE_IMEI_UNREGISTERED_DEDUCTION, 1.0)
        rep = np.where(df["repaired"].map(lambda v: v is True).to_numpy(bool), 1 - PHONE_REPAIRED_DEDUCTION, 1.0)
        return cond * imei * rep
    return cond


def _target_factor(category: str, condition: str | None, attrs: dict[str, Any]) -> float:
    if category not in ("phone", "laptop"):
        return 1.0
    f = CONDITION_MULTIPLIERS.get(condition or "A", CONDITION_MULTIPLIERS["A"])
    if category == "phone":
        if attrs.get("imei_registered") is False:
            f *= 1 - PHONE_IMEI_UNREGISTERED_DEDUCTION
        if attrs.get("repaired") is True:
            f *= 1 - PHONE_REPAIRED_DEDUCTION
    return f


def _adjusted_values(df: pd.DataFrame, category: str, condition: str | None, attrs: dict[str, Any]) -> np.ndarray:
    """Normalize comparable prices to the target item."""
    vals = df["price_uzs"].to_numpy(float) * _target_factor(category, condition, attrs) / df["vf"].to_numpy(float)
    if category == "phone":
        target = _num(attrs.get("storage_gb"))
        if target:
            comp = df["storage_gb"].to_numpy(float)
            steps = np.where(np.isnan(comp), 0.0, np.log2(target / np.where(np.isnan(comp), target, comp)))
            vals = vals * np.power(1 + STORAGE_STEP_PREMIUM, steps)
    if category == "car":
        year = _num(attrs.get("year"))
        if year:
            comp = df["year"].to_numpy(float)
            diff = np.where(np.isnan(comp), 0.0, comp - year)
            vals = vals * np.power(1 - CAR_DEPRECIATION_PER_YEAR, diff)
    return vals


def _tiers(df: pd.DataFrame, category: str, model_norm: str, condition: str | None, district: str | None,
           attrs: dict[str, Any], lang: str) -> list[tuple[str, pd.Series]]:
    """Comparable tiers, strict → loose: (basis label, boolean mask)."""
    tiers: list[tuple[str, pd.Series]] = []
    a = attrs
    model_label = a.get("_model_label") or model_norm
    is_model = df["model_norm"] == model_norm
    if category == "phone":
        storage = _num(a.get("storage_gb"))
        if storage:
            same_storage = is_model & (df["storage_gb"] == storage)
            if condition:
                tiers.append((t("basis.model_storage_condition", lang, model=model_label, storage=int(storage),
                                condition=condition), same_storage & (df["condition"] == condition)))
            tiers.append((t("basis.model_storage", lang, model=model_label, storage=int(storage)), same_storage))
        tiers.append((t("basis.model", lang, model=model_label), is_model))
    elif category == "laptop":
        ram, ssd = _num(a.get("ram_gb")), _num(a.get("ssd_gb"))
        if ram and ssd and condition:
            tiers.append((t("basis.laptop_exact", lang, model=model_label, ram=int(ram), ssd=int(ssd),
                            condition=condition),
                          is_model & (df["ram_gb"] == ram) & (df["ssd_gb"] == ssd) & (df["condition"] == condition)))
        tiers.append((t("basis.model", lang, model=model_label), is_model))
        cls = cpu_class(a.get("cpu"))
        if cls is None and is_model.any():
            mode = df.loc[is_model, "cpu_class"].dropna()
            cls = mode.mode().iat[0] if not mode.empty else None
        if cls and ram:
            tiers.append((t("basis.laptop_class", lang, cpu=cls, ram=int(ram)),
                          (df["cpu_class"] == cls) & (df["ram_gb"] == ram)))
    elif category == "car":
        year, km, fuel = _num(a.get("year")), _num(a.get("mileage_km")), a.get("fuel")
        if year:
            m = is_model & ((df["year"] - year).abs() <= 1)
            if km is not None:
                m &= (df["mileage_km"] - km).abs() <= 30000
            if fuel:
                m &= df["fuel"] == fuel
            tiers.append((t("basis.car_exact", lang, model=model_label, year=int(year), fuel=fuel or "—"), m))
            tiers.append((t("basis.car_year2", lang, model=model_label, year=int(year)),
                          is_model & ((df["year"] - year).abs() <= 2)))
        tiers.append((t("basis.car_model", lang, model=model_label), is_model))
    elif category == "house":
        rooms, building = _num(a.get("rooms")), a.get("building")
        in_d = df["district"] == district if district else None
        if in_d is not None and rooms and building:
            tiers.append((t("basis.realty_drb", lang, district=district, rooms=int(rooms), building=building),
                          in_d & (df["rooms"] == rooms) & (df["building"] == building)))
        if in_d is not None and rooms:
            tiers.append((t("basis.realty_dr", lang, district=district, rooms=int(rooms)),
                          in_d & (df["rooms"] == rooms)))
        if in_d is not None:
            tiers.append((t("basis.realty_d", lang, district=district), in_d))
        if rooms:
            tiers.append((t("basis.realty_r", lang, rooms=int(rooms)), df["rooms"] == rooms))
    elif category == "rent":
        monthly = df["period"].isna() | (df["period"] == "monthly")
        rooms, furnished = _num(a.get("rooms")), a.get("furnished")
        in_d = df["district"] == district if district else None
        if in_d is not None and rooms and furnished is not None:
            ftxt = t("furnished.yes" if furnished else "furnished.no", lang)
            tiers.append((t("basis.rent_drf", lang, district=district, rooms=int(rooms), furnished=ftxt),
                          monthly & in_d & (df["rooms"] == rooms) & (df["furnished"] == furnished)))
        if in_d is not None and rooms:
            tiers.append((t("basis.realty_dr", lang, district=district, rooms=int(rooms)),
                          monthly & in_d & (df["rooms"] == rooms)))
        if rooms:
            tiers.append((t("basis.realty_r", lang, rooms=int(rooms)), monthly & (df["rooms"] == rooms)))
    return tiers


_SAMPLE_COLS = ["id", "brand", "model", "price_uzs", "price_usd", "condition", "district", "seller_type",
                "posted_at", "source_url", "attrs"]


def _nn(v: Any) -> Any:
    """pandas missing values (NaN/NaT/None) → None."""
    return None if not isinstance(v, dict) and pd.isna(v) else v


def _samples(frame: pd.DataFrame) -> list[dict[str, Any]]:
    cols = {c: [_nn(v) for v in frame[c].tolist()] for c in _SAMPLE_COLS}
    return [_sample({c: cols[c][i] for c in _SAMPLE_COLS}) for i in range(len(frame))]


def _sample(row: dict[str, Any]) -> dict[str, Any]:
    return {"listing_id": int(row["id"]), "title": " ".join(x for x in (row["brand"], row["model"]) if x),
            "price_uzs": round(float(row["price_uzs"])), "price_usd": round(float(row["price_usd"]), 2),
            "condition": row["condition"], "district": row["district"], "seller_type": row["seller_type"],
            "posted_at": row["posted_at"].to_pydatetime() if hasattr(row["posted_at"], "to_pydatetime")
            else row["posted_at"], "source_url": row["source_url"],
            "attrs": row["attrs"] if isinstance(row["attrs"], dict) else {}}


def estimate(db: Session, category: str, model: str | None = None, condition: str | None = None,
             district: str | None = None, attrs: dict[str, Any] | None = None, *, brand: str | None = None,
             exclude_id: int | None = None, lang: str = "en") -> Estimate:
    """Fair price for one item. Raises `NotEnoughData` when < 3 comparables.

    Results are memoized until the category's comparables cache expires.
    """
    key = (category, norm_model(model, brand), condition, district, exclude_id, lang,
           tuple(sorted((k, str(v)) for k, v in (attrs or {}).items())))
    load_frame(db, category)  # refreshes the frame (and clears stale memo entries) when expired
    hit = _memo.get(key)
    if hit is not None:
        return hit
    est = _estimate(db, category, model, condition, district, attrs, brand=brand, exclude_id=exclude_id, lang=lang)
    with _lock:
        _memo[key] = est
    return est


def _estimate(db: Session, category: str, model: str | None, condition: str | None, district: str | None,
              attrs: dict[str, Any] | None, *, brand: str | None, exclude_id: int | None, lang: str) -> Estimate:
    attrs = dict(attrs or {})
    district = normalize_district(district) or district
    model_norm = norm_model(model, brand)
    if category in ("phone", "laptop", "car") and not model_norm:
        raise AppError("model_required", "model is required for this category", 422)
    attrs["_model_label"] = model
    df = load_frame(db, category)
    if exclude_id is not None and not df.empty:
        df = df[df["id"] != exclude_id]
    if df.empty:
        raise NotEnoughData(0, lang)

    tiers = _tiers(df, category, model_norm, condition, district, attrs, lang)
    chosen: tuple[int, str, pd.Series] | None = None
    best: tuple[int, str, pd.Series] | None = None
    for i, (basis, mask) in enumerate(tiers):
        n = int(mask.sum())
        if n >= settings.MIN_COMPARABLES:
            chosen = (i, basis, mask)
            break
        if n >= 3 and (best is None or n > int(best[2].sum())):
            best = (i, basis, mask)
    low_conf = chosen is None
    if chosen is None:
        if best is None:
            most = max((int(m.sum()) for _, m in tiers), default=0)
            raise NotEnoughData(most, lang)
        chosen = best
    tier, basis, mask = chosen
    comp = df[mask]

    area = _num(attrs.get("area_m2")) if category == "house" else None
    if category == "house" and area:
        comp = comp[comp["area_m2"].notna() & (comp["area_m2"] > 0)]
        values = comp["price_uzs"].to_numpy(float) / comp["area_m2"].to_numpy(float)
        basis += t("basis.per_m2", lang)
    else:
        values = _adjusted_values(comp, category, condition, attrs)
    keep = np.ones(len(values), dtype=bool)
    if len(values) >= 10:
        lo, hi = np.percentile(values, [10, 90])
        keep = (values >= lo) & (values <= hi)
    vals = values[keep]
    kept = comp[keep]
    scale = area if (category == "house" and area) else 1.0
    fair = float(np.median(vals)) * scale
    p25, p75 = (float(x) * scale for x in np.percentile(vals, [25, 75]))

    by_seller = None
    st = kept["seller_type"].to_numpy()
    if (st == "shop").any() and (st == "private").any():
        by_seller = {s: round(float(np.median(vals[st == s])) * scale) for s in ("shop", "private")}

    n = len(comp)
    if low_conf:
        confidence = "low"
    elif tier == 0 and n >= 2 * settings.MIN_COMPARABLES:
        confidence = "high"
    else:
        confidence = "medium"
    margin = DEALER_MARGIN.get(category, 0.0)
    recent = comp.nlargest(5, "posted_at")
    rate = fx.rate()
    return Estimate(
        category=category, fair_price_uzs=round(fair), fair_price_usd=round(fair / rate, 2),
        range_uzs=(round(p25), round(p75)), fair_buy_price_uzs=round(fair * (1 - margin)),
        fair_buy_price_usd=round(fair * (1 - margin) / rate, 2), comparables=n, basis=basis, tier=tier,
        confidence=confidence, samples=_samples(recent),
        price_by_seller_type=by_seller,
        per_m2_uzs=round(float(np.median(vals))) if (category == "house" and area) else None,
    )


def spec_from(obj: Any) -> dict[str, Any]:
    """Pricing kwargs from any ORM row with category/model/condition/attrs."""
    return {"category": obj.category, "model": obj.model, "brand": getattr(obj, "brand", None),
            "condition": obj.condition, "district": getattr(obj, "district", None), "attrs": obj.attrs or {}}


def try_estimate(db: Session, **kw: Any) -> Estimate | None:
    """`estimate` that returns None instead of raising when data is missing."""
    try:
        return estimate(db, **kw)
    except AppError:
        return None


def assess_listing(db: Session, listing: Listing) -> Estimate | None:
    """Fair price of a listing excluding itself; stores fair price and discount on it."""
    est = try_estimate(db, **spec_from(listing), exclude_id=listing.id)
    if est is None:
        listing.fair_price_uzs = None
        listing.discount_pct = None
        return None
    listing.fair_price_uzs = est.fair_price_uzs
    listing.discount_pct = round((est.fair_price_uzs - listing.price_uzs) / est.fair_price_uzs * 100, 1)
    return est


def badge(price_uzs: float, fair_uzs: float, lang: str) -> tuple[float, str]:
    """(diff % vs market, human badge). Negative diff = below market."""
    diff = (price_uzs / fair_uzs - 1) * 100
    pct = abs(round(diff))
    if pct < 3:
        return round(diff, 1), t("badge.fair", lang)
    return round(diff, 1), t("badge.below" if diff < 0 else "badge.above", lang, pct=pct)
