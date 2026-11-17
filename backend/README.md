# BozorPilot AI — backend

The full documentation (architecture, every endpoint, engines, Telegram, integrations, data model, tests,
deployment, demo script and go-live checklist) is in the repository root: **[../README.md](../README.md)**.
Design decisions and assumptions: **[DECISIONS.md](DECISIONS.md)**.

## Quick start

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

Open http://127.0.0.1:8000/docs and log in with `POST /api/v1/auth/demo-login {"company_slug": "chilonzor-phone"}`
(or send `X-API-Key: demo-chilonzor-phone`). Tests: `pytest -q`. Lint: `ruff check app tests scripts`.
