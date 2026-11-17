"""Bookkeeping (#26, #25): import, AI auditor, peer benchmark, budget control, inventory.

All checks are deterministic pandas code; the LLM only phrases recommendations.
"""

from __future__ import annotations

import calendar
import io
import json
import re
import time
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    MONTHLY_BILL_CATEGORIES,
    OPERATING_CATEGORIES,
    TXN_CATEGORY_ALIASES,
    TXN_CATEGORY_LABELS,
    UTILITY_CATEGORIES,
    label,
    norm_model,
)
from app.config import SURPLUS_PRICE_FACTOR, settings
from app.errors import AppError
from app.i18n import fmt_uzs, register, t
from app.models import Budget, Company, InventoryItem, Transaction
from app.services import alerts, llm, pricing

register({
    "audit.duplicate": {
        "uz": "Takroriy yozuv: {category} {total} ({date}, {counterparty}) {n} marta kiritilgan",
        "ru": "Дубликат: {category} {total} ({date}, {counterparty}) внесено {n} раза",
        "en": "Duplicate entry: {category} {total} ({date}, {counterparty}) recorded {n} times"},
    "audit.qty_mismatch": {
        "uz": "{qty} × {unit} = {expected}, lekin jami {total} yozilgan",
        "ru": "{qty} × {unit} = {expected}, но записано {total}",
        "en": "{qty} × {unit} = {expected}, but the total says {total}"},
    "audit.extra_zero": {
        "uz": "{category} {total} — odatdagidan ~10 barobar ko'p (odatda {median}). Ortiqcha nol bo'lishi mumkin",
        "ru": "{category} {total} — примерно в 10 раз больше обычного ({median}). Возможно, лишний ноль",
        "en": "{category} {total} is ~10× the usual {median}. Possibly an extra zero"},
    "audit.price_spread": {
        "uz": "{model} turli narxlarda olingan: {min} va {max} ({pct}% farq)",
        "ru": "{model} закупался по разным ценам: {min} и {max} (разница {pct}%)",
        "en": "{model} was bought at very different prices: {min} vs {max} ({pct}% apart)"},
    "audit.cost_spike": {
        "uz": "{category} xarajati {month} oyida {pct}% oshgan: {cur} (oldingi 3 oy o'rtachasi {avg})",
        "ru": "Расход «{category}» в {month} вырос на {pct}%: {cur} (среднее за 3 мес. {avg})",
        "en": "{category} cost in {month} is up {pct}%: {cur} vs a 3-month average of {avg}"},
    "audit.overpayment": {
        "uz": "{model} bozor xarid narxidan {pct}% qimmat olingan: {unit} (bozor {fair_buy})",
        "ru": "{model} куплен на {pct}% дороже рыночной закупочной цены: {unit} (рынок {fair_buy})",
        "en": "{model} bought {pct}% above the market purchase price: {unit} vs {fair_buy}"},
    "audit.no_counterparty": {
        "uz": "{category} {total} ({date}) — kontragent ko'rsatilmagan",
        "ru": "{category} {total} ({date}) — не указан контрагент",
        "en": "{category} {total} ({date}) has no counterparty"},
    "rec.duplicate": {"uz": "Takroriy yozuvlarni o'chiring va to'lov ikki marta qilinmaganini bank ko'chirmasidan "
                            "tekshiring.",
                      "ru": "Удалите дубликаты и проверьте по выписке, что оплата не прошла дважды.",
                      "en": "Delete duplicate entries and check the bank statement for a double payment."},
    "rec.qty_mismatch": {"uz": "Miqdor × narx jamiga teng bo'lmagan yozuvlarni hisob-faktura bilan solishtiring.",
                         "ru": "Сверьте записи, где кол-во × цена ≠ сумма, со счетами-фактурами.",
                         "en": "Reconcile entries where qty × price ≠ total against the invoices."},
    "rec.extra_zero": {"uz": "Odatdagidan 10 barobar katta summalarni tekshiring — ehtimol ortiqcha nol.",
                       "ru": "Проверьте суммы, в 10 раз больше обычных, — вероятно, лишний ноль.",
                       "en": "Check amounts that are 10× the usual — likely a typo with an extra zero."},
    "rec.price_spread": {"uz": "Bir xil model uchun yagona xarid narxini belgilang va 2–3 yetkazib beruvchidan taklif "
                               "so'rang (RFQ).",
                         "ru": "Установите единую закупочную цену на модель и запрашивайте 2–3 предложения (RFQ).",
                         "en": "Set one target purchase price per model and request 2–3 quotes (RFQ)."},
    "rec.cost_spike": {"uz": "Kommunal to'lovlar o'sishini hisoblagich ko'rsatkichlari bilan tekshiring.",
                       "ru": "Проверьте рост коммунальных расходов по показаниям счётчиков.",
                       "en": "Check the utility cost jump against meter readings and the tariff."},
    "rec.overpayment": {"uz": "Bozor xarid narxidan qimmat xaridlarni to'xtating: B2B birjada RFQ joylang.",
                        "ru": "Не закупайте выше рынка: разместите RFQ на B2B-бирже.",
                        "en": "Stop buying above the market purchase price: post an RFQ on the B2B exchange."},
    "rec.no_counterparty": {"uz": "1 mln so'mdan katta xarajatlarga kontragent va hujjat biriktiring.",
                            "ru": "Указывайте контрагента и документ для расходов свыше 1 млн сум.",
                            "en": "Record a counterparty and document for every expense above 1M so'm."},
    "rec.clean": {"uz": "Jiddiy xatolar topilmadi. Hisobni har hafta yangilab boring.",
                  "ru": "Серьёзных ошибок не найдено. Обновляйте учёт еженедельно.",
                  "en": "No serious issues found. Keep the books updated weekly."},
    "budget.over": {"uz": "{category}: reja {planned}, fakt {fact} — {pct}% oshib ketgan",
                    "ru": "{category}: план {planned}, факт {fact} — превышение на {pct}%",
                    "en": "{category}: plan {planned}, actual {fact} — {pct}% over"},
    "budget.at_risk": {
        "uz": "{category}: {used}% ishlatilgan, oy oxiriga {forecast} kutilmoqda (reja {planned})",
        "ru": "{category}: использовано {used}%, прогноз на конец месяца {forecast} (план {planned})",
        "en": "{category}: {used}% used, month-end forecast {forecast} (plan {planned})"},
    "budget.alert.title": {"uz": "Byudjet: {category}", "ru": "Бюджет: {category}", "en": "Budget: {category}"},
    "stock.slow": {"uz": "{days} kundan beri sotilmagan. {price} ga tushirib, B2B birjada 'surplus' sifatida "
                         "joylang.",
                   "ru": "Не продаётся {days} дн. Снизьте до {price} и выставьте как излишки на B2B-бирже.",
                   "en": "Unsold for {days} days. Reprice to {price} and list it as surplus on the exchange."},
    "reval.below_cost": {"uz": "Bozor narxi tannarxdan past — tezroq soting, qayta xarid qilmang.",
                         "ru": "Рынок ниже себестоимости — продавайте быстрее, не докупайте.",
                         "en": "Market is below your cost — sell soon and do not restock."},
    "reval.good": {"uz": "Yaxshi marja — joriy narxda soting.", "ru": "Хорошая маржа — продавайте по рынку.",
                   "en": "Healthy margin — sell at the market price."},
    "reval.thin": {"uz": "Marja past — tannarxni pasaytirish uchun ulgurji takliflarni ko'ring.",
                   "ru": "Маржа тонкая — ищите оптовые предложения дешевле.",
                   "en": "Thin margin — look for cheaper wholesale offers."},
    "reval.no_data": {"uz": "Bozor ma'lumoti yetarli emas.", "ru": "Недостаточно рыночных данных.",
                      "en": "Not enough market data."},
})

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# --------------------------------------------------------------------------- #
# Upload                                                                        #
# --------------------------------------------------------------------------- #
_COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["date", "sana", "дата", "kun", "день"],
    "type": ["type", "tur", "turi", "тип", "вид"],
    "category": ["category", "kategoriya", "категория", "modda", "статья", "toifa"],
    "total": ["total", "summa", "сумма", "jami", "итого", "amount", "сумма итого"],
    "qty": ["qty", "quantity", "soni", "miqdor", "miqdori", "кол-во", "количество", "kol-vo"],
    "unit_price": ["unit_price", "price", "narx", "narxi", "цена", "birlik narxi", "цена за ед"],
    "counterparty": ["counterparty", "kontragent", "контрагент", "supplier", "yetkazib beruvchi", "поставщик",
                     "kimga", "kimdan", "mijoz", "клиент"],
    "note": ["note", "izoh", "примечание", "comment", "комментарий", "описание", "tavsif"],
    "item_category": ["item_category", "mahsulot turi", "тип товара"],
    "brand": ["brand", "brend", "бренд", "marka", "марка"],
    "model": ["model", "модель", "mahsulot", "товар", "product"],
    "condition": ["condition", "holat", "holati", "состояние"],
}
_TYPE_ALIASES = {"income": "income", "kirim": "income", "доход": "income", "приход": "income", "daromad": "income",
                 "expense": "expense", "chiqim": "expense", "расход": "expense", "xarajat": "expense"}

TEMPLATE_CSV = (
    "date,type,category,item_category,brand,model,condition,qty,unit_price,total,counterparty,note\n"
    "2026-11-03,expense,stock_purchase,phone,Apple,iPhone 13 128GB,A,3,4300000,12900000,TechOpt Wholesale,\n"
    "2026-11-05,expense,electricity,,,,,1,,820000,Toshkent shahar elektr tarmoqlari,Oktabr\n"
    "2026-11-06,income,sale,phone,Apple,iPhone 13 128GB,A,1,5100000,5100000,Chakana xaridor,\n"
    "2026-11-07,expense,rent,,,,,1,,8000000,IP Karimov (ijara),Noyabr ijarasi\n"
)


def _canon_col(name: str) -> str | None:
    low = str(name).strip().lower()
    for canon, aliases in _COLUMN_ALIASES.items():
        if low in aliases:
            return canon
    return None


def parse_amount(v: Any) -> float | None:
    """'1 200 000', '1,200,000.50', '3.5 mln', 1200000 → float."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, int | float):
        return float(v)
    s = str(v).strip().lower().replace(" ", " ")
    if not s:
        return None
    mult = 1.0
    if re.search(r"(mln|млн)", s):
        mult = 1e6
    elif re.search(r"(ming|тыс)", s):
        mult = 1e3
    s = re.sub(r"[^\d,.\-]", "", s)
    if s.count(",") and s.count("."):
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) <= 2:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s) * mult
    except ValueError:
        return None


def _canon_category(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if s in EXPENSE_CATEGORIES or s in INCOME_CATEGORIES:
        return s
    if s in TXN_CATEGORY_ALIASES:
        return TXN_CATEGORY_ALIASES[s]
    for k, val in TXN_CATEGORY_ALIASES.items():
        if k in s:
            return val
    return None


def parse_upload(content: bytes, filename: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a CSV/XLSX book export. Returns (valid rows, errors[{row, error}])."""
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content), dtype=object)
        else:
            text = content.decode("utf-8-sig", errors="replace")
            sep = ";" if text.count(";") > text.count(",") else ","
            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=object)
    except Exception as exc:
        raise AppError("unreadable_file", f"Could not read file: {type(exc).__name__}", 400) from exc
    mapping = {c: _canon_col(c) for c in df.columns}
    df = df.rename(columns={c: m for c, m in mapping.items() if m})
    missing = [c for c in ("date", "category") if c not in df.columns]
    if missing or ("total" not in df.columns and not {"qty", "unit_price"} <= set(df.columns)):
        raise AppError("missing_columns", "Required columns: date, category and total (or qty + unit_price)", 400,
                       {"missing": missing or ["total"], "found": [str(c) for c in df.columns]})
    rows, errors = [], []
    for i, rec in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        try:
            rows.append(_row(rec))
        except ValueError as exc:
            errors.append({"row": i, "error": str(exc)})
    return rows, errors


def _clean(v: Any) -> Any:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def _row(rec: dict[str, Any]) -> dict[str, Any]:
    d = pd.to_datetime(_clean(rec.get("date")), dayfirst=True, errors="coerce")
    if d is pd.NaT or d is None or pd.isna(d):
        raise ValueError("invalid date")
    cat = _canon_category(rec.get("category"))
    if not cat:
        raise ValueError(f"unknown category '{rec.get('category')}'")
    qty = parse_amount(rec.get("qty")) or 1.0
    unit = parse_amount(rec.get("unit_price"))
    total = parse_amount(rec.get("total"))
    if total is None and unit is not None:
        total = qty * unit
    if total is None or total <= 0:
        raise ValueError("invalid total")
    type_raw = str(_clean(rec.get("type")) or "").lower()
    type_ = _TYPE_ALIASES.get(type_raw) or ("income" if cat in INCOME_CATEGORIES else "expense")
    item_cat = _clean(rec.get("item_category"))
    return {"date": d.date(), "type": type_, "category": cat, "qty": qty, "unit_price": unit, "total": total,
            "counterparty": _clean(rec.get("counterparty")), "note": _clean(rec.get("note")),
            "item_category": item_cat if item_cat in ("phone", "laptop", "car", "house", "rent") else None,
            "brand": _clean(rec.get("brand")), "model": _clean(rec.get("model")),
            "condition": _clean(rec.get("condition")), "attrs": _attrs_from_model(_clean(rec.get("model")))}


def _attrs_from_model(model: str | None) -> dict[str, Any]:
    """Pull storage/RAM from a free-text model ('iPhone 13 128GB', 'Redmi Note 13 8/256')."""
    if not model:
        return {}
    a: dict[str, Any] = {}
    m = re.search(r"\b(\d{1,2})\s*/\s*(\d{2,4})\b", model)
    if m:
        a["ram_gb"], a["storage_gb"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(\d{2,4})\s*(gb|гб)\b", model, re.I)
    if m:
        a["storage_gb"] = int(m.group(1))
    m = re.search(r"\b1\s*tb\b", model, re.I)
    if m:
        a["storage_gb"] = 1024
    return a


def create_transactions(db: Session, company: Company, rows: list[dict[str, Any]], origin: str) -> list[Transaction]:
    txs = [Transaction(company_id=company.id, origin=origin, **r) for r in rows]
    db.add_all(txs)
    db.commit()
    _audit_cache.pop(company.id, None)
    return txs


INVOICE_PROMPT = ("""You read a photo of a purchase invoice / receipt from an Uzbek business (Uzbek or Russian).
Return JSON: {"date": "YYYY-MM-DD" or null, "counterparty": seller name or null, "items": [
 {"description": str, "item_category": "phone"|"laptop"|"car"|null, "brand": str|null, "model": str|null,
  "condition": "new"|"A"|"B"|"C"|null, "qty": number, "unit_price": number|null, "total": number,
  "category": one of CATEGORIES}]}
Amounts are in UZS unless a $ sign is shown (then add "currency": "USD" to the item). Copy numbers exactly as
printed. Unknown values are null. Never invent items.""").replace("CATEGORIES", json.dumps(EXPENSE_CATEGORIES))


def extract_invoice(image: bytes, mime_type: str) -> list[dict[str, Any]]:
    """Vision OCR of an invoice → transaction rows (not saved). 503 without an LLM key."""
    if not llm.available():
        raise AppError("llm_unavailable", "Invoice OCR needs GEMINI_API_KEY", 503)
    data = llm.vision_json(image, mime_type, INVOICE_PROMPT)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise AppError("ocr_failed", "Could not read the invoice", 422)
    from app.services import fx

    d = pd.to_datetime(data.get("date"), errors="coerce")
    tx_date = d.date() if not pd.isna(d) else date.today()
    rows = []
    for it in data["items"]:
        qty = parse_amount(it.get("qty")) or 1.0
        unit = parse_amount(it.get("unit_price"))
        total = parse_amount(it.get("total")) or ((unit or 0) * qty)
        if not total:
            continue
        if str(it.get("currency", "")).upper() == "USD":
            total, unit = fx.to_uzs(total, "USD"), (fx.to_uzs(unit, "USD") if unit else None)
        cat = it.get("category") if it.get("category") in EXPENSE_CATEGORIES else (
            "stock_purchase" if it.get("item_category") else "other")
        rows.append({"date": tx_date, "type": "expense", "category": cat, "qty": qty, "unit_price": unit,
                     "total": round(total), "counterparty": data.get("counterparty"),
                     "note": it.get("description"), "item_category": it.get("item_category"),
                     "brand": it.get("brand"), "model": it.get("model"), "condition": it.get("condition"),
                     "attrs": _attrs_from_model(it.get("model"))})
    return rows


# --------------------------------------------------------------------------- #
# AI Auditor                                                                    #
# --------------------------------------------------------------------------- #
_audit_cache: dict[int, tuple[float, tuple, list[dict[str, Any]]]] = {}
AUDIT_CACHE_TTL_S = 60.0


def _frame(db: Session, company_id: int, since: date | None = None) -> pd.DataFrame:
    q = select(Transaction).where(Transaction.company_id == company_id)
    if since:
        q = q.where(Transaction.date >= since)
    rows = [{"id": t.id, "date": t.date, "type": t.type, "category": t.category, "item_category": t.item_category,
             "brand": t.brand, "model": t.model, "condition": t.condition, "attrs": t.attrs or {},
             "qty": t.qty, "unit_price": t.unit_price, "total": t.total, "counterparty": t.counterparty,
             "origin": t.origin} for t in db.scalars(q)]
    df = pd.DataFrame(rows, columns=["id", "date", "type", "category", "item_category", "brand", "model", "condition",
                                     "attrs", "qty", "unit_price", "total", "counterparty", "origin"])
    if not df.empty:
        df["month"] = df["date"].map(lambda d: d.strftime("%Y-%m"))
    return df


def _cat(c: str, lang: str) -> str:
    return label(TXN_CATEGORY_LABELS, c, lang)


def _flag(type_: str, severity: str, message: str, ids: list[int], amount: float, **extra: Any) -> dict[str, Any]:
    return {"type": type_, "severity": severity, "message": message, "transaction_ids": [int(i) for i in ids],
            "amount_at_risk_uzs": round(max(amount, 0.0)), **extra}


def _audit_flags(db: Session, company_id: int, lang: str) -> list[dict[str, Any]]:
    """Run all 7 checks. Returns flags with transaction ids and money at risk."""
    df = _frame(db, company_id)
    if df.empty:
        return []
    flags: list[dict[str, Any]] = []
    exp = df[df["type"] == "expense"]
    suspicious: set[int] = set()

    # 1. duplicates
    key = ["date", "category", "counterparty", "total", "model"]
    dup = df.assign(counterparty=df["counterparty"].fillna(""), model=df["model"].fillna(""))
    for _, g in dup.groupby(key, sort=False):
        if len(g) > 1:
            r = g.iloc[0]
            suspicious.update(g["id"].iloc[1:].tolist())
            flags.append(_flag("duplicate", "high", t("audit.duplicate", lang, category=_cat(r["category"], lang),
                                                       total=fmt_uzs(r["total"], lang), date=r["date"].isoformat(),
                                                       counterparty=r["counterparty"] or "—", n=len(g)),
                               g["id"].tolist(), float(r["total"]) * (len(g) - 1)))

    # 2. qty × unit_price ≠ total
    m = df[df["unit_price"].notna() & (df["qty"] > 0)]
    for r in m.itertuples():
        expected = r.qty * r.unit_price
        if r.total and abs(expected - r.total) / r.total > 0.01:
            flags.append(_flag("qty_mismatch", "medium", t("audit.qty_mismatch", lang, qty=f"{r.qty:g}",
                                                            unit=fmt_uzs(r.unit_price, lang),
                                                            expected=fmt_uzs(expected, lang),
                                                            total=fmt_uzs(r.total, lang)),
                               [r.id], abs(r.total - expected)))

    # 3. extra-zero typos (operating expenses)
    for cat, g in exp[exp["category"] != "stock_purchase"].groupby("category"):
        if len(g) < 4:
            continue
        totals = g["total"].to_numpy(float)
        for idx, r in enumerate(g.itertuples()):
            others = np.delete(totals, idx)
            med = float(np.median(others))
            if med > 0 and r.total >= 5 * med and 0.5 <= (r.total / 10) / med <= 2:
                suspicious.add(r.id)
                flags.append(_flag("extra_zero", "high", t("audit.extra_zero", lang, category=_cat(cat, lang),
                                                            total=fmt_uzs(r.total, lang),
                                                            median=fmt_uzs(med, lang)),
                                   [r.id], r.total - r.total / 10))

    # 4. same model bought at prices > 25% apart
    stock = exp[(exp["category"] == "stock_purchase") & exp["model"].notna()].copy()
    if not stock.empty:
        stock["unit"] = stock.apply(lambda r: r["unit_price"] if pd.notna(r["unit_price"]) else r["total"] / r["qty"],
                                    axis=1)
        stock["key"] = stock.apply(lambda r: (norm_model(r["model"], r["brand"]), r["condition"] or "",
                                              (r["attrs"] or {}).get("storage_gb")), axis=1)
        for _, g in stock.groupby("key"):
            if len(g) < 2:
                continue
            lo, hi = g.loc[g["unit"].idxmin()], g.loc[g["unit"].idxmax()]
            if lo["unit"] > 0 and hi["unit"] / lo["unit"] > 1.25:
                pct = round((hi["unit"] / lo["unit"] - 1) * 100)
                flags.append(_flag("price_spread", "medium", t("audit.price_spread", lang, model=hi["model"],
                                                                min=fmt_uzs(lo["unit"], lang),
                                                                max=fmt_uzs(hi["unit"], lang), pct=pct),
                                   [lo["id"], hi["id"]], (hi["unit"] - lo["unit"]) * hi["qty"]))

    # 5. utility cost spikes (> 30% vs the previous 3 months), ignoring flagged typos/duplicates
    clean = exp[~exp["id"].isin(suspicious)]
    months = sorted(df["month"].unique())
    for cat in UTILITY_CATEGORIES:
        series = clean[clean["category"] == cat].groupby("month")["total"].sum()
        for mon in months[-2:]:
            if mon not in series.index:
                continue
            i = months.index(mon)
            prev = [series[p] for p in months[max(0, i - 3):i] if p in series.index]
            if len(prev) < 2:
                continue
            avg = float(np.mean(prev))
            cur = float(series[mon])
            if avg > 0 and cur > avg * 1.3:
                ids = clean[(clean["category"] == cat) & (clean["month"] == mon)]["id"].tolist()
                flags.append(_flag("cost_spike", "medium", t("audit.cost_spike", lang, category=_cat(cat, lang),
                                                              month=mon, pct=round((cur / avg - 1) * 100),
                                                              cur=fmt_uzs(cur, lang), avg=fmt_uzs(avg, lang)),
                                   ids, cur - avg))

    # 6. overpayment vs the live market fair purchase price
    for r in stock.itertuples() if not stock.empty else []:
        if r.item_category not in ("phone", "laptop", "car"):
            continue
        est = pricing.try_estimate(db, category=r.item_category, model=r.model, brand=r.brand,
                                   condition=r.condition, attrs=r.attrs or {})
        if est is None or est.confidence == "low":
            continue
        if r.unit > est.fair_buy_price_uzs * 1.10:
            pct = round((r.unit / est.fair_buy_price_uzs - 1) * 100)
            flags.append(_flag("overpayment", "high", t("audit.overpayment", lang, model=r.model, pct=pct,
                                                          unit=fmt_uzs(r.unit, lang),
                                                          fair_buy=fmt_uzs(est.fair_buy_price_uzs, lang)),
                               [r.id], (r.unit - est.fair_buy_price_uzs) * r.qty,
                               fair_buy_price_uzs=est.fair_buy_price_uzs))

    # 7. large expenses without a counterparty
    no_cp = exp[(exp["total"] > 1_000_000) & (exp["counterparty"].isna() | (exp["counterparty"] == ""))]
    for r in no_cp.itertuples():
        flags.append(_flag("no_counterparty", "low", t("audit.no_counterparty", lang, category=_cat(r.category, lang),
                                                        total=fmt_uzs(r.total, lang), date=r.date.isoformat()),
                           [r.id], 0.0))
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f["severity"]], -f["amount_at_risk_uzs"]))
    return flags


def audit_flags(db: Session, company_id: int, lang: str = "uz") -> list[dict[str, Any]]:
    """Cached audit flags (invalidated when the books change or after 60 s)."""
    cnt, max_id = db.execute(select(func.count(Transaction.id), func.max(Transaction.id))
                             .where(Transaction.company_id == company_id)).one()
    sig = (cnt, max_id, lang)
    hit = _audit_cache.get(company_id)
    if hit and hit[1] == sig and time.monotonic() - hit[0] < AUDIT_CACHE_TTL_S:
        return hit[2]
    flags = _audit_flags(db, company_id, lang)
    _audit_cache[company_id] = (time.monotonic(), sig, flags)
    return flags


def audit_summary(flags: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_sev = {"high": 0, "medium": 0, "low": 0}
    for f in flags:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        by_sev[f["severity"]] += 1
    return {"issues": len(flags), "by_type": by_type, "by_severity": by_sev,
            "amount_at_risk_uzs": round(sum(f["amount_at_risk_uzs"] for f in flags))}


def fallback_recommendations(flags: list[dict[str, Any]], lang: str) -> list[str]:
    if not flags:
        return [t("rec.clean", lang)]
    risk: dict[str, float] = {}
    for f in flags:
        risk[f["type"]] = risk.get(f["type"], 0) + f["amount_at_risk_uzs"] + 1
    ranked = sorted(risk, key=risk.get, reverse=True)  # type: ignore[arg-type]
    return [t(f"rec.{k}", lang) for k in ranked[:5]]


def recommendations(flags: list[dict[str, Any]], lang: str, company: Company) -> tuple[list[str], str]:
    """3–5 recommendations: LLM phrasing of the computed flags, deterministic fallback."""
    fallback = fallback_recommendations(flags, lang)
    if not flags or not llm.available():
        return fallback, "rules"
    facts = [{"type": f["type"], "severity": f["severity"], "message": f["message"],
              "amount_at_risk_uzs": f["amount_at_risk_uzs"]} for f in flags[:15]]
    lang_name = {"uz": "Uzbek (Latin)", "ru": "Russian", "en": "English"}[lang]
    prompt = (f"You are an accountant advising a small {company.role} business in Tashkent. Based ONLY on these "
              f"audit findings, write 3-5 short, concrete recommendations in {lang_name}. Do not invent numbers; "
              f"you may quote numbers that appear in the findings. Return JSON: {{\"recommendations\": [str]}}.\n"
              f"Findings: {json.dumps(facts, ensure_ascii=False)}")
    out = llm.generate_json(prompt, timeout=settings.LLM_TIMEOUT_S)
    recs = out.get("recommendations") if isinstance(out, dict) else None
    if isinstance(recs, list) and 3 <= len(recs) <= 5 and all(isinstance(r, str) for r in recs):
        return recs, "llm"
    return fallback, "rules"


# --------------------------------------------------------------------------- #
# Benchmark                                                                     #
# --------------------------------------------------------------------------- #

def _monthly_opex(db: Session, company_id: int, today: date) -> tuple[float, dict[str, float]] | None:
    """Average monthly operating cost over the last 3 complete months with data."""
    start = (today.replace(day=1) - timedelta(days=95)).replace(day=1)
    df = _frame(db, company_id, since=start)
    if df.empty:
        return None
    cur = today.strftime("%Y-%m")
    df = df[(df["type"] == "expense") & df["category"].isin(OPERATING_CATEGORIES) & (df["month"] != cur)]
    months = sorted(df["month"].unique())[-3:]
    if not months:
        return None
    df = df[df["month"].isin(months)]
    n = len(months)
    per_cat = (df.groupby("category")["total"].sum() / n).to_dict()
    return float(df["total"].sum() / n), {k: float(v) for k, v in per_cat.items()}


def benchmark(db: Session, company: Company, today: date | None = None) -> dict[str, Any]:
    """Anonymized percentile of monthly operating costs vs same-role peers sharing a category."""
    today = today or date.today()
    mine = _monthly_opex(db, company.id, today)
    peers = []
    for c in db.scalars(select(Company).where(Company.role == company.role, Company.id != company.id)):
        if set(c.categories or []) & set(company.categories or []):
            v = _monthly_opex(db, c.id, today)
            if v:
                peers.append(v)
    result: dict[str, Any] = {"role": company.role, "peers": len(peers), "enough_peers": len(peers) >= 3,
                              "my_monthly_opex_uzs": round(mine[0]) if mine else None, "percentile": None,
                              "peer_median_uzs": None, "peer_p25_uzs": None, "peer_p75_uzs": None, "categories": []}
    if len(peers) < 3 or not mine:
        return result
    totals = np.array([p[0] for p in peers])
    result.update(percentile=round(float((totals < mine[0]).mean() * 100)),
                  peer_median_uzs=round(float(np.median(totals))),
                  peer_p25_uzs=round(float(np.percentile(totals, 25))),
                  peer_p75_uzs=round(float(np.percentile(totals, 75))))
    for cat in OPERATING_CATEGORIES:
        vals = np.array([p[1].get(cat, 0.0) for p in peers])
        my = mine[1].get(cat, 0.0)
        if my == 0 and not vals.any():
            continue
        med = float(np.median(vals))
        result["categories"].append({"category": cat, "mine_uzs": round(my), "peer_median_uzs": round(med),
                                     "diff_pct": round((my / med - 1) * 100, 1) if med else None,
                                     "percentile": round(float((vals < my).mean() * 100))})
    return result


# --------------------------------------------------------------------------- #
# Budget control                                                                #
# --------------------------------------------------------------------------- #

def budget_status(db: Session, company: Company, month: str, lang: str, today: date | None = None,
                  create_alerts: bool = True) -> dict[str, Any]:
    """Plan vs fact per expense category with month-end forecast and early warnings."""
    today = today or date.today()
    try:
        y, m = (int(x) for x in month.split("-"))
        start = date(y, m, 1)
    except ValueError as exc:
        raise AppError("invalid_month", "month must be YYYY-MM", 422) from exc
    days_in = calendar.monthrange(y, m)[1]
    end = date(y, m, days_in)
    if today < start:
        elapsed = 0
    elif today > end:
        elapsed = days_in
    else:
        elapsed = today.day
    plans = {b.category: b.planned for b in db.scalars(select(Budget).where(Budget.company_id == company.id,
                                                                             Budget.month == month))}
    txs = list(db.scalars(select(Transaction).where(Transaction.company_id == company.id,
                                                     Transaction.type == "expense",
                                                     Transaction.date >= start, Transaction.date <= end)))
    prev_start = (start - timedelta(days=1)).replace(day=1)
    prev_fact: dict[str, float] = {}
    for tx in db.scalars(select(Transaction).where(Transaction.company_id == company.id, Transaction.type == "expense",
                                                    Transaction.date >= prev_start, Transaction.date < start)):
        prev_fact[tx.category] = prev_fact.get(tx.category, 0) + tx.total
    by_cat: dict[str, list[Transaction]] = {}
    for tx in txs:
        by_cat.setdefault(tx.category, []).append(tx)

    items, explanations = [], []
    for cat in EXPENSE_CATEGORIES:
        rows = by_cat.get(cat, [])
        planned = plans.get(cat)
        fact = float(sum(r.total for r in rows))
        if planned is None and fact == 0:
            continue
        if cat in MONTHLY_BILL_CATEGORIES:
            forecast = fact if fact > 0 or elapsed >= days_in else prev_fact.get(cat, 0.0)
        else:
            forecast = fact / elapsed * days_in if elapsed else 0.0
        used = round(fact / planned * 100, 1) if planned else None
        if planned is None:
            status = "no_plan"
        elif fact > planned:
            status = "over"
        elif forecast > planned or (cat not in MONTHLY_BILL_CATEGORIES and used is not None and used >= 90):
            status = "at_risk"
        else:
            status = "ok"
        top = sorted(rows, key=lambda r: r.total, reverse=True)[:3]
        explanation = None
        name = _cat(cat, lang)
        if status == "over":
            explanation = t("budget.over", lang, category=name, planned=fmt_uzs(planned, lang),
                            fact=fmt_uzs(fact, lang), pct=round((fact / planned - 1) * 100))
        elif status == "at_risk":
            explanation = t("budget.at_risk", lang, category=name, used=round(used or 0),
                            forecast=fmt_uzs(forecast, lang), planned=fmt_uzs(planned, lang))
        if explanation:
            explanations.append(explanation)
            if create_alerts and month == today.strftime("%Y-%m"):
                key = f"budget:{month}:{cat}"
                if not alerts.exists_today(db, company.id, "budget", key):
                    kw = {"category": {lg: _cat(cat, lg) for lg in ("uz", "ru", "en")}}
                    i18n = {}
                    for lg in ("uz", "ru", "en"):
                        msg_kw = {"category": kw["category"][lg], "planned": fmt_uzs(planned, lg),
                                  "fact": fmt_uzs(fact, lg), "pct": round((fact / planned - 1) * 100) if planned else 0,
                                  "used": round(used or 0), "forecast": fmt_uzs(forecast, lg)}
                        i18n[lg] = {"title": t("budget.alert.title", lg, category=kw["category"][lg]),
                                    "message": t(f"budget.{status}", lg, **msg_kw)}
                    alerts.create(db, company_id=company.id, type="budget", category=None,
                                  severity="high" if status == "over" else "medium", i18n=i18n,
                                  payload={"key": key, "month": month, "budget_category": cat, "status": status},
                                  commit=False)
        items.append({"category": cat, "planned_uzs": planned, "fact_uzs": round(fact),
                      "used_pct": used, "forecast_uzs": round(forecast), "status": status,
                      "explanation": explanation,
                      "top_transactions": [{"id": r.id, "date": r.date, "total_uzs": r.total,
                                            "counterparty": r.counterparty, "note": r.note or r.model} for r in top]})
    db.commit()
    planned_total = sum(v for v in plans.values())
    fact_planned = sum(i["fact_uzs"] for i in items if i["planned_uzs"] is not None)
    return {"month": month, "days_elapsed": elapsed, "days_in_month": days_in, "items": items,
            "planned_total_uzs": round(planned_total), "fact_total_uzs": round(sum(i["fact_uzs"] for i in items)),
            "forecast_total_uzs": round(sum(i["forecast_uzs"] for i in items)),
            "used_pct": round(fact_planned / planned_total * 100, 1) if planned_total else None,
            "explanations": explanations}


def set_budget(db: Session, company: Company, month: str, items: dict[str, float]) -> None:
    existing = {b.category: b for b in db.scalars(select(Budget).where(Budget.company_id == company.id,
                                                                        Budget.month == month))}
    for cat, planned in items.items():
        if cat not in EXPENSE_CATEGORIES:
            raise AppError("invalid_category", f"Unknown expense category '{cat}'", 422)
        if cat in existing:
            existing[cat].planned = planned
        else:
            db.add(Budget(company_id=company.id, month=month, category=cat, planned=planned))
    db.commit()


# --------------------------------------------------------------------------- #
# Inventory: slow stock and revaluation                                        #
# --------------------------------------------------------------------------- #

def _inv_estimate(db: Session, it: InventoryItem) -> pricing.Estimate | None:
    return pricing.try_estimate(db, **pricing.spec_from(it))


def slow_stock(db: Session, company: Company, lang: str, today: date | None = None) -> dict[str, Any]:
    """Units older than SLOW_STOCK_DAYS, cash tied up and a suggested surplus price."""
    today = today or date.today()
    cutoff = today - timedelta(days=settings.SLOW_STOCK_DAYS)
    items = []
    for it in db.scalars(select(InventoryItem).where(InventoryItem.company_id == company.id,
                                                      InventoryItem.status == "in_stock",
                                                      InventoryItem.acquired_at <= cutoff)
                         .order_by(InventoryItem.acquired_at)):
        est = _inv_estimate(db, it)
        age = (today - it.acquired_at).days
        suggested = round(est.fair_price_uzs * SURPLUS_PRICE_FACTOR, -3) if est else None
        items.append({"inventory_id": it.id, "category": it.category, "brand": it.brand, "model": it.model,
                      "condition": it.condition, "attrs": it.attrs, "qty": it.qty, "age_days": age,
                      "unit_cost_uzs": it.unit_cost, "cash_tied_uzs": round(it.unit_cost * it.qty),
                      "fair_price_uzs": est.fair_price_uzs if est else None,
                      "suggested_surplus_price_uzs": suggested,
                      "loss_vs_cost_uzs": round((it.unit_cost - suggested) * it.qty) if suggested and
                      suggested < it.unit_cost else 0,
                      "advice": t("stock.slow", lang, days=age, price=fmt_uzs(suggested, lang)) if suggested
                      else t("reval.no_data", lang)})
    return {"threshold_days": settings.SLOW_STOCK_DAYS, "units": sum(i["qty"] for i in items),
            "cash_tied_uzs": sum(i["cash_tied_uzs"] for i in items), "items": items}


def revaluation(db: Session, company: Company, lang: str) -> dict[str, Any]:
    """Market value of in-stock inventory and unrealized margin."""
    items, total_cost, total_value = [], 0.0, 0.0
    for it in db.scalars(select(InventoryItem).where(InventoryItem.company_id == company.id,
                                                      InventoryItem.status == "in_stock")):
        est = _inv_estimate(db, it)
        cost = it.unit_cost * it.qty
        total_cost += cost
        if est is None:
            items.append({"inventory_id": it.id, "category": it.category, "brand": it.brand, "model": it.model,
                          "condition": it.condition, "qty": it.qty, "unit_cost_uzs": it.unit_cost,
                          "market_value_per_unit_uzs": None, "market_value_uzs": None, "unrealized_margin_uzs": None,
                          "margin_pct": None, "basis": None, "advice": t("reval.no_data", lang)})
            continue
        value = est.fair_price_uzs * it.qty
        total_value += value
        margin = value - cost
        pct = round(margin / cost * 100, 1) if cost else None
        advice = t("reval.below_cost" if margin < 0 else ("reval.good" if (pct or 0) >= 12 else "reval.thin"), lang)
        items.append({"inventory_id": it.id, "category": it.category, "brand": it.brand, "model": it.model,
                      "condition": it.condition, "qty": it.qty, "unit_cost_uzs": it.unit_cost,
                      "market_value_per_unit_uzs": est.fair_price_uzs, "market_value_uzs": round(value),
                      "unrealized_margin_uzs": round(margin), "margin_pct": pct, "basis": est.basis,
                      "advice": advice})
    return {"total_cost_uzs": round(total_cost), "market_value_uzs": round(total_value),
            "unrealized_margin_uzs": round(total_value - sum(i["unit_cost_uzs"] * i["qty"] for i in items
                                                             if i["market_value_uzs"] is not None)),
            "items": items}
