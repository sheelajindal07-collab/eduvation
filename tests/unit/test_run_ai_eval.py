"""Unit tests for `scripts/run_ai_eval.py` (AI-11, BCI-019).

Every test here uses `--provider mock` (or calls `run_eval`/`main` with
`provider_name="mock"` directly) — zero network, zero real provider call,
matching this card's own Tests section. The only "database" touched is
`FakeDb` below (in-memory Python dicts, no I/O of any kind); the only
provider touched is `app.ai.mock_provider.MockAIProvider`.
`app.ai.gemini_provider.GeminiProvider` is never constructed anywhere in
this file.

Fixture data is imported directly from `scripts.seed_ai_eval_fixtures`
(its own `CLAIMS`/`SOURCES` module-level lists) rather than duplicated
here, so these tests exercise the exact same rows — same ids, same
values, same staleness — a real local-stack run seeded by that script
would use, and never drift out of sync with it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.ai.schemas import AIAnswerStatus, AskRequest
from app.core.config import get_settings
from scripts.run_ai_eval import (
    DEFAULT_MAX_CALLS,
    EVAL_YAML_PATH,
    QUESTION_TEMPLATE_MAP,
    _cooperative_mock_responses,
    _lang_for_ask_request,
    _percentile,
    _status_matches_expected,
    architecture_note_for,
    build_ask_request,
    load_eval_questions,
    main,
    run_eval,
    synthetic_placeholder_to_uuid,
)
from scripts.seed_ai_eval_fixtures import CLAIMS, SOURCES
from scripts.seed_ai_eval_fixtures import TODAY as SEED_TODAY

# The same "as_of" reference scripts/seed_ai_eval_fixtures.py computed its
# own FRESH_VERIFICATION_DATE/STALE_VERIFICATION_DATE from (both are
# date.today() at import time) -- reusing it, rather than a hardcoded
# literal, keeps these tests correct regardless of what day they run on.
TODAY = SEED_TODAY


# ---------------------------------------------------------------------
# A minimal, correctly-filtering fake Supabase client
# ---------------------------------------------------------------------


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    """Enough of Supabase's fluent `.select().eq().eq().in_().execute()`
    interface for `app.ai.retrieval` -- unlike the simpler fakes elsewhere
    in this repo (`tests/unit/test_web_ask.py`'s `_FakeQuery`, which
    ignores every filter because each fixture already holds exactly the
    rows one test wants), this one actually filters, because these tests
    need `fetch_pathway_records`/`fetch_claim_record` to return DIFFERENT
    results for different ids from the SAME shared fixture table."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._predicates: list[Any] = []

    def select(self, *_args: Any, **_kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._predicates.append(lambda row, c=column, v=value: row.get(c) == v)
        return self

    def in_(self, column: str, values: Any) -> _FakeQuery:
        value_set = set(values)
        self._predicates.append(lambda row, c=column, v=value_set: row.get(c) in v)
        return self

    def execute(self) -> _FakeResult:
        rows = [row for row in self._rows if all(pred(row) for pred in self._predicates)]
        return _FakeResult(rows)


class FakeDb:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(list(self._tables.get(name, [])))


def _fake_db() -> FakeDb:
    """A fake db pre-loaded with the real AI-11 eval fixture rows
    (`scripts.seed_ai_eval_fixtures`'s own `CLAIMS`/`SOURCES`) -- the
    exact same rows, same ids, a real local-stack run would have."""
    return FakeDb({"claims": CLAIMS, "sources": SOURCES})


def _find_question(qid: str) -> dict[str, Any]:
    questions = load_eval_questions(EVAL_YAML_PATH)
    match = next(q for q in questions if q["id"] == qid)
    return match


# ---------------------------------------------------------------------
# Settings: AI_ENABLED / GEMINI_API_KEY plumbing, isolated per test
# ---------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Any:
    """`get_settings()` is `lru_cache`d process-wide -- clear it around
    every test so one test's `monkeypatch.setenv` can never leak into the
    next (same convention `tests/unit/test_web_ask.py` already uses)."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def ai_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """`app.ai.pipeline.answer()`'s own step 2 requires both
    `Settings.ai_enabled` and `Settings.ai_configured` (a non-empty
    `gemini_api_key`) before it will run retrieval at all. Never a real
    key -- see `scripts/run_ai_eval.py`'s own
    `_MOCK_PLACEHOLDER_GEMINI_KEY` docstring note; `--provider mock`
    never constructs a `GeminiProvider`, so this value is never used for
    a network call."""
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-fixture-placeholder-not-a-real-key")


# ---------------------------------------------------------------------
# synthetic_placeholder_to_uuid
# ---------------------------------------------------------------------


class TestSyntheticPlaceholderToUuid:
    def test_deterministic(self) -> None:
        first = synthetic_placeholder_to_uuid("synthetic-pathway-001")
        second = synthetic_placeholder_to_uuid("synthetic-pathway-001")
        assert first == second

    def test_distinct_placeholders_resolve_to_distinct_ids(self) -> None:
        first = synthetic_placeholder_to_uuid("synthetic-pathway-001")
        second = synthetic_placeholder_to_uuid("synthetic-pathway-002")
        assert first != second

    def test_resolves_to_a_uuid_shaped_string(self) -> None:
        import uuid

        resolved = synthetic_placeholder_to_uuid("synthetic-claim-030")
        # Round-trips through uuid.UUID -- proves it is a real UUID string,
        # not merely something that happens to look like one.
        assert str(uuid.UUID(resolved)) == resolved

    def test_matches_what_the_seed_fixture_script_actually_used(self) -> None:
        """The single most important property this function has: the id
        this runner resolves for a placeholder must be the SAME id
        `scripts/seed_ai_eval_fixtures.py` used when seeding that row."""
        expected_pathway_id = synthetic_placeholder_to_uuid("synthetic-pathway-002")
        matching_claims = [c for c in CLAIMS if c["entity_id"] == expected_pathway_id]
        assert matching_claims, "no seeded claim references the resolved pathway-002 id"


# ---------------------------------------------------------------------
# QUESTION_TEMPLATE_MAP / load_eval_questions
# ---------------------------------------------------------------------


class TestQuestionTemplateMap:
    def test_covers_every_question_in_the_real_merged_eval_file(self) -> None:
        # load_eval_questions itself raises AssertionError on any gap --
        # this test's whole point is to prove that never happens against
        # the actual, merged evals/ask_bcion_questions.yaml.
        questions = load_eval_questions(EVAL_YAML_PATH)
        assert len(questions) >= 36
        assert {q["id"] for q in questions} <= set(QUESTION_TEMPLATE_MAP)

    def test_raises_when_a_question_id_has_no_mapping(self, tmp_path: Any) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "disclaimer: test\nschema_version: 1\nquestions:\n"
            "  - id: totally-unmapped-question\n"
            "    category: supported\n"
            "    language: en\n"
            "    text: unused\n"
            "    expected_status: answered\n"
            "    synthetic_record_ids: []\n",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError, match="totally-unmapped-question"):
            load_eval_questions(bad_yaml)


# ---------------------------------------------------------------------
# _lang_for_ask_request
# ---------------------------------------------------------------------


class TestLangForAskRequest:
    @pytest.mark.parametrize(
        ("language", "expected"), [("en", "en"), ("hi", "hi"), ("hi-Latn", "hi")]
    )
    def test_maps_correctly(self, language: str, expected: str) -> None:
        assert _lang_for_ask_request(language) == expected


# ---------------------------------------------------------------------
# build_ask_request
# ---------------------------------------------------------------------


class TestBuildAskRequest:
    def test_ask_request_has_no_free_text_field_at_all(self) -> None:
        """Structural proof of the module docstring's central claim: the
        question's own text can never reach AskRequest, because
        AskRequest itself has no field for it."""
        question = _find_question("supported-01")
        request, _template, _placeholder, _resolved = build_ask_request(question)
        assert set(type(request).model_fields) == {
            "template_id",
            "pathway_id",
            "career_id",
            "claim_id",
            "plan_id",
            "lang",
        }

    def test_resolves_a_pathway_id_for_a_pathway_shaped_template(self) -> None:
        request, template, placeholder, resolved = build_ask_request(_find_question("supported-01"))
        assert template.id == "cost_breakdown"
        assert placeholder == "synthetic-pathway-001"
        assert resolved == synthetic_placeholder_to_uuid("synthetic-pathway-001")
        assert request.pathway_id == resolved
        assert request.claim_id is None

    def test_resolves_a_claim_id_for_a_claim_shaped_template(self) -> None:
        request, template, placeholder, resolved = build_ask_request(_find_question("supported-02"))
        assert template.id == "eligibility_gap"
        assert placeholder == "synthetic-claim-002"
        assert resolved == synthetic_placeholder_to_uuid("synthetic-claim-002")
        assert request.claim_id == resolved
        assert request.pathway_id is None

    def test_none_when_no_matching_shaped_placeholder_exists(self) -> None:
        question = _find_question("unsupported-01")
        request, template, placeholder, resolved = build_ask_request(question)
        assert template.id == "cost_breakdown"
        assert placeholder is None
        assert resolved is None
        assert request.pathway_id is None
        # record_id_for is what app.ai.pipeline.answer()'s step 1 actually
        # checks -- proving this is None is the real, load-bearing claim.
        assert request.record_id_for(template) is None

    def test_none_when_only_the_wrong_shaped_placeholder_exists(self) -> None:
        """ambiguous-03: synthetic_record_ids carries two PATHWAY ids and
        no CLAIM id, but the mapped template (eligibility_gap) needs a
        claim id -- must resolve to None, not silently fall back to a
        pathway id."""
        request, template, placeholder, resolved = build_ask_request(_find_question("ambiguous-03"))
        assert template.id == "eligibility_gap"
        assert placeholder is None
        assert resolved is None
        assert request.claim_id is None


# ---------------------------------------------------------------------
# architecture_note_for
# ---------------------------------------------------------------------


class TestArchitectureNoteFor:
    def test_none_for_an_ordinary_fully_resolved_question(self) -> None:
        question = _find_question("supported-01")
        note = architecture_note_for(question, resolved_id="some-resolved-id")
        assert note is None

    def test_flags_a_missing_id(self) -> None:
        question = _find_question("unsupported-01")
        note = architecture_note_for(question, resolved_id=None)
        assert note is not None
        assert "unsupported_template" in note

    def test_flags_ambiguous_category(self) -> None:
        question = _find_question("ambiguous-01")
        note = architecture_note_for(question, resolved_id="resolved")
        assert note is not None
        assert "ambiguous" in note.lower() or "name" in note.lower()

    def test_flags_source_mismatch_category(self) -> None:
        question = _find_question("source-mismatch-01")
        note = architecture_note_for(question, resolved_id="resolved")
        assert note is not None
        assert "claim_id" in note

    def test_flags_injection_user_question_vector(self) -> None:
        question = _find_question("injection-01")
        assert question["injection_vector"] == "user_question"
        note = architecture_note_for(question, resolved_id="resolved")
        assert note is not None
        assert "moot" in note

    def test_does_not_flag_injection_record_text_vector(self) -> None:
        question = _find_question("injection-02")
        assert question["injection_vector"] == "record_text"
        note = architecture_note_for(question, resolved_id="resolved")
        assert note is None


# ---------------------------------------------------------------------
# _status_matches_expected
# ---------------------------------------------------------------------


class TestStatusMatchesExpected:
    def test_answered_matches_answered(self) -> None:
        assert _status_matches_expected(AIAnswerStatus.answered, "answered") is True

    def test_not_available_matches_not_available(self) -> None:
        assert _status_matches_expected(AIAnswerStatus.not_available, "not_available") is True

    def test_provider_error_maps_to_ai_unavailable(self) -> None:
        assert _status_matches_expected(AIAnswerStatus.ai_unavailable, "provider_error") is True

    def test_ai_unavailable_does_not_match_anything_else(self) -> None:
        assert _status_matches_expected(AIAnswerStatus.ai_unavailable, "answered") is False

    def test_unsupported_template_never_matches_any_eval_status(self) -> None:
        for expected in ("answered", "not_available", "insufficient_information", "provider_error"):
            assert _status_matches_expected(AIAnswerStatus.unsupported_template, expected) is False

    def test_budget_exhausted_never_matches_any_eval_status(self) -> None:
        for expected in ("answered", "not_available", "insufficient_information", "provider_error"):
            assert _status_matches_expected(AIAnswerStatus.budget_exhausted, expected) is False


# ---------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------


class TestPercentile:
    def test_single_value(self) -> None:
        assert _percentile([5.0], 95) == 5.0

    def test_p50_of_sorted_values(self) -> None:
        result = _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50)
        assert result == 3.0

    def test_raises_on_empty(self) -> None:
        with pytest.raises(ValueError):
            _percentile([], 95)


# ---------------------------------------------------------------------
# _cooperative_mock_responses
# ---------------------------------------------------------------------


class TestCooperativeMockResponses:
    def test_empty_when_request_id_is_none(self) -> None:
        request = AskRequest(template_id="cost_breakdown", pathway_id=None)
        from app.ai.prompts import TEMPLATE_REGISTRY

        template = TEMPLATE_REGISTRY["cost_breakdown"]
        assert _cooperative_mock_responses(_fake_db(), request, template, as_of=TODAY) == []

    def test_scripts_a_selection_and_verification_pair_for_a_real_pathway(self) -> None:
        from app.ai.prompts import TEMPLATE_REGISTRY
        from app.ai.retrieval import fetch_pathway_records

        template = TEMPLATE_REGISTRY["cost_breakdown"]
        pathway_id = synthetic_placeholder_to_uuid("synthetic-pathway-001")
        request = AskRequest(template_id="cost_breakdown", pathway_id=pathway_id)
        responses = _cooperative_mock_responses(_fake_db(), request, template, as_of=TODAY)
        assert len(responses) == 2
        selection, verification = responses
        expected_ids = {r.id for r in fetch_pathway_records(_fake_db(), pathway_id, as_of=TODAY)}
        assert expected_ids  # sanity: the fixture actually has records
        for record_id in expected_ids:
            assert f"[{record_id}]" in selection
            assert f"YES {record_id}" in verification

    def test_empty_when_nothing_is_retrieved_for_an_unknown_pathway(self) -> None:
        from app.ai.prompts import TEMPLATE_REGISTRY

        template = TEMPLATE_REGISTRY["cost_breakdown"]
        unknown_pathway_id = "00000000-0000-0000-0000-000000000000"
        request = AskRequest(template_id="cost_breakdown", pathway_id=unknown_pathway_id)
        assert _cooperative_mock_responses(_fake_db(), request, template, as_of=TODAY) == []


# ---------------------------------------------------------------------
# run_eval -- end-to-end, against the FakeDb + real seed fixture data
# ---------------------------------------------------------------------


class TestRunEvalAgainstSeededFixtures:
    def test_answered_path_for_a_fresh_published_pathway(self, ai_enabled: None) -> None:
        question = _find_question("supported-01")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        assert result["not_reached"] == []
        entry = result["questions"][0]
        assert entry["actual_status"] == "answered"
        assert entry["matched_expected_status"] is True
        assert entry["selection_ids"]
        assert entry["verification_ids"]
        assert entry["calls_used"] == 2
        assert entry["architecture_note"] is None

    def test_stale_claim_downgrades_to_insufficient_information(self, ai_enabled: None) -> None:
        question = _find_question("stale-01")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        entry = result["questions"][0]
        assert entry["actual_status"] == "insufficient_information"
        assert entry["matched_expected_status"] is True
        assert entry["calls_used"] == 2

    def test_api_failure_forces_ai_unavailable_via_scripted_raise(self, ai_enabled: None) -> None:
        question = _find_question("api-failure-01")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        entry = result["questions"][0]
        assert entry["actual_status"] == "ai_unavailable"
        assert entry["expected_status"] == "provider_error"
        assert entry["matched_expected_status"] is True
        assert "raise_on_call" in entry["provider_used"]
        # Step 4 (budget reservation) still happens before the scripted
        # generate() call raises -- a reservation that led to a failed
        # call is still correctly counted as a call attempted.
        assert entry["calls_used"] == 2

    def test_unsupported_template_when_no_id_is_supplied(self, ai_enabled: None) -> None:
        question = _find_question("unsupported-01")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        entry = result["questions"][0]
        assert entry["actual_status"] == "unsupported_template"
        assert entry["matched_expected_status"] is False
        assert entry["calls_used"] == 0  # step 1 short-circuits before any reservation
        assert entry["architecture_note"] is not None

    def test_no_exception_ever_escapes_a_single_bad_question(self, ai_enabled: None) -> None:
        """Robustness: even if app.ai.pipeline.answer() somehow raised for
        one question, this runner must record it and keep going, never
        crash the batch. Simulated here with a template_id-valid but
        nonsense pathway_id (a real UUID string that resolves to nothing)
        -- exercised via the normal path, since that alone must not
        raise; this test's assertion is simply that run_eval() returns
        cleanly with a real Answer, proving the try/except wrapper is
        inert on the happy/degenerate paths and does not swallow a normal
        result."""
        question = _find_question("unsupported-06")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        entry = result["questions"][0]
        assert entry["error"] is None
        assert entry["actual_status"] is not None


class TestRunEvalHardCallCeiling:
    def test_aborts_the_whole_run_not_just_one_question(self, ai_enabled: None) -> None:
        questions = [
            _find_question("supported-01"),
            _find_question("supported-02"),
            _find_question("supported-03"),
        ]
        # max_calls=2: the first question (2 calls reserved) exactly
        # exhausts it; the next question's worst case (2 more) would
        # exceed it, so the runner must stop BEFORE attempting it.
        result = run_eval(_fake_db(), questions, provider_name="mock", max_calls=2, as_of=TODAY)
        assert len(result["questions"]) == 1
        assert result["questions"][0]["id"] == "supported-01"
        assert result["not_reached"] == ["supported-02", "supported-03"]
        assert result["summary"]["cap_hit"] is True
        assert result["summary"]["reached"] == 1
        assert result["summary"]["not_reached_count"] == 2

    def test_does_not_abort_when_the_cap_is_never_threatened(self, ai_enabled: None) -> None:
        questions = [_find_question("supported-01"), _find_question("supported-02")]
        result = run_eval(
            _fake_db(), questions, provider_name="mock", max_calls=DEFAULT_MAX_CALLS, as_of=TODAY
        )
        assert result["not_reached"] == []
        assert result["summary"]["cap_hit"] is False
        assert result["summary"]["reached"] == 2

    def test_a_question_that_reserves_zero_calls_never_shrinks_remaining_budget(
        self, ai_enabled: None
    ) -> None:
        """unsupported-01 short-circuits at step 1 with zero reservations
        -- running it must never itself trip the cap for a question that
        follows."""
        questions = [_find_question("unsupported-01"), _find_question("supported-01")]
        result = run_eval(_fake_db(), questions, provider_name="mock", max_calls=2, as_of=TODAY)
        assert result["not_reached"] == []
        assert [q["id"] for q in result["questions"]] == ["unsupported-01", "supported-01"]


class TestRunEvalReportShape:
    def test_full_report_is_json_serialisable(self, ai_enabled: None) -> None:
        questions = load_eval_questions(EVAL_YAML_PATH)
        result = run_eval(_fake_db(), questions, provider_name="mock", max_calls=80, as_of=TODAY)
        serialised = json.dumps(result)
        assert isinstance(serialised, str)
        summary = result["summary"]
        assert summary["total_questions"] == len(questions)
        assert summary["reached"] + summary["not_reached_count"] == len(questions)
        matched_plus_mismatched = (
            summary["matched_expected_status_count"] + summary["mismatched_expected_status_count"]
        )
        assert matched_plus_mismatched == summary["reached"]
        assert summary["p95_latency_ms"] is not None
        assert summary["mean_latency_ms"] is not None

    def test_every_question_entry_carries_required_fields(self, ai_enabled: None) -> None:
        question = _find_question("supported-01")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        entry = result["questions"][0]
        required_fields = {
            "id",
            "category",
            "mapped_template_id",
            "mapped_resolved_id",
            "actual_status",
            "matched_expected_status",
            "selection_ids",
            "verification_ids",
            "latency_ms",
            "calls_used",
        }
        assert required_fields <= entry.keys()

    def test_question_text_appears_only_in_its_own_label_field(self, ai_enabled: None) -> None:
        """The report may carry the question's text as a human-readable
        label (module docstring) -- but nothing else about the run
        (selection_ids, verification_ids, mapped ids) may be derived from
        it. This asserts the text is exactly and only where expected."""
        question = _find_question("supported-01")
        result = run_eval(_fake_db(), [question], provider_name="mock", max_calls=10, as_of=TODAY)
        entry = result["questions"][0]
        assert entry["text"] == question["text"]
        # selection/verification ids are real record ids (UUIDs), never
        # anything resembling the free-text question.
        for record_id in entry["selection_ids"] + entry["verification_ids"]:
            assert record_id != question["text"]


class TestRunEvalRequiresGeminiProviderWhenNamed:
    def test_raises_if_provider_name_is_gemini_without_a_constructed_provider(
        self, ai_enabled: None
    ) -> None:
        question = _find_question("supported-01")
        with pytest.raises(ValueError, match="gemini_provider"):
            run_eval(_fake_db(), [question], provider_name="gemini", max_calls=10, as_of=TODAY)


# ---------------------------------------------------------------------
# main() -- CLI wiring, guard behaviour, and one full mock run to disk
# ---------------------------------------------------------------------


class TestMainGuards:
    def test_refuses_when_service_role_key_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        exit_code = main(["--provider", "mock"])
        assert exit_code == 1
        assert "SUPABASE_SERVICE_ROLE_KEY" in capsys.readouterr().err

    def test_refuses_a_non_local_unallowlisted_target(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("SUPABASE_URL", "https://some-random-ref.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "irrelevant")
        monkeypatch.delenv("BCION_SEED_TARGET", raising=False)
        monkeypatch.delenv("BCION_PRODUCTION_PROJECT_REF", raising=False)
        exit_code = main(["--provider", "mock"])
        assert exit_code == 1
        assert "REFUSING TO SEED" in capsys.readouterr().err

    def test_refuses_when_app_env_is_production(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "irrelevant")
        exit_code = main(["--provider", "mock"])
        assert exit_code == 1
        assert "production" in capsys.readouterr().err.lower()


class TestMainFullRun:
    def test_writes_a_valid_report_with_provider_mock(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        small_yaml = tmp_path / "small.yaml"
        small_yaml.write_text(
            "disclaimer: SYNTHETIC EVALUATION DATA -- NOT VERIFIED, NOT REAL.\n"
            "schema_version: 1\n"
            "questions:\n"
            "  - id: supported-01\n"
            "    category: supported\n"
            "    language: en\n"
            "    text: unused label only\n"
            "    expected_status: answered\n"
            "    synthetic_record_ids: [synthetic-pathway-001, synthetic-claim-001]\n"
            "  - id: api-failure-01\n"
            "    category: api_failure\n"
            "    language: en\n"
            "    force_provider_error: true\n"
            "    text: unused label only\n"
            "    expected_status: provider_error\n"
            "    synthetic_record_ids: [synthetic-pathway-001, synthetic-claim-001]\n",
            encoding="utf-8",
        )
        out_path = tmp_path / "report.json"

        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key-not-real")

        fake_db = _fake_db()
        monkeypatch.setattr("supabase.create_client", lambda url, key: fake_db)

        exit_code = main(
            [
                "--provider",
                "mock",
                "--max-calls",
                "10",
                "--eval-set",
                str(small_yaml),
                "--out",
                str(out_path),
                "--as-of",
                TODAY.isoformat(),
            ]
        )

        assert exit_code == 0
        assert out_path.is_file()
        report = json.loads(out_path.read_text(encoding="utf-8"))
        assert report["provider"] == "mock"
        assert len(report["questions"]) == 2
        statuses = {q["id"]: q["actual_status"] for q in report["questions"]}
        assert statuses["supported-01"] == "answered"
        assert statuses["api-failure-01"] == "ai_unavailable"

    def test_provider_gemini_without_a_configured_key_fails_clearly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key-not-real")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("AI_ENABLED", raising=False)

        fake_db = _fake_db()
        monkeypatch.setattr("supabase.create_client", lambda url, key: fake_db)

        exit_code = main(["--provider", "gemini"])
        assert exit_code == 1
        assert "GEMINI_API_KEY" in capsys.readouterr().err
