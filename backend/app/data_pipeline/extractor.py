"""Raw Telegram post → structured listing.

One LLM call per batch of 15 posts (JSON mode, temperature 0). On invalid output the
batch is retried once in halves; posts that still fail are marked `failed`. Without an
API key a deterministic rule-based parser is used instead. Every result is validated
in Python (currency, UZS/USD conversion, outliers, reposts) before it becomes a listing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import db as dbm
from app.core import fx, llm, workers
from app.core.catalog import ATTR_FIELDS, CATEGORIES, CONDITIONS, DISTRICTS, norm_model, normalize_district
from app.core.config import settings
from app.core.events import bus
from app.core.models import Listing, RawPost, Source
from app.intelligence.market import market, pricing

log = logging.getLogger("bozorpilot.extractor")

NEW, DONE, FAILED, SKIPPED = 0, 1, 2, 3

# --------------------------------------------------------------------------- #
# Deterministic price parsing (used by validation and the no-LLM fallback)      #
# --------------------------------------------------------------------------- #
_NUM = r"(\d{1,3}(?:[  .,]\d{3})+|\d+(?:[.,]\d+)?)"
_PRICE_PATTERNS = [
    (re.compile(r"\$\s*" + _NUM), "USD", 1.0),
    (re.compile(_NUM + r"\s*(?:\$|у\.?\s?е\.?|y\.?\s?e\.?|dollar|доллар|usd)", re.I), "USD", 1.0),
    (re.compile(_NUM + r"\s*(?:mln|млн|million|миллион)", re.I), "UZS", 1e6),
    (re.compile(_NUM + r"\s*(?:ming|тыс|минг)", re.I), "UZS", 1e3),
    (re.compile(_NUM + r"\s*(?:so['ʻ’`]?m|сум|sum|uzs)", re.I), "UZS", 1.0),
    (re.compile(r"(?:narx|narxi|цена|price)\s*[:\-]?\s*" + _NUM, re.I), None, 1.0),
]


def _to_float(s: str) -> float:
    s = s.replace(" ", " ").strip()
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", s):
        return float(re.sub(r"[ .,]", "", s))
    return float(s.replace(",", "."))


def parse_price(text: str, category: str | None = None) -> tuple[float, str] | None:
    """Find the first price in free text: '$450', '5.2 mln', '250 ming', '12 500 у.е.'."""
    for pattern, currency, mult in _PRICE_PATTERNS:
        m = pattern.search(text)
        if m:
            value = _to_float(m.group(1)) * mult
            if currency is None:
                currency = default_currency(category, value)
            if value > 0:
                return value, currency
    return None


def default_currency(category: str | None, price: float) -> str:
    """Car and house prices without a currency are USD; otherwise judge by magnitude."""
    if category in ("car", "house"):
        return "USD"
    return "USD" if price < 20000 else "UZS"


# --------------------------------------------------------------------------- #
# LLM prompt                                                                    #
# --------------------------------------------------------------------------- #
_ATTR_SPEC = {c: [f["name"] for f in fields] for c, fields in ATTR_FIELDS.items()}

SYSTEM_PROMPT = f"""You extract sale listings from Telegram posts of Uzbek marketplaces.
Posts are in Uzbek (Latin or Cyrillic) or Russian. Return ONLY a JSON array with exactly one object per input
post, in the same order. Each object:
{{"i": <input index>, "skip": bool, "skip_reason": str|null, "category": "phone"|"laptop"|"car"|"house"|"rent",
 "brand": str|null, "model": str|null (normalized, e.g. "iPhone 13", "Galaxy A54", "Cobalt", "MacBook Air M1"),
 "condition": phone/laptop: "new"|"A"|"B"|"C"; car/house/rent: "new"|"used"; null if unknown,
 "price": number, "currency": "USD"|"UZS", "city": str|null,
 "district": one of {json.dumps(DISTRICTS)} or null, "seller_type": "shop"|"private"|null, "attrs": {{...}}}}
Rules:
- skip=true for questions, "buying"/"sotib olaman"/"куплю" posts, service ads, news, posts without a price.
- If a post lists several items, extract the first one.
- Currency: "$", "y.e.", "у.е.", "dollar" -> USD. "so'm", "сум", "mln", "ming" -> UZS.
  "5.2 mln" = 5200000 UZS; "250 ming" = 250000 UZS. Car or house prices with no currency -> USD.
- category_hint guides you, but decide the category from the text. Rent = monthly/daily rental of a flat.
- attrs per category (unknown -> null, never invent):
  phone: {_ATTR_SPEC['phone']} ("registratsiyadan o'tgan" = imei_registered true; "zamena",
  "ekran almashgan" = repaired true)
  laptop: {_ATTR_SPEC['laptop']}
  car: {_ATTR_SPEC['car']} ("probeg" = mileage_km; "pozitsiya" = trim number; "kraskasi yo'q" = paint_clean
  true; "N joyi kraska" = false; "obmen" = exchange_possible; "kredit"/"nasiya" = credit_available)
  house: {_ATTR_SPEC['house']} ("kadastr bor" = cadastre true; "orientir" = landmark; "ipoteka" = mortgage_ok)
  rent: {_ATTR_SPEC['rent']} ("mebelli"/"jihozlangan" = furnished; "kommunal" = utilities_included;
  period "monthly"|"daily")
- seller_type: "shop" for stores/dealers/agencies, "private" for individuals, null if unclear.
- Never invent values. Use null when unknown."""


def build_prompt(posts: list[RawPost], hints: dict[str, str]) -> str:
    items = [{"i": i, "category_hint": hints.get(p.source, "mixed"), "text": p.text[:1500]}
             for i, p in enumerate(posts)]
    return "Posts:\n" + json.dumps(items, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Rule-based fallback                                                          #
# --------------------------------------------------------------------------- #
_HINT_CATS = {"phone": ["phone"], "laptop": ["laptop"], "car": ["car"], "house": ["house"], "rent": ["rent"],
              "mixed_tech": ["phone", "laptop"], "mixed_realty": ["house", "rent"], "mixed": CATEGORIES}
_RENT_WORDS = re.compile(r"(ijara|arenda|аренд|сдаю|сдается|ijaraga|oyiga|в месяц|посуточ|kunlik)", re.I)
_LAPTOP_WORDS = re.compile(r"(noutbuk|ноутбук|laptop|macbook|ideapad|thinkpad|pavilion|vivobook|nitro|tuf|"
                           r"latitude|i[3579][- ]\d{4,5})", re.I)
_SKIP_WORDS = re.compile(r"(sotib olaman|куплю|olamiz|kerak\b|нужен|ищу|\?$)", re.I)


def _known_models(db: Session, category: str) -> list[tuple[str, str | None, str]]:
    rows = db.execute(select(Listing.model_norm, Listing.brand, Listing.model).where(Listing.category == category)
                      .group_by(Listing.model_norm, Listing.brand, Listing.model)).all()
    return sorted({(n, b, m) for n, b, m in rows if n}, key=lambda r: -len(r[0]))


def _category_by_model(db: Session, text: str, cats: list[str]) -> str | None:
    """Category whose known model (longest first) appears in the text."""
    low = norm_model(text)
    hits = [(len(n), c) for c in cats for n, _, _ in _known_models(db, c)
            if re.search(r"\b" + re.escape(n) + r"\b", low)]
    return max(hits)[1] if hits else None


def rule_extract(db: Session, post: RawPost, hint: str) -> dict[str, Any]:
    """Deterministic extraction used when no LLM key is configured."""
    text = post.text
    if _SKIP_WORDS.search(text):
        return {"skip": True, "skip_reason": "buying_or_question"}
    cats = _HINT_CATS.get(hint, CATEGORIES)
    if "rent" in cats and _RENT_WORDS.search(text):
        cat = "rent"
    elif "laptop" in cats and _LAPTOP_WORDS.search(text):
        cat = "laptop"
    else:
        goods = [c for c in cats if c in ("phone", "laptop", "car")]
        cat = _category_by_model(db, post.text, goods) if len(goods) > 1 else None
        cat = cat or (next(c for c in cats if c != "rent") if cats != ["rent"] else "rent")
    price = parse_price(text, cat)
    if not price:
        return {"skip": True, "skip_reason": "no_price"}
    item: dict[str, Any] = {"skip": False, "category": cat, "price": price[0], "currency": price[1],
                            "district": normalize_district(text), "attrs": {}}
    low = norm_model(text)
    if cat in ("phone", "laptop", "car"):
        for n, b, m in _known_models(db, cat):
            if re.search(r"\b" + re.escape(n) + r"\b", low):
                item.update(brand=b, model=m)
                break
    a = item["attrs"]
    if cat == "phone":
        m = re.search(r"\b(64|128|256|512)\s*(gb|гб)?\b", text, re.I)
        if m:
            a["storage_gb"] = int(m.group(1))
        item["condition"] = "new" if re.search(r"\b(yangi|новый|new|запечат)", text, re.I) else (
            "A" if re.search(r"(ideal|идеал|a\+?\b)", text, re.I) else None)
        if re.search(r"(registratsiya|регистрац)", text, re.I):
            a["imei_registered"] = not re.search(r"(registratsiyasiz|без регистр)", text, re.I)
    elif cat == "car":
        m = re.search(r"\b(20[0-2]\d|199\d)\b", text)
        if m:
            a["year"] = int(m.group(1))
        m = re.search(r"(\d{1,3}(?:[ .]\d{3})+|\d{4,6})\s*(km|км)", text, re.I)
        if m:
            a["mileage_km"] = int(re.sub(r"\D", "", m.group(1)))
        item["condition"] = "used"
    elif cat in ("house", "rent"):
        m = re.search(r"(\d)\s*[- ]?\s*(xonali|xona|комн|к\.)", text, re.I)
        if m:
            a["rooms"] = int(m.group(1))
        m = re.search(r"(\d{2,3}(?:[.,]\d)?)\s*(m2|м2|m²|м²|kv)", text, re.I)
        if m:
            a["area_m2"] = float(m.group(1).replace(",", "."))
        if cat == "rent":
            a["furnished"] = bool(re.search(r"(mebel|мебел|jihoz)", text, re.I)) or None
            a["period"] = "daily" if re.search(r"(kunlik|посуточ|sutka)", text, re.I) else "monthly"
        item["model"] = f"{a.get('rooms') or ''}-xonali {'ijara' if cat == 'rent' else 'kvartira'}".strip("-")
    return item


# --------------------------------------------------------------------------- #
# Validation                                                                    #
# --------------------------------------------------------------------------- #

def _cast(value: Any, type_: str) -> Any:
    if value is None or value == "":
        return None
    try:
        if type_ == "int":
            return int(float(re.sub(r"[^\d.\-]", "", str(value))))
        if type_ == "float":
            return float(re.sub(r"[^\d.\-]", "", str(value).replace(",", ".")))
        if type_ == "bool":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes", "ha", "да")
        return str(value)
    except (TypeError, ValueError):
        return None


def clean_attrs(category: str, attrs: Any) -> dict[str, Any]:
    if not isinstance(attrs, dict):
        return {}
    out = {}
    for f in ATTR_FIELDS[category]:
        v = _cast(attrs.get(f["name"]), "str" if f["type"] == "enum" else f["type"])
        if f["type"] == "enum" and v is not None and f["options"] and v not in f["options"]:
            v = None
        if v is not None:
            out[f["name"]] = v
    return out


def validate(item: dict[str, Any], post: RawPost, source: Source | None) -> tuple[dict[str, Any] | None, str | None]:
    """LLM/rule output → Listing kwargs, or (None, reason)."""
    if not isinstance(item, dict):
        return None, "invalid_item"
    if item.get("skip"):
        return None, f"skipped: {item.get('skip_reason') or 'not an offer'}"
    cat = item.get("category")
    if cat not in CATEGORIES:
        return None, "unknown_category"
    try:
        price = float(item.get("price"))
    except (TypeError, ValueError):
        return None, "no_price"
    if price <= 0:
        return None, "no_price"
    currency = str(item.get("currency") or "").upper()
    if currency in ("$", "Y.E.", "У.Е.", "DOLLAR"):
        currency = "USD"
    if currency in ("SUM", "SO'M", "СУМ"):
        currency = "UZS"
    if currency not in ("USD", "UZS"):
        currency = default_currency(cat, price)
    if currency == "UZS" and price < 1000:  # "5.2" with "mln" dropped by the model
        price *= 1e6
    model = (item.get("model") or "").strip()
    if cat in ("phone", "laptop", "car") and not model:
        return None, "no_model"
    attrs = clean_attrs(cat, item.get("attrs"))
    cond = item.get("condition")
    if cond not in CONDITIONS[cat]:
        cond = {"used": "B", "ideal": "A"}.get(str(cond).lower()) if cat in ("phone", "laptop") else (
            "used" if cond else None)
    if cat in ("house", "rent") and not model:
        model = f"{attrs.get('rooms') or ''}-xonali {'ijara' if cat == 'rent' else 'kvartira'}".strip("-")
    seller = item.get("seller_type") if item.get("seller_type") in ("shop", "private") else (
        source.seller_type_default if source else "private")
    price_uzs = fx.to_uzs(price, currency)
    username = source.username if source else post.source
    return {"raw_post_id": post.id, "category": cat, "brand": item.get("brand"), "model": model,
            "model_norm": norm_model(model, item.get("brand")), "condition": cond, "price": price,
            "currency": currency, "price_uzs": round(price_uzs), "price_usd": round(fx.to_usd(price_uzs), 2),
            "city": item.get("city") or "Toshkent", "district": normalize_district(item.get("district")),
            "attrs": attrs, "seller_type": seller, "posted_at": post.posted_at,
            "source_url": f"https://t.me/{username}/{post.msg_id}", "origin": "telegram"}, None


def is_outlier(db: Session, data: dict[str, Any]) -> bool:
    """Price outside 0.3×–3× the current fair price (only when there is enough data)."""
    est = pricing.try_estimate(db, category=data["category"], model=data["model"], brand=data["brand"],
                               condition=data["condition"], district=data["district"], attrs=data["attrs"])
    if est is None or est.confidence == "low":
        return False
    ratio = data["price_uzs"] / est.fair_price_uzs
    return ratio < 0.3 or ratio > 3


def is_repost(db: Session, data: dict[str, Any], post: RawPost) -> bool:
    """Same text hash, or same category/model/price within 7 days from another source."""
    same_text = db.scalar(select(RawPost.id).join(Listing, Listing.raw_post_id == RawPost.id)
                          .where(RawPost.text_hash == post.text_hash, RawPost.id != post.id).limit(1))
    if same_text:
        return True
    since = data["posted_at"] - timedelta(days=7)
    rows = db.execute(select(Listing.price_uzs, RawPost.source).join(RawPost, Listing.raw_post_id == RawPost.id)
                      .where(Listing.category == data["category"], Listing.model_norm == data["model_norm"],
                             Listing.posted_at >= since, RawPost.source != post.source)).all()
    return any(abs(p - data["price_uzs"]) <= 0.01 * data["price_uzs"] for p, _ in rows)


def store(db: Session, post: RawPost, item: dict[str, Any], source: Source | None) -> Listing | None:
    """Validate one extracted item and insert the listing (+ deal check)."""
    data, reason = validate(item, post, source)
    if data is None:
        post.processed, post.error = SKIPPED, reason
        return None
    if is_outlier(db, data):
        post.processed, post.error = SKIPPED, "price_outlier"
        return None
    data["is_duplicate"] = is_repost(db, data, post)
    listing = Listing(**data)
    db.add(listing)
    db.flush()
    post.processed, post.error = DONE, None
    pricing.invalidate(listing.category)
    if not listing.is_duplicate:
        market.deal_check(db, listing)
    return listing


def _call_llm(posts: list[RawPost], hints: dict[str, str]) -> list[dict[str, Any]] | None:
    out = llm.generate_json(build_prompt(posts, hints), system=SYSTEM_PROMPT, temperature=0.0)
    if isinstance(out, dict):
        out = out.get("items") or out.get("listings")
    if not isinstance(out, list) or len(out) != len(posts):
        return None
    return out


def process_batch(db: Session, posts: list[RawPost]) -> dict[str, int]:
    """Extract and store a batch. Returns counts of created / skipped / failed posts."""
    sources = {s.username: s for s in db.scalars(select(Source).where(Source.username.in_({p.source for p in posts})))}
    hints = {u: s.category_hint for u, s in sources.items()}
    results: list[tuple[RawPost, dict[str, Any] | None]] = []
    if llm.available():
        out = _call_llm(posts, hints)
        if out is not None:
            results = list(zip(posts, out, strict=True))
        else:
            half = max(1, len(posts) // 2)
            for chunk in (posts[:half], posts[half:]):
                if not chunk:
                    continue
                sub = _call_llm(chunk, hints)
                results += list(zip(chunk, sub, strict=True)) if sub is not None else [(p, None) for p in chunk]
    else:
        results = [(p, rule_extract(db, p, hints.get(p.source, "mixed"))) for p in posts]

    created = skipped = failed = 0
    new_listings: list[Listing] = []
    for post, item in results:
        if item is None:
            post.processed, post.error = FAILED, "llm_output_invalid"
            failed += 1
            continue
        try:
            listing = store(db, post, item, sources.get(post.source))
        except Exception as exc:  # one bad item must not sink the batch
            log.exception("store failed for raw post %s", post.id)
            post.processed, post.error = FAILED, f"{type(exc).__name__}: {str(exc)[:200]}"
            failed += 1
            continue
        if listing is None:
            skipped += 1
        else:
            created += 1
            new_listings.append(listing)
    db.commit()
    for lst in new_listings:
        bus.publish("listing.created", {"id": lst.id, "category": lst.category, "title": market.listing_title(lst),
                                        "price_uzs": lst.price_uzs, "price_usd": lst.price_usd,
                                        "district": lst.district, "seller_type": lst.seller_type,
                                        "discount_pct": lst.discount_pct, "source_url": lst.source_url,
                                        "is_duplicate": lst.is_duplicate},
                    category=lst.category)
    return {"processed": len(posts), "created": created, "skipped": skipped, "failed": failed}


def run_once(db: Session, limit: int | None = None) -> dict[str, int]:
    """Process pending raw posts in batches until none (or `limit`) remain."""
    total = {"processed": 0, "created": 0, "skipped": 0, "failed": 0}
    size = settings.EXTRACT_BATCH_SIZE
    while limit is None or total["processed"] < limit:
        take = size if limit is None else min(size, limit - total["processed"])
        posts = list(db.scalars(select(RawPost).where(RawPost.processed == NEW).order_by(RawPost.id).limit(take)))
        if not posts:
            break
        for k, v in process_batch(db, posts).items():
            total[k] += v
    return total


async def run_loop(interval: float = 5.0) -> None:
    """Background extractor: polls for pending posts every few seconds."""
    mode = "llm" if llm.available() else "rules"
    workers.set_status("extractor", "ok", f"mode={mode}")

    def tick() -> dict[str, int]:
        with dbm.SessionLocal() as db:
            return run_once(db, limit=settings.EXTRACT_BATCH_SIZE * 4)

    while True:
        try:
            stats = await asyncio.to_thread(tick)
            if stats["processed"]:
                log.info("extracted processed=%d created=%d skipped=%d failed=%d", stats["processed"],
                         stats["created"], stats["skipped"], stats["failed"])
                workers.set_status("extractor", "ok", f"mode={mode}; last batch created {stats['created']}")
        except Exception as exc:
            log.exception("extractor tick failed")
            workers.set_status("extractor", "error", type(exc).__name__)
        await asyncio.sleep(interval)
