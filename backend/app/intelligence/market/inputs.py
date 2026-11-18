"""Fast inputs (#19, #26): free text, voice, t.me link, IMEI → a structured, priceable item.

The LLM (same field schema as the extractor) is optional; the rule parser always works and is the fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import llm
from app.core.catalog import CATEGORIES, normalize_district
from app.core.config import settings
from app.core.errors import AppError
from app.core.models import Listing
from app.data_pipeline import extractor
from app.intelligence.market import pricing
from app.intelligence.market.imei import load_tac, luhn_digit

REQUIRED: dict[str, list[str]] = {
    "phone": ["model", "storage_gb", "condition"],
    "laptop": ["model", "ram_gb", "ssd_gb", "condition"],
    "car": ["model", "year", "mileage_km"],
    "house": ["district", "rooms", "area_m2"],
    "rent": ["district", "rooms"],
}
_VARIANT = re.compile(r"\b(pro max|pro|max|plus|mini|ultra|lite)\b", re.I)
_RENT = re.compile(r"(ijara|arenda|аренд|сдаю|сдается|mebel|мебел|oyiga|в месяц|kunlik|посуточ)", re.I)
_REALTY = re.compile(r"(\d)\s*[- ]?\s*(xona|xonali|комн|к\b)|\b(kv|m2|m²|м2|кв)\b", re.I)
_MILEAGE = re.compile(r"(\d{1,3}(?:[ .]\d{3})*|\d+(?:[.,]\d+)?)\s*(ming|тыс|k)?\s*(km|км)?\s*(probeg|пробег)|"
                      r"(probeg|пробег)\s*[:\-]?\s*(\d{1,3}(?:[ .]\d{3})*|\d+)\s*(ming|тыс|k)?|"
                      r"(\d{1,3}(?:[ .]\d{3})+|\d{4,6})\s*(km|км)\b", re.I)


def _known(db: Session, cats: list[str]) -> list[tuple[str, str, str | None, str]]:
    out = []
    for c in cats:
        out += [(c, n, b, m) for n, b, m in extractor._known_models(db, c)]
    return sorted(out, key=lambda r: -len(r[1]))


def _num(s: str) -> float:
    return float(re.sub(r"[ .]", "", s)) if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", s) else float(s.replace(",", "."))


def rule_parse(db: Session, text: str, category_hint: str | None = None) -> dict[str, Any]:
    """Deterministic parser for short owner input in uz/ru/en."""
    low = text.lower()
    from app.core.catalog import norm_model

    norm = norm_model(text)
    attrs: dict[str, Any] = {}
    item: dict[str, Any] = {"category": None, "brand": None, "model": None, "condition": None, "district": None,
                            "attrs": attrs, "price": None, "currency": None}
    hint_cats = [category_hint] if category_hint in CATEGORIES else ["phone", "laptop", "car"]
    if category_hint in (None, "house", "rent") and _REALTY.search(low):
        item["category"] = "rent" if (category_hint == "rent" or _RENT.search(low)) else "house"
    else:
        for cat, n, brand, model in _known(db, [c for c in hint_cats if c in ("phone", "laptop", "car")]):
            if re.search(r"\b" + re.escape(n) + r"\b", norm):
                item.update(category=cat, brand=brand, model=model)
                after = norm.split(n, 1)[1]
                v = _VARIANT.match(after.strip())
                if v and v.group(1).lower() not in n:
                    item["model"] = f"{model} {v.group(1).title()}"
                break
        if item["category"] is None and category_hint in CATEGORIES:
            item["category"] = category_hint
    cat = item["category"]

    mileage_span = None
    if cat == "car":
        m = _MILEAGE.search(low)
        if m:
            g = [x for x in m.groups() if x]
            numtxt = next(x for x in g if re.match(r"\d", x))
            km = _num(numtxt)
            if re.search(r"(ming|тыс|\dk\b)", m.group(0)):
                km *= 1000
            attrs["mileage_km"] = int(km)
            mileage_span = m.span()
        y = re.search(r"\b(19[89]\d|20[0-3]\d)\b", low)
        if y:
            attrs["year"] = int(y.group(1))
        tr = re.search(r"(pozitsiya|позиция|poz)\s*(\d)|(\d)\s*[- ]?(pozitsiya|позиция)", low)
        if tr:
            attrs["trim"] = int(tr.group(2) or tr.group(3))
        for fuel in ("benzin", "metan", "propan", "gibrid", "elektro"):
            if fuel in low:
                attrs["fuel"] = fuel
        if re.search(r"(avtomat|автомат)", low):
            attrs["transmission"] = "avtomat"
        if re.search(r"(kraskasi yo'q|kraska yo'q|без окрас)", low):
            attrs["paint_clean"] = True
        item["condition"] = "new" if re.search(r"\b(yangi|новый|new)\b", low) else "used"
    elif cat in ("phone", "laptop"):
        if cat == "phone":
            m = re.search(r"\b(64|128|256|512|1024)\s*(gb|гб|g)?\b", low)
            if m:
                attrs["storage_gb"] = int(m.group(1))
            m = re.search(r"\b(\d{1,2})\s*/\s*(64|128|256|512)\b", low)
            if m:
                attrs["ram_gb"], attrs["storage_gb"] = int(m.group(1)), int(m.group(2))
            m = re.search(r"\b(\d{2,3})\s*%", low)
            if m and 40 <= int(m.group(1)) <= 100:
                attrs["battery_pct"] = int(m.group(1))
            if re.search(r"(korobka|karobka|коробк|box)", low):
                attrs["has_box"] = not re.search(r"(korobka(si)? yo'q|без коробк|no box)", low)
            if re.search(r"(registr|регистр)", low):
                attrs["imei_registered"] = not re.search(r"(siz\b|без)", low)
            if re.search(r"(zamena|almashgan|замен)", low):
                attrs["repaired"] = True
        else:
            m = re.search(r"\b(\d{1,2})\s*/\s*(\d{3,4})\b", low)
            if m:
                attrs["ram_gb"], attrs["ssd_gb"] = int(m.group(1)), int(m.group(2))
        if re.search(r"\b(yangi|новый|new|запечат)", low):
            item["condition"] = "new"
        elif re.search(r"\b(ideal|идеал|a\+?)\b", low):
            item["condition"] = "A"
    elif cat in ("house", "rent"):
        m = re.search(r"(\d)\s*[- ]?\s*(xona|xonali|комн|к\b)", low)
        if m:
            attrs["rooms"] = int(m.group(1))
        m = re.search(r"(\d{2,3}(?:[.,]\d)?)\s*(kv|m2|m²|м2|кв)", low)
        if m:
            attrs["area_m2"] = float(m.group(1).replace(",", "."))
        item["district"] = normalize_district(text)
        if cat == "rent":
            if re.search(r"(mebel|мебел|jihoz)", low):
                attrs["furnished"] = not re.search(r"(mebelsiz|без мебел)", low)
            attrs["period"] = "daily" if re.search(r"(kunlik|посуточ|sutka)", low) else "monthly"
        if cat == "house":
            for b in ("novostroyka", "vtorichka"):
                if b in low:
                    attrs["building"] = b
        item["model"] = f"{attrs.get('rooms') or ''}-xonali {'ijara' if cat == 'rent' else 'kvartira'}".strip("-")
    price_text = low if mileage_span is None else low[:mileage_span[0]] + " " + low[mileage_span[1]:]
    if cat and re.search(r"(\$|у\.?е|y\.?e|so['ʻ’`]?m|сум|\bmln\b|млн|\bming\b|narx|цена|dollar)", price_text):
        p = extractor.parse_price(price_text, cat)
        if p:
            item["price"], item["currency"] = p
    return item


def _finish(item: dict[str, Any], source: str) -> dict[str, Any]:
    cat = item.get("category")
    missing = []
    if cat is None:
        missing = ["category"]
    else:
        for f in REQUIRED[cat]:
            v = item.get(f) if f in ("model", "condition", "district") else item["attrs"].get(f)
            if v in (None, ""):
                missing.append(f)
    confidence = "high" if not missing else ("medium" if len(missing) == 1 else "low")
    return {**item, "missing_fields": missing, "confidence": confidence, "source": source}


def parse_text(db: Session, text: str, category_hint: str | None = None) -> dict[str, Any]:
    """LLM extraction with the extractor's schema when available; rule parser otherwise or on failure."""
    rules = rule_parse(db, text, category_hint)
    if llm.available():
        out = llm.generate_json(
            "Extract ONE item a shop owner typed (not an ad; it may have no price). Return a JSON array with one "
            f"object using the schema. category_hint: {category_hint}\nText: {json.dumps(text, ensure_ascii=False)}",
            system=extractor.SYSTEM_PROMPT, temperature=0.0, timeout=settings.LLM_TIMEOUT_S)
        if isinstance(out, list) and out and isinstance(out[0], dict) and out[0].get("category") in CATEGORIES:
            o = out[0]
            cat = o["category"]
            attrs = extractor.clean_attrs(cat, o.get("attrs"))
            item = {"category": cat, "brand": o.get("brand"), "model": o.get("model"),
                    "condition": o.get("condition") if o.get("condition") in ("new", "A", "B", "C", "used") else None,
                    "district": normalize_district(o.get("district")), "attrs": attrs,
                    "price": None, "currency": None}
            if o.get("price") and rules.get("price"):  # numbers come from the rule parser, never the LLM
                item["price"], item["currency"] = rules["price"], rules["currency"]
            for k in ("model", "brand", "district", "condition"):
                item[k] = item[k] or rules.get(k)
            item["attrs"] = {**attrs, **rules["attrs"]}
            return _finish(item, "llm")
    return _finish(rules, "rules")


# --------------------------------------------------------------------------- #
# IMEI                                                                          #
# --------------------------------------------------------------------------- #

def check_imei(imei: str) -> dict[str, Any]:
    """Luhn check + lookup in the local demo TAC table (never calls external services)."""
    digits = re.sub(r"\D", "", imei or "")
    valid = len(digits) == 15 and luhn_digit(digits[:14]) == digits[14]
    tac = load_tac().get(digits[:8]) if len(digits) >= 8 else None
    return {"imei": digits, "valid": valid, "tac": digits[:8] if len(digits) >= 8 else None,
            "brand": tac["brand"] if tac else None, "model": tac["model"] if tac else None,
            "storage_options": tac["storage_options"] if tac else [], "category": "phone" if tac else None,
            "source": "demo_tac_table"}


# --------------------------------------------------------------------------- #
# Pricing a listing                                                             #
# --------------------------------------------------------------------------- #

def price_listing(db: Session, lst: Listing, lang: str) -> dict[str, Any]:
    est = pricing.estimate(db, **pricing.spec_from(lst), exclude_id=lst.id, lang=lang)
    diff, text = pricing.badge(lst.price_uzs, est.fair_price_uzs, lang)
    return {"estimate": est, "diff_pct": diff, "badge": text}


def require_text(text: str | None) -> str:
    if not text or not text.strip():
        raise AppError("empty_input", "Nothing to parse", 422)
    return text.strip()


async def listing_for_link(db: Session, url: str) -> tuple[Listing, str]:
    """DB hit → that listing. Else, if the Telegram worker is connected, fetch that one public message
    read-only, run it through the normal pipeline (PII strip → raw_posts → extract) and return the listing."""
    import asyncio

    from app.core.models import RawPost
    from app.data_pipeline import telegram_ingest
    from app.intelligence.advisor import lender

    try:
        return lender.listing_from_url(db, url), "database"
    except AppError as exc:
        if exc.code != "post_not_found" or not telegram_ingest.connected():
            raise
        channel, msg_id = exc.details["channel"], exc.details["msg_id"]
    fetched = await telegram_ingest.fetch_message(channel, msg_id)
    if fetched is None:
        raise AppError("post_not_found", "Could not read this post (private channel or deleted)", 404,
                       {"channel": channel, "msg_id": msg_id})
    text, posted, has_photo = fetched
    post = telegram_ingest.save_post(db, channel, msg_id, posted, text, has_photo)
    if post is None:
        post = db.scalar(select(RawPost).where(RawPost.source == channel, RawPost.msg_id == msg_id))
        if post is None:
            raise AppError("not_an_offer", "This post does not look like a sale offer", 422)
    if post.processed == extractor.NEW:
        await asyncio.to_thread(lambda: extractor.process_batch(db, [post]))
    lst = db.scalar(select(Listing).where(Listing.raw_post_id == post.id))
    if lst is None:
        raise AppError("not_an_offer", post.error or "No listing could be extracted from this post", 422)
    return lst, "telegram"
