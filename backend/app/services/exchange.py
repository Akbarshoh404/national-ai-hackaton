"""B2B exchange (#19): requests for quotes, quote ranking, offers board, deals, ratings, demand.

Deals are booked into both companies' books and inventories in one DB transaction,
guarded by conditional status updates so the same deal is never booked twice.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.catalog import REALTY_CATEGORIES, norm_model, normalize_district
from app.db import utcnow
from app.errors import AppError, conflict, forbidden, not_found
from app.i18n import fmt_uzs, register, t
from app.models import Company, Deal, InventoryItem, Listing, Offer, Quote, Rating, Rfq, Transaction
from app.services import alerts, pricing

register({
    "rfq.new.title": {"uz": "Yangi so'rov: {item} × {qty}", "ru": "Новый запрос: {item} × {qty}",
                      "en": "New RFQ: {item} × {qty}"},
    "rfq.new.message": {"uz": "{company} {qty} dona {item} so'ramoqda. Maqsadli narx: {target}. Muddat: {deadline}.",
                        "ru": "{company} ищет {item}, {qty} шт. Целевая цена: {target}. Срок: {deadline}.",
                        "en": "{company} wants {qty} × {item}. Target price: {target}. Deadline: {deadline}."},
    "quote.new.title": {"uz": "Yangi taklif: {item}", "ru": "Новое предложение: {item}", "en": "New quote: {item}"},
    "quote.new.message": {"uz": "{supplier}: {price} × {qty} dona, {days} kunda yetkazadi.",
                          "ru": "{supplier}: {price} × {qty} шт., доставка {days} дн.",
                          "en": "{supplier}: {price} × {qty}, delivery in {days} days."},
    "deal.title": {"uz": "Bitim: {item} × {qty}", "ru": "Сделка: {item} × {qty}", "en": "Deal: {item} × {qty}"},
    "deal.message": {"uz": "{buyer} ← {seller}: {total}. Ikkala tomonning hisobiga yozildi.",
                     "ru": "{buyer} ← {seller}: {total}. Проведено в учёте обеих сторон.",
                     "en": "{buyer} ← {seller}: {total}. Booked in both companies' books."},
    "q.cheapest": {"uz": "Eng arzon taklif", "ru": "Самая низкая цена", "en": "Lowest price"},
    "q.vs_fair_below": {"uz": "Bozor xarid narxidan {pct}% arzon", "ru": "На {pct}% ниже рыночной закупочной цены",
                        "en": "{pct}% below the market purchase price"},
    "q.vs_fair_above": {"uz": "Bozor xarid narxidan {pct}% qimmat", "ru": "На {pct}% выше рыночной закупочной цены",
                        "en": "{pct}% above the market purchase price"},
    "q.rated": {"uz": "Reyting {rating} ({n} ta baho)", "ru": "Рейтинг {rating} ({n} оценок)",
                "en": "Rated {rating} ({n} ratings)"},
    "q.unrated": {"uz": "Hali baholanmagan (neytral 3.0)", "ru": "Ещё нет оценок (нейтрально 3.0)",
                  "en": "Not rated yet (neutral 3.0)"},
    "q.delivery": {"uz": "Yetkazish {days} kun", "ru": "Доставка {days} дн.", "en": "Delivery in {days} days"},
    "q.fastest": {"uz": "Eng tez yetkazish", "ru": "Самая быстрая доставка", "en": "Fastest delivery"},
    "q.partial": {"uz": "Faqat {have}/{need} dona", "ru": "Только {have} из {need} шт.",
                  "en": "Covers only {have}/{need} units"},
    "q.full": {"uz": "To'liq miqdor", "ru": "Полный объём", "en": "Covers the full quantity"},
    "q.above_retail": {"uz": "Chakana bozor narxidan qimmat (−15 ball)", "ru": "Дороже розничного рынка (−15 баллов)",
                       "en": "Above the retail market price (−15 points)"},
    "q.recommend": {"uz": "{supplier} taklifini tanlang: ball {score}/100. Eng qimmat taklifga nisbatan tejash: "
                          "{saving}.",
                    "ru": "Рекомендуем {supplier}: {score}/100 баллов. Экономия против самого дорогого: {saving}.",
                    "en": "Pick {supplier}: score {score}/100. Saving vs the most expensive quote: {saving}."},
    "match.district": {"uz": "Hudud mos: {d}", "ru": "Район совпадает: {d}", "en": "Same district: {d}"},
    "match.rooms": {"uz": "{n} xona", "ru": "{n}-комн.", "en": "{n} rooms"},
    "match.budget": {"uz": "Byudjetga mos ({pct}% maqsaddan)", "ru": "В бюджете ({pct}% от цели)",
                     "en": "Within budget ({pct}% of target)"},
    "match.model": {"uz": "Model mos", "ru": "Модель совпадает", "en": "Same model"},
    "match.split": {"uz": "Komissiya bo'linishi {mine}/{theirs}", "ru": "Раздел комиссии {mine}/{theirs}",
                    "en": "Commission split {mine}/{theirs}"},
})


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


def item_title(obj: Any) -> str:
    a = obj.attrs or {}
    parts = [obj.brand or "", obj.model or ""]
    if obj.category == "phone" and a.get("storage_gb"):
        parts.append(f"{a['storage_gb']}GB")
    if obj.category == "car" and a.get("year"):
        parts.append(str(a["year"]))
    if obj.condition and obj.category in ("phone", "laptop"):
        parts.append(f"({obj.condition})")
    return " ".join(p for p in parts if p)


def _texts(title_key: str, msg_key: str, **kw: Any) -> dict[str, dict[str, str]]:
    """Like alerts.texts, but money kwargs ending in _uzs are formatted per language."""
    out = {}
    for lang in ("uz", "ru", "en"):
        k = {key.removesuffix("_uzs"): (fmt_uzs(v, lang) if key.endswith("_uzs") else v) for key, v in kw.items()}
        out[lang] = {"title": t(title_key, lang, **k), "message": t(msg_key, lang, **k)}
    return out


def market_estimate(db: Session, obj: Any, lang: str = "en") -> pricing.Estimate | None:
    return pricing.try_estimate(db, **pricing.spec_from(obj), lang=lang)


# --------------------------------------------------------------------------- #
# RFQs and quotes                                                               #
# --------------------------------------------------------------------------- #

def create_rfq(db: Session, company: Company, data: dict[str, Any],
               lang: str) -> tuple[Rfq, pricing.Estimate | None, int]:
    """Create an RFQ, notify every company in the category; returns (rfq, market estimate, notified)."""
    if data["category"] in REALTY_CATEGORIES and not data.get("model"):
        rooms = (data.get("attrs") or {}).get("rooms")
        data["model"] = f"{rooms}-xonali" if rooms else data["category"]
    data["district"] = normalize_district(data.get("district")) or data.get("district")
    rfq = Rfq(company_id=company.id, **data)
    db.add(rfq)
    db.flush()
    est = market_estimate(db, rfq, lang)
    notified = alerts.notify_category(
        db, rfq.category, exclude_company_id=company.id, type="rfq", severity="info",
        i18n=_texts("rfq.new.title", "rfq.new.message", item=item_title(rfq), qty=rfq.qty, company=company.name,
                    target_uzs=rfq.target_unit_price, deadline=str(rfq.deadline or "—")),
        payload={"rfq_id": rfq.id, "key": f"rfq:{rfq.id}"})
    db.commit()
    return rfq, est, notified


def get_rfq_visible(db: Session, company: Company, rfq_id: int) -> Rfq:
    rfq = db.get(Rfq, rfq_id)
    if rfq is None:
        raise not_found("rfq", rfq_id)
    if rfq.company_id != company.id and rfq.category not in (company.categories or []):
        raise forbidden("This request is not in your categories")
    return rfq


def submit_quote(db: Session, company: Company, rfq_id: int, data: dict[str, Any]) -> Quote:
    rfq = get_rfq_visible(db, company, rfq_id)
    if rfq.company_id == company.id:
        raise forbidden("You cannot quote on your own request")
    if rfq.status != "open":
        raise conflict("rfq_closed", "This request is no longer open")
    if db.scalar(select(Quote.id).where(Quote.rfq_id == rfq_id, Quote.supplier_id == company.id)):
        raise conflict("quote_exists", "You already quoted on this request")
    q = Quote(rfq_id=rfq_id, supplier_id=company.id, **data)
    db.add(q)
    db.flush()
    alerts.create(db, company_id=rfq.company_id, type="quote", category=rfq.category, severity="info",
                  i18n=_texts("quote.new.title", "quote.new.message", item=item_title(rfq), supplier=company.name,
                              price_uzs=q.unit_price, qty=q.qty, days=q.delivery_days),
                  payload={"rfq_id": rfq.id, "quote_id": q.id}, commit=False)
    db.commit()
    return q


def rank_quotes(db: Session, company: Company, rfq_id: int, lang: str) -> dict[str, Any]:
    """Score quotes: 50% price, 20% rating, 15% delivery, 15% quantity; −15 above retail."""
    rfq = db.get(Rfq, rfq_id)
    if rfq is None:
        raise not_found("rfq", rfq_id)
    if rfq.company_id != company.id:
        raise forbidden("Only the buyer can see the quotes")
    quotes = list(db.scalars(select(Quote).where(Quote.rfq_id == rfq_id)))
    est = market_estimate(db, rfq, lang)
    out: dict[str, Any] = {"rfq_id": rfq_id, "fair_price_uzs": est.fair_price_uzs if est else None,
                           "fair_buy_price_uzs": est.fair_buy_price_uzs if est else None, "quotes": [],
                           "recommendation": None}
    if not quotes:
        return out
    min_price = min(q.unit_price for q in quotes)
    min_days = min(q.delivery_days for q in quotes)
    ranked = []
    for q in quotes:
        sup = db.get(Company, q.supplier_id)
        rep = reputation(db, q.supplier_id)
        price_s = 50 * min_price / q.unit_price
        rating_s = 20 * (rep["rating"] / 5 if rep["rating"] is not None else 0.6)
        delivery_s = 15 * (min_days + 1) / (q.delivery_days + 1)
        qty_s = 15 * min(1.0, q.qty / rfq.qty)
        penalty = -15.0 if est and q.unit_price > est.fair_price_uzs else 0.0
        reasons = []
        if q.unit_price == min_price:
            reasons.append(t("q.cheapest", lang))
        vs = None
        if est:
            vs = round((q.unit_price / est.fair_buy_price_uzs - 1) * 100, 1)
            if abs(vs) >= 0.5:
                reasons.append(t("q.vs_fair_below" if vs < 0 else "q.vs_fair_above", lang, pct=abs(round(vs))))
        reasons.append(t("q.rated", lang, rating=rep["rating"], n=rep["ratings_count"]) if rep["rating"] is not None
                       else t("q.unrated", lang))
        reasons.append(t("q.fastest", lang) if q.delivery_days == min_days and len(quotes) > 1
                       else t("q.delivery", lang, days=q.delivery_days))
        reasons.append(t("q.full", lang) if q.qty >= rfq.qty else t("q.partial", lang, have=q.qty, need=rfq.qty))
        if penalty:
            reasons.append(t("q.above_retail", lang))
        score = round(price_s + rating_s + delivery_s + qty_s + penalty, 1)
        ranked.append({"id": q.id, "rfq_id": q.rfq_id, "supplier": {"id": sup.id, "name": sup.name, **rep},
                       "unit_price_uzs": q.unit_price, "qty": q.qty, "delivery_days": q.delivery_days,
                       "note": q.note, "status": q.status, "score": score,
                       "score_breakdown": {"price": round(price_s, 1), "rating": round(rating_s, 1),
                                           "delivery": round(delivery_s, 1), "quantity": round(qty_s, 1),
                                           "penalty": penalty},
                       "vs_fair_purchase_pct": vs, "reasons": reasons})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    best = ranked[0]
    worst_price = max(q.unit_price for q in quotes)
    saving = (worst_price - best["unit_price_uzs"]) * min(rfq.qty, best["qty"])
    out["quotes"] = ranked
    out["recommendation"] = {"quote_id": best["id"], "supplier_name": best["supplier"]["name"],
                             "score": best["score"], "saving_vs_worst_uzs": round(saving),
                             "text": t("q.recommend", lang, supplier=best["supplier"]["name"], score=best["score"],
                                       saving=fmt_uzs(saving, lang))}
    return out


# --------------------------------------------------------------------------- #
# Deals                                                                         #
# --------------------------------------------------------------------------- #

def _move_inventory(db: Session, seller_id: int, buyer_id: int, item: Any, qty: int, unit_price: float,
                    district: str | None) -> None:
    """FIFO decrement on the seller, new stock line on the buyer."""
    if item.category in REALTY_CATEGORIES:
        return
    target = norm_model(item.model, item.brand)
    left = qty
    rows = db.scalars(select(InventoryItem).where(InventoryItem.company_id == seller_id,
                                                  InventoryItem.category == item.category,
                                                  InventoryItem.status == "in_stock")
                      .order_by(InventoryItem.acquired_at, InventoryItem.id))
    for row in rows:
        if left <= 0:
            break
        if norm_model(row.model, row.brand) != target or (item.condition and row.condition
                                                         and row.condition != item.condition):
            continue
        take = min(row.qty, left)
        row.qty -= take
        left -= take
        if row.qty == 0:
            row.status = "sold"
    db.add(InventoryItem(company_id=buyer_id, category=item.category, brand=item.brand, model=item.model,
                         condition=item.condition, attrs=item.attrs or {}, district=district, qty=qty,
                         unit_cost=unit_price, acquired_at=date.today()))


def book_deal(db: Session, *, buyer: Company, seller: Company, item: Any, qty: int, unit_price: float,
              rfq_id: int | None = None, quote_id: int | None = None, offer_id: int | None = None) -> Deal:
    """Create the deal, book both sides, move inventory and alert both companies (no commit)."""
    total = round(unit_price * qty)
    deal = Deal(buyer_id=buyer.id, seller_id=seller.id, rfq_id=rfq_id, quote_id=quote_id, offer_id=offer_id,
                category=item.category, brand=item.brand, model=item.model, condition=item.condition,
                attrs=item.attrs or {}, qty=qty, unit_price=unit_price, total=total, status="completed")
    db.add(deal)
    db.flush()
    common = {"date": date.today(), "item_category": item.category, "brand": item.brand, "model": item.model,
              "condition": item.condition, "attrs": item.attrs or {}, "qty": qty, "unit_price": unit_price,
              "total": total, "origin": "exchange", "deal_id": deal.id}
    db.add(Transaction(company_id=buyer.id, type="expense", category="stock_purchase", counterparty=seller.name,
                       note=f"B2B deal #{deal.id}", **common))
    db.add(Transaction(company_id=seller.id, type="income", category="sale", counterparty=buyer.name,
                       note=f"B2B deal #{deal.id}", **common))
    _move_inventory(db, seller.id, buyer.id, item, qty, unit_price, buyer.district)
    texts = _texts("deal.title", "deal.message", item=item_title(item), qty=qty, buyer=buyer.name, seller=seller.name,
                   total_uzs=total)
    for cid in (buyer.id, seller.id):
        alerts.create(db, company_id=cid, type="deal", category=item.category, severity="info", i18n=texts,
                      payload={"deal_id": deal.id}, commit=False)
    from app.services import books

    books._audit_cache.pop(buyer.id, None)
    books._audit_cache.pop(seller.id, None)
    return deal


def accept_quote(db: Session, company: Company, quote_id: int) -> Deal:
    """Buyer accepts a quote → deal booked in both books in one transaction."""
    q = db.get(Quote, quote_id)
    if q is None:
        raise not_found("quote", quote_id)
    rfq = db.get(Rfq, q.rfq_id)
    if rfq.company_id != company.id:
        raise forbidden("Only the buyer can accept a quote")
    # conditional updates make double-booking impossible even under concurrency
    if db.execute(update(Rfq).where(Rfq.id == rfq.id, Rfq.status == "open").values(status="awarded")).rowcount != 1:
        db.rollback()
        raise conflict("rfq_closed", "This request was already awarded or closed")
    if db.execute(update(Quote).where(Quote.id == q.id, Quote.status == "pending")
                  .values(status="accepted")).rowcount != 1:
        db.rollback()
        raise conflict("quote_not_pending", "This quote is no longer pending")
    db.execute(update(Quote).where(Quote.rfq_id == rfq.id, Quote.id != q.id).values(status="rejected"))
    seller = db.get(Company, q.supplier_id)
    deal = book_deal(db, buyer=company, seller=seller, item=rfq, qty=min(q.qty, rfq.qty), unit_price=q.unit_price,
                     rfq_id=rfq.id, quote_id=q.id)
    db.commit()
    return deal


# --------------------------------------------------------------------------- #
# Offers board                                                                  #
# --------------------------------------------------------------------------- #

def offer_view(db: Session, o: Offer, lang: str) -> dict[str, Any]:
    est = market_estimate(db, o, lang)
    diff, text = pricing.badge(o.unit_price, est.fair_price_uzs, lang) if est else (None, None)
    company = db.get(Company, o.company_id)
    return {"id": o.id, "company": {"id": company.id, "name": company.name, **reputation(db, company.id)},
            "kind": o.kind, "category": o.category, "brand": o.brand, "model": o.model, "condition": o.condition,
            "attrs": o.attrs, "qty": o.qty, "unit_price_uzs": o.unit_price, "district": o.district,
            "commission_split": o.commission_split, "note": o.note, "status": o.status, "created_at": o.created_at,
            "title": item_title(o), "market_fair_price_uzs": est.fair_price_uzs if est else None,
            "market_diff_pct": diff, "market_badge": text}


def buy_offer(db: Session, company: Company, offer_id: int, qty: int) -> Deal:
    o = db.get(Offer, offer_id)
    if o is None:
        raise not_found("offer", offer_id)
    if o.company_id == company.id:
        raise forbidden("You cannot buy your own offer")
    if o.kind == "cobroker":
        raise AppError("not_purchasable", "Co-brokerage offers are matched, not bought", 400)
    res = db.execute(update(Offer).where(Offer.id == o.id, Offer.status == "active", Offer.qty >= qty)
                     .values(qty=Offer.qty - qty))
    if res.rowcount != 1:
        db.rollback()
        raise conflict("insufficient_qty", "Offer is not active or has fewer units than requested",
                       {"available": o.qty if o.status == "active" else 0})
    db.refresh(o)
    if o.qty == 0:
        o.status = "sold_out"
    seller = db.get(Company, o.company_id)
    deal = book_deal(db, buyer=company, seller=seller, item=o, qty=qty, unit_price=o.unit_price, offer_id=o.id)
    db.commit()
    return deal


def matches(db: Session, company: Company, rfq_id: int, lang: str) -> list[dict[str, Any]]:
    """Board offers matching a request; for house/rent this is realtor co-brokerage."""
    rfq = get_rfq_visible(db, company, rfq_id)
    offers = db.scalars(select(Offer).where(Offer.status == "active", Offer.category == rfq.category,
                                            Offer.company_id != rfq.company_id))
    a = rfq.attrs or {}
    out = []
    for o in offers:
        reasons = []
        if rfq.category in REALTY_CATEGORIES:
            oa = o.attrs or {}
            if rfq.district and o.district != rfq.district:
                continue
            if rfq.district:
                reasons.append(t("match.district", lang, d=o.district))
            if a.get("rooms") and oa.get("rooms") != a.get("rooms"):
                continue
            if a.get("rooms"):
                reasons.append(t("match.rooms", lang, n=a["rooms"]))
            if rfq.target_unit_price:
                if o.unit_price > rfq.target_unit_price * 1.10:
                    continue
                reasons.append(t("match.budget", lang, pct=round(o.unit_price / rfq.target_unit_price * 100)))
            if o.commission_split is not None:
                theirs = round(o.commission_split * 100)
                reasons.append(t("match.split", lang, mine=100 - theirs, theirs=theirs))
        else:
            if norm_model(o.model, o.brand) != norm_model(rfq.model, rfq.brand):
                continue
            if rfq.condition and o.condition and o.condition != rfq.condition:
                continue
            reasons.append(t("match.model", lang))
            if rfq.target_unit_price:
                reasons.append(t("match.budget", lang, pct=round(o.unit_price / rfq.target_unit_price * 100)))
        out.append({**offer_view(db, o, lang), "match_reasons": reasons})
    out.sort(key=lambda x: x["unit_price_uzs"])
    return out


def rate_deal(db: Session, company: Company, deal_id: int, score: int, comment: str | None) -> Rating:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise not_found("deal", deal_id)
    if company.id not in (deal.buyer_id, deal.seller_id):
        raise forbidden("Only deal parties can rate")
    if db.scalar(select(Rating.id).where(Rating.deal_id == deal_id, Rating.rater_id == company.id)):
        raise conflict("already_rated", "You already rated this deal")
    ratee = deal.seller_id if company.id == deal.buyer_id else deal.buyer_id
    r = Rating(deal_id=deal_id, rater_id=company.id, ratee_id=ratee, score=score, comment=comment)
    db.add(r)
    db.commit()
    return r


def demand(db: Session, days: int, category: str | None, limit: int = 10) -> dict[str, Any]:
    """Most requested models (RFQs) and most listed models (Telegram) — for suppliers."""
    since = utcnow() - timedelta(days=days)
    q = select(Rfq).where(Rfq.created_at >= since)
    if category:
        q = q.where(Rfq.category == category)
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for r in db.scalars(q):
        key = (r.category, norm_model(r.model, r.brand))
        e = agg.setdefault(key, {"category": r.category, "model": item_title(r).replace(f"({r.condition})", "").strip(),
                                 "requests": 0, "units": 0})
        e["requests"] += 1
        e["units"] += r.qty
    requested = sorted(agg.values(), key=lambda e: (e["requests"], e["units"]), reverse=True)[:limit]
    lq = (select(Listing.category, Listing.model_norm, func.max(Listing.brand), func.max(Listing.model), func.count(),
                 func.avg(Listing.price_uzs))
          .where(Listing.posted_at >= since, Listing.is_duplicate.is_(False), Listing.model_norm != "")
          .group_by(Listing.category, Listing.model_norm).order_by(func.count().desc()).limit(limit))
    if category:
        lq = lq.where(Listing.category == category)
    listed = [{"category": c, "model": " ".join(x for x in (b, m) if x), "listings": int(n),
               "avg_price_uzs": round(float(avg))} for c, _, b, m, n, avg in db.execute(lq).all()]
    return {"days": days, "most_requested": requested, "most_listed": listed}
