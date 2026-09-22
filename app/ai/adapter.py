"""Pluggable AI provider interface — Lite Build Pack §9, `app/ai/__init__.py`.

Deliberately minimal. Every safety-relevant decision (which facts an
answer is allowed to be built from, how the prompt is constructed, how
the response is validated before anything reaches a student, spend
control) lives in `app/ai/grounding.py` and `app/ai/budget.py`, applied
uniformly to *any* provider. A provider implementation is trusted with
nothing more than "turn this already-built prompt string into a text
completion" — it is never asked to judge groundedness itself, because
"trust the model's own restraint" is not something this codebase is
willing to rely on as the only safeguard (CLAUDE.md: "AI never invents
facts").
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIProvider(Protocol):
    """A hosted text-generation provider, behind the adapter.

    Implementations (see `app/ai/mock_provider.py` for tests,
    `app/ai/gemini_provider.py` for the real Gemini-backed one) must
    raise on a transport/API failure rather than returning an empty or
    placeholder string, so a failure is visible to the caller instead of
    silently degrading into something that looks like a grounded answer.

    Confirmed compatible as-is with AI-3's hardening (no change needed to
    this Protocol's shape): a failure is one of `app/ai/schemas.py`'s four
    typed provider errors — `AIProviderTimeout`, `AIProviderQuota`,
    `AIProviderMalformed`, `AIProviderError` (the base class, for anything
    else) — never a provider-SDK-specific exception type. `Protocol`
    carries no `raises` clause in Python's type system, so this is a
    behavioural contract every implementation must uphold, checked by
    `tests/unit/test_ai_provider.py` for `GeminiProvider` and satisfiable
    by construction for `MockAIProvider` via its `raise_on_call` hook.
    """

    def generate(self, prompt: str) -> str:
        """Send `prompt` (already fully built by `app/ai/grounding.py`,
        containing only the permitted facts and the response-format
        instructions) to the provider and return its raw text response.

        Must NOT filter, validate or otherwise interpret the response —
        that is `app/ai/grounding.py`'s job, applied identically no
        matter which provider produced the text.
        """
        ...
