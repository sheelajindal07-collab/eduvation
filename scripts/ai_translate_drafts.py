#!/usr/bin/env python
"""Offline, owner-run batch: propose Hindi translations for every
`app/i18n/en.json` key missing from `app/i18n/hi.json` (AI-20).

**Never called from a request path, never imported by `app/`.** This is a
standalone content-drafting tool, run by hand or in CI (with `--provider
mock`), not application code.

What it does
------------
For every key present in `en.json` but absent from `hi.json` (a plain key
diff -- see `missing_keys()` -- not a value comparison, so a key that
exists in both files is left alone even if its Hindi value looks stale):

1. **Translation pass** -- one `provider.generate(...)` call: the English
   string in, a proposed Hindi translation out.
2. **Back-translation check pass** -- a SECOND, separate
   `provider.generate(...)` call: that proposed Hindi translation in, an
   English back-translation out. This is never a re-run of the first call
   and never reuses its output beyond feeding the Hindi draft in as the
   new prompt's input.

The two are compared by a cheap, documented heuristic (see "The agreement
heuristic, honestly" below) and every key becomes one row in a CSV under
`content/staging/hindi_drafts/<run-date>.csv` for a human Hindi reviewer.

**This script never writes `hi.json` or `en.json`.** Both are only ever
opened for reading, via `load_catalogue()`. There is no flag, no code
path, that opens either for writing -- the CSV is the only output. Never
writes to a database either.

The agreement heuristic, honestly
----------------------------------
`agreement_score()` is a normalised **token-overlap ratio (Jaccard
similarity)**: lower-case both the original English string and the
back-translation, extract alphanumeric tokens (`[a-z0-9]+`), and divide
the size of their intersection by the size of their union. A score of
`1.0` means the two strings used exactly the same set of distinct words;
`0.0` means they shared none. `agreement_flag()` calls a score `>=
AGREEMENT_THRESHOLD` (0.5, chosen because a correct translation and its
own round-tripped back-translation are two independently-phrased English
sentences, not the same sentence twice -- demanding much stricter overlap
would flag almost every good translation, and demanding much looser
overlap would stop catching real mistranslations) `"agrees"`, otherwise
`"needs_review"`.

**What this heuristic does NOT do: it does not check meaning.** Word
overlap is a cheap proxy that can be fooled in both directions -- two
sentences can share every word and mean opposite things ("the fee is
refundable" vs. "the fee is not refundable" overlap heavily), and a
faithful translation can legitimately use different words in its
back-translation ("charge" vs. "fee") and score low. It catches gross
translation failures (empty output, wrong-language output, a wildly
different sentence) reasonably well and nothing subtler than that. This
is exactly why EVERY row -- agreeing or not -- goes into the CSV for a
human to actually read (see this card's "the whole point of the CSV"),
and why `agreement_flag` is a triage hint, never a pass/fail gate: a
`"needs_review"` row is not silently dropped, and an `"agrees"` row is
not silently auto-accepted anywhere in this codebase.

Providers
---------
`--provider gemini` (default) uses the real, hosted `GeminiProvider`
(`app/ai/gemini_provider.py`) and needs `GEMINI_API_KEY` set in the
environment, exactly like every other AI-1a script -- copy `.env.example`
to `.env` and fill in a real key via the provider dashboard (CLAUDE.md:
no secrets in repo memory). `--provider mock` uses `MockAIProvider`
(`app/ai/mock_provider.py`): deterministic, zero network calls, what
every test in `tests/unit/test_ai_translate_drafts.py` and CI use.

Usage
-----
    python scripts/ai_translate_drafts.py --provider mock   # CI / smoke
    python scripts/ai_translate_drafts.py                   # real run, needs GEMINI_API_KEY
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from app.ai.adapter import AIProvider
from app.ai.gemini_provider import GeminiNotConfiguredError, GeminiProvider
from app.ai.mock_provider import MockAIProvider

# ---------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_EN_PATH: Final[Path] = REPO_ROOT / "app" / "i18n" / "en.json"
DEFAULT_HI_PATH: Final[Path] = REPO_ROOT / "app" / "i18n" / "hi.json"
DEFAULT_OUTPUT_DIR: Final[Path] = REPO_ROOT / "content" / "staging" / "hindi_drafts"

#: See the module docstring's "The agreement heuristic, honestly" section
#: for what this threshold means and does not mean.
AGREEMENT_THRESHOLD: Final[float] = 0.5

AGREEMENT_FLAG_OK: Final[str] = "agrees"
AGREEMENT_FLAG_REVIEW: Final[str] = "needs_review"

#: Column order for the output CSV -- exactly as this card specifies.
CSV_FIELDNAMES: Final[tuple[str, ...]] = (
    "key",
    "english",
    "hindi_draft",
    "back_translation",
    "agreement_flag",
    "agreement_score",
)

_TRANSLATE_PROMPT: Final[str] = """Translate the following English user-interface text into \
Hindi (Devanagari script). This string is shown to Indian school students (Class 8-12) using \
a career-guidance product. If the text contains a placeholder token in curly braces (for \
example {{requirement}} or {{date}}), copy that placeholder EXACTLY as written -- do not \
translate, reword or remove anything inside curly braces. Reply with ONLY the Hindi \
translation and nothing else: no explanation, no quotation marks, no English text.

English text:
{english}"""

_BACK_TRANSLATE_PROMPT: Final[str] = """Translate the following Hindi text back into English. \
If the text contains a placeholder token in curly braces (for example {{requirement}} or \
{{date}}), copy that placeholder EXACTLY as written -- do not translate, reword or remove \
anything inside curly braces. Reply with ONLY the English translation and nothing else: no \
explanation, no quotation marks, no Hindi text.

Hindi text:
{hindi}"""

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------
# Catalogue I/O -- reading only. Nothing in this module ever opens
# en_path/hi_path in a write mode; see the module docstring.
# ---------------------------------------------------------------------


def load_catalogue(path: Path) -> dict[str, str]:
    """Read an i18n catalogue JSON file (`app/i18n/en.json` or `hi.json`
    shape: a flat `{"key": "value", ...}` object). Read-only -- this
    function never opens `path` for writing."""
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object at the top level")
    for key, value in data.items():
        if not isinstance(value, str):
            raise ValueError(
                f"{path}: key {key!r} has a non-string value ({type(value).__name__}); "
                "this script only knows how to translate flat string catalogues"
            )
    return data


def missing_keys(en: dict[str, str], hi: dict[str, str]) -> list[str]:
    """Every key present in `en` but absent from `hi`, in `en`'s own
    iteration order (a Python dict preserves insertion order, which here
    matches the order keys were read from the JSON file) so the CSV's row
    order is stable and traceable back to the catalogue file, rather than
    an arbitrary set order."""
    return [key for key in en if key not in hi]


# ---------------------------------------------------------------------
# The agreement heuristic -- see module docstring for what it does and
# does not mean.
# ---------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def agreement_score(english: str, back_translation: str) -> float:
    """Normalised token-overlap ratio (Jaccard similarity) between the
    original English string and the back-translation. `1.0` = identical
    token sets, `0.0` = no shared tokens, both-empty = `1.0` (nothing to
    disagree about). See module docstring: this is a lexical proxy, not a
    semantic-equivalence check."""
    english_tokens = _tokenize(english)
    back_tokens = _tokenize(back_translation)
    if not english_tokens and not back_tokens:
        return 1.0
    if not english_tokens or not back_tokens:
        return 0.0
    return len(english_tokens & back_tokens) / len(english_tokens | back_tokens)


def agreement_flag(score: float, *, threshold: float = AGREEMENT_THRESHOLD) -> str:
    """`AGREEMENT_FLAG_OK` if `score >= threshold`, else
    `AGREEMENT_FLAG_REVIEW`. Never used to drop or auto-accept a row --
    only to label it for the human reviewer (module docstring)."""
    return AGREEMENT_FLAG_OK if score >= threshold else AGREEMENT_FLAG_REVIEW


# ---------------------------------------------------------------------
# One row: translate, then back-translate-and-check
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class DraftRow:
    """One CSV row: a proposed Hindi translation for one `en.json` key,
    plus the back-translation check that produced its agreement fields."""

    key: str
    english: str
    hindi_draft: str
    back_translation: str
    agreement_flag: str
    agreement_score: float

    def as_csv_row(self) -> dict[str, str]:
        return {
            "key": self.key,
            "english": self.english,
            "hindi_draft": self.hindi_draft,
            "back_translation": self.back_translation,
            "agreement_flag": self.agreement_flag,
            "agreement_score": f"{self.agreement_score:.3f}",
        }


def draft_translation(
    key: str,
    english: str,
    provider: AIProvider,
    *,
    threshold: float = AGREEMENT_THRESHOLD,
) -> DraftRow:
    """Run the translation pass then the back-translation check pass for
    one key. Exactly two `provider.generate()` calls, in order -- the
    second is a genuinely separate call fed the FIRST call's output, never
    a re-run of the first (module docstring)."""
    hindi_draft = provider.generate(_TRANSLATE_PROMPT.format(english=english)).strip()
    back_translation = provider.generate(_BACK_TRANSLATE_PROMPT.format(hindi=hindi_draft)).strip()
    score = agreement_score(english, back_translation)
    return DraftRow(
        key=key,
        english=english,
        hindi_draft=hindi_draft,
        back_translation=back_translation,
        agreement_flag=agreement_flag(score, threshold=threshold),
        agreement_score=score,
    )


# ---------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------


def write_csv(rows: Sequence[DraftRow], path: Path) -> None:
    """Write `rows` to `path` as the reviewer CSV. `utf-8-sig` so the
    Devanagari text renders correctly if a reviewer opens this directly in
    Excel, rather than the mojibake a plain `utf-8` file shows there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDNAMES))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_row())


# ---------------------------------------------------------------------
# The whole batch
# ---------------------------------------------------------------------


def run(
    *,
    en_path: Path,
    hi_path: Path,
    output_dir: Path,
    run_date: str,
    provider: AIProvider,
    threshold: float = AGREEMENT_THRESHOLD,
) -> Path | None:
    """Read `en_path`/`hi_path`, translate every key missing from
    `hi_path`, and write the reviewer CSV. Returns the CSV path written,
    or `None` if there was nothing to translate (every `en_path` key
    already has an `hi_path` entry) -- in which case nothing is written
    anywhere, not even an empty CSV.

    Never writes to `en_path` or `hi_path`: both only ever pass through
    `load_catalogue()`, which opens them read-only.
    """
    en = load_catalogue(en_path)
    hi = load_catalogue(hi_path)
    keys = missing_keys(en, hi)
    if not keys:
        return None

    rows = [draft_translation(key, en[key], provider, threshold=threshold) for key in keys]
    output_path = output_dir / f"{run_date}.csv"
    write_csv(rows, output_path)
    return output_path


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def _build_provider(name: str) -> AIProvider:
    if name == "mock":
        return MockAIProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"unknown --provider {name!r}")  # pragma: no cover - argparse restricts this


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--provider",
        choices=("gemini", "mock"),
        default="gemini",
        help=(
            "'gemini' (default): the real Gemini API, needs GEMINI_API_KEY set. "
            "'mock': MockAIProvider, zero network calls -- for CI/tests."
        ),
    )
    parser.add_argument("--en-path", type=Path, default=DEFAULT_EN_PATH)
    parser.add_argument("--hi-path", type=Path, default=DEFAULT_HI_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--run-date",
        default=date.today().isoformat(),
        help="Used in the output filename, <run-date>.csv. Defaults to today (UTC/local date).",
    )
    parser.add_argument(
        "--agreement-threshold",
        type=float,
        default=AGREEMENT_THRESHOLD,
        help="See module docstring's 'The agreement heuristic, honestly' section.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        provider = _build_provider(args.provider)
    except GeminiNotConfiguredError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        output_path = run(
            en_path=args.en_path,
            hi_path=args.hi_path,
            output_dir=args.output_dir,
            run_date=args.run_date,
            provider=provider,
            threshold=args.agreement_threshold,
        )
    except (OSError, ValueError) as exc:
        print(f"ai_translate_drafts: {exc}", file=sys.stderr)
        return 1

    if output_path is None:
        print(
            f"ai_translate_drafts: no missing keys -- every key in {args.en_path} "
            f"already has an entry in {args.hi_path}. Nothing written."
        )
        return 0

    print(
        f"ai_translate_drafts: wrote {output_path}\n"
        "This is a machine-drafted, back-translation-checked CANDIDATE only -- "
        "a human Hindi reviewer must read every row before any of it reaches "
        "app/i18n/hi.json. See content/staging/hindi_drafts/README.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
