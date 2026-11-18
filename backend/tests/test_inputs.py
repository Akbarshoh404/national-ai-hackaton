"""v2 phase 6: free-text parse (rule fallback), IMEI, upload preview + mapping, price-from-link, voice."""

import json
from datetime import timedelta

import pytest

from app.core import db as dbm
from app.core.db import utcnow
from app.data_pipeline import extractor, telegram_ingest
from app.data_pipeline.telegram_ingest import save_post
from app.intelligence.market.imei import make_imei

APPRAISER = {"X-API-Key": "demo-chilonzor-appraiser"}


@pytest.mark.parametrize("text,expected", [
    ("iphone 13 pro 256 87% korobka bor",
     {"category": "phone", "brand": "Apple", "model": "iPhone 13 Pro",
      "attrs": {"storage_gb": 256, "battery_pct": 87, "has_box": True}}),
    ("cobalt 2021 45 ming probeg pozitsiya 4",
     {"category": "car", "brand": "Chevrolet", "model": "Cobalt", "price": None,
      "attrs": {"year": 2021, "mileage_km": 45000, "trim": 4}}),
    ("chilonzor 2 xona 55 kv mebelli",
     {"category": "rent", "district": "Chilonzor", "attrs": {"rooms": 2, "area_m2": 55.0, "furnished": True}}),
])
def test_parse_rule_fallback(client, chilonzor, text, expected):
    r = client.post("/api/v1/input/parse", headers=chilonzor, json={"text": text})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["source"] == "rules"
    for k, v in expected.items():
        if k == "attrs":
            assert {a: out["attrs"].get(a) for a in v} == v
        else:
            assert out[k] == v, (k, out)


def test_parse_missing_fields_and_price(client, chilonzor):
    out = client.post("/api/v1/input/parse", headers=chilonzor,
                      json={"text": "iphone 13 pro 256 87% korobka bor"}).json()
    assert out["missing_fields"] == ["condition"] and out["confidence"] == "medium"
    priced = client.post("/api/v1/input/parse", headers=chilonzor,
                         json={"text": "Redmi note 13 8/256 yangi 2.6 mln"}).json()
    assert priced["price"] == 2_600_000 and priced["currency"] == "UZS" and priced["missing_fields"] == []
    # parse → price round trip, as the frontend does
    est = client.post("/api/v1/market/price", headers=chilonzor, json={
        k: priced[k] for k in ("category", "brand", "model", "condition", "attrs")})
    assert est.status_code == 200
    assert client.post("/api/v1/input/parse", headers=APPRAISER, json={"text": "gentra 2020"}).status_code == 200


def test_imei(client, chilonzor):
    good = make_imei("35340913", 123456)
    r = client.post("/api/v1/input/imei", headers=chilonzor, json={"imei": good}).json()
    assert r["valid"] and r["model"] == "iPhone 13" and r["storage_options"] == [128, 256, 512]
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert client.post("/api/v1/input/imei", headers=chilonzor, json={"imei": bad}).json()["valid"] is False
    unknown = make_imei("99999999", 1)
    u = client.post("/api/v1/input/imei", headers=chilonzor, json={"imei": unknown}).json()
    assert u["valid"] and u["model"] is None
    units = client.get("/api/v1/stock/units?category=phone&limit=5", headers=chilonzor).json()["items"]
    seeded = next(x for x in units if x["identifier"])
    s = client.post("/api/v1/input/imei", headers=chilonzor, json={"imei": seeded["identifier"]}).json()
    assert s["valid"] and s["model"] == seeded["model"]


CSV = ("Sana;Modda;Jami summa;Yetkazib beruvchi;Nimadir\n"
       "05.11.2026;svet;1 250 000;Elektr tarmoqlari;x\n"
       "06.11.2026;ijara;6 000 000;Ijara egasi;y\n"
       "bad;reklama;500 000;;z\n")


def test_upload_preview_and_mapping(client, sergeli):
    r = client.post("/api/v1/books/upload/preview", headers=sergeli,
                    files={"file": ("b.csv", CSV.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["columns"] == ["Sana", "Modda", "Jami summa", "Yetkazib beruvchi", "Nimadir"]
    assert p["mapping"]["Sana"] == {"field": "date", "confidence": 1.0}
    assert p["mapping"]["Jami summa"]["field"] == "total" and p["mapping"]["Jami summa"]["confidence"] == 0.6
    assert p["mapping"]["Nimadir"]["field"] is None
    assert len(p["rows"]) == 2 and p["errors"][0]["row"] == 4 and p["total_rows"] == 3
    mapping = {"Sana": "date", "Modda": "category", "Jami summa": "total", "Yetkazib beruvchi": "note",
               "Nimadir": None}
    up = client.post("/api/v1/books/upload", headers=sergeli, files={"file": ("b.csv", CSV.encode(), "text/csv")},
                     data={"mapping": json.dumps(mapping)})
    assert up.status_code == 200 and up.json()["created"] == 2
    bad = client.post("/api/v1/books/upload", headers=sergeli, files={"file": ("b.csv", CSV.encode(), "text/csv")},
                      data={"mapping": json.dumps({"Sana": "price_of_tea"})})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_mapping"
    nocols = client.post("/api/v1/books/upload/preview", headers=sergeli,
                         files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")}).json()
    assert nocols["rows"] == [] and nocols["errors"][0]["row"] == 0


def test_price_from_link_db_hit(client, chilonzor):
    with dbm.SessionLocal() as db:
        post = save_post(db, "linkshop", 77, utcnow() - timedelta(hours=2),
                         "iPhone 14 128gb A holat narxi 7 900 000 so'm")
        extractor.process_batch(db, [post])
    r = client.post("/api/v1/market/price-from-link", headers=chilonzor, json={"url": "https://t.me/linkshop/77"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["fetched"] == "database" and out["listing"]["model"] == "iPhone 14"
    assert out["estimate"]["fair_price_uzs"] > 0 and out["badge"] and out["diff_pct"] > 0
    missing = client.post("/api/v1/market/price-from-link", headers=chilonzor, json={"url": "t.me/linkshop/78"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "post_not_found"
    assert client.post("/api/v1/market/price-from-link", headers=chilonzor,
                       json={"url": "https://example.com/x"}).status_code == 422


def test_price_from_link_telegram_path(client, chilonzor, monkeypatch):
    async def fake_fetch(channel, msg_id):
        assert (channel, msg_id) == ("liveshop", 5)
        return "Gentra 2020 probeg 70 000 km metan, narxi 12 300$ +998 90 123 45 67", utcnow(), False

    monkeypatch.setattr(telegram_ingest, "connected", lambda: True)
    monkeypatch.setattr(telegram_ingest, "fetch_message", fake_fetch)
    r = client.post("/api/v1/market/price-from-link", headers=chilonzor, json={"url": "https://t.me/liveshop/5"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["fetched"] == "telegram" and out["listing"]["model"] == "Gentra" and out["listing"]["price_usd"] == 12300
    with dbm.SessionLocal() as db:
        from app.core.models import RawPost

        raw = db.query(RawPost).filter_by(source="liveshop", msg_id=5).one()
        assert "+998" not in raw.text and "[tel]" in raw.text
    again = client.post("/api/v1/market/price-from-link", headers=chilonzor, json={"url": "https://t.me/liveshop/5"})
    assert again.json()["fetched"] == "database"


def test_voice_without_key(client, chilonzor):
    r = client.post("/api/v1/input/voice", headers=chilonzor, files={"file": ("v.ogg", b"OggS....", "audio/ogg")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"
    bad = client.post("/api/v1/input/voice", headers=chilonzor, files={"file": ("v.txt", b"hi", "text/plain")})
    assert bad.status_code == 415
