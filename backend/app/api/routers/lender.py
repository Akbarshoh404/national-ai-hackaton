"""Lender & bazaar console (partners) and borrower loan applications."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select

from app.api.schemas.common import Category, Page
from app.api.schemas.lender import (
    ApplicationDecisionIn,
    CollateralIn,
    CollateralOut,
    CollateralSummary,
    LenderRef,
    LoanApplicationDetail,
    LoanApplicationIn,
    LoanApplicationOut,
    MarketReportOut,
    ValuationIn,
    ValuationOut,
)
from app.core import activity
from app.core.catalog import normalize_district
from app.core.deps import CompanyDep, DbDep, LangDep, OwnerDep, require_company_role
from app.core.errors import not_found
from app.core.models import Collateral, Company, LoanApplication
from app.intelligence.advisor import finance, lender

LenderDep = Annotated[Company, Depends(require_company_role("lender"))]
PartnerDep = Annotated[Company, Depends(require_company_role("lender", "market_admin"))]

router = APIRouter(tags=["lender & bazaar console (#20, #19)"])


def app_out(db: DbDep, a: LoanApplication, detail: bool = False) -> LoanApplicationOut | LoanApplicationDetail:
    base = {**LoanApplicationOut.model_validate(a).model_dump(), "company_name": db.get(Company, a.company_id).name,
            "lender_name": db.get(Company, a.lender_id).name,
            "readiness_score": (a.snapshot or {}).get("loan_readiness", {}).get("score")}
    if detail:
        return LoanApplicationDetail(**base, snapshot=a.snapshot,
                                     business_plan_url=f"/api/v1/lender/applications/{a.id}/business-plan")
    return LoanApplicationOut(**base)


# --- valuations ---------------------------------------------------------------------------

@router.post("/lender/valuations", response_model=ValuationOut)
def lender_valuation(body: ValuationIn, db: DbDep, company: LenderDep, lang: LangDep) -> ValuationOut:
    """Collateral valuation: fair price, range and liquidation value = p25 × (1 − haircut)."""
    return ValuationOut(**lender.value_item(db, company, body.model_dump(), lang))


# --- collateral ---------------------------------------------------------------------------

@router.get("/lender/collateral", response_model=Page[CollateralOut])
def lender_collateral_list(db: DbDep, company: LenderDep, lang: LangDep,
                           status: Literal["ok", "watch", "breach", "no_data"] | None = None) -> Page[CollateralOut]:
    """Collateral portfolio revalued live; breaches raise an alert (once per item per day)."""
    rows = lender.revalue(db, company, lang)
    if status:
        rows = [r for r in rows if r["status"] == status]
    return Page(items=[CollateralOut(**r) for r in rows], next_cursor=None, total=len(rows))


@router.post("/lender/collateral", response_model=CollateralOut, status_code=201)
def lender_collateral_add(body: CollateralIn, db: DbDep, company: LenderDep, lang: LangDep) -> CollateralOut:
    data = body.model_dump()
    data["district"] = normalize_district(data["district"]) or data["district"]
    c = Collateral(lender_id=company.id, **data)
    db.add(c)
    db.flush()
    activity.log(db, company, "collateral.create", "collateral", c.id, f"Collateral for {c.borrower_name}")
    return CollateralOut(**next(r for r in lender.revalue(db, company, lang) if r["id"] == c.id))


@router.get("/lender/collateral/summary", response_model=CollateralSummary)
def lender_collateral_summary(db: DbDep, company: LenderDep, lang: LangDep) -> CollateralSummary:
    rows = lender.revalue(db, company, lang)
    return CollateralSummary(**lender.collateral_summary(rows, lender.valuations_count(db, company)))


# --- loan applications (lender side) ---------------------------------------------------------

@router.get("/lender/applications", response_model=Page[LoanApplicationOut])
def lender_applications(db: DbDep, company: LenderDep,
                        status: Literal["submitted", "reviewing", "approved", "rejected"] | None = None,
                        cursor: str | None = None, limit: int = Query(50, ge=1, le=200)) -> Page[LoanApplicationOut]:
    q = select(LoanApplication).where(LoanApplication.lender_id == company.id)
    if status:
        q = q.where(LoanApplication.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if cursor:
        q = q.where(LoanApplication.id < int(cursor))
    rows = list(db.scalars(q.order_by(LoanApplication.id.desc()).limit(limit + 1)))
    nxt = str(rows[limit - 1].id) if len(rows) > limit else None
    return Page(items=[app_out(db, a) for a in rows[:limit]], next_cursor=nxt, total=total)


@router.get("/lender/applications/{app_id}", response_model=LoanApplicationDetail)
def lender_application_get(app_id: int, db: DbDep, company: LenderDep) -> LoanApplicationDetail:
    """Full borrower snapshot (readiness, cash flow, audit, inventory at market, credit, collateral)."""
    a = db.get(LoanApplication, app_id)
    if a is None or a.lender_id != company.id:
        raise not_found("loan_application", app_id)
    return app_out(db, a, detail=True)


@router.get("/lender/applications/{app_id}/business-plan", response_class=HTMLResponse)
def lender_application_plan(app_id: int, db: DbDep, company: LenderDep, lang: LangDep) -> Response:
    """The borrower's business plan for this application (HTML)."""
    a = db.get(LoanApplication, app_id)
    if a is None or a.lender_id != company.id:
        raise not_found("loan_application", app_id)
    borrower = db.get(Company, a.company_id)
    plan = finance.business_plan(db, borrower, a.principal_uzs, min(a.months, 120), a.purpose, None, lang)
    return HTMLResponse(finance.render_plan_html(plan))


@router.post("/lender/applications/{app_id}/decision", response_model=LoanApplicationOut)
def lender_application_decide(app_id: int, body: ApplicationDecisionIn, db: DbDep,
                              company: LenderDep) -> LoanApplicationOut:
    return app_out(db, lender.decide(db, company, app_id, body.status, body.note))


# --- loan applications (borrower side) -------------------------------------------------------

@router.get("/advisor/lenders", response_model=list[LenderRef])
def advisor_lenders(db: DbDep, _: CompanyDep) -> list[LenderRef]:
    """Lenders a borrower can apply to."""
    return [LenderRef(id=c.id, name=c.name) for c in db.scalars(select(Company).where(Company.role == "lender"))]


@router.post("/advisor/loan-applications", response_model=LoanApplicationDetail, status_code=201)
def advisor_apply(body: LoanApplicationIn, db: DbDep, company: OwnerDep, lang: LangDep) -> LoanApplicationDetail:
    """Owner submits an application; a verified-books snapshot is frozen and the lender is alerted."""
    return app_out(db, lender.submit_application(db, company, body.model_dump(), lang), detail=True)


@router.get("/advisor/loan-applications", response_model=Page[LoanApplicationOut])
def advisor_applications(db: DbDep, company: OwnerDep) -> Page[LoanApplicationOut]:
    rows = list(db.scalars(select(LoanApplication).where(LoanApplication.company_id == company.id)
                           .order_by(LoanApplication.id.desc())))
    return Page(items=[app_out(db, a) for a in rows], next_cursor=None, total=len(rows))


# --- partner market report -----------------------------------------------------------------

@router.get("/partner/market-report", response_model=MarketReportOut,
            responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
def partner_market_report(db: DbDep, _: PartnerDep, category: Category = "phone", district: str | None = None,
                          days: int = Query(30, ge=7, le=365), format: Literal["json", "xlsx"] = "json"):
    """Median price and volume per model and district, weekly trend, listings by seller type."""
    report = lender.market_report(db, category, normalize_district(district) or district, days)
    if format == "xlsx":
        return Response(lender.report_xlsx(report),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="market_{category}.xlsx"'})
    return MarketReportOut(**report)
