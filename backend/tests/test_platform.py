"""v2 phase 1: roles and permissions, stores, users, activity log, /meta additions."""

MANAGER = {"X-API-Key": "demo-chilonzor-manager"}
APPRAISER = {"X-API-Key": "demo-chilonzor-appraiser"}
BANK = {"X-API-Key": "demo-demo-bank"}
BOZOR = {"X-API-Key": "demo-bozor-admin"}


def test_user_keys_resolve_to_company(client):
    me = client.get("/api/v1/companies/me", headers=MANAGER).json()
    assert me["name"] == "Chilonzor Phone Market" and me["my_role"] == "manager" and me["plan"] == "pro"


def test_appraiser_read_only(client):
    assert client.get("/api/v1/market/listings?limit=1", headers=APPRAISER).status_code == 200
    assert client.post("/api/v1/market/price", headers=APPRAISER, json={
        "category": "phone", "model": "iPhone 13", "condition": "A", "attrs": {"storage_gb": 128}}).status_code == 200
    assert client.get("/api/v1/books/inventory", headers=APPRAISER).status_code == 200
    r = client.post("/api/v1/books/transactions", headers=APPRAISER,
                    json={"date": "2026-11-01", "type": "expense", "category": "ads", "total": 1000})
    assert r.status_code == 403 and r.json()["error"]["code"] == "role_forbidden"
    assert client.get("/api/v1/books/audit", headers=APPRAISER).status_code == 403
    assert client.post("/api/v1/exchange/offers", headers=APPRAISER, json={}).status_code == 403


def test_manager_limits(client):
    assert client.get("/api/v1/books/audit", headers=MANAGER).status_code == 200
    assert client.patch("/api/v1/companies/me", headers=MANAGER, json={"name": "X"}).status_code == 403
    assert client.get("/api/v1/users", headers=MANAGER).status_code == 403


def test_partner_accounts_blocked_from_books(client):
    assert client.get("/api/v1/books/transactions", headers=BANK).status_code == 403
    assert client.get("/api/v1/books/audit", headers=BOZOR).status_code == 403
    assert client.get("/api/v1/market/stats", headers=BANK).status_code == 200


def test_users_crud(client, sergeli):
    r = client.post("/api/v1/users", headers=sergeli, json={"name": "Bobur", "role": "appraiser"})
    assert r.status_code == 201
    key, uid = r.json()["api_key"], r.json()["user"]["id"]
    assert client.get("/api/v1/companies/me", headers={"X-API-Key": key}).json()["my_role"] == "appraiser"
    users = client.get("/api/v1/users", headers=sergeli).json()
    assert any(u["id"] == uid for u in users["items"])
    assert client.delete(f"/api/v1/users/{uid}", headers=sergeli).status_code == 200
    assert client.get("/api/v1/companies/me", headers={"X-API-Key": key}).status_code == 401


def test_stores_and_meta(client, chilonzor):
    stores = client.get("/api/v1/stores", headers=chilonzor).json()
    assert stores["total"] == 2
    new = client.post("/api/v1/stores", headers=chilonzor, json={"name": "Sergeli nuqtasi", "district": "sergeli"})
    assert new.status_code == 201 and new.json()["district"] == "Sergeli"
    sid = new.json()["id"]
    assert client.patch(f"/api/v1/stores/{sid}", headers=chilonzor, json={"active": False}).json()["active"] is False
    meta = client.get("/api/v1/meta", headers=chilonzor).json()
    assert len(meta["stores"]) == 3 and {p["code"] for p in meta["plans"]} == {"start", "pro", "business"}
    assert {c["code"] for c in meta["credit_products"]} == {"business_loan", "auto_loan", "mortgage", "leasing"}
    assert "loan_schedule" in meta["block_types"] and len(meta["decision_types"]) == 8
    assert {r["code"] for r in meta["user_roles"]} == {"owner", "manager", "appraiser", "lender_officer"}
    assert client.get("/api/v1/meta").json()["stores"] == []


def test_register_creates_default_store_and_partner(client):
    r = client.post("/api/v1/auth/register", json={"name": "Test Bank", "stir": "555555555", "role": "lender"})
    assert r.status_code == 201
    key = {"X-API-Key": r.json()["api_key"]}
    assert client.get("/api/v1/stores", headers=key).json()["total"] == 1
    bad = client.post("/api/v1/auth/register", json={"name": "No cats", "stir": "555555556", "role": "retailer"})
    assert bad.status_code == 422


def test_activity_log(client, chilonzor):
    client.put("/api/v1/books/budget", headers=chilonzor, json={"month": "2026-12", "items": {"ads": 1_000_000}})
    acts = client.get("/api/v1/activity?entity=budget", headers=chilonzor).json()
    assert acts["total"] >= 1 and "2026-12" in acts["items"][0]["summary"]
    client.post("/api/v1/books/transactions", headers=MANAGER,
                json={"date": "2026-11-01", "type": "expense", "category": "documents", "total": 50000})
    tx = client.get("/api/v1/activity?entity=transaction", headers=chilonzor).json()["items"][0]
    assert tx["user_name"] == "Dilshod (menejer)"
