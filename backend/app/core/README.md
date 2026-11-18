# `app.core` — shared kernel

Infrastructure every other package builds on. **Imports nothing outside `app.core`** (enforced by
`tests/test_architecture.py`).

| Module | What it does |
|---|---|
| `config` | All settings from env + documented engine constants (margins, haircuts, credit products) |
| `db` | Engine (SQLite WAL locally, PostgreSQL/Neon with a small recycled pool), sessions, migrate/create/drop |
| `models` | Every ORM table |
| `errors` | The single error format `{"error": {code, message, details}}` |
| `i18n`, `catalog` | uz/ru/en texts, money formatting; categories, attributes, districts, model normalizer |
| `deps`, `permissions` | API-key auth (company or user), roles, admin key, central role policy |
| `llm` | Gemini wrapper (JSON, text, vision, audio); returns `None` so callers fall back to rules |
| `events`, `sse` | In-process pub/sub and Server-Sent Events responses |
| `alerts`, `activity` | Alert creation/fan-out (texts in 3 languages); activity log |
| `fx`, `workers`, `memory`, `logging_setup` | USD/UZS rate, background-worker supervision, RSS memory, redacted logs |

Serves all problems (#19, #20, #25, #26) as shared infrastructure.
