"""Ask the running copilot a few questions and print intent, how it was routed, and the answer.

Usage: python scripts/chat_probe.py [base_url] [api_key]
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
KEY = sys.argv[2] if len(sys.argv) > 2 else "demo-chilonzor-phone"
QUESTIONS = [
    "salom",
    "iphone 14ni narxi qancha",
    "Samsung A54 nechpul bozorda",
    "MacBook Air M1 qancha turadi",
    "bu oy qancha foyda qildim",
    "qaysi telefon yaxshi sotiladi",
    "do'konim ahvoli qanday",
    "rahmat",
    "сколько стоит iPhone 13",
]

sys.stdout.reconfigure(encoding="utf-8")
for q in QUESTIONS:
    t = time.time()
    r = httpx.post(f"{BASE}/api/v1/advisor/chat", headers={"X-API-Key": KEY, "Accept-Language": "uz"},
                   json={"question": q, "context": {"screen": "advisor"}}, timeout=90)
    d = r.json()
    print(f"{time.time() - t:5.1f}s  {q}")
    print(f"       {d.get('intent')} / {d.get('intent_source')} / {d.get('source')}: {d.get('answer') or d}")
