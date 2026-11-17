"""Demo data: `python -m app.cli seed --reset`.

!!! ALL NUMBERS IN THIS FILE ARE SYNTHETIC DEMO DATA !!!
Base prices, per-m² prices and rent ratios are realistic-looking placeholders for the
hackathon demo, not market research. The demo works with no Telegram and no LLM key.
"""

from __future__ import annotations

import calendar
import logging
import math
import random
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app import db as dbm
from app.catalog import DISTRICTS, norm_model
from app.config import CONDITION_MULTIPLIERS, settings
from app.db import utcnow
from app.deps import hash_key
from app.models import (
    Budget,
    Company,
    Deal,
    InventoryItem,
    Listing,
    Offer,
    Quote,
    Rating,
    Rfq,
    Store,
    Transaction,
)
from app.services import market, pricing

log = logging.getLogger("bozorpilot.seed")

# --------------------------------------------------------------------------- #
# SYNTHETIC market reference data                                             #
# --------------------------------------------------------------------------- #
# brand, model, base USD, base storage GB, ram GB, storage variants
PHONES = [
    ("Apple", "iPhone 11", 250, 64, 4, [64, 128]),
    ("Apple", "iPhone 12", 350, 128, 4, [128, 256]),
    ("Apple", "iPhone 13", 450, 128, 4, [128, 256]),
    ("Apple", "iPhone 14", 560, 128, 6, [128, 256]),
    ("Apple", "iPhone 15", 700, 128, 6, [128, 256]),
    ("Apple", "iPhone 15 Pro", 950, 256, 8, [256, 512]),
    ("Samsung", "Galaxy A54", 260, 128, 8, [128, 256]),
    ("Samsung", "Galaxy S23", 600, 256, 8, [128, 256]),
    ("Xiaomi", "Redmi Note 13", 200, 256, 8, [128, 256]),
    ("Xiaomi", "Redmi Note 12", 150, 128, 4, [128]),
    ("Xiaomi", "Poco X6 Pro", 260, 256, 8, [256, 512]),
]
# brand, model, base USD, cpu, cpu_gen, ram, ssd, gpu, screen, purpose
LAPTOPS = [
    ("Apple", "MacBook Air M1", 650, "Apple M1", 1, 8, 256, "integrated", 13.3, "study"),
    ("Apple", "MacBook Air M2", 900, "Apple M2", 2, 8, 256, "integrated", 13.6, "office"),
    ("HP", "Pavilion 15", 550, "Intel Core i5", 12, 8, 512, "integrated", 15.6, "office"),
    ("Lenovo", "IdeaPad 3", 380, "Intel Core i3", 11, 8, 256, "integrated", 15.6, "study"),
    ("ASUS", "TUF F15", 800, "Intel Core i5", 12, 16, 512, "RTX 3050", 15.6, "gaming"),
    ("Acer", "Nitro 5", 750, "Intel Core i5", 11, 16, 512, "RTX 3050", 15.6, "gaming"),
    ("Dell", "Latitude 5420", 450, "Intel Core i5", 11, 8, 256, "integrated", 14.0, "office"),
]
# brand, model, base USD (year 2022), min year, max year, fuels
CARS = [
    ("Chevrolet", "Cobalt", 11500, 2014, 2024, ["benzin", "metan", "propan"]),
    ("Chevrolet", "Gentra", 12500, 2015, 2024, ["benzin", "metan", "propan"]),
    ("Chevrolet", "Nexia 3", 9000, 2016, 2020, ["benzin", "metan"]),
    ("Chevrolet", "Spark", 7500, 2014, 2022, ["benzin", "metan"]),
    ("Chevrolet", "Malibu 2", 24000, 2018, 2024, ["benzin"]),
    ("Chevrolet", "Tracker 2", 19000, 2020, 2024, ["benzin"]),
    ("Chevrolet", "Damas", 6500, 2012, 2024, ["benzin", "metan", "propan"]),
    ("BYD", "Song Plus", 30000, 2021, 2024, ["gibrid", "elektro"]),
]
CAR_BASE_YEAR = 2022
#: USD per m² by district
HOUSE_PPM2 = {"Yunusobod": 1300, "Mirzo Ulug'bek": 1350, "Chilonzor": 1000, "Yakkasaroy": 1600,
              "Mirobod": 1700, "Shayxontohur": 1150, "Sergeli": 750, "Yashnobod": 950, "Olmazor": 1000,
              "Uchtepa": 850, "Bektemir": 650, "Yangihayot": 700}
RENT_RATIO = 0.0055  # monthly rent ≈ 0.55% of apartment value
LISTINGS_PER_CATEGORY = 400
NOISE_SIGMA = 0.07
SHOP_PREMIUM = 1.04  # shops list slightly above private sellers

DEMO_COMPANIES = {
    "chilonzor-phone": ("Chilonzor Phone Market", "301234567", "retailer", ["phone", "laptop"], "Chilonzor"),
    "techopt": ("TechOpt Wholesale", "302345678", "supplier", ["phone", "laptop"], "Yunusobod"),
    "sergeli-avto": ("Sergeli Avto", "303456789", "retailer", ["car"], "Sergeli"),
    "yunusobod-realty": ("Yunusobod Realty", "304567890", "realtor", ["house", "rent"], "Yunusobod"),
}
PEER_SHOPS = ["Malika Mobile", "Abu Saxiy Phone", "Samsung Point", "Mobile City Sergeli", "iStyle Yunusobod",
              "Phone House Olmazor"]
EXTRA_SUPPLIERS = [("Samarqand Darvoza Opt", "305678901", [5, 5, 4]), ("Malika Gadget Opt", "306789012", [4, 4, 4, 3])]


class _Rng(random.Random):
    def noise(self, sigma: float = NOISE_SIGMA) -> float:
        return math.exp(self.gauss(0, sigma))


R = _Rng(42)


def _posted(max_days: float = 58, min_days: float = 0) -> datetime:
    return utcnow() - timedelta(days=R.uniform(min_days, max_days), minutes=R.randint(0, 59))


def _cond_phone() -> str:
    return R.choices(["new", "A", "B", "C"], weights=[30, 35, 25, 10])[0]


def phone_price_usd(base: float, base_storage: int, storage: int, cond: str, imei: bool = True,
                    repaired: bool = False) -> float:
    """Reference price formula used by the synthetic market (not by the engine)."""
    p = base * (1.12 ** math.log2(storage / base_storage)) * CONDITION_MULTIPLIERS[cond]
    if not imei:
        p *= 0.85
    if repaired:
        p *= 0.92
    return p


def house_price_usd(district: str, area: float, building: str, renovation: str) -> float:
    p = HOUSE_PPM2[district] * area
    if building == "novostroyka":
        p *= 1.08
    if renovation == "yevro":
        p *= 1.12
    elif renovation == "korobka":
        p *= 0.85
    return p


def _listing(category: str, i: int, brand: str | None, model: str, cond: str | None, usd: float,
             attrs: dict[str, Any], seller: str, district: str | None, posted: datetime,
             currency: str = "USD") -> Listing:
    rate = settings.USD_UZS
    if seller == "shop":
        usd *= SHOP_PREMIUM
    uzs = usd * rate
    if currency == "UZS":
        price = round(uzs, -4)
        uzs = price
        usd = uzs / rate
    else:
        price = round(usd, 0) if usd > 1000 else round(usd)
        uzs = price * rate
        usd = price
    return Listing(category=category, brand=brand, model=model, model_norm=norm_model(model, brand), condition=cond,
                   price=price, currency=currency, price_uzs=round(uzs), price_usd=round(usd, 2), city="Toshkent",
                   district=district, attrs=attrs, seller_type=seller, posted_at=posted,
                   source_url=f"seed://{category}/{i}", origin="seed")


def gen_phones(n: int) -> list[Listing]:
    out = []
    for i in range(n):
        brand, model, base, bst, ram, variants = PHONES[i % len(PHONES)]
        storage = R.choice(variants) if len(variants) == 1 else R.choices(variants, weights=[70, 30])[0]
        cond = _cond_phone()
        imei = R.random() > 0.1
        repaired = cond != "new" and R.random() < 0.08
        usd = phone_price_usd(base, bst, storage, cond, imei, repaired) * R.noise()
        attrs = {"storage_gb": storage, "ram_gb": ram, "battery_pct": 100 if cond == "new" else R.randint(78, 99),
                 "has_box": cond == "new" or R.random() < 0.5, "imei_registered": imei,
                 "region_version": R.choice(["LL/A", "ZA/A", "J/A", None]) if brand == "Apple" else None,
                 "repaired": repaired, "color": R.choice(["black", "white", "blue", "gold", None])}
        seller = "shop" if R.random() < 0.7 else "private"
        out.append(_listing("phone", i, brand, model, cond, usd, attrs, seller, R.choice(DISTRICTS), _posted(),
                            currency=R.choice(["USD", "USD", "UZS"])))
    return out


def gen_laptops(n: int) -> list[Listing]:
    out = []
    for i in range(n):
        brand, model, base, cpu, gen, ram, ssd, gpu, screen, purpose = LAPTOPS[i % len(LAPTOPS)]
        cond = _cond_phone()
        usd = base * CONDITION_MULTIPLIERS[cond] * R.noise()
        attrs = {"cpu": cpu, "cpu_gen": gen, "ram_gb": ram, "ssd_gb": ssd, "gpu": gpu, "screen_in": screen,
                 "battery_health": 100 if cond == "new" else R.randint(75, 98), "purpose": purpose}
        seller = "shop" if R.random() < 0.7 else "private"
        out.append(_listing("laptop", i, brand, model, cond, usd, attrs, seller, R.choice(DISTRICTS), _posted()))
    return out


def car_price_usd(base: float, year: int, km: int, trim: int, paint_clean: bool) -> float:
    p = base * (1 - 0.06) ** (CAR_BASE_YEAR - year) * max(0.5, 1 - 0.02 * km / 10000) * 1.04 ** (trim - 1)
    return p if paint_clean else p * 0.93


def gen_cars(n: int) -> list[Listing]:
    out = []
    for i in range(n):
        brand, model, base, y0, y1, fuels = CARS[i % len(CARS)]
        year = R.randint(y0, y1)
        km = max(0, int((2025 - year) * R.uniform(9000, 18000)))
        cond = "new" if km < 5000 else "used"
        trim = R.randint(1, 3)
        paint = R.random() < 0.7
        usd = car_price_usd(base, year, km, trim, paint) * R.noise()
        attrs = {"year": year, "mileage_km": km, "trim": trim, "fuel": R.choice(fuels),
                 "transmission": "avtomat" if model in ("Malibu 2", "Tracker 2", "Song Plus") or R.random() < 0.3
                 else "mexanika", "engine_l": 1.5, "paint_clean": paint, "customs_cleared": True,
                 "exchange_possible": R.random() < 0.3, "credit_available": R.random() < 0.25}
        seller = "shop" if R.random() < 0.35 else "private"
        out.append(_listing("car", i, brand, model, cond, usd, attrs, seller, R.choice(DISTRICTS), _posted()))
    return out


def _flat(district: str) -> tuple[dict[str, Any], float]:
    rooms = R.choices([1, 2, 3, 4], weights=[25, 35, 28, 12])[0]
    area = round(22 + rooms * 19 * R.uniform(0.85, 1.2), 1)
    building = R.choice(["novostroyka", "vtorichka"])
    renovation = R.choices(["yevro", "oddiy", "korobka"], weights=[35, 50, 15])[0]
    floors = R.choice([4, 5, 9, 12, 16])
    attrs = {"rooms": rooms, "area_m2": area, "floor": R.randint(1, floors), "floors_total": floors,
             "building": building, "material": R.choice(["kirpich", "panel", "monolit"]), "renovation": renovation,
             "cadastre": R.random() < 0.85, "landmark": None, "mortgage_ok": building == "novostroyka"}
    return attrs, house_price_usd(district, area, building, renovation)


def gen_houses(n: int) -> list[Listing]:
    out = []
    for i in range(n):
        d = DISTRICTS[i % len(DISTRICTS)]
        attrs, usd = _flat(d)
        cond = "new" if attrs["building"] == "novostroyka" else "used"
        seller = "shop" if R.random() < 0.4 else "private"
        out.append(_listing("house", i, None, f"{attrs['rooms']}-xonali kvartira", cond, usd * R.noise(), attrs,
                            seller, d, _posted()))
    return out


def gen_rent(n: int) -> list[Listing]:
    out = []
    for i in range(n):
        d = DISTRICTS[i % len(DISTRICTS)]
        flat, value = _flat(d)
        furnished = R.random() < 0.6
        usd = value * RENT_RATIO * (1.15 if furnished else 1.0) * R.noise()
        attrs = {"rooms": flat["rooms"], "area_m2": flat["area_m2"], "furnished": furnished,
                 "appliances": furnished or R.random() < 0.3, "utilities_included": R.random() < 0.2,
                 "prepay_months": R.choice([1, 1, 2, 3]), "deposit": None,
                 "tenant_type": R.choice(["oila", "student", "any"]), "period": "monthly", "landmark": None}
        seller = "shop" if R.random() < 0.3 else "private"
        out.append(_listing("rent", i, None, f"{flat['rooms']}-xonali ijara", "used", usd, attrs, seller, d,
                            _posted()))
    return out


def plant_deals(listings: list[Listing], per_category: int = 5) -> None:
    """Make a few recent listings clearly below market (sourcing radar demo)."""
    by_cat: dict[str, list[Listing]] = {}
    for lst in listings:
        by_cat.setdefault(lst.category, []).append(lst)
    for items in by_cat.values():
        for lst in R.sample(items, per_category):
            f = R.uniform(0.68, 0.78)
            lst.price = round(lst.price * f)
            lst.price_uzs = round(lst.price_uzs * f)
            lst.price_usd = round(lst.price_usd * f, 2)
            lst.posted_at = utcnow() - timedelta(hours=R.uniform(1, 40))


# --------------------------------------------------------------------------- #
# Companies and books                                                          #
# --------------------------------------------------------------------------- #

def _company(db: Session, slug: str | None, name: str, stir: str, role: str, cats: list[str],
             district: str) -> Company:
    from app.routers.auth import demo_key

    key = demo_key(slug) if slug else f"seed-{stir}"
    c = Company(slug=slug, name=name, stir=stir, role=role, categories=cats, district=district,
                api_key=hash_key(key), tax_regime="turnover")
    db.add(c)
    db.flush()
    db.add(Store(company_id=c.id, name="Asosiy do'kon", district=district))
    return c


def month_start(d: date, back: int) -> date:
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _day(ms: date, day: int, today: date) -> date:
    last = calendar.monthrange(ms.year, ms.month)[1]
    d = date(ms.year, ms.month, min(day, last))
    return min(d, today)


def _tx(company: Company, d: date, type_: str, cat: str, total: float, counterparty: str | None = None, *,
        qty: float = 1, unit: float | None = None, item: dict[str, Any] | None = None,
        note: str | None = None) -> Transaction:
    item = item or {}
    return Transaction(company_id=company.id, date=d, type=type_, category=cat, item_category=item.get("category"),
                       brand=item.get("brand"), model=item.get("model"), condition=item.get("condition"),
                       attrs=item.get("attrs") or {}, qty=qty, unit_price=unit if unit is not None else total / qty,
                       total=round(total), counterparty=counterparty, note=note, origin="seed")


def _item(cat: str, brand: str, model: str, cond: str, **attrs: Any) -> dict[str, Any]:
    return {"category": cat, "brand": brand, "model": model, "condition": cond, "attrs": attrs}


def _fair(db: Session, item: dict[str, Any]) -> pricing.Estimate:
    return pricing.estimate(db, item["category"], item["model"], item["condition"], item.get("district"),
                            item["attrs"], brand=item["brand"])


SUPPLIERS = ["TechOpt Wholesale", "Samarqand Darvoza Opt", "Malika Gadget Opt"]
OPEX_CHILONZOR = {"rent": 8_000_000, "electricity": 800_000, "gas": 150_000, "water": 80_000,
                  "internet": 350_000}
BILL_DAY = {"rent": 1, "internet": 3, "electricity": 5, "gas": 7, "water": 7}
COUNTERPARTY = {"rent": "IP Karimov (ijara)", "electricity": "Toshkent shahar elektr tarmoqlari",
                "gas": "Hududgaztaminot", "water": "Suvsoz", "internet": "Uzonline"}


def seed_chilonzor(db: Session, c: Company, today: date) -> None:
    """Six months of books with the planted problems listed in the spec."""
    goods = [
        _item("phone", "Apple", "iPhone 13", "A", storage_gb=128),
        _item("phone", "Apple", "iPhone 14", "A", storage_gb=128),
        _item("phone", "Samsung", "Galaxy A54", "new", storage_gb=128),
        _item("phone", "Xiaomi", "Redmi Note 12", "new", storage_gb=128),
        _item("phone", "Apple", "iPhone 11", "B", storage_gb=64),
        _item("laptop", "Apple", "MacBook Air M1", "A", ram_gb=8, ssd_gb=256),
        _item("laptop", "HP", "Pavilion 15", "new", ram_gb=8, ssd_gb=512),
    ]
    fairs = {g["model"]: _fair(db, g) for g in goods}
    txs: list[Transaction] = []
    rng = random.Random(7)
    for back in range(5, -1, -1):
        ms = month_start(today, back)
        last_day = calendar.monthrange(ms.year, ms.month)[1] if back else today.day
        # --- utility bills (spike: electricity +45% this month) -------------
        for cat, amount in OPEX_CHILONZOR.items():
            amt = amount if cat == "rent" else amount * rng.uniform(0.97, 1.03)
            if cat == "electricity" and back == 0:
                amt = amount * 1.45
            if cat == "internet" and back == 2:
                amt = 3_500_000  # planted extra-zero typo (should be 350 000)
            txs.append(_tx(c, _day(ms, BILL_DAY[cat], today), "expense", cat, round(amt, -3), COUNTERPARTY[cat]))
        if back == 4:  # planted duplicate electricity bill
            bill = next(t for t in reversed(txs) if t.category == "electricity")
            txs.append(_tx(c, bill.date, "expense", "electricity", bill.total, bill.counterparty))
        if back > 0 or today.day >= 25:
            txs.append(_tx(c, _day(ms, 25, today), "expense", "salaries", 12_000_000, "Xodimlar (ish haqi)"))
        # --- ads ----------------------------------------------------------------
        if back == 0:  # ads already over plan (plan 2.0M)
            txs.append(_tx(c, _day(ms, 2, today), "expense", "ads", 1_400_000, "Instagram Ads"))
            txs.append(_tx(c, _day(ms, 10, today), "expense", "ads", 1_200_000, "Telegram kanal reklama"))
        else:
            txs.append(_tx(c, _day(ms, 8, today), "expense", "ads", round(rng.uniform(1.3e6, 1.7e6), -3),
                           "Instagram Ads"))
        txs.append(_tx(c, _day(ms, 12, today), "expense", "transport", round(rng.uniform(5e5, 7e5), -3),
                       "Yandex Go Dostavka"))
        if back == 1:  # planted: large expense with no counterparty
            txs.append(_tx(c, _day(ms, 18, today), "expense", "repairs", 1_500_000, None, note="Do'kon ta'miri"))
        # --- stock purchases (~3 per week) and sales ---------------------------
        days = list(range(1, last_day + 1))
        n_purchases = max(2, round(len(days) / 30 * 13))
        for k in range(n_purchases):
            g = goods[k % len(goods)]
            d = _day(ms, days[int(k * len(days) / n_purchases)], today)
            qty = rng.randint(2, 5)
            unit = round(fairs[g["model"]].fair_buy_price_uzs * rng.uniform(0.98, 1.02), -3)
            txs.append(_tx(c, d, "expense", "stock_purchase", unit * qty, rng.choice(SUPPLIERS), qty=qty,
                           unit=unit, item=g))
            sale_unit = round(fairs[g["model"]].fair_price_uzs * rng.uniform(0.98, 1.02), -3)
            txs.append(_tx(c, min(d + timedelta(days=3), today), "income", "sale", sale_unit * qty,
                           "Chakana xaridorlar", qty=qty, unit=sale_unit, item=g))
        txs.append(_tx(c, _day(ms, 20, today), "income", "other_income", round(rng.uniform(10e6, 13e6), -3),
                       "Aksessuar va servis"))
        if back < 5:
            prev = month_start(today, back + 1)
            prev_income = sum(t.total for t in txs if t.type == "income" and t.date.month == prev.month
                              and t.date.year == prev.year)
            txs.append(_tx(c, _day(ms, 15, today), "expense", "taxes", round(prev_income * 0.04, -3),
                           "Soliq qo'mitasi", note="Aylanma soliq"))
    # --- planted purchase problems -------------------------------------------------
    this_month = month_start(today, 0)
    i13 = goods[0]
    overpay = round(fairs["iPhone 13"].fair_buy_price_uzs * 1.20, -3)
    txs.append(_tx(c, _day(this_month, 4, today), "expense", "stock_purchase", overpay * 3, "Qora bozor Abdulla",
                   qty=3, unit=overpay, item=i13, note="Shoshilinch xarid"))
    a54 = goods[2]
    unit = round(fairs["Galaxy A54"].fair_buy_price_uzs, -3)
    txs.append(_tx(c, _day(month_start(today, 1), 9, today), "expense", "stock_purchase", unit * 5 * 1.1,
                   "TechOpt Wholesale", qty=5, unit=unit, item=a54))  # qty × price ≠ total
    redmi = _item("phone", "Xiaomi", "Redmi Note 13", "new", storage_gb=256, ram_gb=8)
    txs.append(_tx(c, _day(month_start(today, 3), 14, today), "expense", "stock_purchase", 2_500_000,
                   "Malika Gadget Opt", qty=1, unit=2_500_000, item=redmi))
    txs.append(_tx(c, _day(this_month, 6, today), "expense", "stock_purchase", 3_300_000,
                   "Samarqand Darvoza Opt", qty=1, unit=3_300_000, item=redmi))
    db.add_all(txs)

    # --- budget for this month: ads over, stock purchase forecast over -----------
    month = this_month.strftime("%Y-%m")
    stock_fact = sum(t.total for t in txs if t.category == "stock_purchase" and t.date >= this_month)
    r = today.day / calendar.monthrange(today.year, today.month)[1]
    stock_plan = round(stock_fact / ((1 + r) / 2) if r < 1 else stock_fact / 0.95, -3)
    plans = {"stock_purchase": stock_plan, "ads": 2_000_000, "rent": 8_000_000, "electricity": 1_000_000,
             "gas": 200_000, "water": 100_000, "internet": 400_000, "salaries": 12_000_000, "transport": 800_000,
             "taxes": 12_000_000, "repairs": 500_000}
    db.add_all(Budget(company_id=c.id, month=month, category=k, planned=v) for k, v in plans.items())

    # --- inventory: 8 slow units (>75 days) + recent stock ---------------------------
    slow = [(goods[2], 3, 80), (goods[3], 2, 90), (goods[6], 2, 85),
            (_item("laptop", "Lenovo", "IdeaPad 3", "new", ram_gb=8, ssd_gb=256), 1, 100)]
    for g, qty, age in slow:
        cost = _fair(db, g).fair_buy_price_uzs
        db.add(_inv(c, g, qty, cost, today - timedelta(days=age)))
    db.add(_inv(c, i13, 3, overpay, _day(this_month, 4, today)))
    db.add(_inv(c, goods[1], 4, fairs["iPhone 14"].fair_buy_price_uzs, today - timedelta(days=12)))
    db.add(_inv(c, goods[5], 2, fairs["MacBook Air M1"].fair_buy_price_uzs, today - timedelta(days=20)))
    db.add(_inv(c, redmi, 1, 3_300_000, _day(this_month, 6, today)))


def _inv(c: Company, g: dict[str, Any], qty: int, cost: float, acquired: date) -> InventoryItem:
    return InventoryItem(company_id=c.id, category=g["category"], brand=g["brand"], model=g["model"],
                         condition=g["condition"], attrs=g["attrs"], district=g.get("district") or c.district,
                         qty=qty, unit_cost=round(cost), acquired_at=acquired)


def seed_opex(db: Session, c: Company, today: date, months: int, scale: float, rng: random.Random) -> None:
    """Generic operating costs (peer shops, suppliers, dealers, realtors)."""
    base = {"rent": 7e6, "electricity": 7e5, "gas": 1.4e5, "water": 8e4, "internet": 3.5e5, "salaries": 10e6,
            "ads": 1.5e6, "transport": 6e5}
    for back in range(months, 0, -1):
        ms = month_start(today, back)
        for cat, amt in base.items():
            v = round(amt * scale * rng.uniform(0.9, 1.1), -3)
            db.add(_tx(c, _day(ms, BILL_DAY.get(cat, 15), today), "expense", cat, v,
                       COUNTERPARTY.get(cat, "Xodimlar" if cat == "salaries" else "Reklama agentligi")))


def seed_trader(db: Session, c: Company, today: date, goods: list[dict[str, Any]], monthly_units: int,
                margin: float, rng: random.Random, months: int = 6) -> None:
    """Purchases and sales for a generic trader (supplier / car dealer)."""
    for back in range(months - 1, -1, -1):
        ms = month_start(today, back)
        for k in range(monthly_units):
            g = goods[k % len(goods)]
            est = _fair(db, g)
            d = _day(ms, 1 + (k * 27) // max(monthly_units, 1), today)
            qty = 1 if g["category"] == "car" else rng.randint(5, 20)
            buy = round(est.fair_buy_price_uzs * (1 - margin) * rng.uniform(0.98, 1.02), -3)
            db.add(_tx(c, d, "expense", "stock_purchase", buy * qty, "Import yetkazib beruvchi", qty=qty, unit=buy,
                       item=g))
            sell = round(est.fair_buy_price_uzs * rng.uniform(0.98, 1.03), -3) if g["category"] != "car" \
                else round(est.fair_price_uzs * rng.uniform(0.97, 1.01), -3)
            db.add(_tx(c, min(d + timedelta(days=5), today), "income", "sale", sell * qty, "Mijozlar", qty=qty,
                       unit=sell, item=g))


def seed_companies(db: Session, today: date) -> dict[str, Company]:
    rng = random.Random(11)
    cs = {slug: _company(db, slug, *spec) for slug, spec in DEMO_COMPANIES.items()}
    seed_chilonzor(db, cs["chilonzor-phone"], today)

    # --- TechOpt: wholesale offers + inventory ---------------------------------
    t = cs["techopt"]
    tech_goods = [_item("phone", "Apple", "iPhone 13", "A", storage_gb=128),
                  _item("phone", "Samsung", "Galaxy A54", "new", storage_gb=128),
                  _item("phone", "Xiaomi", "Redmi Note 13", "new", storage_gb=256, ram_gb=8),
                  _item("laptop", "Apple", "MacBook Air M1", "A", ram_gb=8, ssd_gb=256),
                  _item("phone", "Apple", "iPhone 15", "new", storage_gb=128)]
    seed_trader(db, t, today, tech_goods, 6, 0.06, rng, months=3)
    seed_opex(db, t, today, 3, 1.3, rng)
    for g, qty, factor, stock in zip(tech_goods, [20, 30, 50, 10, 15], [0.95, 0.97, 0.93, 0.96, 0.98],
                                     [40, 50, 100, 15, 20], strict=True):
        est = _fair(db, g)
        db.add(Offer(company_id=t.id, kind="wholesale", category=g["category"], brand=g["brand"], model=g["model"],
                     condition=g["condition"], attrs=g["attrs"], qty=qty, unit_price=round(est.fair_buy_price_uzs
                                                                                          * factor, -3),
                     district=t.district, note="Ulgurji narx, kafolat 3 oy"))
        db.add(_inv(t, g, stock, est.fair_buy_price_uzs * 0.94, today - timedelta(days=20)))

    # --- Sergeli Avto: books, car inventory and a car_trade offer -----------------
    s = cs["sergeli-avto"]
    cars = [_item("car", "Chevrolet", "Cobalt", "used", year=2021, mileage_km=50000, fuel="benzin"),
            _item("car", "Chevrolet", "Gentra", "used", year=2020, mileage_km=70000, fuel="metan"),
            _item("car", "Chevrolet", "Spark", "used", year=2019, mileage_km=80000, fuel="benzin"),
            _item("car", "Chevrolet", "Tracker 2", "used", year=2022, mileage_km=30000, fuel="benzin"),
            _item("car", "Chevrolet", "Nexia 3", "used", year=2019, mileage_km=90000, fuel="metan")]
    seed_trader(db, s, today, cars, 4, 0.04, rng)
    seed_opex(db, s, today, 6, 0.9, rng)
    for i, g in enumerate(cars):
        db.add(_inv(s, g, 1, _fair(db, g).fair_buy_price_uzs, today - timedelta(days=10 + 15 * i)))
    cobalt = _fair(db, cars[0])
    db.add(Offer(company_id=s.id, kind="car_trade", category="car", brand="Chevrolet", model="Cobalt", condition="used",
                 attrs=cars[0]["attrs"], qty=1, unit_price=round(cobalt.fair_price_uzs * 0.92, -3),
                 district="Sergeli", note="Obmen mumkin, kraskasi yo'q"))

    # --- Yunusobod Realty: co-brokerage offers + commission income -----------------
    y = cs["yunusobod-realty"]
    seed_opex(db, y, today, 6, 0.6, rng)
    for back in range(5, -1, -1):
        db.add(_tx(y, _day(month_start(today, back), 20, today), "income", "commission",
                   round(rng.uniform(25e6, 40e6), -3), "Mijozlar (komissiya)"))
    realty = [("house", "Yunusobod", {"rooms": 3, "area_m2": 85, "building": "novostroyka", "renovation": "yevro"}),
              ("house", "Mirzo Ulug'bek", {"rooms": 2, "area_m2": 62, "building": "vtorichka"}),
              ("rent", "Yunusobod", {"rooms": 2, "area_m2": 60, "furnished": True, "period": "monthly"}),
              ("rent", "Chilonzor", {"rooms": 1, "area_m2": 40, "furnished": False, "period": "monthly"})]
    for cat, district, attrs in realty:
        est = pricing.estimate(db, cat, district=district, attrs=attrs)
        db.add(Offer(company_id=y.id, kind="cobroker", category=cat, brand=None,
                     model=f"{attrs['rooms']}-xonali {'kvartira' if cat == 'house' else 'ijara'}",
                     condition="new" if attrs.get("building") == "novostroyka" else "used", attrs=attrs, qty=1,
                     unit_price=round(est.fair_price_uzs * 0.97, -3), district=district, commission_split=0.5,
                     note="Komissiya 50/50"))

    # --- 6 peer phone shops (benchmark) ---------------------------------------
    peers = [_company(db, None, name, f"31{i:07d}", "retailer", ["phone"], DISTRICTS[i * 2 % 12])
             for i, name in enumerate(PEER_SHOPS)]
    for i, p in enumerate(peers):
        seed_opex(db, p, today, 3, 0.75 + i * 0.12, rng)

    # --- 2 extra suppliers with ratings ---------------------------------------
    sup = []
    for name, stir, scores in EXTRA_SUPPLIERS:
        co = _company(db, None, name, stir, "supplier", ["phone", "laptop"], "Shayxontohur")
        sup.append(co)
        for k, score in enumerate(scores):
            buyer = peers[k % len(peers)]
            deal = Deal(buyer_id=buyer.id, seller_id=co.id, category="phone", brand="Apple", model="iPhone 12",
                        condition="A", attrs={"storage_gb": 128}, qty=5, unit_price=3_400_000, total=17_000_000,
                        created_at=utcnow() - timedelta(days=30 + k * 7))
            db.add(deal)
            db.flush()
            db.add(Rating(deal_id=deal.id, rater_id=buyer.id, ratee_id=co.id, score=score, comment=None))

    # --- open RFQ from Chilonzor with 2 quotes --------------------------------
    i13 = _item("phone", "Apple", "iPhone 13", "A", storage_gb=128)
    est = _fair(db, i13)
    rfq = Rfq(company_id=cs["chilonzor-phone"].id, category="phone", brand="Apple", model="iPhone 13", condition="A",
              attrs=i13["attrs"], qty=10, target_unit_price=est.fair_buy_price_uzs, district="Chilonzor",
              deadline=today + timedelta(days=5), note="Kafolat bilan, box bo'lsa yaxshi")
    db.add(rfq)
    db.flush()
    db.add(Quote(rfq_id=rfq.id, supplier_id=sup[0].id, unit_price=round(est.fair_buy_price_uzs * 0.99, -3), qty=10,
                 delivery_days=3, note="Hammasi box bilan"))
    db.add(Quote(rfq_id=rfq.id, supplier_id=sup[1].id, unit_price=round(est.fair_buy_price_uzs * 1.04, -3), qty=6,
                 delivery_days=7, note="6 dona bor"))
    return cs


def run(reset: bool = True) -> dict[str, int]:
    """Seed the database. With `reset`, drop and recreate all tables first."""
    if reset:
        dbm.drop_all()
        dbm.migrate()
    pricing.invalidate()
    today = date.today()
    with dbm.SessionLocal() as db:
        listings = (gen_phones(LISTINGS_PER_CATEGORY) + gen_laptops(LISTINGS_PER_CATEGORY)
                    + gen_cars(LISTINGS_PER_CATEGORY) + gen_houses(LISTINGS_PER_CATEGORY)
                    + gen_rent(LISTINGS_PER_CATEGORY))
        plant_deals(listings)
        db.add_all(listings)
        db.commit()
        pricing.invalidate()
        # fair price + discount for recent listings (radar), deal alerts for planted deals
        cutoff = utcnow() - timedelta(days=30)
        deals = 0
        for lst in listings:
            if lst.posted_at >= cutoff:
                est = pricing.assess_listing(db, lst)
                if lst.posted_at >= utcnow() - timedelta(days=2) and market.deal_check(db, lst, est):
                    deals += 1
        db.commit()
        companies = seed_companies(db, today)
        db.commit()
        from app import seed_v2

        v2 = seed_v2.run(db, companies, today)
        db.commit()
        try:
            from app.services.telegram_ingest import sync_sources_from_yaml

            sync_sources_from_yaml(db)
        except Exception:  # sources file is optional for the demo
            log.warning("sources.yaml sync skipped")
        db.commit()
    pricing.invalidate()
    return {"listings": len(listings), "companies": len(companies), "deal_alerts": deals, **v2}
