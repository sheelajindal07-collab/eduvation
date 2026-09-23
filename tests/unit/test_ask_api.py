"""Tests for AI-7 — wiring `app/ai/pipeline.py` (AI-6, merged) into
GET /ask (`app/api/ask.py`) and GET /ask/view (`app/web/ask_pages.py`)
as an ADDITIVE layer over the UI-11/BCI-014 deterministic baseline.

`tests/unit/test_web_ask.py` (UI-11, not owned by this card) already
covers the deterministic-only behaviour in full; `tests/db/test_ask_view.py`
(also UI-11) proves that same behaviour against the real stack and is run
unmodified as this card's own proof that the baseline is untouched.
`tests/unit/test_ai_pipeline.py` (AI-6, not owned by this card) already
covers `app.ai.pipeline.answer()`'s own two-pass correctness in full.

This file therefore tests exactly the seam AI-7 owns:

- `app.api.ask._pipeline_answer()` in isolation -- the AI feature-flag
  gate, the `GeminiProvider()` construction/`GeminiNotConfiguredError`
  catch, the `AskRequest` built from `entity_kind`/`entity_id`, and the
  process-local `_ai_budget()` singleton -- via direct calls and via
  monkeypatching `app.api.ask.GeminiProvider` / `app.api.ask.ai_pipeline
  .answer` (never the real network, never a real provider call).
- Both routes' own rendering logic -- fact cards are always present,
  `ai_sentences`/`ai_citations` are populated only when the pipeline
  returned `AIAnswerStatus.answered`, and every other status renders
  nothing extra -- via monkeypatching `app.api.ask._pipeline_answer` /
  `app.web.ask_pages._pipeline_answer` directly (a separate name binding
  per module, since `from app.api.ask import _pipeline_answer` copies the
  reference at import time).

BCI-026 extends this file with the second seam these two routes own: the
per-request AI spend IDENTITY, and the database-backed budget built from
it (`app.api.ask._ai_budget_for_request`). Everything here is still
fake-only -- the account lookup is a fake `client.auth.get_user`, the
`AIRequestBudgetDB` is never actually RPC'd -- because the real
reservation reaching a real `ai_usage` row is proved against the live
stack in `tests/db/test_ask_view.py`, which is where that belongs.

No real database, no real provider, no network call anywhere in this
file.
"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.ask as ask_module
import app.web.ask_pages as ask_pages_module
from app.ai.budget import AIBudgetExceededError, AIRequestBudget
from app.ai.budget_db import ACCOUNT, GUEST, AIRequestBudgetDB, AIUsageError, identity_digest
from app.ai.gemini_provider import GeminiNotConfiguredError
from app.ai.schemas import AIAnswerStatus, AskRequest
from app.ai.schemas import Answer as AIAnswer
from app.ai.what_changed import WhatChangedAnswer
from app.api.ask import router as ask_json_router
from app.api.deps import get_db_client
from app.core.config import Settings, get_settings
from app.web.ask_pages import router as ask_html_router
from app.web.common import _db_client_or_none
from app.web.guest_session import COOKIE_NAME as GUEST_SESSION_COOKIE_NAME

_PATHWAY_ID = "11111111-1111-1111-1111-111111111111"
_CAREER_ID = "33333333-3333-3333-3333-333333333333"
_SOURCE_ID = "22222222-2222-2222-2222-222222222222"
_FRESH_VERIFICATION_DATE = "2026-09-01"  # well within the 180-day SLA of "today" in tests
_FALLBACK_COPY = "You can still compare routes and use the calculators."


# ---------------------------------------------------------------------
# Fakes -- a minimal in-memory `Client` stand-in for
# `assemble_ask_answer()`'s `.table(...).select().eq().in_().execute()`
# calls, the same convention `tests/unit/test_web_ask.py`'s own
# `_FakeDbClient`/`_FakeQuery` use (duplicated here, not imported, so
# this file stays self-contained -- that module is not owned by this
# card).
# ---------------------------------------------------------------------


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def in_(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def execute(self) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeDbClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._tables.get(name, []))


# ---------------------------------------------------------------------
# BCI-026 fakes -- the ACCOUNT half of identity resolution is a live
# `client.auth.get_user(jwt=...)` call (the pattern
# `app/api/plans.py`'s `_current_user_id()` establishes). These stand in
# for it; no token is ever decoded here, and no network call is made.
# ---------------------------------------------------------------------

_ACCOUNT_ID = "aaaaaaaa-1111-2222-3333-444444444444"
_OTHER_ACCOUNT_ID = "bbbbbbbb-1111-2222-3333-444444444444"
_GUEST_TOKEN = "guest-session-token-for-tests-only"
_BEARER = {"Authorization": "Bearer test-only-access-token"}


class _FakeUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


class _FakeUserResponse:
    def __init__(self, user: _FakeUser | None) -> None:
        self.user = user


class _FakeAuth:
    """Just enough of `supabase.Client.auth` for `_ai_budget_for_request`.

    `outcome` is the account id to resolve to, `None` for "this token
    resolves to no user", or an exception instance to raise -- the three
    things a real `get_user(jwt=...)` can do to this code path.
    """

    def __init__(self, outcome: str | None | Exception) -> None:
        self._outcome = outcome
        self.jwts_seen: list[str | None] = []

    def get_user(self, jwt: str | None = None) -> _FakeUserResponse | None:
        self.jwts_seen.append(jwt)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        if self._outcome is None:
            return _FakeUserResponse(None)
        return _FakeUserResponse(_FakeUser(self._outcome))


class _FakeDbClientWithAuth(_FakeDbClient):
    def __init__(
        self,
        tables: dict[str, list[dict[str, Any]]],
        *,
        auth_outcome: str | None | Exception = _ACCOUNT_ID,
    ) -> None:
        super().__init__(tables)
        self.auth = _FakeAuth(auth_outcome)


def _claim_row(
    *,
    field: str,
    value: Any,
    entity_type: str = "Pathway",
    entity_id: str = _PATHWAY_ID,
    status: str = "published",
    verification_date: str = _FRESH_VERIFICATION_DATE,
    source_id: str = _SOURCE_ID,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"claim-{field}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field": field,
        "value": value,
        "source_id": source_id,
        "verification_date": verification_date,
        "verifier": "tester",
        "status": status,
        "review_due_date": "2099-01-01",
        "currency": currency,
    }


def _source_row(source_id: str = _SOURCE_ID) -> dict[str, Any]:
    return {
        "id": source_id,
        "authority_name": "Test Authority",
        "official_url": "https://example.invalid/test-source",
        "source_type": "official",
    }


def _tables_with_one_published_claim(
    *, entity_type: str = "Pathway", entity_id: str = _PATHWAY_ID
) -> dict[str, list[dict[str, Any]]]:
    return {
        "claims": [
            _claim_row(
                field="entry_requirements",
                value="Class 12 pass",
                entity_type=entity_type,
                entity_id=entity_id,
            )
        ],
        "sources": [_source_row()],
    }


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ask_json_router)
    app.include_router(ask_html_router)
    return app


def _client_with_tables(tables: dict[str, list[dict[str, Any]]]) -> TestClient:
    app = _make_app()
    fake_db = _FakeDbClient(tables)
    app.dependency_overrides[get_db_client] = lambda: fake_db
    app.dependency_overrides[_db_client_or_none] = lambda: fake_db
    return TestClient(app)


def _client_with_auth_db(
    tables: dict[str, list[dict[str, Any]]],
    *,
    auth_outcome: str | None | Exception = _ACCOUNT_ID,
) -> tuple[TestClient, _FakeDbClientWithAuth]:
    """BCI-026: the same standalone app, but with a fake db that also
    answers `auth.get_user(jwt=...)` -- returned alongside the client so
    a test can assert what the route asked it."""
    app = _make_app()
    fake_db = _FakeDbClientWithAuth(tables, auth_outcome=auth_outcome)
    app.dependency_overrides[get_db_client] = lambda: fake_db
    app.dependency_overrides[_db_client_or_none] = lambda: fake_db
    return TestClient(app), fake_db


def _settings(*, ai_enabled: bool = True, configured: bool = True) -> Settings:
    """Same idiom as `tests/unit/test_ai_pipeline.py`'s own `_settings()`
    helper -- `_env_file=None` bypasses any real `.env` on disk."""
    return Settings(
        _env_file=None,
        ai_enabled=ai_enabled,
        gemini_api_key="test-only-not-a-real-key" if configured else None,
    )


def _explode(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("must not be called on this path")


class _FakeGeminiProviderNotConfigured:
    """Stands in for the real `GeminiProvider`, whose own constructor
    raises `GeminiNotConfiguredError` when `GEMINI_API_KEY` is missing --
    this fake raises unconditionally, so a test can exercise the route's
    catch of that error without depending on real Settings plumbing."""

    def __init__(self) -> None:
        raise GeminiNotConfiguredError("GEMINI_API_KEY is not set (test double).")


class _FakeGeminiProviderOK:
    """Constructing this always succeeds and makes no network call.
    `.generate()` is never exercised in tests that use this fake, because
    `app.api.ask.ai_pipeline.answer` is monkeypatched separately in every
    test that uses it -- this class only proves *construction* happened,
    never a real provider call."""

    def generate(self, prompt: str) -> str:  # pragma: no cover - never called
        raise AssertionError("must not be called -- ai_pipeline.answer is monkeypatched")


@pytest.fixture(autouse=True)
def _reset_caches() -> Any:
    """`get_settings()` and `app.api.ask._ai_budget()` are both
    `lru_cache`d process-wide (this card's own module-level singleton
    budget mirrors `get_settings()`'s lifecycle, by design -- see
    `_ai_budget()`'s own docstring) -- clear both around every test so
    one test's settings/budget state can never leak into the next."""
    get_settings.cache_clear()
    ask_module._ai_budget.cache_clear()
    yield
    get_settings.cache_clear()
    ask_module._ai_budget.cache_clear()


# ---------------------------------------------------------------------
# `_pipeline_answer()` in isolation.
# ---------------------------------------------------------------------


class TestPipelineAnswerHelper:
    def test_returns_none_and_never_touches_the_pipeline_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ask_module, "get_settings", lambda: _settings(ai_enabled=False))
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        result = ask_module._pipeline_answer(
            object(),
            template,
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 22),
        )

        assert result is None

    def test_returns_none_and_never_touches_the_pipeline_when_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=False)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        result = ask_module._pipeline_answer(
            object(),
            template,
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 22),
        )

        assert result is None

    def test_gemini_not_configured_error_is_caught_as_ai_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE proof this card's completion report asks for:
        `GeminiNotConfiguredError` never escapes `_pipeline_answer()`."""
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderNotConfigured)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)  # must never be reached
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        result = ask_module._pipeline_answer(
            object(),
            template,
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 22),
        )

        assert result is not None
        assert result.status == AIAnswerStatus.ai_unavailable
        assert result.sentences == []
        assert result.citations == []

    def test_builds_a_pathway_id_request_for_a_pathway_entity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            captured["db"] = db
            captured["request"] = request
            captured["provider"] = provider
            captured["budget"] = budget
            captured["as_of"] = as_of
            return AIAnswer(status=AIAnswerStatus.answered, sentences=["s"], citations=[])

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]
        as_of = date(2026, 9, 22)
        db = object()

        result = ask_module._pipeline_answer(
            db, template, entity_kind="pathway", entity_id=_PATHWAY_ID, as_of=as_of
        )

        assert result is not None
        assert result.status == AIAnswerStatus.answered
        request = captured["request"]
        assert isinstance(request, AskRequest)
        assert request.template_id == "pathway_overview"
        assert request.pathway_id == _PATHWAY_ID
        assert request.career_id is None
        assert captured["db"] is db
        assert captured["as_of"] == as_of
        assert isinstance(captured["provider"], _FakeGeminiProviderOK)
        assert captured["budget"] is ask_module._ai_budget()

    def test_builds_a_career_id_request_for_a_career_entity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            captured["request"] = request
            return AIAnswer(status=AIAnswerStatus.not_available)

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        ask_module._pipeline_answer(
            object(), template, entity_kind="career", entity_id=_CAREER_ID, as_of=date(2026, 9, 22)
        )

        request = captured["request"]
        assert request.pathway_id is None
        assert request.career_id == _CAREER_ID


class TestAiBudgetSingleton:
    def test_is_shared_across_calls_not_reconstructed_per_call(self) -> None:
        first = ask_module._ai_budget()
        second = ask_module._ai_budget()
        assert first is second


# ---------------------------------------------------------------------
# BCI-026 -- the per-request identity and the database-backed budget.
# ---------------------------------------------------------------------


class TestGuestSessionCookieName:
    def test_matches_the_web_layers_own_constant_exactly(self) -> None:
        """`app/api/ask.py` writes the cookie name as a literal rather
        than importing it (that would be the repo's first
        `app/api/** -> app/web/**` import -- see that constant's own
        docstring). This is the check that keeps the two in step; a test
        module may import both freely."""
        assert ask_module._GUEST_SESSION_COOKIE_NAME == GUEST_SESSION_COOKIE_NAME


class TestBudgetDbIsADropIn:
    """This card's item 4: CONFIRM, rather than assume, that
    `AIRequestBudgetDB` really is interchangeable with `AIRequestBudget`
    for the only two calls `app.ai.pipeline.answer()`/
    `app.ai.what_changed.answer_what_changed()` make. Neither had ever
    been exercised end-to-end through a real route before this card."""

    @pytest.mark.parametrize("method", ["reserve", "remaining"])
    def test_both_budgets_expose_the_same_call_signature(self, method: str) -> None:
        in_memory = inspect.signature(getattr(AIRequestBudget, method))
        database = inspect.signature(getattr(AIRequestBudgetDB, method))
        assert list(in_memory.parameters) == list(database.parameters)
        assert in_memory.parameters["today"].kind is inspect.Parameter.KEYWORD_ONLY
        assert database.parameters["today"].kind is inspect.Parameter.KEYWORD_ONLY
        assert database.parameters["today"].default is None

    def test_reserve_accepts_the_today_kwarg_the_pipeline_actually_passes(self) -> None:
        """`app/ai/pipeline.py` calls `budget.reserve(today=resolved_as_of)`.
        A signature check alone would not catch a body that rejected it,
        so this really calls it -- against a fake RPC, never a database."""
        calls: list[tuple[str, dict[str, Any]]] = []

        class _FakeRpcResult:
            def __init__(self, data: Any) -> None:
                self.data = data

        class _FakeRpc:
            def __init__(self, data: Any) -> None:
                self._data = data

            def execute(self) -> _FakeRpcResult:
                return _FakeRpcResult(self._data)

        class _FakeRpcClient:
            def rpc(self, name: str, params: dict[str, Any]) -> _FakeRpc:
                calls.append((name, params))
                return _FakeRpc("11111111-2222-3333-4444-555555555555")

        budget = AIRequestBudgetDB.for_account(
            _ACCOUNT_ID, template_id="pathway_overview", client=_FakeRpcClient()
        )
        budget.reserve(today=date(2026, 9, 23))

        assert [name for name, _ in calls] == ["ai_reserve"]
        params = calls[0][1]
        assert params["p_identity_kind"] == ACCOUNT
        assert params["p_identity_hash"] == identity_digest(_ACCOUNT_ID)
        assert params["p_template_id"] == "pathway_overview"
        assert params["p_calls"] == 1


class TestAiBudgetForRequestIdentityResolution:
    """The three identity cases this card names, one test each."""

    def test_account_a_bearer_token_builds_a_db_budget_for_that_account(self) -> None:
        db = _FakeDbClientWithAuth({}, auth_outcome=_ACCOUNT_ID)

        budget = ask_module._ai_budget_for_request(
            db,
            template_id="pathway_overview",
            authorization="Bearer test-only-access-token",
            guest_session_token=None,
        )

        assert isinstance(budget, ask_module._GuardedDBBudget)
        inner = budget.inner
        assert isinstance(inner, AIRequestBudgetDB)
        assert inner.identity_kind == ACCOUNT
        assert inner.identity_hash == identity_digest(_ACCOUNT_ID)
        assert inner.template_id == "pathway_overview"
        # 0015 binds an ACCOUNT reservation to auth.uid() on the
        # connection, so the request's own RLS-scoped client is the only
        # one that can make it -- never a fresh anon client.
        assert inner.client is db
        # The token was passed explicitly, never decoded here.
        assert db.auth.jwts_seen == ["test-only-access-token"]

    def test_guest_a_session_cookie_builds_a_db_budget_for_that_session(self) -> None:
        db = _FakeDbClientWithAuth({})

        budget = ask_module._ai_budget_for_request(
            db,
            template_id="cost_breakdown",
            authorization=None,
            guest_session_token=_GUEST_TOKEN,
        )

        assert isinstance(budget, ask_module._GuardedDBBudget)
        inner = budget.inner
        assert inner.identity_kind == GUEST
        assert inner.identity_hash == identity_digest(_GUEST_TOKEN)
        assert inner.client is db
        # No account lookup at all on the guest path.
        assert db.auth.jwts_seen == []

    def test_neither_falls_back_to_the_existing_global_in_memory_budget(self) -> None:
        budget = ask_module._ai_budget_for_request(
            _FakeDbClientWithAuth({}),
            template_id="pathway_overview",
            authorization=None,
            guest_session_token=None,
        )

        assert budget is ask_module._ai_budget()

    def test_an_empty_guest_cookie_is_treated_as_no_cookie(self) -> None:
        """Matches `app/web/guest_session.py`'s `token_from_request`: a
        browser handed `bcion_guest_session=` has no session."""
        budget = ask_module._ai_budget_for_request(
            _FakeDbClientWithAuth({}),
            template_id="pathway_overview",
            authorization=None,
            guest_session_token="   ",
        )

        assert budget is ask_module._ai_budget()

    def test_a_non_bearer_authorization_header_is_not_an_account(self) -> None:
        db = _FakeDbClientWithAuth({})

        budget = ask_module._ai_budget_for_request(
            db,
            template_id="pathway_overview",
            authorization="Basic not-a-bearer-token",
            guest_session_token=None,
        )

        assert budget is ask_module._ai_budget()
        assert db.auth.jwts_seen == []

    def test_an_account_never_falls_through_to_the_guest_cookie(self) -> None:
        """A signed-in student who also carries a stale guest cookie must
        be capped as THEMSELVES, never as that guest session."""
        db = _FakeDbClientWithAuth({}, auth_outcome=_ACCOUNT_ID)

        budget = ask_module._ai_budget_for_request(
            db,
            template_id="pathway_overview",
            authorization="Bearer test-only-access-token",
            guest_session_token=_GUEST_TOKEN,
        )

        assert isinstance(budget, ask_module._GuardedDBBudget)
        assert budget.inner.identity_kind == ACCOUNT
        assert budget.inner.identity_hash == identity_digest(_ACCOUNT_ID)

    def test_two_accounts_get_two_different_identities(self) -> None:
        first = ask_module._ai_budget_for_request(
            _FakeDbClientWithAuth({}, auth_outcome=_ACCOUNT_ID),
            template_id="pathway_overview",
            authorization="Bearer a",
            guest_session_token=None,
        )
        second = ask_module._ai_budget_for_request(
            _FakeDbClientWithAuth({}, auth_outcome=_OTHER_ACCOUNT_ID),
            template_id="pathway_overview",
            authorization="Bearer b",
            guest_session_token=None,
        )

        assert isinstance(first, ask_module._GuardedDBBudget)
        assert isinstance(second, ask_module._GuardedDBBudget)
        assert first.inner.identity_hash != second.inner.identity_hash

    def test_a_bearer_token_that_resolves_to_no_user_raises_rather_than_falling_back(
        self,
    ) -> None:
        """Never the global budget for a real auth problem -- that would
        spend it against a counter shared with everyone else and hide
        it."""
        with pytest.raises(ask_module.AIBudgetUnavailableError):
            ask_module._ai_budget_for_request(
                _FakeDbClientWithAuth({}, auth_outcome=None),
                template_id="pathway_overview",
                authorization="Bearer expired-or-forged",
                guest_session_token=_GUEST_TOKEN,
            )

    def test_a_raising_account_lookup_raises_the_typed_error_not_the_raw_one(self) -> None:
        with pytest.raises(ask_module.AIBudgetUnavailableError):
            ask_module._ai_budget_for_request(
                _FakeDbClientWithAuth({}, auth_outcome=RuntimeError("auth service is down")),
                template_id="pathway_overview",
                authorization="Bearer test-only-access-token",
                guest_session_token=None,
            )


def cast_any(value: Any) -> Any:
    """Tiny readability shim -- `_GuardedDBBudget.inner` is annotated
    `AIRequestBudgetDB`, and the tests below deliberately pass a stand-in
    with the same two methods to exercise the guard without a database."""
    return value


class TestGuardedDbBudget:
    """A cap and a bug must not look the same -- `app/ai/budget_db.py`'s
    own rule, applied at this module's boundary."""

    def test_a_genuine_cap_is_re_raised_unchanged_for_the_pipeline_to_handle(self) -> None:
        class _CappedBudget:
            def reserve(self, *, today: date | None = None) -> None:
                raise AIBudgetExceededError("AI budget exceeded")

            def remaining(self, *, today: date | None = None) -> int:
                return 0

        guarded = ask_module._GuardedDBBudget(cast_any(_CappedBudget()))

        with pytest.raises(AIBudgetExceededError):
            guarded.reserve()

    @pytest.mark.parametrize(
        "error",
        [
            AIUsageError("ai_reserve: identity_kind 'account' requires a signed-in caller"),
            RuntimeError("PGRST202: function ai_reserve does not exist"),
        ],
    )
    def test_every_non_cap_failure_becomes_the_typed_unavailable_error(
        self, error: Exception
    ) -> None:
        class _BrokenBudget:
            def reserve(self, *, today: date | None = None) -> None:
                raise error

            def remaining(self, *, today: date | None = None) -> int:
                raise error

        guarded = ask_module._GuardedDBBudget(cast_any(_BrokenBudget()))

        with pytest.raises(ask_module.AIBudgetUnavailableError):
            guarded.reserve()
        with pytest.raises(ask_module.AIBudgetUnavailableError):
            guarded.remaining()


class TestPipelineAnswerBudgetWiring:
    """`_pipeline_answer()` hands the pipeline the RIGHT budget -- the
    whole point of this card."""

    def _capture_budget(
        self, monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
    ) -> None:
        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            captured["budget"] = budget
            return AIAnswer(status=AIAnswerStatus.answered, sentences=["s"], citations=[])

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)

    def test_an_account_request_reaches_the_pipeline_with_its_own_db_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture_budget(monkeypatch, captured)

        ask_module._pipeline_answer(
            _FakeDbClientWithAuth({}, auth_outcome=_ACCOUNT_ID),
            ask_module.ASK_TEMPLATES["pathway_overview"],
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 23),
            authorization="Bearer test-only-access-token",
            guest_session_token=None,
        )

        budget = captured["budget"]
        assert isinstance(budget, ask_module._GuardedDBBudget)
        assert budget.inner.identity_kind == ACCOUNT
        assert budget.inner.identity_hash == identity_digest(_ACCOUNT_ID)
        assert budget.inner.template_id == "pathway_overview"

    def test_a_guest_request_reaches_the_pipeline_with_its_own_db_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture_budget(monkeypatch, captured)

        ask_module._pipeline_answer(
            _FakeDbClientWithAuth({}),
            ask_module.ASK_TEMPLATES["cost_breakdown"],
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 23),
            guest_session_token=_GUEST_TOKEN,
        )

        budget = captured["budget"]
        assert isinstance(budget, ask_module._GuardedDBBudget)
        assert budget.inner.identity_kind == GUEST
        assert budget.inner.identity_hash == identity_digest(_GUEST_TOKEN)

    def test_no_identity_at_all_still_reaches_the_pipeline_with_the_global_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture_budget(monkeypatch, captured)

        ask_module._pipeline_answer(
            _FakeDbClientWithAuth({}),
            ask_module.ASK_TEMPLATES["pathway_overview"],
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 23),
        )

        assert captured["budget"] is ask_module._ai_budget()

    def test_a_budget_construction_failure_degrades_to_ai_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This card's item 5: never a 500, and never a silent
        fall-through to the global budget that would mask a real auth
        problem."""
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)

        result = ask_module._pipeline_answer(
            _FakeDbClientWithAuth({}, auth_outcome=None),
            ask_module.ASK_TEMPLATES["pathway_overview"],
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 23),
            authorization="Bearer expired-or-forged",
        )

        assert result is not None
        assert result.status == AIAnswerStatus.ai_unavailable
        assert result.sentences == []
        assert result.citations == []

    def test_a_non_cap_budget_failure_during_reserve_degrades_to_ai_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure mode the in-memory budget structurally could not
        have: `ai_reserve()` itself erroring (0011 unapplied, a BCAI3
        protocol error). It must not escape as a 500."""

        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            budget.reserve(today=as_of)
            raise AssertionError("unreachable -- reserve() must have raised")

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)

        class _RaisingRpcClient:
            def rpc(self, name: str, params: dict[str, Any]) -> Any:
                raise RuntimeError("PGRST202: function ai_reserve does not exist")

        db = _FakeDbClientWithAuth({}, auth_outcome=_ACCOUNT_ID)
        db.auth = _FakeAuth(_ACCOUNT_ID)
        monkeypatch.setattr(
            ask_module.AIRequestBudgetDB,
            "_db",
            lambda self: _RaisingRpcClient(),
        )

        result = ask_module._pipeline_answer(
            db,
            ask_module.ASK_TEMPLATES["pathway_overview"],
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 23),
            authorization="Bearer test-only-access-token",
        )

        assert result is not None
        assert result.status == AIAnswerStatus.ai_unavailable


class TestWhatChangedAnswerBudgetWiring:
    """`what_changed` shares the identity, because the cap is per
    identity and not per template."""

    def test_an_account_request_reaches_what_changed_with_its_own_db_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_what_changed(
            db: Any, claim_id: str, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> WhatChangedAnswer:
            captured["budget"] = budget
            return WhatChangedAnswer(status=AIAnswerStatus.not_available)

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module, "answer_what_changed", _fake_what_changed)

        ask_module._what_changed_answer(
            _FakeDbClientWithAuth({}, auth_outcome=_ACCOUNT_ID),
            "55555555-5555-5555-5555-555555555555",
            as_of=date(2026, 9, 23),
            authorization="Bearer test-only-access-token",
        )

        budget = captured["budget"]
        assert isinstance(budget, ask_module._GuardedDBBudget)
        assert budget.inner.identity_kind == ACCOUNT
        assert budget.inner.template_id == "what_changed"

    def test_a_budget_construction_failure_degrades_to_ai_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module, "answer_what_changed", _explode)

        result = ask_module._what_changed_answer(
            _FakeDbClientWithAuth({}, auth_outcome=None),
            "55555555-5555-5555-5555-555555555555",
            as_of=date(2026, 9, 23),
            authorization="Bearer expired-or-forged",
        )

        assert result is not None
        assert result.status == AIAnswerStatus.ai_unavailable


class TestRoutesCarryTheIdentityThroughToTheBudget:
    """End to end through both routes' own signatures -- the Authorization
    header and the `bcion_guest_session` cookie really do reach
    `_ai_budget_for_request`."""

    def _capture(
        self, monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
    ) -> None:
        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            captured["budget"] = budget
            return AIAnswer(status=AIAnswerStatus.not_available)

        ai_on = _settings(ai_enabled=True, configured=True)
        monkeypatch.setattr(ask_module, "get_settings", lambda: ai_on)
        monkeypatch.setattr(ask_pages_module, "get_settings", lambda: ai_on)
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)

    def test_json_route_with_a_bearer_token_uses_an_account_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture(monkeypatch, captured)
        client, _ = _client_with_auth_db(_tables_with_one_published_claim())

        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID},
            headers=_BEARER,
        )

        assert response.status_code == 200
        assert captured["budget"].inner.identity_kind == ACCOUNT
        assert captured["budget"].inner.identity_hash == identity_digest(_ACCOUNT_ID)

    def test_json_route_with_a_guest_cookie_uses_a_guest_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture(monkeypatch, captured)
        client, _ = _client_with_auth_db(_tables_with_one_published_claim())
        client.cookies.set(GUEST_SESSION_COOKIE_NAME, _GUEST_TOKEN)

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert captured["budget"].inner.identity_kind == GUEST
        assert captured["budget"].inner.identity_hash == identity_digest(_GUEST_TOKEN)

    def test_json_route_with_no_identity_uses_the_global_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture(monkeypatch, captured)
        client, _ = _client_with_auth_db(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert captured["budget"] is ask_module._ai_budget()

    def test_html_page_with_a_guest_cookie_uses_a_guest_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture(monkeypatch, captured)
        client, _ = _client_with_auth_db(_tables_with_one_published_claim())
        client.cookies.set(GUEST_SESSION_COOKIE_NAME, _GUEST_TOKEN)

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert captured["budget"].inner.identity_kind == GUEST
        assert captured["budget"].inner.identity_hash == identity_digest(_GUEST_TOKEN)

    def test_html_page_with_a_bearer_token_uses_an_account_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        self._capture(monkeypatch, captured)
        client, _ = _client_with_auth_db(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view",
            params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID},
            headers=_BEARER,
        )

        assert response.status_code == 200
        assert captured["budget"].inner.identity_kind == ACCOUNT
        assert captured["budget"].inner.identity_hash == identity_digest(_ACCOUNT_ID)

    def test_neither_route_ever_sets_a_guest_session_cookie(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The documented judgment call: a session-less guest is NOT given
        a new guest session by these two GET routes."""
        captured: dict[str, Any] = {}
        self._capture(monkeypatch, captured)
        client, _ = _client_with_auth_db(_tables_with_one_published_claim())

        for path in ("/ask", "/ask/view"):
            response = client.get(
                path, params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
            )
            assert response.status_code == 200, path
            assert "set-cookie" not in {k.lower() for k in response.headers}, path
            assert GUEST_SESSION_COOKIE_NAME not in client.cookies, path


# ---------------------------------------------------------------------
# GET /ask (JSON route) -- fact cards always present; ai_sentences/
# ai_citations additive-only.
# ---------------------------------------------------------------------


class TestAskJsonRouteAiWiring:
    def test_never_calls_the_pipeline_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []
        assert any(c["field"] == "entry_requirements" for c in body["fact_cards"])

    def test_answered_renders_ai_sentences_and_citations_alongside_fact_cards(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE proof this card's completion report asks for: AI on +
        pipeline `answered` renders sentences/citations alongside, never
        instead of, the deterministic fact cards."""
        canned = AIAnswer(
            status=AIAnswerStatus.answered,
            sentences=["According to GSEB: entry requirements is Class 12 pass."],
            citations=[
                {
                    "record_id": "rec-1",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "GSEB",
                    "source_url": "https://gseb.example.invalid",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_module, "_pipeline_answer", lambda *a, **k: canned)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        # The deterministic fact card is still present -- never replaced.
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["entry_requirements"]["value"]["value"] == "Class 12 pass"
        # The AI content is present ALONGSIDE it.
        assert body["ai_sentences"] == canned.sentences
        assert body["ai_citations"] == canned.citations

    @pytest.mark.parametrize(
        "status",
        [
            AIAnswerStatus.not_available,
            AIAnswerStatus.insufficient_information,
            AIAnswerStatus.ai_unavailable,
            AIAnswerStatus.budget_exhausted,
            AIAnswerStatus.unsupported_template,
        ],
    )
    def test_every_non_answered_status_renders_exactly_what_ai_off_already_rendered(
        self, monkeypatch: pytest.MonkeyPatch, status: AIAnswerStatus
    ) -> None:
        """THE proof this card's completion report asks for: AI on +
        pipeline falling back to any non-`answered` status renders
        exactly what AI-off already rendered -- no blank page, no error,
        no second, conflicting message."""
        tables = _tables_with_one_published_claim()
        baseline = _client_with_tables(tables).get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )
        assert baseline.status_code == 200
        baseline_body = baseline.json()

        canned = AIAnswer(
            status=status,
            citations=[
                {
                    "record_id": "rec-1",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "GSEB",
                    "source_url": None,
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_module, "_pipeline_answer", lambda *a, **k: canned)
        client = _client_with_tables(tables)

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["fact_cards"] == baseline_body["fact_cards"]
        assert body["missing_information"] == baseline_body["missing_information"]
        assert body["show_fallback"] == baseline_body["show_fallback"]
        assert body["fallback_message"] == baseline_body["fallback_message"]
        # Nothing extra -- even though the canned Answer carries a
        # citation, it must never surface for a non-answered status.
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []

    def test_never_500s_when_gemini_is_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderNotConfigured)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []
        assert any(c["field"] == "entry_requirements" for c in body["fact_cards"])


# ---------------------------------------------------------------------
# GET /ask/view (HTML page) -- same additive wiring, threaded into the
# template context. `app/web/templates/ask.html` is a forbidden file for
# this card and, as of this card, has no markup that reads either
# `ai_sentences` or `ai_citations` -- see `app/web/ask_pages.py`'s own
# module docstring. These tests prove the DATA reaches the template
# context correctly; they do not (and cannot, without touching the
# forbidden template) prove anything is visually rendered from it.
# ---------------------------------------------------------------------


class TestAskViewPageAiWiring:
    def test_never_calls_the_pipeline_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert _FALLBACK_COPY in response.text

    def test_answered_passes_ai_sentences_and_citations_into_template_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = AIAnswer(
            status=AIAnswerStatus.answered,
            sentences=["According to GSEB: entry requirements is Class 12 pass."],
            citations=[
                {
                    "record_id": "rec-1",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "GSEB",
                    "source_url": "https://gseb.example.invalid",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_pages_module, "_pipeline_answer", lambda *a, **k: canned)

        original_template_response = ask_pages_module.templates.TemplateResponse
        captured: dict[str, Any] = {}

        def _capture(
            request: Any, name: str, context: Any = None, *args: Any, **kwargs: Any
        ) -> Any:
            captured["context"] = context
            return original_template_response(request, name, context, *args, **kwargs)

        monkeypatch.setattr(ask_pages_module.templates, "TemplateResponse", _capture)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        context = captured["context"]
        assert context["ai_sentences"] == canned.sentences
        assert context["ai_citations"] == canned.citations
        # The deterministic fact card is still in context too -- never
        # replaced (AskFactCard is a dataclass, not a dict -- .field).
        assert any(card.field == "entry_requirements" for card in context["fact_cards"])

    def test_non_answered_status_passes_empty_ai_lists_into_template_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = AIAnswer(
            status=AIAnswerStatus.insufficient_information, citations=[{"record_id": "r"}]
        )
        monkeypatch.setattr(ask_pages_module, "_pipeline_answer", lambda *a, **k: canned)

        original_template_response = ask_pages_module.templates.TemplateResponse
        captured: dict[str, Any] = {}

        def _capture(
            request: Any, name: str, context: Any = None, *args: Any, **kwargs: Any
        ) -> Any:
            captured["context"] = context
            return original_template_response(request, name, context, *args, **kwargs)

        monkeypatch.setattr(ask_pages_module.templates, "TemplateResponse", _capture)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        context = captured["context"]
        assert context["ai_sentences"] == []
        assert context["ai_citations"] == []

    def test_never_500s_when_gemini_is_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ai_on_settings = _settings(ai_enabled=True, configured=True)
        monkeypatch.setattr(ask_module, "get_settings", lambda: ai_on_settings)
        monkeypatch.setattr(ask_pages_module, "get_settings", lambda: ai_on_settings)
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderNotConfigured)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert "Class 12 pass" in response.text
