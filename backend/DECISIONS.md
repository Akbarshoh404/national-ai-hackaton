# Decisions

Choices made while building, where the spec left room. Grouped by area.

## Platform
- **Demo API keys are deterministic** (`demo-<slug>`) so `/auth/demo-login` can return them while keys stay
  hashed (sha256) in the DB. Registered companies get random `bp_…` keys. Extra seeded companies (peers,
  suppliers) use `seed-<stir>`, e.g. `seed-305678901` for Samarqand Darvoza Opt.
- `companies.slug` was added (nullable, unique) for demo login.
- **Generated text is stored in all three languages.** Alerts keep `payload.i18n.{uz,ru,en}` and the API picks the
  one matching `Accept-Language`; the `title`/`message` columns hold the Uzbek text.
- **Broadcast alerts** (`company_id = NULL`, e.g. sourcing deals) are visible to every company trading in the
  category; per-company read state is in a small `alert_reads` table. RFQ, quote, deal and budget alerts are
  per-company rows.
- `raw_posts.text_hash` added for repost detection; `listings.fair_price_uzs` / `discount_pct` added so the
  sourcing radar is a plain indexed query and never runs the price engine inside a request.
- Paginated lists use an id cursor (`next_cursor` = last id). `/companies` uses an offset cursor because it
  filters JSON categories in Python.
- `/books/benchmark` returns `enough_peers: false` (200) instead of an error when there are fewer than 3 peers,
  so the frontend can render an empty state.
- `GET` and `POST /admin/fx/refresh` both exist (the spec names both) with separate operation IDs.
- Startup runs Alembic (`AUTO_MIGRATE=true`); tests use `create_all`. `seed --reset` drops all tables
  (including `alembic_version`) and migrates again.

## Price engine
- Comparables are always normalized to the target (condition, IMEI, repairs, storage, model year), even in the
  strict tiers. When the attributes match, the factor is 1, so this only makes the result more precise.
- **Storage adjustment** (+12% per storage doubling) is also applied in the loose phone tier. That is the same
  factor the seed uses; without it, 128 GB and 256 GB listings would be mixed unadjusted.
- A missing phone/laptop condition is treated as "A" when normalizing.
- **Confidence:** high = strictest tier with ≥ 2 × MIN_COMPARABLES; medium = any tier with ≥ MIN_COMPARABLES;
  low = fallback tier with 3–4 matches. Deal alerts, overpayment flags and outlier rejection ignore low.
- House estimates without `area_m2` use the median total price instead of price per m² × area.
- Rent's `fair_buy` margin is 0 (there is no trade-in price for a rental).
- Estimates are memoized until the 20 s comparables cache expires; inserts invalidate the category.

## Extraction
- **Without `GEMINI_API_KEY`, a rule-based parser runs instead of the LLM** (price regexes for `$`, `у.е.`,
  `mln`, `ming`, `so'm`; model matching against known models; year, mileage, rooms, area). It is less
  thorough but keeps the pipeline alive.
- If the LLM returns UZS with a value below 1000, it is treated as millions (the model dropped "mln").
- Prices with no currency: car/house → USD; otherwise USD if below 20,000, else UZS.
- Reposts are stored but flagged `is_duplicate` (excluded from pricing, the feed and alerts) so the data stays
  auditable.
- Default `seller_type`: phone/laptop channels and the two dealer car channels → `shop`; `autoseyll` and the
  rent channels → `private`. The LLM can override this per post.

## Books, budget, audit
- **Spike check** looks at the last 2 months and ignores rows already flagged as duplicates or extra-zero
  typos, so one typo can't hide or fake a spike. It needs at least 2 prior months.
- **Extra-zero check** applies to operating expenses (not stock purchases). It needs ≥ 4 rows in the category and
  compares each row to the median of the *other* rows.
- **Price-spread check** groups purchases by model + condition + storage.
- **Budget forecast:** spending categories are extrapolated by days elapsed. Monthly bills (rent, utilities,
  salaries, taxes) are not; when this month's bill hasn't arrived yet, the forecast uses last month's amount.
  `at_risk` = forecast above plan, or ≥ 90% used for spending categories.
- Invoice OCR previews by default (`?commit=true` saves). The bot saves straight away and replies with what it
  added.
- Audit results are cached per company for 60 s, keyed on the transaction count and max id.

## Exchange
- **Quote ranking** follows the spec weights. Price score = 50 × best/this; delivery = 15 × (min+1)/(days+1);
  unrated suppliers get 0.6 × 20. "Saving vs worst" is (most expensive price − recommended price) × quantity.
- Deals are protected by conditional `UPDATE … WHERE status = 'open'/'pending'` (and `qty >= n` for offers)
  inside one DB transaction, so a deal can never be booked twice, even under concurrent requests.
- Seller inventory is decremented FIFO by matching model and condition. If the seller has too little stock,
  the deal still goes through (their books may be incomplete).
- Co-brokerage offers can't be bought (400). They are matched via `/rfqs/{id}/matches` with the commission split.

## Advisor
- "Average net cash flow" = mean of the last 3 **complete** months that have data.
- **Tax model** (estimate, rates from config marked VERIFY): turnover tax = income × 4%. The VAT regime treats
  amounts as VAT-inclusive: output VAT from income, input VAT from all expenses except salaries and taxes,
  profit tax 15% on the net-of-VAT profit.
- **Loan readiness:** history = months with data (6 = full); profitability = net margin / 15%;
  stability = coefficient of variation of monthly net (≤ 0.2 full, ≥ 1.0 zero); books = 15 − 5 per open
  high-severity flag; reputation = deals (up to 5 → 8 pts) + rating (7 pts, 0.6 × 7 if unrated).
- **Expansion (goods):** top 3 models by listing volume, each at its most common market configuration; stock
  budget split by volume; extra monthly opex of the new point = current monthly opex; break-even = setup cost /
  monthly net profit.
- PDF needs WeasyPrint (installed in the Docker image). Locally without it, `format=pdf` returns the HTML with an
  `X-PDF-Fallback` header.

## Telegram
- The bot only pushes alerts younger than 30 minutes; older unsent ones are marked sent, so linking a chat
  doesn't flood it with history.
- The listener reloads sources when an admin change bumps a version counter. Albums are handled once per
  `grouped_id` (caption only).
- If the session isn't authorized, the listener goes idle with status `error` instead of crash-looping.

## Seed (synthetic!)
- 400 listings per category over 58 days, σ = 7% noise, shops list 4% above private sellers, 5 planted
  below-market deals per category in the last 40 hours. All of this is marked synthetic in `app/seed.py`.
- Chilonzor's planted problems are generated relative to today, so they work on any date. The one exception:
  on the last day of a month, `stock_purchase` is `at_risk` via the ≥ 90% rule rather than the forecast.
- The seeded RFQ has two quotes. The better-rated supplier (Samarqand, 4.67★, 3 days, full qty, 0.99 ×
  fair buy) beats a pricier, partial, slower one (Malika, 3.75★).

---

# v2 decisions (B2B command center, lender console, rich answers)

## Platform, roles, stores
- **One migration (`0002`) for the whole v2 schema.** Foreign keys are named explicitly so SQLite batch
  downgrades work. `inventory.sold_at` was added as well: it links a unit to its sale date (FIFO), which
  `expected_days_to_sell` needs.
- **Permissions are enforced centrally** in the auth dependency (`app/permissions.py`), based on method + path.
  Partner companies (`lender`, `market_admin`) can only use the partner surface (`/lender`, `/partner`, `/market`,
  `/companies`, `/alerts`, `/users`, `/activity`, `/integrations`, `/input`, `/stores`). Appraisers have an
  allow-list (market, pricing, inventory reads, input parsing). Managers have a deny-list (company settings,
  users, loan applications). Router-level checks stay for `/lender/*` (company must be a lender) and owner-only
  actions. Denials return 403 `role_forbidden`.
- A company key acts as `owner`. User keys are hashed the same way. The caller's role is attached to the
  request-scoped `Company` instance (`actor_role`, `actor_user_id`), which the activity log reads.
- `budgets.store_id` exists, but the unique key stays (company, month, category). Budgets are company-wide
  for now.
- Partner companies may register without categories; all other roles still need at least one.
- The demo lender is **"Demo Lizing Bank"** (slug `demo-bank`): "Hamkor" is a real Uzbek bank brand.
- Every company gets a default store ("Asosiy do'kon") on register and in the seed.

## Stock command center
- `/stock/units` returns one row per inventory row. The v2 seed stores phones and laptops as single units
  (qty 1, each with its own IMEI); deal stock arrives as one row per deal, in the buyer's first (main) store.
- **Rating band tolerance 1%:** overpriced means list > p75 × 1.01, underpriced means list < p25 × 0.99. Small
  skewed samples can have median = p75, and prices are rounded to 1,000 so'm, so without the tolerance a unit
  priced exactly at market would show as "overpriced".
- A unit without `list_price_uzs` is rated `no_data`, with the reason "no list price set" and the fair price as
  the suggestion.
- **Suggested price precedence:** aging (> SLOW_STOCK_DAYS) → p25 (a loss vs cost is shown in `reasons`, not
  blocked) → overpriced → median → underpriced → max(median, cost × 1.03) → otherwise keep.
- **Margin at risk** = Σ (list − suggested) over overpriced units that are not already aging, plus the cost of
  aging units. A unit is never counted twice.
- `expected_days_to_sell` uses the company's sold units (`inventory.status = sold` with `sold_at`, set FIFO by
  deals) when there are ≥ 5 in the category; otherwise the config defaults (phone 21, laptop 30, car 45, house 120,
  rent 30). Then × 1.3 when overpriced, × 0.8 when underpriced.
- `list-on-exchange` groups identical units (same model, condition, attributes and price) into one `surplus`
  offer.
- **1C export format:** semicolon-separated UTF-8 CSV with a BOM and CommerceML-style Russian headers. Stock:
  `Ид;Наименование;Артикул;ЕдиницаИзмерения;Количество;ЦенаЗакупки;ЦенаПродажи;Склад;Характеристики`.
  Transactions: `Дата;ВидОперации;Статья;Контрагент;Номенклатура;Количество;Цена;Сумма;Комментарий`.
  This is a pragmatic import layout for 1C "Загрузка данных из табличного документа", not full CommerceML XML.

## Decisions queue
- **One card per type** (at most 8, sorted by amount): `reprice` covers every overpriced, non-aging unit in a
  single card ("14 units are priced above market"). For the audit-based types, the flag with the largest amount
  at risk becomes the card. Keys: `reprice`, `slow_stock`, `dup:<tx ids>`, `typo:<tx>`, `overpay:<tx>`,
  `budget:<month>:<category>`, `deal:<listing>`, `rfq:<rfq>`.
- **Idempotent build.** A pending card with the same (type, key) is refreshed in place. Pending cards whose
  condition disappeared are set to `expired`. A card approved or ignored today isn't recreated the same day.
- Built on the first `GET /decisions` (or `/dashboard`) of the day per company (tracked in process memory),
  on `?refresh=true`, and every 10 minutes by the `decisions` worker (`WORKERS_DECISIONS`).
- **Approve runs exactly once.** A conditional `UPDATE … WHERE status='pending'` claims the card, and the action
  runs in the same transaction. If the action fails, everything rolls back and the card stays pending.
  A second approve or ignore returns 409 `decision_resolved`.
- **Approve actions:**
  - `reprice` re-checks the units at approve time and only reprices those still overpriced.
  - `slow_stock` creates surplus offers for the units still in stock.
  - `duplicate_invoice` deletes the extra rows (never exchange-origin ones).
  - `typo_amount` sets the total to /10 and notes the old value.
  - `overpayment` creates an `audit` alert and notes the transaction; no money moves.
  - `deal_to_buy` sets `payload.watch = true`.
  - `budget_limit` and `rfq_quote` are acknowledgements. The rfq card's action points at the quote endpoint for
    the frontend form.
- The seed adds one open RFQ from a peer shop (Malika Mobile, Galaxy A54 × 10), so Chilonzor gets an `rfq_quote`
  card.
- Tests that change seed data use a module-scoped `fresh_seed` fixture, which reseeds and clears in-process caches.

## Copilot and credit products
- **`POST /advisor/chat` now runs `services/copilot.py`.** The v1 paragraph-style chat code was removed. The old
  response fields (`answer`, `used_data`, `language`, `source`) are kept, and `used_data` still contains the v1
  keys (e.g. `max_affordable_loan_uzs`, `tax`, `budget`) so v1 clients keep working.
- **Intent order** (first match wins): business_plan → loan_readiness → expansion → credit → tax → budget → audit
  → demand → stock → price → cashflow. When no keyword matches, the order is: selected inventory → `stock`,
  selected transactions → `audit`, screen default (stock/books/budget/exchange), then the LLM (only an intent
  name from a fixed list; anything else is ignored), then `overview`.
- `price` with selected inventory rows becomes `stock`, so "why is this one overpriced?" answers about those
  rows. Ids that don't belong to the caller are dropped from the context.
- **Answer:** each intent has a 2-sentence template. If an LLM is configured, it may rephrase the template
  ("keep every number exactly"). The output is cut to 2 sentences. Blocks and chips are never touched by the LLM
  (there is a test for this).
- **Chips** are `{label, action:{endpoint, method, body}}` pointing at real endpoints (tested against
  OpenAPI). The `file` block for business plans needs a linkable URL, so `GET /advisor/business-plan` was added
  (same plan as POST, via query params).
- `parse_money` reads "100 mln", "1.5 mlrd", "250 ming" in questions. Copilot credit terms are clamped to 36
  months; the credit endpoint itself allows each product's max.
- **Credit products** (`CREDIT_PRODUCTS` in config, all rates are placeholders — VERIFY with partner banks):
  business_loan 24% / 36 mo / 0% down (still honours `DEFAULT_LOAN_RATE`); auto_loan (dealer stock) 26% / 60 mo
  / 20%; mortgage 18% / 240 mo / 30%; leasing 28% / 36 mo / 20%.
  - With `asset_value_uzs`: principal defaults to asset × (1 − down), and LTV = principal / asset.
  - Terms above the product maximum return 422 `term_too_long`.
- **Schedule:** the full annuity schedule is rounded to 0.01. The last row absorbs rounding, so Σ principal equals
  the principal exactly and Σ payment = principal + Σ interest.

## Lender & bazaar console
- **Liquidation value** = p25 × (1 − haircut). Haircuts are in config: car 10%, house 10%, phone 20%, laptop 25%.
- **Valuations** are logged as activity rows (`action = lender.valuation`). Each valuation response returns
  `valuations_this_month`, and the collateral summary does too (usage metric for the business model).
- A lender can value an applicant's inventory unit only if that borrower has applied to this lender
  (403 otherwise). Valuing by `url` uses listings already in the DB; live Telegram fetch is part of
  `/market/price-from-link`.
- **Collateral status:** `breach` when LTV > limit, `watch` when LTV > limit − 5 points, `no_data` when the engine
  can't price the item. Revaluation is live and batched per identical spec. `value_change_30d_pct` compares the
  first and last weekly medians over the last 45 days (by model for goods, by category for apartments).
- **Breach alerts** go to the lender (`type = system`, `payload.key = collateral:<id>`), at most once per item per
  day.
- **Loan applications:** owner only (managers and appraisers get 403). `consent: true` is required (422
  `consent_required`). The snapshot is frozen at submission: readiness with factors, 6-month cash flow, audit
  summary, stock tiles at market value, the credit calculation (first 12 schedule rows) and pledged units valued
  at market. A final decision (approved/rejected) can't be changed (409).
- `GET /advisor/lenders` lists lender companies for the borrower's form.
- The lender sees the business plan at `/lender/applications/{id}/business-plan`, generated from the borrower's
  live books (the snapshot keeps the numbers as submitted).
- `/partner/market-report` is for lender and market_admin. It covers the top 100 (model, district) groups by
  volume, the category's weekly trend and listing counts by seller type; `format=xlsx` gives three sheets.
- **Seed:** Demo Lizing Bank holds 10 collateral items. Balances are set as a share of live market value
  (Malibu 2 at 80% → breach, Tracker 2 at 67% → watch). Chilonzor's 150M business-loan application pledges 5
  iPhone 13 units.
