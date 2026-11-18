"""Phase 4: RFQ → quotes → ranking → accept → deal in both books → inventory → ratings; offers; co-brokerage."""

SAMARQAND = {"X-API-Key": "seed-305678901"}


def _inv_qty(client, headers, model):
    items = client.get("/api/v1/books/inventory", headers=headers).json()["items"]
    return sum(i["qty"] for i in items if i["model"] == model)


def test_seeded_rfq_ranking(client, chilonzor):
    mine = client.get("/api/v1/exchange/rfqs?scope=mine", headers=chilonzor).json()["items"]
    rfq = next(r for r in mine if r["model"] == "iPhone 13" and r["status"] == "open")
    ranked = client.get(f"/api/v1/exchange/rfqs/{rfq['id']}/quotes", headers=chilonzor).json()
    assert len(ranked["quotes"]) == 2
    assert ranked["quotes"][0]["score"] >= ranked["quotes"][1]["score"]
    assert all(q["reasons"] and q["vs_fair_purchase_pct"] is not None for q in ranked["quotes"])
    assert ranked["recommendation"]["saving_vs_worst_uzs"] > 0


def test_full_exchange_flow(client, chilonzor, techopt):
    tech_before = _inv_qty(client, techopt, "Galaxy A54")
    chil_before = _inv_qty(client, chilonzor, "Galaxy A54")
    r = client.post("/api/v1/exchange/rfqs", headers=chilonzor, json={
        "category": "phone", "brand": "Samsung", "model": "Galaxy A54", "condition": "new",
        "attrs": {"storage_gb": 128}, "qty": 5, "target_unit_price": 2_900_000, "district": "Chilonzor"})
    assert r.status_code == 201, r.text
    created = r.json()
    rfq_id = created["rfq"]["id"]
    assert created["market"]["fair_price_uzs"] > 0 and created["notified_companies"] >= 3

    incoming = client.get("/api/v1/exchange/rfqs?scope=incoming", headers=techopt).json()["items"]
    assert any(x["id"] == rfq_id for x in incoming)
    alerts = client.get("/api/v1/alerts", headers=techopt).json()["items"]
    assert any(a["type"] == "rfq" and a["payload"].get("rfq_id") == rfq_id for a in alerts)

    q1 = client.post(f"/api/v1/exchange/rfqs/{rfq_id}/quotes", headers=techopt,
                     json={"unit_price": 2_800_000, "qty": 5, "delivery_days": 1})
    assert q1.status_code == 201, q1.text
    q2 = client.post(f"/api/v1/exchange/rfqs/{rfq_id}/quotes", headers=SAMARQAND,
                     json={"unit_price": 3_000_000, "qty": 3, "delivery_days": 4})
    assert q2.status_code == 201
    dup = client.post(f"/api/v1/exchange/rfqs/{rfq_id}/quotes", headers=techopt,
                      json={"unit_price": 2_700_000, "qty": 5, "delivery_days": 1})
    assert dup.status_code == 409
    own = client.post(f"/api/v1/exchange/rfqs/{rfq_id}/quotes", headers=chilonzor,
                      json={"unit_price": 1, "qty": 1, "delivery_days": 1})
    assert own.status_code == 403
    assert client.get(f"/api/v1/exchange/rfqs/{rfq_id}/quotes", headers=techopt).status_code == 403

    ranked = client.get(f"/api/v1/exchange/rfqs/{rfq_id}/quotes",
                        headers={**chilonzor, "Accept-Language": "en"}).json()
    best = ranked["quotes"][0]
    assert best["id"] == q1.json()["id"] and best["rank"] == 1
    assert "Lowest price" in best["reasons"]
    assert any("Covers only 3/5" in x for x in ranked["quotes"][1]["reasons"])
    assert ranked["recommendation"]["saving_vs_worst_uzs"] == 200_000 * 5

    deal = client.post(f"/api/v1/exchange/quotes/{best['id']}/accept", headers=chilonzor)
    assert deal.status_code == 200, deal.text
    d = deal.json()
    assert d["total"] == 14_000_000 and d["seller_name"] == "TechOpt Wholesale"
    again = client.post(f"/api/v1/exchange/quotes/{best['id']}/accept", headers=chilonzor)
    assert again.status_code == 409

    buyer_tx = client.get("/api/v1/books/transactions?category=stock_purchase&limit=500", headers=chilonzor).json()
    seller_tx = client.get("/api/v1/books/transactions?category=sale&limit=500", headers=techopt).json()
    btx = [t for t in buyer_tx["items"] if t["deal_id"] == d["id"]]
    stx = [t for t in seller_tx["items"] if t["deal_id"] == d["id"]]
    assert len(btx) == 1 and len(stx) == 1 and btx[0]["total"] == stx[0]["total"] == 14_000_000
    assert client.delete(f"/api/v1/books/transactions/{btx[0]['id']}", headers=chilonzor).status_code == 409

    assert _inv_qty(client, techopt, "Galaxy A54") == tech_before - 5
    assert _inv_qty(client, chilonzor, "Galaxy A54") == chil_before + 5
    rfq = client.get(f"/api/v1/exchange/rfqs/{rfq_id}", headers=chilonzor).json()
    assert rfq["status"] == "awarded"
    ranked = client.get(f"/api/v1/exchange/rfqs/{rfq_id}/quotes", headers=chilonzor).json()
    assert {q["status"] for q in ranked["quotes"]} == {"accepted", "rejected"}

    assert client.post(f"/api/v1/exchange/deals/{d['id']}/rate", headers=chilonzor,
                       json={"score": 5, "comment": "Tez"}).status_code == 201
    assert client.post(f"/api/v1/exchange/deals/{d['id']}/rate", headers=techopt, json={"score": 4}).status_code == 201
    assert client.post(f"/api/v1/exchange/deals/{d['id']}/rate", headers=chilonzor,
                       json={"score": 1}).status_code == 409
    assert client.post(f"/api/v1/exchange/deals/{d['id']}/rate", headers=SAMARQAND,
                       json={"score": 1}).status_code == 403
    deals = client.get("/api/v1/exchange/deals", headers=techopt).json()["items"]
    assert any(x["id"] == d["id"] and x["my_rating"] == 4 for x in deals)
    techopt_id = client.get("/api/v1/companies/me", headers=techopt).json()["id"]
    rep = client.get(f"/api/v1/companies/{techopt_id}", headers=chilonzor).json()["reputation"]
    assert rep["rating"] == 5 and rep["deals_count"] >= 1


def test_offer_buy_flow(client, chilonzor, techopt, sergeli):
    offers = client.get("/api/v1/exchange/offers?kind=wholesale&category=phone", headers=chilonzor).json()["items"]
    redmi = next(o for o in offers if o["model"] == "Redmi Note 13")
    assert redmi["market_badge"] and redmi["market_diff_pct"] < 0
    stock_before = _inv_qty(client, techopt, "Redmi Note 13")
    r = client.post(f"/api/v1/exchange/offers/{redmi['id']}/buy", headers=chilonzor, json={"qty": 4})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == round(redmi["unit_price_uzs"] * 4)
    after = client.get("/api/v1/exchange/offers?mine=true", headers=techopt).json()["items"]
    assert next(o for o in after if o["id"] == redmi["id"])["qty"] == redmi["qty"] - 4
    assert _inv_qty(client, techopt, "Redmi Note 13") == stock_before - 4
    too_many = client.post(f"/api/v1/exchange/offers/{redmi['id']}/buy", headers=chilonzor, json={"qty": 10_000})
    assert too_many.status_code == 409
    assert client.post(f"/api/v1/exchange/offers/{redmi['id']}/buy", headers=techopt,
                       json={"qty": 1}).status_code == 403
    new = client.post("/api/v1/exchange/offers", headers=sergeli, json={
        "kind": "surplus", "category": "car", "brand": "Chevrolet", "model": "Spark", "condition": "used",
        "attrs": {"year": 2019, "mileage_km": 80000}, "qty": 1, "unit_price": 70_000_000})
    assert new.status_code == 201 and new.json()["market_badge"]
    offer_id = new.json()["id"]
    assert client.delete(f"/api/v1/exchange/offers/{offer_id}", headers=chilonzor).status_code == 403
    assert client.delete(f"/api/v1/exchange/offers/{offer_id}", headers=sergeli).status_code == 200


def test_cobroker_matches(client, realty):
    r = client.post("/api/v1/auth/register", json={"name": "Mirobod Rieltor", "stir": "399999999", "role": "realtor",
                                                  "categories": ["house", "rent"], "district": "Mirobod"})
    other = {"X-API-Key": r.json()["api_key"], "Accept-Language": "en"}
    created = client.post("/api/v1/exchange/rfqs", headers=other, json={
        "category": "rent", "district": "Yunusobod", "attrs": {"rooms": 2, "furnished": True}, "qty": 1,
        "target_unit_price": 9_000_000}).json()
    rfq_id = created["rfq"]["id"]
    matches = client.get(f"/api/v1/exchange/rfqs/{rfq_id}/matches", headers=other).json()
    assert matches and all(m["district"] == "Yunusobod" and m["kind"] == "cobroker" for m in matches)
    assert any("Commission split 50/50" in x for x in matches[0]["match_reasons"])
    cob = client.post(f"/api/v1/exchange/offers/{matches[0]['id']}/buy", headers=other, json={"qty": 1})
    assert cob.status_code == 400


def test_demand(client, techopt):
    d = client.get("/api/v1/exchange/demand?days=30&category=phone", headers=techopt).json()
    assert d["most_requested"] and d["most_listed"]
    assert d["most_listed"][0]["listings"] >= d["most_listed"][-1]["listings"]


def test_supplier_sees_own_quote_and_deal_by_rfq(client, chilonzor, techopt):
    """Incoming RFQs carry the supplier's own quote (status, counter); deals filter by rfq_id."""
    rfq = client.post("/api/v1/exchange/rfqs", headers=chilonzor, json={
        "category": "phone", "brand": "Apple", "model": "iPhone 13", "condition": "A",
        "attrs": {"storage_gb": 128}, "qty": 2}).json()["rfq"]
    assert rfq["my_quote"] is None
    q = client.post(f"/api/v1/exchange/rfqs/{rfq['id']}/quotes", headers=techopt,
                    json={"unit_price": 4_400_000, "qty": 2, "delivery_days": 2, "note": "Kafolat 3 oy"}).json()
    client.post(f"/api/v1/exchange/quotes/{q['id']}/counter", headers=chilonzor, json={"unit_price": 4_300_000})
    incoming = client.get("/api/v1/exchange/rfqs?scope=incoming", headers=techopt).json()["items"]
    mine = next(x for x in incoming if x["id"] == rfq["id"])
    assert mine["my_quote_id"] == q["id"]
    assert mine["my_quote"]["status"] == "countered" and mine["my_quote"]["counter_unit_price"] == 4_300_000
    assert mine["my_quote"]["note"] == "Kafolat 3 oy"
    # the buyer never has a quote of its own
    assert client.get(f"/api/v1/exchange/rfqs/{rfq['id']}", headers=chilonzor).json()["my_quote"] is None

    client.post(f"/api/v1/exchange/quotes/{q['id']}/respond", headers=techopt, json={"accept": True})
    deal = client.post(f"/api/v1/exchange/quotes/{q['id']}/accept", headers=chilonzor).json()
    by_rfq = client.get(f"/api/v1/exchange/deals?rfq_id={rfq['id']}", headers=chilonzor).json()
    assert by_rfq["total"] == 1 and by_rfq["items"][0]["id"] == deal["id"]
    assert client.get("/api/v1/exchange/deals?rfq_id=999999", headers=chilonzor).json()["total"] == 0
