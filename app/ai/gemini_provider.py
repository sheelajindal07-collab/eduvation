"""Real `AIProvider` implementation backed by the Gemini API — docs/
DECISIONS.md "2026-09-19 — AI provider: Google Gemini API (owner-
confirmed)". Uses `google-genai`, Google's current SDK (the older
`google-generativeai` package this decision predates is deprecated
upstream; `google-genai` is the maintained replacement).

**Never called by this task's own tests, and never called anywhere in
this codebase yet** — no route wires an actual `/ask` endpoint in this
task (deliberately out of scope; see `app/ai/__init__.py`). Constructing
one of these objects makes no network call by itself; only `.generate()`
does, and nothing in `tests/` invokes `.generate()` on a real
`GeminiProvider` instance.

Gated construction (mirrors `app/db/client.py`'s
`SupabaseNotConfiguredError` — "fail clearly, don't silently degrade"):
`GeminiProvider()` raises `GeminiNotConfiguredError` immediately unless
`Settings.gemini_api_key` is actually set, rather than constructing
successfully and failing later (or worse, silently falling back to some
other behaviour) the first time `.generate()` is called.
"""

from __future__ import annotations

from google import genai
from google.genai import types

from app.core.config import get_settings


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
        self._client = genai.Client(api_key=settings.gemini_api_key)
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
        milliseconds for the SDK's `http_options`).
        """
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                http_options=types.HttpOptions(timeout=self._timeout_seconds * 1000),
            ),
        )
        return response.text or ""
