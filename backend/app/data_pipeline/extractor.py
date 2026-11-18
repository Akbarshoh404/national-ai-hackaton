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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import db as dbm
from app.core import fx, llm, workers
from app.core.catalog import ATTR_FIELDS, CATEGORIES, CONDITIONS, DISTRICTS, norm_model, normalize_district
from app.core.config import settings
from app.core.events import bus
from app.core.models import Listing, RawPost, Source
from app.intelligence.market import market, pricing

log = logging.getLogger("raft.extractor")

NEW, DONE, FAILED, SKIPPED = 0, 1, 2, 3

# --------------------------------------------------------------------------- #
# Deterministic price parsing (used by validation and the no-LLM fallback)      #
# --------------------------------------------------------------------------- #
_NUM = r"(\d{1,3}(?:[  .,]\d{3})+|\d+(?:[.,]\d+)?)"
_USD = r"\$|у\.?\s?е\.?|y\.?\s?e\.?|dollar|доллар|usd"
_UZS = r"so['ʻ’`]?m|сум|sum|uzs"
_PRICE_RX = re.compile(
    r"(?:(?P<key>narx\w*|нарх\w*|цена|цены|price|💰|💵)\s*[:\-–=]?\s*)?"
    r"(?P<pre>\$\s*)?"
    rf"(?<![A-Za-zА-Яа-яЁё])(?P<num>{_NUM})"  # not glued to letters: "A54" is a model name
    r"(?:\s*(?P<mult>mln|млн|million|миллион|ming|минг|тыс)\b"
    rf"(?:\s*(?P<num2>{_NUM})\s*(?:ming|минг|тыс)\b)?)?"
    rf"(?:\s*(?P<cur>{_USD}|{_UZS})(?![a-zа-я])(?!\s*\d))?",  # "$260" is a prefix of 260, not 54's suffix
    re.IGNORECASE)
#: a number right before these words is a duration (installment term), not a price
_MONTHS_AFTER = re.compile(r"\s*(oy|oyga|ой|мес|month)", re.IGNORECASE)


def _to_float(s: str) -> float:
    s = s.replace(" ", " ").strip()
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", s):
        return float(re.sub(r"[ .,]", "", s))
    return float(s.replace(",", "."))


def price_candidates(text: str, category: str | None = None) -> list[tuple[int, int, float, str]]:
    """(score, position, value, currency) for every price-looking amount; bare numbers are ignored.

    Score: 3 after a price keyword (narxi/цена/💰/💵), +1 with a unit or currency; 2 for a postfix currency or
    mln/ming; 1 for a bare `$` prefix. Numbers followed by oy/мес (installment terms) are dropped.
    """
    out = []
    for m in _PRICE_RX.finditer(text):
        key, pre, mult, cur = m.group("key"), m.group("pre"), m.group("mult"), m.group("cur")
        if not (key or pre or mult or cur):
            continue
        if not (mult or cur) and _MONTHS_AFTER.match(text, m.end()):
            continue
        try:
            value = _to_float(m.group("num"))
        except ValueError:
            continue
        unit = (mult or "").lower()
        if unit in ("mln", "млн", "million", "миллион"):
            value *= 1e6
            if m.group("num2"):
                value += _to_float(m.group("num2")) * 1e3
        elif unit:
            value *= 1e3
        if value <= 0:
            continue
        if cur:
            currency = "USD" if re.fullmatch(_USD, cur, re.IGNORECASE) else "UZS"
        elif mult:
            currency = "UZS"
        elif pre:
            currency = "USD"
        else:
            currency = default_currency(category, value)
        score = 3 + int(bool(mult or cur)) if key else (2 if (mult or cur) else 1)
        out.append((score, m.start(), value, currency))
    return out


def parse_price(text: str, category: str | None = None) -> tuple[float, str] | None:
    """The most price-like amount: '💰 225$', 'Narxi: 4 mln 600 ming', '5.2 mln', '$450', '12 500 у.е.'.

    Highest score wins; among equals the earliest. Installment terms ('79$ 6 oy') and deposits listed before
    an explicit 'Цена:' do not win any more.
    """
    cands = price_candidates(text, category)
    if not cands:
        return None
    best = max(cands, key=lambda c: (c[0], -c[1]))
    return best[2], best[3]


def default_currency(category: str | None, price: float) -> str:
    """Car and house prices without a currency are USD; otherwise judge by magnitude."""
    if category in ("car", "house"):
        return "USD"
    return "USD" if price < 20000 else "UZS"


def normalize_price(category: str | None, price: float, currency: Any) -> tuple[float, str]:
    """Canonical (price, "USD"|"UZS") for a model-read price (currency aliases, missing currency, dropped "mln")."""
    cur = str(currency or "").upper()
    if cur in ("$", "Y.E.", "У.Е.", "DOLLAR"):
        cur = "USD"
    if cur in ("SUM", "SO'M", "СУМ"):
        cur = "UZS"
    if cur not in ("USD", "UZS"):
        cur = default_currency(category, price)
    if cur == "UZS" and price < 1000:  # "5.2" with "mln" dropped by the model
        price *= 1e6
    return price, cur




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
    price, currency = normalize_price(cat, price, item.get("currency"))
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


def store(db: Session, post: RawPost, item: dict[str, Any], source: Source | None,
          extracted_by: str | None = None) -> Listing | None:
    """Validate one extracted item and insert the listing (+ deal check). `extracted_by` → attrs._extracted_by."""
    data, reason = validate(item, post, source)
    if data is None:
        post.processed, post.error = SKIPPED, reason
        return None
    if extracted_by:
        data["attrs"]["_extracted_by"] = extracted_by
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


class ExtractedItem(BaseModel):
    """Schema of one extracted post (the JSON the prompt asks for). Local-model output is validated with it."""

    model_config = ConfigDict(extra="ignore")
    skip: bool = False
    skip_reason: str | None = None
    category: Literal["phone", "laptop", "car", "house", "rent"] | None = None
    brand: str | None = None
    model: str | None = None
    condition: str | None = None
    price: float | None = None
    currency: str | None = None
    city: str | None = None
    district: str | None = None
    seller_type: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


#: Same instructions as the Gemini batch prompt, adapted to ONE post per call (small models are steadier).
_BATCH_FORMAT = ('Return ONLY a JSON array with exactly one object per input\npost, in the same order. '
                 'Each object:\n{"i": <input index>, ')
if _BATCH_FORMAT not in SYSTEM_PROMPT:  # keep the two prompts in sync
    raise RuntimeError("SYSTEM_PROMPT changed: update LOCAL_SYSTEM_PROMPT")
LOCAL_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(_BATCH_FORMAT, "You receive ONE post. Return ONLY one JSON object:\n{")

#: (category_hint, post text, expected JSON) — six short worked examples for the local model.
FEW_SHOTS: list[tuple[str, str, dict[str, Any]]] = [
    ("phone", "iPhone 13 128gb ideal holatda, batareya 89%, korobka bor. Narxi 5.2 mln so'm. Chilonzor",
     {"skip": False, "category": "phone", "brand": "Apple", "model": "iPhone 13", "condition": "A",
      "price": 5200000, "currency": "UZS", "city": "Toshkent", "district": "Chilonzor", "seller_type": None,
      "attrs": {"storage_gb": 128, "battery_pct": 89, "has_box": True}}),
    ("car", "Cobalt 2021, probeg 45 000 km, 4 pozitsiya, kraskasi yo'q, metan bor. Narxi 11 800$",
     {"skip": False, "category": "car", "brand": "Chevrolet", "model": "Cobalt", "condition": "used",
      "price": 11800, "currency": "USD", "city": None, "district": None, "seller_type": None,
      "attrs": {"year": 2021, "mileage_km": 45000, "trim": 4, "paint_clean": True, "fuel": "metan"}}),
    ("rent", "Сдаю 2-комнатную квартиру в Юнусабаде, с мебелью и техникой, коммунальные включены. 450$ в месяц",
     {"skip": False, "category": "rent", "brand": None, "model": "2-xonali ijara", "condition": "used",
      "price": 450, "currency": "USD", "city": "Toshkent", "district": "Yunusobod", "seller_type": None,
      "attrs": {"rooms": 2, "furnished": True, "appliances": True, "utilities_included": True,
                "period": "monthly"}}),
    ("laptop", "Продаю MacBook Air M1 8/256, состояние отличное, батарея 92%. Цена 620$",
     {"skip": False, "category": "laptop", "brand": "Apple", "model": "MacBook Air M1", "condition": "A",
      "price": 620, "currency": "USD", "city": None, "district": None, "seller_type": None,
      "attrs": {"cpu": "Apple M1", "ram_gb": 8, "ssd_gb": 256, "battery_health": 92}}),
    ("house", "Сотилади 3 хонали квартира, Мирзо Улуғбек, 78 м², 5/9 қават, евро таъмир, кадастр бор. Нархи 95 000",
     {"skip": False, "category": "house", "brand": None, "model": "3-xonali kvartira", "condition": "used",
      "price": 95000, "currency": "USD", "city": "Toshkent", "district": "Mirzo Ulug'bek", "seller_type": None,
      "attrs": {"rooms": 3, "area_m2": 78, "floor": 5, "floors_total": 9, "renovation": "yevro",
                "cadastre": True}}),
    ("phone", "Sotib olaman iPhone 14 Pro, 9 mln gacha, tez javob bering",
     {"skip": True, "skip_reason": "buying"}),
]


#: Post text is capped so prompt + 6 examples + answer fit the 2,048-token context (measured: ~1.7k worst case).
LOCAL_MAX_POST_CHARS = 600


def clip_post(text: str, limit: int = LOCAL_MAX_POST_CHARS) -> str:
    """Head + tail of long posts: the model sees the title and the price line that shops put at the bottom."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    return text[:head].rstrip() + " … " + text[-(limit - head - 3):].lstrip()


def _compact(obj: dict[str, Any]) -> str:
    """Example answers without null fields and spaces: same information, far fewer tokens."""
    return json.dumps({k: v for k, v in obj.items() if v is not None}, ensure_ascii=False, separators=(",", ":"))


def local_messages(text: str, hint: str) -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": LOCAL_SYSTEM_PROMPT}]
    for ex_hint, ex_text, ex_out in FEW_SHOTS:
        msgs.append({"role": "user", "content": _compact({"category_hint": ex_hint, "text": ex_text})})
        msgs.append({"role": "assistant", "content": _compact(ex_out)})
    msgs.append({"role": "user", "content": _compact({"category_hint": hint, "text": clip_post(text)})})
    return msgs


def local_extract(text: str, hint: str = "mixed") -> dict[str, Any] | None:
    """One post → validated item from the local model, or None (invalid JSON / schema / timeout).

    Raises `llm.LocalLLMError("down")` when Ollama is not reachable, so callers can skip the provider.
    """
    try:
        out = llm.local_chat_json(local_messages(text, hint))
    except llm.LocalLLMError as exc:
        if exc.kind == "down":
            raise
        log.warning("local model failed (%s); falling through", exc.kind)
        return None
    if isinstance(out, list) and len(out) == 1:
        out = out[0]
    if not isinstance(out, dict):
        log.warning("local model returned %s instead of an object; falling through", type(out).__name__)
        return None
    try:
        return ExtractedItem.model_validate(out).model_dump()
    except ValidationError as exc:
        log.warning("local model output failed the schema (%d errors); falling through", exc.error_count())
        return None


def check_price(item: dict[str, Any], text: str, provider: str) -> dict[str, Any]:
    """The model reads the price, the regex verifies it: on a > 1% disagreement the rule price wins."""
    if item.get("skip") or item.get("category") not in CATEGORIES or item.get("price") in (None, ""):
        return item
    try:
        model_price, model_cur = normalize_price(item["category"], float(item["price"]), item.get("currency"))
    except (TypeError, ValueError):
        return item
    rule = parse_price(text, item["category"])
    if rule is None:
        return item
    model_uzs, rule_uzs = fx.to_uzs(model_price, model_cur), fx.to_uzs(*rule)
    if rule_uzs > 0 and abs(model_uzs - rule_uzs) > 0.01 * rule_uzs:
        log.warning("price mismatch (%s): model %.0f %s vs rule %.0f %s; using the rule price",
                    provider, model_price, model_cur, rule[0], rule[1])
        return {**item, "price": rule[0], "currency": rule[1]}
    return item


def _gemini_items(posts: list[RawPost], hints: dict[str, str]) -> dict[int, dict[str, Any] | None]:
    """One Gemini call per batch; on a bad answer retry once in halves."""
    out = _call_llm(posts, hints)
    if out is not None:
        return {p.id: item for p, item in zip(posts, out, strict=True)}
    res: dict[int, dict[str, Any] | None] = {}
    half = max(1, len(posts) // 2)
    for chunk in (posts[:half], posts[half:]):
        if chunk:
            sub = _call_llm(chunk, hints)
            res.update({p.id: (sub[i] if sub is not None else None) for i, p in enumerate(chunk)})
    return res


def extract_items(db: Session, posts: list[RawPost], hints: dict[str, str],
                  order: list[str]) -> list[tuple[RawPost, dict[str, Any] | None, str | None]]:
    """Run the provider chain. Each post keeps the first valid result: (post, item | None, provider | None)."""
    got: dict[int, tuple[dict[str, Any], str]] = {}
    pending = list(posts)
    for provider in order:
        if not pending:
            break
        if provider == "local":
            if llm.local_suspended():
                continue
            still: list[RawPost] = []
            for i, post in enumerate(pending):
                try:
                    item = local_extract(post.text, hints.get(post.source, "mixed"))
                except llm.LocalLLMError:
                    log.warning("Ollama not reachable; skipping the local model for this batch")
                    still.extend(pending[i:])
                    break
                if item is None:
                    still.append(post)
                else:
                    got[post.id] = (check_price(item, post.text, "local"), llm.local_label())
            pending = still
        elif provider == "gemini":
            if not llm.available():
                continue
            res = _gemini_items(pending, hints)
            for post in pending:
                if isinstance(res.get(post.id), dict):
                    got[post.id] = (check_price(res[post.id], post.text, "gemini"), "gemini")
            pending = [p for p in pending if p.id not in got]
        elif provider == "rules":
            for post in pending:
                got[post.id] = (rule_extract(db, post, hints.get(post.source, "mixed")), "rules")
            pending = []
    return [(p, *got[p.id]) if p.id in got else (p, None, None) for p in posts]


_COMPARE = ("category", "brand", "model_norm", "condition", "price_uzs", "district", "seller_type")


def compare_listing(old: Listing, new: dict[str, Any] | None) -> list[str]:
    """Names of fields that differ between a stored listing and a re-extracted one."""
    if new is None:
        return ["<skipped>"]
    changed = [f for f in _COMPARE if f != "price_uzs" and (getattr(old, f) or None) != (new.get(f) or None)]
    if abs((old.price_uzs or 0) - (new.get("price_uzs") or 0)) > 0.01 * max(old.price_uzs or 1, 1):
        changed.append("price_uzs")
    a = {k: v for k, v in (old.attrs or {}).items() if not k.startswith("_")}
    b = {k: v for k, v in (new.get("attrs") or {}).items() if not k.startswith("_")}
    changed += [f"attrs.{k}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    return changed


def reextract(db: Session, provider: str, limit: int) -> dict[str, Any]:
    """Re-run one provider on already-processed posts (no writes) and diff against the stored listings."""
    rows = db.execute(select(RawPost, Listing).join(Listing, Listing.raw_post_id == RawPost.id)
                      .where(RawPost.processed == DONE).order_by(RawPost.id.desc()).limit(limit)).all()
    sources = {s.username: s for s in db.scalars(select(Source))}
    hints = {u: s.category_hint for u, s in sources.items()}
    posts = [r[0] for r in rows]
    results = {p.id: (item, by) for p, item, by in extract_items(db, posts, hints, [provider])}
    report: list[dict[str, Any]] = []
    field_counts: dict[str, int] = {}
    for post, listing in rows:
        item, by = results[post.id]
        new = validate(item, post, sources.get(post.source))[0] if item is not None else None
        changed = compare_listing(listing, new) if item is not None else ["<failed>"]
        for f in changed:
            field_counts[f] = field_counts.get(f, 0) + 1
        report.append({"raw_post_id": post.id, "was": (listing.attrs or {}).get("_extracted_by", "unknown"),
                       "now": by, "changed": changed})
    return {"provider": provider, "compared": len(rows), "with_changes": sum(1 for r in report if r["changed"]),
            "fields_changed": sum(len(r["changed"]) for r in report), "by_field": field_counts, "posts": report}


def process_batch(db: Session, posts: list[RawPost]) -> dict[str, int]:
    """Extract and store a batch. Returns counts of created / skipped / failed posts."""
    sources = {s.username: s for s in db.scalars(select(Source).where(Source.username.in_({p.source for p in posts})))}
    hints = {u: s.category_hint for u, s in sources.items()}
    results = extract_items(db, posts, hints, settings.provider_order)

    created = skipped = failed = 0
    new_listings: list[Listing] = []
    for post, item, provider in results:
        if item is None:
            post.processed, post.error = FAILED, "llm_output_invalid: no provider produced a valid result"
            failed += 1
            continue
        try:
            listing = store(db, post, item, sources.get(post.source), provider)
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
