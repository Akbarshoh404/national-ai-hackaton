"""All API routers, mounted under /api/v1 in `app.main`."""

from app.routers import admin, auth, meta

ROUTERS = [auth.router, meta.router, admin.router]
