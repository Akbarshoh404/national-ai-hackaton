# `app.channels` — delivery channels and external systems

| Module | What it does | Problem |
|---|---|---|
| `bot` | Telegram bot over the Bot API (long polling): `/link`, `/budget`, `/audit`, `/deals`, `/rfqs`, `/price`, invoice photos → OCR, forwarded posts and voice notes → priced, alert push every 5 s | #25, #26, #19 |
| `integrations` | Adapter interface + status cards. Telegram is live; Didox, Soliq, BILLZ, 1C and bank are **mock** adapters reading `data/samples/` (real APIs need partner agreements). Syncs go through the normal upload → audit path | #26 |

May import anything below it (`core`, `data_pipeline`, `intelligence`).
