"""Books: import, transactions, AI auditor (#26), benchmark, budget control (#25), inventory."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from app.deps import CompanyDep, DbDep, LangDep
from app.errors import AppError, not_found
from app.models import InventoryItem, Transaction
from app.schemas.books import (
    AuditOut,
    BenchmarkOut,
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
    UploadResult,
)
from app.schemas.common import OkResponse, Page
from app.services import books

router = APIRouter(prefix="/books", tags=["books (#25, #26)"])


async def _read_limited(file: UploadFile) -> bytes:
    data = await file.read(books.MAX_UPLOAD_BYTES + 1)
    if len(data) > books.MAX_UPLOAD_BYTES:
        raise AppError("file_too_large", "Maximum upload size is 10 MB", 413)
    return data


@router.post("/upload", response_model=UploadResult)
async def books_upload(db: DbDep, company: CompanyDep, file: UploadFile = File(...)) -> UploadResult:
    """Import a CSV/XLSX book export (column names in uz/ru/en)."""
    content = await _read_limited(file)
    rows, errors = books.parse_upload(content, file.filename or "upload.csv")
    books.create_transactions(db, company, rows, origin="upload")
    return UploadResult(created=len(rows), errors=errors)


@router.get("/upload/template", response_class=PlainTextResponse,
            responses={200: {"content": {"text/csv": {}}}})
def books_upload_template() -> PlainTextResponse:
    """Example CSV for the import."""
    return PlainTextResponse(books.TEMPLATE_CSV, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="bozorpilot_template.csv"'})


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
    return InvoiceResult(committed=bool(commit and rows), extracted=[TransactionIn(**r) for r in rows],
                         created_ids=ids)


@router.get("/transactions", response_model=Page[TransactionOut])
def books_list_transactions(db: DbDep, company: CompanyDep,
                            month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                            category: str | None = None, type: TxType | None = None, cursor: str | None = None,
                            limit: int = Query(50, ge=1, le=500)) -> Page[TransactionOut]:
    q = select(Transaction).where(Transaction.company_id == company.id)
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
    return Page(items=[TransactionOut.model_validate(r) for r in rows[:limit]], next_cursor=nxt, total=total)


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def books_create_transaction(body: TransactionIn, db: DbDep, company: CompanyDep) -> TransactionOut:
    data = body.model_dump()
    if data["unit_price"] is None:
        data["unit_price"] = data["total"] / data["qty"]
    if body.model and not data["attrs"]:
        data["attrs"] = books._attrs_from_model(body.model)
    tx = books.create_transactions(db, company, [data], origin="manual")[0]
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
    db.commit()
    books._audit_cache.pop(company.id, None)
    return OkResponse()


@router.get("/audit", response_model=AuditOut)
def books_audit(db: DbDep, company: CompanyDep, lang: LangDep) -> AuditOut:
    """AI Auditor: duplicates, typos, wrong totals, cost spikes, overpayments."""
    flags = books.audit_flags(db, company.id, lang)
    recs, source = books.recommendations(flags, lang, company)
    return AuditOut(summary=books.audit_summary(flags), flags=flags, recommendations=recs,
                    recommendations_source=source)


@router.get("/benchmark", response_model=BenchmarkOut)
def books_benchmark(db: DbDep, company: CompanyDep) -> BenchmarkOut:
    """Anonymized peer comparison of monthly operating costs (needs ≥ 3 peers)."""
    return BenchmarkOut(**books.benchmark(db, company))


@router.put("/budget", response_model=BudgetOut)
def books_set_budget(body: BudgetIn, db: DbDep, company: CompanyDep, lang: LangDep) -> BudgetOut:
    books.set_budget(db, company, body.month, body.items)
    return BudgetOut(**books.budget_status(db, company, body.month, lang))


@router.get("/budget", response_model=BudgetOut)
def books_budget(db: DbDep, company: CompanyDep, lang: LangDep,
                 month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")) -> BudgetOut:
    """Budget control: plan vs fact, month-end forecast, status and explanations."""
    return BudgetOut(**books.budget_status(db, company, month or date.today().strftime("%Y-%m"), lang))


@router.get("/inventory", response_model=Page[InventoryOut])
def books_inventory(db: DbDep, company: CompanyDep, status: str | None = "in_stock") -> Page[InventoryOut]:
    q = select(InventoryItem).where(InventoryItem.company_id == company.id)
    if status:
        q = q.where(InventoryItem.status == status)
    rows = list(db.scalars(q.order_by(InventoryItem.id.desc())))
    return Page(items=[InventoryOut.model_validate(r) for r in rows], next_cursor=None, total=len(rows))


@router.post("/inventory", response_model=InventoryOut, status_code=201)
def books_add_inventory(body: InventoryIn, db: DbDep, company: CompanyDep) -> InventoryOut:
    data = body.model_dump()
    data["acquired_at"] = data["acquired_at"] or date.today()
    data["district"] = data["district"] or company.district
    it = InventoryItem(company_id=company.id, **data)
    db.add(it)
    db.commit()
    return InventoryOut.model_validate(it)


@router.get("/slow-stock", response_model=SlowStockOut)
def books_slow_stock(db: DbDep, company: CompanyDep, lang: LangDep) -> SlowStockOut:
    return SlowStockOut(**books.slow_stock(db, company, lang))


@router.get("/stock-revaluation", response_model=RevaluationOut)
def books_stock_revaluation(db: DbDep, company: CompanyDep, lang: LangDep) -> RevaluationOut:
    return RevaluationOut(**books.revaluation(db, company, lang))
