"""In-memory spend-cap guard for the AI adapter — docs/SECURITY.md "AI /
LLM controls": "atomic per-request spend reservation; global + per-account
spend caps; graceful fallback to deterministic tools at the cap."

A single in-process counter is deliberately the right amount of
engineering here: CLAUDE.md pins this pilot at 10-100 users and its own
Postgres-jobs-table-plus-one-worker stack choice sets the precedent of
not reaching for distributed infrastructure this project doesn't need
yet. This is a request-count budget (how many provider calls may be made
today), not the rupee-denominated `ai_monthly_spend_cap_inr` figure in
`app/core/config.py` — that one is a business/ops ceiling tracked
separately; this one is the mechanical circuit breaker that actually
stops a runaway loop of calls mid-day.

A future multi-worker deployment would need to move this to a shared
counter (e.g. a Postgres row, mirroring the jobs table already used
elsewhere) — noted, not built, since Lite runs one worker process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.config import get_settings


class AIBudgetExceededError(RuntimeError):
    """Raised when a caller tries to reserve another provider call after
    today's request budget is already exhausted.

    Mirrors `app/db/client.py`'s `SupabaseNotConfiguredError` pattern:
    fail loudly and specifically the moment the cap is hit, rather than
    silently skipping the call, returning an empty result, or (worse)
    letting the request fall through to some other, ungoverned code path.
    Raised BEFORE the provider is ever invoked — reservation happens
    first, so a refusal here means no request reached the provider and no
    spend was incurred.
    """


@dataclass
class AIRequestBudget:
    """A process-local counter of provider calls made "today" (UTC
    calendar date), reset automatically the first time it is touched on a
    new date. Not thread-safe beyond what Python's GIL already gives a
    single `+= 1`; adequate for this pilot's one worker process."""

    daily_request_budget: int
    _count: int = field(default=0, init=False)
    _day: date | None = field(default=None, init=False)

    def _roll_if_new_day(self, *, today: date) -> None:
        if self._day != today:
            self._day = today
            self._count = 0

    def remaining(self, *, today: date | None = None) -> int:
        """How many calls are still allowed today. Does not reserve one —
        purely informational (e.g. for a future "AI unavailable today"
        banner)."""
        as_of_today = today or date.today()
        self._roll_if_new_day(today=as_of_today)
        return max(0, self.daily_request_budget - self._count)

    def reserve(self, *, today: date | None = None) -> None:
        """Reserve one call against today's budget.

        Raises `AIBudgetExceededError` — and reserves nothing — once
        `daily_request_budget` calls have already been reserved today.
        Callers (see `app/ai/grounding.py`) must call this immediately
        before invoking the provider, and must not invoke the provider at
        all if this raises.
        """
        as_of_today = today or date.today()
        self._roll_if_new_day(today=as_of_today)
        if self._count >= self.daily_request_budget:
            raise AIBudgetExceededError(
                f"AI daily request budget of {self.daily_request_budget} "
                f"already used for {as_of_today.isoformat()}. The provider "
                "was not called."
            )
        self._count += 1


def default_budget() -> AIRequestBudget:
    """A fresh budget sized from `Settings.ai_daily_request_budget`.

    Not process-wide cached on purpose (unlike `get_settings()`): a
    caller that wants a single shared counter across requests (the real
    use case) should construct one `AIRequestBudget` itself at app
    startup and reuse that instance — this factory exists for tests and
    one-off scripts that just want "today's configured cap, please."
    """
    return AIRequestBudget(daily_request_budget=get_settings().ai_daily_request_budget)
