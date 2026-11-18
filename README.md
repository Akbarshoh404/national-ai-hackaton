# Raft

**B2B market intelligence and finance co-pilot for Uzbek businesses that trade phones, laptops, cars,
apartments (sale) and apartment rent.** Built for the National AI Hackathon (Tashkent).

The backend reads Telegram sale channels live, turns posts into a fair-price index, rates every unit a shop
holds against that market, audits the shop's books, controls its budget, runs a B2B exchange between businesses,
prepares a daily queue of decisions, answers questions with charts and tables, and gives banks a console to value
collateral and review loan applications built from the same verified numbers.

> **Core rule: the LLM reads and explains; Python calculates.** Every price, tax, loan payment, budget number,
> ranking and chart value is computed in code. Every LLM call has a deterministic fallback with a 15 s timeout,
> so **the whole API works with no `GEMINI_API_KEY` and no Telegram** (on seed data).

---

## Contents

1. [What it solves](#1-what-it-solves)
2. [Architecture](#2-architecture)
3. [Repository layout](#3-repository-layout)
4. [Quick start](#4-quick-start)
5. [Demo accounts and demo data](#5-demo-accounts-and-demo-data)
6. [Configuration](#6-configuration)
7. [API conventions](#7-api-conventions)
8. [Roles and permissions](#8-roles-and-permissions)
9. [Endpoint reference](#9-endpoint-reference)
10. [How the engines work](#10-how-the-engines-work)
11. [Telegram: ingestion and bot](#11-telegram-ingestion-and-bot)
12. [Integrations](#12-integrations)
13. [Data model](#13-data-model)
14. [Testing, linting and the smoke run](#14-testing-linting-and-the-smoke-run)
15. [Deployment](#15-deployment)
16. [5-minute demo script](#16-5-minute-demo-script)
17. [Before going live: manual checklist](#17-before-going-live-manual-checklist)
18. [Known limitations](#18-known-limitations)

Design decisions and every assumption behind the numbers are listed in
[backend/DECISIONS.md](backend/DECISIONS.md).

---

## 1. What it solves

The four official problems (Chamber of Commerce) and the modules that answer them:

| Problem | Module | What it does |
|---|---|---|
| **#19** Market price analytics + B2B trading platform | Market engine, Stock command center, B2B exchange | Reads Telegram sale channels, builds a fair-price index, rates every unit in stock, lets businesses trade (RFQs, quotes, offers, counter-offers, deals, ratings) |
| **#26** Operating costs + human-error audit | AI Auditor, Decisions queue, Integrations | Finds duplicates, typos, wrong totals, cost spikes, overpayments and missing counterparties, and offers one-click fixes |
| **#25** Budget plan vs fact, early warning | Budget control, Decisions queue, Alerts | Plan vs actual per category, month-end forecast, alerts before a limit is crossed |
| **#20** Financial advisor: credit, tax, market | AI Advisor (copilot), Lender console | Copilot with answer blocks, cash flow, credit products with schedules, tax comparison, loan readiness, loan applications to banks |

**B2B only.** Every user is a registered business (STIR/INN). Telegram posts from private sellers are used only
as anonymized market data.

The frontend (Next.js, a separate project) has five sections served by this API: **Bugun** (today: dashboard +
decisions), **Narxlar** (prices and stock), **Birja** (exchange), **Kitoblar** (books) and **Maslahat** (advisor).
It also has a separate **lender console** for banks and bazaar administrators.

---

## 2. Architecture

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
                   │        ├── stock command center ── decisions worker (every 10 min)      │ │
                   │        ├── AI auditor / budget ── copilot tools ── lender valuations    │ │
                   │        │                                                                │ │
 Next.js frontend ◄┼── REST /api/v1 (FastAPI, typed OpenAPI) ── SSE streams ◄── events ◄─────┤ │
 Bank console     ◄┼──  market · stock · books · exchange · advisor · lender · decisions …   │ │
                   │        │                                                                │ │
                   │   SQLAlchemy 2 ─► SQLite (WAL) locally / PostgreSQL in production       │ │
                   │                                                                         ▼ │
 Telegram users ◄──┼── bot (Bot API long polling): /link /budget /audit /deals /rfqs /price,  │
                   │      invoice photo OCR, forwarded posts, voice notes, alert push (5 s) ◄─┘ │
                   └──────────────────────────────────────────────────────────────────────────┘
```

**One process runs everything.** The FastAPI `lifespan` runs migrations and starts four background workers, each
behind an env flag and each under a supervisor that logs crashes and restarts with backoff. A crashing worker
never takes the API down.

| Worker | Flag | What it does |
|---|---|---|
| `telegram` | `WORKERS_TELEGRAM` | Live Telethon listener over the active sources (needs `TG_API_ID`, `TG_API_HASH`, a session) |
| `extractor` | `WORKERS_EXTRACTOR` | Turns pending raw posts into listings every 5 s (LLM or rule parser) |
| `decisions` | `WORKERS_DECISIONS` | Rebuilds every business's decisions queue every 10 min |
| `bot` | `BOT_ENABLED` | Telegram bot long polling plus the alert push loop (needs `TG_BOT_TOKEN`) |

**Tech stack:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, Pydantic v2, pandas/numpy, Telethon,
httpx, google-genai (Gemini), openpyxl, WeasyPrint (optional, for PDF), pytest, ruff.

---

## 3. Repository layout

`backend/app` is a **modular monolith**: one deployable process, five packages with a one-way import direction
(enforced by `tests/test_architecture.py`). Each package has its own `README.md`.

```
 api ──────────┐            channels ──────┐        (HTTP routers + schemas │ Telegram bot, integrations)
               ▼                           ▼
        intelligence  (market · books · b2b · advisor — the engines; never imports api/channels)
               ▲
 data_pipeline ┘ (Telegram → listings; may import only core + intelligence.market)
               ▼
             core   (config, db, models, auth, i18n, llm, events, alerts — imports nothing else)
```

```
.
├── README.md                         ← this file
├── start-raft.cmd / start-raft.ps1   start the backend on this machine (local hosting)
├── render.yaml                       Render Blueprint (free Docker web service, for later)
├── docs/DEPLOY.md                    free hosting: Neon + Render + cron-job.org + Cloudflare tunnel + frontend
└── backend/
    ├── app/
    │   ├── main.py                   FastAPI app: lifespan (migrations, workers, memory log), CORS, errors, routers;
    │   │                             `python -m app.main` honours $PORT
    │   ├── cli.py                    python -m app.cli init-db | seed | tg-login | tg-resolve | tg-history | extract-once
    │   ├── seed.py, seed_v2.py       synthetic demo data (market, companies, planted problems, stock, bank)
    │   ├── core/                     shared kernel — imports nothing outside core
    │   │   ├── config.py             settings from env + documented engine constants (margins, haircuts, products)
    │   │   ├── db.py                 engine (SQLite WAL / PostgreSQL+Neon pool), sessions, migrate/create/drop
    │   │   ├── models.py             every table (see §13)
    │   │   ├── deps.py, permissions.py  API-key auth (company or user), roles, central role policy
    │   │   ├── errors.py, i18n.py, catalog.py  error format; uz/ru/en texts; categories, attributes, districts
    │   │   ├── llm.py                Gemini wrapper (JSON, text, vision, audio) with fallbacks
    │   │   ├── events.py, sse.py, alerts.py, activity.py  pub/sub, SSE, alerts, activity log
    │   │   └── fx.py, workers.py, memory.py, logging_setup.py  FX rate, worker supervision, RSS, redacted logs
    │   ├── data_pipeline/            Telegram → listings (#19)
    │   │   ├── sources.py            sources.yaml ⇄ sources table, live reload counter
    │   │   ├── telegram_ingest.py    Telethon (TG_SESSION StringSession) listener, history, PII stripping
    │   │   └── extractor.py          raw post → listing (LLM or rules) → validation → deal check
    │   ├── intelligence/             the engines — never imports api / channels
    │   │   ├── market/               pricing (fair-price engine), market (radar, trends, heatmap, yield),
    │   │   │                         stock (command center), inputs (free text, links), imei (Luhn + TAC)
    │   │   ├── books/                books (import, AI auditor, budget, benchmark, revaluation), decisions
    │   │   ├── b2b/                  exchange (RFQs, ranking, counter-offers, deals, ratings, demand)
    │   │   └── advisor/              finance (cash flow, credit, tax, readiness), copilot, lender
    │   ├── api/
    │   │   ├── routers/              one file per area (auth, meta, dashboard, decisions, market, inputs, stock,
    │   │   │                         books, exchange, advisor, alerts, platform, lender, admin)
    │   │   └── schemas/              Pydantic request/response models (+ blocks.py for copilot blocks)
    │   └── channels/
    │       ├── bot.py                Telegram bot + alert push
    │       └── integrations/         adapter interface; Didox/Soliq/BILLZ/1C/bank mock adapters
    ├── alembic/                      migrations (0001 initial, 0002 v2)
    ├── data/
    │   ├── tac.csv                   DEMO IMEI TAC table (made up; see §17)
    │   └── samples/                  mock integration files (Didox invoice with planted errors, 1C, bank, BILLZ, Soliq)
    ├── scripts/smoke.py              calls every endpoint once against a running server
    ├── tests/                        pytest suite (temp SQLite + seed, no LLM, no Telegram)
    ├── sources.yaml                  Telegram channels by display name (usernames resolved with tg-resolve)
    ├── DECISIONS.md                  every design decision and assumption
    ├── Dockerfile, docker-compose.yml, .env.example
    ├── requirements.txt, requirements-dev.txt, pyproject.toml (ruff + pytest config)
    └── README.md                     short pointer to this file
```

---

## 4. Quick start

Requirements: Python 3.11+.

```bash
cd backend
```
```bash
python -m venv .venv && .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
```
```bash
pip install -r requirements-dev.txt
```
```bash
cp .env.example .env
```
```bash
python -m app.cli seed --reset
```
```bash
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** — it redirects to **Swagger UI** (`/docs`). Click **Authorize**, paste a demo key
(e.g. `demo-chilonzor-phone`) into `ApiKey`, and every "Try it out" call is sent with it (the key is remembered
across reloads). The Swagger page lists all demo keys and good first calls. ReDoc is at `/redoc`, the raw spec at
`/openapi.json`. On Windows, use `127.0.0.1` rather than
`localhost`: some HTTP clients try IPv6 first and add about 2 s per request.

Log in as a demo company:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/demo-login -H "Content-Type: application/json" -d "{\"company_slug\": \"chilonzor-phone\"}"
```

Then send the returned key as `X-API-Key` on every call.

**Generate a TypeScript client for the frontend:**

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.ts
```

### CLI

| Command | What it does |
|---|---|
| `python -m app.cli init-db` | Run Alembic migrations and load resolved sources from `sources.yaml` |
| `python -m app.cli seed --reset` | Drop everything, migrate, load all demo data (≈10 s) |
| `python -m app.cli tg-login` | Interactive Telegram login; prints `TG_SESSION=...` for servers |
| `python -m app.cli tg-resolve` | Find `@usernames` for the channel titles in `sources.yaml`, with confirmation |
| `python -m app.cli tg-history --limit 3000` | Import the newest messages since the last import, at most N per source (FloodWait-aware) |
| `python -m app.cli tg-history --days 30` | Import **every** message from the last 30 days (UTC) per active source, newest-first, stopping at the cutoff. Combine with `--limit` (whichever stops first). Prints scanned / kept (has a price) / skipped / oldest date per source, plus a summary; a failing source (private, renamed) is reported and skipped. Re-running only adds new posts |
| `python -m app.cli extract-once [--limit N]` | Process pending raw posts now |

---

## 5. Demo accounts and demo data

Demo keys exist only after `seed --reset`. `POST /auth/demo-login` only works with `DEMO_MODE=true`.

| Account | Type | Slug | API key |
|---|---|---|---|
| Chilonzor Phone Market | retailer (phone, laptop) — the main demo shop | `chilonzor-phone` | `demo-chilonzor-phone` |
| — its manager | user, role `manager` | — | `demo-chilonzor-manager` |
| — its appraiser | user, role `appraiser` (read-only market/stock) | — | `demo-chilonzor-appraiser` |
| TechOpt Wholesale | supplier (phone, laptop) | `techopt` | `demo-techopt` |
| Sergeli Avto | retailer (car) | `sergeli-avto` | `demo-sergeli-avto` |
| Yunusobod Realty | realtor (house, rent) | `yunusobod-realty` | `demo-yunusobod-realty` |
| Demo Lizing Bank | lender | `demo-bank` | `demo-demo-bank` |
| Malika Bozori Ma'muriyati | market admin (bazaar administration) | `bozor-admin` | `demo-bozor-admin` |
| Samarqand Darvoza Opt, Malika Gadget Opt | rated suppliers | — | `seed-305678901`, `seed-306789012` |

Admin endpoints use `X-Admin-Key` (the `ADMIN_KEY` env value, `change-me` by default).

### What the seed contains (all synthetic, marked as such in the code)

- **Market:** 2,000 listings, 400 each of phones, laptops, cars, apartments for sale and rent. They span 58 days
  with realistic base prices, ±7% noise and shops listing 4% above private sellers. 5 below-market deals are
  planted per category in the last 40 hours, which produce 25 broadcast "sourcing deal" alerts.
- **Chilonzor Phone Market:**
  - 6 months of books with planted problems: a duplicate electricity bill, an extra-zero internet bill
    (3,500,000 instead of 350,000), a qty × price ≠ total purchase, a +45% electricity spike this month, 3×
    iPhone 13 bought 20% above the fair purchase price, a Redmi Note 13 bought at both 2.5M and 3.3M, and a
    1.5M repair without a counterparty.
  - This month's budget: ads already over plan, stock purchases forecast over plan, electricity over plan.
  - 2 stores (Chilonzor, Yunusobod) and **80 units in stock**: **14 overpriced**, 2 underpriced, **6 older than 30
    days**, **8 older than 60 days**. Phones carry IMEIs matching the demo TAC table, and there are 12 sold
    iPhones for days-to-sell history.
  - An open RFQ with 2 quotes, an incoming RFQ from a peer shop, a submitted 150M loan application to the bank,
    and a connected (mock) Didox integration.
- **TechOpt:** wholesale offers and stock. **Sergeli Avto:** car books, car inventory and a `car_trade` offer.
  **Yunusobod Realty:** co-brokerage offers and commission income.
- **6 peer phone shops** with 3 months of operating costs (for the benchmark), and **2 rated suppliers**.
- **Demo Lizing Bank:** 10 collateral items (cars, apartments, one phone-stock pledge): one in **breach**
  (Malibu 2, LTV 80% vs a 70% limit) and one on **watch** (Tracker 2, 67%).
- Integration rows for every company.

Decisions are **not** seeded. `build_decisions` generates them from the engines, and the tests prove all 8 card
types appear.

---

## 6. Configuration

Everything comes from environment variables (or `backend/.env`). Defaults are shown.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./raft.db` | SQLite locally; `postgresql://…` / `postgres://…` switch to PostgreSQL with no code changes. Neon strings with `?sslmode=require` work as-is (pool: pre-ping, 3 + 2 connections, recycle every 300 s) |
| `ADMIN_KEY` | `change-me` | `X-Admin-Key` for `/admin/*` |
| `CORS_ORIGINS` | `http://localhost:3000,https://raft.vercel.app` | Comma-separated allowed origins |
| `DEMO_MODE` | `true` | Enables `/auth/demo-login` and demo companies in `/meta` |
| `AUTO_MIGRATE` | `true` | Run Alembic on startup |
| `LOG_LEVEL` | `INFO` | Log level (key=value format, secrets redacted) |
| `PORT` / `HOST` | `8000` / `0.0.0.0` | Listening port and host for `python -m app.main` and the Docker CMD (Render injects `PORT`) |
| `WORKERS_TELEGRAM` / `WORKERS_EXTRACTOR` / `WORKERS_DECISIONS` / `BOT_ENABLED` | `true` | Worker switches |
| `TG_API_ID`, `TG_API_HASH` | — | Telegram app credentials (my.telegram.org) |
| `TG_SESSION` | — | StringSession printed by `tg-login`. **The server uses only this** (no session file); the CLI may fall back to the local file. One running backend per session |
| `TG_SESSION_FILE` | `raft` | Local session file name |
| `TG_HISTORY_LIMIT` | `3000` | Messages per source for history import |
| `TG_BOT_TOKEN` | — | Bot token from @BotFather |
| `SOURCES_FILE` | `sources.yaml` | Telegram sources file |
| `GEMINI_API_KEY` | — | Optional. Without it every feature uses its rule-based fallback (voice and invoice OCR return 503) |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Model name |
| `LLM_TIMEOUT_S` | `15` | Timeout for every in-request LLM call |
| `EXTRACT_BATCH_SIZE` | `15` | Posts per Gemini extraction call |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama server for the local model |
| `LOCAL_MODEL` | `qwen2.5:3b` | Local model (must be pulled: `ollama pull qwen2.5:3b`) |
| `LOCAL_TIMEOUT_S` | `30` | Per-post timeout for the local model |
| `EXTRACT_PROVIDER_ORDER` | `local,gemini,rules` | Extraction / `/input/parse` providers, tried in order |
| `USD_UZS` | `12700` | Fallback FX rate (refreshed from cbu.uz via `/admin/fx/refresh`) |
| `MARKET_WINDOW_DAYS` | `60` | Comparable listings window |
| `MIN_COMPARABLES` | `5` | Minimum matches for a pricing tier |
| `DEAL_THRESHOLD` | `0.15` | Sourcing-deal alert threshold (15% below fair price) |
| `PRICE_CACHE_TTL_S` | `20` | Pricing cache per category |
| `SLOW_STOCK_DAYS` | `60` | Age at which stock counts as slow |
| `TURNOVER_TAX_RATE` / `VAT_RATE` / `PROFIT_TAX_RATE` | `0.04` / `0.12` / `0.15` | **VERIFY with soliq.uz** |
| `DEFAULT_LOAN_RATE` | `24` | Business-loan rate, **VERIFY with partner banks** |
| `MAX_DEBT_SERVICE_RATIO` | `0.5` | Loan payment must be ≤ 50% of average net cash flow |

Engine constants that are part of the model (not env-driven) live in `app/config.py`:
- condition multipliers, car depreciation, phone deductions, storage premium;
- dealer margins, stock turns, rent opex ratio, surplus factor;
- default days to sell, resale handling, liquidation haircuts, LTV watch margin;
- **credit products**.

---

## 7. API conventions

| Topic | Rule |
|---|---|
| Base path | Everything under `/api/v1` |
| Auth | `X-API-Key` (company key = owner, or a user key with its role). `X-Admin-Key` for `/admin/*`. 401 when missing or invalid, 403 when the role forbids the call |
| Errors | Always `{"error": {"code": "not_enough_market_data", "message": "...", "details": {...}}}` with the correct HTTP code (400/401/403/404/409/413/415/422/503). Validation errors use the same shape (`validation_error`) |
| Lists | Always `{items, next_cursor, total}`. Pass `cursor=<next_cursor>` for the next page |
| Money | Raw numbers only: `*_uzs`, `*_usd`. Text fields with formatted amounts appear only in generated messages |
| Dates | ISO 8601 UTC with `Z`. Months are `YYYY-MM` |
| Language | `Accept-Language: uz \| ru \| en` (default `uz`) controls every generated text. The copilot also detects the language of the question |
| Real time | SSE at `/market/stream` (`listing.created`, `alert.created`) and `/alerts/stream`, with a 15 s heartbeat. Polling fallback: `since_id` on `/market/listings` and `/alerts` |
| Files | Multipart upload for CSV/XLSX/images/audio (10 MB max). Deal documents come back as `text/html` or `application/pdf`. Exports as xlsx/csv/1C CSV |
| Explainability | Every computed output carries its reasons: `basis`, `comparables`, `samples` (with `source_url`), `reasons`, `transaction_ids`, `inventory_ids`, `factors`, `score_breakdown` |
| OpenAPI | Every endpoint has a Pydantic response model and a readable `operationId` (e.g. `market_price`, `exchange_accept_quote`, `stock_reprice`) |
| Speed | Dashboard and pricing respond in < 500 ms on seed data (measured on the server: dashboard ~60 ms, stock summary ~80 ms) |

---

## 8. Roles and permissions

Two layers, enforced centrally in `app/permissions.py`:

**Company role** — `retailer`, `supplier`, `realtor`, `landlord` are businesses. `lender` and `market_admin`
are partners: they may only use `/lender`, `/partner`, `/market`, `/companies`, `/alerts`, `/users`,
`/activity`, `/integrations`, `/input` and `/stores`. `/lender/*` additionally requires a `lender` company, and
`/partner/*` a lender or market admin.

**User role** (inside a company):

| Role | Access |
|---|---|
| `owner` (the company key) | everything |
| `manager` | everything except company settings (`PATCH /companies/me`), `/users` and loan applications |
| `appraiser` | read-only: market, pricing, `/stock/units`, `/stock/summary`, `/books/inventory`, input parsing |
| `lender_officer` | everything a lender company can do except managing users and company settings |

Denials return 403 `role_forbidden`. Every state-changing action is written to the **activity log** with the
acting user.

---

## 9. Endpoint reference

105 operations. Full schemas live in `/docs`. The last column maps each area to the problem it addresses.

### Platform, auth and meta (all problems)

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register a business (9-digit STIR); returns the API key once and creates a default store |
| POST | `/auth/demo-login` | API key of a seeded demo company (DEMO_MODE only) |
| GET / PATCH | `/companies/me` | Own company (incl. `plan`, `my_role`) / update it |
| GET | `/companies?role&category` | Directory with reputation (rating, ratings count, deals) |
| GET | `/companies/{id}` | One company's public profile |
| GET | `/meta` | Dropdowns and labels: categories, conditions, attribute fields, districts, roles, user roles, offer kinds, credit products, decision types, block types, integration kinds, plans, FX, currency formats, demo companies, and your stores (when called with a key) |
| GET | `/health` | DB, LLM, local model (Ollama), Telegram, extractor, bot status |
| GET | `/ping` | `{"ok": true}` — no auth, no database; for uptime pingers |
| GET | `/model` | "Our model" card — local model name, provider order, 24 h share of listings per provider (no auth) |
| GET | `/dashboard` | KPIs, top alerts, sourcing deals, open RFQs, recent deals, 6-month cash flow, **top 5 decisions**, **stock tiles** |
| GET / POST / PATCH | `/stores`, `/stores/{id}` | Stores of the company |
| GET / POST / DELETE | `/users`, `/users/{id}` | Users with roles (owner only; the key is shown once) |
| GET | `/activity?entity` | Activity log |
| GET | `/integrations` | Integration status cards (Telegram live; others mock) |
| POST | `/integrations/{kind}/sync` | Import from didox / soliq / billz / onec / bank (mock) through the upload + audit path |
| GET | `/alerts?unread_only&since_id` | Alerts addressed to you plus broadcasts in your categories |
| GET | `/alerts/stream` | SSE alerts |
| POST | `/alerts/{id}/read`, `/alerts/read-all` | Read state |

### Market engine — #19

| Method | Path | Description |
|---|---|---|
| GET | `/market/listings` | Feed: `category, model, district, condition, seller_type, min_price, max_price, since_id`, cursor |
| GET | `/market/stream` | SSE `listing.created` + `alert.created` for your categories |
| GET | `/market/stats` | Counts per category, new in the last hour, raw-post backlog, latest post, FX |
| POST | `/market/price` | **Pricing desk**: fair price, p25–p75 range, fair buy (trade-in) price, comparables, samples, basis, confidence, shop vs private prices; optional `asking_price_uzs` → "12% below market" badge |
| POST | `/market/price-from-link` | Price a `t.me/<channel>/<id>` post (DB, or a live read-only fetch when Telegram is connected) |
| GET | `/market/sourcing-radar` | Listings ≥ N% below fair price, with expected resale margin and days to sell |
| GET | `/market/trend?category&model&days` | Weekly median price and listing count |
| GET | `/market/models?category&q` | Model autocomplete by listing count |
| POST | `/market/rental-yield` | Apartment price, monthly rent, gross/net yield, payback |
| GET | `/market/heatmap?category=house\|rent` | Median price per m² / rent per Tashkent district |

### Stock command center (Narxlar) — #19, #26

| Method | Path | Description |
|---|---|---|
| GET | `/stock/units?store_id&category&rating&aging_only` | Every unit rated `underpriced / fair / overpriced / no_data`, with market range, margin at list, expected days to sell, suggested price and action, and reasons |
| GET | `/stock/summary?store_id` | Stock at cost and at market, units, overpriced, older than 30 / 60 days, margin at risk |
| POST | `/stock/reprice` | `{items:[{inventory_id,new_price_uzs}]}` or `{inventory_ids, use_suggested:true}`, atomic |
| POST | `/stock/list-on-exchange` | Create `surplus` offers from units (identical units grouped) |
| GET | `/stock/export?format=xlsx\|csv\|1c` | Stock export |

### Books: AI Auditor (#26) and Budget control (#25)

| Method | Path | Description |
|---|---|---|
| POST | `/books/upload` | CSV/XLSX import with uz/ru/en column names, or an explicit `mapping` form field; returns `{created, errors[{row,error}]}` |
| POST | `/books/upload/preview` | Detected columns, proposed mapping with confidence, first 10 parsed rows, per-row errors |
| GET | `/books/upload/template` | Example CSV |
| POST | `/books/invoice?commit` | Invoice photo → vision OCR → transactions (preview unless `commit=true`; needs Gemini) |
| GET / POST | `/books/transactions` | List (`month, category, type, store_id`) / create |
| GET | `/books/transactions/export?format&month` | xlsx / csv / 1C |
| DELETE | `/books/transactions/{id}` | Delete (exchange-booked entries are locked → 409) |
| GET | `/books/audit` | **AI Auditor**: 7 checks with `transaction_ids`, money at risk, summary, 3–5 recommendations |
| GET | `/books/benchmark` | Anonymized peer percentile of monthly operating costs (≥ 3 peers) |
| PUT / GET | `/books/budget` | Set plans / plan vs fact, month-end forecast, status, top transactions, explanations, alerts |
| GET / POST | `/books/inventory` | Inventory rows (with `list_price_uzs`, IMEI/VIN `identifier`, `store_id`) |
| GET | `/books/slow-stock` | Units older than `SLOW_STOCK_DAYS`, cash tied up, surplus price |
| GET | `/books/stock-revaluation` | Market value and unrealized margin per unit |

### Decisions queue (Bugun) — #25, #26, #19

| Method | Path | Description |
|---|---|---|
| GET | `/decisions?status&refresh` | Today's cards (built on the first call of the day, every 10 min by the worker, or with `refresh=true`) |
| POST | `/decisions/{id}/approve` | Execute the card's action exactly once (409 when already resolved) |
| POST | `/decisions/{id}/ignore` | Dismiss |

### Fast inputs — #19, #26

| Method | Path | Description |
|---|---|---|
| POST | `/input/parse` | Free text → `{category, brand, model, condition, attrs, price?, currency?, missing_fields, confidence}` |
| POST | `/input/voice` | Voice note (ogg/mp3/m4a/wav) → transcript → parsed item (503 without a Gemini key) |
| POST | `/input/imei` | Luhn check + local demo TAC lookup → brand, model, storage options |

### B2B exchange (Birja) — #19

| Method | Path | Description |
|---|---|---|
| POST / GET | `/exchange/rfqs`, `/exchange/rfqs/{id}` | Request for quotes (alerts every company in the category, returns the market estimate) / `scope=mine\|incoming` |
| POST / GET | `/exchange/rfqs/{id}/quotes` | Submit a quote / **ranked** quotes with reasons and a recommendation (buyer only) |
| POST | `/exchange/quotes/{id}/counter` | Buyer counter-offer (one round) |
| POST | `/exchange/quotes/{id}/respond` | Supplier accepts the counter or sets a final price |
| POST | `/exchange/quotes/{id}/accept` | Deal → booked in both companies' books and inventories in one transaction |
| GET | `/exchange/rfqs/{id}/matches` | Matching board offers (co-brokerage for house/rent) |
| POST / GET / DELETE | `/exchange/offers`, `/exchange/offers/{id}` | wholesale / surplus / car_trade / cobroker offers with a market badge |
| POST | `/exchange/offers/{id}/buy` | Buy from an offer → deal |
| GET | `/exchange/deals` | Your deals |
| GET | `/exchange/deals/{id}/document?format=html\|pdf` | Deal act / receipt (not a tax invoice) |
| POST | `/exchange/deals/{id}/rate` | Rate the other party (1–5, once) |
| GET | `/exchange/demand?days&category` | Most requested and most listed models, plus requests by district |

### AI Advisor (Maslahat) — #20

| Method | Path | Description |
|---|---|---|
| POST | `/advisor/chat` | **Copilot**: `{question, history, context:{screen, inventory_ids, transaction_ids, rfq_id}}` → `answer` (≤ 2 sentences), typed `blocks`, `chips`, `intent`, `used_data` |
| GET | `/advisor/cashflow?months` | Monthly income / expense / net |
| POST | `/advisor/credit` | Credit calculator per product (business_loan, auto_loan, mortgage, leasing): annuity, full schedule, affordability, max loan, LTV for asset loans |
| GET | `/advisor/tax` | Turnover tax vs VAT + profit tax for the last 3 months, with a disclaimer |
| GET | `/advisor/loan-readiness` | 0–100 score, grade A–D, factors, how to improve |
| GET | `/advisor/lenders` | Lenders you can apply to |
| POST / GET | `/advisor/loan-applications` | Apply with consent (owner only) / your applications |

### Lender & bazaar console — #20, #19

| Method | Path | Description |
|---|---|---|
| POST | `/lender/valuations` | Value an item by parameters, a `t.me` link or an applicant's `inventory_id`: fair price, range, **liquidation value**, samples; counted per lender |
| GET / POST | `/lender/collateral` | Portfolio revalued live: market value, liquidation value, LTV, status `ok / watch / breach`, 30-day value change |
| GET | `/lender/collateral/summary` | Totals, portfolio LTV, counts by status, valuations this month |
| GET | `/lender/applications`, `/lender/applications/{id}` | Applications with the frozen snapshot of the borrower's numbers |
| POST | `/lender/applications/{id}/decision` | `reviewing / approved / rejected` + note → alerts the borrower |
| GET | `/partner/market-report?category&district&days&format=json\|xlsx` | Median price and volume per model and district, weekly trend, listings by seller type |

### Admin (`X-Admin-Key`)

| Method | Path | Description |
|---|---|---|
| GET | `/admin/status` | Raw-post counters, listings, active sources, worker states, FX |
| GET / POST / PATCH | `/admin/sources`, `/admin/sources/{id}` | Telegram sources (the listener reloads without a restart) |
| POST | `/admin/telegram/history?limit&days` | Background history import (`days=30`: everything from the last 30 days) |
| POST | `/admin/extract/run?limit` | Run the extractor now |
| GET | `/admin/raw-posts?processed` | Raw posts (0 new, 1 done, 2 failed, 3 skipped) |
| GET / POST | `/admin/fx/refresh` | Pull today's USD/UZS rate from cbu.uz |

---

## 10. How the engines work

### 10.1 Fair-price engine (`services/pricing.py`)

1. Load non-duplicate listings of the category from the last `MARKET_WINDOW_DAYS` (cached for 20 s, memoized per
   item).
2. Try **comparable tiers from strict to loose**. The first tier with ≥ `MIN_COMPARABLES` (5) matches wins;
   otherwise the largest tier with ≥ 3 is used with `confidence: low`; otherwise 422 `not_enough_market_data`.

   | Category | Tiers |
   |---|---|
   | phone | model + storage + condition → model + storage → model |
   | laptop | model + RAM + SSD + condition → model → CPU class + RAM |
   | car | model + year ±1 + mileage ±30,000 km + fuel → model + year ±2 → model |
   | house | district + rooms + building → district + rooms → district → rooms citywide (**price per m² × area**) |
   | rent | district + rooms + furnished → district + rooms → rooms citywide (monthly only) |

3. **Normalize every comparable to the target:**
   - condition multipliers: new 1.0, A 0.88, B 0.78, C 0.62;
   - storage +12% per doubling;
   - phones: IMEI not registered −15%, repaired −8%;
   - cars: 6% depreciation per model year.
4. With ≥ 10 values, trim the outer 10%. Then: **fair price = median**, **range = p25–p75**, **fair buy price =
   fair × (1 − dealer margin)**, where the margin is phone 15%, laptop 15%, car 8%, house 5%, rent 0%.
5. **Confidence:** `high` = strictest tier with ≥ 10 matches, `medium` = any tier with ≥ 5, `low` = fallback.
   The output also includes `samples` (5 most recent, with Telegram links), `basis` in plain words, and shop vs
   private medians.

### 10.2 Telegram → listing pipeline (`telegram_ingest.py`, `extractor.py`)

1. **Filter:** keep posts with ≥ 15 characters and a price signal (`$`, `у.е`, `so'm`, `сум`, `mln`, `ming`,
   `narx`, `цена`, or a 6+ digit number).
2. **Remove personal data** before storing (ZRU-547): Uzbek phone numbers, `@usernames`, `t.me` and other links.
   Senders of group messages are never stored. The account never posts.
3. **Extract** through the provider chain `EXTRACT_PROVIDER_ORDER` (default `local,gemini,rules`, see
   [§10.12](#1012-local-model-ollama)). The **local model** (Ollama) reads one post per call. **Gemini** reads
   batches of 15 posts in one JSON-mode call; a wrong-length or invalid answer is retried once in halves. The
   **rule parser** (price regexes, a model dictionary from the market, year, mileage, rooms, area) never fails.
   A post that a provider can't handle falls through to the next one. The prompts cover uz (Latin and Cyrillic)
   and ru, skip rules, currency rules (`5.2 mln` = 5,200,000; `250 ming` = 250,000; car/house prices without a
   currency are USD) and per-category attributes. Model-read prices are cross-checked against the rule parser
   (more than 1% apart → the rule price wins). Each listing records its extractor in `attrs._extracted_by`.
4. **Validate:** convert to UZS and USD, drop prices outside 0.3×–3× of the fair price, and flag reposts as
   duplicates (same text hash, or same model and price within 7 days from another source).
5. **After insert:** invalidate the price cache, publish `listing.created` over SSE, and run the **deal check**.
   A listing ≥ 15% below a medium/high-confidence fair price creates a broadcast `sourcing_deal` alert.

### 10.3 AI Auditor (`books.py`)

Seven deterministic checks, each returning `type, severity, message, transaction_ids, amount_at_risk_uzs`:

1. **Duplicates:** same date + category + counterparty + total + model.
2. **qty × unit price ≠ total** (more than 1% off).
3. **Extra-zero typos:** ≥ 5× the category median and ≈ the median once divided by 10.
4. **Same model bought at prices > 25% apart.**
5. **Utility cost spikes:** more than 30% above the previous 3-month average (rent, electricity, gas, water,
   internet), ignoring rows already flagged as duplicates or typos.
6. **Overpayment:** stock bought more than 10% above the live market fair buy price.
7. **Expenses over 1,000,000 so'm with no counterparty.**

Recommendations (3–5) are phrased by the LLM from the flags, or come from templates.

### 10.4 Budget control

For every expense category: plan, actual, % used, **month-end forecast**, status `ok / at_risk / over / no_plan`,
the top 3 transactions behind it, and a plain-language explanation.
- Spending categories are extrapolated by days elapsed.
- Monthly bills (rent, utilities, salaries, taxes) are not extrapolated; if this month's bill hasn't arrived,
  last month's amount is used.
- `at_risk` = forecast above plan, or ≥ 90% used for spending categories.
- A `budget` alert fires at most once per category per day.

### 10.5 Stock command center (`stock.py`)

- **Rating:** list price > p75 × 1.01 → `overpriced`; < p25 × 0.99 → `underpriced`; otherwise `fair`. No list
  price or no market data → `no_data`.
- **Suggested price:**
  - aging (> 60 days) → p25 (`list_on_exchange`);
  - overpriced → median (`reprice_down`);
  - underpriced → max(median, cost × 1.03) (`reprice_up`);
  - otherwise keep.
- **Expected days to sell:** the median of the company's own sales in that category when there are ≥ 5 (FIFO links
  via `sold_at`), else the defaults (phone 21, laptop 30, car 45). Then × 1.3 if overpriced, × 0.8 if
  underpriced.
- **Margin at risk** = Σ (list − suggested) on overpriced units plus the cash tied up in aging units.
- Pricing is batched: one engine pass per identical (category, model, condition, attributes) group.

### 10.6 Decisions queue (`decisions.py`)

Up to 8 cards, one per type, sorted by amount. Every card has `amount_uzs`, `reasons`, `transaction_ids` /
`inventory_ids` and an `action` describing what Approve does.

| Type | Source | Approve does |
|---|---|---|
| `reprice` | overpriced, non-aging units | bulk reprice to the suggested prices |
| `slow_stock` | units > 60 days | list them on the exchange as surplus |
| `duplicate_invoice` | audit duplicates | delete the extra rows (never exchange-origin ones) |
| `typo_amount` | audit extra-zero | correct the total to /10 (old value noted) |
| `overpayment` | audit overpayment | create an `audit` alert + note; no money moves |
| `budget_limit` | budget at risk / over | acknowledge (shows a weekly spending limit) |
| `deal_to_buy` | sourcing radar | add to the watch list |
| `rfq_quote` | incoming RFQ you haven't quoted | acknowledge (the frontend opens the quote form) |

The build is idempotent: cards are refreshed in place, stale cards expire, and cards resolved today aren't
recreated. Approve claims the card with a conditional update, so it runs exactly once and rolls back on failure.

### 10.7 B2B exchange (`exchange.py`)

- **Quote ranking (0–100):** price 50% (best/this), supplier rating 20% (0.6 × 20 if unrated), delivery speed 15%,
  quantity coverage 15%; −15 points when the price is above the retail market. Each quote gets plain-language
  `reasons` and `vs_fair_purchase_pct`, and there is an overall recommendation with the saving vs the most
  expensive quote.
- **Counter-offers:** one round per quote. The supplier accepts or sets a final price, and the quote returns to
  `pending`.
- **Deals** are booked in one DB transaction:
  - buyer: expense `stock_purchase`; seller: income `sale`;
  - seller inventory decremented FIFO; buyer gets a new stock line in its main store;
  - other quotes rejected, RFQ awarded, both sides alerted.
  Conditional status updates make double-booking impossible.
- **Co-brokerage:** house/rent requests match realtor offers by district, rooms and budget (offers up to 110% of the target) and show the
  commission split.

### 10.8 Copilot (`copilot.py`)

1. **Intent router:** keyword rules in uz/ru/en across 9 tools (price, stock, audit, budget, cash flow, credit,
   tax, loan readiness, demand) plus overview. Then the screen context and selected rows. The LLM is used only to
   pick an intent name when the rules fail. Questions about opening a branch or expanding route to **credit**
   (how much the business can borrow), and "business plan" questions route to **loan readiness**; both answer
   only with numbers the calculators already produce.
2. **The tool runs in Python** and builds 1–2 typed **blocks** and 2–3 **chips**. Chips are
   `{label, action:{endpoint, method, body}}` that the frontend can run.

   | Block | Content |
   |---|---|
   | `price_range` | fair, p25, p75, your price, buy price |
   | `comparables` | up to 5 samples with links |
   | `kpi_row` | 2–4 numbers with optional deltas |
   | `bar_chart`, `line_chart` | `{x, series:[{name, values}]}` |
   | `table` | `{columns, rows, row_ids}` |
   | `steps` | ordered steps with `done` / `todo` |
   | `loan_schedule` | payment, total interest, first 12 schedule rows |
   | `file` | `{title, url, mime}` (documents and exports; no current tool emits it) |

3. **Answer:** a 2-sentence template per intent. If Gemini is configured it may rephrase ("keep every number
   exactly"). Blocks are built before the LLM call and returned unchanged (tested).

### 10.9 Finance (`finance.py`)

- **Cash flow:** monthly income / expense / net. "Average net" = mean of the last 3 complete months.
- **Credit:** annuity P·r / (1 − (1 + r)^−n), full schedule (Σ principal = principal exactly), affordability
  (payment ≤ 50% of average net), max loan for 12/24/36 months, LTV for asset loans. Products (placeholders,
  **VERIFY with partner banks**):

  | Product | Rate | Max months | Down payment |
  |---|---|---|---|
  | business_loan | 24% (`DEFAULT_LOAN_RATE`) | 36 | 0% |
  | auto_loan (dealer stock) | 26% | 60 | 20% |
  | mortgage | 18% | 240 | 30% |
  | leasing | 28% | 36 | 20% |

- **Tax** (last 3 complete months, rates from config, **VERIFY with soliq.uz**): turnover tax = income × 4%, vs.
  VAT (12%, VAT-inclusive, input VAT from purchases except salaries and taxes) + 15% profit tax. Returns which
  regime is cheaper and a disclaimer.
- **Loan readiness (0–100):**

  | Factor | Points | Rule |
  |---|---|---|
  | Data history | 25 | months with records; 6 = full |
  | Profitability | 25 | net margin / 15% |
  | Stability | 20 | variation of monthly net: ≤ 0.2 full, ≥ 1 zero |
  | Bookkeeping | 15 | −5 per open high-severity audit flag |
  | B2B reputation | 15 | deals (8) + rating (7) |

  Grades: A ≥ 80, B ≥ 65, C ≥ 50, D otherwise. Tips are given for weak factors.

The roadmap maker (expansion planner and business-plan generator) was removed; see `DECISIONS.md`.

### 10.10 Lender console (`lender.py`)

- **Liquidation value** = p25 × (1 − haircut): car 10%, house 10%, phone 20%, laptop 25%.
- **Collateral:** revalued live (batched). LTV = loan balance / market value. Status `breach` when above the
  limit (default 0.7), `watch` within 5 points of it. A breach alerts the lender once per item per day.
  `value_change_30d_pct` comes from the trend.
- **Loan applications:** owner only, `consent: true` required. At submission a snapshot is frozen: readiness
  with factors, 6-month cash flow, audit summary, stock at market, the credit calculation, and pledged units at
  market value. The lender sees exactly these numbers.

### 10.11 Fast inputs (`inputs.py`)

- **Free text:** a rule parser (model dictionary from the market, regexes for storage, battery %, year, mileage
  "45 ming probeg", trim "pozitsiya", rooms "2 xona", area "55 kv", prices in mln/ming/$). Gemini can add text
  fields; any price always comes from the rules. Missing required fields are listed, so the UI can ask for them.
- **IMEI:** Luhn check + local demo TAC table. No external IMEI services.
- **Links:** DB first, then a single read-only Telegram fetch through the normal pipeline.

### 10.12 Local model (Ollama)

Extraction (and `/input/parse`) runs first on a **local model served by Ollama**, by default `qwen2.5:3b`. It
needs no API key, sends no data off the machine and has no per-call cost. Copilot answers and audit
recommendations do **not** use it: they stay on Gemini or the templates.

**Setup:**

```bash
ollama pull qwen2.5:3b
```
```bash
curl http://127.0.0.1:11434/api/tags
```

Ollama runs as a background service after installing it from https://ollama.com. The settings are `OLLAMA_URL`
(default `http://127.0.0.1:11434`), `LOCAL_MODEL`, `LOCAL_TIMEOUT_S` (30) and `EXTRACT_PROVIDER_ORDER`.

**How it is called:** `POST {OLLAMA_URL}/api/chat` with `stream: false`, `format: "json"`,
`options: {temperature: 0, num_ctx: 2048}`.
- **One post per call** (small models are steadier that way), with the same instructions and JSON schema as
  Gemini plus **6 short few-shot examples**: a phone in Uzbek Latin with `mln`, a car with `probeg` /
  `pozitsiya` / `kraskasi yo'q`, a Russian rental with furniture and utilities, a Russian laptop priced in `$`,
  an apartment in Uzbek Cyrillic with no currency, and a "sotib olaman" buying post that must return
  `skip: true`.
- The prompt is about 1,600 tokens; posts are capped at 600 characters so prompt + answer fit the 2,048-token
  window.
- On this machine a post takes about 0.5–2 s.

**Fallback chain** (`local → gemini → rules`, per post):

| Local model outcome | What happens |
|---|---|
| valid JSON that passes the extraction schema (`ExtractedItem`) | used; listing gets `_extracted_by: "local:qwen2.5:3b"` |
| invalid JSON, schema failure, HTTP error, timeout | this post falls through to Gemini (if a key is set), then the rule parser |
| Ollama not running (connection refused) | local is skipped for the rest of the batch and paused for 30 s |

**Price safety:** the model reads the price, and the rule parser's regex price for the same post is the check.
If both found a price and they differ by more than 1% (after the same currency and "mln" normalization), the rule
price is used and a warning is logged. This applies to Gemini output as well.

The regex parser ranks all candidates rather than taking the first one:
- a price after `narxi` / `нархи` / `цена` / 💰 / 💵 beats one followed by a currency or `mln`/`ming`, which beats
  a bare `$`;
- `4 mln 600 ming` is read as 4,600,000;
- installment terms (`79$ 6 oy`) and model numbers (`A54 $260`) are not mistaken for prices.

Long posts are clipped head + tail, because shops put the price at the bottom.

**Visibility:**
- `GET /api/v1/health` → `local_model`: reachable and pulled, or why not.
- `GET /api/v1/model` (no auth) → model name, provider order, and the share of the last 24 h of Telegram
  listings each provider extracted. This is the "Our model" card.

**Comparing providers:**

```bash
python -m app.cli reextract --provider local --limit 50
```

It re-runs one provider (`local`, `gemini` or `rules`) on already-processed posts, **without writing**, and
prints how many fields differ from the stored listing (category, brand, model, condition, price, district,
seller type, each attribute).

---

## 11. Telegram: ingestion and bot

### Log in (read-only user account)

1. Create an app at https://my.telegram.org → *API development tools*. Put `TG_API_ID` and `TG_API_HASH` in
   `.env`.
2. Run `python -m app.cli tg-login` and enter your phone, code and 2FA password. It saves `raft.session`
   locally (used by the CLI) and prints `TG_SESSION=…`. **The server needs `TG_SESSION`**; without it the
   listener stays off with a warning. **Treat it like a password.**

### Resolve channels

`sources.yaml` lists 19 channels by display name (cars, rent, phones, laptops; the house-sale slot is kept
empty), with `username: TODO`, a `category_hint` (`phone | laptop | car | house | rent | mixed_tech |
mixed_realty | mixed`) and a default seller type (`shop` for stores, `private` otherwise).

```bash
python -m app.cli tg-resolve
```

For each title it searches Telegram, shows candidates (username, subscribers, last post date) and writes the
usernames you confirm back to `sources.yaml` and the database. Sources can also be added at runtime with
`POST /api/v1/admin/sources`.

### Import and run

```bash
python -m app.cli tg-history --days 30
```

The live listener starts with the server (`WORKERS_TELEGRAM=true`). The extractor processes the backlog every
5 s.

### Bot (`TG_BOT_TOKEN`)

| Input | Reply |
|---|---|
| `/start`, `/help` | Help text |
| `/link <API_KEY>` | Connects the chat to a company (company or user key) |
| `/budget` | Budget status and explanations |
| `/audit` | Auditor summary and top issues |
| `/deals` | Below-market listings in your categories |
| `/rfqs` | Open incoming requests for quotes |
| `/price <free text>` | Parse + market price (+ badge if you include a price) |
| Photo of an invoice | Vision OCR → transactions added (needs Gemini) |
| Forwarded channel post | Priced with a "X% below/above market" badge |
| Voice note | Transcribed and priced (needs Gemini) |

**Alert push:** every 5 s, unsent alerts go to linked chats; broadcasts fan out by category. Alerts older than
30 minutes are marked sent without sending, so linking a chat doesn't flood it.

---

## 12. Integrations

`GET /integrations` returns a card per kind; `POST /integrations/{kind}/sync` imports through the normal upload
→ audit path and returns the audit flags on the imported rows. Imported invoice numbers are remembered, so
syncing twice imports nothing.

| Kind | Mode | What the sync does |
|---|---|---|
| `telegram` | **live** | Status of the listener, active sources, last post time (syncs continuously) |
| `didox` | mock | Imports `data/samples/didox_invoice.json`, a demo e-invoice with **a wrong total** and **an above-market iPhone 14 purchase** that the auditor catches |
| `soliq` | mock | Imports `soliq_invoices.json` (a clean internet bill) |
| `onec` | mock | Imports `onec_transactions.csv` (1C export layout) |
| `bank` | mock | Imports `bank_statement.csv` |
| `billz` | mock | Imports `billz_stock.csv` into inventory |

Adapters share one interface in `services/integrations/`. **Real access to Didox, Soliq, BILLZ, 1C or bank APIs
needs partner agreements**; until then the responses say `mode: "mock"`.

---

## 13. Data model

| Table | Purpose |
|---|---|
| `companies` | Businesses and partners: STIR, role, categories, district, tax regime, plan, hashed API key, Telegram chat |
| `users` | Users inside a company with a role and hashed API key |
| `stores` | Shops of a company (inventory, transactions and budgets can point to a store) |
| `sources` | Telegram channels/groups: username, category hint, default seller type, last message id |
| `raw_posts` | PII-stripped posts: source, message id, text, text hash, processed state (0/1/2/3), error |
| `listings` | Structured market listings: category, brand, model (+ normalized), condition, price (orig/UZS/USD), district, attrs (JSON), seller type, source URL, duplicate flag, fair price, discount |
| `transactions` | Books: income/expense, category, item fields, qty, unit price, total, counterparty, origin, deal, store |
| `inventory` | Stock units: cost, list price, IMEI/VIN, acquired/sold dates, status, store |
| `budgets` | Plan per company / month / category |
| `rfqs`, `quotes`, `offers`, `deals`, `ratings` | B2B exchange (quotes carry counter-offer fields) |
| `alerts`, `alert_reads` | Alerts (texts in uz/ru/en in the payload); per-company read state for broadcasts |
| `decisions` | Decision cards: type, key, payload (texts, ids, action), amount, status, resolved by/at |
| `loan_applications` | Borrower → lender applications with the frozen snapshot and consent time |
| `collateral` | Lender portfolio items with loan balance and LTV limit |
| `integrations` | Status per company and kind, last sync, imported ids |
| `activity_log` | Who did what, when |

Category-specific attributes (storage, RAM, year, mileage, rooms, area, furnished, …) are JSON `attrs`; their
names, types, units and labels are served by `/meta`. Migrations: `alembic/versions/0001` (v1) and `0002` (v2).

---

## 14. Testing, linting and the smoke run

```bash
cd backend && pytest -q
```

162 tests run on a temporary SQLite database with seed data, **no LLM and no Telegram**. Test modules that change
seed data use a module-scoped reseed fixture.

| Test file | Covers |
|---|---|
| `test_auth_meta.py` | registration, error format, 401/403, `/meta`, `/health`, operation IDs |
| `test_market.py` | pricing for all 5 categories (< 500 ms), badges, condition ordering, IMEI deduction, feed, radar, trend, heatmap, yield |
| `test_books.py` | **every planted audit problem**, budget statuses, benchmark, slow stock, revaluation, upload, CRUD, 413, invoice without LLM |
| `test_exchange.py` | RFQ → quotes → ranking → accept → deal in both books → inventory moved → ratings; offer buy; co-brokerage; demand |
| `test_advisor.py` | annuity against a known value, credit, tax, readiness bounds, chat fallback, dashboard shape and speed |
| `test_ingest.py` | PII stripping, price parsing (`mln` / `ming` / `$`), extractor with a **mocked LLM** (retry in halves), reposts, deal alerts, outliers, rule fallback, admin, SSE |
| `test_bot.py` | bot commands, alert fan-out |
| `test_platform.py` | roles (appraiser / manager / partner 403s), users, stores, activity, `/meta` additions |
| `test_stock.py` | planted 14 overpriced / 6 aging / 8 slow, rules, atomic reprice, store filter, < 500 ms, exports |
| `test_decisions.py` | all 8 decision types from the seed, idempotent build, approve exactly once, duplicate gone after approve |
| `test_copilot.py` | every intent → expected block types, roadmap questions → credit / loan readiness, chips point at real endpoints, blocks untouched by the LLM, schedules, mortgage LTV, removed roadmap endpoints return 404 |
| `test_lender.py` | liquidation < fair, breach/watch detection and alert once a day, consent required, snapshot contains the score, market report |
| `test_inputs.py` | the three free-text examples, IMEI Luhn + TAC, upload preview + mapping, link pricing (DB and mocked Telegram), voice 503 |
| `test_v2_exchange_integrations.py` | counter-offer flow, deal document, demand by district, radar fields, Didox sync catches planted errors, bot additions |
| `test_regressions.py` | bugs found by the live smoke run |
| `test_architecture.py` | import-direction rules of the modular monolith, package READMEs |
| `test_local_llm.py` | local model (mocked Ollama): one post per call + few-shots, invalid JSON → Gemini, timeout → rules, Ollama down → skipped, price mismatch → rule price, `/input/parse` order, copilot never uses it, `/health` + `/model`, `reextract` |
| `test_hosting.py` | `/ping` without auth or DB, Neon pool settings, `PORT`, lazy pandas/openpyxl/WeasyPrint, workers off without secrets |

```bash
ruff check app tests scripts
```

**Smoke run:** with the server running, this calls every endpoint once with the demo keys and prints the status
and timing of each. It writes demo actions (RFQs, deals, uploads) into the target database. Add `--no-extract`
on a database whose Telegram backlog must stay untouched (otherwise it processes one pending post):

```bash
python scripts/smoke.py http://127.0.0.1:8000 <ADMIN_KEY> --no-extract
```

---

## 15. Deployment

### Run it on this machine (current setup)

Raft is hosted locally: one process on this computer, SQLite in `backend/raft.db`, and the local model in Ollama.

```bash
start-raft.cmd
```

Double-click it, or run it from a terminal (`.\start-raft.ps1` in PowerShell). The script:
- checks the virtualenv, `backend\.env` and Ollama (`qwen2.5:3b`);
- starts the API on `127.0.0.1:8000` with every worker from `.env`: Telegram listener, extractor, decisions
  and bot;
- writes the log to `backend\logsaft-YYYYMMDD.log`.

Stop it with Ctrl+C.

| Option | Effect |
|---|---|
| `-Lan` | listen on `0.0.0.0` so other devices on the same network can use it (Windows may ask for firewall access) |
| `-NoExtractor` | leave pending Telegram posts unprocessed (the extractor otherwise works through them in the background) |
| `-Port 9000` | another port |

Checks after starting:
- **Swagger:** http://127.0.0.1:8000/docs
- **Status:** http://127.0.0.1:8000/api/v1/health shows the DB, Gemini, local model, Telegram listener,
  extractor and bot.
- **Model card:** http://127.0.0.1:8000/api/v1/model.

To reach it from the internet (e.g. a hosted frontend), run `cloudflared tunnel --url http://localhost:8000`
(see [docs/DEPLOY.md](docs/DEPLOY.md) §5) and add the frontend origin to `CORS_ORIGINS`.

> **Never run `python -m app.cli seed --reset` on this database.** It drops everything, including the imported
> Telegram posts.

The Render + Neon setup below is kept for later.

### Free cloud hosting (later)

Full guide: [docs/DEPLOY.md](docs/DEPLOY.md).

| Piece | Where | Notes |
|---|---|---|
| API | **Render** free Docker web service, from [`render.yaml`](render.yaml) | `PORT` injected; one uvicorn worker; health check `/api/v1/ping`; migrations on startup |
| Database | **Neon** free PostgreSQL | paste the connection string (`?sslmode=require`) into `DATABASE_URL`; seed once from your laptop: `DATABASE_URL=<neon> python -m app.cli seed --reset` |
| Keep-alive | **cron-job.org** | `GET /api/v1/ping` every 10 min (free Render services sleep after ~15 min idle) |
| Frontend | **Vercel** or **Cloudflare Pages** | set `CORS_ORIGINS` on the API to the frontend origin(s) |
| From a laptop | **Cloudflare quick tunnel** | `cloudflared tunnel --url http://localhost:8000` → public `https://….trycloudflare.com` |

Free-tier fit:
- Memory stays under Render's 512 MB: pandas, openpyxl and WeasyPrint are imported only inside the functions
  that use them, and the startup log prints the process memory.
- Missing `TG_SESSION`, `TG_BOT_TOKEN` or `GEMINI_API_KEY` only switch that feature off, with a warning in the
  log; the API keeps running.
- **Only one running backend may use a given `TG_SESSION`** (and bot token) at a time.

### Docker (any host)

```bash
docker compose up --build
```

`docker-compose.yml` runs the API image with PostgreSQL 16. The image runs
`uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` and includes the WeasyPrint system libraries for
PDFs. Seed once with `docker compose exec api python -m app.cli seed --reset`.

---

## 16. 5-minute demo script

Start from a fresh `seed --reset`. Keys are in §5.

1. **Live feed.** As Chilonzor, open `GET /market/stream`.
   - `POST /market/price-from-link` with a `t.me` link turns that post into a priced listing with a "X% below
     market" badge.
   - Without a Telegram login, show `GET /market/listings` and `GET /market/sourcing-radar` instead.
2. **Stock center.** `GET /stock/summary` shows 80 units, 14 overpriced, 6 older than 30 days and 8 older than
   60.
   - `GET /decisions` → approve the "14 units are priced above market" card; the overpriced count drops to 0.
   - In the copilot, ask "Nega bu qimmat?" with selected units → price range block + reprice button.
3. **Didox sync.** `POST /integrations/didox/sync` → the auditor flags the wrong total (4 × 2.8M ≠ 12.2M) and
   the iPhone 14 bought far above market.
4. **Budget.** `GET /books/budget` → ads over plan, stock purchases forecast over plan, a budget alert. With
   `/link demo-chilonzor-phone` in the bot, the alert arrives in Telegram.
5. **Loan.** Chilonzor's 150M application is already submitted. As `demo-demo-bank`:
   - `GET /lender/applications/{id}` shows the same readiness score, cash flow and audit numbers the shop sees;
   - `GET /lender/collateral` revalues the portfolio live (one breach, one watch);
   - `POST /lender/applications/{id}/decision` notifies the shop.

---

## 17. Before going live: manual checklist

- [ ] **Telegram login:** `python -m app.cli tg-login`; set `TG_SESSION` on the server
- [ ] **Resolve the 19 channel usernames:** `python -m app.cli tg-resolve`, then `tg-history`
- [ ] **Gemini key** (`GEMINI_API_KEY`) for voice input, invoice OCR and LLM extraction/phrasing
- [ ] **Bot token** (`TG_BOT_TOKEN`) from @BotFather
- [ ] **Verify tax rates** (`TURNOVER_TAX_RATE`, `VAT_RATE`, `PROFIT_TAX_RATE`) and regime eligibility on soliq.uz
- [ ] **Verify credit product rates, terms and down payments** (`DEFAULT_LOAN_RATE`, `CREDIT_PRODUCTS`) with
      partner banks
- [ ] **Replace `data/tac.csv`** with a licensed TAC source (GSMA); the current table is made-up demo data
- [ ] **Didox / Soliq / BILLZ / 1C / bank API agreements**; until then the adapters are mock-only
- [ ] Set a strong `ADMIN_KEY`, set `CORS_ORIGINS` to the real frontend domain, and set `DEMO_MODE=false` in
      production
- [ ] Run a single instance of the backend (Render free plan = 1 instance); one backend per `TG_SESSION`

---

## 18. Known limitations

- **All seed numbers are synthetic** (prices per model, per m², rent ratios, books). They are realistic-looking
  placeholders, not market research.
- **Not yet exercised against real services:** Gemini (extraction, OCR, voice, phrasing), fetching a new post
  from Telegram by link, and the bot's forward and voice handling. Tests cover them with mocks or the no-key
  path.
- Tax and credit figures are estimates for planning, not advice. The responses carry disclaimers.
- Deal documents are records, not tax invoices; e-invoices must be issued in Didox/Soliq.
- Budgets are company-wide (`store_id` exists, but the unique key is per company, month and category).
- Decision-queue build state and pricing/audit caches are in process memory, which is fine for the single
  replica this design requires.
