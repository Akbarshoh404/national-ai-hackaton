"""Integration adapters.

Telegram is live (the ingest worker). Didox, Soliq, BILLZ, 1C and bank statements are adapters with one
interface (`Adapter.fetch`); **only `mock` implementations exist**. They read sample files from `data/samples/`.
Real API access needs partner agreements with Didox / Soliq / BILLZ / 1C partners / banks.

A sync always goes through the normal path: rows → `books.create_transactions` (or inventory) → AI auditor.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import workers
from app.core.catalog import INTEGRATION_KINDS, INTEGRATION_LABELS, label
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.models import Company, Integration, InventoryItem, RawPost, Source, Store
from app.intelligence.books import books

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"
NOTE_MOCK = ("Mock adapter: imports a sample file from data/samples/. Real API access requires a partner "
             "agreement.")


def ensure_rows(db: Session, company: Company) -> list[Integration]:
    """Make sure the company has one integration row per kind."""
    have = {i.kind: i for i in db.scalars(select(Integration).where(Integration.company_id == company.id))}
    for kind in INTEGRATION_KINDS:
        if kind not in have:
            row = Integration(company_id=company.id, kind=kind, status="not_connected",
                              details={"mode": "live" if kind == "telegram" else "mock"})
            db.add(row)
            have[kind] = row
    return [have[k] for k in INTEGRATION_KINDS]


class Adapter(Protocol):
    """Fetch new records. Returns ("transactions" | "inventory", rows, external ids)."""

    kind: str
    mode: str

    def fetch(self, company: Company, already: set[str]) -> tuple[str, list[dict[str, Any]], list[str]]: ...


def _today_csv(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8-sig").replace("{today}", date.today().isoformat())


class MockEInvoice:
    """Didox / Soliq e-invoice JSON → purchase transactions (one per line item)."""

    mode = "mock"

    def __init__(self, kind: str, filename: str):
        self.kind, self.filename = kind, filename

    def fetch(self, company: Company, already: set[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
        data = json.loads((SAMPLES / self.filename).read_text(encoding="utf-8"))
        rows, ids = [], []
        for inv in data["invoices"]:
            if inv["invoice_no"] in already:
                continue
            ids.append(inv["invoice_no"])
            d = date.fromisoformat(inv["date"]) if inv.get("date") else date.today()
            for it in inv["items"]:
                goods = it.get("category") in ("phone", "laptop", "car")
                rows.append({"date": d, "type": "expense",
                             "category": "stock_purchase" if goods else it.get("expense_category", "other"),
                             "item_category": it.get("category") if goods else None, "brand": it.get("brand"),
                             "model": it.get("model"), "condition": it.get("condition"), "attrs": it.get("attrs") or {},
                             "qty": it["qty"], "unit_price": it.get("unit_price"), "total": it["total"],
                             "counterparty": inv["seller"]["name"],
                             "note": f"{self.kind}:{inv['invoice_no']} {it['name']}"})
        return "transactions", rows, ids


class MockCsvBooks:
    """1C export / bank statement CSV → the normal upload parser."""

    mode = "mock"

    def __init__(self, kind: str, filename: str):
        self.kind, self.filename = kind, filename

    def fetch(self, company: Company, already: set[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
        text = _today_csv(self.filename)
        key = f"{self.filename}:{date.today().isoformat()}"
        if key in already:
            return "transactions", [], []
        rows, _errors = books.parse_upload(text.encode("utf-8"), self.filename)
        return "transactions", rows, [key]


class MockBillzStock:
    """BILLZ stock CSV → inventory units."""

    mode = "mock"
    kind = "billz"

    def fetch(self, company: Company, already: set[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
        key = f"billz_stock:{date.today().isoformat()}"
        if key in already:
            return "inventory", [], []
        rows = []
        for r in csv.DictReader(io.StringIO(_today_csv("billz_stock.csv"))):
            attrs = {k: int(r[k]) for k in ("storage_gb", "ram_gb", "ssd_gb") if r.get(k)}
            rows.append({"category": r["category"], "brand": r["brand"], "model": r["model"],
                         "condition": r["condition"], "attrs": attrs, "qty": int(r["qty"]),
                         "unit_cost": float(r["unit_cost"]), "list_price_uzs": float(r["list_price"]) or None,
                         "identifier": r.get("imei") or None})
        return "inventory", rows, [key]


ADAPTERS: dict[str, Adapter] = {
    "didox": MockEInvoice("didox", "didox_invoice.json"),
    "soliq": MockEInvoice("soliq", "soliq_invoices.json"),
    "onec": MockCsvBooks("onec", "onec_transactions.csv"),
    "bank": MockCsvBooks("bank", "bank_statement.csv"),
    "billz": MockBillzStock(),
}


def telegram_card(db: Session) -> dict[str, Any]:
    status, detail = workers.STATUS.get("telegram", ("disabled", None))
    mapped = {"ok": "connected", "starting": "connected", "error": "error"}.get(status, "not_connected")
    return {"status": mapped, "mode": "live", "last_sync_at": db.scalar(select(func.max(RawPost.created_at))),
            "details": {"worker": status, "worker_detail": detail,
                        "active_sources": db.scalar(select(func.count(Source.id)).where(Source.active.is_(True))) or 0,
                        "last_post_at": (lp.isoformat() + "Z") if (lp := db.scalar(select(func.max(RawPost.posted_at))))
                        else None},
            "note": "Live: read-only Telethon listener over the channels in sources.yaml."}


def cards(db: Session, company: Company, lang: str) -> list[dict[str, Any]]:
    rows = ensure_rows(db, company)
    db.commit()
    out = []
    for r in rows:
        if r.kind == "telegram":
            card = telegram_card(db)
        else:
            card = {"status": r.status, "mode": "mock", "last_sync_at": r.last_sync_at,
                    "details": {k: v for k, v in (r.details or {}).items() if k != "imported"}, "note": NOTE_MOCK}
        out.append({"kind": r.kind, "label": label(INTEGRATION_LABELS, r.kind, lang), **card})
    return out


def sync(db: Session, company: Company, kind: str, lang: str) -> dict[str, Any]:
    """Run a mock import through the normal upload path, then audit the imported rows."""
    if kind == "telegram":
        raise AppError("not_syncable", "Telegram syncs continuously via the listener", 400)
    adapter = ADAPTERS.get(kind)
    if adapter is None:
        raise AppError("unknown_integration", f"Unknown integration '{kind}'", 404)
    row = next(r for r in ensure_rows(db, company) if r.kind == kind)
    already = set((row.details or {}).get("imported", []))
    target, rows, ids = adapter.fetch(company, already)
    created_ids: list[int] = []
    if target == "transactions" and rows:
        created_ids = [t.id for t in books.create_transactions(db, company, rows, origin="upload")]
    elif target == "inventory" and rows:
        store_id = db.scalar(select(Store.id).where(Store.company_id == company.id).order_by(Store.id).limit(1))
        for r in rows:
            it = InventoryItem(company_id=company.id, district=company.district, acquired_at=date.today(),
                               store_id=store_id, **r)
            db.add(it)
            db.flush()
            created_ids.append(it.id)
    row.status, row.last_sync_at = "connected", utcnow()
    row.details = {**(row.details or {}), "mode": adapter.mode, "imported": sorted(already | set(ids)),
                   "last_result": {"created": len(created_ids), "external_ids": ids}}
    db.commit()
    flags = []
    if target == "transactions" and created_ids:
        books._audit_cache.pop(company.id, None)
        flags = [f for f in books.audit_flags(db, company.id, lang) if set(f["transaction_ids"]) & set(created_ids)]
    return {"kind": kind, "mode": adapter.mode, "created": len(created_ids), "errors": [], "audit_flags": flags,
            "transaction_ids": created_ids if target == "transactions" else []}
