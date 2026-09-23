"""Tests for UI-4: `app/planning/suggest.py`'s pure suggestion logic, and
its wiring into `/start/results` (`app/web/start_pages.py`).

Two layers, matching this task's own acceptance criteria:

  * `TestSuggestPathways*` -- the pure function directly, no HTTP
    involved: determinism, the budget/"affordable" answer never
    hard-filtering, the no-match-returns-broader-alternatives case, and
    "every suggestion has at least one reason".
  * `TestStartResultsLive` -- `/start/results` via `TestClient`, both
    branches live: real published tag data (simulated by monkeypatching
    `app.web.start_pages._candidates_for_suggestions`, the one seam that
    function documents -- there is no other way to reach that branch
    today, since no real tag data exists anywhere in this codebase yet,
    see that function's own docstring) and the honest no-data fallback,
    which is what this codebase's default actually does right now.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.planning.suggest import (
    MAX_SUGGESTIONS,
    QuickStartAnswers,
    SuggestionCandidate,
    suggest_pathways,
)

client = TestClient(app)


def _candidate(pathway_id: str, name: str, *tags: str) -> SuggestionCandidate:
    return SuggestionCandidate(pathway_id=pathway_id, name=name, tags=frozenset(tags))


NURSING = _candidate(
    "11111111-1111-1111-1111-111111111111",
    "Nursing (B.Sc)",
    "interest:healthcare",
    "decision:career",
)
SOFTWARE = _candidate(
    "22222222-2222-2222-2222-222222222222",
    "Software Engineering (B.Tech)",
    "interest:science_tech",
    "decision:career",
    "priority:start_work_sooner",
)
FINE_ARTS = _candidate(
    "33333333-3333-3333-3333-333333333333",
    "Fine Arts (BFA)",
    "interest:arts_design",
    "decision:stream",
)
ITI_ELECTRICIAN = _candidate(
    "44444444-4444-4444-4444-444444444444",
    "ITI Electrician",
    "interest:skilled_trades",
    "decision:career",
    "priority:affordable",
)


class TestSuggestPathwaysDeterminism:
    def test_same_inputs_always_produce_the_same_output(self) -> None:
        answers = QuickStartAnswers(
            stage="senior_secondary", goal="career", interest="science_tech", priority="affordable"
        )
        candidates = [NURSING, SOFTWARE, FINE_ARTS, ITI_ELECTRICIAN]
        first = suggest_pathways(answers, candidates)
        for _ in range(5):
            assert suggest_pathways(answers, candidates) == first

    def test_output_is_the_same_regardless_of_candidate_list_order(self) -> None:
        answers = QuickStartAnswers(goal="career", interest="science_tech")
        forward = suggest_pathways(answers, [NURSING, SOFTWARE, FINE_ARTS, ITI_ELECTRICIAN])
        reversed_order = suggest_pathways(
            answers, [ITI_ELECTRICIAN, FINE_ARTS, SOFTWARE, NURSING]
        )
        assert forward == reversed_order


class TestSuggestPathwaysMatching:
    def test_matches_on_interest_tag(self) -> None:
        result = suggest_pathways(
            QuickStartAnswers(interest="healthcare"), [NURSING, SOFTWARE, FINE_ARTS]
        )
        assert result.has_data is True
        assert result.is_broadened is False
        ids = [s.pathway_id for s in result.suggestions]
        assert NURSING.pathway_id in ids
        assert SOFTWARE.pathway_id not in ids
        assert FINE_ARTS.pathway_id not in ids

    def test_returns_at_most_three_suggestions(self) -> None:
        many = [
            _candidate(f"{i:08d}-0000-0000-0000-000000000000", f"Pathway {i}", "decision:career")
            for i in range(10)
        ]
        result = suggest_pathways(QuickStartAnswers(goal="career"), many)
        assert len(result.suggestions) == MAX_SUGGESTIONS

    def test_every_suggestion_has_at_least_one_reason(self) -> None:
        for answers in (
            QuickStartAnswers(interest="science_tech"),
            QuickStartAnswers(),  # nothing stated at all
            QuickStartAnswers(priority="affordable"),
        ):
            result = suggest_pathways(
                answers, [NURSING, SOFTWARE, FINE_ARTS, ITI_ELECTRICIAN]
            )
            assert result.suggestions, "expected at least a broadened suggestion"
            for suggestion in result.suggestions:
                assert len(suggestion.reasons) >= 1

    def test_no_reason_is_a_score_or_percentage(self) -> None:
        result = suggest_pathways(
            QuickStartAnswers(interest="science_tech", priority="affordable"),
            [NURSING, SOFTWARE, FINE_ARTS, ITI_ELECTRICIAN],
        )
        for suggestion in result.suggestions:
            for reason in suggestion.reasons:
                assert "%" not in reason
                for forbidden in ("score", "rank", "suited", "guarantee"):
                    assert forbidden not in reason.lower()


class TestSuggestPathwaysBudgetNeverFilters:
    """CLAUDE.md non-negotiable, and this card's own explicit rule:
    "Budget" may only affect ranking/reasons, never remove a pathway from
    consideration."""

    def test_a_pathway_with_no_affordable_tag_still_appears_when_it_matches_otherwise(
        self,
    ) -> None:
        # SOFTWARE matches on interest+goal but carries no
        # "priority:affordable" tag at all.
        result = suggest_pathways(
            QuickStartAnswers(goal="career", interest="science_tech", priority="affordable"),
            [SOFTWARE, FINE_ARTS],
        )
        ids = [s.pathway_id for s in result.suggestions]
        assert SOFTWARE.pathway_id in ids

    def test_priority_answer_does_not_change_which_candidates_are_eligible(self) -> None:
        # NURSING matches on goal alone and carries no "priority:*" tag
        # at all -- stating "affordable" must not remove it.
        candidates = [NURSING, FINE_ARTS]
        without_priority = suggest_pathways(QuickStartAnswers(goal="career"), candidates)
        with_affordable = suggest_pathways(
            QuickStartAnswers(goal="career", priority="affordable"), candidates
        )
        without_ids = {s.pathway_id for s in without_priority.suggestions}
        with_ids = {s.pathway_id for s in with_affordable.suggestions}
        assert without_ids == with_ids == {NURSING.pathway_id}


class TestSuggestPathwaysNoMatch:
    def test_no_match_returns_broader_alternatives_not_an_empty_list(self) -> None:
        result = suggest_pathways(
            QuickStartAnswers(interest="healthcare"), [SOFTWARE, FINE_ARTS]
        )
        assert result.has_data is True
        assert result.is_broadened is True
        assert len(result.suggestions) > 0
        for suggestion in result.suggestions:
            assert len(suggestion.reasons) >= 1
            assert "healthcare" in " ".join(suggestion.unknowns).lower() or suggestion.unknowns

    def test_nothing_stated_at_all_still_returns_candidates_when_available(self) -> None:
        result = suggest_pathways(QuickStartAnswers(), [NURSING, SOFTWARE])
        assert result.has_data is True
        assert result.is_broadened is True
        assert len(result.suggestions) == 2

    def test_no_candidates_at_all_is_the_honest_no_data_case(self) -> None:
        result = suggest_pathways(QuickStartAnswers(interest="healthcare"), [])
        assert result.has_data is False
        assert result.is_broadened is False
        assert result.suggestions == ()


class TestSuggestionUnknownChangeLabel:
    """ux-qa-reviewer finding on UI-4: the "why am I seeing this" link
    should name the ONE preference that is actually unknown/editable for
    a given suggestion, never the generic catch-all, when there is
    exactly one -- and must fall back to the generic (`None` here, which
    the template turns into "Change what matters most to you") whenever
    zero or more than one preference is unknown."""

    def test_exactly_one_unknown_preference_is_named(self) -> None:
        # NURSING matches goal + interest but carries no "priority:*" tag
        # at all -- exactly one preference (priority) is unknown.
        result = suggest_pathways(
            QuickStartAnswers(goal="career", interest="healthcare", priority="affordable"),
            [NURSING],
        )
        assert result.is_broadened is False
        suggestion = result.suggestions[0]
        assert suggestion.unknowns == ("Affordable",)
        assert suggestion.unknown_change_label == "your priority"

    def test_more_than_one_unknown_preference_falls_back_to_none(self) -> None:
        # NURSING only matches "goal" here -- interest and priority are
        # both unknown, so naming just one would be misleading.
        result = suggest_pathways(
            QuickStartAnswers(goal="career", interest="science_tech", priority="affordable"),
            [NURSING],
        )
        suggestion = result.suggestions[0]
        assert len(suggestion.unknowns) == 2
        assert suggestion.unknown_change_label is None

    def test_zero_unknown_preferences_falls_back_to_none(self) -> None:
        result = suggest_pathways(
            QuickStartAnswers(
                goal="career", interest="science_tech", priority="start_work_sooner"
            ),
            [SOFTWARE],
        )
        suggestion = result.suggestions[0]
        assert suggestion.unknowns == ()
        assert suggestion.unknown_change_label is None

    def test_broadened_suggestion_with_exactly_one_stated_preference_is_named(self) -> None:
        result = suggest_pathways(QuickStartAnswers(interest="healthcare"), [FINE_ARTS])
        assert result.is_broadened is True
        suggestion = result.suggestions[0]
        assert suggestion.unknown_change_label == "your interest"

    def test_goal_labels_are_capitalized_like_interest_and_priority_labels(self) -> None:
        # ux-qa-reviewer finding: a joined "What you told us" line must
        # not mix a lowercase goal fragment into otherwise capitalised
        # labels.
        result = suggest_pathways(
            QuickStartAnswers(goal="career", interest="science_tech", priority="affordable"),
            [SOFTWARE],
        )
        suggestion = result.suggestions[0]
        for label in suggestion.preferences:
            assert label[0].isupper()


class TestStartResultsLive:
    """`/start/results` via TestClient -- both real branches, live."""

    def test_default_degrades_honestly_with_no_published_tag_data(self) -> None:
        """Today's real default: `_candidates_for_suggestions()` returns
        an empty list (no tags column exists anywhere yet), so this is
        the branch a real deployment actually takes right now."""
        response = client.get(
            "/start/results",
            params={"stage": "senior_secondary", "interest": "science_tech"},
        )
        assert response.status_code == 200
        assert "Suggestions are not available yet" in response.text
        assert 'href="/explore"' in response.text
        assert "<script" not in response.text
        assert "Set-Cookie" not in response.headers

    def test_editing_answers_link_back_to_start_actually_works(self) -> None:
        response = client.get("/start/results")
        assert response.status_code == 200
        assert 'href="/start"' in response.text
        back = client.get("/start")
        assert back.status_code == 200
        assert "Question 1 of 4" in back.text

    def test_with_real_published_tag_data_it_shows_real_suggestions(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import app.web.start_pages as start_pages_module

        monkeypatch.setattr(
            start_pages_module,
            "_candidates_for_suggestions",
            lambda: [NURSING, SOFTWARE, FINE_ARTS, ITI_ELECTRICIAN],
        )
        response = client.get(
            "/start/results",
            params={
                "stage": "senior_secondary",
                "goal": "career",
                "interest": "healthcare",
                "priority": "affordable",
            },
        )
        assert response.status_code == 200
        assert "Nursing (B.Sc)" in response.text
        assert f'href="/pathways/{NURSING.pathway_id}/view"' in response.text
        assert "Why this pathway" in response.text
        assert "Matches your interest in Healthcare and life sciences." in response.text
        assert "Suggestions are not available yet" not in response.text
        assert "<script" not in response.text
        assert "Set-Cookie" not in response.headers

    def test_no_match_branch_is_reachable_live_and_degrades_to_broader_picks(
        self, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        import app.web.start_pages as start_pages_module

        monkeypatch.setattr(
            start_pages_module,
            "_candidates_for_suggestions",
            lambda: [FINE_ARTS],
        )
        response = client.get(
            "/start/results",
            params={"interest": "healthcare"},
        )
        assert response.status_code == 200
        assert "Fine Arts (BFA)" in response.text
        assert "None of the published pathways matched" in response.text
        assert "Suggestions are not available yet" not in response.text

    def test_single_unknown_preference_link_names_it(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """ux-qa-reviewer finding: with exactly one unknown preference
        (NURSING matches goal + interest but has no "priority:*" tag),
        the "change preferences" link names it rather than reading the
        generic catch-all."""
        import app.web.start_pages as start_pages_module

        monkeypatch.setattr(
            start_pages_module,
            "_candidates_for_suggestions",
            lambda: [NURSING],
        )
        response = client.get(
            "/start/results",
            params={"goal": "career", "interest": "healthcare", "priority": "affordable"},
        )
        assert response.status_code == 200
        assert "Change your priority" in response.text
        assert "Change what matters most to you" not in response.text

    def test_multiple_unknown_preferences_link_stays_generic(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """With two preferences unknown for the one matching candidate,
        naming just one would mislead -- the link keeps the generic
        wording."""
        import app.web.start_pages as start_pages_module

        monkeypatch.setattr(
            start_pages_module,
            "_candidates_for_suggestions",
            lambda: [NURSING],
        )
        response = client.get(
            "/start/results",
            params={"goal": "career", "interest": "science_tech", "priority": "affordable"},
        )
        assert response.status_code == 200
        assert "Change what matters most to you" in response.text
        assert "Change your priority" not in response.text
        assert "Change your interest" not in response.text

    def test_broadened_section_heading_reads_pathways_available(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """ux-qa-reviewer finding: `suggestions_broadened` was wired into
        the template context but never rendered -- the section heading
        must now say so, distinct from the tailored-match heading."""
        import app.web.start_pages as start_pages_module

        monkeypatch.setattr(
            start_pages_module,
            "_candidates_for_suggestions",
            lambda: [FINE_ARTS],
        )
        response = client.get("/start/results", params={"interest": "healthcare"})
        assert response.status_code == 200
        assert "Pathways available" in response.text
        assert "Suggested pathways" not in response.text

    def test_real_match_section_heading_stays_suggested_pathways(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The tailored-match heading is unchanged when suggestions are
        real tag matches, not a broadened sample."""
        import app.web.start_pages as start_pages_module

        monkeypatch.setattr(
            start_pages_module,
            "_candidates_for_suggestions",
            lambda: [NURSING, SOFTWARE, FINE_ARTS, ITI_ELECTRICIAN],
        )
        response = client.get(
            "/start/results",
            params={"goal": "career", "interest": "healthcare", "priority": "affordable"},
        )
        assert response.status_code == 200
        assert "Suggested pathways" in response.text
        assert "Pathways available" not in response.text
