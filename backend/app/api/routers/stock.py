"""Stock command center (Narxlar): rated units, summary tiles, bulk reprice, surplus listing, exports."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.schemas.common import Category, Page
from app.api.schemas.exchange import OfferOut
from app.api.schemas.stock import ListOnExchangeIn, Rating, RepriceIn, RepriceOut, StockSummary, StockUnit
from app.core import activity
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.errors import AppError
from app.intelligence.b2b import exchange
from app.intelligence.market import stock

router = APIRouter(prefix="/stock", tags=["stock command center (#19, #26)"])
FILE_RESPONSES = {200: {"content": {"text/csv": {}, "application/vnd.openxmlformats-officedocument."
                                                                 "spreadsheetml.sheet": {}}}}


@router.get("/units", response_model=Page[StockUnit])
def stock_units(db: DbDep, company: CompanyDep, lang: LangDep, store_id: int | None = None,
                category: Category | None = None, rating: Rating | None = None, aging_only: bool = False,
                cursor: str | None = None, limit: int = Query(100, ge=1, le=500)) -> Page[StockUnit]:
    """Every unit in stock rated against the live market, with a suggested price and action."""
    rows = stock.units(db, company, lang, store_id=store_id, category=category)
    if rating:
        rows = [r for r in rows if r["rating"] == rating]
    if aging_only:
        rows = [r for r in rows if r["days_in_stock"] > stock.AGING_DAYS]
    start = int(cursor) if cursor else 0
    page = rows[start:start + limit]
    nxt = str(start + limit) if start + limit < len(rows) else None
    return Page(items=[StockUnit(**r) for r in page], next_cursor=nxt, total=len(rows))


@router.get("/summary", response_model=StockSummary)
def stock_summary(db: DbDep, company: CompanyDep, lang: LangDep, store_id: int | None = None) -> StockSummary:
    """Top tiles: stock at cost and at market, overpriced and aging units, margin at risk."""
    return StockSummary(**stock.summary(stock.units(db, company, lang, store_id=store_id)))


@router.post("/reprice", response_model=RepriceOut)
def stock_reprice(body: RepriceIn, db: DbDep, company: CompanyDep, lang: LangDep) -> RepriceOut:
    """Bulk reprice in one DB transaction (explicit prices or each unit's suggested price)."""
    if body.items:
        prices = {i.inventory_id: i.new_price_uzs for i in body.items}
    else:
        rows = stock.units(db, company, lang, ids=body.inventory_ids)
        found = {r["inventory_id"] for r in rows}
        missing = sorted(set(body.inventory_ids or []) - found)
        if missing:
            raise AppError("inventory_not_found", "Some units are not in your stock", 404, {"inventory_ids": missing})
        prices = {r["inventory_id"]: r["suggested_price_uzs"] for r in rows if r["suggested_price_uzs"]}
    ids = stock.reprice(db, company, prices)
    activity.log(db, company, "stock.reprice", "inventory", ids[0] if len(ids) == 1 else None,
                 f"Repriced {len(ids)} units", commit=False)
    db.commit()
    rows = stock.units(db, company, lang, ids=ids)
    return RepriceOut(updated=len(ids), units=[StockUnit(**r) for r in rows])


@router.post("/list-on-exchange", response_model=list[OfferOut], status_code=201)
def stock_list_on_exchange(body: ListOnExchangeIn, db: DbDep, company: CompanyDep, lang: LangDep) -> list[OfferOut]:
    """Create `surplus` offers from (aging) units; identical units are grouped into one offer."""
    offers = stock.list_on_exchange(db, company, body.inventory_ids, body.unit_price_uzs, lang)
    activity.log(db, company, "stock.list_on_exchange", "offer", None,
                 f"Listed {len(body.inventory_ids)} units as {len(offers)} surplus offers", commit=False)
    db.commit()
    return [OfferOut(**exchange.offer_view(db, o, lang)) for o in offers]


@router.get("/export", response_class=Response, responses=FILE_RESPONSES)
def stock_export(db: DbDep, company: CompanyDep, lang: LangDep,
                 format: Literal["xlsx", "csv", "1c"] = "xlsx", store_id: int | None = None) -> Response:
    """Export rated stock to Excel, CSV or a 1C import CSV."""
    rows = stock.units(db, company, lang, store_id=store_id)
    data, media, ext = stock.export_rows(rows, format, stock.STOCK_COLUMNS, stock.STOCK_1C, "Stock")
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="stock.{ext}"'})
