"""v2 phase 4: copilot intents → typed blocks and valid chips (no LLM key), credit products and schedules."""

import re

import pytest

from app.core import llm
from app.intelligence.advisor import copilot
from app.main import app

CASES = [
    ("iPhone 13 128 qancha turadi?", None, "price", {"price_range", "comparables"}),
    ("Omborimda qaysi mahsulotlar qimmat?", None, "stock", {"kpi_row", "table"}),
    ("Hisobimda qanday xatolar bor?", None, "audit", {"kpi_row", "table"}),
    ("Как дела с бюджетом?", None, "budget", {"bar_chart", "kpi_row"}),
    ("What was my profit last month?", None, "cashflow", {"line_chart", "kpi_row"}),
    ("100 mln kredit 24 oyga olsam bo'ladimi?", None, "credit", {"loan_schedule", "kpi_row"}),
    ("Какой налоговый режим выгоднее?", None, "tax", {"kpi_row", "bar_chart"}),
    ("Kreditga tayyorlik darajam qanday?", None, "loan_readiness", {"kpi_row", "steps"}),
    # roadmap-style questions route to the remaining finance calculators
    ("Yangi filial ochsam 300 mln bilan nima bo'ladi?", None, "credit", {"loan_schedule", "kpi_row"}),
    ("Can I open a second branch?", None, "credit", {"loan_schedule", "kpi_row"}),
    ("Bank uchun biznes-reja kerak", None, "loan_readiness", {"kpi_row", "steps"}),
    ("Мне нужен бизнес-план", None, "loan_readiness", {"kpi_row", "steps"}),
    ("What is in demand right now?", None, "demand", {"bar_chart", "table"}),
    ("Salom", None, "overview", {"kpi_row"}),
    ("nima qilay?", {"screen": "budget"}, "budget", {"bar_chart", "kpi_row"}),
]


def _route_exists(method: str, endpoint: str) -> bool:
    """Chip endpoints must exist in the OpenAPI spec with that method."""
    path = endpoint.split("?")[0]
    for template, ops in app.openapi()["paths"].items():
        pattern = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", template) + "$"
        if re.match(pattern, path) and method.lower() in ops:
            return True
    return False


@pytest.mark.parametrize("question,context,intent,types", CASES)
def test_intents_blocks_and_chips(client, chilonzor, question, context, intent, types):
    body = {"question": question, **({"context": context} if context else {})}
    r = client.post("/api/v1/advisor/chat", headers=chilonzor, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["intent"] == intent and out["source"] == "rules"
    assert {b["type"] for b in out["blocks"]} == types
    assert 1 <= len(out["blocks"]) <= 2 and 2 <= len(out["chips"]) <= 3
    assert len(re.findall(r"[.!?](\s|$)", out["answer"])) <= 2
    for c in out["chips"]:
        assert _route_exists(c["action"]["method"], c["action"]["endpoint"]), c


def test_context_selected_rows(client, chilonzor):
    over = client.get("/api/v1/stock/units?rating=overpriced&limit=2", headers=chilonzor).json()["items"]
    ids = [u["inventory_id"] for u in over]
    r = client.post("/api/v1/advisor/chat", headers={**chilonzor, "Accept-Language": "en"}, json={
        "question": "Why is this one overpriced?", "context": {"screen": "stock", "inventory_ids": ids}}).json()
    assert r["intent"] == "stock" and r["language"] == "en"
    pr = next(b for b in r["blocks"] if b["type"] == "price_range")
    assert pr["your_price_uzs"] == over[0]["list_price_uzs"]
    table = next(b for b in r["blocks"] if b["type"] == "table")
    assert table["row_ids"] == ids
    reprice = next(c for c in r["chips"] if c["action"]["endpoint"] == "/api/v1/stock/reprice")
    assert reprice["action"]["body"]["inventory_ids"] == ids
    foreign = client.post("/api/v1/advisor/chat", headers=chilonzor, json={
        "question": "qimmatmi?", "context": {"inventory_ids": [999999]}}).json()
    assert foreign["intent"] == "stock"


def test_blocks_untouched_by_llm(client, chilonzor, monkeypatch):
    """Blocks are built by the tool before the LLM call and passed through unchanged."""
    q = "100 mln kredit 24 oyga"
    plain = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: "Kredit 999 999 999 so'm. Ikkinchi gap. Uchinchi gap.")
    with_llm = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
    assert with_llm["source"] == "llm" and with_llm["blocks"] == plain["blocks"]
    assert with_llm["answer"] == "Kredit 999 999 999 so'm. Ikkinchi gap."
    assert "999999999" not in str(with_llm["blocks"]).replace(" ", "")


def test_llm_picks_intent_only_when_rules_fail(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"intent": "tax", "fair_uzs": 1})
    assert copilot.route_intent("hmm???", None) == ("tax", "llm")
    assert copilot.route_intent("soliq qancha?", None) == ("tax", "rules")
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"intent": "steal_money"})
    assert copilot.route_intent("hmm???", None) == ("overview", "default")


def test_annuity_schedule_sums(client, chilonzor):
    c = client.post("/api/v1/advisor/credit", headers=chilonzor,
                    json={"principal_uzs": 120_000_000, "months": 24, "annual_rate_pct": 24}).json()
    sched = c["schedule"]
    assert len(sched) == 24 and sched[-1]["balance_uzs"] == 0
    assert sum(r["principal_uzs"] for r in sched) == pytest.approx(120_000_000, abs=0.01)
    total = sum(r["payment_uzs"] for r in sched)
    assert total == pytest.approx(120_000_000 + sum(r["interest_uzs"] for r in sched), abs=0.01)
    assert total == pytest.approx(c["total_payment_uzs"], abs=24)
    assert sum(r["interest_uzs"] for r in sched) == pytest.approx(c["total_interest_uzs"], abs=24)


def test_credit_products(client, chilonzor, realty):
    m = client.post("/api/v1/advisor/credit", headers=realty, json={
        "product": "mortgage", "months": 180, "asset_value_uzs": 1_000_000_000}).json()
    assert m["product"] == "mortgage" and m["ltv"] == 0.7 and m["down_payment_uzs"] == 300_000_000
    assert m["principal_uzs"] == 700_000_000 and m["annual_rate_pct"] == 18 and len(m["schedule"]) == 180
    a = client.post("/api/v1/advisor/credit", headers=realty, json={
        "product": "auto_loan", "months": 36, "asset_value_uzs": 500_000_000, "down_payment_pct": 0.4}).json()
    assert a["ltv"] == 0.6 and a["principal_uzs"] == 300_000_000
    too_long = client.post("/api/v1/advisor/credit", headers=chilonzor,
                           json={"product": "leasing", "months": 48, "principal_uzs": 10_000_000})
    assert too_long.status_code == 422 and too_long.json()["error"]["code"] == "term_too_long"
    no_principal = client.post("/api/v1/advisor/credit", headers=chilonzor, json={"months": 12})
    assert no_principal.status_code == 422


REMOVED = [("POST", "/api/v1/advisor/expansion"), ("POST", "/api/v1/advisor/business-plan"),
           ("GET", "/api/v1/advisor/business-plan"), ("GET", "/api/v1/lender/applications/1/business-plan")]


@pytest.mark.parametrize("method,path", REMOVED)
def test_roadmap_endpoints_removed(client, chilonzor, method, path):
    headers = {"X-API-Key": "demo-demo-bank"} if "/lender/" in path else chilonzor
    r = client.request(method, path, headers=headers, json={})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("expansion" in p or "business-plan" in p for p in paths)


def test_roadmap_questions_use_existing_numbers_only(client, chilonzor):
    """Branch / business-plan questions get calculator blocks and no links to removed endpoints."""
    for q in ("Ikkinchi filial ochsam bo'ladimi?", "biznes reja", "open a new branch with 300 mln"):
        out = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
        assert out["intent"] in ("credit", "loan_readiness")
        assert all(b["type"] != "file" for b in out["blocks"])
        endpoints = [c["action"]["endpoint"] for c in out["chips"]]
        assert not any("expansion" in e or "business-plan" in e for e in endpoints)
