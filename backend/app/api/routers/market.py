"""Market engine (#19): feed, live stream, pricing desk, radar, trends, heatmap, yield."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.schemas.common import Category, Page
from app.api.schemas.inputs import LinkIn, LinkPriceOut
from app.api.schemas.market import (
    AskingComparison,
    HeatmapOut,
    ListingOut,
    MarketStats,
    ModelSuggestion,
    PriceEstimateOut,
    PriceRequest,
    RentalYieldOut,
    RentalYieldRequest,
    TrendOut,
)
from app.core.catalog import norm_model, normalize_district
from app.core.config import RESALE_HANDLING_PCT
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.models import Listing
from app.core.sse import sse_response
from app.intelligence.market import inputs, market, pricing, stock

router = APIRouter(prefix="/market", tags=["market (#19)"])


def listing_out(lst: Listing) -> ListingOut:
    out = ListingOut.model_validate(lst)
    out.title = market.listing_title(lst)
    return out


def estimate_out(est: pricing.Estimate, asking: float | None = None, lang: str = "uz") -> PriceEstimateOut:
    out = PriceEstimateOut(
        category=est.category, fair_price_uzs=est.fair_price_uzs, fair_price_usd=est.fair_price_usd,
        range_uzs=est.range_uzs, fair_buy_price_uzs=est.fair_buy_price_uzs,
        fair_buy_price_usd=est.fair_buy_price_usd, comparables=est.comparables, basis=est.basis,
        confidence=est.confidence, samples=est.samples, price_by_seller_type=est.price_by_seller_type,
        per_m2_uzs=est.per_m2_uzs)
    if asking:
        diff, text = pricing.badge(asking, est.fair_price_uzs, lang)
        out.asking = AskingComparison(asking_price_uzs=asking, diff_pct=diff, badge=text)
    return out


@router.get("/listings", response_model=Page[ListingOut])
def market_listings(
    db: DbDep, company: CompanyDep, category: Category | None = None, model: str | None = None,
    district: str | None = None, condition: str | None = None,
    seller_type: Literal["shop", "private"] | None = None, min_price: float | None = None,
    max_price: float | None = None, cursor: str | None = None, limit: int = Query(30, ge=1, le=200),
    since_id: int | None = Query(None, description="Polling fallback: only listings with id > since_id"),
) -> Page[ListingOut]:
    """Market feed (newest first) with cursor pagination. Prices filter on UZS."""
    q = select(Listing).where(Listing.is_duplicate.is_(False))
    if category:
        q = q.where(Listing.category == category)
    if model:
        q = q.where(Listing.model_norm.contains(norm_model(model)))
    if district:
        q = q.where(Listing.district == (normalize_district(district) or district))
    if condition:
        q = q.where(Listing.condition == condition)
    if seller_type:
        q = q.where(Listing.seller_type == seller_type)
    if min_price is not None:
        q = q.where(Listing.price_uzs >= min_price)
    if max_price is not None:
        q = q.where(Listing.price_uzs <= max_price)
    if since_id is not None:
        q = q.where(Listing.id > since_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(Listing.id < int(cursor))
    rows = list(db.scalars(q.order_by(Listing.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[listing_out(r) for r in rows[:limit]], next_cursor=nxt, total=total)


@router.get("/stream", response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}})
async def market_stream(request: Request, company: CompanyDep) -> StreamingResponse:
    """Live SSE feed: `listing.created` and `alert.created` for the company's categories."""
    return sse_response(request, company, {"listing.created", "alert.created"})


@router.get("/stats", response_model=MarketStats)
def market_stats(db: DbDep, _: CompanyDep) -> MarketStats:
    return MarketStats(**market.stats(db))


@router.post("/price", response_model=PriceEstimateOut)
def market_price(body: PriceRequest, db: DbDep, _: CompanyDep, lang: LangDep) -> PriceEstimateOut:
    """Pricing desk: fair price, range, trade-in price, comparables and samples."""
    est = pricing.estimate(db, body.category, body.model, body.condition, body.district, body.attrs,
                           brand=body.brand, lang=lang)
    return estimate_out(est, body.asking_price_uzs, lang)


@router.post("/price-from-link", response_model=LinkPriceOut)
async def market_price_from_link(body: LinkIn, db: DbDep, _: CompanyDep, lang: LangDep) -> LinkPriceOut:
    """Price a t.me/<channel>/<msg_id> post: from the DB, or fetched read-only when the Telegram worker is on."""
    lst, fetched = await inputs.listing_for_link(db, body.url)
    priced = inputs.price_listing(db, lst, lang)
    return LinkPriceOut(listing=listing_out(lst), estimate=estimate_out(priced["estimate"], lang=lang),
                        diff_pct=priced["diff_pct"], badge=priced["badge"], fetched=fetched)


@router.get("/sourcing-radar", response_model=Page[ListingOut])
def market_sourcing_radar(db: DbDep, company: CompanyDep, lang: LangDep, category: Category | None = None,
                          min_discount_pct: float = Query(15, ge=0, le=90), days: int = Query(7, ge=1, le=30),
                          limit: int = Query(50, ge=1, le=200)) -> Page[ListingOut]:
    """Listings priced well below their fair price (best first)."""
    cats = [category] if category else (company.categories or [])
    rows = market.sourcing_radar(db, cats, min_discount_pct, days, limit)
    base = stock.days_to_sell_base(db, company.id, lang)
    items = []
    for r in rows:
        out = listing_out(r)
        if r.fair_price_uzs:
            out.expected_resale_margin_uzs = round(r.fair_price_uzs * (1 - RESALE_HANDLING_PCT) - r.price_uzs)
        out.expected_days_to_sell = base.get(r.category, (None, ""))[0]
        items.append(out)
    return Page(items=items, next_cursor=None, total=len(rows))


@router.get("/trend", response_model=TrendOut)
def market_trend(db: DbDep, _: CompanyDep, category: Category, model: str | None = None,
                 days: int = Query(60, ge=7, le=365)) -> TrendOut:
    """Weekly median price and listing count."""
    pts = market.trend(db, category, model, days)
    change = None
    if len(pts) >= 2 and pts[0]["median_price_uzs"]:
        change = round((pts[-1]["median_price_uzs"] / pts[0]["median_price_uzs"] - 1) * 100, 1)
    return TrendOut(category=category, model=model, points=pts, change_pct=change)


@router.get("/models", response_model=list[ModelSuggestion])
def market_models(db: DbDep, _: CompanyDep, category: Category, q: str | None = None,
                  limit: int = Query(20, ge=1, le=100)) -> list[ModelSuggestion]:
    """Model-name autocomplete sorted by listing count."""
    return [ModelSuggestion(**m) for m in market.models(db, category, q, limit)]


@router.post("/rental-yield", response_model=RentalYieldOut)
def market_rental_yield(body: RentalYieldRequest, db: DbDep, _: CompanyDep, lang: LangDep) -> RentalYieldOut:
    """Portfolio yield analyzer: price, rent, gross/net yield and payback."""
    return RentalYieldOut(**market.rental_yield(db, body.district, body.rooms, body.area_m2, body.furnished, lang))


@router.get("/heatmap", response_model=HeatmapOut)
def market_heatmap(db: DbDep, _: CompanyDep, category: Literal["house", "rent"] = "house") -> HeatmapOut:
    """Median price per m² (house) or monthly rent (rent) per Tashkent district."""
    return HeatmapOut(category=category, cells=market.heatmap(db, category))
