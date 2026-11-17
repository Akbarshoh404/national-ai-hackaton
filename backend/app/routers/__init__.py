"""All API routers, mounted under /api/v1 in `app.main`."""

from app.routers import (
           admin,
           advisor,
           alerts,
           auth,
           books,
           dashboard,
           decisions,
           exchange,
           market,
           meta,
           platform,
           stock,
)

ROUTERS = [
    auth.router, meta.router, dashboard.router, decisions.router, market.router, stock.router, books.router,
    exchange.router, advisor.router, alerts.router, platform.router, admin.router,
]
