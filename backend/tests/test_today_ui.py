"""Home screen ("Bugun") dashboard additions, command-palette search, store unit counts."""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.core import db as dbm
from app.core.models import Company, InventoryItem, Transaction


def _company_id(slug: str) -> int:
    with dbm.SessionLocal() as s:
        return s.scalar(select(Company.id).where(Company.slug == slug))


def test_dashboard_today_fields(client, chilonzor):
    d = client.get("/api/v1/dashboard", headers=chilonzor).json()
    today = date.fromisoformat(d["today"])
    assert d["fx_usd_uzs"] > 0 and d["insight"]

    sales = d["sales"]
    assert len(sales["days"]) == 90 and sales["days"][-1]["date"] == d["today"]
    cid = _company_id("chilonzor-phone")
    with dbm.SessionLocal() as s:
        def day_total(day: date) -> float:
            return float(s.scalar(select(func.coalesce(func.sum(Transaction.total), 0)).where(
                Transaction.company_id == cid, Transaction.type == "income", Transaction.category == "sale",
                Transaction.date == day)))
        assert sales["today_uzs"] == round(day_total(today))
        assert sales["yesterday_uzs"] == round(day_total(today - timedelta(days=1)))
        prev30 = sum(day_total(today - timedelta(days=i)) for i in range(1, 31))
    assert sales["avg_daily_uzs"] == round(prev30 / 30)
    assert sales["delta_uzs"] == sales["today_uzs"] - sales["yesterday_uzs"]

    b = d["budget"]
    assert b["planned_total_uzs"] > 0 and b["used_pct"] == d["kpis"]["budget_used_pct"]
    assert d["credit"] == {"score": d["kpis"]["loan_readiness_score"], "grade": d["kpis"]["loan_readiness_grade"]}


def test_dashboard_price_index_and_rfq_quotes(client, chilonzor):
    d = client.get("/api/v1/dashboard", headers=chilonzor).json()
    ix = d["price_index"]
    if ix is not None:
        weeks = [p["week_start"] for p in ix["points"]]
        assert weeks == sorted(weeks) and len(weeks) >= 2
        for p in ix["points"]:
            assert p["p25_usd"] <= p["median_usd"] <= p["p75_usd"] and p["listings"] > 0
    rq = d["rfq_quotes"]
    if rq is not None:
        prices = [q["unit_price_uzs"] for q in rq["quotes"]]
        assert prices == sorted(prices) and rq["quotes"][0]["best"] and sum(q["best"] for q in rq["quotes"]) == 1


def test_search(client, chilonzor):
    r = client.get("/api/v1/search?q=iphone", headers=chilonzor)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(h["kind"] == "stock" for h in items)
    assert all("iphone" in (h["title"] + h["subtitle"]).lower() or h["kind"] != "stock" for h in items)
    cp = client.get("/api/v1/search?q=elektr", headers=chilonzor).json()["items"]
    assert any(h["kind"] == "counterparty" for h in cp) and any(h["kind"] == "transaction" for h in cp)
    assert client.get("/api/v1/search?q=a", headers=chilonzor).status_code == 422
    assert client.get("/api/v1/search?q=zzzzqqq", headers=chilonzor).json()["items"] == []


def test_search_is_company_scoped(client, chilonzor, techopt):
    mine = {h["id"] for h in client.get("/api/v1/search?q=iphone&limit=20", headers=chilonzor).json()["items"]
            if h["kind"] == "stock"}
    theirs = {h["id"] for h in client.get("/api/v1/search?q=iphone&limit=20", headers=techopt).json()["items"]
              if h["kind"] == "stock"}
    assert not (mine & theirs)


def test_store_units(client, chilonzor):
    stores = client.get("/api/v1/stores", headers=chilonzor).json()["items"]
    cid = _company_id("chilonzor-phone")
    with dbm.SessionLocal() as s:
        for st in stores:
            expected = s.scalar(select(func.coalesce(func.sum(InventoryItem.qty), 0)).where(
                InventoryItem.company_id == cid, InventoryItem.store_id == st["id"],
                InventoryItem.status == "in_stock"))
            assert st["units_in_stock"] == expected
