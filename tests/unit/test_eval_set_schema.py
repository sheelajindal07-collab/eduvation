"""AI-9 (BCI-011): schema/shape test over evals/ask_bcion_questions.yaml.

This is a structural lint, not a call to any AI provider -- no network,
no `make test-db`, no e2e, nothing but reading two directories of YAML
fixtures under this repo. It exists so the eval set stays honest as
people add questions to it: the counts and fields the card required
(BCI-011's "What to build") are asserted here mechanically rather than
trusted to stay true by memory.

Everything this test reads (`evals/ask_bcion_questions.yaml`,
`tests/fixtures/ai_invalid/*.yaml`) is synthetic, per each file's own
header -- see evals/README.md.

## BANNED_PHRASES

Imported from `app/ai/schemas.py` (BCI-009/AI-1), the canonical
append-only list -- used only to calibrate
`tests/fixtures/ai_invalid/hedge_word.yaml`'s `hedge_phrase: probably`
against the real list, not a copy of it. AI-1 merged after this card was
first written; this file originally carried a smaller local fallback
copy, reconciled at merge time (2026-09-22, see docs/DECISIONS.md).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.ai.schemas import BANNED_PHRASES

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_YAML_PATH = REPO_ROOT / "evals" / "ask_bcion_questions.yaml"
AI_INVALID_DIR = REPO_ROOT / "tests" / "fixtures" / "ai_invalid"

REQUIRED_QUESTION_FIELDS = {
    "id",
    "category",
    "language",
    "text",
    "expected_status",
    "synthetic_record_ids",
}
ALLOWED_CATEGORIES = {
    "supported",
    "ambiguous",
    "unsupported",
    "stale",
    "injection",
    "source_mismatch",
    "api_failure",
}
CATEGORY_MIN_COUNT = 4
ALLOWED_LANGUAGES = {"en", "hi", "hi-Latn"}
HINDI_LANGUAGES = {"hi", "hi-Latn"}
HINDI_MIN_COUNT = 12
ALLOWED_STATUSES = {"answered", "not_available", "insufficient_information", "provider_error"}
ALLOWED_SCOPES = {"all_india", "abroad"}
SCOPE_MIN_COUNT = 2
TOTAL_MIN_COUNT = 36
SYNTHETIC_ID_RE = re.compile(r"^synthetic-[a-z0-9-]+$")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
PHONE_RES = [
    re.compile(r"(?<!\d)\d{10}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
    re.compile(r"\+91[-.\s]?\d{10}(?!\d)"),
    re.compile(r"(?<!\d)\d{5}[-.\s]\d{5}(?!\d)"),
]

REQUIRED_AI_INVALID_FIELDS = {
    "case_id",
    "reason_type",
    "question",
    "retrieved_record_ids",
    "answer",
    "why_wrong",
}
EXPECTED_AI_INVALID_REASONS = {
    "invented_number",
    "out_of_context_citation",
    "hedge_word",
    "guarantee_claim",
    "stale_without_flag",
}


def load_eval_set() -> dict[str, Any]:
    text = EVAL_YAML_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert isinstance(data, dict), f"{EVAL_YAML_PATH} did not parse to a mapping"
    return data


def find_pii(text: str) -> list[str]:
    """Return every PII-shaped substring (email or phone-number pattern)
    found in `text`. Empty list means clean."""
    hits = [m.group(0) for m in EMAIL_RE.finditer(text)]
    for pattern in PHONE_RES:
        hits.extend(m.group(0) for m in pattern.finditer(text))
    return hits


def load_ai_invalid_fixtures() -> list[dict[str, Any]]:
    paths = sorted(AI_INVALID_DIR.glob("*.yaml"))
    fixtures = []
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path} did not parse to a mapping"
        fixtures.append(data)
    return fixtures


# ---------------------------------------------------------------------
# evals/ask_bcion_questions.yaml
# ---------------------------------------------------------------------


def test_eval_set_file_exists() -> None:
    assert EVAL_YAML_PATH.is_file(), f"Missing {EVAL_YAML_PATH}"


def test_eval_set_has_synthetic_disclaimer() -> None:
    data = load_eval_set()
    disclaimer = data.get("disclaimer", "")
    assert isinstance(disclaimer, str) and disclaimer.strip(), (
        "evals/ask_bcion_questions.yaml must carry a plain-text disclaimer "
        "stating everything in it is synthetic and never verified data."
    )
    lowered = disclaimer.lower()
    assert "synthetic" in lowered
    assert "not" in lowered and "verif" in lowered


def test_eval_set_has_at_least_36_questions() -> None:
    data = load_eval_set()
    questions = data["questions"]
    assert isinstance(questions, list)
    assert len(questions) >= TOTAL_MIN_COUNT, (
        f"Expected at least {TOTAL_MIN_COUNT} questions, got {len(questions)}"
    )


def test_every_question_has_required_fields() -> None:
    data = load_eval_set()
    for q in data["questions"]:
        missing = REQUIRED_QUESTION_FIELDS - q.keys()
        assert not missing, f"{q.get('id', '<no id>')} missing fields: {missing}"
        assert isinstance(q["id"], str) and q["id"].strip()
        assert isinstance(q["text"], str) and q["text"].strip()
        assert isinstance(q["synthetic_record_ids"], list)


def test_question_ids_are_unique() -> None:
    data = load_eval_set()
    ids = [q["id"] for q in data["questions"]]
    duplicates = {qid for qid in ids if ids.count(qid) > 1}
    assert not duplicates, f"Duplicate question ids: {duplicates}"


def test_categories_are_from_the_allowed_set() -> None:
    data = load_eval_set()
    bad = {
        q["id"]: q["category"]
        for q in data["questions"]
        if q["category"] not in ALLOWED_CATEGORIES
    }
    assert not bad, f"Question(s) with an unrecognised category: {bad}"


def test_every_category_has_the_minimum_question_count() -> None:
    data = load_eval_set()
    counts: dict[str, int] = {cat: 0 for cat in ALLOWED_CATEGORIES}
    for q in data["questions"]:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    short = {cat: n for cat, n in counts.items() if n < CATEGORY_MIN_COUNT}
    assert not short, f"Categories below the minimum of {CATEGORY_MIN_COUNT}: {short}"


def test_languages_are_from_the_allowed_set() -> None:
    data = load_eval_set()
    bad = {
        q["id"]: q["language"]
        for q in data["questions"]
        if q["language"] not in ALLOWED_LANGUAGES
    }
    assert not bad, f"Question(s) with an unrecognised language: {bad}"


def test_at_least_twelve_hindi_or_hinglish_questions() -> None:
    data = load_eval_set()
    hindi_count = sum(1 for q in data["questions"] if q["language"] in HINDI_LANGUAGES)
    assert hindi_count >= HINDI_MIN_COUNT, (
        f"Expected at least {HINDI_MIN_COUNT} Hindi/Hinglish (hi or hi-Latn) "
        f"questions, got {hindi_count}"
    )


def test_expected_status_is_from_the_allowed_set() -> None:
    data = load_eval_set()
    bad = {
        q["id"]: q["expected_status"]
        for q in data["questions"]
        if q["expected_status"] not in ALLOWED_STATUSES
    }
    assert not bad, f"Question(s) with an unrecognised expected_status: {bad}"


def test_synthetic_record_ids_never_look_like_real_content() -> None:
    data = load_eval_set()
    for q in data["questions"]:
        for record_id in q["synthetic_record_ids"]:
            assert SYNTHETIC_ID_RE.match(record_id), (
                f"{q['id']}: synthetic_record_ids entry {record_id!r} does not "
                "look like a synthetic-*-NNN placeholder"
            )


def test_scope_values_are_from_the_allowed_set_when_present() -> None:
    data = load_eval_set()
    bad = {
        q["id"]: q["scope"]
        for q in data["questions"]
        if "scope" in q and q["scope"] not in ALLOWED_SCOPES
    }
    assert not bad, f"Question(s) with an unrecognised scope: {bad}"


def test_at_least_two_all_india_and_two_abroad_cases() -> None:
    data = load_eval_set()
    all_india = sum(1 for q in data["questions"] if q.get("scope") == "all_india")
    abroad = sum(1 for q in data["questions"] if q.get("scope") == "abroad")
    assert all_india >= SCOPE_MIN_COUNT, (
        f"Expected >= {SCOPE_MIN_COUNT} all_india cases, got {all_india}"
    )
    assert abroad >= SCOPE_MIN_COUNT, f"Expected >= {SCOPE_MIN_COUNT} abroad cases, got {abroad}"


def test_injection_questions_carry_an_injection_vector() -> None:
    data = load_eval_set()
    for q in data["questions"]:
        if q["category"] == "injection":
            assert q.get("injection_vector") in {"user_question", "record_text"}, (
                f"{q['id']}: injection question missing a valid injection_vector"
            )


def test_api_failure_questions_are_flagged_to_force_the_provider_to_error() -> None:
    data = load_eval_set()
    for q in data["questions"]:
        if q["category"] == "api_failure":
            assert q.get("force_provider_error") is True, (
                f"{q['id']}: api_failure question must set force_provider_error: true"
            )
            assert q["expected_status"] == "provider_error", (
                f"{q['id']}: api_failure question must expect provider_error"
            )


def test_no_question_text_contains_pii_shaped_strings() -> None:
    data = load_eval_set()
    violations: dict[str, list[str]] = {}
    for q in data["questions"]:
        hits = find_pii(q["text"])
        if hits:
            violations[q["id"]] = hits
    assert not violations, (
        "Question text containing a real-looking phone number or email "
        f"pattern (positive-control lint, not for real PII): {violations}"
    )


def test_pii_lint_detects_a_seeded_phone_number_and_email() -> None:
    """Positive control: proves find_pii() isn't vacuously passing."""
    seeded = "Call me on 9876543210 or email fake.person@example.com about this."
    hits = find_pii(seeded)
    assert hits, "Expected the seeded phone/email pattern to be detected but it was not"


# ---------------------------------------------------------------------
# tests/fixtures/ai_invalid/
# ---------------------------------------------------------------------


def test_ai_invalid_directory_exists_and_is_not_empty() -> None:
    assert AI_INVALID_DIR.is_dir(), f"Missing {AI_INVALID_DIR}"
    fixtures = load_ai_invalid_fixtures()
    assert fixtures, f"No fixture files found under {AI_INVALID_DIR}"


def test_ai_invalid_fixtures_cover_every_required_reason() -> None:
    fixtures = load_ai_invalid_fixtures()
    reasons = {f["reason_type"] for f in fixtures}
    missing = EXPECTED_AI_INVALID_REASONS - reasons
    assert not missing, f"tests/fixtures/ai_invalid/ is missing reason(s): {missing}"


def test_every_ai_invalid_fixture_has_required_fields() -> None:
    fixtures = load_ai_invalid_fixtures()
    for fixture in fixtures:
        missing = REQUIRED_AI_INVALID_FIELDS - fixture.keys()
        assert not missing, f"{fixture.get('case_id', '<no id>')} missing fields: {missing}"
        assert isinstance(fixture["answer"], str) and fixture["answer"].strip()
        assert isinstance(fixture["why_wrong"], str) and fixture["why_wrong"].strip()
        assert isinstance(fixture["retrieved_record_ids"], list)


def test_hedge_word_fixture_uses_a_real_banned_phrase() -> None:
    fixtures = load_ai_invalid_fixtures()
    hedge_fixtures = [f for f in fixtures if f["reason_type"] == "hedge_word"]
    assert hedge_fixtures, "No hedge_word fixture found"
    for fixture in hedge_fixtures:
        phrase = fixture.get("hedge_phrase", "")
        assert phrase, f"{fixture['case_id']}: hedge_word fixture missing hedge_phrase"
        assert phrase.lower() in {p.lower() for p in BANNED_PHRASES}, (
            f"{fixture['case_id']}: hedge_phrase {phrase!r} is not in BANNED_PHRASES"
        )
        assert phrase.lower() in fixture["answer"].lower(), (
            f"{fixture['case_id']}: hedge_phrase {phrase!r} does not actually "
            "appear in the fixture's answer text"
        )
