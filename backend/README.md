# BozorPilot AI — backend

B2B market intelligence and finance co-pilot for Uzbek businesses that trade **phones, laptops, cars,
apartments (sale) and apartment rent**. Built for the National AI Hackathon (Tashkent).

**Core rule:** the LLM reads and explains; Python calculates. Every price, tax, loan payment, budget number
and ranking is computed in code. Every LLM call has a deterministic fallback, so the whole API works
**without any API key** and **without Telegram** (seed data).

## Architecture

```
                   ┌───────────────────────── one process (uvicorn) ─────────────────────────┐
 Telegram channels │  telegram_ingest (Telethon, read-only)                                   │
  & groups ───────►│    live NewMessage + history ─► PII strip ─► raw_posts                   │
                   │                                               │                          │
                   │  extractor loop (every 5 s, batches of 15)    ▼                          │
 Gemini (optional)◄┼──  LLM JSON  ──or──  rule parser ─► validate ─► listings ─► deal check ──┐ │
                   │                        (FX, outliers, reposts)      │                   │ │
                   │  pricing engine (pandas, tiers, 20 s cache) ◄───────┘                   │ │
                   │        ▲                                                                │ │
 Next.js frontend ◄┼── REST /api/v1 (FastAPI, typed OpenAPI) ── SSE /market/stream ◄─ events ◄┤ │
  (Vercel)         │   market · books · exchange · advisor · alerts · dashboard · admin      │ │
                   │        │                                                                │ │
                   │   SQLAlchemy ─► SQLite (WAL) / PostgreSQL                               │ │
                   │                                                                         ▼ │
 Telegram users ◄──┼── bot (Bot API long polling): /link /budget /audit /deals /rfqs, invoice  │
                   │      photo OCR, alert push every 5 s ◄──────────────── alerts ◄────────┘  │
                   └──────────────────────────────────────────────────────────────────────────┘
```

Every worker is behind an env flag (`WORKERS_TELEGRAM`, `WORKERS_EXTRACTOR`, `BOT_ENABLED`) and runs under a
supervisor that logs and restarts it — a crashing worker never takes down the API.

## Setup in 5 commands

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -m app.cli seed --reset
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs. Demo login: `POST /api/v1/auth/demo-login {"company_slug": "chilonzor-phone"}`.

| Demo company | slug | API key |
|---|---|---|
| Chilonzor Phone Market (retailer: phone, laptop) | `chilonzor-phone` | `demo-chilonzor-phone` |
| TechOpt Wholesale (supplier: phone, laptop) | `techopt` | `demo-techopt` |
| Sergeli Avto (retailer: car) | `sergeli-avto` | `demo-sergeli-avto` |
| Yunusobod Realty (realtor: house, rent) | `yunusobod-realty` | `demo-yunusobod-realty` |

Demo keys only exist when the database was seeded; `demo-login` only works with `DEMO_MODE=true`.

### Tests, lint, smoke

```bash
pytest -q                                   # temp SQLite + seed, no LLM, no Telegram
ruff check app tests scripts
python scripts/smoke.py http://127.0.0.1:8000 change-me   # calls every endpoint on a running server
```

### TypeScript client for the frontend

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.ts
```

Operation IDs are readable (`market_price`, `exchange_accept_quote`, …). Every error has the shape
`{"error": {"code", "message", "details"}}`, every list is `{items, next_cursor, total}`, money is raw numbers
(`*_uzs`, `*_usd`), dates are ISO 8601 UTC, months are `YYYY-MM`. `Accept-Language: uz|ru|en` selects the
language of generated text (default `uz`).

## Telegram

### 1. Log in (user account, read-only)

1. Create an app at https://my.telegram.org → *API development tools*; put `TG_API_ID` and `TG_API_HASH` in `.env`.
2. `python -m app.cli tg-login` — enter phone, code and 2FA password. It saves `bozorpilot.session` locally
   and prints a `TG_SESSION=...` string for servers. **Treat it like a password.**

The account only reads. It never posts or sends messages. Phone numbers, @usernames and links are stripped
before storing (ZRU-547), and senders of group messages are never stored.

### 2. Resolve channel usernames

`sources.yaml` lists the channels by display name with `username: TODO`. Run:

```bash
python -m app.cli tg-resolve
```

For every unresolved title it searches Telegram, prints candidates (username, subscribers, last post date) and
asks you to pick one; confirmed usernames are written back to `sources.yaml` and loaded into the database.
Sources can also be added at runtime with `POST /api/v1/admin/sources`; the listener reloads without a restart.

### 3. Import history and run

```bash
python -m app.cli tg-history --limit 3000   # or POST /api/v1/admin/telegram/history
python -m app.cli extract-once              # or let the extractor worker do it every 5 s
```

### Bot

Create a bot with @BotFather and set `TG_BOT_TOKEN`. In Telegram: `/link demo-chilonzor-phone`, then `/budget`,
`/audit`, `/deals`, `/rfqs`, or send an invoice photo (needs `GEMINI_API_KEY`).

## Endpoints → problems

| Area | Endpoints | Problem |
|---|---|---|
| Market engine | `GET /market/listings`, `GET /market/stream` (SSE), `GET /market/stats`, `POST /market/price`, `GET /market/sourcing-radar`, `GET /market/trend`, `GET /market/models`, `POST /market/rental-yield`, `GET /market/heatmap` | **#19** |
| B2B exchange | `POST/GET /exchange/rfqs`, `GET /exchange/rfqs/{id}`, `POST/GET /exchange/rfqs/{id}/quotes`, `POST /exchange/quotes/{id}/accept`, `GET /exchange/rfqs/{id}/matches`, `POST/GET/DELETE /exchange/offers`, `POST /exchange/offers/{id}/buy`, `GET /exchange/deals`, `POST /exchange/deals/{id}/rate`, `GET /exchange/demand` | **#19** |
| AI Auditor | `POST /books/upload`, `GET /books/upload/template`, `POST /books/invoice`, `GET/POST/DELETE /books/transactions`, `GET /books/audit`, `GET /books/benchmark`, `GET/POST /books/inventory`, `GET /books/slow-stock`, `GET /books/stock-revaluation` | **#26** |
| Budget control | `PUT/GET /books/budget`, budget alerts, `GET /alerts`, `GET /alerts/stream` | **#25** |
| AI Advisor | `POST /advisor/chat`, `GET /advisor/cashflow`, `POST /advisor/credit`, `GET /advisor/tax`, `GET /advisor/loan-readiness`, `POST /advisor/expansion`, `POST /advisor/business-plan` | **#20** |
| Platform | `POST /auth/register`, `POST /auth/demo-login`, `GET/PATCH /companies/me`, `GET /companies`, `GET /companies/{id}`, `GET /meta`, `GET /dashboard`, `GET /health`, `/admin/*` | all |

## Deploy to Railway

1. New project → *Deploy from GitHub repo* (root directory `backend`); Railway builds the `Dockerfile`.
2. Add the **PostgreSQL** plugin; set `DATABASE_URL=${{Postgres.DATABASE_URL}}` (the `postgres://` scheme is
   handled automatically).
3. Set variables from `.env.example`: `ADMIN_KEY`, `CORS_ORIGINS` (your Vercel domain), `TG_API_ID`,
   `TG_API_HASH`, **`TG_SESSION`** (the string printed by `tg-login`), `TG_BOT_TOKEN`, `GEMINI_API_KEY`.
4. Deploy. Migrations run on startup (`AUTO_MIGRATE=true`). Seed once from the Railway shell:
   `python -m app.cli seed --reset`.
5. Run **one replica only**: the Telegram listener and the bot must not run twice.

`docker compose up --build` runs the same image locally with Postgres.
