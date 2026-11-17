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
