"""Phase 6: PII stripping, price parsing, extractor with a mocked LLM, reposts, deal alerts, admin, SSE."""

from datetime import timedelta

import pytest

from app.core import db as dbm
from app.core import llm
from app.core.db import utcnow
from app.core.events import Event, bus
from app.core.models import Alert, Listing, RawPost, Source
from app.core.sse import visible
from app.data_pipeline import extractor
from app.data_pipeline.telegram_ingest import is_offer, save_post, strip_pii
from app.intelligence.market import pricing


@pytest.mark.parametrize("raw,clean", [
    ("iPhone 13 5.2 mln +998 90 123-45-67", "iPhone 13 5.2 mln [tel]"),
    ("Cobalt 9500$ tel: 90 123 45 67 @seller_uz", "Cobalt 9500$ tel: [tel] [user]"),
    ("Kvartira https://t.me/somechannel/12 narxi 85000$", "Kvartira [link] narxi 85000$"),
    ("Telefon (91) 234-56-78 t.me/xyz narx 300$", "Telefon [tel] [link] narx 300$"),
])
def test_strip_pii(raw, clean):
    assert strip_pii(raw) == clean


def test_price_values_survive_pii_filter():
    assert "950 000 000" in strip_pii("Kvartira 950 000 000 so'm")
    assert "120000000" in strip_pii("Cobalt narxi 120000000 so'm")


def test_is_offer():
    assert is_offer("Sotiladi iPhone 12, narxi 3 mln")
    assert not is_offer("Assalomu alaykum hammaga")
    assert not is_offer("5 mln")  # too short


@pytest.mark.parametrize("text,cat,expected", [
    ("iPhone 13 128gb 5.2 mln so'm", "phone", (5_200_000, "UZS")),
    ("Narxi 250 ming so'm", "phone", (250_000, "UZS")),
    ("Galaxy A54 $260 ideal", "phone", (260, "USD")),
    ("Gentra 2020 12 500 у.е.", "car", (12_500, "USD")),
    ("Narxi: 4 300 000 so'm", "phone", (4_300_000, "UZS")),
    ("Cobalt 2021 narxi 11500", "car", (11_500, "USD")),
    ("Ijara 2 xona 450$ oyiga", "rent", (450, "USD")),
])
def test_parse_price(text, cat, expected):
    assert extractor.parse_price(text, cat) == expected


def _post(db, source, msg_id, text, hours_ago=1):
    p = save_post(db, source, msg_id, utcnow() - timedelta(hours=hours_ago), text)
    assert p is not None
    return p


@pytest.fixture()
def mock_llm(monkeypatch):
    calls = []

    def install(responder):
        monkeypatch.setattr(llm, "available", lambda: True)

        def fake(prompt, **kw):
            calls.append(prompt)
            return responder(prompt, len(calls))

        monkeypatch.setattr(llm, "generate_json", fake)
        return calls

    return install


def test_extractor_with_mocked_llm(client, mock_llm):
    with dbm.SessionLocal() as db:
        db.add(Source(title="Test Phones", username="testphones", category_hint="phone", seller_type_default="shop"))
        db.add(Source(title="Test Cars", username="testcars", category_hint="car", seller_type_default="private"))
        db.commit()
        p1 = _post(db, "testphones", 1, "iPhone 13 128gb A holat 5.2 mln so'm +998 90 123 45 67 @mixmobile")
        p2 = _post(db, "testphones", 2, "Galaxy A54 128gb yangi $255, t.me/mixmobiles")
        p3 = _post(db, "testcars", 3, "Sotib olaman Cobalt, narxi 10000 gacha bo'lsin")
        p4 = _post(db, "testcars", 4, "Cobalt 2021 probeg 50 000 km benzin, kraskasi yo'q, 9 900$")
        assert "[tel]" in p1.text and "[user]" in p1.text and "+998" not in p1.text
        assert "[link]" in p2.text
        ids = [p1.id, p2.id, p3.id, p4.id]

    responses = [
        {"i": 0, "skip": False, "category": "phone", "brand": "Apple", "model": "iPhone 13", "condition": "A",
         "price": 5.2, "currency": "UZS", "district": "Chilonzor", "seller_type": None,
         "attrs": {"storage_gb": 128, "imei_registered": "true", "bogus": 1}},
        {"i": 1, "skip": False, "category": "phone", "brand": "Samsung", "model": "Galaxy A54", "condition": "new",
         "price": 255, "currency": "$", "district": None, "seller_type": "shop", "attrs": {"storage_gb": "128"}},
        {"i": 2, "skip": True, "skip_reason": "buying"},
        {"i": 3, "skip": False, "category": "car", "brand": "Chevrolet", "model": "Cobalt", "condition": "used",
         "price": 9900, "currency": None, "district": None, "seller_type": None,
         "attrs": {"year": 2021, "mileage_km": 50000, "fuel": "benzin", "paint_clean": True}},
    ]

    def responder(prompt, n):
        if n == 1:
            return responses[:3]  # wrong length -> retried in halves
        if "Sotib olaman" in prompt:
            return [dict(r, i=k) for k, r in enumerate(responses[2:])]
        return responses[:2]

    calls = mock_llm(responder)
    with dbm.SessionLocal() as db:
        stats = extractor.run_once(db)
        assert stats["created"] == 3 and stats["skipped"] == 1 and stats["failed"] == 0
        assert len(calls) == 3
        rows = {p.id: p for p in db.query(RawPost).filter(RawPost.id.in_(ids))}
        assert rows[ids[2]].processed == extractor.SKIPPED
        lst = {x.raw_post_id: x for x in db.query(Listing).filter(Listing.raw_post_id.in_(ids))}
        iphone = lst[ids[0]]
        assert iphone.price_uzs == 5_200_000 and iphone.currency == "UZS"
        assert iphone.attrs == {"storage_gb": 128, "imei_registered": True, "_extracted_by": "gemini"}
        assert iphone.seller_type == "shop" and iphone.source_url == "https://t.me/testphones/1"
        assert lst[ids[1]].currency == "USD" and lst[ids[1]].price_uzs == 255 * 12700
        car = lst[ids[3]]
        assert car.currency == "USD" and car.price_uzs == 9900 * 12700 and car.seller_type == "private"
        assert car.attrs["mileage_km"] == 50000


def test_extractor_failure_falls_through_or_fails(client, mock_llm, monkeypatch):
    """A bad Gemini answer falls through to the rule parser; with no fallback left the post is FAILED."""
    from app.core.config import settings

    with dbm.SessionLocal() as db:
        p = _post(db, "testphones", 50, "iPhone 12 128gb narxi 3.4 mln so'm")
        q = _post(db, "testphones", 51, "iPhone 11 64gb narxi 2.9 mln so'm")
    mock_llm(lambda prompt, n: "not a list")
    with dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, p.id)])
        assert db.get(RawPost, p.id).processed in (extractor.DONE, extractor.SKIPPED)
        assert db.get(RawPost, p.id).processed != extractor.FAILED
    monkeypatch.setattr(settings, "EXTRACT_PROVIDER_ORDER", "gemini")
    with dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, q.id)])
        assert db.get(RawPost, q.id).processed == extractor.FAILED


def test_repost_and_deal_alert(client, mock_llm):
    with dbm.SessionLocal() as db:
        db.add(Source(title="Other", username="otherphones", category_hint="phone", seller_type_default="shop"))
        db.commit()
        fair = pricing.estimate(db, "phone", "iPhone 14", "A", attrs={"storage_gb": 128}).fair_price_uzs
        cheap = round(fair * 0.75 / 12700)
        a = _post(db, "testphones", 100, f"iPhone 14 128gb A holat ${cheap} srochno")
        b = _post(db, "otherphones", 7, f"Srochno! iPhone 14 128gb ${cheap} ideal")
        ids = (a.id, b.id)
    item = {"skip": False, "category": "phone", "brand": "Apple", "model": "iPhone 14", "condition": "A",
            "price": cheap, "currency": "USD", "attrs": {"storage_gb": 128}}
    mock_llm(lambda prompt, n: [dict(item, i=i) for i in range(prompt.count('"text"'))])
    with dbm.SessionLocal() as db:
        extractor.run_once(db)
        la, lb = (db.query(Listing).filter(Listing.raw_post_id == i).one() for i in ids)
        assert not la.is_duplicate and lb.is_duplicate
        assert la.discount_pct >= 20
        alert = db.query(Alert).filter(Alert.type == "sourcing_deal").order_by(Alert.id.desc()).first()
        assert alert.payload["listing_id"] == la.id and alert.company_id is None


def test_outlier_rejected(client, mock_llm):
    with dbm.SessionLocal() as db:
        p = _post(db, "testphones", 200, "iPhone 14 128gb A $5 ideal holat")
    mock_llm(lambda prompt, n: [{"i": 0, "skip": False, "category": "phone", "brand": "Apple", "model": "iPhone 14",
                                 "condition": "A", "price": 5, "currency": "USD", "attrs": {"storage_gb": 128}}])
    with dbm.SessionLocal() as db:
        extractor.run_once(db)
        post = db.get(RawPost, p.id)
        assert post.processed == extractor.SKIPPED and post.error == "price_outlier"


def test_rule_fallback_without_llm(client):
    with dbm.SessionLocal() as db:
        p = _post(db, "testcars", 300, "Gentra 2020 probeg 70 000 km, metan, narxi 12 300$")
        stats = extractor.run_once(db)
        assert stats["created"] >= 1
        lst = db.query(Listing).filter(Listing.raw_post_id == p.id).one()
        assert lst.model == "Gentra" and lst.price_usd == 12300 and lst.attrs["year"] == 2020


def test_idempotent_save(client):
    with dbm.SessionLocal() as db:
        assert save_post(db, "testphones", 999, utcnow(), "Redmi Note 12 narxi 1.9 mln so'm") is not None
        assert save_post(db, "testphones", 999, utcnow(), "Redmi Note 12 narxi 1.9 mln so'm") is None


def test_admin_endpoints(client, admin):
    r = client.post("/api/v1/admin/sources", headers=admin,
                    json={"title": "New Shop", "username": "@newshop_uz", "category_hint": "mixed_tech"})
    assert r.status_code == 201 and r.json()["username"] == "newshop_uz"
    dup = client.post("/api/v1/admin/sources", headers=admin,
                      json={"title": "Again", "username": "newshop_uz", "category_hint": "phone"})
    assert dup.status_code == 409
    sid = r.json()["id"]
    assert client.patch(f"/api/v1/admin/sources/{sid}", headers=admin, json={"active": False}).json()["active"] is False
    assert any(s["username"] == "newshop_uz" for s in client.get("/api/v1/admin/sources", headers=admin).json())
    raw = client.get("/api/v1/admin/raw-posts?processed=3", headers=admin).json()
    assert raw["total"] >= 1 and all(p["processed"] == 3 for p in raw["items"])
    assert client.post("/api/v1/admin/extract/run", headers=admin).json()["processed"] >= 0
    hist = client.post("/api/v1/admin/telegram/history", headers=admin)
    assert hist.status_code == 503
    st = client.get("/api/v1/admin/status", headers=admin).json()
    assert st["listings"] >= 2000 and st["workers"]["telegram"]["status"] == "disabled"


def test_sse_filtering():
    ev = Event("listing.created", {}, None, "car")
    assert visible(ev, 1, {"car"}) and not visible(ev, 1, {"phone"})
    own = Event("alert.created", {}, 5, None)
    assert visible(own, 5, {"phone"}) and not visible(own, 6, {"phone"})
    bus.publish("listing.created", {"x": 1}, category="phone")  # no loop bound in tests: must not raise
    a, b = bus.subscribe(), bus.subscribe()  # subscribers must be hashable and distinct
    assert bus.subscriber_count >= 2
    bus.unsubscribe(a)
    bus.unsubscribe(b)


def test_sse_requires_auth(client):
    assert client.get("/api/v1/market/stream").status_code == 401
    assert client.get("/api/v1/alerts/stream").status_code == 401
