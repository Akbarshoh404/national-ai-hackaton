"""Phase 2: pricing engine and market endpoints on seed data."""

import time

import pytest

SEED_USD = 12700


@pytest.mark.parametrize("body,lo,hi", [
    ({"category": "phone", "model": "iPhone 13", "condition": "A", "attrs": {"storage_gb": 128}}, 330, 480),
    ({"category": "laptop", "brand": "Apple", "model": "MacBook Air M1", "condition": "A",
      "attrs": {"ram_gb": 8, "ssd_gb": 256}}, 480, 680),
    ({"category": "car", "model": "Chevrolet Cobalt", "condition": "used",
      "attrs": {"year": 2021, "mileage_km": 50000, "fuel": "benzin"}}, 7500, 12500),
    ({"category": "house", "district": "Yunusobod", "attrs": {"rooms": 3, "area_m2": 85}}, 85000, 150000),
    ({"category": "rent", "district": "Chilonzor", "attrs": {"rooms": 2, "furnished": True}}, 300, 700),
])
def test_price_all_categories(client, chilonzor, body, lo, hi):
    t0 = time.perf_counter()
    r = client.post("/api/v1/market/price", json=body, headers=chilonzor)
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    e = r.json()
    assert lo <= e["fair_price_usd"] <= hi, e
    assert e["range_uzs"][0] <= e["fair_price_uzs"] <= e["range_uzs"][1]
    assert e["fair_buy_price_uzs"] <= e["fair_price_uzs"]
    assert e["comparables"] >= 3 and e["basis"] and e["confidence"] in ("high", "medium", "low")
    assert e["samples"] and all(x["source_url"] for x in e["samples"])
    assert elapsed < 0.5


def test_price_asking_badge(client, chilonzor):
    body = {"category": "phone", "model": "iPhone 13", "condition": "A", "attrs": {"storage_gb": 128}}
    fair = client.post("/api/v1/market/price", json=body, headers=chilonzor).json()["fair_price_uzs"]
    r = client.post("/api/v1/market/price", json={**body, "asking_price_uzs": fair * 0.88},
                    headers={**chilonzor, "Accept-Language": "en"})
    a = r.json()["asking"]
    assert a["diff_pct"] == pytest.approx(-12, abs=0.2)
    assert a["badge"] == "12% below market"


def test_price_buy_quote(client, chilonzor):
    body = {"category": "phone", "model": "iPhone 13", "condition": "A", "attrs": {"storage_gb": 128}}
    e = client.post("/api/v1/market/price", json=body, headers=chilonzor).json()
    q = e["buy_quote"]
    assert q["resale_price_uzs"] == e["fair_price_uzs"] and q["max_buy_price_uzs"] == e["fair_buy_price_uzs"]
    assert q["handling_uzs"] == round(e["fair_price_uzs"] * q["handling_pct"])
    assert q["expected_profit_uzs"] == pytest.approx(
        q["resale_price_uzs"] - q["handling_uzs"] - q["max_buy_price_uzs"], abs=1)
    assert q["expected_profit_uzs"] > 0 and q["dealer_margin_pct"] == 0.15
    assert q["expected_days_to_sell"] and q["days_basis"]


def test_price_condition_ordering(client, chilonzor):
    vals = []
    for cond in ["new", "A", "B", "C"]:
        r = client.post("/api/v1/market/price", headers=chilonzor, json={
            "category": "phone", "model": "iPhone 14", "condition": cond, "attrs": {"storage_gb": 128}})
        vals.append(r.json()["fair_price_uzs"])
    assert vals == sorted(vals, reverse=True)


def test_price_imei_deduction(client, chilonzor):
    base = {"category": "phone", "model": "iPhone 12", "condition": "B", "attrs": {"storage_gb": 128}}
    a = client.post("/api/v1/market/price", json=base, headers=chilonzor).json()["fair_price_uzs"]
    b = client.post("/api/v1/market/price", headers=chilonzor,
                    json={**base, "attrs": {"storage_gb": 128, "imei_registered": False}}).json()["fair_price_uzs"]
    assert b < a


def test_not_enough_data(client, chilonzor):
    r = client.post("/api/v1/market/price", headers=chilonzor,
                    json={"category": "phone", "model": "Nokia 3310", "condition": "new"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "not_enough_market_data"


def test_listings_feed_and_cursor(client, chilonzor):
    r = client.get("/api/v1/market/listings?category=phone&limit=10", headers=chilonzor).json()
    assert len(r["items"]) == 10 and r["total"] >= 390 and r["next_cursor"]
    r2 = client.get(f"/api/v1/market/listings?category=phone&limit=10&cursor={r['next_cursor']}",
                    headers=chilonzor).json()
    assert r2["items"][0]["id"] < r["items"][-1]["id"]
    shop = client.get("/api/v1/market/listings?category=phone&seller_type=shop&limit=5", headers=chilonzor).json()
    assert all(i["seller_type"] == "shop" for i in shop["items"])


def test_stats(client, chilonzor):
    s = client.get("/api/v1/market/stats", headers=chilonzor).json()
    assert s["listings_per_category"]["car"] >= 390 and s["fx_usd_uzs"] == SEED_USD


def test_sourcing_radar(client, chilonzor, sergeli):
    r = client.get("/api/v1/market/sourcing-radar?days=3", headers=chilonzor).json()
    assert r["items"], "planted deals should appear"
    assert all(i["category"] in ("phone", "laptop") for i in r["items"])
    assert all(i["discount_pct"] >= 15 for i in r["items"])
    cars = client.get("/api/v1/market/sourcing-radar?days=3", headers=sergeli).json()
    assert all(i["category"] == "car" for i in cars["items"])


def test_trend_models_heatmap_yield(client, chilonzor, realty):
    tr = client.get("/api/v1/market/trend?category=phone&model=iPhone 13", headers=chilonzor).json()
    assert len(tr["points"]) >= 6 and all(p["listings"] > 0 for p in tr["points"])
    models = client.get("/api/v1/market/models?category=phone&q=iphone", headers=chilonzor).json()
    assert models and all("iphone" in m["model_norm"] for m in models)
    hm = client.get("/api/v1/market/heatmap?category=house", headers=realty).json()
    cells = {c["district"]: c for c in hm["cells"]}
    assert cells["Mirobod"]["median_per_m2_usd"] > cells["Bektemir"]["median_per_m2_usd"]
    y = client.post("/api/v1/market/rental-yield", headers=realty,
                    json={"district": "Yunusobod", "rooms": 2, "area_m2": 60}).json()
    assert 3 < y["gross_yield_pct"] < 12 and y["net_yield_pct"] < y["gross_yield_pct"]
    assert y["payback_years"] > 5
