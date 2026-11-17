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

    v2(ch, to, sa, yr)

    bad = [r for r in results if r[0] != "OK "]
    for status, name, code, ms in results:
        print(f"{status} {code} {ms:7.0f} ms  {name}")
    print(f"\n{len(results) - len(bad)}/{len(results)} OK")
    sys.exit(1 if bad else 0)


def v2(ch: dict, to: dict, sa: dict, yr: dict) -> None:
    """Every v2 endpoint once with the demo keys."""
    mgr, appr = {"X-API-Key": "demo-chilonzor-manager"}, {"X-API-Key": "demo-chilonzor-appraiser"}
    bank, bozor = {"X-API-Key": "demo-demo-bank"}, {"X-API-Key": "demo-bozor-admin"}
    call("POST", "/auth/demo-login", json={"company_slug": "demo-bank"})
    call("GET", "/meta", ch)

    # platform
    stores = call("GET", "/stores", ch).json()["items"]
    st = call("POST", "/stores", ch, expect=201, json={"name": "Smoke nuqta", "district": "Sergeli"}).json()
    call("PATCH", f"/stores/{st['id']}", ch, json={"active": False})
    u = call("POST", "/users", sa, expect=201, json={"name": "Smoke user", "role": "manager"}).json()
    call("GET", "/users", sa)
    call("DELETE", f"/users/{u['user']['id']}", sa)
    call("GET", "/activity?limit=5", ch)
    call("GET", "/users", mgr, expect=403)
    call("GET", "/books/audit", appr, expect=403)

    # stock command center
    call("GET", f"/stock/units?limit=100&store_id={stores[0]['id']}", ch)
    units = call("GET", "/stock/units?rating=overpriced", appr).json()["items"]
    call("GET", "/stock/summary", ch)
    if units:
        call("POST", "/stock/reprice", ch, json={"inventory_ids": [units[0]["inventory_id"]], "use_suggested": True})
    aging = call("GET", "/stock/units?aging_only=true", ch).json()["items"]
    if aging:
        call("POST", "/stock/list-on-exchange", ch, expect=201, json={"inventory_ids": [aging[0]["inventory_id"]]})
    for fmt in ("xlsx", "csv", "1c"):
        call("GET", f"/stock/export?format={fmt}", ch)
        call("GET", f"/books/transactions/export?format={fmt}", ch)

    # decisions
    cards = call("GET", "/decisions?refresh=true", ch).json()["items"]
    by_type = {c["type"]: c for c in cards}
    if "typo_amount" in by_type:
        call("POST", f"/decisions/{by_type['typo_amount']['id']}/approve", ch)
        call("POST", f"/decisions/{by_type['typo_amount']['id']}/approve", ch, expect=409)
    if "rfq_quote" in by_type:
        call("POST", f"/decisions/{by_type['rfq_quote']['id']}/ignore", ch)
    call("GET", "/dashboard", ch)

    # copilot + credit
    call("POST", "/advisor/chat", ch, json={"question": "Nega bu qimmat?",
                                            "context": {"screen": "stock",
                                                        "inventory_ids": [x["inventory_id"] for x in units[:2]]}})
    call("POST", "/advisor/chat", ch, json={"question": "100 mln kredit 24 oyga"})
    call("POST", "/advisor/credit", yr, json={"product": "mortgage", "months": 180, "asset_value_uzs": 900_000_000})
    call("GET", "/advisor/business-plan?loan_amount_uzs=100000000&loan_months=24", ch)

    # fast inputs
    call("POST", "/input/parse", ch, json={"text": "cobalt 2021 45 ming probeg pozitsiya 4"})
    call("POST", "/input/imei", ch, json={"imei": "353409131234565"})
    call("POST", "/input/voice", ch, expect=(200, 503), files={"file": ("v.ogg", b"OggS", "audio/ogg")})
    csv = "Sana;Modda;Jami summa\n2026-11-05;svet;900000\n"
    call("POST", "/books/upload/preview", ch, files={"file": ("b.csv", csv.encode(), "text/csv")})
    call("POST", "/market/price-from-link", ch, expect=(200, 404), json={"url": "https://t.me/mixmobiles/1"})

    # exchange additions
    rfq = call("POST", "/exchange/rfqs", ch, expect=201, json={
        "category": "phone", "model": "iPhone 14", "condition": "A", "attrs": {"storage_gb": 128}, "qty": 2}).json()
    q = call("POST", f"/exchange/rfqs/{rfq['rfq']['id']}/quotes", to, expect=201,
             json={"unit_price": 5_900_000, "qty": 2, "delivery_days": 2}).json()
    call("POST", f"/exchange/quotes/{q['id']}/counter", ch, json={"unit_price": 5_600_000})
    call("POST", f"/exchange/quotes/{q['id']}/respond", to, json={"accept": True})
    deal = call("POST", f"/exchange/quotes/{q['id']}/accept", ch).json()
    call("GET", f"/exchange/deals/{deal['id']}/document", to)
    call("GET", f"/exchange/deals/{deal['id']}/document?format=pdf", ch)
    call("GET", "/exchange/demand?days=30", to)

    # lender & bazaar console
    lenders = call("GET", "/advisor/lenders", sa).json()
    call("POST", "/advisor/loan-applications", sa, expect=201, json={
        "lender_id": lenders[0]["id"], "product": "auto_loan", "principal_uzs": 150_000_000, "months": 36,
        "purpose": "Avto zaxirasi", "consent": True})
    call("GET", "/advisor/loan-applications", sa)
    call("POST", "/lender/valuations", bank, json={"category": "car", "model": "Gentra",
                                                   "attrs": {"year": 2020, "mileage_km": 70000}})
    call("GET", "/lender/collateral", bank)
    call("POST", "/lender/collateral", bank, expect=201, json={
        "borrower_name": "Smoke IP", "category": "car", "model": "Spark", "attrs": {"year": 2019},
        "loan_balance_uzs": 40_000_000})
    call("GET", "/lender/collateral/summary", bank)
    apps = call("GET", "/lender/applications", bank).json()["items"]
    call("GET", f"/lender/applications/{apps[0]['id']}", bank)
    call("GET", f"/lender/applications/{apps[0]['id']}/business-plan", bank)
    call("POST", f"/lender/applications/{apps[0]['id']}/decision", bank, expect=(200, 409),
         json={"status": "reviewing"})
    call("GET", "/partner/market-report?category=phone", bozor)
    call("GET", "/partner/market-report?category=car&format=xlsx", bank)
    call("GET", "/lender/collateral", ch, expect=403)

    # integrations
    call("GET", "/integrations", ch)
    call("POST", "/integrations/didox/sync", ch)
    call("POST", "/integrations/bank/sync", sa)


if __name__ == "__main__":
    main()
