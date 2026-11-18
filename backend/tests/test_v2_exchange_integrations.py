"""v2 phase 7: counter-offers, deal document, demand by district, radar fields, integrations, bot additions."""

import asyncio
from datetime import timedelta

from app.channels import bot
from app.core import db as dbm
from app.core.db import utcnow
from app.data_pipeline import extractor
from app.data_pipeline.telegram_ingest import save_post

SAMARQAND = {"X-API-Key": "seed-305678901"}


def test_counter_offer_flow(client, chilonzor, techopt):
    rfq = client.post("/api/v1/exchange/rfqs", headers=chilonzor, json={
        "category": "phone", "brand": "Apple", "model": "iPhone 14", "condition": "A", "attrs": {"storage_gb": 128},
        "qty": 4, "target_unit_price": 5_000_000, "district": "Chilonzor"}).json()["rfq"]
    q = client.post(f"/api/v1/exchange/rfqs/{rfq['id']}/quotes", headers=techopt,
                    json={"unit_price": 5_600_000, "qty": 4, "delivery_days": 2}).json()
    assert client.post(f"/api/v1/exchange/quotes/{q['id']}/counter", headers=techopt,
                       json={"unit_price": 5_000_000}).status_code == 403
    c = client.post(f"/api/v1/exchange/quotes/{q['id']}/counter", headers=chilonzor,
                    json={"unit_price": 5_200_000, "note": "Ulgurji narx"})
    assert c.status_code == 200 and c.json()["status"] == "countered" and c.json()["counter_unit_price"] == 5_200_000
    assert client.post(f"/api/v1/exchange/quotes/{q['id']}/accept", headers=chilonzor).status_code == 409
    alerts = client.get("/api/v1/alerts", headers=techopt).json()["items"]
    assert any(a["payload"].get("quote_id") == q["id"] and a["type"] == "quote" for a in alerts)
    assert client.post(f"/api/v1/exchange/quotes/{q['id']}/respond", headers=chilonzor,
                       json={"accept": True}).status_code == 403
    r = client.post(f"/api/v1/exchange/quotes/{q['id']}/respond", headers=techopt, json={"accept": True}).json()
    assert r["status"] == "pending" and r["unit_price"] == 5_200_000
    second = client.post(f"/api/v1/exchange/quotes/{q['id']}/counter", headers=chilonzor, json={"unit_price": 1})
    assert second.status_code == 409 and second.json()["error"]["code"] == "counter_used"
    ranked = client.get(f"/api/v1/exchange/rfqs/{rfq['id']}/quotes", headers=chilonzor).json()
    assert ranked["quotes"][0]["unit_price_uzs"] == 5_200_000
    deal = client.post(f"/api/v1/exchange/quotes/{q['id']}/accept", headers=chilonzor).json()
    assert deal["unit_price"] == 5_200_000 and deal["total"] == 20_800_000

    doc = client.get(f"/api/v1/exchange/deals/{deal['id']}/document", headers=techopt)
    assert doc.status_code == 200 and "TechOpt Wholesale" in doc.text and "302345678" in doc.text
    assert "not a tax invoice" in doc.text and f"#{deal['id']}" in doc.text
    assert client.get(f"/api/v1/exchange/deals/{deal['id']}/document?format=pdf", headers=chilonzor).status_code == 200
    assert client.get(f"/api/v1/exchange/deals/{deal['id']}/document", headers=SAMARQAND).status_code == 404


def test_final_price_response(client, chilonzor):
    rfq = client.post("/api/v1/exchange/rfqs", headers=chilonzor, json={
        "category": "phone", "model": "Galaxy S23", "condition": "A", "attrs": {"storage_gb": 256},
        "qty": 2}).json()["rfq"]
    q = client.post(f"/api/v1/exchange/rfqs/{rfq['id']}/quotes", headers=SAMARQAND,
                    json={"unit_price": 6_500_000, "qty": 2, "delivery_days": 3}).json()
    client.post(f"/api/v1/exchange/quotes/{q['id']}/counter", headers=chilonzor, json={"unit_price": 5_500_000})
    r = client.post(f"/api/v1/exchange/quotes/{q['id']}/respond", headers=SAMARQAND,
                    json={"accept": False, "unit_price": 6_100_000}).json()
    assert r["status"] == "pending" and r["unit_price"] == 6_100_000
    again = client.post(f"/api/v1/exchange/quotes/{q['id']}/respond", headers=SAMARQAND, json={"accept": True})
    assert again.status_code == 409


def test_demand_by_district_and_radar_fields(client, chilonzor, techopt):
    d = client.get("/api/v1/exchange/demand?days=30", headers=techopt).json()
    assert d["by_district"] and {"district", "model", "requests", "units"} <= set(d["by_district"][0])
    radar = client.get("/api/v1/market/sourcing-radar?days=3", headers=chilonzor).json()["items"]
    assert radar
    r = radar[0]
    assert r["expected_resale_margin_uzs"] == round(r["fair_price_uzs"] * 0.97 - r["price_uzs"])
    assert r["expected_days_to_sell"] and r["expected_days_to_sell"] > 0


def test_integrations_cards_and_didox_sync(client, chilonzor):
    cards = {c["kind"]: c for c in client.get("/api/v1/integrations", headers=chilonzor).json()}
    assert set(cards) == {"telegram", "didox", "soliq", "billz", "onec", "bank"}
    assert cards["telegram"]["mode"] == "live" and cards["didox"]["mode"] == "mock"
    assert cards["didox"]["status"] == "connected" and cards["bank"]["status"] == "not_connected"
    r = client.post("/api/v1/integrations/didox/sync", headers=chilonzor)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 3 and out["mode"] == "mock"
    types = {f["type"] for f in out["audit_flags"]}
    assert {"qty_mismatch", "overpayment"} <= types, types
    over = next(f for f in out["audit_flags"] if f["type"] == "overpayment")
    assert "iPhone 14" in over["message"]
    again = client.post("/api/v1/integrations/didox/sync", headers=chilonzor).json()
    assert again["created"] == 0, "invoices are imported once"
    acts = client.get("/api/v1/activity?entity=integration", headers=chilonzor).json()
    assert acts["total"] >= 2


def test_other_mock_syncs(client, sergeli):
    for kind, expected in (("onec", 2), ("bank", 2), ("soliq", 1), ("billz", 2)):
        r = client.post(f"/api/v1/integrations/{kind}/sync", headers=sergeli)
        assert r.status_code == 200 and r.json()["created"] == expected, (kind, r.text)
    assert client.post("/api/v1/integrations/telegram/sync", headers=sergeli).status_code == 400
    assert client.post("/api/v1/integrations/sap/sync", headers=sergeli).status_code == 404


def test_bot_price_forward_voice(client):
    bot.handle_text(444, "/link demo-chilonzor-phone")
    reply = bot.handle_text(444, "/price cobalt 2021 45 ming probeg pozitsiya 4")
    assert "Cobalt" in reply and "Oraliq" in reply
    assert "Masalan" in bot.handle_text(444, "/price")
    with dbm.SessionLocal() as db:
        post = save_post(db, "fwdshop", 9, utcnow() - timedelta(hours=1),
                         "iPhone 13 128gb A holat narxi 4 100 000 so'm")
        extractor.process_batch(db, [post])
    fwd = asyncio.run(bot.handle_forward(444, "https://t.me/fwdshop/9", ""))
    assert "iPhone 13" in fwd and "Bozor" in fwd
    unknown = asyncio.run(bot.handle_forward(444, "https://t.me/nowhere/1", "gentra 2020 70000 km 12500$"))
    assert "Gentra" in unknown
    assert "GEMINI_API_KEY" in bot.handle_voice(444, b"OggS", "audio/ogg")
