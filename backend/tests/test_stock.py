"""v2 phase 2: stock command center — ratings, summary, atomic reprice, surplus listing, exports."""

import io
import time

from openpyxl import load_workbook

APPRAISER = {"X-API-Key": "demo-chilonzor-appraiser"}


def _units(client, headers, **params):
    q = "&".join(f"{k}={v}" for k, v in {"limit": 500, **params}.items())
    return client.get(f"/api/v1/stock/units?{q}", headers=headers).json()


def test_planted_stock_detected(client, chilonzor):
    s = client.get("/api/v1/stock/summary", headers=chilonzor).json()
    assert s["units_overpriced"] == 14
    assert s["units_older_slow"] == 8
    assert s["units_older_30d"] == 14  # 6 aging + 8 slow
    assert s["stock_value_market_uzs"] > s["stock_value_cost_uzs"] > 0
    assert s["margin_at_risk_uzs"] == s["overpricing_at_risk_uzs"] + s["aging_cash_tied_uzs"]
    page = _units(client, chilonzor, rating="overpriced")
    assert page["total"] == 14
    u = page["items"][0]
    assert u["list_price_uzs"] > u["range_uzs"][1] and u["suggested_action"] == "reprice_down"
    assert u["suggested_price_uzs"] == round(u["fair_price_uzs"], -3) and u["reasons"]
    assert u["identifier"] is None or len(u["identifier"]) == 15


def test_unit_rules(client, chilonzor):
    rows = _units(client, chilonzor)["items"]
    under = [r for r in rows if r["rating"] == "underpriced"]
    assert under and all(r["suggested_price_uzs"] >= round(r["unit_cost_uzs"] * 1.03, -3) for r in under)
    assert all(r["suggested_action"] == "reprice_up" for r in under)
    slow = [r for r in rows if r["days_in_stock"] > 60]
    assert len(slow) == 8 and all(r["suggested_action"] == "list_on_exchange" for r in slow)
    assert all(r["suggested_price_uzs"] == round(r["range_uzs"][0], -3) for r in slow if r["range_uzs"])
    iphones = [r for r in rows if r["model"].startswith("iPhone") and r["rating"] == "fair"]
    assert (iphones and "sales" in iphones[0]["days_basis"].lower()) or "sotuv" in iphones[0]["days_basis"]
    laptop = next(r for r in rows if r["category"] == "laptop")
    assert laptop["expected_days_to_sell"] in (30, 39, 24)  # default × rating factor


def test_store_filter_and_appraiser(client, chilonzor):
    stores = client.get("/api/v1/stores", headers=chilonzor).json()["items"]
    a = _units(client, chilonzor, store_id=stores[0]["id"])["total"]
    b = _units(client, chilonzor, store_id=stores[1]["id"])["total"]
    assert a + b == _units(client, chilonzor)["total"] and a > 0 and b > 0
    assert client.get("/api/v1/stock/units?limit=1", headers=APPRAISER).status_code == 200
    assert client.post("/api/v1/stock/reprice", headers=APPRAISER,
                       json={"items": [{"inventory_id": 1, "new_price_uzs": 1}]}).status_code == 403


def test_summary_fast(client, chilonzor):
    client.get("/api/v1/stock/summary", headers=chilonzor)
    t0 = time.perf_counter()
    assert client.get("/api/v1/stock/summary", headers=chilonzor).status_code == 200
    assert client.get("/api/v1/stock/units?limit=500", headers=chilonzor).status_code == 200
    assert time.perf_counter() - t0 < 0.5


def test_reprice_atomic_and_bulk(client, chilonzor):
    rows = _units(client, chilonzor, rating="overpriced")["items"]
    a, b = rows[0], rows[1]
    bad = client.post("/api/v1/stock/reprice", headers=chilonzor, json={"items": [
        {"inventory_id": a["inventory_id"], "new_price_uzs": 1_000_000}, {"inventory_id": 999999,
                                                                          "new_price_uzs": 1_000_000}]})
    assert bad.status_code == 404
    again = {r["inventory_id"]: r for r in _units(client, chilonzor)["items"]}
    assert again[a["inventory_id"]]["list_price_uzs"] == a["list_price_uzs"], "nothing applied on failure"
    zero = client.post("/api/v1/stock/reprice", headers=chilonzor,
                       json={"items": [{"inventory_id": a["inventory_id"], "new_price_uzs": 0}]})
    assert zero.status_code == 422
    ok = client.post("/api/v1/stock/reprice", headers=chilonzor,
                     json={"inventory_ids": [a["inventory_id"], b["inventory_id"]], "use_suggested": True})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["updated"] == 2 and all(u["rating"] == "fair" for u in body["units"])
    s = client.get("/api/v1/stock/summary", headers=chilonzor).json()
    assert s["units_overpriced"] == 12
    acts = client.get("/api/v1/activity?entity=inventory", headers=chilonzor).json()["items"]
    assert any("Repriced 2 units" in x["summary"] for x in acts)


def test_list_on_exchange(client, chilonzor):
    slow = [r for r in _units(client, chilonzor)["items"] if r["days_in_stock"] > 60]
    ids = [r["inventory_id"] for r in slow if r["model"] == "Redmi Note 12"]
    r = client.post("/api/v1/stock/list-on-exchange", headers=chilonzor, json={"inventory_ids": ids})
    assert r.status_code == 201, r.text
    offers = r.json()
    assert len(offers) == 1 and offers[0]["kind"] == "surplus" and offers[0]["qty"] == 2
    assert offers[0]["market_badge"]


def test_exports(client, chilonzor):
    x = client.get("/api/v1/stock/export?format=xlsx", headers=chilonzor)
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    ws = load_workbook(io.BytesIO(x.content)).active
    assert ws.max_row >= 81 and ws.cell(1, 1).value == "inventory_id"
    c = client.get("/api/v1/stock/export?format=csv", headers=chilonzor)
    assert c.text.startswith("inventory_id,")
    one_c = client.get("/api/v1/stock/export?format=1c", headers=chilonzor)
    assert one_c.content.decode("utf-8-sig").startswith("Ид;Наименование;Артикул")
    tx = client.get("/api/v1/books/transactions/export?format=1c", headers=chilonzor)
    assert tx.status_code == 200 and tx.content.decode("utf-8-sig").startswith("Дата;ВидОперации")
    txx = client.get("/api/v1/books/transactions/export?format=xlsx&month=2026-11", headers=chilonzor)
    assert txx.status_code == 200
