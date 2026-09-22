"""Tests for AI-3 (BCI-012): `app/ai/gemini_provider.py`'s hardening and
`app/ai/mock_provider.py`'s new multi-call scripting.

Covers, precisely:
- the installed `google-genai==2.24.0` SDK's own automatic retry is
  disabled, both at `Client` construction and on every individual
  `.generate()` call;
- every transport/API failure is mapped to exactly one of
  `app/ai/schemas.py`'s four typed provider errors
  (`AIProviderTimeout`/`AIProviderQuota`/`AIProviderMalformed`/
  `AIProviderError`), never a raw SDK exception;
- the API key can never appear in a log line or in a raised exception's
  string representation, even when the underlying (faked) SDK exception's
  own message deliberately contains it;
- `MockAIProvider`'s new `responses=[...]` sequencing and `raise_on_call`
  hook, and that its pre-existing `canned_response`/echo-default modes
  are unaffected.

No `make test-db`, no e2e, no real network call, no real provider call
anywhere in this file. `GeminiProvider` is always exercised through an
injected fake `models.generate_content` callable on a real (but
fake-keyed) `genai.Client` -- constructing the client itself makes no
network call (see `app/ai/gemini_provider.py`'s module docstring), and
nothing here ever invokes the real HTTP transport.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from app.ai.adapter import AIProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.mock_provider import MockAIProvider
from app.ai.schemas import (
    AIProviderError,
    AIProviderMalformed,
    AIProviderQuota,
    AIProviderTimeout,
)
from app.core.config import Settings

#: Deliberately shaped like a real key so a substring check is meaningful,
#: but unmistakably synthetic (CLAUDE.md) and never a live credential.
FAKE_API_KEY = "FAKE-TEST-KEY-do-not-use-9f3a7c21"


def _configured_provider(
    monkeypatch: pytest.MonkeyPatch, *, api_key: str = FAKE_API_KEY
) -> GeminiProvider:
    """A real `GeminiProvider`, constructed against a fake (never live)
    key -- construction itself makes no network call (module docstring),
    so this is safe unconditionally. Same monkeypatch idiom as the
    existing `tests/unit/test_ai_adapter.py` gating tests."""
    import app.ai.gemini_provider as gemini_provider_module

    monkeypatch.setattr(
        gemini_provider_module,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=api_key),
    )
    return GeminiProvider()


def _install_fake_generate_content(
    provider: GeminiProvider,
    monkeypatch: pytest.MonkeyPatch,
    *,
    response_text: str | None = "[claim-x]",
    raise_error: BaseException | None = None,
) -> list[dict[str, Any]]:
    """Monkeypatch `provider`'s real, already-hardened
    `genai.Client.models.generate_content` with a fake that never touches
    the network: returns `response_text` wrapped in a bare object with a
    `.text` attribute, or raises `raise_error` if given. Returns the list
    every call's kwargs (`model`/`contents`/`config`) are recorded into,
    so a test can assert on call count and on exactly what `generate()`
    passed the SDK (e.g. `config.http_options.retry_options`)."""
    calls: list[dict[str, Any]] = []

    def fake_generate_content(*, model: str, contents: str, config: Any) -> Any:
        calls.append({"model": model, "contents": contents, "config": config})
        if raise_error is not None:
            raise raise_error
        return SimpleNamespace(text=response_text)

    monkeypatch.setattr(provider._client.models, "generate_content", fake_generate_content)
    return calls


# ---------------------------------------------------------------------
# The SDK's own automatic retry is disabled -- both layers.
# ---------------------------------------------------------------------


def test_sdk_retry_is_disabled_at_client_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _configured_provider(monkeypatch)
    retry_options = provider._client._api_client._http_options.retry_options
    assert retry_options is not None
    assert retry_options.attempts == 1


def test_sdk_retry_is_also_disabled_on_every_individual_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _configured_provider(monkeypatch)
    calls = _install_fake_generate_content(provider, monkeypatch, response_text="[claim-a]")

    provider.generate("some fully-built grounding prompt")

    (call,) = calls
    per_call_retry = call["config"].http_options.retry_options
    assert per_call_retry is not None
    assert per_call_retry.attempts == 1


def test_generate_makes_exactly_one_request_even_when_it_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"One request per `generate()` call, proven how": a failing call
    must never be silently retried underneath the caller (the SDK's own
    retry is disabled -- see the two tests above). This is what actually
    proves it operationally: the fake `generate_content` is invoked
    exactly once for one `provider.generate()` call, even though the
    scripted failure (a 503) is one of the status codes the SDK would
    normally retry on by default."""
    provider = _configured_provider(monkeypatch)
    calls = _install_fake_generate_content(
        provider,
        monkeypatch,
        raise_error=errors.ServerError(
            503, {"error": {"status": "UNAVAILABLE", "message": "down"}}
        ),
    )

    with pytest.raises(AIProviderError):
        provider.generate("prompt")

    assert len(calls) == 1


def test_response_mime_type_is_explicitly_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two-pass selection/verification format (a later card) is
    line-based, not JSON -- confirm this module does not leave the SDK's
    response format on an unstated default."""
    provider = _configured_provider(monkeypatch)
    calls = _install_fake_generate_content(provider, monkeypatch, response_text="[claim-a]")

    provider.generate("prompt")

    (call,) = calls
    assert call["config"].response_mime_type == "text/plain"


def test_hardened_gemini_provider_still_satisfies_ai_provider_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _configured_provider(monkeypatch)
    assert isinstance(provider, AIProvider)


# ---------------------------------------------------------------------
# Every failure class -> typed error mapping, and the API key never
# leaks into the raised error's string representation or into any log
# line, even when the underlying (faked) SDK exception's own message
# deliberately contains it (an adversarial simulation of a worst-case
# SDK message, not a claim that the real SDK actually does this).
# ---------------------------------------------------------------------


def _timeout_error() -> BaseException:
    return httpx.TimeoutException(f"timed out talking to Gemini (key={FAKE_API_KEY})")


def _quota_error_429() -> BaseException:
    return errors.ClientError(
        429,
        {
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": f"Quota exceeded, key={FAKE_API_KEY}",
            }
        },
    )


def _quota_error_detected_by_message_not_code() -> BaseException:
    # Some hosted APIs report the same "you have been rate limited"
    # condition under a different numeric status -- the message/status
    # text is what app/ai/gemini_provider.py's `_is_quota_error` falls
    # back to. Code 403 deliberately chosen to prove the 429 check alone
    # is not what is firing here.
    return errors.ClientError(
        403,
        {
            "error": {
                "status": "PERMISSION_DENIED",
                "message": f"Rate limit exceeded for key {FAKE_API_KEY}",
            }
        },
    )


def _client_error_not_quota() -> BaseException:
    return errors.ClientError(
        400,
        {"error": {"status": "INVALID_ARGUMENT", "message": f"Bad request, key={FAKE_API_KEY}"}},
    )


def _server_error() -> BaseException:
    return errors.ServerError(
        503,
        {"error": {"status": "UNAVAILABLE", "message": f"Server overloaded, key={FAKE_API_KEY}"}},
    )


def _unexpected_error() -> BaseException:
    return RuntimeError(f"totally unexpected transport failure, key={FAKE_API_KEY}")


ERROR_PATH_CASES = [
    pytest.param(_timeout_error, AIProviderTimeout, id="timeout"),
    pytest.param(_quota_error_429, AIProviderQuota, id="quota-429"),
    pytest.param(_quota_error_detected_by_message_not_code, AIProviderQuota, id="quota-by-message"),
    pytest.param(_client_error_not_quota, AIProviderError, id="client-error-not-quota"),
    pytest.param(_server_error, AIProviderError, id="server-error"),
    pytest.param(_unexpected_error, AIProviderError, id="unexpected-exception"),
]


@pytest.mark.parametrize("make_error, expected_type", ERROR_PATH_CASES)
def test_every_failure_class_maps_to_its_typed_error_and_never_leaks_the_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_error: Any,
    expected_type: type[Exception],
) -> None:
    provider = _configured_provider(monkeypatch)
    calls = _install_fake_generate_content(provider, monkeypatch, raise_error=make_error())

    caplog.set_level(logging.DEBUG)
    with pytest.raises(expected_type) as excinfo:
        provider.generate("some fully-built grounding prompt")

    # No raw SDK exception type ever escapes -- exactly the typed error
    # this failure class maps to, nothing else.
    assert type(excinfo.value) is expected_type
    # Exactly one request -- no retry loop ran underneath this failure.
    assert len(calls) == 1
    # The key never survives into the raised error's string
    # representation, even though the (faked) underlying SDK exception's
    # own message deliberately contained it.
    assert FAKE_API_KEY not in str(excinfo.value)
    assert FAKE_API_KEY not in repr(excinfo.value)
    # ... nor into any log line captured during the call.
    assert FAKE_API_KEY not in caplog.text


@pytest.mark.parametrize(
    "response_text",
    [None, "", "   \n  "],
    ids=["none", "empty-string", "whitespace-only"],
)
def test_empty_or_blank_response_raises_ai_provider_malformed(
    monkeypatch: pytest.MonkeyPatch, response_text: str | None
) -> None:
    provider = _configured_provider(monkeypatch)
    calls = _install_fake_generate_content(provider, monkeypatch, response_text=response_text)

    with pytest.raises(AIProviderMalformed) as excinfo:
        provider.generate("prompt")

    assert len(calls) == 1
    assert FAKE_API_KEY not in str(excinfo.value)


def test_successful_response_text_is_returned_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _configured_provider(monkeypatch)
    calls = _install_fake_generate_content(
        provider, monkeypatch, response_text="[claim-a]\n[claim-b]"
    )

    result = provider.generate("prompt")

    assert result == "[claim-a]\n[claim-b]"
    assert len(calls) == 1


# ---------------------------------------------------------------------
# MockAIProvider: sequenced responses + raise_on_call (new, this card),
# and the pre-existing canned/echo modes kept working unchanged.
# ---------------------------------------------------------------------


def test_mock_provider_sequenced_responses_returns_one_per_call_in_order() -> None:
    provider = MockAIProvider(responses=["[claim-a]", "[claim-a]"])

    first = provider.generate("selection prompt")
    second = provider.generate("verification prompt")

    assert first == "[claim-a]"
    assert second == "[claim-a]"
    assert provider.calls == ["selection prompt", "verification prompt"]


def test_mock_provider_sequenced_responses_can_differ_across_calls() -> None:
    """The exact shape a later card's two-pass pipeline needs: a
    selection-pass response and a different verification-pass response,
    each independently controlled."""
    provider = MockAIProvider(responses=["[claim-a]\n[claim-b]", "[claim-a]"])

    assert provider.generate("selection") == "[claim-a]\n[claim-b]"
    assert provider.generate("verification") == "[claim-a]"


def test_mock_provider_responses_exhausted_raises_assertion_error() -> None:
    provider = MockAIProvider(responses=["[claim-a]"])
    provider.generate("first call")

    with pytest.raises(AssertionError):
        provider.generate("second call -- nothing scripted for it")


def test_mock_provider_raise_on_call_raises_only_on_the_scripted_call_number() -> None:
    provider = MockAIProvider(responses=["[claim-a]", "[claim-a]"])
    provider.raise_on_call(2, AIProviderTimeout("verification call timed out"))

    first = provider.generate("selection prompt")
    assert first == "[claim-a]"

    with pytest.raises(AIProviderTimeout, match="verification call timed out"):
        provider.generate("verification prompt")

    # Both calls were still recorded even though the second one raised.
    assert provider.calls == ["selection prompt", "verification prompt"]


def test_mock_provider_raise_on_call_accepts_an_exception_class_too() -> None:
    provider = MockAIProvider()
    provider.raise_on_call(1, AIProviderQuota)

    with pytest.raises(AIProviderQuota):
        provider.generate("prompt")


def test_mock_provider_raise_on_call_takes_priority_over_responses_for_that_call() -> None:
    provider = MockAIProvider(responses=["[claim-a]", "[claim-b]"])
    provider.raise_on_call(1, AIProviderMalformed("selection call malformed"))

    with pytest.raises(AIProviderMalformed):
        provider.generate("prompt")
    # The 2nd call is unaffected and still gets its scripted response.
    assert provider.generate("prompt-2") == "[claim-b]"


def test_mock_provider_raise_on_call_rejects_a_call_number_below_one() -> None:
    provider = MockAIProvider()
    with pytest.raises(ValueError):
        provider.raise_on_call(0, AIProviderError("x"))


def test_mock_provider_existing_canned_response_mode_is_unaffected() -> None:
    provider = MockAIProvider(canned_response="[claim-real]")
    assert provider.generate("anything") == "[claim-real]"
    assert provider.generate("anything else") == "[claim-real]"


def test_mock_provider_existing_echo_default_mode_is_unaffected() -> None:
    provider = MockAIProvider()
    prompt = "CLAIM claim-1: field=x value=1 source=y verified_on=2026-01-01\n"
    assert provider.generate(prompt) == "[claim-1]"


def test_mock_provider_satisfies_ai_provider_protocol() -> None:
    assert isinstance(MockAIProvider(), AIProvider)
