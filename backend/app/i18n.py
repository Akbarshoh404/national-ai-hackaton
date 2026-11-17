"""Tiny translation layer for generated text (uz / ru / en) and money formatting."""

from __future__ import annotations

import re

LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

_M: dict[str, dict[str, str]] = {
    # --- errors -------------------------------------------------------------
    "err.missing_api_key": {"uz": "X-API-Key sarlavhasi kerak", "ru": "Нужен заголовок X-API-Key",
                            "en": "X-API-Key header is required"},
    "err.invalid_api_key": {"uz": "API kalit noto'g'ri", "ru": "Неверный API-ключ", "en": "Invalid API key"},
    "err.missing_admin_key": {"uz": "X-Admin-Key kerak", "ru": "Нужен X-Admin-Key",
                              "en": "X-Admin-Key header is required"},
    "err.invalid_admin_key": {"uz": "Admin kalit noto'g'ri", "ru": "Неверный админ-ключ",
                              "en": "Invalid admin key"},
    "err.not_enough_market_data": {
        "uz": "Bozor ma'lumotlari yetarli emas ({n} ta o'xshash e'lon)",
        "ru": "Недостаточно рыночных данных ({n} похожих объявлений)",
        "en": "Not enough market data ({n} comparable listings)"},
    # --- pricing basis --------------------------------------------------------
    "basis.model_storage_condition": {"uz": "{model} {storage}GB, holati {condition}",
                                      "ru": "{model} {storage}GB, состояние {condition}",
                                      "en": "{model} {storage}GB in condition {condition}"},
    "basis.model_storage": {"uz": "{model} {storage}GB, holat bo'yicha moslashtirilgan",
                            "ru": "{model} {storage}GB, с поправкой на состояние",
                            "en": "{model} {storage}GB, adjusted for condition"},
    "basis.model": {"uz": "Barcha {model} e'lonlari, holat/xotira bo'yicha moslashtirilgan",
                    "ru": "Все объявления {model} с поправкой на состояние/память",
                    "en": "All {model} listings, adjusted for condition/storage"},
    "basis.laptop_exact": {"uz": "{model} {ram}/{ssd}, holati {condition}",
                           "ru": "{model} {ram}/{ssd}, состояние {condition}",
                           "en": "{model} {ram}/{ssd} in condition {condition}"},
    "basis.laptop_class": {"uz": "{cpu} + {ram}GB RAM sinfidagi noutbuklar",
                           "ru": "Ноутбуки класса {cpu} + {ram}GB RAM",
                           "en": "Laptops of class {cpu} + {ram}GB RAM"},
    "basis.car_exact": {"uz": "{model}, {year}±1 yil, probeg ±30 000 km, {fuel}",
                        "ru": "{model}, {year}±1 год, пробег ±30 000 км, {fuel}",
                        "en": "{model}, {year}±1 yr, mileage ±30,000 km, {fuel}"},
    "basis.car_year2": {"uz": "{model}, {year}±2 yil, yil bo'yicha moslashtirilgan",
                        "ru": "{model}, {year}±2 года, с поправкой на год",
                        "en": "{model}, {year}±2 yrs, adjusted for year"},
    "basis.car_model": {"uz": "Barcha {model} e'lonlari, yil bo'yicha moslashtirilgan",
                        "ru": "Все {model}, с поправкой на год",
                        "en": "All {model} listings, adjusted for year"},
    "basis.realty_drb": {"uz": "{district}, {rooms} xona, {building}", "ru": "{district}, {rooms}-комн., {building}",
                         "en": "{district}, {rooms} rooms, {building}"},
    "basis.realty_dr": {"uz": "{district}, {rooms} xona", "ru": "{district}, {rooms}-комн.",
                        "en": "{district}, {rooms} rooms"},
    "basis.realty_d": {"uz": "{district} tumanidagi barcha kvartiralar", "ru": "Все квартиры в районе {district}",
                       "en": "All apartments in {district}"},
    "basis.realty_r": {"uz": "Toshkent bo'yicha {rooms} xonali kvartiralar",
                       "ru": "{rooms}-комн. квартиры по всему Ташкенту",
                       "en": "{rooms}-room apartments citywide"},
    "basis.rent_drf": {"uz": "{district}, {rooms} xona, {furnished}", "ru": "{district}, {rooms}-комн., {furnished}",
                       "en": "{district}, {rooms} rooms, {furnished}"},
    "basis.per_m2": {"uz": " (1 m² narxi × maydon)", "ru": " (цена за м² × площадь)",
                     "en": " (price per m² × area)"},
    "furnished.yes": {"uz": "mebelli", "ru": "с мебелью", "en": "furnished"},
    "furnished.no": {"uz": "mebelsiz", "ru": "без мебели", "en": "unfurnished"},
    "badge.below": {"uz": "Bozordan {pct}% arzon", "ru": "На {pct}% ниже рынка", "en": "{pct}% below market"},
    "badge.above": {"uz": "Bozordan {pct}% qimmat", "ru": "На {pct}% выше рынка", "en": "{pct}% above market"},
    "badge.fair": {"uz": "Bozor narxida", "ru": "По рыночной цене", "en": "At market price"},
}


def lang_from_header(value: str | None) -> str:
    """Pick uz/ru/en from an Accept-Language header (default uz)."""
    if not value:
        return DEFAULT_LANG
    for part in value.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return DEFAULT_LANG


def detect_lang(text: str, default: str = DEFAULT_LANG) -> str:
    """Guess the language of a user question."""
    if re.search(r"[ўқғҳЎҚҒҲ]", text):
        return "uz"
    if re.search(r"[а-яА-ЯёЁ]", text):
        return "ru"
    low = text.lower()
    if re.search(r"\b(qancha|qanday|nima|kredit olsam|soliq|mening|bormi|kerak|o'|g')", low):
        return "uz"
    if re.search(r"\b(how|what|can i|should|my|loan|tax|budget|which|is it)\b", low):
        return "en"
    return default


def register(messages: dict[str, dict[str, str]]) -> None:
    """Add module-specific messages to the catalogue."""
    _M.update(messages)


def t(key: str, lang: str, **kw: object) -> str:
    """Translate `key` into `lang`, formatting with `kw`."""
    entry = _M.get(key)
    if entry is None:
        return key
    template = entry.get(lang) or entry["en"]
    try:
        return template.format(**kw)
    except (KeyError, IndexError, ValueError):
        return template


_CUR = {"uz": "so'm", "ru": "сум", "en": "UZS"}


def fmt_uzs(amount: float | None, lang: str = DEFAULT_LANG) -> str:
    """Format a UZS amount for generated text: 12 345 678 so'm."""
    if amount is None:
        return "—"
    return f"{round(amount):,}".replace(",", " ") + " " + _CUR.get(lang, "so'm")


def fmt_usd(amount: float | None) -> str:
    """Format a USD amount: $1,234."""
    return "—" if amount is None else f"${round(amount):,}"
