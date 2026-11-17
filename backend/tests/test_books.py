"""Phase 3: upload, auditor (every planted problem), budget, benchmark, inventory."""

import calendar
from datetime import date

PLANTED = {"duplicate", "qty_mismatch", "extra_zero", "price_spread", "cost_spike", "overpayment",
           "no_counterparty"}


def test_audit_finds_every_planted_problem(client, chilonzor):
    r = client.get("/api/v1/books/audit", headers={**chilonzor, "Accept-Language": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    types = {f["type"] for f in body["flags"]}
    assert types >= PLANTED, f"missing: {PLANTED - types}"
    flags = body["flags"]
    dup = next(f for f in flags if f["type"] == "duplicate")
    assert "Electricity" in dup["message"] and len(dup["transaction_ids"]) == 2
    ez = next(f for f in flags if f["type"] == "extra_zero")
    assert "Internet" in ez["message"] and ez["amount_at_risk_uzs"] == 3_150_000
    spike = next(f for f in flags if f["type"] == "cost_spike")
    assert "Electricity" in spike["message"] and date.today().strftime("%Y-%m") in spike["message"]
    assert not any(f["type"] == "cost_spike" and "Internet" in f["message"] for f in flags)
    over = [f for f in flags if f["type"] == "overpayment"]
    assert any("iPhone 13" in f["message"] for f in over)
    spread = next(f for f in flags if f["type"] == "price_spread")
    assert "Redmi Note 13" in spread["message"]
    assert all(f["transaction_ids"] for f in flags)
    assert body["summary"]["amount_at_risk_uzs"] > 0
    assert 3 <= len(body["recommendations"]) <= 5 and body["recommendations_source"] == "rules"


def test_audit_clean_company(client, techopt):
    r = client.get("/api/v1/books/audit", headers=techopt).json()
    assert not any(f["type"] in ("duplicate", "extra_zero", "overpayment") for f in r["flags"])


def test_budget_statuses_match_plants(client, chilonzor):
    r = client.get("/api/v1/books/budget", headers={**chilonzor, "Accept-Language": "en"})
    assert r.status_code == 200
    items = {i["category"]: i for i in r.json()["items"]}
    assert items["ads"]["status"] == "over"
    assert items["stock_purchase"]["status"] == "at_risk"
    last_day = calendar.monthrange(date.today().year, date.today().month)[1]
    if date.today().day < last_day:
        assert items["stock_purchase"]["fact_uzs"] < items["stock_purchase"]["planned_uzs"]
        assert items["stock_purchase"]["forecast_uzs"] > items["stock_purchase"]["planned_uzs"]
    assert items["electricity"]["status"] == "over"
    assert items["rent"]["status"] == "ok"
    assert items["ads"]["explanation"] and items["ads"]["top_transactions"]
    alerts = client.get("/api/v1/alerts", headers=chilonzor)
    if alerts.status_code == 200:
        budget_alerts = [a for a in alerts.json()["items"] if a["type"] == "budget"]
        before = len(budget_alerts)
        client.get("/api/v1/books/budget", headers=chilonzor)
        after = [a for a in client.get("/api/v1/alerts", headers=chilonzor).json()["items"] if a["type"] == "budget"]
        assert before == len(after), "at most one budget alert per category per day"


def test_budget_put(client, sergeli):
    month = date.today().strftime("%Y-%m")
    r = client.put("/api/v1/books/budget", headers=sergeli, json={"month": month, "items": {"ads": 100_000}})
    assert r.status_code == 200
    ads = next(i for i in r.json()["items"] if i["category"] == "ads")
    assert ads["planned_uzs"] == 100_000
    bad = client.put("/api/v1/books/budget", headers=sergeli, json={"month": month, "items": {"yacht": 1}})
    assert bad.status_code == 422


def test_benchmark(client, chilonzor):
    b = client.get("/api/v1/books/benchmark", headers=chilonzor).json()
    assert b["enough_peers"] and b["peers"] >= 6
    assert 0 <= b["percentile"] <= 100 and b["categories"]


def test_slow_stock_and_revaluation(client, chilonzor):
    s = client.get("/api/v1/books/slow-stock", headers=chilonzor).json()
    assert s["units"] == 8 and all(i["age_days"] > 75 for i in s["items"])
    assert s["cash_tied_uzs"] > 0 and all(i["suggested_surplus_price_uzs"] for i in s["items"])
    rv = client.get("/api/v1/books/stock-revaluation", headers=chilonzor).json()
    assert rv["market_value_uzs"] > 0 and rv["items"]
    i13 = next(i for i in rv["items"] if i["model"] == "iPhone 13")
    assert i13["unrealized_margin_uzs"] < i13["market_value_uzs"]


def test_upload_flexible_columns(client, sergeli):
    csv = ("Sana;Kategoriya;Summa;Kontragent;Izoh\n"
           "05.11.2026;svet;1 250 000;Elektr tarmoqlari;\n"
           "06.11.2026;ijara;6 000 000;Ijara egasi;\n"
           "07.11.2026;nomalum;100;X;\n"
           "bad;reklama;500 000;;\n")
    r = client.post("/api/v1/books/upload", headers=sergeli,
                    files={"file": ("books.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2 and {e["row"] for e in body["errors"]} == {4, 5}
    tx = client.get("/api/v1/books/transactions?category=electricity&month=2026-11", headers=sergeli).json()
    assert any(t["total"] == 1_250_000 for t in tx["items"])
    tpl = client.get("/api/v1/books/upload/template")
    assert tpl.status_code == 200 and tpl.text.startswith("date,type,category")


def test_upload_too_large(client, sergeli):
    big = b"a" * (10 * 1024 * 1024 + 10)
    r = client.post("/api/v1/books/upload", headers=sergeli, files={"file": ("big.csv", big, "text/csv")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_transactions_crud(client, sergeli):
    r = client.post("/api/v1/books/transactions", headers=sergeli, json={
        "date": date.today().isoformat(), "type": "expense", "category": "documents", "total": 150000})
    assert r.status_code == 201
    tid = r.json()["id"]
    page = client.get("/api/v1/books/transactions?limit=2", headers=sergeli).json()
    assert len(page["items"]) == 2 and page["next_cursor"] and page["total"] > 2
    assert client.delete(f"/api/v1/books/transactions/{tid}", headers=sergeli).status_code == 200
    assert client.delete(f"/api/v1/books/transactions/{tid}", headers=sergeli).status_code == 404


def test_invoice_without_llm(client, sergeli):
    r = client.post("/api/v1/books/invoice", headers=sergeli, files={"file": ("inv.jpg", b"\xff\xd8", "image/jpeg")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"
