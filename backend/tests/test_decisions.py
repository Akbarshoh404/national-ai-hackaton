"""v2 phase 3: decisions queue built from the seed; approve exactly once; dashboard additions."""

import pytest

from app.intelligence.books.decisions import TYPES

ALL = set(TYPES)


@pytest.fixture(scope="module")
def cards(client, chilonzor, fresh_seed):
    r = client.get("/api/v1/decisions?refresh=true", headers={**chilonzor, "Accept-Language": "en"})
    assert r.status_code == 200, r.text
    return {c["type"]: c for c in r.json()["items"]}


def test_every_type_generated(cards):
    assert set(cards) == ALL, f"missing: {ALL - set(cards)}"
    assert len(cards) <= 8
    for c in cards.values():
        assert c["status"] == "pending" and c["amount_uzs"] >= 0 and c["title"] and c["action"]["kind"]
    assert cards["reprice"]["title"].startswith("14 units")
    assert len(cards["slow_stock"]["inventory_ids"]) == 8
    assert cards["typo_amount"]["amount_uzs"] == 3_150_000


def test_idempotent_build(client, chilonzor, cards):
    again = client.get("/api/v1/decisions?refresh=true", headers=chilonzor).json()
    assert {c["id"] for c in again["items"]} == {c["id"] for c in cards.values()}


def test_duplicate_invoice_approve_once(client, chilonzor, cards):
    card = cards["duplicate_invoice"]
    extra = card["action"]["body"]["delete_ids"]
    r = client.post(f"/api/v1/decisions/{card['id']}/approve", headers=chilonzor)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["deleted_transaction_ids"] == extra
    assert client.post(f"/api/v1/decisions/{card['id']}/approve", headers=chilonzor).status_code == 409
    txs = client.get("/api/v1/books/transactions?category=electricity&limit=500", headers=chilonzor).json()["items"]
    assert not any(t["id"] in extra for t in txs)
    audit = client.get("/api/v1/books/audit", headers=chilonzor).json()
    assert not any(f["type"] == "duplicate" for f in audit["flags"])


def test_typo_and_reprice_and_slow(client, chilonzor, cards):
    typo = cards["typo_amount"]
    r = client.post(f"/api/v1/decisions/{typo['id']}/approve", headers=chilonzor).json()
    assert r["result"]["new_total_uzs"] == 350_000
    rep = client.post(f"/api/v1/decisions/{cards['reprice']['id']}/approve", headers=chilonzor).json()
    assert len(rep["result"]["updated_ids"]) >= 12
    assert client.get("/api/v1/stock/summary", headers=chilonzor).json()["units_overpriced"] == 0
    slow = client.post(f"/api/v1/decisions/{cards['slow_stock']['id']}/approve", headers=chilonzor).json()
    assert slow["result"]["offer_ids"]


def test_other_types_and_ignore(client, chilonzor, cards):
    over = client.post(f"/api/v1/decisions/{cards['overpayment']['id']}/approve", headers=chilonzor).json()
    assert over["result"]["alert_id"]
    deal = client.post(f"/api/v1/decisions/{cards['deal_to_buy']['id']}/approve", headers=chilonzor).json()
    assert deal["result"]["watching_listing_id"]
    ign = client.post(f"/api/v1/decisions/{cards['budget_limit']['id']}/ignore", headers=chilonzor)
    assert ign.status_code == 200 and ign.json()["status"] == "ignored"
    assert client.post(f"/api/v1/decisions/{cards['budget_limit']['id']}/approve", headers=chilonzor).status_code == 409
    done = client.get("/api/v1/decisions?status=approved", headers=chilonzor).json()
    assert done["total"] >= 5
    acts = client.get("/api/v1/activity?entity=decision", headers=chilonzor).json()
    assert acts["total"] >= 6


def test_dashboard_has_decisions_and_stock(client, sergeli, fresh_seed):
    d = client.get("/api/v1/dashboard", headers=sergeli).json()
    assert "decisions" in d and len(d["decisions"]) <= 5 and d["stock"]["units_total"] >= 0
