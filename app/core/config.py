"""Application settings.

Values come from environment variables only (see .env.example for the
names). Nothing here holds a real secret — CLAUDE.md non-negotiable.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed environment configuration.

    All fields default to empty/None so the app boots and is testable
    before any external account (Supabase, AI provider, WhatsApp, ...) is
    provisioned — see docs/DECISIONS.md.
    """

    # frozen=True (data-security-reviewer finding, 2026-09-19): this
    # instance is process-wide cached (see get_settings below), which is
    # only safe because nothing mutates it. Freezing makes that an
    # enforced invariant instead of a convention — any future code path
    # that tried `settings.x = ...` fails loudly instead of silently
    # corrupting the shared singleton for every subsequent request.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    app_env: str = Field(default="development")
    app_secret_key: str = Field(default="dev-insecure-key-change-me")

    supabase_url: str | None = Field(default=None)
    supabase_publishable_key: str | None = Field(default=None)
    supabase_jwt_secret: str | None = Field(default=None)

    ai_provider: str = Field(default="gemini")  # docs/DECISIONS.md, owner-confirmed 2026-09-19
    gemini_api_key: str | None = Field(default=None)
    ai_monthly_spend_cap_inr: int = Field(default=5000)
    ai_request_timeout_seconds: int = Field(default=15)
    # Pilot-scale spend guard (app/ai/budget.py) — a request count, not a
    # money figure (ai_monthly_spend_cap_inr above is the separate
    # rupee-denominated ceiling from docs/SECURITY.md's spend controls).
    # In-memory, per-process, resets at UTC-date rollover; deliberately
    # not a distributed limiter (CLAUDE.md: 10-100 users, don't
    # over-engineer this).
    ai_daily_request_budget: int = Field(default=200)

    whatsapp_cloud_api_token: str | None = Field(default=None)
    whatsapp_phone_number_id: str | None = Field(default=None)

    error_tracking_dsn: str | None = Field(default=None)
    uptime_check_url: str | None = Field(default=None)

    n8n_webhook_url: str | None = Field(default=None)

    @property
    def db_configured(self) -> bool:
        """Whether Supabase is provisioned yet (see docs/DECISIONS.md)."""
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def ai_configured(self) -> bool:
        """Whether the AI provider adapter can make live calls."""
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
