"""Phase 5: credit maths, tax, loan readiness, chat fallback, dashboard."""

import time

import pytest

from app.intelligence.advisor.finance import annuity_payment, max_principal


def test_annuity_known_value():
    # 10,000,000 over 12 months at 24%/yr (2%/month): payment = 945,595.96
    assert annuity_payment(10_000_000, 12, 24) == pytest.approx(945_595.96, abs=0.01)
    assert annuity_payment(1_200_000, 12, 0) == 100_000
    assert max_principal(annuity_payment(50_000_000, 24, 24), 24, 24) == pytest.approx(50_000_000, rel=1e-9)


def test_credit_endpoint(client, chilonzor):
    r = client.post("/api/v1/advisor/credit", headers=chilonzor,
                    json={"principal_uzs": 10_000_000, "months": 12, "annual_rate_pct": 24})
    c = r.json()
    assert c["monthly_payment_uzs"] == 945_596 and c["total_interest_uzs"] == 1_347_152
    assert c["affordable"] is True and c["max_loan_uzs"] > 10_000_000
    huge = client.post("/api/v1/advisor/credit", headers=chilonzor,
                       json={"principal_uzs": 5_000_000_000, "months": 12}).json()
    assert huge["affordable"] is False and huge["annual_rate_pct"] == 24
    assert set(huge["max_loan_by_term"]) == {"12", "24", "36"}


def test_cashflow_and_tax(client, chilonzor):
    cf = client.get("/api/v1/advisor/cashflow?months=6", headers=chilonzor).json()
    assert len(cf["months"]) == 6 and cf["months"][-1]["partial"] and cf["avg_monthly_net_uzs"] > 0
    tax = client.get("/api/v1/advisor/tax", headers=chilonzor).json()
    assert len(tax["months"]) == 3 and tax["turnover_regime"]["tax_uzs"] == round(tax["turnover_uzs"] * 0.04)
    assert tax["cheaper_regime"] in ("turnover", "vat") and tax["disclaimer"]


@pytest.mark.parametrize("who", ["chilonzor", "techopt", "sergeli", "realty"])
def test_loan_readiness_bounds(client, request, who):
    r = client.get("/api/v1/advisor/loan-readiness", headers=request.getfixturevalue(who)).json()
    assert 0 <= r["score"] <= 100 and r["grade"] in "ABCD"
    assert sum(f["max_points"] for f in r["factors"]) == 100
    assert all(0 <= f["points"] <= f["max_points"] for f in r["factors"])


def test_loan_readiness_new_company(client):
    key = client.post("/api/v1/auth/register", json={"name": "Empty LLC", "stir": "777777777", "role": "landlord",
                                                    "categories": ["rent"]}).json()["api_key"]
    r = client.get("/api/v1/advisor/loan-readiness", headers={"X-API-Key": key}).json()
    assert 0 <= r["score"] <= 100 and r["how_to_improve"]


@pytest.mark.parametrize("question,lang,key", [
    ("Qancha kredit olsam bo'ladi?", "uz", "max_affordable_loan_uzs"),
    ("Какой налоговый режим выгоднее?", "ru", "tax"),
    ("What is wrong with my budget?", "en", "budget"),
])
def test_chat_fallback(client, chilonzor, question, lang, key):
    r = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": question}).json()
    assert r["language"] == lang and r["source"] == "rules" and key in r["used_data"] and r["answer"]


def test_dashboard_shape_and_speed(client, chilonzor):
    client.get("/api/v1/dashboard", headers=chilonzor)  # warm caches
    t0 = time.perf_counter()
    r = client.get("/api/v1/dashboard", headers=chilonzor)
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    d = r.json()
    k = d["kpis"]
    assert k["audit_issues"] >= 7 and k["money_at_risk_uzs"] > 0 and k["inventory_market_value_uzs"] > 0
    assert 0 <= k["loan_readiness_score"] <= 100 and k["budget_used_pct"] is not None
    assert len(d["cashflow"]) == 6 and len(d["alerts"]) <= 3 and len(d["sourcing_deals"]) <= 5
    assert {"open_rfqs", "recent_deals"} <= set(d)
    assert elapsed < 0.5, f"dashboard took {elapsed:.3f}s"
