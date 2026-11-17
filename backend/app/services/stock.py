"""Stock command center (#19, #26): every unit rated against the live market.

Pricing is batched: one engine pass per (category, model, condition, attributes) group, and the
engine itself memoizes, so 80 units cost ~20 estimates.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import norm_model
from app.config import DEFAULT_DAYS_TO_SELL, settings
from app.errors import AppError
from app.i18n import fmt_uzs, register, t
from app.models import Company, InventoryItem
from app.services import pricing

register({
    "stock.over": {"uz": "Narx bozordan {pct}% yuqori (p75 {p75} dan qimmat)",
                   "ru": "Цена на {pct}% выше рынка (дороже p75 {p75})",
                   "en": "Priced {pct}% above market (above p75 {p75})"},
    "stock.under": {"uz": "Narx bozordan {pct}% past (p25 {p25} dan arzon)",
                    "ru": "Цена на {pct}% ниже рынка (дешевле p25 {p25})",
                    "en": "Priced {pct}% below market (below p25 {p25})"},
    "stock.fair": {"uz": "Narx bozor oralig'ida ({p25} – {p75})", "ru": "Цена в рыночном диапазоне ({p25} – {p75})",
                   "en": "Price is within the market range ({p25} – {p75})"},
    "stock.aging": {"uz": "{days} kundan beri omborda — p25 narxida tez soting yoki birjaga chiqaring",
                    "ru": "{days} дн. на складе — продайте по p25 или выставьте на биржу",
                    "en": "{days} days in stock — sell at p25 or list it on the exchange"},
    "stock.loss": {"uz": "Tavsiya narx tannarxdan past: zarar {loss}", "ru": "Рекомендуемая цена ниже "
                   "себестоимости: убыток {loss}", "en": "Suggested price is below cost: loss {loss}"},
    "stock.floor": {"uz": "Minimal narx: tannarx + 3%", "ru": "Минимум: себестоимость + 3%",
                    "en": "Floor: cost + 3%"},
    "stock.no_data": {"uz": "Bozor ma'lumoti yetarli emas", "ru": "Недостаточно рыночных данных",
                      "en": "Not enough market data"},
    "stock.no_list": {"uz": "Sotuv narxi kiritilmagan", "ru": "Цена продажи не задана", "en": "No list price set"},
    "stock.days_company": {"uz": "Sizning {n} ta sotuvingiz medianasi", "ru": "Медиана ваших {n} продаж",
                           "en": "Median of your {n} sales"},
    "stock.days_default": {"uz": "Kategoriya bo'yicha standart", "ru": "Стандарт для категории",
                           "en": "Category default"},
})

AGING_DAYS = 30
#: Prices within 1% of p25/p75 still count as fair (absorbs rounding to 1 000 so'm and skewed small samples).
BAND_TOLERANCE = 0.01


def _group_key(it: InventoryItem) -> tuple:
    return (it.category, norm_model(it.model, it.brand), it.condition,
            json.dumps(it.attrs or {}, sort_keys=True), it.district if it.category in ("house", "rent") else None)


def batch_estimates(db: Session, items: list[InventoryItem], lang: str) -> dict[tuple, pricing.Estimate | None]:
    """One pricing pass per group of identical items."""
    out: dict[tuple, pricing.Estimate | None] = {}
    for it in items:
        k = _group_key(it)
        if k not in out:
            out[k] = pricing.try_estimate(db, **pricing.spec_from(it), lang=lang)
    return out


def days_to_sell_base(db: Session, company_id: int, lang: str) -> dict[str, tuple[float, str]]:
    """Median acquired→sold days per category from the company's own sales (≥ 5), else config defaults."""
    sold: dict[str, list[int]] = {}
    for it in db.scalars(select(InventoryItem).where(InventoryItem.company_id == company_id,
                                                     InventoryItem.status == "sold",
                                                     InventoryItem.sold_at.is_not(None))):
        sold.setdefault(it.category, []).append(max((it.sold_at - it.acquired_at).days, 0))
    out = {}
    for cat, default in DEFAULT_DAYS_TO_SELL.items():
        days = sold.get(cat, [])
        if len(days) >= 5:
            out[cat] = (float(median(days)), t("stock.days_company", lang, n=len(days)))
        else:
            out[cat] = (float(default), t("stock.days_default", lang))
    return out


def rate_unit(it: InventoryItem, est: pricing.Estimate | None, days_base: tuple[float, str], today: date,
              lang: str) -> dict[str, Any]:
    """Rating, suggested price, action and reasons for one inventory row."""
    days = (today - it.acquired_at).days
    lp = it.list_price_uzs
    row: dict[str, Any] = {
        "inventory_id": it.id, "store_id": it.store_id, "category": it.category, "brand": it.brand,
        "model": it.model, "condition": it.condition, "attrs": it.attrs or {}, "identifier": it.identifier,
        "qty": it.qty, "list_price_uzs": lp, "unit_cost_uzs": it.unit_cost, "days_in_stock": days,
        "fair_price_uzs": None, "range_uzs": None, "fair_buy_price_uzs": None, "confidence": None,
        "comparables": 0, "basis": None, "rating": "no_data", "vs_market_pct": None,
        "margin_at_list_uzs": round(lp - it.unit_cost) if lp else None,
        "expected_days_to_sell": None, "days_basis": days_base[1], "suggested_price_uzs": None,
        "suggested_action": "keep", "reasons": []}
    aging = days > settings.SLOW_STOCK_DAYS
    if est is None:
        row["reasons"].append(t("stock.no_data", lang))
        if aging:
            row["suggested_action"] = "list_on_exchange"
            row["reasons"].append(t("stock.aging", lang, days=days))
        return row
    p25, p75 = est.range_uzs
    fair = est.fair_price_uzs
    row.update(fair_price_uzs=fair, range_uzs=[p25, p75], fair_buy_price_uzs=est.fair_buy_price_uzs,
               confidence=est.confidence, comparables=est.comparables, basis=est.basis)
    f = lambda v: fmt_uzs(v, lang)  # noqa: E731
    days_factor = 1.0
    if lp is None:
        row["reasons"].append(t("stock.no_list", lang))
        suggested = fair
    else:
        row["vs_market_pct"] = round((lp / fair - 1) * 100, 1)
        if lp > p75 * (1 + BAND_TOLERANCE):
            row["rating"], days_factor = "overpriced", 1.3
            row["reasons"].append(t("stock.over", lang, pct=abs(round(row["vs_market_pct"])), p75=f(p75)))
        elif lp < p25 * (1 - BAND_TOLERANCE):
            row["rating"], days_factor = "underpriced", 0.8
            row["reasons"].append(t("stock.under", lang, pct=abs(round(row["vs_market_pct"])), p25=f(p25)))
        else:
            row["rating"] = "fair"
            row["reasons"].append(t("stock.fair", lang, p25=f(p25), p75=f(p75)))
        suggested = lp
    if aging:
        suggested, action = p25, "list_on_exchange"
        row["reasons"].append(t("stock.aging", lang, days=days))
        if p25 < it.unit_cost:
            row["reasons"].append(t("stock.loss", lang, loss=f((it.unit_cost - p25) * it.qty)))
    elif row["rating"] == "overpriced":
        suggested, action = fair, "reprice_down"
    elif row["rating"] == "underpriced":
        floor = it.unit_cost * 1.03
        suggested, action = max(fair, floor), "reprice_up"
        if floor > fair:
            row["reasons"].append(t("stock.floor", lang))
    else:
        action = "keep"
    row["suggested_price_uzs"] = round(suggested, -3)
    row["suggested_action"] = action
    row["expected_days_to_sell"] = round(days_base[0] * days_factor, 1)
    return row


def units(db: Session, company: Company, lang: str, *, store_id: int | None = None, category: str | None = None,
          ids: list[int] | None = None, today: date | None = None) -> list[dict[str, Any]]:
    """All rated in-stock units for a company (optionally filtered)."""
    today = today or date.today()
    q = select(InventoryItem).where(InventoryItem.company_id == company.id, InventoryItem.status == "in_stock",
                                    InventoryItem.qty > 0)
    if store_id is not None:
        q = q.where(InventoryItem.store_id == store_id)
    if category:
        q = q.where(InventoryItem.category == category)
    if ids is not None:
        q = q.where(InventoryItem.id.in_(ids))
    items = list(db.scalars(q.order_by(InventoryItem.id)))
    ests = batch_estimates(db, items, lang)
    base = days_to_sell_base(db, company.id, lang)
    default = (30.0, t("stock.days_default", lang))
    return [rate_unit(it, ests[_group_key(it)], base.get(it.category, default), today, lang) for it in items]


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Top tiles of the stock screen."""
    over = [r for r in rows if r["rating"] == "overpriced"]
    aging_slow = [r for r in rows if r["days_in_stock"] > settings.SLOW_STOCK_DAYS]
    at_risk = sum((r["list_price_uzs"] - r["suggested_price_uzs"]) * r["qty"] for r in over
                  if r["days_in_stock"] <= settings.SLOW_STOCK_DAYS)
    tied = sum(r["unit_cost_uzs"] * r["qty"] for r in aging_slow)
    return {
        "stock_value_cost_uzs": round(sum(r["unit_cost_uzs"] * r["qty"] for r in rows)),
        "stock_value_market_uzs": round(sum((r["fair_price_uzs"] or 0) * r["qty"] for r in rows)),
        "units_total": sum(r["qty"] for r in rows),
        "units_overpriced": sum(r["qty"] for r in over),
        "units_underpriced": sum(r["qty"] for r in rows if r["rating"] == "underpriced"),
        "units_no_data": sum(r["qty"] for r in rows if r["rating"] == "no_data"),
        "units_older_30d": sum(r["qty"] for r in rows if r["days_in_stock"] > AGING_DAYS),
        "units_older_slow": sum(r["qty"] for r in aging_slow),
        "slow_stock_days": settings.SLOW_STOCK_DAYS,
        "overpricing_at_risk_uzs": round(at_risk),
        "aging_cash_tied_uzs": round(tied),
        "margin_at_risk_uzs": round(at_risk + tied),
    }


def reprice(db: Session, company: Company, prices: dict[int, float]) -> list[int]:
    """Set new list prices in one transaction. Raises 404 for foreign/missing units."""
    if not prices:
        raise AppError("nothing_to_reprice", "No units given", 422)
    if any(p <= 0 for p in prices.values()):
        raise AppError("invalid_price", "Prices must be greater than 0", 422)
    rows = {it.id: it for it in db.scalars(select(InventoryItem).where(
        InventoryItem.company_id == company.id, InventoryItem.id.in_(list(prices)),
        InventoryItem.status == "in_stock"))}
    missing = sorted(set(prices) - set(rows))
    if missing:
        raise AppError("inventory_not_found", "Some units are not in your stock", 404, {"inventory_ids": missing})
    for iid, price in prices.items():
        rows[iid].list_price_uzs = round(price, -3) if price >= 1000 else price
    return list(rows)


# --------------------------------------------------------------------------- #
# Exports                                                                       #
# --------------------------------------------------------------------------- #
STOCK_COLUMNS = ["inventory_id", "store_id", "category", "brand", "model", "condition", "identifier", "qty",
                 "unit_cost_uzs", "list_price_uzs", "fair_price_uzs", "rating", "suggested_price_uzs",
                 "days_in_stock"]
#: 1C import layout (CommerceML-like, semicolon CSV with Russian headers)
STOCK_1C = [("Ид", "inventory_id"), ("Наименование", "_name"), ("Артикул", "identifier"),
            ("ЕдиницаИзмерения", "_unit"), ("Количество", "qty"), ("ЦенаЗакупки", "unit_cost_uzs"),
            ("ЦенаПродажи", "list_price_uzs"), ("Склад", "store_id"), ("Характеристики", "_chars")]
TX_COLUMNS = ["id", "date", "type", "category", "item_category", "brand", "model", "condition", "qty",
              "unit_price", "total", "counterparty", "note", "origin", "store_id"]
TX_1C = [("Дата", "date"), ("ВидОперации", "_kind"), ("Статья", "category"), ("Контрагент", "counterparty"),
         ("Номенклатура", "_name"), ("Количество", "qty"), ("Цена", "unit_price"), ("Сумма", "total"),
         ("Комментарий", "note")]


def _name(r: dict[str, Any]) -> str:
    return " ".join(str(x) for x in (r.get("brand"), r.get("model"), r.get("condition")) if x)


def _1c_value(r: dict[str, Any], key: str) -> Any:
    if key == "_name":
        return _name(r)
    if key == "_unit":
        return "шт"
    if key == "_chars":
        return ", ".join(f"{k}={v}" for k, v in (r.get("attrs") or {}).items())
    if key == "_kind":
        return "Поступление" if r.get("type") == "income" else "Списание"
    v = r.get(key)
    return "" if v is None else v


def export_rows(rows: list[dict[str, Any]], fmt: str, columns: list[str],
                one_c: list[tuple[str, str]], sheet: str) -> tuple[bytes, str, str]:
    """Rows → (bytes, media type, file extension) for xlsx / csv / 1c."""
    if fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = sheet
        ws.append(columns)
        for r in rows:
            ws.append([r.get(c) if not isinstance(r.get(c), dict | list) else json.dumps(r.get(c)) for c in columns])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    buf = io.StringIO()
    if fmt == "1c":
        w = csv.writer(buf, delimiter=";")
        w.writerow([h for h, _ in one_c])
        for r in rows:
            w.writerow([_1c_value(r, k) for _, k in one_c])
        return ("﻿" + buf.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", "1c.csv"
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in columns])
    return buf.getvalue().encode("utf-8"), "text/csv; charset=utf-8", "csv"
