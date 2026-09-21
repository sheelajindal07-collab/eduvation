"""Unit tests for app.api.auth.authenticate()'s AuthApiError handling
(UI-review finding, 2026-09-21, HIGH, FIX 2).

Mocked, not live: reliably triggering Supabase's own rate limit on
repeated sign-in attempts from a test would be slow and flaky (see
tests/db/test_api_auth.py's TestSignUp docstring for the same problem
already observed on the sign-up path). A fake auth client that raises
the exact `AuthApiError` shape Supabase's own SDK raises exercises
authenticate()'s branching logic directly, without needing the network
call itself to behave a particular way.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.api.auth import authenticate


class _FakeAuthClient:
    def __init__(self, *, result: Any = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def sign_in_with_password(self, credentials: dict[str, str]) -> Any:
        if self._error is not None:
            raise self._error
        return self._result


def _fake_client(*, result: Any = None, error: Exception | None = None) -> Client:
    # Duck-typed: authenticate() only ever touches `.auth.sign_in_with_password`.
    # cast() satisfies the type checker without a heavier real-client mock.
    return cast("Client", SimpleNamespace(auth=_FakeAuthClient(result=result, error=error)))


class TestAuthenticateAntiEnumeration:
    def test_invalid_credentials_error_stays_the_generic_401(self) -> None:
        """Supabase's own "invalid_credentials" code covers BOTH wrong
        password and no-such-email -- it must collapse to the same
        ambiguous 401 as every other failure, never its own real status
        or message."""
        error = AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        client = _fake_client(error=error)

        with pytest.raises(HTTPException) as exc_info:
            authenticate(client, "student@example.com", "wrong-password")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password."

    def test_unstructured_exception_still_collapses_to_the_generic_401(self) -> None:
        """Existing behaviour, unchanged: a network error or any other
        non-AuthApiError exception is not a structured provider signal,
        so it still becomes the same generic 401 as a login failure."""
        client = _fake_client(error=ConnectionError("boom"))

        with pytest.raises(HTTPException) as exc_info:
            authenticate(client, "student@example.com", "whatever")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password."

    def test_no_session_or_user_in_the_result_is_also_the_generic_401(self) -> None:
        client = _fake_client(result=SimpleNamespace(session=None, user=None))

        with pytest.raises(HTTPException) as exc_info:
            authenticate(client, "student@example.com", "whatever")

        assert exc_info.value.status_code == 401


class TestAuthenticateRateLimitPropagation:
    """The actual FIX 2 behaviour: a structured, provider-level error
    that ISN'T a login failure must reach the caller with its real
    status/message, not be flattened into the same 401 a wrong password
    gets -- otherwise Supabase's own rate-limit signal is silently
    unloggable and unfixable from the caller's side."""

    def test_over_request_rate_limit_propagates_its_real_status_and_message(self) -> None:
        error = AuthApiError("Request rate limit reached", 429, "over_request_rate_limit")
        client = _fake_client(error=error)

        with pytest.raises(HTTPException) as exc_info:
            authenticate(client, "student@example.com", "whatever")

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Request rate limit reached"

    def test_over_email_send_rate_limit_also_propagates(self) -> None:
        error = AuthApiError("Email rate limit exceeded", 429, "over_email_send_rate_limit")
        client = _fake_client(error=error)

        with pytest.raises(HTTPException) as exc_info:
            authenticate(client, "student@example.com", "whatever")

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Email rate limit exceeded"


class TestAuthenticateSuccess:
    def test_successful_sign_in_returns_the_session_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guardian-consent gate, 2026-09-21: authenticate() now also
        calls enforce_guardian_consent_gate(), which -- but only once
        db/migrations/0004_guardian_consent.sql is actually live against
        whatever real project this test suite happens to run against --
        goes on to touch client.postgrest/.table(), neither of which this
        module's deliberately minimal _fake_client provides (see its own
        docstring: "authenticate() only ever touches
        .auth.sign_in_with_password", true before this gate existed).
        This test's own concern is narrowly "does authenticate() pass the
        session through unchanged", not the gate's internal DB behaviour
        (that has its own dedicated, thorough live suite in
        tests/db/test_guardian_consent.py) -- so the schema-live check is
        forced False here rather than building out a heavier fake client,
        keeping this test's pass/fail independent of whatever a real
        Supabase project's migration state happens to be at run time."""
        monkeypatch.setattr(
            "app.api.guardian_consent.guardian_consent_schema_is_live", lambda: False
        )
        fake_session = SimpleNamespace(access_token="a-real-looking-token")
        fake_user = SimpleNamespace(id="user-123")
        client = _fake_client(result=SimpleNamespace(session=fake_session, user=fake_user))

        session = authenticate(client, "student@example.com", "correct-password")

        assert session is fake_session
