"""Application settings.

Values come from environment variables only (see .env.example for the
names). Nothing here holds a real secret — CLAUDE.md non-negotiable.
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _fail_closed_bool(value: object) -> bool:
    """Parse an env-style boolean the safe way round (DEPLOY-18):
    anything that isn't unambiguously a "true" token is treated as
    False, including a missing var, an empty string, or a typo/garbled
    value. A flag that fails to parse must never be silently read as
    "enabled" — CLAUDE.md's fail-closed rule, applied to every boolean
    flag this app has (SIGNUP_ENABLED, MAINTENANCE_MODE, AI_ENABLED,
    HINDI_UI_ENABLED, MINOR_ACCOUNTS_ENABLED, the demo-mode guard).

    Deliberately never raises: pydantic's own bool coercion rejects an
    unparseable string outright (a `ValidationError` that would crash
    `Settings()`/the whole app at boot for a mere typo in a kill
    switch) — this trades that strictness for "always boots, always
    into the safe state" instead, which is the behaviour DEPLOY-18 asks
    for.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


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

    # --- Feature flags / kill switches (DEPLOY-18) ---
    # docs/CONTRACTS.md "Settled — the flag list, and only this list":
    # SIGNUP_ENABLED, MAINTENANCE_MODE, AI_ENABLED, HINDI_UI_ENABLED,
    # ALLOWED_HOSTS, MINOR_ACCOUNTS_ENABLED, plus the demo-mode guard.
    # `SIGNUPS_ENABLED` (with an S) is a stale name from an earlier plan
    # draft and must never be reintroduced anywhere in this codebase.
    # Every boolean flag here defaults to its closed/disabled state and
    # is parsed by `_fail_closed_bool` below, so a missing var, an empty
    # string, or a typo can never be silently read as "enabled".
    signup_enabled: bool = Field(
        default=False,
        description="Public sign-up. Off by default outside an explicit opt-in.",
    )
    maintenance_mode: bool = Field(
        default=False,
        description="Kill switch: when true, every route except /healthz "
        "should degrade to a paused response. Off by default so a missing "
        "var never takes the whole app down by accident.",
    )
    ai_enabled: bool = Field(
        default=False,
        description="Operator toggle for AI-backed features, independent of "
        "`ai_configured` (whether a provider key is even set). Off by default.",
    )
    hindi_ui_enabled: bool = Field(default=False, description="Hindi UI/copy variant.")
    minor_accounts_enabled: bool = Field(
        default=False,
        description="CLAUDE.md non-negotiable: real minor accounts stay "
        "disabled until the consent/safeguarding workflow is reviewed by a "
        "person. The pilot's first phase is adults-only.",
    )
    demo_mode: bool = Field(
        default=False,
        description="Guard for a supervised demo/showcase run (e.g. the "
        "teacher demo, docs/DECISIONS.md). DEPLOY-18 added the flag with a "
        "fail-closed default; DATA-12 is the 'later task' that gives it "
        "meaning — see `_refuse_demo_mode_in_production` below and "
        "db/migrations/0007_demo_mode.sql. NOTE: this process-level flag "
        "does NOT itself unlock anything. What a visitor can actually see "
        "is decided entirely by the database (the `demo_mode()` function "
        "and the `claims_select_demo_synthetic` policy over an "
        "owner-writable `app_settings` row), so no application deploy, "
        "environment variable or code path can widen it. This flag is the "
        "application's own copy of the same switch, used to label the read "
        "path and to refuse to boot in the one place demo data must never "
        "appear.",
    )
    # Raw comma-separated value from the environment. Use
    # `allowed_hosts_list` below, never this field directly — it applies
    # the fail-closed environment-aware fallback (see that property).
    allowed_hosts: str = Field(
        default="",
        description="Comma-separated hostnames for TrustedHostMiddleware. "
        "Empty outside development means 'nothing is a valid Host header "
        "yet' (fail closed), never a wildcard.",
    )

    @field_validator(
        "signup_enabled",
        "maintenance_mode",
        "ai_enabled",
        "hindi_ui_enabled",
        "minor_accounts_enabled",
        "demo_mode",
        mode="before",
    )
    @classmethod
    def _parse_flags_fail_closed(cls, value: object) -> bool:
        return _fail_closed_bool(value)

    # DATA-12. Added alongside DEPLOY-18's flag block above, not folded
    # into it: `_parse_flags_fail_closed` is a per-field coercion that
    # deliberately never raises, and this is a whole-model consistency
    # check that deliberately does.
    @model_validator(mode="after")
    def _refuse_demo_mode_in_production(self) -> "Settings":
        """`DEMO_MODE=true` with `APP_ENV=production` refuses to start.

        Demo mode's entire purpose is to make unverified, clearly-labelled
        *sample* rows visible to a visitor who is not signed in
        (db/migrations/0007_demo_mode.sql). On staging that is the point;
        on production it would put unpublished content in front of a real
        student, which CLAUDE.md's non-negotiable forbids outright
        ("Synthetic fixtures ... NEVER published as verified facts").

        This raises rather than silently forcing the flag to False, and
        that is a deliberate departure from `_fail_closed_bool`'s "always
        boots, always into the safe state" rule directly above. The two
        cases are not the same: that rule protects against a *typo* in a
        kill switch taking the whole app down, where guessing "off" is
        both safe and almost certainly what was meant. Here nothing is
        ambiguous — somebody has explicitly written a true-token into
        DEMO_MODE on a production deploy. Silently ignoring that would
        leave an operator believing demo mode is on while it is not,
        which is how the *next* person "fixes" it by loosening the
        database policy instead. A refused boot is loud, immediate, and
        cannot be mistaken for success.

        Mirrors `app/main.py`'s `_verify_critical_settings` "Refusing to
        start:" contract, but lives here because the check needs no
        registry and must hold for every construction of `Settings`, not
        only the one `create_app` performs.
        """
        if self.demo_mode and self.app_env == "production":
            raise ValueError(
                "Refusing to start: DEMO_MODE is on with APP_ENV='production'. "
                "Demo mode exposes unpublished, synthetic-sourced sample claims "
                "to anonymous visitors (db/migrations/0007_demo_mode.sql) and "
                "must never be enabled on production. Unset DEMO_MODE, or use "
                "APP_ENV='staging'."
            )
        return self

    @property
    def allowed_hosts_list(self) -> list[str]:
        """`TrustedHostMiddleware(allowed_hosts=...)`'s actual input.

        A configured, non-empty `ALLOWED_HOSTS` always wins. Left unset:
        development gets a permissive `["*"]` (local/testing convenience,
        never a production concern) — anywhere else, the fail-closed
        state is an empty list, i.e. no Host header is valid until this
        is actually configured, never "allow anything" (DEPLOY-18: the
        safe state, never the permissive one).
        """
        hosts = [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
        if hosts:
            return hosts
        if self.app_env == "development":
            return ["*"]
        return []

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
