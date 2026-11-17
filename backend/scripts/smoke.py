"""Call every endpoint once against a running server with the demo keys.

Usage: python scripts/smoke.py [http://localhost:8000] [admin-key]
"""

from __future__ import annotations

import sys
import time
from datetime import date

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000") + "/api/v1"
ADMIN = {"X-Admin-Key": sys.argv[2] if len(sys.argv) > 2 else "change-me"}
results: list[tuple[str, str, int, float]] = []


def call(method: str, path: str, headers: dict | None = None, expect: int | tuple = 200, **kw) -> httpx.Response:
    t0 = time.perf_counter()
    r = httpx.request(method, BASE + path, headers=headers or {}, timeout=60, **kw)
    ms = (time.perf_counter() - t0) * 1000
    ok = r.status_code in (expect if isinstance(expect, tuple) else (expect,))
    results.append(("OK " if ok else "BAD", f"{method} {path}", r.status_code, ms))
    if not ok:
        print(f"!! {method} {path} -> {r.status_code}: {r.text[:300]}")
    return r


def key(slug: str) -> dict[str, str]:
    r = call("POST", "/auth/demo-login", json={"company_slug": slug})
    return {"X-API-Key": r.json()["api_key"]}


def main() -> None:
    call("GET", "/health")
    call("GET", "/meta")
    ch, to, sa, yr = (key(s) for s in ("chilonzor-phone", "techopt", "sergeli-avto", "yunusobod-realty"))
    stir = str(int(time.time()))[-9:]
    new = call("POST", "/auth/register", expect=201, json={"name": "Smoke Shop", "stir": stir, "role": "retailer",
                                                           "categories": ["phone"]}).json()
    nk = {"X-API-Key": new["api_key"]}
    call("GET", "/companies/me", ch)
    call("PATCH", "/companies/me", nk, json={"district": "Olmazor"})
    comps = call("GET", "/companies?role=supplier", ch).json()
    call("GET", f"/companies/{comps['items'][0]['id']}", ch)
    call("GET", "/dashboard", ch)

    # market
    call("GET", "/market/listings?category=phone&limit=5", ch)
    call("GET", "/market/stats", ch)
    call("POST", "/market/price", ch, json={"category": "phone", "model": "iPhone 13", "condition": "A",
                                            "attrs": {"storage_gb": 128}, "asking_price_uzs": 4_500_000})
    call("POST", "/market/price", sa, json={"category": "car", "model": "Gentra",
                                            "attrs": {"year": 2020, "mileage_km": 70000, "fuel": "metan"}})
    call("GET", "/market/sourcing-radar", ch)
    call("GET", "/market/trend?category=phone&model=iPhone%2013", ch)
    call("GET", "/market/models?category=laptop&q=mac", ch)
    call("POST", "/market/rental-yield", yr, json={"district": "Yunusobod", "rooms": 2, "area_m2": 60})
    call("GET", "/market/heatmap?category=rent", yr)
    with httpx.stream("GET", BASE + "/market/stream", headers=ch, timeout=10) as s:
        first = next(s.iter_text())
        results.append(("OK " if "connected" in first else "BAD", "GET /market/stream", s.status_code, 0))
    with httpx.stream("GET", BASE + "/alerts/stream", headers=ch, timeout=10) as s:
        first = next(s.iter_text())
        results.append(("OK " if "connected" in first else "BAD", "GET /alerts/stream", s.status_code, 0))

    # books
    call("GET", "/books/upload/template")
    csv = "sana,kategoriya,summa,kontragent\n2026-11-02,internet,350000,Uzonline\n"
    call("POST", "/books/upload", nk, files={"file": ("b.csv", csv.encode(), "text/csv")})
    call("POST", "/books/invoice", nk, expect=(200, 503), files={"file": ("i.jpg", b"\xff\xd8", "image/jpeg")})
    tx = call("POST", "/books/transactions", nk, expect=201, json={"date": date.today().isoformat(),
                                                                   "type": "expense", "category": "ads",
                                                                   "total": 500000, "counterparty": "IG"}).json()
    call("GET", "/books/transactions?limit=5", ch)
    call("DELETE", f"/books/transactions/{tx['id']}", nk)
    call("GET", "/books/audit", ch)
    call("GET", "/books/benchmark", ch)
    month = date.today().strftime("%Y-%m")
    call("PUT", "/books/budget", nk, json={"month": month, "items": {"ads": 400000}})
    call("GET", "/books/budget", ch)
    call("GET", "/books/inventory", ch)
    call("POST", "/books/inventory", nk, expect=201, json={"category": "phone", "model": "iPhone 12",
                                                           "condition": "B", "attrs": {"storage_gb": 128},
                                                           "qty": 2, "unit_cost": 3_000_000})
    call("GET", "/books/slow-stock", ch)
    call("GET", "/books/stock-revaluation", ch)

    # exchange
    rfq = call("POST", "/exchange/rfqs", ch, expect=201, json={
        "category": "phone", "brand": "Apple", "model": "iPhone 15", "condition": "new",
        "attrs": {"storage_gb": 128}, "qty": 3, "target_unit_price": 7_500_000}).json()["rfq"]
    call("GET", "/exchange/rfqs?scope=mine", ch)
    call("GET", "/exchange/rfqs?scope=incoming", to)
    call("GET", f"/exchange/rfqs/{rfq['id']}", to)
    q = call("POST", f"/exchange/rfqs/{rfq['id']}/quotes", to, expect=201,
             json={"unit_price": 7_400_000, "qty": 3, "delivery_days": 2}).json()
    call("GET", f"/exchange/rfqs/{rfq['id']}/quotes", ch)
    call("GET", f"/exchange/rfqs/{rfq['id']}/matches", ch)
    deal = call("POST", f"/exchange/quotes/{q['id']}/accept", ch).json()
    offer = call("POST", "/exchange/offers", ch, expect=201, json={
        "kind": "surplus", "category": "phone", "brand": "Samsung", "model": "Galaxy A54", "condition": "new",
        "attrs": {"storage_gb": 128}, "qty": 3, "unit_price": 3_000_000}).json()
    offers = call("GET", "/exchange/offers?kind=wholesale", ch).json()
    call("POST", f"/exchange/offers/{offers['items'][0]['id']}/buy", ch, json={"qty": 1})
    call("DELETE", f"/exchange/offers/{offer['id']}", ch)
    call("GET", "/exchange/deals", ch)
    call("POST", f"/exchange/deals/{deal['id']}/rate", ch, expect=201, json={"score": 5})
    call("GET", "/exchange/demand", to)

    # advisor
    call("POST", "/advisor/chat", ch, json={"question": "Qancha kredit olsam bo'ladi?"})
    call("GET", "/advisor/cashflow", ch)
    call("POST", "/advisor/credit", ch, json={"principal_uzs": 100_000_000, "months": 24})
    call("GET", "/advisor/tax", ch)
    call("GET", "/advisor/loan-readiness", ch)
    call("POST", "/advisor/expansion", ch, json={"category": "laptop", "budget_uzs": 400_000_000})
    call("POST", "/advisor/expansion", yr, json={"category": "rent", "budget_uzs": 900_000_000})
    for fmt in ("html", "pdf", "json"):
        call("POST", "/advisor/business-plan", ch, json={"loan_amount_uzs": 150_000_000, "loan_months": 24,
                                                         "purpose": "Yangi filial", "format": fmt})

    # alerts
    al = call("GET", "/alerts?unread_only=true", ch).json()
    if al["items"]:
        call("POST", f"/alerts/{al['items'][0]['id']}/read", ch)
    call("POST", "/alerts/read-all", ch)

    # admin
    call("GET", "/admin/status", ADMIN)
    src = call("GET", "/admin/sources", ADMIN).json()
    s = call("POST", "/admin/sources", ADMIN, expect=(201, 409), json={"title": "Smoke", "username": "smoke_src_x",
                                                                      "category_hint": "phone"})
    sid = s.json()["id"] if s.status_code == 201 else (src[0]["id"] if src else None)
    if sid:
        call("PATCH", f"/admin/sources/{sid}", ADMIN, json={"active": False})
    call("POST", "/admin/telegram/history", ADMIN, expect=(202, 503))
    call("POST", "/admin/extract/run", ADMIN)
    call("GET", "/admin/raw-posts", ADMIN)
    call("POST", "/admin/fx/refresh", ADMIN)
    call("GET", "/admin/fx/refresh", ADMIN)

    bad = [r for r in results if r[0] != "OK "]
    for status, name, code, ms in results:
        print(f"{status} {code} {ms:7.0f} ms  {name}")
    print(f"\n{len(results) - len(bad)}/{len(results)} OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
