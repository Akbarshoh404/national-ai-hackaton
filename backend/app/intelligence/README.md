# `app.intelligence` — the engines (Python calculates, the LLM only explains)

Pure business logic. **Never imports `app.api`, `app.channels` or the entry points** (`main`, `cli`, seed),
so it can be called from HTTP, the bot, workers or the CLI alike.

| Subpackage | Modules | Problem |
|---|---|---|
| `market/` | `pricing` (fair-price engine: comparable tiers, normalization, p25–p75, fair buy price), `market` (feed stats, sourcing radar + deal alerts, trends, heatmap, rental yield), `stock` (stock command center: unit ratings, suggested prices, reprice, xlsx/csv/1C export), `inputs` (free-text/IMEI/t.me-link inputs), `imei` (Luhn + demo TAC table) | **#19**, #26 |
| `books/` | `books` (import + column mapping, AI auditor's 7 checks, peer benchmark, budget control with forecast, slow stock, revaluation), `decisions` (daily decisions queue, approve-once actions) | **#26, #25** |
| `b2b/` | `exchange` (RFQs, quote ranking, counter-offers, offers, deals booked in both books, ratings, demand, deal act) | **#19** |
| `advisor/` | `finance` (cash flow, credit products + schedules, tax, loan readiness), `copilot` (intent router → tools → typed answer blocks + chips), `lender` (valuations, collateral LTV monitoring, loan applications, market report) | **#20**, #19 |
