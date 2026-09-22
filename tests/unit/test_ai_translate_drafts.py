"""Tests for scripts/ai_translate_drafts.py (AI-20).

`--provider mock` (`MockAIProvider`) only, throughout this file -- zero
network calls, zero real provider calls. No `make test-db`, no e2e: this
is a pure-Python/filesystem unit-test file.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from app.ai.gemini_provider import GeminiNotConfiguredError
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings
from scripts.ai_translate_drafts import (
    AGREEMENT_FLAG_OK,
    AGREEMENT_FLAG_REVIEW,
    CSV_FIELDNAMES,
    DEFAULT_EN_PATH,
    DEFAULT_HI_PATH,
    DraftRow,
    _build_provider,
    agreement_flag,
    agreement_score,
    draft_translation,
    load_catalogue,
    main,
    missing_keys,
    run,
    write_csv,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: dict[str, str]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------
# missing_keys
# ---------------------------------------------------------------------


def test_missing_keys_returns_only_keys_absent_from_hi_in_en_order() -> None:
    en = {"a.one": "One", "a.two": "Two", "a.three": "Three"}
    hi = {"a.two": "दो"}
    assert missing_keys(en, hi) == ["a.one", "a.three"]


def test_missing_keys_empty_when_hi_already_has_everything() -> None:
    en = {"a.one": "One", "a.two": "Two"}
    hi = {"a.one": "एक", "a.two": "दो", "a.extra": "अतिरिक्त"}
    assert missing_keys(en, hi) == []


def test_missing_keys_is_pure_key_presence_not_value_comparison() -> None:
    """A key present in both files is never "missing", even if its hi
    value looks like a placeholder/stale draft -- this script only ever
    fills in genuinely absent keys, per the card."""
    en = {"a.one": "One"}
    hi = {"a.one": "SOMETHING ELSE ENTIRELY"}
    assert missing_keys(en, hi) == []


# ---------------------------------------------------------------------
# load_catalogue
# ---------------------------------------------------------------------


def test_load_catalogue_reads_a_flat_string_object(tmp_path: Path) -> None:
    path = tmp_path / "en.json"
    _write_json(path, {"x.y": "Hello"})
    assert load_catalogue(path) == {"x.y": "Hello"}


def test_load_catalogue_rejects_a_non_string_value(tmp_path: Path) -> None:
    path = tmp_path / "en.json"
    path.write_text(json.dumps({"x.y": 5}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-string value"):
        load_catalogue(path)


def test_load_catalogue_rejects_a_non_object_top_level(tmp_path: Path) -> None:
    path = tmp_path / "en.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_catalogue(path)


# ---------------------------------------------------------------------
# agreement_score / agreement_flag -- the heuristic itself
# ---------------------------------------------------------------------


def test_agreement_score_is_one_for_identical_text() -> None:
    assert agreement_score("What will this cost?", "What will this cost?") == 1.0


def test_agreement_score_is_one_for_both_empty() -> None:
    assert agreement_score("", "") == 1.0


def test_agreement_score_is_zero_when_no_tokens_are_shared() -> None:
    assert agreement_score("apple banana cherry", "xyzzy plugh quux") == 0.0


def test_agreement_score_is_case_insensitive() -> None:
    assert agreement_score("Ask BCION about this", "ASK bcion ABOUT this") == 1.0


def test_agreement_score_partial_overlap_is_between_zero_and_one() -> None:
    score = agreement_score("What will this cost?", "What is this?")
    assert 0.0 < score < 1.0


def test_agreement_flag_ok_at_and_above_threshold() -> None:
    assert agreement_flag(0.5, threshold=0.5) == AGREEMENT_FLAG_OK
    assert agreement_flag(1.0, threshold=0.5) == AGREEMENT_FLAG_OK


def test_agreement_flag_needs_review_below_threshold() -> None:
    assert agreement_flag(0.49, threshold=0.5) == AGREEMENT_FLAG_REVIEW
    assert agreement_flag(0.0, threshold=0.5) == AGREEMENT_FLAG_REVIEW


# ---------------------------------------------------------------------
# draft_translation -- exactly two separate provider.generate() calls,
# the second is a genuinely separate call, never a re-run of the first.
# ---------------------------------------------------------------------


def test_draft_translation_makes_exactly_two_calls_translation_then_back_translation() -> None:
    provider = MockAIProvider(responses=["यह क्या है?", "What is this? (back)"])

    row = draft_translation("ask.entry.default_label", "What is this?", provider)

    assert len(provider.calls) == 2
    # Call 1: the translation pass prompt carries the original English text.
    assert "What is this?" in provider.calls[0]
    # Call 2: the back-translation pass prompt carries the FIRST call's
    # output (the Hindi draft), not the original English again -- proving
    # it is a genuinely separate, second call and not a re-run of the first.
    assert "यह क्या है?" in provider.calls[1]
    assert "What is this?" not in provider.calls[1]

    assert row.key == "ask.entry.default_label"
    assert row.english == "What is this?"
    assert row.hindi_draft == "यह क्या है?"
    assert row.back_translation == "What is this? (back)"


def test_draft_translation_computes_agreement_from_english_and_back_translation() -> None:
    provider = MockAIProvider(responses=["ठीक अनुवाद", "What will this cost?"])
    row = draft_translation("ask.prompt.cost_breakdown", "What will this cost?", provider)
    assert row.agreement_score == agreement_score("What will this cost?", "What will this cost?")
    assert row.agreement_flag == AGREEMENT_FLAG_OK


def test_draft_translation_flags_a_disagreeing_back_translation_never_drops_it() -> None:
    """A low agreement score is a flag, not a rejection -- the row still
    comes out, with both translations still present (module docstring:
    "never silently dropped or silently accepted")."""
    provider = MockAIProvider(responses=["कुछ अनुवाद", "Completely unrelated sentence"])
    row = draft_translation("ask.prompt.cost_breakdown", "What will this cost?", provider)
    assert row.agreement_flag == AGREEMENT_FLAG_REVIEW
    assert row.hindi_draft == "कुछ अनुवाद"
    assert row.back_translation == "Completely unrelated sentence"


# ---------------------------------------------------------------------
# write_csv -- real shape, real column order
# ---------------------------------------------------------------------


def test_write_csv_produces_the_exact_column_order_and_values(tmp_path: Path) -> None:
    rows = [
        DraftRow(
            key="ask.entry.default_label",
            english="Ask BCION about this",
            hindi_draft="इसके बारे में BCION से पूछें",
            back_translation="Ask BCION about this",
            agreement_flag=AGREEMENT_FLAG_OK,
            agreement_score=1.0,
        ),
    ]
    out = tmp_path / "2026-09-22.csv"
    write_csv(rows, out)

    with out.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(CSV_FIELDNAMES)
        read_rows = list(reader)

    assert len(read_rows) == 1
    row = read_rows[0]
    assert row["key"] == "ask.entry.default_label"
    assert row["english"] == "Ask BCION about this"
    assert row["hindi_draft"] == "इसके बारे में BCION से पूछें"
    assert row["back_translation"] == "Ask BCION about this"
    assert row["agreement_flag"] == AGREEMENT_FLAG_OK
    assert row["agreement_score"] == "1.000"


# ---------------------------------------------------------------------
# run() -- the whole batch, with synthetic fixture catalogues
# ---------------------------------------------------------------------


@pytest.fixture
def fixture_catalogues(tmp_path: Path) -> tuple[Path, Path]:
    en_path = tmp_path / "en.json"
    hi_path = tmp_path / "hi.json"
    _write_json(
        en_path,
        {
            "_meta.locale": "en",
            "greeting.hello": "Hello",
            "greeting.goodbye": "Goodbye",
            "already.translated": "Already translated",
        },
    )
    _write_json(
        hi_path,
        {
            "_meta.locale": "hi",
            "already.translated": "पहले से अनूदित",
        },
    )
    return en_path, hi_path


def test_run_writes_one_row_per_missing_key_and_never_touches_the_catalogues(
    tmp_path: Path, fixture_catalogues: tuple[Path, Path]
) -> None:
    en_path, hi_path = fixture_catalogues
    en_hash_before = _sha256(en_path)
    hi_hash_before = _sha256(hi_path)

    # Two missing keys (greeting.hello, greeting.goodbye) -> 4 calls total,
    # 2 per key (translation, back-translation), in en.json's key order.
    provider = MockAIProvider(
        responses=[
            "नमस्ते",  # greeting.hello translation
            "Hello",  # greeting.hello back-translation (agrees)
            "अलविदा",  # greeting.goodbye translation
            "Something totally different",  # greeting.goodbye back-translation (disagrees)
        ]
    )
    output_dir = tmp_path / "out"

    output_path = run(
        en_path=en_path,
        hi_path=hi_path,
        output_dir=output_dir,
        run_date="2026-09-22",
        provider=provider,
    )

    assert output_path == output_dir / "2026-09-22.csv"
    assert output_path.exists()

    # PROOF: en.json/hi.json byte-for-byte unchanged after the run.
    assert _sha256(en_path) == en_hash_before
    assert _sha256(hi_path) == hi_hash_before

    with output_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [r["key"] for r in rows] == ["greeting.hello", "greeting.goodbye"]
    assert rows[0]["hindi_draft"] == "नमस्ते"
    assert rows[0]["agreement_flag"] == AGREEMENT_FLAG_OK
    assert rows[1]["hindi_draft"] == "अलविदा"
    assert rows[1]["agreement_flag"] == AGREEMENT_FLAG_REVIEW
    # The already-translated key never went to the provider at all.
    assert len(provider.calls) == 4
    for call in provider.calls:
        assert "already.translated" not in call
        assert "Already translated" not in call


def test_run_returns_none_and_writes_nothing_when_no_keys_are_missing(tmp_path: Path) -> None:
    en_path = tmp_path / "en.json"
    hi_path = tmp_path / "hi.json"
    _write_json(en_path, {"a.one": "One"})
    _write_json(hi_path, {"a.one": "एक"})
    en_hash_before = _sha256(en_path)
    hi_hash_before = _sha256(hi_path)

    output_dir = tmp_path / "out"
    provider = MockAIProvider()

    result = run(
        en_path=en_path,
        hi_path=hi_path,
        output_dir=output_dir,
        run_date="2026-09-22",
        provider=provider,
    )

    assert result is None
    assert not output_dir.exists()
    assert provider.calls == []
    assert _sha256(en_path) == en_hash_before
    assert _sha256(hi_path) == hi_hash_before


def test_run_against_the_real_repo_catalogues_never_writes_them() -> None:
    """The property the card asks for explicitly, proven against the
    REAL app/i18n/en.json and app/i18n/hi.json this repo ships (not a
    fixture) -- hash both files before and after a real `run()` call and
    assert nothing changed. Uses MockAIProvider regardless of whether
    there happen to be any missing keys right now, so this never makes a
    network call even if that changes later."""
    en_hash_before = _sha256(DEFAULT_EN_PATH)
    hi_hash_before = _sha256(DEFAULT_HI_PATH)

    run(
        en_path=DEFAULT_EN_PATH,
        hi_path=DEFAULT_HI_PATH,
        output_dir=Path("this-directory-must-never-be-created-if-nothing-is-missing"),
        run_date="2026-09-22",
        provider=MockAIProvider(),
    )

    assert _sha256(DEFAULT_EN_PATH) == en_hash_before
    assert _sha256(DEFAULT_HI_PATH) == hi_hash_before


# ---------------------------------------------------------------------
# CLI (main()) -- --provider mock end-to-end, zero network calls
# ---------------------------------------------------------------------


def test_cli_provider_mock_end_to_end_writes_a_csv(tmp_path: Path) -> None:
    en_path = tmp_path / "en.json"
    hi_path = tmp_path / "hi.json"
    _write_json(en_path, {"a.one": "One", "a.two": "Two"})
    _write_json(hi_path, {})
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "--provider",
            "mock",
            "--en-path",
            str(en_path),
            "--hi-path",
            str(hi_path),
            "--output-dir",
            str(output_dir),
            "--run-date",
            "2026-09-22",
        ]
    )

    assert exit_code == 0
    out_file = output_dir / "2026-09-22.csv"
    assert out_file.exists()
    with out_file.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2


def test_cli_provider_mock_never_constructs_gemini_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--provider mock` must never touch GeminiProvider at all, even to
    check configuration -- proven by making GeminiProvider raise if
    constructed, then running the CLI with --provider mock and asserting
    it does not raise."""
    import scripts.ai_translate_drafts as module

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GeminiProvider must never be constructed under --provider mock")

    monkeypatch.setattr(module, "GeminiProvider", _explode)

    en_path = tmp_path / "en.json"
    hi_path = tmp_path / "hi.json"
    _write_json(en_path, {"a.one": "One"})
    _write_json(hi_path, {})

    exit_code = main(
        [
            "--provider",
            "mock",
            "--en-path",
            str(en_path),
            "--hi-path",
            str(hi_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--run-date",
            "2026-09-22",
        ]
    )
    assert exit_code == 0


def test_cli_reports_no_missing_keys_cleanly(tmp_path: Path) -> None:
    en_path = tmp_path / "en.json"
    hi_path = tmp_path / "hi.json"
    _write_json(en_path, {"a.one": "One"})
    _write_json(hi_path, {"a.one": "एक"})
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "--provider",
            "mock",
            "--en-path",
            str(en_path),
            "--hi-path",
            str(hi_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert not output_dir.exists()


# ---------------------------------------------------------------------
# _build_provider / real-provider gate (construction only -- never
# .generate(), never a network call)
# ---------------------------------------------------------------------


def test_build_provider_mock_returns_a_mock_ai_provider() -> None:
    provider = _build_provider("mock")
    assert isinstance(provider, MockAIProvider)


def test_build_provider_gemini_without_a_key_raises_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.ai.gemini_provider as gemini_provider_module

    monkeypatch.setattr(
        gemini_provider_module,
        "get_settings",
        lambda: Settings(_env_file=None),
    )

    with pytest.raises(GeminiNotConfiguredError):
        _build_provider("gemini")
