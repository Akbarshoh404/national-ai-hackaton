"""All API routers, mounted under /api/v1 in `app.main`."""

from app.routers import admin, advisor, alerts, auth, books, dashboard, exchange, market, meta

ROUTERS = [auth.router, meta.router, dashboard.router, market.router, books.router, exchange.router,
           advisor.router, alerts.router, admin.router]
