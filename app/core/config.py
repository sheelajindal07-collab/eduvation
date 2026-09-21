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

    # --- Guardian-consent confirmation link (app/api/guardian_consent.py) ---
    # Needed to build an absolute GET /consent/confirm?token=... URL for
    # the guardian email — a relative path alone means nothing in an
    # email client. Defaults to local dev; set to the real public origin
    # once one exists (docs/DECISIONS.md "Public domain").
    app_base_url: str = Field(default="http://localhost:8000")

    # --- Email sending (app/notifications/) ---
    # No real provider is configured anywhere in this codebase yet — see
    # app/notifications/logging_sender.py. These fields exist so
    # app/notifications/smtp_sender.py's SmtpEmailSender can be
    # constructed once the owner provisions a real SMTP relay (any
    # provider's SMTP endpoint — SendGrid/SES/Mailgun/Resend/etc. all
    # expose one), mirroring gemini_api_key's own "field exists, value
    # unset until the owner provisions the account" shape above. All
    # unset today; the app boots and every test passes without them.
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_username: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    smtp_from_address: str | None = Field(default=None)

    @property
    def db_configured(self) -> bool:
        """Whether Supabase is provisioned yet (see docs/DECISIONS.md)."""
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def ai_configured(self) -> bool:
        """Whether the AI provider adapter can make live calls."""
        return bool(self.gemini_api_key)

    @property
    def email_configured(self) -> bool:
        """Whether a real SmtpEmailSender can be constructed. False in
        every environment today — see app/notifications/logging_sender.py
        for what actually runs instead, and STATUS.md for the owner
        action needed before this flips true anywhere."""
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
