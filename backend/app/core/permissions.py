"""Role-based access policy, enforced centrally by the auth dependency.

Two layers:
* company role — `lender` / `market_admin` partners only use the partner surface;
* user role — `owner` (company key), `manager`, `appraiser`, `lender_officer`.

Router-specific checks (e.g. `/lender/*` needs a lender company) live in the routers.
"""

from __future__ import annotations

PARTNER_COMPANY_ROLES = {"lender", "market_admin"}
USER_ROLES = ["owner", "manager", "appraiser", "lender_officer"]

#: path prefixes partner companies (banks, bazaar admins) may use
_PARTNER_PREFIXES = ("/lender", "/partner", "/market", "/companies", "/alerts", "/users", "/activity",
                     "/integrations", "/input", "/stores")

#: (method, path prefix) an appraiser may call: market, pricing and inventory read-only
_APPRAISER_ALLOW = (
    ("GET", "/market"), ("POST", "/market/price"), ("POST", "/market/rental-yield"),
    ("POST", "/market/price-from-link"), ("GET", "/stock/units"), ("GET", "/stock/summary"),
    ("GET", "/books/inventory"), ("GET", "/companies"), ("GET", "/alerts"), ("POST", "/alerts"),
    ("POST", "/input/parse"), ("POST", "/input/imei"), ("POST", "/input/voice"), ("GET", "/stores"),
)

#: what a manager may NOT do: company settings, users, loan applications
_MANAGER_DENY = (("PATCH", "/companies/me"), ("*", "/users"), ("*", "/advisor/loan-applications"))

_LENDER_OFFICER_DENY = (("*", "/users"), ("PATCH", "/companies/me"))


def _match(rules: tuple[tuple[str, str], ...], method: str, path: str) -> bool:
    return any((m == "*" or m == method) and path.startswith(prefix) for m, prefix in rules)


def denial(method: str, path: str, company_role: str, user_role: str) -> str | None:
    """Return a reason string if the call is not allowed, else None. `path` excludes `/api/v1`."""
    if company_role in PARTNER_COMPANY_ROLES and not path.startswith(_PARTNER_PREFIXES):
        return "Partner accounts (lender, market admin) cannot use business endpoints"
    if user_role == "owner":
        return None
    if user_role == "manager" and _match(_MANAGER_DENY, method, path):
        return "Managers cannot change company settings, users or loan applications"
    if user_role == "appraiser" and not _match(_APPRAISER_ALLOW, method, path):
        return "Appraisers have read-only access to market, pricing and inventory"
    if user_role == "lender_officer" and _match(_LENDER_OFFICER_DENY, method, path):
        return "Lender officers cannot manage users or company settings"
    return None
