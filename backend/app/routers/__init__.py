"""All API routers, mounted under /api/v1 in `app.main`."""

from app.routers import admin, auth, books, market, meta

ROUTERS = [auth.router, meta.router, market.router, books.router, admin.router]
