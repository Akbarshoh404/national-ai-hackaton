"""All API routers, mounted under /api/v1 in `app.main`."""

from app.routers import admin, alerts, auth, books, exchange, market, meta

ROUTERS = [auth.router, meta.router, market.router, books.router, exchange.router, alerts.router, admin.router]
