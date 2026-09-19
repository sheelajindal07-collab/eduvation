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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development")
    app_secret_key: str = Field(default="dev-insecure-key-change-me")

    supabase_url: str | None = Field(default=None)
    supabase_publishable_key: str | None = Field(default=None)
    supabase_jwt_secret: str | None = Field(default=None)

    ai_provider: str = Field(default="anthropic")
    anthropic_api_key: str | None = Field(default=None)
    ai_monthly_spend_cap_inr: int = Field(default=5000)
    ai_request_timeout_seconds: int = Field(default=15)

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
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
