"""DESIGN-3 -- banned-phrase lint test.

Loads the machine-readable regex block from `docs/COPY.md` section 5
("Banned patterns") and scans the rendered template source under
`app/web/templates/` for any match: rank predictions, suitability
percentages, personality-type claims, guarantees and the other phrasing
CLAUDE.md's non-negotiables forbid ("No rank predictions, no 'you are not
suited', no personality-type labels, no guarantees").

`docs/COPY.md` is the single source of truth for the pattern list -- this
test never hard-codes a copy of it, so a new banned phrase added there is
enforced here automatically without a code change.

Jinja comments (`{# ... #}`) and HTML comments (`<!-- ... -->`) are
stripped before scanning, so an honest discussion of a banned phrase in a
template's own commentary (e.g. "don't say X here") is never itself
flagged -- only phrasing that would actually render to the page counts.

Scope: this test scans `app/web/templates/**/*.html` only, per its task
card. It does not scan Python string literals (e.g. `app/ai/grounding.py`'s
prompt-building strings, or `app/web/*.py` error messages) -- a static
regex scan can't see those without parsing Python source, which is a
known limitation flagged on DESIGN-3's own task card ("A static scan
cannot see strings built in Python ... note the limit"). Extending the
scan to app/ai and app/web/*.py source is a follow-up, not done here.

This runs under the existing `pytest tests/unit` job (see `Makefile`'s
`test-unit` target and `.github/workflows/ci.yml`) -- no CI config change
needed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COPY_MD_PATH = REPO_ROOT / "docs" / "COPY.md"
TEMPLATES_DIR = REPO_ROOT / "app" / "web" / "templates"

BANNED_BLOCK_RE = re.compile(r"```regex\n(.*?)```", re.DOTALL)
JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def load_banned_patterns() -> list[re.Pattern[str]]:
    """Parse the fenced ` ```regex ` block out of `docs/COPY.md` section 5
    and compile each non-blank line as a case-insensitive pattern."""
    copy_text = COPY_MD_PATH.read_text(encoding="utf-8")
    block_match = BANNED_BLOCK_RE.search(copy_text)
    assert block_match, (
        "docs/COPY.md no longer has a fenced ```regex block under "
        "'Banned patterns' -- DESIGN-3's lint test has nothing to enforce."
    )
    lines = [line.strip() for line in block_match.group(1).splitlines()]
    patterns = [line for line in lines if line]
    assert patterns, "docs/COPY.md's banned-patterns block is empty."
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


def strip_comments(text: str) -> str:
    """Remove Jinja `{# ... #}` and HTML `<!-- ... -->` comments so
    developer commentary about a banned phrase is never itself flagged."""
    without_jinja = JINJA_COMMENT_RE.sub(" ", text)
    return HTML_COMMENT_RE.sub(" ", without_jinja)


def find_banned_matches(
    text: str, patterns: list[re.Pattern[str]]
) -> list[tuple[str, str]]:
    """Return (pattern, matched text) for every banned pattern that
    matches anywhere in `text`, after stripping comments."""
    cleaned = strip_comments(text)
    return [
        (pattern.pattern, match.group(0))
        for pattern in patterns
        if (match := pattern.search(cleaned)) is not None
    ]


def discover_template_files() -> list[Path]:
    return sorted(TEMPLATES_DIR.rglob("*.html"))


def test_banned_patterns_load_from_copy_md() -> None:
    patterns = load_banned_patterns()
    # Sanity floor, not an exact count -- docs/COPY.md owns the real list.
    assert len(patterns) >= 10


def test_real_templates_have_no_banned_phrases() -> None:
    patterns = load_banned_patterns()
    template_files = discover_template_files()
    assert template_files, f"No template files found under {TEMPLATES_DIR}"

    violations: list[str] = []
    for path in template_files:
        text = path.read_text(encoding="utf-8")
        for pattern_str, matched_text in find_banned_matches(text, patterns):
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: /{pattern_str}/ matched {matched_text!r}"
            )

    assert not violations, (
        "Banned phrase(s) from docs/COPY.md found in a live template -- "
        "this is a real copy bug, not a test bug:\n" + "\n".join(violations)
    )


def test_seeded_banned_phrase_is_detected(tmp_path: Path) -> None:
    """Positive control: a banned phrase seeded into a template must be
    caught, proving the scan isn't vacuously passing."""
    patterns = load_banned_patterns()
    seeded = tmp_path / "seeded.html"
    seeded.write_text(
        "<p>Discover your perfect career with BCION today!</p>", encoding="utf-8"
    )

    matches = find_banned_matches(seeded.read_text(encoding="utf-8"), patterns)

    assert matches, "Expected the seeded banned phrase to be detected but it was not"


def test_banned_phrase_inside_a_comment_is_not_flagged(tmp_path: Path) -> None:
    """A banned phrase mentioned only inside a Jinja or HTML comment (e.g.
    developer commentary about what NOT to write) must not fail the
    build -- only phrasing that actually renders counts."""
    patterns = load_banned_patterns()
    commented = tmp_path / "commented.html"
    commented.write_text(
        "{# reminder: never write 'your perfect career' in this template #}\n"
        "<!-- also never say 'we guarantee' anywhere below -->\n"
        "<p>Explore this route</p>",
        encoding="utf-8",
    )

    matches = find_banned_matches(commented.read_text(encoding="utf-8"), patterns)

    assert not matches, f"Comment-only text should not be flagged, got: {matches}"
