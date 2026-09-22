"""Real `AIProvider` implementation backed by the Gemini API — docs/
DECISIONS.md "2026-09-19 — AI provider: Google Gemini API (owner-
confirmed)". Uses `google-genai`, Google's current SDK (the older
`google-generativeai` package this decision predates is deprecated
upstream; `google-genai` is the maintained replacement).

**Never called by this task's own tests, and never called anywhere in
this codebase yet** — no route wires an actual `/ask` endpoint in this
task (deliberately out of scope; see `app/ai/__init__.py`). Constructing
one of these objects makes no network call by itself; only `.generate()`
does. `tests/unit/test_ai_provider.py` (AI-3) exercises every failure
path of `.generate()` through an injected fake `models.generate_content`
callable — never a real network call, never a real provider call.

Gated construction (mirrors `app/db/client.py`'s
`SupabaseNotConfiguredError` — "fail clearly, don't silently degrade"):
`GeminiProvider()` raises `GeminiNotConfiguredError` immediately unless
`Settings.gemini_api_key` is actually set, rather than constructing
successfully and failing later (or worse, silently falling back to some
other behaviour) the first time `.generate()` is called.

Hardening (AI-3, this module's own card)
-----------------------------------------
Three properties, each load-bearing:

1. **The SDK's own automatic retry is disabled, everywhere.** By default
   `google-genai==2.24.0` wraps every request in a `tenacity` retry loop
   (`app.ai.gemini_provider._NO_RETRY` mirrors what the installed SDK
   calls `HttpRetryOptions`; see `google.genai._api_client.retry_args` —
   `attempts=1` means exactly one attempt, no retry; the SDK itself
   normalises a caller's `attempts=0` to the same thing). This module
   sets it in two places for defence in depth: once as the `Client`'s own
   default `http_options` (covers any call that does not specify its
   own), and again on every individual `generate_content` call's
   `http_options` (an explicit per-request override the installed SDK
   supports — see `google.genai._api_client.BaseApiClient._request`'s
   "Support per request retry options"). A caller of this module (the
   two-pass pipeline, a later card) owns its own retry/backoff policy, if
   any — this module must never silently retry underneath it and spend
   budget or wall-clock time the caller did not ask for.
2. **No raw SDK exception ever escapes `.generate()`.** Every transport
   or API failure is caught and re-raised as one of the four typed
   errors `app/ai/schemas.py` defines: `AIProviderTimeout` (the request
   did not complete inside the deadline), `AIProviderQuota` (the
   provider refused on a 429/quota/rate-limit basis), `AIProviderMalformed`
   (the provider replied, but with an empty or otherwise unusable
   response), `AIProviderError` (anything else). A caller therefore never
   needs to know this module is backed by `google-genai` specifically.
3. **The constructed error message never repeats anything the SDK gave
   back.** Every message here is a fixed literal (plus, at most, a
   provider-assigned numeric status code) — never `str(exc)`, never
   `exc.message`, never the raw exception object. This is what makes "the
   API key can never appear in a log line or an exception's string
   representation" true by construction rather than by care: the key
   lives only in `self._client`'s internal HTTP headers (see
   `google.genai._api_client.BaseApiClient`), which this module never
   stringifies, logs, or embeds in a message.
   `tests/unit/test_ai_provider.py` deliberately triggers each error path
   with a fake client whose raised exception's own text *contains* a
   fake API key (an adversarial simulation of a worst-case SDK message)
   and asserts the key does not survive into the typed error this module
   raises.

Plain-text response mode: `GenerateContentConfig.response_mime_type`
defaults to `None` in the installed SDK, which is already plain text, not
JSON — `response_mime_type="text/plain"` below makes that explicit rather
than relying on an unstated default, since the two-pass selection/
verification format (a later card) is line-based, not JSON.
"""

from __future__ import annotations

from typing import Final

import httpx
from google import genai
from google.genai import errors, types

from app.ai.schemas import (
    AIProviderError,
    AIProviderMalformed,
    AIProviderQuota,
    AIProviderTimeout,
)
from app.core.config import get_settings

#: "Exactly one attempt, no retry" in the installed `google-genai==2.24.0`
#: SDK's own vocabulary — see the module docstring's "Hardening" section
#: and `google.genai._api_client.retry_args`, which treats `attempts=1`
#: (and normalises a supplied `attempts=0` to the same value) as "never
#: retry" rather than "never call".
_NO_RETRY: Final = types.HttpRetryOptions(attempts=1)

#: Status codes/substrings that mean "the provider's own quota or rate
#: limit refused this call" (as opposed to any other 4xx/5xx failure).
#: `429` is the standard HTTP rate-limit code; the string checks catch a
#: provider that instead reports the same condition with a different
#: numeric status (observed in practice across hosted APIs) but a
#: recognisable message/status string.
_QUOTA_STATUS_CODE = 429
_QUOTA_STATUS_MARKERS: Final = ("RESOURCE_EXHAUSTED",)
_QUOTA_MESSAGE_MARKERS: Final = ("quota", "rate limit", "rate-limit", "too many requests")


def _is_quota_error(exc: errors.ClientError) -> bool:
    """Whether `exc` represents the provider's own quota/rate-limit
    refusal, as opposed to any other client error (bad request, auth
    failure, ...). Never inspects or returns anything derived from the
    exception into a message — see the module docstring's point 3."""
    if exc.code == _QUOTA_STATUS_CODE:
        return True
    status = (exc.status or "").upper()
    if any(marker in status for marker in _QUOTA_STATUS_MARKERS):
        return True
    message = (exc.message or "").lower()
    return any(marker in message for marker in _QUOTA_MESSAGE_MARKERS)


class GeminiNotConfiguredError(RuntimeError):
    """Raised by `GeminiProvider()` when `GEMINI_API_KEY` is not set.

    Mirrors `app.db.client.SupabaseNotConfiguredError`: a missing
    credential is a clear, immediate construction-time failure, never a
    provider that silently no-ops or falls back to an unbounded/ungated
    behaviour.
    """


class GeminiProvider:
    """`AIProvider` backed by the real Gemini API. See module docstring.

    `model` defaults to a Flash-tier model — docs/BCION-Lite-Build-Pack.md
    §9 leaves "flash vs pro" open until M5's actual model selection, so
    this is a deliberately swappable default via the constructor
    parameter, not a hardcoded choice a caller cannot override.
    """

    def __init__(self, *, model: str = "gemini-2.5-flash") -> None:
        settings = get_settings()
        if not settings.ai_configured:
            raise GeminiNotConfiguredError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and fill in a "
                "real key via the provider dashboard (CLAUDE.md: no secrets in repo "
                "memory, values via provider dashboards / environment only)."
            )
        assert settings.gemini_api_key is not None
        # `http_options.retry_options` here is the Client-wide default —
        # see the module docstring's "Hardening" point 1. `generate()`
        # below repeats it per-call as a second, explicit layer.
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(retry_options=_NO_RETRY),
        )
        self._model = model
        self._timeout_seconds = settings.ai_request_timeout_seconds

    def generate(self, prompt: str) -> str:
        """Send `prompt` to Gemini and return its raw text response.

        `prompt` here is always the fully-built, citation-template prompt
        `app/ai/grounding.py` constructs — this method does no prompt
        construction, filtering or validation of its own; that happens
        uniformly for every provider in `app/ai/grounding.py`, applied to
        whatever text this method returns.

        `temperature=0` — a grounded-citation task wants the most
        literal, least creative reading of the supplied facts, not
        variety. The request timeout mirrors docs/SECURITY.md's
        15-second AI timeout (`Settings.ai_request_timeout_seconds`,
        milliseconds for the SDK's `http_options`). `response_mime_type`
        and `retry_options` are explained in the module docstring's
        "Hardening" section and "Plain-text response mode" paragraph.

        Raises exactly one of `app.ai.schemas`' four typed provider
        errors on any failure — see the module docstring's "Hardening"
        point 2 — and never the raw `google-genai`/`httpx` exception.
        Makes exactly one HTTP request: the SDK's own retry is disabled
        (point 1), so a failure here is never silently retried underneath
        the caller.
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="text/plain",
                    http_options=types.HttpOptions(
                        timeout=self._timeout_seconds * 1000,
                        retry_options=_NO_RETRY,
                    ),
                ),
            )
        except errors.ClientError as exc:
            if _is_quota_error(exc):
                raise AIProviderQuota(
                    "Gemini API refused the request on quota/rate-limit grounds "
                    f"(status {exc.code})."
                ) from None
            raise AIProviderError(
                f"Gemini API rejected the request (client error, status {exc.code})."
            ) from None
        except errors.ServerError as exc:
            raise AIProviderError(
                f"Gemini API returned a server error (status {exc.code})."
            ) from None
        except errors.APIError as exc:
            # Any other APIError subtype not already handled above.
            raise AIProviderError(
                f"Gemini API returned an error (status {exc.code})."
            ) from None
        except httpx.TimeoutException:
            raise AIProviderTimeout(
                "Gemini API did not respond inside the request deadline "
                f"({self._timeout_seconds}s)."
            ) from None
        except Exception as exc:  # noqa: BLE001 - last-resort typed-error boundary;
            # see the module docstring's "Hardening" point 2: no raw SDK/transport
            # exception may escape this method, and point 3: never str(exc).
            raise AIProviderError(
                f"Gemini API call failed unexpectedly ({type(exc).__name__})."
            ) from None

        text = response.text
        if text is None or not text.strip():
            raise AIProviderMalformed("Gemini API returned an empty response.")
        return text
