"""Static reference data: categories, conditions, attribute fields, districts, labels.

`/meta` serves this to the frontend; services use it for validation and parsing.
"""

from __future__ import annotations

import re

Lang = str  # "uz" | "ru" | "en"

CATEGORIES = ["phone", "laptop", "car", "house", "rent"]
CATEGORY_HINTS = ["phone", "laptop", "car", "house", "rent", "mixed_tech", "mixed_realty", "mixed"]
GOODS_CATEGORIES = {"phone", "laptop", "car"}
REALTY_CATEGORIES = {"house", "rent"}

CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "phone": {"uz": "Telefonlar", "ru": "Телефоны", "en": "Phones"},
    "laptop": {"uz": "Noutbuklar", "ru": "Ноутбуки", "en": "Laptops"},
    "car": {"uz": "Avtomobillar", "ru": "Автомобили", "en": "Cars"},
    "house": {"uz": "Kvartira sotuvi", "ru": "Продажа квартир", "en": "Apartments for sale"},
    "rent": {"uz": "Kvartira ijarasi", "ru": "Аренда квартир", "en": "Apartment rent"},
}

CONDITIONS: dict[str, list[str]] = {
    "phone": ["new", "A", "B", "C"],
    "laptop": ["new", "A", "B", "C"],
    "car": ["new", "used"],
    "house": ["new", "used"],
    "rent": ["new", "used"],
}
CONDITION_LABELS: dict[str, dict[str, str]] = {
    "new": {"uz": "Yangi", "ru": "Новый", "en": "New"},
    "A": {"uz": "A (ideal)", "ru": "A (идеал)", "en": "A (like new)"},
    "B": {"uz": "B (yaxshi)", "ru": "B (хорошее)", "en": "B (good)"},
    "C": {"uz": "C (o'rtacha)", "ru": "C (среднее)", "en": "C (fair)"},
    "used": {"uz": "Ishlatilgan", "ru": "Б/у", "en": "Used"},
}


def _f(name: str, type_: str, uz: str, ru: str, en: str, unit: str | None = None,
       options: list[str] | None = None) -> dict:
    return {"name": name, "type": type_, "unit": unit, "options": options,
            "label": {"uz": uz, "ru": ru, "en": en}}


ATTR_FIELDS: dict[str, list[dict]] = {
    "phone": [
        _f("storage_gb", "int", "Xotira", "Память", "Storage", "GB"),
        _f("ram_gb", "int", "Operativ xotira", "ОЗУ", "RAM", "GB"),
        _f("battery_pct", "int", "Batareya", "Батарея", "Battery", "%"),
        _f("has_box", "bool", "Korobka bor", "Есть коробка", "Has box"),
        _f("imei_registered", "bool", "Registratsiyadan o'tgan", "IMEI зарегистрирован", "IMEI registered"),
        _f("region_version", "str", "Versiya (LL/A)", "Версия (LL/A)", "Region version"),
        _f("repaired", "bool", "Almashtirilgan qism", "Были замены", "Repaired"),
        _f("color", "str", "Rang", "Цвет", "Color"),
    ],
    "laptop": [
        _f("cpu", "str", "Protsessor", "Процессор", "CPU"),
        _f("cpu_gen", "int", "Avlod", "Поколение", "CPU generation"),
        _f("ram_gb", "int", "Operativ xotira", "ОЗУ", "RAM", "GB"),
        _f("ssd_gb", "int", "SSD", "SSD", "SSD", "GB"),
        _f("gpu", "str", "Videokarta", "Видеокарта", "GPU"),
        _f("screen_in", "float", "Ekran", "Экран", "Screen", "in"),
        _f("battery_health", "int", "Batareya holati", "Здоровье батареи", "Battery health", "%"),
        _f("purpose", "enum", "Maqsad", "Назначение", "Purpose", options=["gaming", "office", "study"]),
    ],
    "car": [
        _f("year", "int", "Yili", "Год", "Year"),
        _f("mileage_km", "int", "Probeg", "Пробег", "Mileage", "km"),
        _f("trim", "int", "Pozitsiya", "Позиция", "Trim"),
        _f("fuel", "enum", "Yoqilg'i", "Топливо", "Fuel",
           options=["benzin", "metan", "propan", "gibrid", "elektro"]),
        _f("transmission", "enum", "Uzatma", "КПП", "Transmission", options=["avtomat", "mexanika"]),
        _f("engine_l", "float", "Dvigatel", "Двигатель", "Engine", "L"),
        _f("paint_clean", "bool", "Kraskasi yo'q", "Без окраса", "Original paint"),
        _f("customs_cleared", "bool", "Rastamojka", "Растаможен", "Customs cleared"),
        _f("exchange_possible", "bool", "Obmen bor", "Обмен", "Exchange possible"),
        _f("credit_available", "bool", "Kredit/nasiya", "Кредит/рассрочка", "Credit available"),
    ],
    "house": [
        _f("rooms", "int", "Xonalar", "Комнат", "Rooms"),
        _f("area_m2", "float", "Maydon", "Площадь", "Area", "m²"),
        _f("floor", "int", "Qavat", "Этаж", "Floor"),
        _f("floors_total", "int", "Qavatlar soni", "Этажность", "Floors total"),
        _f("building", "enum", "Bino turi", "Тип дома", "Building", options=["novostroyka", "vtorichka"]),
        _f("material", "enum", "Material", "Материал", "Material", options=["kirpich", "panel", "monolit"]),
        _f("renovation", "enum", "Ta'mir", "Ремонт", "Renovation",
           options=["yevro", "oddiy", "korobka", "none"]),
        _f("cadastre", "bool", "Kadastr bor", "Есть кадастр", "Cadastre"),
        _f("landmark", "str", "Mo'ljal", "Ориентир", "Landmark"),
        _f("mortgage_ok", "bool", "Ipoteka", "Ипотека", "Mortgage OK"),
    ],
    "rent": [
        _f("rooms", "int", "Xonalar", "Комнат", "Rooms"),
        _f("area_m2", "float", "Maydon", "Площадь", "Area", "m²"),
        _f("furnished", "bool", "Mebelli", "С мебелью", "Furnished"),
        _f("appliances", "bool", "Jihozlar", "Техника", "Appliances"),
        _f("utilities_included", "bool", "Kommunal kiradi", "Коммуналка включена", "Utilities included"),
        _f("prepay_months", "int", "Oldindan to'lov", "Предоплата", "Prepay", "months"),
        _f("deposit", "float", "Depozit", "Депозит", "Deposit"),
        _f("tenant_type", "enum", "Ijarachi", "Арендатор", "Tenant", options=["oila", "student", "any"]),
        _f("period", "enum", "Muddat", "Период", "Period", options=["monthly", "daily"]),
        _f("landmark", "str", "Mo'ljal", "Ориентир", "Landmark"),
    ],
}

EXPENSE_CATEGORIES = ["stock_purchase", "rent", "electricity", "gas", "water", "internet", "salaries",
                      "ads", "repairs", "documents", "transport", "taxes", "other"]
INCOME_CATEGORIES = ["sale", "commission", "rent_income", "other_income"]
#: Utility-type bills checked for spikes by the auditor.
UTILITY_CATEGORIES = ["rent", "electricity", "gas", "water", "internet"]
#: Costs that recur once a month (not extrapolated by the budget forecast).
MONTHLY_BILL_CATEGORIES = {"rent", "electricity", "gas", "water", "internet", "salaries", "taxes"}
#: Operating costs used for the peer benchmark (everything except stock and taxes).
OPERATING_CATEGORIES = ["rent", "electricity", "gas", "water", "internet", "salaries", "ads",
                        "repairs", "documents", "transport", "other"]

TXN_CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "stock_purchase": {"uz": "Tovar xaridi", "ru": "Закупка товара", "en": "Stock purchase"},
    "rent": {"uz": "Ijara", "ru": "Аренда", "en": "Rent"},
    "electricity": {"uz": "Elektr energiya", "ru": "Электричество", "en": "Electricity"},
    "gas": {"uz": "Gaz", "ru": "Газ", "en": "Gas"},
    "water": {"uz": "Suv", "ru": "Вода", "en": "Water"},
    "internet": {"uz": "Internet", "ru": "Интернет", "en": "Internet"},
    "salaries": {"uz": "Ish haqi", "ru": "Зарплаты", "en": "Salaries"},
    "ads": {"uz": "Reklama", "ru": "Реклама", "en": "Ads"},
    "repairs": {"uz": "Ta'mirlash", "ru": "Ремонт", "en": "Repairs"},
    "documents": {"uz": "Hujjatlar", "ru": "Документы", "en": "Documents"},
    "transport": {"uz": "Transport", "ru": "Транспорт", "en": "Transport"},
    "taxes": {"uz": "Soliqlar", "ru": "Налоги", "en": "Taxes"},
    "other": {"uz": "Boshqa", "ru": "Прочее", "en": "Other"},
    "sale": {"uz": "Sotuv", "ru": "Продажа", "en": "Sale"},
    "commission": {"uz": "Komissiya", "ru": "Комиссия", "en": "Commission"},
    "rent_income": {"uz": "Ijara daromadi", "ru": "Доход от аренды", "en": "Rent income"},
    "other_income": {"uz": "Boshqa daromad", "ru": "Прочий доход", "en": "Other income"},
}

#: Aliases for bookkeeping categories found in uploaded files (uz/ru/en).
TXN_CATEGORY_ALIASES: dict[str, str] = {
    "tovar": "stock_purchase", "xarid": "stock_purchase", "закупка": "stock_purchase",
    "purchase": "stock_purchase", "stock": "stock_purchase", "товар": "stock_purchase",
    "ijara": "rent", "аренда": "rent", "arenda": "rent",
    "svet": "electricity", "elektr": "electricity", "электричество": "electricity", "свет": "electricity",
    "gaz": "gas", "газ": "gas", "suv": "water", "вода": "water",
    "интернет": "internet", "ish haqi": "salaries", "oylik": "salaries", "зарплата": "salaries",
    "salary": "salaries", "reklama": "ads", "реклама": "ads", "advertising": "ads",
    "ta'mir": "repairs", "tamir": "repairs", "ремонт": "repairs", "hujjat": "documents",
    "документы": "documents", "транспорт": "transport", "yo'l": "transport",
    "soliq": "taxes", "налог": "taxes", "налоги": "taxes", "tax": "taxes",
    "boshqa": "other", "прочее": "other",
    "sotuv": "sale", "продажа": "sale", "savdo": "sale", "komissiya": "commission",
    "комиссия": "commission", "ijara daromadi": "rent_income", "доход от аренды": "rent_income",
}

ROLES = ["retailer", "supplier", "realtor", "landlord"]
ROLE_LABELS: dict[str, dict[str, str]] = {
    "retailer": {"uz": "Chakana savdo", "ru": "Розница", "en": "Retailer"},
    "supplier": {"uz": "Ulgurji yetkazib beruvchi", "ru": "Оптовый поставщик", "en": "Supplier"},
    "realtor": {"uz": "Rieltor", "ru": "Риелтор", "en": "Realtor"},
    "landlord": {"uz": "Ijaraga beruvchi", "ru": "Арендодатель", "en": "Landlord"},
}
OFFER_KINDS = ["wholesale", "surplus", "car_trade", "cobroker"]
OFFER_KIND_LABELS: dict[str, dict[str, str]] = {
    "wholesale": {"uz": "Ulgurji", "ru": "Опт", "en": "Wholesale"},
    "surplus": {"uz": "Ortiqcha tovar", "ru": "Излишки", "en": "Surplus stock"},
    "car_trade": {"uz": "Avto savdo", "ru": "Авто-трейд", "en": "Car trade"},
    "cobroker": {"uz": "Hamkor rieltorlik", "ru": "Ко-брокеридж", "en": "Co-brokerage"},
}

DISTRICTS = ["Bektemir", "Chilonzor", "Mirobod", "Mirzo Ulug'bek", "Olmazor", "Sergeli",
             "Shayxontohur", "Uchtepa", "Yakkasaroy", "Yashnobod", "Yunusobod", "Yangihayot"]

_DISTRICT_ALIASES: dict[str, list[str]] = {
    "Bektemir": ["bektemir", "бектемир"],
    "Chilonzor": ["chilonzor", "chilanzar", "чиланзар", "чилонзор"],
    "Mirobod": ["mirobod", "mirabad", "мирабад", "миробод"],
    "Mirzo Ulug'bek": ["mirzo ulug", "mirzo-ulug", "ulugbek", "улугбек", "мирзо", "m.ulugbek"],
    "Olmazor": ["olmazor", "almazar", "алмазар", "олмазор"],
    "Sergeli": ["sergeli", "сергели"],
    "Shayxontohur": ["shayxontohur", "shayhontohur", "шайхантахур", "шайхонтохур"],
    "Uchtepa": ["uchtepa", "учтепа"],
    "Yakkasaroy": ["yakkasaroy", "yakkasaray", "яккасарай", "яккасарой"],
    "Yashnobod": ["yashnobod", "yashnabad", "яшнабад", "яшнобод"],
    "Yunusobod": ["yunusobod", "yunusabad", "юнусабад", "юнусобод"],
    "Yangihayot": ["yangihayot", "янгихаёт", "янгихаят"],
}


def normalize_district(value: str | None) -> str | None:
    """Map free-text district names (uz/ru, Latin/Cyrillic) to a canonical name."""
    if not value:
        return None
    low = value.lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'")
    for canon, aliases in _DISTRICT_ALIASES.items():
        if canon.lower() == low or any(a in low for a in aliases):
            return canon
    return None


_BRAND_PREFIXES = ("apple ", "samsung ", "xiaomi ", "chevrolet ", "chevy ", "byd ", "ravon ",
                   "daewoo ", "hp ", "lenovo ", "asus ", "acer ", "dell ")
_STORAGE_TOKEN = re.compile(r"\b\d{1,2}\s*/\s*\d{2,4}\b|\b\d{2,4}\s*(gb|гб|tb)\b")

MODEL_ALIASES: dict[str, str] = {
    "galaxy a54": "galaxy a54", "samsung a54": "galaxy a54", "a54": "galaxy a54",
    "s23": "galaxy s23", "galaxy s23": "galaxy s23",
    "kobalt": "cobalt", "кобальт": "cobalt", "джентра": "gentra", "jentra": "gentra",
    "нексия 3": "nexia 3", "nexia3": "nexia 3", "спарк": "spark", "малибу 2": "malibu 2",
    "malibu2": "malibu 2", "трекер 2": "tracker 2", "tracker2": "tracker 2", "дамас": "damas",
    "song plus": "song plus", "macbook air m1": "macbook air m1", "mba m1": "macbook air m1",
}


def norm_model(model: str | None, brand: str | None = None) -> str:
    """Normalize a model name for grouping: lowercase, no brand prefix, no storage tokens."""
    if not model or not isinstance(model, str):
        return ""
    if not isinstance(brand, str):
        brand = None
    s = model.lower().replace("ё", "е")
    s = _STORAGE_TOKEN.sub(" ", s)
    s = re.sub(r"(?<=[a-z]{4})(?=\d)", " ", s)  # iphone13 -> iphone 13 (keeps a54, m1)
    s = re.sub(r"[^\w\s+]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if brand:
        b = brand.lower().strip() + " "
        if s.startswith(b):
            s = s[len(b):]
    for p in _BRAND_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    s = re.sub(r"\b(pro) (max)\b", r"\1 \2", s)
    return MODEL_ALIASES.get(s, s)


def label(table: dict[str, dict[str, str]], key: str, lang: Lang) -> str:
    """Localized label with English fallback."""
    entry = table.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


# ---------------------------------------------------------------------------
# v2 reference lists
# ---------------------------------------------------------------------------
USER_ROLE_LABELS: dict[str, dict[str, str]] = {
    "owner": {"uz": "Egasi", "ru": "Владелец", "en": "Owner"},
    "manager": {"uz": "Menejer", "ru": "Менеджер", "en": "Manager"},
    "appraiser": {"uz": "Baholovchi", "ru": "Оценщик", "en": "Appraiser"},
    "lender_officer": {"uz": "Kredit xodimi", "ru": "Кредитный специалист", "en": "Lender officer"},
}
ROLE_LABELS.update({
    "lender": {"uz": "Bank / lizing", "ru": "Банк / лизинг", "en": "Lender"},
    "market_admin": {"uz": "Bozor ma'muriyati", "ru": "Администрация рынка", "en": "Market admin"},
})
ROLES_ALL = [*ROLES, "lender", "market_admin"]
PLANS = ["start", "pro", "business"]
PLAN_LABELS: dict[str, dict[str, str]] = {
    "start": {"uz": "Start", "ru": "Старт", "en": "Start"},
    "pro": {"uz": "Pro", "ru": "Pro", "en": "Pro"},
    "business": {"uz": "Biznes", "ru": "Бизнес", "en": "Business"},
}
CREDIT_PRODUCT_LABELS: dict[str, dict[str, str]] = {
    "business_loan": {"uz": "Biznes kredit", "ru": "Бизнес-кредит", "en": "Business loan"},
    "auto_loan": {"uz": "Avto zaxirasini moliyalash", "ru": "Финансирование автостока", "en": "Dealer stock loan"},
    "mortgage": {"uz": "Ipoteka", "ru": "Ипотека", "en": "Mortgage"},
    "leasing": {"uz": "Lizing", "ru": "Лизинг", "en": "Leasing"},
}
DECISION_TYPE_LABELS: dict[str, dict[str, str]] = {
    "reprice": {"uz": "Narxni o'zgartirish", "ru": "Переоценка", "en": "Reprice"},
    "duplicate_invoice": {"uz": "Takroriy hisob", "ru": "Дубликат счёта", "en": "Duplicate invoice"},
    "typo_amount": {"uz": "Summada xato", "ru": "Опечатка в сумме", "en": "Typo in amount"},
    "overpayment": {"uz": "Ortiqcha to'lov", "ru": "Переплата", "en": "Overpayment"},
    "budget_limit": {"uz": "Byudjet chegarasi", "ru": "Лимит бюджета", "en": "Budget limit"},
    "deal_to_buy": {"uz": "Arzon taklif", "ru": "Выгодная покупка", "en": "Deal to buy"},
    "slow_stock": {"uz": "Sekin tovar", "ru": "Залежавшийся товар", "en": "Slow stock"},
    "rfq_quote": {"uz": "So'rovga javob", "ru": "Ответ на запрос", "en": "Quote an RFQ"},
}
BLOCK_TYPES = ["price_range", "comparables", "kpi_row", "bar_chart", "line_chart", "table", "steps",
               "loan_schedule", "file"]
INTEGRATION_KINDS = ["telegram", "didox", "soliq", "billz", "onec", "bank"]
INTEGRATION_LABELS: dict[str, dict[str, str]] = {
    "telegram": {"uz": "Telegram kanallar", "ru": "Telegram-каналы", "en": "Telegram channels"},
    "didox": {"uz": "Didox e-hisob-faktura", "ru": "Didox ЭСФ", "en": "Didox e-invoices"},
    "soliq": {"uz": "Soliq.uz", "ru": "Soliq.uz", "en": "Soliq.uz"},
    "billz": {"uz": "BILLZ kassa/ombor", "ru": "BILLZ касса/склад", "en": "BILLZ POS/stock"},
    "onec": {"uz": "1C", "ru": "1С", "en": "1C"},
    "bank": {"uz": "Bank ko'chirmasi", "ru": "Банковская выписка", "en": "Bank statement"},
}
