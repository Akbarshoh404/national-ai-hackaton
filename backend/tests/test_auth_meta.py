"""Phase 1: auth, error format, /meta and /health."""


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"]["status"] == "ok"
    assert body["llm"]["status"] == "not_configured"


def test_register_and_me(client):
    r = client.post("/api/v1/auth/register", json={
        "name": "Test Shop", "stir": "123456789", "role": "retailer", "categories": ["phone"],
        "district": "chilanzar"})
    assert r.status_code == 201, r.text
    key = r.json()["api_key"]
    assert r.json()["company"]["district"] == "Chilonzor"
    me = client.get("/api/v1/companies/me", headers={"X-API-Key": key})
    assert me.status_code == 200 and me.json()["name"] == "Test Shop"
    dup = client.post("/api/v1/auth/register", json={
        "name": "Again", "stir": "123456789", "role": "retailer", "categories": ["phone"]})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "stir_taken"
    patched = client.patch("/api/v1/companies/me", headers={"X-API-Key": key}, json={"categories": ["phone", "laptop"]})
    assert patched.json()["categories"] == ["phone", "laptop"]


def test_validation_error_format(client):
    r = client.post("/api/v1/auth/register", json={"name": "X", "stir": "12", "role": "retailer",
                                                  "categories": ["phone"]})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and err["details"]["errors"]


def test_auth_errors(client):
    r = client.get("/api/v1/companies/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "missing_api_key"
    r = client.get("/api/v1/companies/me", headers={"X-API-Key": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"


def test_admin_errors(client):
    r = client.get("/api/v1/admin/status")
    assert r.status_code == 401
    r = client.get("/api/v1/admin/status", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "invalid_admin_key"


def test_meta_shape(client):
    r = client.get("/api/v1/meta", headers={"Accept-Language": "ru"})
    assert r.status_code == 200
    m = r.json()
    assert {c["code"] for c in m["categories"]} == {"phone", "laptop", "car", "house", "rent"}
    assert [c["code"] for c in m["conditions"]["phone"]] == ["new", "A", "B", "C"]
    assert any(f["name"] == "mileage_km" and f["unit"] == "km" for f in m["attributes"]["car"])
    assert len(m["districts"]) == 12
    assert "stock_purchase" in [c["code"] for c in m["expense_categories"]]
    assert m["fx_usd_uzs"] == 12700


def test_openapi_operation_ids(client):
    spec = client.get("/openapi.json").json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    assert "auth_register" in ops and "meta_get" in ops
