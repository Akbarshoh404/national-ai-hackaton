"""B2B exchange (#19): RFQs, quotes, offers, deals, ratings, demand."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, or_, select

from app.api.routers.market import estimate_out
from app.api.schemas.common import Category, OkResponse, Page
from app.api.schemas.exchange import (
    BuyIn,
    CounterIn,
    DealOut,
    DemandOut,
    OfferIn,
    OfferKind,
    OfferMatch,
    OfferOut,
    QuoteIn,
    QuoteOut,
    RankedQuotes,
    RatingIn,
    RatingOut,
    RespondIn,
    RfqCreated,
    RfqIn,
    RfqOut,
)
from app.core import activity
from app.core.catalog import normalize_district
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.errors import AppError, forbidden, not_found
from app.core.models import Company, Deal, Offer, Quote, Rating, Rfq
from app.intelligence.b2b import exchange

router = APIRouter(prefix="/exchange", tags=["B2B exchange (#19)"])


def rfq_out(db: DbDep, rfq: Rfq, me: Company) -> RfqOut:
    out = RfqOut.model_validate(rfq)
    out.company_name = db.get(Company, rfq.company_id).name
    out.quotes_count = db.scalar(select(func.count(Quote.id)).where(Quote.rfq_id == rfq.id)) or 0
    mine = db.scalar(select(Quote).where(Quote.rfq_id == rfq.id, Quote.supplier_id == me.id))
    out.my_quote_id = mine.id if mine else None
    out.my_quote = QuoteOut.model_validate(mine) if mine else None
    return out


def deal_out(db: DbDep, d: Deal, me: Company) -> DealOut:
    out = DealOut.model_validate(d)
    out.buyer_name = db.get(Company, d.buyer_id).name
    out.seller_name = db.get(Company, d.seller_id).name
    out.my_rating = db.scalar(select(Rating.score).where(Rating.deal_id == d.id, Rating.rater_id == me.id))
    return out


@router.post("/rfqs", response_model=RfqCreated, status_code=201)
def exchange_create_rfq(body: RfqIn, db: DbDep, company: CompanyDep, lang: LangDep) -> RfqCreated:
    """Post a request for quotes; every company in the category is alerted."""
    if body.category in ("phone", "laptop", "car") and not body.model:
        raise AppError("model_required", "model is required for this category", 422)
    rfq, est, notified = exchange.create_rfq(db, company, body.model_dump(), lang)
    activity.log(db, company, "rfq.create", "rfq", rfq.id, f"RFQ {rfq.model} × {rfq.qty}")
    return RfqCreated(rfq=rfq_out(db, rfq, company), market=estimate_out(est, lang=lang) if est else None,
                      notified_companies=notified)


@router.get("/rfqs", response_model=Page[RfqOut])
def exchange_list_rfqs(db: DbDep, company: CompanyDep, scope: Literal["mine", "incoming"] = "incoming",
                       status: Literal["open", "awarded", "closed"] | None = None, cursor: str | None = None,
                       limit: int = Query(50, ge=1, le=200)) -> Page[RfqOut]:
    """`mine`: my requests. `incoming`: open requests in my categories from others."""
    q = select(Rfq)
    if scope == "mine":
        q = q.where(Rfq.company_id == company.id)
    else:
        q = q.where(Rfq.company_id != company.id, Rfq.category.in_(company.categories or []))
        status = status or "open"
    if status:
        q = q.where(Rfq.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(Rfq.id < int(cursor))
    rows = list(db.scalars(q.order_by(Rfq.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[rfq_out(db, r, company) for r in rows[:limit]], next_cursor=nxt, total=total)


@router.get("/rfqs/{rfq_id}", response_model=RfqOut)
def exchange_get_rfq(rfq_id: int, db: DbDep, company: CompanyDep) -> RfqOut:
    return rfq_out(db, exchange.get_rfq_visible(db, company, rfq_id), company)


@router.post("/rfqs/{rfq_id}/quotes", response_model=QuoteOut, status_code=201)
def exchange_submit_quote(rfq_id: int, body: QuoteIn, db: DbDep, company: CompanyDep) -> QuoteOut:
    """Supplier quotes on a request; the buyer gets an alert."""
    q = exchange.submit_quote(db, company, rfq_id, body.model_dump())
    activity.log(db, company, "quote.submit", "quote", q.id,
                 f"Quote on RFQ #{rfq_id}: {round(q.unit_price):,} × {q.qty}")
    return QuoteOut.model_validate(q)


@router.get("/rfqs/{rfq_id}/quotes", response_model=RankedQuotes)
def exchange_ranked_quotes(rfq_id: int, db: DbDep, company: CompanyDep, lang: LangDep) -> RankedQuotes:
    """Quotes ranked by price (50%), rating (20%), delivery (15%), quantity (15%). Buyer only."""
    return RankedQuotes(**exchange.rank_quotes(db, company, rfq_id, lang))


@router.post("/quotes/{quote_id}/accept", response_model=DealOut)
def exchange_accept_quote(quote_id: int, db: DbDep, company: CompanyDep) -> DealOut:
    """Accept a quote → deal booked in both companies' books, inventory moved."""
    deal = exchange.accept_quote(db, company, quote_id)
    activity.log(db, company, "quote.accept", "deal", deal.id, f"Deal #{deal.id}: {deal.model} × {deal.qty}")
    return deal_out(db, deal, company)


@router.post("/quotes/{quote_id}/counter", response_model=QuoteOut)
def exchange_counter_quote(quote_id: int, body: CounterIn, db: DbDep, company: CompanyDep) -> QuoteOut:
    """Buyer counters a quote once; the supplier is alerted."""
    q = exchange.counter_quote(db, company, quote_id, body.unit_price, body.note)
    activity.log(db, company, "quote.counter", "quote", q.id, f"Counter {round(body.unit_price):,} on quote #{q.id}")
    return QuoteOut.model_validate(q)


@router.post("/quotes/{quote_id}/respond", response_model=QuoteOut)
def exchange_respond_counter(quote_id: int, body: RespondIn, db: DbDep, company: CompanyDep) -> QuoteOut:
    """Supplier accepts the counter (price = counter) or sets a final price; the quote returns to pending."""
    q = exchange.respond_counter(db, company, quote_id, body.accept, body.unit_price)
    activity.log(db, company, "quote.respond", "quote", q.id,
                 f"{'Accepted' if body.accept else 'Final price'} {round(q.unit_price):,} on quote #{q.id}")
    return QuoteOut.model_validate(q)


@router.get("/deals/{deal_id}/document", response_class=HTMLResponse,
            responses={200: {"content": {"text/html": {}, "application/pdf": {}}}})
def exchange_deal_document(deal_id: int, db: DbDep, company: CompanyDep, lang: LangDep,
                           format: Literal["html", "pdf"] = "html") -> Response:
    """Deal act / receipt for both parties (not a tax invoice — issue the e-invoice in Didox/Soliq)."""
    d = db.get(Deal, deal_id)
    if d is None or company.id not in (d.buyer_id, d.seller_id):
        raise not_found("deal", deal_id)
    doc = exchange.deal_document_html(db, d, lang)
    if format == "pdf":
        from app.core.pdf import render_pdf

        pdf = render_pdf(doc)
        if pdf is not None:
            return Response(pdf, media_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="deal_{d.id}.pdf"'})
        return HTMLResponse(doc, headers={"X-PDF-Fallback": "weasyprint-not-installed"})
    return HTMLResponse(doc)


@router.get("/rfqs/{rfq_id}/matches", response_model=list[OfferMatch])
def exchange_rfq_matches(rfq_id: int, db: DbDep, company: CompanyDep, lang: LangDep) -> list[OfferMatch]:
    """Board offers matching a request (co-brokerage for house/rent)."""
    return [OfferMatch(**m) for m in exchange.matches(db, company, rfq_id, lang)]


@router.post("/offers", response_model=OfferOut, status_code=201)
def exchange_create_offer(body: OfferIn, db: DbDep, company: CompanyDep, lang: LangDep) -> OfferOut:
    if body.category in ("phone", "laptop", "car") and not body.model:
        raise AppError("model_required", "model is required for this category", 422)
    if body.kind == "cobroker" and body.category not in ("house", "rent"):
        raise AppError("invalid_kind", "cobroker offers are for house/rent", 422)
    data = body.model_dump()
    if not data["model"]:
        rooms = data["attrs"].get("rooms")
        data["model"] = f"{rooms}-xonali" if rooms else body.category
    data["district"] = normalize_district(data["district"]) or data["district"] or company.district
    o = Offer(company_id=company.id, **data)
    db.add(o)
    db.flush()
    activity.log(db, company, "offer.create", "offer", o.id, f"{o.kind} offer {o.model} × {o.qty}")
    return OfferOut(**exchange.offer_view(db, o, lang))


@router.get("/offers", response_model=Page[OfferOut])
def exchange_list_offers(db: DbDep, company: CompanyDep, lang: LangDep, kind: OfferKind | None = None,
                         category: Category | None = None, district: str | None = None, mine: bool = False,
                         cursor: str | None = None, limit: int = Query(50, ge=1, le=200)) -> Page[OfferOut]:
    """Offer board with a market badge on every offer."""
    q = select(Offer).where(Offer.company_id == company.id if mine else Offer.status == "active")
    if kind:
        q = q.where(Offer.kind == kind)
    if category:
        q = q.where(Offer.category == category)
    if district:
        q = q.where(Offer.district == (normalize_district(district) or district))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(Offer.id < int(cursor))
    rows = list(db.scalars(q.order_by(Offer.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[OfferOut(**exchange.offer_view(db, o, lang)) for o in rows[:limit]], next_cursor=nxt,
                total=total)


@router.delete("/offers/{offer_id}", response_model=OkResponse)
def exchange_withdraw_offer(offer_id: int, db: DbDep, company: CompanyDep) -> OkResponse:
    o = db.get(Offer, offer_id)
    if o is None:
        raise not_found("offer", offer_id)
    if o.company_id != company.id:
        raise forbidden("Not your offer")
    o.status = "withdrawn"
    activity.log(db, company, "offer.withdraw", "offer", o.id, f"Offer {o.model} withdrawn")
    return OkResponse()


@router.post("/offers/{offer_id}/buy", response_model=DealOut)
def exchange_buy_offer(offer_id: int, body: BuyIn, db: DbDep, company: CompanyDep) -> DealOut:
    """Buy from an offer → deal booked like an accepted quote."""
    deal = exchange.buy_offer(db, company, offer_id, body.qty)
    activity.log(db, company, "offer.buy", "deal", deal.id, f"Bought {deal.model} × {deal.qty}")
    return deal_out(db, deal, company)


@router.get("/deals", response_model=Page[DealOut])
def exchange_list_deals(db: DbDep, company: CompanyDep, rfq_id: int | None = None, cursor: str | None = None,
                        limit: int = Query(50, ge=1, le=200)) -> Page[DealOut]:
    """My deals (as buyer or seller), newest first; `rfq_id` narrows to the deal booked on one request."""
    q = select(Deal).where(or_(Deal.buyer_id == company.id, Deal.seller_id == company.id))
    if rfq_id is not None:
        q = q.where(Deal.rfq_id == rfq_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(Deal.id < int(cursor))
    rows = list(db.scalars(q.order_by(Deal.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[deal_out(db, d, company) for d in rows[:limit]], next_cursor=nxt, total=total)


@router.post("/deals/{deal_id}/rate", response_model=RatingOut, status_code=201)
def exchange_rate_deal(deal_id: int, body: RatingIn, db: DbDep, company: CompanyDep) -> RatingOut:
    r = exchange.rate_deal(db, company, deal_id, body.score, body.comment)
    activity.log(db, company, "deal.rate", "deal", deal_id, f"Rated deal #{deal_id}: {body.score}/5")
    return RatingOut.model_validate(r)


@router.get("/demand", response_model=DemandOut)
def exchange_demand(db: DbDep, _: CompanyDep, days: int = Query(30, ge=1, le=365),
                    category: Category | None = None) -> DemandOut:
    """Most requested (RFQs) and most listed (Telegram) models — for suppliers."""
    return DemandOut(**exchange.demand(db, days, category))
