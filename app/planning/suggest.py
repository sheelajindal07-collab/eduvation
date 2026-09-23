"""Quick-start suggestion logic — UI-4.

Given the four `/start` quick-start answers (`app/web/start_pages.py`) and
a set of already-fetched pathway candidates, return up to three suggested
pathways by tag matching, each carrying the full "why am I seeing this"
explanation docs/UI.md requires: the reasons it matched, which of the
student's stated preferences influenced the match, and what is still
UNKNOWN (missing tag data that would sharpen the match).

Pure function, caller fetches the data — mirrors
`app.planning.comparison`'s "pure function, caller fetches the data"
shape exactly: nothing in this module does I/O, imports `app.db.*`, or
otherwise reaches a database. `app.data.models.Pathway` has no `tags`
field yet (there is no tags column anywhere in `db/migrations/` either),
so as of UI-4 there is no live, published source of tag data for a
caller to fetch — `app/web/start_pages.py`'s own candidate-provider seam
documents this and returns an empty list today. A caller with zero
candidates and a caller with candidates that simply don't match the
student's answers are two different, both perfectly real, situations —
see `SuggestionResult` below — and neither one is treated as an error.

CLAUDE.md non-negotiables this module exists to honour:
  - "No rank predictions ... ranges and named assumptions only": a
    suggestion's `reasons` are plain sentences naming a matched
    preference, never a score, a percentage, or an "N% match".
  - No salary or prestige signal anywhere in this module — matching is
    on the student's own stated preferences against a pathway's tags,
    nothing else, and candidates are never reordered by anything else.
  - "Budget" (the `priority="affordable"` answer) never removes a
    pathway from consideration: `_score` below only ever *adds* to a
    candidate's score for a matched preference tag. There is no code
    path anywhere in this module that drops a candidate from
    consideration because of what `priority` is — the only thing that
    ever shrinks the matched list is the "up to three" truncation,
    which applies identically regardless of which preferences matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# docs/UI.md "Quick start": "up to three" suggested pathways.
MAX_SUGGESTIONS = 3


@dataclass(frozen=True)
class QuickStartAnswers:
    """The four `/start` answers, already validated against each
    question's fixed option list by `app/web/start_pages.py`'s
    `_valid_or_none` — this module never sees free text, only `None` or
    one of each question's known values.

    `stage` is accepted but deliberately never tag-matched below: it
    describes the student's own life-stage band (docs/UI.md), not a
    property a pathway is tagged with, and there is no "which stage is
    this pathway relevant to" tag anywhere to match it against. Carrying
    it here (rather than dropping it from this dataclass) keeps this
    type a complete, honest record of all four answers, even though only
    three of them currently drive a match."""

    stage: str | None = None
    goal: str | None = None
    interest: str | None = None
    priority: str | None = None


@dataclass(frozen=True)
class SuggestionCandidate:
    """One pathway available to suggest, exactly as already fetched and
    filtered by the caller — "published (non-draft, non-synthetic)" is
    the caller's job to guarantee before it ever reaches this module,
    the same division of labour `app.planning.comparison.field_value_for`
    already draws between "decide what's publishable" (claim/source
    status) and "assemble the screen" (pure function over the result).
    This module does no publication-status filtering of its own; it only
    matches whatever `tags` it is handed."""

    pathway_id: str
    name: str
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Suggestion:
    """One suggested pathway, plus the "why am I seeing this" parts
    docs/UI.md requires and `app/web/templates/_why.html`'s
    `why_am_i_seeing_this` macro renders: `reasons`, `preferences`
    (which of the student's stated answers influenced this suggestion)
    and `unknowns` (which stated preferences this candidate carries no
    tag data for at all — the part a recommendation engine is tempted to
    leave out). `reasons` is never empty: every `Suggestion` this module
    returns has at least one reason, whether it is a genuine tag match or
    the honest "nothing matched, here's what's available" reason a
    broadened suggestion carries."""

    pathway_id: str
    name: str
    reasons: tuple[str, ...]
    preferences: tuple[str, ...]
    unknowns: tuple[str, ...]
    unknown_change_label: str | None = None
    """What the "change preferences" link should name when there is
    exactly ONE unknown preference for this suggestion -- e.g. "your
    interest" so the link can read "Change your interest" instead of the
    generic "Change what matters most to you" (ux-qa-reviewer finding on
    UI-4: the link always named the same generic thing regardless of
    which preference was actually missing). `None` whenever zero or more
    than one preference is unknown, which is also the caller's signal to
    fall back to the generic wording -- `_components.html`'s
    `why_seeing_this` decides nothing about which case it is in; this
    field is the already-decided answer."""


@dataclass(frozen=True)
class SuggestionResult:
    """`suggest_pathways`'s one return shape, covering all three cases a
    caller has to render something honest for:

      has_data=True,  is_broadened=False   real tag matches; `suggestions`
                                            is the matched, ranked list.
      has_data=True,  is_broadened=True    candidates existed but none of
                                            their tags matched the stated
                                            answers; `suggestions` is a
                                            deterministic sample of what
                                            *is* available, each still
                                            carrying an honest reason —
                                            never an empty list with no
                                            explanation.
      has_data=False                       the caller had no candidates
                                            to offer at all (today's real
                                            case: no published pathway
                                            carries any tag data yet).
                                            `suggestions` is always empty
                                            here; the caller's own
                                            template degrades to a plain
                                            link to Explore instead of a
                                            fabricated or empty-looking
                                            "match".
    """

    suggestions: tuple[Suggestion, ...]
    has_data: bool
    is_broadened: bool


# Which quick-start answer value maps to which tag a candidate might
# carry, and the plain-language label used in a reason/preference/unknown
# line. Deliberately excludes each question's own "not_sure" option (and
# "stage" entirely, see `QuickStartAnswers` above) — "not sure yet" is not
# a preference to match against, it is the absence of one.
#
# Capitalised the same way `app/web/start_pages.py`'s own `GOAL_OPTIONS`
# labels already are ("Which subject stream to choose", etc, verbatim) --
# `_INTEREST_TAGS`/`_PRIORITY_TAGS` labels below are capitalised phrases
# too, so a joined "What you told us: ..." line never mixes a lowercase
# goal fragment into an otherwise capitalised list (ux-qa-reviewer finding
# on UI-4).
_GOAL_TAGS: dict[str, tuple[str, str]] = {
    "stream": ("decision:stream", "Which subject stream to choose"),
    "course": ("decision:course", "Which course to study after school"),
    "career": ("decision:career", "Which career path to explore"),
}
_INTEREST_TAGS: dict[str, tuple[str, str]] = {
    "science_tech": ("interest:science_tech", "Science and technology"),
    "arts_design": ("interest:arts_design", "Arts and design"),
    "business_commerce": ("interest:business_commerce", "Business and commerce"),
    "healthcare": ("interest:healthcare", "Healthcare and life sciences"),
    "skilled_trades": ("interest:skilled_trades", "Skilled trades and vocational work"),
}
_PRIORITY_TAGS: dict[str, tuple[str, str]] = {
    "affordable": ("priority:affordable", "Affordable"),
    "near_home": ("priority:near_home", "Near home"),
    "start_work_sooner": ("priority:start_work_sooner", "Start work sooner"),
    "keep_options_open": ("priority:keep_options_open", "Keep options open"),
    "particular_interest": ("priority:particular_interest", "A particular interest"),
}


@dataclass(frozen=True)
class _StatedPreference:
    tag: str
    label: str
    reason_template: str
    change_label: str
    """The phrase that completes "Change {change_label}" when this is the
    ONE preference a suggestion carries no tag data for -- named after
    the question it came from ("your interest", "your priority", "what
    you're trying to decide"), never the generic "what matters most to
    you" catch-all, which stays reserved for the multiple-or-none-unknown
    case (see `Suggestion.unknown_change_label`)."""


def _stated_preferences(answers: QuickStartAnswers) -> list[_StatedPreference]:
    """Every preference this module actually knows how to tag-match,
    given what the student stated — order is fixed (goal, interest,
    priority) so `reasons`/`preferences`/`unknowns` come back in the same
    order on every call for the same answers, part of what makes
    `suggest_pathways` deterministic."""
    preferences: list[_StatedPreference] = []
    if answers.goal in _GOAL_TAGS:
        tag, label = _GOAL_TAGS[answers.goal]
        preferences.append(
            _StatedPreference(
                tag,
                label,
                "Matches what you're trying to decide: {label}.",
                "what you're trying to decide",
            )
        )
    if answers.interest in _INTEREST_TAGS:
        tag, label = _INTEREST_TAGS[answers.interest]
        preferences.append(
            _StatedPreference(
                tag, label, "Matches your interest in {label}.", "your interest"
            )
        )
    if answers.priority in _PRIORITY_TAGS:
        tag, label = _PRIORITY_TAGS[answers.priority]
        preferences.append(
            _StatedPreference(
                tag,
                label,
                "Matches what matters most to you: {label}.",
                "your priority",
            )
        )
    return preferences


def _unknown_change_label(unknown_preferences: list[_StatedPreference]) -> str | None:
    """`Suggestion.unknown_change_label` for one suggestion: the single
    unknown preference's own `change_label` when there is exactly one,
    `None` (generic fallback) otherwise -- zero unknowns never reaches
    this (nothing to name), and more than one is deliberately not named
    ("Change your interest" would be misleading/incomplete when the
    priority is unknown too)."""
    if len(unknown_preferences) == 1:
        return unknown_preferences[0].change_label
    return None


def _matched_suggestion(
    candidate: SuggestionCandidate, stated: list[_StatedPreference]
) -> tuple[Suggestion, int]:
    """One candidate's `Suggestion` plus its match score (the count of
    stated preferences it actually carries a tag for) — score is used
    only to rank/truncate the matched list, never to drop a candidate
    from it (see this module's own docstring on the budget rule)."""
    reasons: list[str] = []
    preferences: list[str] = []
    unknowns: list[str] = []
    unknown_preferences: list[_StatedPreference] = []
    for pref in stated:
        if pref.tag in candidate.tags:
            reasons.append(pref.reason_template.format(label=pref.label))
            preferences.append(pref.label)
        else:
            unknowns.append(pref.label)
            unknown_preferences.append(pref)
    return (
        Suggestion(
            pathway_id=candidate.pathway_id,
            name=candidate.name,
            reasons=tuple(reasons),
            preferences=tuple(preferences),
            unknowns=tuple(unknowns),
            unknown_change_label=_unknown_change_label(unknown_preferences),
        ),
        len(reasons),
    )


def _broadened_suggestion(
    candidate: SuggestionCandidate, stated: list[_StatedPreference]
) -> Suggestion:
    """The honest "nothing matched" suggestion for one candidate: still
    exactly one reason (never a fabricated match), and every stated
    preference is carried forward as unknown, because — by construction,
    this helper is only ever called once `suggest_pathways` has already
    established that NO candidate matched ANY stated preference — none of
    them are known to apply to this candidate either."""
    reason = (
        "None of the published pathways matched what you told us yet — this is"
        " one of the pathways currently available."
        if stated
        else "You didn't tell us enough yet to narrow this down — this is one"
        " of the pathways currently available."
    )
    return Suggestion(
        pathway_id=candidate.pathway_id,
        name=candidate.name,
        reasons=(reason,),
        preferences=(),
        unknowns=tuple(pref.label for pref in stated),
        unknown_change_label=_unknown_change_label(stated),
    )


def suggest_pathways(
    answers: QuickStartAnswers, candidates: list[SuggestionCandidate]
) -> SuggestionResult:
    """Up to `MAX_SUGGESTIONS` suggested pathways for these answers.

    Deterministic: the same `answers` and the same `candidates` always
    produce the same `SuggestionResult`, regardless of the input list's
    own order — matched candidates are ranked by (score desc, name,
    pathway_id) rather than left in caller-supplied order, and a
    broadened/no-match sample is ordered the same way.
    """
    if not candidates:
        return SuggestionResult(suggestions=(), has_data=False, is_broadened=False)

    stated = _stated_preferences(answers)

    scored = [_matched_suggestion(candidate, stated) for candidate in candidates]
    matched = [(suggestion, score) for suggestion, score in scored if score > 0]

    if matched:
        matched.sort(key=lambda pair: (-pair[1], pair[0].name, pair[0].pathway_id))
        top = tuple(suggestion for suggestion, _score in matched[:MAX_SUGGESTIONS])
        return SuggestionResult(suggestions=top, has_data=True, is_broadened=False)

    broadened = sorted(candidates, key=lambda c: (c.name, c.pathway_id))[:MAX_SUGGESTIONS]
    suggestions = tuple(_broadened_suggestion(candidate, stated) for candidate in broadened)
    return SuggestionResult(suggestions=suggestions, has_data=True, is_broadened=True)
