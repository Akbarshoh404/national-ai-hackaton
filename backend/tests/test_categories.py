"""ACTIVE_CATEGORIES: the app shows only phones and laptops; car / apartment data is kept but hidden."""

import pytest

from app.core import db as dbmod
from app.core.config import settings
from app.core.models import Listing
from app.intelligence.advisor import copilot


@pytest.fixture
def phones_and_laptops(monkeypatch):
    monkeypatch.setattr(settings, "ACTIVE_CATEGORIES", "phone,laptop")


def _cats(rows) -> set[str]:
    return {r["category"] for r in rows if r.get("category")}


def test_api_hides_inactive_categories(client, chilonzor, phones_and_laptops):
    meta = client.get("/api/v1/meta").json()
    assert [c["code"] for c in meta["categories"]] == ["phone", "laptop"]
    offers = client.get("/api/v1/exchange/offers", headers=chilonzor).json()
    items = offers["items"] if isinstance(offers, dict) else offers
    assert _cats(items) <= {"phone", "laptop"}


def test_workers_still_see_every_category(client, phones_and_laptops):
    """Sessions outside the API (Telegram, extractor) are not filtered, so nothing is lost or duplicated."""
    with dbmod.SessionLocal() as s:
        worker_cats = {c for (c,) in s.query(Listing.category).distinct()}
    scoped = dbmod.SessionLocal()
    scoped.info[dbmod.CATEGORY_SCOPE] = True
    try:
        api_cats = {c for (c,) in scoped.query(Listing.category).distinct()}
    finally:
        scoped.close()
    assert api_cats <= {"phone", "laptop"}
    assert worker_cats - api_cats, "seed has car / realty listings that the workers must still see"


@pytest.mark.parametrize("question", ["nexia narxi qancha", "Chilonzorda 2 xonali kvartira ijarasi",
                                      "сколько стоит машина"])
def test_copilot_declines_cars_and_apartments(client, chilonzor, phones_and_laptops, question):
    d = client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": question}).json()
    assert d["intent"] == "unsupported"
    assert not d["blocks"]


def test_copilot_unsupported_off_when_all_categories(monkeypatch):
    monkeypatch.setattr(settings, "ACTIVE_CATEGORIES", "")
    assert copilot.route("nexia narxi", None)[0] == "price"


def test_api_hides_junk_prices(client, phones_and_laptops):
    """A "$1 MacBook" listing (extraction error) never reaches the app."""
    from datetime import timedelta

    from app.core.db import utcnow
    with dbmod.SessionLocal() as s:
        s.add(Listing(category="laptop", brand="Apple", model="MacBook Pro", model_norm="macbook pro",
                      condition="new", price=1, currency="USD", price_uzs=12_700, price_usd=1, city="Toshkent",
                      attrs={}, seller_type="private", posted_at=utcnow() - timedelta(hours=1), origin="telegram"))
        s.commit()
    scoped = dbmod.SessionLocal()
    scoped.info[dbmod.CATEGORY_SCOPE] = True
    try:
        assert scoped.query(Listing).filter(Listing.price_uzs < 300_000).count() == 0
    finally:
        scoped.close()
