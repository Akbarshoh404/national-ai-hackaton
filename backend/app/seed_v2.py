"""v2 demo data: stores, users, partner accounts, integrations, the 80-unit stock center.

!!! SYNTHETIC DEMO DATA. TACs in data/tac.csv are made up (demo only). !!!
Called at the end of `seed.run`.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.catalog import INTEGRATION_KINDS
from app.core.deps import hash_key
from app.core.models import Company, InventoryItem, Store, User
from app.intelligence.market import pricing
from app.intelligence.market.imei import load_tac, make_imei

PARTNERS = {
    # slug: (name, stir, role, categories, district)
    "demo-bank": ("Demo Lizing Bank", "307890123", "lender", [], "Mirobod"),
    "bozor-admin": ("Malika Bozori Ma'muriyati", "308901234", "market_admin", [], "Olmazor"),
}
DEMO_USERS = [("chilonzor-phone", "chilonzor-manager", "Dilshod (menejer)", "manager"),
              ("chilonzor-phone", "chilonzor-appraiser", "Aziza (baholovchi)", "appraiser")]

# (brand, model, condition, attrs, count) per stock group
FAIR_UNITS = [
    ("Apple", "iPhone 13", "A", {"storage_gb": 128}, 8), ("Apple", "iPhone 14", "A", {"storage_gb": 128}, 6),
    ("Apple", "iPhone 15", "new", {"storage_gb": 128}, 5), ("Apple", "iPhone 12", "B", {"storage_gb": 128}, 5),
    ("Apple", "iPhone 11", "B", {"storage_gb": 64}, 4), ("Samsung", "Galaxy A54", "new", {"storage_gb": 128}, 5),
    ("Samsung", "Galaxy S23", "A", {"storage_gb": 256}, 3),
    ("Xiaomi", "Redmi Note 13", "new", {"storage_gb": 256, "ram_gb": 8}, 4),
    ("Xiaomi", "Poco X6 Pro", "new", {"storage_gb": 256}, 3),
    ("Apple", "MacBook Air M1", "A", {"ram_gb": 8, "ssd_gb": 256}, 3),
    ("Apple", "MacBook Air M2", "new", {"ram_gb": 8, "ssd_gb": 256}, 2),
    ("ASUS", "TUF F15", "new", {"ram_gb": 16, "ssd_gb": 512}, 2),
]
OVERPRICED_UNITS = [
    ("Apple", "iPhone 13", "A", {"storage_gb": 128}, 3), ("Apple", "iPhone 14", "A", {"storage_gb": 128}, 3),
    ("Apple", "iPhone 15", "new", {"storage_gb": 128}, 2), ("Samsung", "Galaxy S23", "A", {"storage_gb": 256}, 2),
    ("Xiaomi", "Redmi Note 13", "new", {"storage_gb": 256, "ram_gb": 8}, 2),
    ("Apple", "MacBook Air M1", "A", {"ram_gb": 8, "ssd_gb": 256}, 2),
]
UNDERPRICED_UNITS = [("Apple", "iPhone 12", "B", {"storage_gb": 128}, 1),
                     ("Samsung", "Galaxy A54", "new", {"storage_gb": 128}, 1)]
AGING_UNITS = [  # 31–55 days old
    ("Apple", "iPhone 11", "B", {"storage_gb": 64}, 2), ("Samsung", "Galaxy A54", "new", {"storage_gb": 128}, 2),
    ("Lenovo", "IdeaPad 3", "new", {"ram_gb": 8, "ssd_gb": 256}, 1),
    ("Dell", "Latitude 5420", "A", {"ram_gb": 8, "ssd_gb": 256}, 1),
]
SLOW_UNITS = [  # > SLOW_STOCK_DAYS (the 8 units of v1), with their age in days
    ("Samsung", "Galaxy A54", "new", {"storage_gb": 128}, 3, 80),
    ("Xiaomi", "Redmi Note 12", "new", {"storage_gb": 128}, 2, 90),
    ("HP", "Pavilion 15", "new", {"ram_gb": 8, "ssd_gb": 512}, 2, 85),
    ("Lenovo", "IdeaPad 3", "new", {"ram_gb": 8, "ssd_gb": 256}, 1, 100),
]
LAPTOPS = {"MacBook Air M1", "MacBook Air M2", "TUF F15", "IdeaPad 3", "Latitude 5420", "Pavilion 15"}


def run(db: Session, companies: dict[str, Company], today: date) -> dict[str, int]:
    from app.api.routers.auth import demo_key
    from app.seed import _company

    rng = random.Random(23)
    ch = companies["chilonzor-phone"]
    for slug, spec in PARTNERS.items():
        companies[slug] = _company(db, slug, *spec)
    db.flush()

    # stores: Chilonzor has two
    main = db.scalar(select(Store).where(Store.company_id == ch.id))
    main.name = "Chilonzor (asosiy)"
    second = Store(company_id=ch.id, name="Yunusobod filiali", district="Yunusobod", area_m2=45)
    db.add(second)
    db.flush()
    stores = [main.id, second.id]

    for slug, key, name, role in DEMO_USERS:
        db.add(User(company_id=companies[slug].id, name=name, role=role, api_key=hash_key(demo_key(key))))

    # integrations: rows for every company; Chilonzor's Didox is connected (mock)
    from app.channels.integrations import ensure_rows

    for c in db.scalars(select(Company)):
        ensure_rows(db, c)
    db.flush()
    from app.core.models import Integration

    didox = db.scalar(select(Integration).where(Integration.company_id == ch.id, Integration.kind == "didox"))
    didox.status = "connected"
    didox.details = {"mode": "mock", "account": "Chilonzor Phone Market (demo)"}

    # an incoming RFQ for Chilonzor from a peer shop (feeds the rfq_quote decision)
    from app.core.models import Rfq

    peer = db.scalar(select(Company).where(Company.name == "Malika Mobile"))
    est = pricing.estimate(db, "phone", "Galaxy A54", "new", attrs={"storage_gb": 128}, brand="Samsung")
    db.add(Rfq(company_id=peer.id, category="phone", brand="Samsung", model="Galaxy A54", condition="new",
               attrs={"storage_gb": 128}, qty=10, target_unit_price=round(est.fair_buy_price_uzs, -3),
               district=peer.district, deadline=today + timedelta(days=4), note="Korobkasi bilan"))

    units = seed_stock(db, ch, stores, today, rng)
    db.flush()
    pricing.invalidate()
    collateral = seed_lender(db, companies["demo-bank"], ch, today)
    return {"stock_units": units, "integrations": len(INTEGRATION_KINDS), "collateral": collateral}


# (borrower, category, brand, model, condition, district, attrs, qty, balance as share of market value)
COLLATERAL = [
    ("Sergeli Avto", "car", "Chevrolet", "Cobalt", "used", None, {"year": 2021, "mileage_km": 50000}, 1, 0.50),
    ("Sergeli Avto", "car", "Chevrolet", "Gentra", "used", None, {"year": 2020, "mileage_km": 70000}, 1, 0.45),
    ("IP Rahimov", "car", "Chevrolet", "Malibu 2", "used", None, {"year": 2022, "mileage_km": 30000}, 1, 0.80),
    ("IP Karimova", "car", "Chevrolet", "Tracker 2", "used", None, {"year": 2022, "mileage_km": 25000}, 1, 0.67),
    ("OOO Yo'l Servis", "car", "Chevrolet", "Damas", "used", None, {"year": 2019, "mileage_km": 90000}, 2, 0.40),
    ("IP Toshmatov", "car", "BYD", "Song Plus", "used", None, {"year": 2023, "mileage_km": 15000}, 1, 0.55),
    ("Yunusobod Realty", "house", None, "3-xonali kvartira", "used", "Yunusobod", {"rooms": 3, "area_m2": 85}, 1,
     0.50),
    ("IP Azimova", "house", None, "2-xonali kvartira", "used", "Chilonzor", {"rooms": 2, "area_m2": 55}, 1, 0.60),
    ("IP Yusupov", "house", None, "2-xonali kvartira", "new", "Mirzo Ulug'bek", {"rooms": 2, "area_m2": 60}, 1,
     0.35),
    ("Chilonzor Phone Market", "phone", "Apple", "iPhone 13", "A", None, {"storage_gb": 128}, 20, 0.45),
]


def seed_lender(db: Session, bank: Company, borrower: Company, today: date) -> int:
    """Demo Lizing Bank: ~10 collateral items (one breach, one watch) and one submitted application."""
    from app.core.models import Collateral
    from app.intelligence.advisor import lender

    app = lender.submit_application(db, borrower, {
        "lender_id": bank.id, "product": "business_loan", "principal_uzs": 150_000_000, "months": 24,
        "purpose": "Aylanma mablag': iPhone zaxirasini to'ldirish", "consent": True,
        "collateral_inventory_ids": [i for i in db.scalars(select(InventoryItem.id).where(
            InventoryItem.company_id == borrower.id, InventoryItem.model == "iPhone 13",
            InventoryItem.status == "in_stock").limit(5))]}, "en")
    for name, cat, brand, model, cond, district, attrs, qty, share in COLLATERAL:
        est = pricing.estimate(db, cat, model, cond, district, attrs, brand=brand)
        db.add(Collateral(lender_id=bank.id, borrower_name=name, category=cat, brand=brand, model=model,
                          condition=cond, district=district, attrs=attrs, qty=qty,
                          loan_balance_uzs=round(est.fair_price_uzs * qty * share, -3), ltv_limit=0.7,
                          loan_application_id=app.id if name == borrower.name else None))
    return len(COLLATERAL)


def seed_stock(db: Session, ch: Company, stores: list[int], today: date, rng: random.Random) -> int:
    """Replace Chilonzor's v1 inventory with 80 single units (14 overpriced, 6 aging, 8 slow)."""
    db.execute(delete(InventoryItem).where(InventoryItem.company_id == ch.id))
    tacs = {(v["brand"], v["model"]): k for k, v in load_tac().items()}
    serial = iter(range(100001, 999999))
    pricing.invalidate()
    n = 0

    def unit(brand: str, model: str, cond: str, attrs: dict[str, Any], age: int, list_mode: str,
             cost_factor: float | None = None, status: str = "in_stock", sold_after: int | None = None) -> None:
        nonlocal n
        cat = "laptop" if model in LAPTOPS else "phone"
        est = pricing.estimate(db, cat, model, cond, attrs=attrs, brand=brand)
        p25, p75 = est.range_uzs
        list_price = {
            "fair": est.fair_price_uzs * rng.uniform(0.995, 1.005),
            "over": p75 * rng.uniform(1.08, 1.15),
            "under": p25 * 0.93,
        }[list_mode]
        cost = est.fair_buy_price_uzs * (cost_factor or rng.uniform(0.97, 1.02))
        tac = tacs.get((brand, model))
        acquired = today - timedelta(days=age)
        db.add(InventoryItem(
            company_id=ch.id, category=cat, brand=brand, model=model, condition=cond, attrs=attrs,
            district="Chilonzor", qty=1, unit_cost=round(cost, -3), acquired_at=acquired, status=status,
            list_price_uzs=round(list_price, -3), store_id=stores[n % 2],
            identifier=make_imei(tac, next(serial)) if tac else None,
            sold_at=acquired + timedelta(days=sold_after) if sold_after is not None else None))
        if status == "in_stock":
            n += 1

    overpaid = 3  # the 3 iPhone 13 bought 20% above fair purchase price (v1 audit plant)
    for brand, model, cond, attrs, count in FAIR_UNITS:
        for _ in range(count):
            factor = None
            if model == "iPhone 13" and overpaid:
                factor, overpaid = 1.20, overpaid - 1
            unit(brand, model, cond, attrs, rng.randint(2, 28), "fair", factor)
    for brand, model, cond, attrs, count in OVERPRICED_UNITS:
        for _ in range(count):
            unit(brand, model, cond, attrs, rng.randint(3, 25), "over")
    for brand, model, cond, attrs, count in UNDERPRICED_UNITS:
        for _ in range(count):
            unit(brand, model, cond, attrs, rng.randint(2, 15), "under")
    for brand, model, cond, attrs, count in AGING_UNITS:
        for _ in range(count):
            unit(brand, model, cond, attrs, rng.randint(31, 55), "fair")
    for brand, model, cond, attrs, count, age in SLOW_UNITS:
        for _ in range(count):
            unit(brand, model, cond, attrs, age, "fair")
    # sold history (iPhones): enough for company-specific expected_days_to_sell
    for i in range(12):
        brand, model, cond, attrs, _ = FAIR_UNITS[i % 4]
        unit(brand, model, cond, attrs, rng.randint(40, 120), "fair", status="sold", sold_after=8 + (i * 7) % 18)
    return n
