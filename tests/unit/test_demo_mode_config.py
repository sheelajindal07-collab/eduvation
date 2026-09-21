"""DATA-12's application-side half: the production demo-mode guard.

Acceptance line: "production config check refuses start when demo_mode
is on."

`Settings` is constructed by `get_settings()`, which `create_app()` calls
before it builds anything, so a `ValidationError` raised here really is a
refused boot — the same contract `app/main.py`'s `_verify_critical_settings`
provides for the other critical values.

Every `Settings(...)` below passes `_env_file=None`, matching
tests/unit/test_health.py's existing convention: without it pydantic-
settings would read the developer's real `.env` and the result would
depend on whose machine it ran on.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestProductionRefusesDemoMode:
    def test_demo_mode_on_in_production_refuses_to_construct(self) -> None:
        with pytest.raises(ValidationError, match="Refusing to start"):
            Settings(_env_file=None, app_env="production", demo_mode="true")

    def test_the_message_names_the_flag_and_a_way_out(self) -> None:
        """An operator reading this in a crash log needs to know which
        variable to change, not just that something is wrong."""
        with pytest.raises(ValidationError) as caught:
            Settings(_env_file=None, app_env="production", demo_mode="true")
        message = str(caught.value)
        assert "DEMO_MODE" in message
        assert "production" in message

    @pytest.mark.parametrize("token", ["1", "true", "TRUE", "yes", "on"])
    def test_every_true_token_is_caught(self, token: str) -> None:
        """`_fail_closed_bool` accepts several spellings of true; the
        guard must fire for all of them, not just the literal "true"."""
        with pytest.raises(ValidationError, match="Refusing to start"):
            Settings(_env_file=None, app_env="production", demo_mode=token)


class TestEverythingElseStillBoots:
    def test_production_without_demo_mode_is_fine(self) -> None:
        settings = Settings(_env_file=None, app_env="production")
        assert settings.demo_mode is False

    def test_production_with_demo_mode_explicitly_off_is_fine(self) -> None:
        settings = Settings(_env_file=None, app_env="production", demo_mode="false")
        assert settings.demo_mode is False

    def test_staging_may_have_demo_mode_on(self) -> None:
        """Staging is exactly where demo mode is meant to be used —
        the guard must not be a blanket "never outside development"."""
        settings = Settings(_env_file=None, app_env="staging", demo_mode="true")
        assert settings.demo_mode is True

    def test_development_may_have_demo_mode_on(self) -> None:
        settings = Settings(_env_file=None, app_env="development", demo_mode="true")
        assert settings.demo_mode is True

    @pytest.mark.parametrize("garbled", ["", "  ", "flase", "maybe", "0", "off"])
    def test_a_garbled_flag_in_production_still_boots_into_the_safe_state(
        self, garbled: str
    ) -> None:
        """DEPLOY-18's fail-closed parsing is unchanged and still comes
        first: only an unambiguous true-token reaches the new guard, so a
        typo is read as "off" and boots normally rather than taking
        production down. The guard fires on a deliberate choice, never on
        a mistake."""
        settings = Settings(_env_file=None, app_env="production", demo_mode=garbled)
        assert settings.demo_mode is False


class TestTheGuardIsNotOverBroad:
    def test_other_flags_are_unaffected_in_production(self) -> None:
        """Regression guard: the new model validator must not have turned
        into a general "no flags in production" rule."""
        settings = Settings(
            _env_file=None,
            app_env="production",
            signup_enabled="true",
            ai_enabled="true",
            hindi_ui_enabled="true",
            minor_accounts_enabled="true",
        )
        assert settings.signup_enabled is True
        assert settings.ai_enabled is True
        assert settings.hindi_ui_enabled is True
        assert settings.minor_accounts_enabled is True
        assert settings.demo_mode is False
