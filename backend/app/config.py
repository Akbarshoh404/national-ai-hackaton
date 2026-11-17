"""Application settings, all read from the environment (or a local `.env`).

Business constants that tune the price engine and the advisor live here too, so
that they are documented in one place and can be overridden per deployment.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field maps to an env variable of the same name."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- infrastructure -------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./bozorpilot.db"
    ADMIN_KEY: str = "change-me"
    CORS_ORIGINS: str = "http://localhost:3000,https://bozorpilot.vercel.app"
    DEMO_MODE: bool = True
    AUTO_MIGRATE: bool = True
    LOG_LEVEL: str = "INFO"

    # --- workers --------------------------------------------------------------
    WORKERS_TELEGRAM: bool = True
    WORKERS_EXTRACTOR: bool = True
    BOT_ENABLED: bool = True

    # --- telegram -------------------------------------------------------------
    TG_API_ID: int | None = None
    TG_API_HASH: str = ""
    TG_SESSION: str = ""
    TG_SESSION_FILE: str = "bozorpilot"
    TG_HISTORY_LIMIT: int = 3000
    TG_BOT_TOKEN: str = ""
    SOURCES_FILE: str = "sources.yaml"

    # --- LLM ------------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LLM_TIMEOUT_S: float = 15.0
    EXTRACT_BATCH_SIZE: int = 15

    # --- market ---------------------------------------------------------------
    USD_UZS: float = 12700.0
    MARKET_WINDOW_DAYS: int = 60
    MIN_COMPARABLES: int = 5
    DEAL_THRESHOLD: float = 0.15
    PRICE_CACHE_TTL_S: float = 20.0

    # --- books / advisor --------------------------------------------------------
    SLOW_STOCK_DAYS: int = 60
    TURNOVER_TAX_RATE: float = 0.04  # VERIFY with soliq.uz
    VAT_RATE: float = 0.12  # VERIFY with soliq.uz
    PROFIT_TAX_RATE: float = 0.15  # VERIFY with soliq.uz
    DEFAULT_LOAN_RATE: float = 24.0  # VERIFY with partner banks
    MAX_DEBT_SERVICE_RATIO: float = 0.5

    @field_validator("TG_API_ID", mode="before")
    @classmethod
    def _empty_int(cls, v: object) -> object:
        return None if v in ("", None) else v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.TG_API_ID and self.TG_API_HASH)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()

# ---------------------------------------------------------------------------
# Price-engine factors (documented in DECISIONS.md). Not env-driven on purpose:
# they are part of the model and are covered by tests.
# ---------------------------------------------------------------------------

#: Value of an item in a given condition relative to "new".
CONDITION_MULTIPLIERS: dict[str, float] = {"new": 1.0, "A": 0.88, "B": 0.78, "C": 0.62, "used": 1.0}
#: Cars lose this share of value per model year.
CAR_DEPRECIATION_PER_YEAR = 0.06
#: Phones whose IMEI is not registered with UZIMEI sell for less.
PHONE_IMEI_UNREGISTERED_DEDUCTION = 0.15
#: Phones with replaced parts ("zamena") sell for less.
PHONE_REPAIRED_DEDUCTION = 0.08
#: Each storage doubling (64→128→256) adds this share of value.
STORAGE_STEP_PREMIUM = 0.12
#: Dealer margin: fair buy (trade-in / wholesale) = fair × (1 − margin).
DEALER_MARGIN: dict[str, float] = {"phone": 0.15, "laptop": 0.15, "car": 0.08, "house": 0.05, "rent": 0.0}
#: Stock turns per month used by the expansion planner.
STOCK_TURNS_PER_MONTH: dict[str, float] = {"phone": 1.5, "laptop": 1.0, "car": 0.6}
#: Share of gross rent lost to vacancy, maintenance and property tax.
RENT_OPEX_RATIO = 0.15
#: Price a slow-moving unit at this share of the market price to clear it.
SURPLUS_PRICE_FACTOR = 0.92
