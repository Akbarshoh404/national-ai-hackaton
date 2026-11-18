# `app.api` — HTTP layer

FastAPI routers (`routers/`) and Pydantic request/response models (`schemas/`). Thin: validate input, call
`app.intelligence` / `app.data_pipeline`, shape the response. Every route has a typed `response_model` and a
readable `operationId` (the function name, e.g. `market_price`). Mounted under `/api/v1` by `app.main`.

| Router | Area | Problem |
|---|---|---|
| `auth`, `meta`, `platform`, `alerts`, `admin` | registration, demo login, `/meta`, `/health`, `/ping`, stores, users, activity, integrations, alerts, admin | all |
| `market`, `inputs`, `stock` | market engine, fast inputs, stock command center | #19, #26 |
| `books`, `decisions`, `dashboard` | AI auditor, budget control, decisions queue, home screen | #26, #25 |
| `exchange` | B2B exchange | #19 |
| `advisor`, `lender` | copilot, credit, tax, plans, loan applications, lender & bazaar console | #20 |
