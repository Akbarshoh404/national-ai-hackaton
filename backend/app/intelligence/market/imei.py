"""IMEI helpers: Luhn check digit and the local TAC table.

`data/tac.csv` is DEMO data covering the seeded phone models. A real TAC database needs a paid GSMA licence.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@lru_cache(maxsize=1)
def load_tac() -> dict[str, dict[str, Any]]:
    """TAC (first 8 IMEI digits) → {brand, model, storage_options}. Demo table, not licensed data."""
    out = {}
    with open(DATA_DIR / "tac.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["tac"]] = {"brand": row["brand"], "model": row["model"],
                               "storage_options": [int(x) for x in row["storage_options"].split("|")]}
    return out


def luhn_digit(body: str) -> str:
    """Luhn check digit for a 14-digit IMEI body."""
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_imei(tac: str, serial: int) -> str:
    body = f"{tac}{serial:06d}"
    return body + luhn_digit(body)
