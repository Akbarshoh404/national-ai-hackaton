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
    ("Do‘konim ahvoli qanday?", None, "overview", {"kpi_row"}),
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
    """Blocks are built by the tool before the LLM call and passed through unchanged; a rewrite that changes a
    number is rejected and the template answer is kept."""
    q = "100 mln kredit 24 oyga"
    plain = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: "Kredit 999 999 999 so'm. Ikkinchi gap. Uchinchi gap.")
    with_llm = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
    assert with_llm["blocks"] == plain["blocks"]
    assert with_llm["source"] == "rules" and with_llm["answer"] == plain["answer"]  # changed numbers → rejected
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: plain["answer"] + " Qo'shimcha gap. Uchinchi gap.")
    kept = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
    assert kept["source"] == "llm" and kept["blocks"] == plain["blocks"]
    assert len(re.findall(r"[.!?](\s|$)", kept["answer"])) <= 2


def test_local_model_does_not_write_answers(client, chilonzor, monkeypatch):
    """With the local model first, it only routes; the answer is the template (qwen2.5:3b writes poor Uzbek)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "EXTRACT_PROVIDER_ORDER", "local,gemini,rules")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: "Boshqa matn.")
    out = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "100 mln kredit 24 oyga"}).json()
    assert out["source"] == "rules" and out["answer"] != "Boshqa matn."


def test_greeting_and_thanks(client, chilonzor):
    for q, intent in [("Salom", "greeting"), ("assalomu alaykum!", "greeting"), ("Привет", "greeting"),
                      ("rahmat", "thanks"), ("Спасибо!", "thanks")]:
        out = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": q}).json()
        assert out["intent"] == intent and out["blocks"] == [] and len(out["chips"]) == 3, (q, out)
        for c in out["chips"]:
            assert _route_exists(c["action"]["method"], c["action"]["endpoint"]), c
    # a greeting followed by a real question is not small talk
    assert copilot.route_intent("salom, iPhone 13 narxi qancha?", None)[0] == "price"
    assert copilot.route_intent("hisobimda xato bormi", None)[0] == "audit"  # "hi" inside a word


@pytest.mark.parametrize("question", ["iphone 13ni narxi qancha", "iPhone 13 128 nechpul", "сколько стоит iPhone 13"])
def test_price_with_uzbek_suffixes(client, chilonzor, question):
    out = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": question}).json()
    assert out["intent"] == "price", out
    assert {b["type"] for b in out["blocks"]} == {"price_range", "comparables"}


def test_model_aliases():
    assert copilot._aliases("galaxy a54") == ["galaxy a54", "a54"]
    assert copilot._aliases("galaxy tab") == ["galaxy tab"]  # no digit → too generic to match alone
    assert copilot._aliases("iphone 13") == ["iphone 13"]


def test_local_model_routes_with_product(monkeypatch):
    """When rules and context fail, the local model names the tool and the product (never numbers)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "EXTRACT_PROVIDER_ORDER", "local,rules")
    monkeypatch.setattr(llm, "local_suspended", lambda: False)
    monkeypatch.setattr(llm, "local_chat_json", lambda *a, **k: {"intent": "price", "product": "iPhone 13"})
    assert copilot.route("bu telefon arzonmi?", None) == ("price", "local", "iPhone 13")

    def down(*a, **k):
        raise llm.LocalLLMError("down")

    monkeypatch.setattr(llm, "local_chat_json", down)
    assert copilot.route("bu telefon arzonmi?", None) == ("overview", "default", "")


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


@pytest.mark.parametrize("screen", [None, "stock", "books", "budget", "exchange", "advisor"])
@pytest.mark.parametrize("lang", ["uz", "ru", "en"])
def test_chat_suggestions_route_to_their_tool(client, chilonzor, screen, lang):
    """Starter questions come from the backend and each one is routed by the keyword rules to its tool."""
    r = client.get("/api/v1/advisor/chat/suggestions", headers={**chilonzor, "Accept-Language": lang},
                   params={"screen": screen} if screen else None)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["screen"] == screen and 3 <= len(out["questions"]) <= 4
    for s in out["questions"]:
        assert copilot.route_intent(s["question"], {"screen": screen}) == (s["intent"], "rules"), s


def test_chat_suggestion_answers(client, chilonzor):
    qs = client.get("/api/v1/advisor/chat/suggestions?screen=advisor", headers=chilonzor).json()["questions"]
    for s in qs:
        out = client.post("/api/v1/advisor/chat", headers=chilonzor,
                          json={"question": s["question"], "context": {"screen": "advisor"}}).json()
        assert out["intent"] == s["intent"] and out["blocks"]


@pytest.mark.parametrize("question", ["qalesan", "Nima qila olasan?", "ishlar qalay", "что ты умеешь"])
def test_small_talk_is_a_greeting(client, chilonzor, question):
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": question}).json()
    assert d["intent"] == "greeting" and d["intent_source"] == "rules"


@pytest.mark.parametrize(("question", "intent"), [
    ("bugun qancha sotdim", "sales"), ("Сколько продаж в этом месяце?", "sales"),
    ("qaysi tovar sekin sotilyapti", "stock"), ("narxni qayta belgilash kerakmi", "stock"),
])
def test_sales_and_stock_questions(client, chilonzor, question, intent):
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": question}).json()
    assert d["intent"] == intent
    assert d["blocks"]


def test_sales_answer_has_today_and_month(client, chilonzor):
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "bugun qancha sotdim"}).json()
    assert d["answer"].startswith("Bugun") and "Shu oy" in d["answer"]
    assert d["blocks"][0]["type"] == "kpi_row" and d["blocks"][1]["type"] == "bar_chart"


def test_this_month_profit_uses_current_month(client, chilonzor):
    from datetime import date
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "bu oy foyda qancha"}).json()
    assert d["intent"] == "cashflow"
    assert d["answer"].startswith(date.today().strftime("%Y-%m"))
    assert "tushum" in d["answer"] and "xarajat" in d["answer"]


def test_category_price_question_lists_models(client, chilonzor):
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "telefon narxlari qanday"}).json()
    assert d["intent"] == "price"
    assert d["blocks"][0]["type"] == "table" and d["blocks"][0]["rows"]


def test_price_without_model_asks_which_one(client, chilonzor):
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "narxi qancha"}).json()
    assert d["intent"] == "price" and "Qaysi model" in d["answer"]
    asks = [c for c in d["chips"] if c["action"]["endpoint"] == "/api/v1/advisor/chat"]
    assert asks and all(c["action"]["body"]["question"] == c["label"] for c in asks)


def test_unknown_variant_is_not_priced_as_the_base_model(client, chilonzor):
    """"S23 Ultra" must not get the plain S23 price; a model with no data says so instead of failing."""
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "Galaxy A54 Ultra narxi"}).json()
    assert d["intent"] == "price" and not d["blocks"]
    assert "yetarli e'lon yo'q" in d["answer"]


def test_brand_follows_model_name():
    from app.core.catalog import fix_brand
    assert fix_brand("iPhone 14 Pro", "Samsung") == "Apple"
    assert fix_brand("Galaxy A54", None) == "Samsung"
    assert fix_brand("ThinkPad X1", "Lenovo") == "Lenovo"
