# `app.data_pipeline` — Telegram → market data (#19)

Turns Telegram sale channels into structured, anonymized market listings. May import only `app.core` and
`app.intelligence.market` (for pricing the new listings and the deal check).

| Module | What it does |
|---|---|
| `sources` | `sources.yaml` ⇄ `sources` table; version counter so the listener reloads without a restart |
| `telegram_ingest` | Read-only Telethon client from `TG_SESSION`: live listener, history import (FloodWait-aware), single-message fetch, offer filter and **PII stripping** (phones, @usernames, links) before storage |
| `extractor` | Raw post → listing: Gemini JSON extraction in batches of 15 (retry in halves) or the rule parser without a key; validation (currency, UZS/USD, outliers, reposts); price-cache invalidation, SSE `listing.created`, deal alerts |

Feeds problem **#19** (market price analytics); every other module prices against what this package produces.
