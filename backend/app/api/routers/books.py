"""Books: import, transactions, AI auditor (#26), benchmark, budget control (#25), inventory."""

from __future__ import annotations

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select

from app.api.schemas.books import (
    AuditFixOut,
    AuditFlagOut,
    AuditOut,
    BenchmarkOut,
    BooksSummaryOut,
    BudgetIn,
    BudgetOut,
    InventoryIn,
    InventoryOut,
    InvoiceResult,
    RevaluationOut,
    SlowStockOut,
    TransactionIn,
    TransactionOut,
    TxType,
    UploadPreview,
    UploadResult,
)
from app.api.schemas.common import OkResponse, Page
from app.core import activity
from app.core.catalog import TXN_CATEGORY_LABELS, label
from app.core.deps import CompanyDep, DbDep, LangDep
from app.core.errors import AppError, not_found
from app.core.i18n import t
from app.core.models import InventoryItem, Transaction
from app.intelligence.books import books
from app.intelligence.market import stock

router = APIRouter(prefix="/books", tags=["books (#25, #26)"])


async def _read_limited(file: UploadFile) -> bytes:
    data = await file.read(books.MAX_UPLOAD_BYTES + 1)
    if len(data) > books.MAX_UPLOAD_BYTES:
        raise AppError("file_too_large", "Maximum upload size is 10 MB", 413)
    return data


@router.post("/upload", response_model=UploadResult)
async def books_upload(db: DbDep, company: CompanyDep, file: UploadFile = File(...),
                       mapping: str | None = Form(None, description='Optional JSON {"source column": "field"}'),
                       store_id: int | None = Form(None)) -> UploadResult:
    """Import a CSV/XLSX book export (column names in uz/ru/en, or an explicit mapping from the preview)."""
    content = await _read_limited(file)
    rows, errors = books.parse_upload(content, file.filename or "upload.csv", _mapping(mapping))
    if store_id is not None:
        for r in rows:
            r["store_id"] = store_id
    books.create_transactions(db, company, rows, origin="upload")
    activity.log(db, company, "books.upload", "transaction", None,
                 f"Imported {len(rows)} rows from {file.filename} ({len(errors)} errors)")
    return UploadResult(created=len(rows), errors=errors)


def _mapping(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        m = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError("invalid_mapping", "mapping must be a JSON object", 422) from exc
    if not isinstance(m, dict):
        raise AppError("invalid_mapping", "mapping must be a JSON object", 422)
    return m


@router.post("/upload/preview", response_model=UploadPreview)
async def books_upload_preview(_: CompanyDep, file: UploadFile = File(...),
                               mapping: str | None = Form(None)) -> UploadPreview:
    """Detected columns, proposed mapping with confidence, first 10 parsed rows and per-row errors."""
    content = await _read_limited(file)
    frame = books._read_frame(content, file.filename or "upload.csv")
    detected = books.detect_mapping(list(frame.columns))
    override = _mapping(mapping)
    used = override if override is not None else {c: m["field"] for c, m in detected.items()}
    try:
        rows, errors = books.parse_upload(content, file.filename or "upload.csv", used, limit=10)
    except AppError as exc:
        if exc.code != "missing_columns":
            raise
        rows, errors = [], [{"row": 0, "error": f"{exc.message}: map {', '.join(exc.details['missing'])}"}]
    return UploadPreview(columns=[str(c) for c in frame.columns], mapping=detected, fields=books.UPLOAD_FIELDS,
                         total_rows=len(frame), rows=[TransactionIn(**r) for r in rows], errors=errors)


@router.get("/upload/template", response_class=PlainTextResponse,
            responses={200: {"content": {"text/csv": {}}}})
def books_upload_template() -> PlainTextResponse:
    """Example CSV for the import."""
    return PlainTextResponse(books.TEMPLATE_CSV, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="raft_template.csv"'})


@router.post("/invoice", response_model=InvoiceResult)
async def books_invoice(db: DbDep, company: CompanyDep, file: UploadFile = File(...),
                        commit: bool = Query(False, description="Save the extracted rows immediately")
                        ) -> InvoiceResult:
    """Invoice photo → vision OCR → transactions. Without `commit` it only previews."""
    content = await _read_limited(file)
    rows = books.extract_invoice(content, file.content_type or "image/jpeg")
    ids: list[int] = []
    if commit and rows:
        ids = [tx.id for tx in books.create_transactions(db, company, rows, origin="invoice_ocr")]
        activity.log(db, company, "books.invoice", "transaction", None, f"Invoice OCR added {len(ids)} rows")
    return InvoiceResult(committed=bool(commit and rows), extracted=[TransactionIn(**r) for r in rows],
                         created_ids=ids)


def _tx_out(tx: Transaction, lang: str) -> TransactionOut:
    out = TransactionOut.model_validate(tx)
    out.category_label = label(TXN_CATEGORY_LABELS, tx.category, lang)
    return out


@router.get("/transactions", response_model=Page[TransactionOut])
def books_list_transactions(db: DbDep, company: CompanyDep, lang: LangDep,
                            month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                            category: str | None = None, type: TxType | None = None, cursor: str | None = None,
                            limit: int = Query(50, ge=1, le=500),
                            store_id: int | None = None) -> Page[TransactionOut]:
    q = select(Transaction).where(Transaction.company_id == company.id)
    if store_id is not None:
        q = q.where(Transaction.store_id == store_id)
    if month:
        y, m = (int(x) for x in month.split("-"))
        start = date(y, m, 1)
        end = date(y + (m == 12), m % 12 + 1, 1)
        q = q.where(Transaction.date >= start, Transaction.date < end)
    if category:
        q = q.where(Transaction.category == category)
    if type:
        q = q.where(Transaction.type == type)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(Transaction.id < int(cursor))
    rows = list(db.scalars(q.order_by(Transaction.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[_tx_out(r, lang) for r in rows[:limit]], next_cursor=nxt, total=total)


@router.get("/transactions/export", response_class=Response,
            responses={200: {"content": {"text/csv": {}, "application/vnd.openxmlformats-officedocument."
                                                                     "spreadsheetml.sheet": {}}}})
def books_export_transactions(db: DbDep, company: CompanyDep, format: Literal["xlsx", "csv", "1c"] = "xlsx",
                              month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                              store_id: int | None = None) -> Response:
    """Export transactions to Excel, CSV or a 1C import CSV."""
    q = select(Transaction).where(Transaction.company_id == company.id)
    if month:
        y, m = (int(x) for x in month.split("-"))
        q = q.where(Transaction.date >= date(y, m, 1), Transaction.date < date(y + (m == 12), m % 12 + 1, 1))
    if store_id is not None:
        q = q.where(Transaction.store_id == store_id)
    rows = [TransactionOut.model_validate(t).model_dump() for t in db.scalars(q.order_by(Transaction.date))]
    data, media, ext = stock.export_rows(rows, format, stock.TX_COLUMNS, stock.TX_1C, "Transactions")
    name = f"transactions_{month or 'all'}.{ext}"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def books_create_transaction(body: TransactionIn, db: DbDep, company: CompanyDep) -> TransactionOut:
    data = body.model_dump()
    if data["unit_price"] is None:
        data["unit_price"] = data["total"] / data["qty"]
    if body.model and not data["attrs"]:
        data["attrs"] = books._attrs_from_model(body.model)
    tx = books.create_transactions(db, company, [data], origin="manual")[0]
    activity.log(db, company, "transaction.create", "transaction", tx.id,
                 f"{tx.type} {tx.category} {round(tx.total):,} so'm")
    return TransactionOut.model_validate(tx)


@router.delete("/transactions/{tx_id}", response_model=OkResponse)
def books_delete_transaction(tx_id: int, db: DbDep, company: CompanyDep) -> OkResponse:
    """Delete a manual/imported entry. Entries booked by exchange deals are locked."""
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.company_id != company.id:
        raise not_found("transaction", tx_id)
    if tx.origin == "exchange" or tx.deal_id:
        raise AppError("exchange_entry_locked", "Entries created by exchange deals cannot be deleted", 409)
    db.delete(tx)
    activity.log(db, company, "transaction.delete", "transaction", tx_id,
                 f"Deleted {tx.category} {round(tx.total):,} so'm")
    books._audit_cache.pop(company.id, None)
    return OkResponse()


@router.get("/audit", response_model=AuditOut)
def books_audit(db: DbDep, company: CompanyDep, lang: LangDep) -> AuditOut:
    """AI Auditor: duplicates, typos, wrong totals, cost spikes, overpayments.

    Flags marked as checked are hidden; each flag carries its transactions, the numbers behind the message,
    the available automatic fix and the counterparty's recent history."""
    flags = books.open_flags(db, company.id, lang)
    txs, history = books.flag_context(db, company.id, flags)
    out = []
    for f in flags:
        first = txs.get(f["transaction_ids"][0])
        cp = first.counterparty if first is not None else None
        out.append(AuditFlagOut(**f, title=t(f"audit.title.{f['type']}", lang), fix=books.fix_kind(f, txs),
                                counterparty=cp,
                                transactions=[_tx_out(txs[i], lang) for i in f["transaction_ids"][:10] if i in txs],
                                supplier_history=history.get(cp, []) if cp else []))
    total = db.scalar(select(func.count(Transaction.id)).where(Transaction.company_id == company.id)) or 0
    flagged = {i for f in flags for i in f["transaction_ids"]}
    recs, source = books.recommendations(flags, lang, company)
    return AuditOut(summary=books.audit_summary(flags), flags=out, recommendations=recs,
                    recommendations_source=source, total_records=total, ok_records=max(total - len(flagged), 0),
                    checked=len(books.ignored_flag_ids(db, company.id)))


@router.post("/audit/{flag_id}/fix", response_model=AuditFixOut)
def books_audit_fix(flag_id: str, db: DbDep, company: CompanyDep, lang: LangDep) -> AuditFixOut:
    """Apply the flag's automatic fix (delete extra duplicates / set the computed total). 409 if it has none."""
    f = books.find_open_flag(db, company.id, flag_id, lang)
    res = books.fix_flag(db, company, f)
    activity.log(db, company, "books.audit_fix", f"audit:{f['type']}", min(f["transaction_ids"]),
                 f"Fixed: {f['message']}")
    return AuditFixOut(**res)


@router.post("/audit/{flag_id}/ignore", response_model=OkResponse)
def books_audit_ignore(flag_id: str, db: DbDep, company: CompanyDep, lang: LangDep) -> OkResponse:
    """Mark a flag as checked: it is hidden from the auditor list (recorded in the activity log)."""
    f = books.find_open_flag(db, company.id, flag_id, lang)
    activity.log(db, company, books.AUDIT_IGNORE_ACTION, f"audit:{f['type']}", min(f["transaction_ids"]),
                 f"Marked as checked: {f['message']}")
    return OkResponse()


@router.get("/summary", response_model=BooksSummaryOut)
def books_summary(db: DbDep, company: CompanyDep,
                  month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")) -> BooksSummaryOut:
    """Month totals: income, expenses, net and the estimated tax (current regime; rates unverified)."""
    return BooksSummaryOut(**books.month_summary(db, company, month or date.today().strftime("%Y-%m")))


@router.get("/benchmark", response_model=BenchmarkOut)
def books_benchmark(db: DbDep, company: CompanyDep) -> BenchmarkOut:
    """Anonymized peer comparison of monthly operating costs (needs ≥ 3 peers)."""
    return BenchmarkOut(**books.benchmark(db, company))


@router.put("/budget", response_model=BudgetOut)
def books_set_budget(body: BudgetIn, db: DbDep, company: CompanyDep, lang: LangDep) -> BudgetOut:
    books.set_budget(db, company, body.month, body.items)
    activity.log(db, company, "budget.update", "budget", None,
                 f"Budget {body.month}: " + ", ".join(f"{k}={round(v):,}" for k, v in body.items.items()))
    return _budget_out(db, company, body.month, lang)


@router.get("/budget", response_model=BudgetOut)
def books_budget(db: DbDep, company: CompanyDep, lang: LangDep,
                 month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")) -> BudgetOut:
    """Budget control: plan vs fact, month-end forecast, status and explanations."""
    return _budget_out(db, company, month or date.today().strftime("%Y-%m"), lang)


def _budget_out(db: DbDep, company: CompanyDep, month: str, lang: str) -> BudgetOut:
    st = books.budget_status(db, company, month, lang)
    for it in st["items"]:
        it["label"] = label(TXN_CATEGORY_LABELS, it["category"], lang)
    return BudgetOut(**st, cumulative_uzs=books.budget_daily(db, company, month, st["days_elapsed"]))


@router.get("/inventory", response_model=Page[InventoryOut])
def books_inventory(db: DbDep, company: CompanyDep, status: str | None = "in_stock",
                    store_id: int | None = None) -> Page[InventoryOut]:
    q = select(InventoryItem).where(InventoryItem.company_id == company.id)
    if store_id is not None:
        q = q.where(InventoryItem.store_id == store_id)
    if status:
        q = q.where(InventoryItem.status == status)
    rows = list(db.scalars(q.order_by(InventoryItem.id.desc())))
    return Page(items=[InventoryOut.model_validate(r) for r in rows], next_cursor=None, total=len(rows))


@router.post("/inventory", response_model=InventoryOut, status_code=201)
def books_add_inventory(body: InventoryIn, db: DbDep, company: CompanyDep) -> InventoryOut:
    data = body.model_dump()
    data["acquired_at"] = data["acquired_at"] or date.today()
    data["district"] = data["district"] or company.district
    if data["identifier"] and db.scalar(select(InventoryItem.id).where(
            InventoryItem.company_id == company.id, InventoryItem.identifier == data["identifier"])):
        raise AppError("identifier_exists", "A unit with this IMEI/VIN already exists", 409)
    it = InventoryItem(company_id=company.id, **data)
    db.add(it)
    db.flush()
    activity.log(db, company, "inventory.create", "inventory", it.id, f"{it.model} × {it.qty} added")
    return InventoryOut.model_validate(it)


@router.get("/slow-stock", response_model=SlowStockOut)
def books_slow_stock(db: DbDep, company: CompanyDep, lang: LangDep) -> SlowStockOut:
    return SlowStockOut(**books.slow_stock(db, company, lang))


@router.get("/stock-revaluation", response_model=RevaluationOut)
def books_stock_revaluation(db: DbDep, company: CompanyDep, lang: LangDep) -> RevaluationOut:
    return RevaluationOut(**books.revaluation(db, company, lang))
