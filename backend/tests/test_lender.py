"""v2 phase 5: lender console — valuations, collateral LTV monitoring, loan applications, market report."""

import io

from openpyxl import load_workbook

BANK = {"X-API-Key": "demo-demo-bank"}
BOZOR = {"X-API-Key": "demo-bozor-admin"}
MANAGER = {"X-API-Key": "demo-chilonzor-manager"}


def test_valuation_liquidation_below_fair(client):
    r = client.post("/api/v1/lender/valuations", headers=BANK, json={
        "category": "car", "model": "Cobalt", "condition": "used", "attrs": {"year": 2021, "mileage_km": 50000}})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["liquidation_value_uzs"] < v["range_uzs"][0] <= v["fair_price_uzs"]
    assert v["liquidation_value_uzs"] == round(v["range_uzs"][0] * 0.9) and v["haircut_pct"] == 10
    assert v["samples"] and v["valuations_this_month"] >= 1
    phone = client.post("/api/v1/lender/valuations", headers=BANK, json={
        "category": "phone", "model": "iPhone 13", "condition": "A", "attrs": {"storage_gb": 128}}).json()
    assert phone["haircut_pct"] == 20 and phone["valuations_this_month"] == v["valuations_this_month"] + 1


def test_valuation_by_applicant_inventory_and_url(client, chilonzor):
    app = client.get("/api/v1/lender/applications", headers=BANK).json()["items"][0]
    detail = client.get(f"/api/v1/lender/applications/{app['id']}", headers=BANK).json()
    inv_id = detail["snapshot"]["collateral"][0]["inventory_id"]
    v = client.post("/api/v1/lender/valuations", headers=BANK, json={"inventory_id": inv_id}).json()
    assert v["source"]["inventory_id"] == inv_id and v["fair_price_uzs"] > 0
    techopt_unit = client.get("/api/v1/books/inventory", headers={"X-API-Key": "demo-techopt"}).json()["items"][0]
    assert client.post("/api/v1/lender/valuations", headers=BANK,
                       json={"inventory_id": techopt_unit["id"]}).status_code == 403
    missing = client.post("/api/v1/lender/valuations", headers=BANK, json={"url": "https://t.me/nochannel/123"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "post_not_found"


def test_collateral_breach_and_watch(client):
    rows = client.get("/api/v1/lender/collateral", headers=BANK).json()["items"]
    assert len(rows) == 10
    by_status = {}
    for r in rows:
        by_status.setdefault(r["status"], []).append(r)
    assert len(by_status["breach"]) == 1 and by_status["breach"][0]["model"] == "Malibu 2"
    assert len(by_status["watch"]) == 1 and by_status["watch"][0]["model"] == "Tracker 2"
    b = by_status["breach"][0]
    assert b["ltv"] > b["ltv_limit"] and b["liquidation_value_uzs"] < b["market_value_uzs"]
    alerts = client.get("/api/v1/alerts", headers=BANK).json()["items"]
    breach_alerts = [a for a in alerts if a["payload"].get("collateral_id") == b["id"]]
    assert len(breach_alerts) == 1
    client.get("/api/v1/lender/collateral", headers=BANK)
    again = [a for a in client.get("/api/v1/alerts", headers=BANK).json()["items"]
             if a["payload"].get("collateral_id") == b["id"]]
    assert len(again) == 1, "one breach alert per item per day"
    s = client.get("/api/v1/lender/collateral/summary", headers=BANK).json()
    assert s["by_status"]["breach"] == 1 and s["by_status"]["watch"] == 1 and 0 < s["portfolio_ltv"] < 1
    assert s["total_liquidation_value_uzs"] < s["total_market_value_uzs"]


def test_add_collateral(client):
    r = client.post("/api/v1/lender/collateral", headers=BANK, json={
        "borrower_name": "Test IP", "category": "house", "district": "Sergeli", "attrs": {"rooms": 2, "area_m2": 50},
        "loan_balance_uzs": 10_000_000_000})
    assert r.status_code == 201 and r.json()["status"] == "breach"


def test_loan_application_flow(client, sergeli):
    lenders = client.get("/api/v1/advisor/lenders", headers=sergeli).json()
    bank_id = next(x["id"] for x in lenders if x["name"] == "Demo Lizing Bank")
    body = {"lender_id": bank_id, "product": "auto_loan", "principal_uzs": 200_000_000, "months": 36,
            "purpose": "Avto zaxirasini kengaytirish"}
    no = client.post("/api/v1/advisor/loan-applications", headers=sergeli, json={**body, "consent": False})
    assert no.status_code == 422 and no.json()["error"]["code"] == "consent_required"
    r = client.post("/api/v1/advisor/loan-applications", headers=sergeli, json={**body, "consent": True})
    assert r.status_code == 201, r.text
    app = r.json()
    snap = app["snapshot"]
    assert 0 <= snap["loan_readiness"]["score"] <= 100 and app["readiness_score"] == snap["loan_readiness"]["score"]
    assert len(snap["cashflow"]) == 6 and "issues" in snap["audit_summary"] and snap["credit"]["monthly_payment_uzs"]
    mine = client.get("/api/v1/advisor/loan-applications", headers=sergeli).json()
    assert any(a["id"] == app["id"] for a in mine["items"])
    bank_alerts = client.get("/api/v1/alerts", headers=BANK).json()["items"]
    assert any(a["payload"].get("loan_application_id") == app["id"] for a in bank_alerts)
    seen = client.get(f"/api/v1/lender/applications/{app['id']}", headers=BANK).json()
    assert seen["snapshot"]["loan_readiness"]["score"] == snap["loan_readiness"]["score"]
    plan = client.get(seen["business_plan_url"], headers=BANK)
    assert plan.status_code == 200 and "Sergeli Avto" in plan.text
    d = client.post(f"/api/v1/lender/applications/{app['id']}/decision", headers=BANK,
                    json={"status": "approved", "note": "Garov: avtomobillar"})
    assert d.json()["status"] == "approved"
    again = client.post(f"/api/v1/lender/applications/{app['id']}/decision", headers=BANK, json={"status": "rejected"})
    assert again.status_code == 409
    notes = client.get("/api/v1/alerts", headers=sergeli).json()["items"]
    assert any(a["payload"].get("status") == "approved" for a in notes)


def test_lender_permissions(client, chilonzor):
    assert client.get("/api/v1/lender/collateral", headers=chilonzor).status_code == 403
    assert client.get("/api/v1/lender/collateral", headers=BOZOR).status_code == 403
    assert client.get("/api/v1/advisor/loan-applications", headers=MANAGER).status_code == 403
    assert client.get("/api/v1/partner/market-report?category=phone", headers=chilonzor).status_code == 403


def test_market_report(client):
    r = client.get("/api/v1/partner/market-report?category=phone&days=30", headers=BOZOR).json()
    assert r["total_listings"] > 0 and r["by_model_district"] and r["weekly_trend"]
    assert set(r["by_seller_type"]) <= {"shop", "private"}
    d = client.get("/api/v1/partner/market-report?category=house&district=yunusobod", headers=BANK).json()
    assert all(row["district"] == "Yunusobod" for row in d["by_model_district"])
    x = client.get("/api/v1/partner/market-report?category=car&format=xlsx", headers=BANK)
    assert x.status_code == 200
    assert load_workbook(io.BytesIO(x.content)).sheetnames == ["Models", "Weekly trend", "Seller types"]
