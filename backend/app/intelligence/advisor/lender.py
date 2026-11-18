"""Lender & bazaar console (#20, #19): collateral valuation, live LTV monitoring, loan applications, market report.

Liquidation value = p25 × (1 − haircut[category]). Everything is computed from the same fair-price engine the
borrowers use, so bank and shop see the same numbers.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import activity, alerts
from app.core.config import CREDIT_PRODUCTS, LIQUIDATION_HAIRCUT, LTV_WATCH_MARGIN
from app.core.db import utcnow
from app.core.errors import AppError, forbidden, not_found
from app.core.i18n import register
from app.core.models import ActivityLog, Collateral, Company, InventoryItem, Listing, LoanApplication
from app.intelligence.advisor import finance
from app.intelligence.books import books
from app.intelligence.market import market, pricing, stock

register({
    "col.breach.t": {"uz": "LTV chegarasi buzildi: {name}", "ru": "Превышен LTV: {name}", "en": "LTV breach: {name}"},
    "col.breach.m": {"uz": "{item}: LTV {ltv}% (chegara {limit}%). Bozor qiymati {value}, qarz {balance}.",
                     "ru": "{item}: LTV {ltv}% (лимит {limit}%). Рынок {value}, долг {balance}.",
                     "en": "{item}: LTV {ltv}% (limit {limit}%). Market value {value}, balance {balance}."},
    "app.new.t": {"uz": "Yangi kredit arizasi: {company}", "ru": "Новая заявка на кредит: {company}",
                  "en": "New loan application: {company}"},
    "app.new.m": {"uz": "{product}: {amount}, {months} oy. Tayyorlik {score}/100.",
                  "ru": "{product}: {amount}, {months} мес. Готовность {score}/100.",
                  "en": "{product}: {amount}, {months} months. Readiness {score}/100."},
    "app.dec.t": {"uz": "Kredit arizasi: {status}", "ru": "Заявка на кредит: {status}",
                  "en": "Loan application: {status}"},
    "app.dec.m": {"uz": "{lender}: {amount} — {status}. {note}", "ru": "{lender}: {amount} — {status}. {note}",
                  "en": "{lender}: {amount} — {status}. {note}"},
})

_TME = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z0-9_]{3,})/(\d+)")


def _money_texts(title_key: str, msg_key: str, **kw: Any) -> dict[str, dict[str, str]]:
    from app.intelligence.b2b.exchange import _texts

    return _texts(title_key, msg_key, **kw)


# --------------------------------------------------------------------------- #
# Valuation                                                                     #
# --------------------------------------------------------------------------- #

def liquidation(est: pricing.Estimate, category: str) -> float:
    """p25 × (1 − haircut) — a conservative forced-sale value."""
    return round(est.range_uzs[0] * (1 - LIQUIDATION_HAIRCUT.get(category, 0.2)))


def valuation_dict(est: pricing.Estimate, category: str, qty: int = 1) -> dict[str, Any]:
    return {"category": category, "qty": qty, "fair_price_uzs": est.fair_price_uzs, "range_uzs": list(est.range_uzs),
            "fair_price_usd": est.fair_price_usd, "liquidation_value_uzs": liquidation(est, category),
            "haircut_pct": LIQUIDATION_HAIRCUT.get(category, 0.2) * 100, "total_market_value_uzs": est.fair_price_uzs
            * qty, "total_liquidation_value_uzs": liquidation(est, category) * qty, "confidence": est.confidence,
            "comparables": est.comparables, "basis": est.basis, "samples": est.samples}


def listing_from_url(db: Session, url: str) -> Listing:
    """Listing for a t.me/<channel>/<msg_id> link already in the DB (404 otherwise)."""
    from app.core.models import RawPost

    m = _TME.search(url or "")
    if not m:
        raise AppError("invalid_url", "Expected a t.me/<channel>/<message_id> link", 422)
    channel, msg_id = m.group(1), int(m.group(2))
    lst = db.scalar(select(Listing).join(RawPost, Listing.raw_post_id == RawPost.id).where(
        func.lower(RawPost.source) == channel.lower(), RawPost.msg_id == msg_id))
    if lst is None:
        lst = db.scalar(select(Listing).where(Listing.source_url.ilike(f"%t.me/{channel}/{msg_id}")))
    if lst is None:
        raise AppError("post_not_found", "This post is not in the market database", 404,
                       {"channel": channel, "msg_id": msg_id})
    return lst


def value_item(db: Session, lender: Company, body: dict[str, Any], lang: str) -> dict[str, Any]:
    """Value by parameters, by t.me link or by an applicant's inventory unit. Every call is logged."""
    qty = 1
    source: dict[str, Any] = {}
    if body.get("inventory_id"):
        it = db.get(InventoryItem, body["inventory_id"])
        if it is None:
            raise not_found("inventory", body["inventory_id"])
        applied = db.scalar(select(LoanApplication.id).where(LoanApplication.company_id == it.company_id,
                                                             LoanApplication.lender_id == lender.id))
        if not applied:
            raise forbidden("This unit does not belong to one of your applicants")
        spec, qty = pricing.spec_from(it), it.qty
        source = {"inventory_id": it.id, "borrower_id": it.company_id}
    elif body.get("url"):
        lst = listing_from_url(db, body["url"])
        spec = pricing.spec_from(lst)
        source = {"listing_id": lst.id, "listing_price_uzs": lst.price_uzs, "source_url": lst.source_url}
    else:
        if not body.get("category") and body.get("text"):
            # Free text ("malibu 2019", "iphone 13 128gb") -> structured item via the fast-input parser.
            from app.intelligence.market import inputs

            text = body["text"].strip()
            parsed = inputs.parse_text(db, text, None)
            if not parsed.get("category"):
                raise AppError("item_not_recognized", "Could not recognise an item in this text", 422, {"text": text})
            body = {**parsed, "attrs": parsed.get("attrs") or {}}
            source = {"text": text, "parsed_by": parsed["source"]}
        if not body.get("category"):
            raise AppError("item_required", "Send an item (category, model, attrs), text, a url or an inventory_id",
                           422)
        spec = {k: body.get(k) for k in ("category", "model", "brand", "condition", "district")}
        spec["attrs"] = body.get("attrs") or {}
    est = pricing.estimate(db, **spec, lang=lang)
    out = {**valuation_dict(est, spec["category"], qty), "source": source,
           "item": {k: spec.get(k) for k in ("category", "brand", "model", "condition", "district")}
           | {"attrs": spec.get("attrs") or {}},
           "value_change_30d_pct": change_30d(db, spec["category"], spec.get("model"))}
    activity.log(db, lender, "lender.valuation", "valuation", source.get("inventory_id") or source.get("listing_id"),
                 f"Valued {spec['category']} {spec.get('model') or ''}: {round(est.fair_price_uzs):,} so'm")
    out["valuations_this_month"] = valuations_count(db, lender)
    return out


def valuations_count(db: Session, lender: Company) -> int:
    start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count(ActivityLog.id)).where(ActivityLog.company_id == lender.id,
                                                              ActivityLog.action == "lender.valuation",
                                                              ActivityLog.created_at >= start)) or 0


# --------------------------------------------------------------------------- #
# Collateral portfolio                                                          #
# --------------------------------------------------------------------------- #

def change_30d(db: Session, category: str, model: str | None) -> float | None:
    """Median price change over the last ~30 days (weekly trend, first vs last point)."""
    model = model if category in ("phone", "laptop", "car") else None
    pts = market.trend(db, category, model, 45)
    if len(pts) < 2 or not pts[0]["median_price_uzs"]:
        return None
    return round((pts[-1]["median_price_uzs"] / pts[0]["median_price_uzs"] - 1) * 100, 1)


def revalue(db: Session, lender: Company, lang: str, create_alerts: bool = True) -> list[dict[str, Any]]:
    """Live revaluation of every collateral item (batched by identical spec)."""
    items = list(db.scalars(select(Collateral).where(Collateral.lender_id == lender.id).order_by(Collateral.id)))
    cache: dict[str, pricing.Estimate | None] = {}
    trend_cache: dict[tuple, float | None] = {}
    out = []
    for c in items:
        key = json.dumps([c.category, c.brand, c.model, c.condition, c.district, c.attrs], sort_keys=True, default=str)
        if key not in cache:
            cache[key] = pricing.try_estimate(db, category=c.category, model=c.model, brand=c.brand,
                                              condition=c.condition, district=c.district, attrs=c.attrs or {},
                                              lang=lang)
        est = cache[key]
        tkey = (c.category, c.model if c.category in ("phone", "laptop", "car") else None)
        if tkey not in trend_cache:
            trend_cache[tkey] = change_30d(db, c.category, c.model)
        row = {"id": c.id, "loan_application_id": c.loan_application_id, "borrower_name": c.borrower_name,
               "category": c.category, "brand": c.brand, "model": c.model, "condition": c.condition,
               "district": c.district, "attrs": c.attrs or {}, "qty": c.qty, "loan_balance_uzs": c.loan_balance_uzs,
               "ltv_limit": c.ltv_limit, "market_value_uzs": None, "liquidation_value_uzs": None, "ltv": None,
               "status": "no_data", "value_change_30d_pct": trend_cache[tkey], "basis": None, "confidence": None,
               "comparables": 0, "created_at": c.created_at}
        if est is not None:
            mv = est.fair_price_uzs * c.qty
            ltv = c.loan_balance_uzs / mv if mv else None
            status = "ok"
            if ltv is not None and ltv > c.ltv_limit:
                status = "breach"
            elif ltv is not None and ltv > c.ltv_limit - LTV_WATCH_MARGIN:
                status = "watch"
            row.update(market_value_uzs=round(mv), liquidation_value_uzs=liquidation(est, c.category) * c.qty,
                       ltv=round(ltv, 4) if ltv is not None else None, status=status, basis=est.basis,
                       confidence=est.confidence, comparables=est.comparables)
            if status == "breach" and create_alerts:
                key_a = f"collateral:{c.id}"
                if not alerts.exists_today(db, lender.id, "system", key_a):
                    item = " ".join(x for x in (c.brand, c.model) if x) or c.category
                    alerts.create(db, company_id=lender.id, type="system", severity="high", category=c.category,
                                  i18n=_money_texts("col.breach.t", "col.breach.m", name=c.borrower_name, item=item,
                                                    ltv=round(ltv * 100, 1), limit=round(c.ltv_limit * 100),
                                                    value_uzs=mv, balance_uzs=c.loan_balance_uzs),
                                  payload={"key": key_a, "collateral_id": c.id, "ltv": row["ltv"]}, commit=False)
        out.append(row)
    db.commit()
    return out


def collateral_summary(rows: list[dict[str, Any]], valuations: int) -> dict[str, Any]:
    valued = [r for r in rows if r["market_value_uzs"]]
    mv = sum(r["market_value_uzs"] for r in valued)
    bal = sum(r["loan_balance_uzs"] for r in rows)
    return {"items": len(rows), "total_loan_balance_uzs": round(bal), "total_market_value_uzs": round(mv),
            "total_liquidation_value_uzs": round(sum(r["liquidation_value_uzs"] for r in valued)),
            "portfolio_ltv": round(bal / mv, 4) if mv else None,
            "by_status": {s: sum(1 for r in rows if r["status"] == s) for s in ("ok", "watch", "breach", "no_data")},
            "by_category": {c: round(sum(r["market_value_uzs"] or 0 for r in rows if r["category"] == c))
                            for c in sorted({r["category"] for r in rows})},
            "valuations_this_month": valuations}


# --------------------------------------------------------------------------- #
# Loan applications                                                             #
# --------------------------------------------------------------------------- #

def build_snapshot(db: Session, company: Company, product: str, principal: float, months: int,
                   collateral_ids: list[int], lang: str) -> dict[str, Any]:
    """Verified-books snapshot a lender receives (frozen at submission)."""
    flags = books.audit_flags(db, company.id, lang)
    rows = stock.units(db, company, lang)
    c = finance.credit(db, company, principal, months, None, lang, product)
    pledged = [r for r in rows if r["inventory_id"] in set(collateral_ids)]
    return {
        "company": {"id": company.id, "name": company.name, "stir": company.stir, "role": company.role,
                    "district": company.district, "categories": company.categories},
        "loan_readiness": finance.loan_readiness(db, company, lang, flags),
        "cashflow": finance.cashflow(db, company.id, 6),
        "audit_summary": books.audit_summary(flags),
        "inventory": stock.summary(rows),
        "credit": {k: v for k, v in c.items() if k != "schedule"} | {"schedule_first_12": c["schedule"][:12]},
        "collateral": [{"inventory_id": r["inventory_id"], "model": r["model"], "condition": r["condition"],
                        "identifier": r["identifier"], "qty": r["qty"], "fair_price_uzs": r["fair_price_uzs"],
                        "range_uzs": r["range_uzs"]} for r in pledged],
        "collateral_market_value_uzs": round(sum((r["fair_price_uzs"] or 0) * r["qty"] for r in pledged)),
        "generated_at": utcnow().isoformat() + "Z",
    }


def submit_application(db: Session, company: Company, data: dict[str, Any], lang: str) -> LoanApplication:
    if not data.get("consent"):
        raise AppError("consent_required", "The borrower must consent to sharing the snapshot", 422)
    lender = db.get(Company, data["lender_id"])
    if lender is None or lender.role != "lender":
        raise not_found("lender", data["lender_id"])
    spec = CREDIT_PRODUCTS[data["product"]]
    if data["months"] > spec["max_months"]:
        raise AppError("term_too_long", f"At most {int(spec['max_months'])} months", 422)
    ids = data.get("collateral_inventory_ids") or []
    if ids:
        own = set(db.scalars(select(InventoryItem.id).where(InventoryItem.company_id == company.id,
                                                            InventoryItem.id.in_(ids))))
        if own != set(ids):
            raise AppError("inventory_not_found", "Some collateral units are not yours", 404,
                           {"inventory_ids": sorted(set(ids) - own)})
    snapshot = build_snapshot(db, company, data["product"], data["principal_uzs"], data["months"], ids, lang)
    app = LoanApplication(company_id=company.id, lender_id=lender.id, product=data["product"],
                          principal_uzs=data["principal_uzs"], months=data["months"], purpose=data["purpose"],
                          status="submitted", snapshot=snapshot, consent_at=utcnow())
    db.add(app)
    db.flush()
    from app.core.catalog import CREDIT_PRODUCT_LABELS

    alerts.create(db, company_id=lender.id, type="system", severity="info", category=None,
                  i18n={lg: {"title": _money_texts("app.new.t", "app.new.m", company=company.name)[lg]["title"],
                             "message": _money_texts("app.new.t", "app.new.m", company=company.name,
                                                     product=CREDIT_PRODUCT_LABELS[app.product][lg],
                                                     amount_uzs=app.principal_uzs, months=app.months,
                                                     score=snapshot["loan_readiness"]["score"])[lg]["message"]}
                        for lg in ("uz", "ru", "en")},
                  payload={"loan_application_id": app.id}, commit=False)
    activity.log(db, company, "loan_application.submit", "loan_application", app.id,
                 f"Applied to {lender.name}: {round(app.principal_uzs):,} so'm, {app.months} months", commit=False)
    db.commit()
    return app


def decide(db: Session, lender: Company, app_id: int, status: str, note: str | None) -> LoanApplication:
    app = db.get(LoanApplication, app_id)
    if app is None or app.lender_id != lender.id:
        raise not_found("loan_application", app_id)
    if app.status in ("approved", "rejected"):
        raise AppError("application_closed", "A final decision was already made", 409, {"status": app.status})
    app.status, app.decision_note = status, note
    labels = {"reviewing": {"uz": "ko'rib chiqilmoqda", "ru": "на рассмотрении", "en": "under review"},
              "approved": {"uz": "tasdiqlandi", "ru": "одобрена", "en": "approved"},
              "rejected": {"uz": "rad etildi", "ru": "отклонена", "en": "rejected"}}[status]
    alerts.create(db, company_id=app.company_id, type="system", severity="high" if status != "reviewing" else "info",
                  category=None,
                  i18n={lg: {"title": _money_texts("app.dec.t", "app.dec.m", status=labels[lg])[lg]["title"],
                             "message": _money_texts("app.dec.t", "app.dec.m", status=labels[lg], lender=lender.name,
                                                     amount_uzs=app.principal_uzs, note=note or "")[lg]["message"]}
                        for lg in ("uz", "ru", "en")},
                  payload={"loan_application_id": app.id, "status": status}, commit=False)
    activity.log(db, lender, f"loan_application.{status}", "loan_application", app.id,
                 f"Application #{app.id}: {status}", commit=False)
    db.commit()
    return app


# --------------------------------------------------------------------------- #
# Partner market report                                                         #
# --------------------------------------------------------------------------- #

def market_report(db: Session, category: str, district: str | None, days: int) -> dict[str, Any]:
    """Median price and volume per model and district, weekly trend, listing count by seller type."""
    since = utcnow() - timedelta(days=days)
    q = select(Listing.model, Listing.model_norm, Listing.brand, Listing.district, Listing.price_uzs,
               Listing.seller_type).where(Listing.category == category, Listing.posted_at >= since,
                                          Listing.is_duplicate.is_(False))
    if district:
        q = q.where(Listing.district == district)
    rows = db.execute(q).all()
    groups: dict[tuple, list[float]] = {}
    names: dict[str, str] = {}
    sellers: dict[str, int] = {}
    for model, norm, brand, dist, price, seller in rows:
        groups.setdefault((norm, dist or "—"), []).append(price)
        brand_in_model = brand and model and model.lower().startswith(brand.lower())
        names[norm] = model if brand_in_model else " ".join(x for x in (brand, model) if x)
        sellers[seller] = sellers.get(seller, 0) + 1
    by_model = sorted(({"model": names[n], "district": d, "listings": len(v),
                        "median_price_uzs": round(float(np.median(v)))} for (n, d), v in groups.items()),
                      key=lambda r: -r["listings"])[:100]
    return {"category": category, "district": district, "days": days, "total_listings": len(rows),
            "by_model_district": by_model, "weekly_trend": market.trend(db, category, None, days),
            "by_seller_type": sellers}


def report_xlsx(report: dict[str, Any]) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Models"
    ws.append(["model", "district", "listings", "median_price_uzs"])
    for r in report["by_model_district"]:
        ws.append([r["model"], r["district"], r["listings"], r["median_price_uzs"]])
    wt = wb.create_sheet("Weekly trend")
    wt.append(["week_start", "median_price_uzs", "listings"])
    for p in report["weekly_trend"]:
        wt.append([p["week_start"].isoformat(), p["median_price_uzs"], p["listings"]])
    st = wb.create_sheet("Seller types")
    st.append(["seller_type", "listings"])
    for k, v in report["by_seller_type"].items():
        st.append([k, v])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
