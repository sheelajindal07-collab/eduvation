"""Tests for the `/start` quick-start question chain (app/web/start_pages.py)
and the new `/` landing page (app/web/landing_pages.py), via TestClient.

Stateless -- no database involved for `/start` itself (every answer is a
query param, never a lookup); the landing page degrades to `db=None` in
this environment (no Supabase configured for tests/unit), which is
exactly its own "no careers published yet" branch, exercised below too.

UI-3 acceptance covered here: a guest can complete all four questions, or
skip every one of them, with zero JavaScript; the browser Back button's
own behaviour (re-fetching a previously visited URL) still shows that
URL's own previously-answered questions, because every answer lives in
the query string, never a cookie or client-side storage.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from app.web.pages import _db_client_or_none

client = TestClient(app)


def _assert_zero_js(response) -> None:  # type: ignore[no-untyped-def]
    assert "<script" not in response.text
    assert "Set-Cookie" not in response.headers


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def execute(self) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeDbClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._tables.get(name, []))


class TestLandingPage:
    def test_landing_page_renders_three_choices_with_no_account_wall(self) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "Find your next step" in response.text
        assert "I have a career in mind" in response.text
        assert "I'm not sure yet" in response.text
        assert "Just show me everything" in response.text
        assert 'href="/start"' in response.text
        assert 'href="/explore"' in response.text
        # No sign-up/sign-in prompt anywhere on this screen.
        assert "sign in" not in response.text.lower()
        assert "sign up" not in response.text.lower()
        _assert_zero_js(response)

    def test_landing_page_degrades_gracefully_with_no_careers_published(self) -> None:
        """No Supabase configured in this test environment, so `db` is
        always `None` here -- same degrade-to-empty-list path a real
        empty catalogue would take."""
        response = client.get("/")
        assert response.status_code == 200
        assert "No careers published yet" in response.text
        assert "Browse Explore instead" in response.text

    def test_i_have_a_career_in_mind_links_straight_to_its_explore_anchor(self) -> None:
        """The published-careers branch: each name becomes its own link
        to `/explore#career-{id}` -- the same anchor id UI-3 added to
        each career's `<section class="card">` in explore.html."""

        def _fake_db() -> Iterator[Client | None]:
            yield _FakeDbClient(  # type: ignore[arg-type]
                {"careers": [{"id": "11111111-1111-1111-1111-111111111111", "name": "Nursing"}]}
            )

        app.dependency_overrides[_db_client_or_none] = _fake_db
        try:
            response = client.get("/")
        finally:
            app.dependency_overrides.pop(_db_client_or_none, None)
        assert response.status_code == 200
        assert (
            'href="/explore#career-11111111-1111-1111-1111-111111111111"' in response.text
        )
        assert "Nursing" in response.text


class TestStartQuestionOne:
    def test_question_one_has_no_prior_answers_to_carry(self) -> None:
        response = client.get("/start")
        assert response.status_code == 200
        assert "Question 1 of 4" in response.text
        assert "What are you studying right now?" in response.text
        assert 'name="stage"' in response.text
        assert 'action="/start/decide"' in response.text
        assert 'href="/start/decide"' in response.text  # the skip link, no query yet
        _assert_zero_js(response)


class TestStartAnswerAllPath:
    """A guest answers every question, one page at a time, purely via
    GET links/forms -- verifying the actual rendered chain live, not
    just each route in isolation."""

    def test_full_chain_carries_every_answer_to_the_end(self) -> None:
        decide = client.get("/start/decide", params={"stage": "secondary"})
        assert decide.status_code == 200
        assert "Question 2 of 4" in decide.text
        assert 'value="secondary"' in decide.text  # carried forward as a hidden field
        assert 'action="/start/interest"' in decide.text

        interest = client.get(
            "/start/interest", params={"stage": "secondary", "goal": "career"}
        )
        assert interest.status_code == 200
        assert "Question 3 of 4" in interest.text
        assert 'value="secondary"' in interest.text
        assert 'value="career"' in interest.text
        assert 'action="/start/priority"' in interest.text

        priority = client.get(
            "/start/priority",
            params={"stage": "secondary", "goal": "career", "interest": "science_tech"},
        )
        assert priority.status_code == 200
        assert "Question 4 of 4" in priority.text
        assert 'value="science_tech"' in priority.text
        assert 'action="/start/results"' in priority.text

        results = client.get(
            "/start/results",
            params={
                "stage": "secondary",
                "goal": "career",
                "interest": "science_tech",
                "priority": "affordable",
            },
        )
        assert results.status_code == 200
        assert "Class 8-10" in results.text
        assert "Which career path to explore" in results.text
        assert "Science and technology" in results.text
        assert "Affordable" in results.text
        assert "Skipped" not in results.text
        for page in (decide, interest, priority, results):
            _assert_zero_js(page)


class TestStartSkipAllPath:
    """A guest skips every question via the "Skip this question" link,
    following each page's own `skip_url` exactly as rendered."""

    def test_skip_every_question_reaches_a_plain_summary(self) -> None:
        first = client.get("/start")
        assert 'href="/start/decide"' in first.text

        decide = client.get("/start/decide")  # followed the skip link: no query at all
        assert decide.status_code == 200
        assert 'href="/start/interest"' in decide.text
        assert "value=" not in decide.text.split("<fieldset")[0]  # no hidden fields yet

        interest = client.get("/start/interest")
        assert interest.status_code == 200
        assert 'href="/start/priority"' in interest.text

        priority = client.get("/start/priority")
        assert priority.status_code == 200
        assert 'href="/start/results"' in priority.text

        results = client.get("/start/results")
        assert results.status_code == 200
        assert "You skipped every question" in results.text
        assert results.text.count("Skipped") == 4
        for page in (first, decide, interest, priority, results):
            _assert_zero_js(page)


class TestStartPartialSkip:
    """Skipping ONE question must not lose the others -- each page's
    hidden fields carry forward only what was actually answered."""

    def test_skipping_the_second_question_still_carries_the_first(self) -> None:
        decide = client.get("/start/decide", params={"stage": "senior_secondary"})
        assert 'href="/start/interest?stage=senior_secondary"' in decide.text

        interest = client.get("/start/interest", params={"stage": "senior_secondary"})
        assert interest.status_code == 200
        assert 'value="senior_secondary"' in interest.text
        assert "goal" not in interest.text.split("<fieldset")[0].replace(
            'name="stage"', ""
        )

        results = client.get("/start/results", params={"stage": "senior_secondary"})
        assert "Class 11-12" in results.text
        assert results.text.count("Skipped") == 3


class TestStartRejectsUnknownValues:
    """A hand-edited/tampered query value outside a question's own fixed
    option list is dropped, never carried forward as free text -- these
    four answers are fixed, non-personal categories only."""

    def test_an_unrecognised_stage_value_is_not_carried_forward(self) -> None:
        response = client.get("/start/decide", params={"stage": "not-a-real-option"})
        assert response.status_code == 200
        assert "not-a-real-option" not in response.text
        assert 'href="/start/interest"' in response.text  # skip URL has no leftover query


class TestBackButtonPreservesAnswers:
    """The acceptance criterion this task names explicitly: browser Back
    must preserve previously-answered questions. Since every answer
    lives in the URL's own query string, "Back" is just the browser
    re-requesting a URL it already visited -- proven here by actually
    re-issuing that exact prior request and checking the answer is still
    there, not by asserting anything about a server-side session."""

    def test_revisiting_a_prior_question_url_still_shows_its_answer(self) -> None:
        # Forward: answer question 1, then question 2.
        first_visit = client.get("/start/decide", params={"stage": "secondary"})
        assert 'value="secondary"' in first_visit.text

        client.get("/start/interest", params={"stage": "secondary", "goal": "career"})

        # Back: re-fetch the exact URL the student was on before
        # answering question 2. It must still carry question 1's answer.
        back_visit = client.get("/start/decide", params={"stage": "secondary"})
        assert back_visit.status_code == 200
        assert 'value="secondary"' in back_visit.text
        assert back_visit.text == first_visit.text
