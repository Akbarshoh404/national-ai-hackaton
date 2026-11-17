"""Regressions found by the live smoke run."""

from app.catalog import norm_model


def test_norm_model_ignores_nan_brand():
    assert norm_model("iPhone 13", float("nan")) == "iphone 13"
    assert norm_model(float("nan")) == ""


def test_audit_with_brandless_stock_rows(client, sergeli):
    r = client.post("/api/v1/books/transactions", headers=sergeli, json={
        "date": "2026-11-10", "type": "expense", "category": "stock_purchase", "item_category": "car",
        "model": "Spark", "qty": 1, "total": 70_000_000})
    assert r.status_code == 201
    assert client.get("/api/v1/books/audit", headers=sergeli).status_code == 200
