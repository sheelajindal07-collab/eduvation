"""AI-2 tests: AI_ENABLED flag, kill switch and AI settings.

Tests for the AI configuration fields added in AI-2: ai_model,
ai_max_input_tokens, ai_max_output_tokens, ai_per_account_daily_cap.
"""

from __future__ import annotations

from app.core.config import Settings


class TestAiSettingsDefaults:
    """Test defaults for new AI settings fields (AI-2)."""

    def test_ai_settings_default_to_none(self) -> None:
        """ai_model, ai_max_input_tokens, ai_max_output_tokens, and
        ai_per_account_daily_cap all default to None when unset."""
        settings = Settings(_env_file=None)
        assert settings.ai_model is None
        assert settings.ai_max_input_tokens is None
        assert settings.ai_max_output_tokens is None
        assert settings.ai_per_account_daily_cap is None

    def test_ai_enabled_defaults_false(self) -> None:
        """ai_enabled defaults to False (fail-closed, DEPLOY-18)."""
        settings = Settings(_env_file=None)
        assert settings.ai_enabled is False

    def test_ai_configured_still_false_with_only_new_fields_set(self) -> None:
        """Setting only the new AI config fields does not make ai_configured true.
        ai_configured requires the API key (gemini_api_key) to be set."""
        settings = Settings(
            _env_file=None,
            ai_model="gemini-1.5-pro",
            ai_max_input_tokens=30000,
            ai_max_output_tokens=2000,
            ai_per_account_daily_cap=10,
        )
        assert settings.ai_configured is False
        assert settings.ai_enabled is False


class TestAiSettingsCanBeConfigured:
    """Test that new AI settings can be read from environment."""

    def test_ai_settings_can_be_set(self) -> None:
        """All four new AI settings can be configured via constructor."""
        settings = Settings(
            _env_file=None,
            ai_model="gemini-1.5-pro",
            ai_max_input_tokens=32000,
            ai_max_output_tokens=8192,
            ai_per_account_daily_cap=50,
        )
        assert settings.ai_model == "gemini-1.5-pro"
        assert settings.ai_max_input_tokens == 32000
        assert settings.ai_max_output_tokens == 8192
        assert settings.ai_per_account_daily_cap == 50
