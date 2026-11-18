"""All API routers, mounted under /api/v1 in `app.main`."""

from app.api.routers import (
    admin,
    advisor,
    alerts,
    auth,
    books,
    dashboard,
    decisions,
    exchange,
    inputs,
    lender,
    market,
    meta,
    platform,
    stock,
)

ROUTERS = [
    auth.router, meta.router, dashboard.router, decisions.router, market.router, inputs.router, stock.router,
    books.router, exchange.router, advisor.router, alerts.router, platform.router, lender.router, admin.router,
]
