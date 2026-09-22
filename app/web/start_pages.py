"""GET /start, one question per page — docs/UI.md "Quick start
(progressive, skippable where not essential)": "One question at a time:
studying now -> what to decide -> interests -> what matters most
... Account creation only when the user wants to save or sync -- not
before." (UI-3)

Everything below is a plain GET-chain: each page is a form whose ACTION
is the next question's URL and whose METHOD is "get", so submitting it
is indistinguishable, from the browser's point of view, from clicking a
plain link -- the whole flow works with zero JavaScript, and every
answer so far is always visible, bookmarkable and back-button-safe
because it lives in the URL's own query string, never a cookie or any
client-side storage. This is also why every question is independently
skippable with a plain `<a href="...">` "Skip this question" link: it is
just the same next-page URL with one field left out.

These four answers are coarse, non-identifying preference buckets --
"studying now" is a broad life-stage band (docs/UI.md's own example),
never a birth date; "what matters most" is verbatim the six named
options `docs/UI.md`'s Quick start section lists. None of the four is
age, marks, income, phone number or any other field CLAUDE.md's
non-negotiables would call personal, and none is ever accepted as free
text -- `_valid_or_none` below drops anything outside each question's
fixed option list rather than carrying an arbitrary string forward.

`/start/results` (the chain's end) renders a plain, non-judgemental
summary of whatever was answered or skipped. The actual suggestion
engine that would turn these answers into pathway matches is UI-4's job,
not this task's -- docs/UI.md's `why_am_i_seeing_this` slot
(`_why.html`) stays empty until that task exists, same as every other
screen today.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request

from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface

TOTAL_STEPS = 4

# docs/UI.md "studying now" -- a broad life-stage band, never an exact
# age or date of birth.
STAGE_OPTIONS: list[dict[str, str]] = [
    {"value": "secondary", "label": "Class 8-10"},
    {"value": "senior_secondary", "label": "Class 11-12"},
    {"value": "finished_school", "label": "Already finished school"},
]

# docs/UI.md "what to decide".
GOAL_OPTIONS: list[dict[str, str]] = [
    {"value": "stream", "label": "Which subject stream to choose"},
    {"value": "course", "label": "Which course to study after school"},
    {"value": "career", "label": "Which career path to explore"},
    {"value": "not_sure", "label": "Not sure yet"},
]

# docs/UI.md "interests" -- broad, non-scored interest areas, never a
# personality-type label (CLAUDE.md non-negotiables).
INTEREST_OPTIONS: list[dict[str, str]] = [
    {"value": "science_tech", "label": "Science and technology"},
    {"value": "arts_design", "label": "Arts and design"},
    {"value": "business_commerce", "label": "Business and commerce"},
    {"value": "healthcare", "label": "Healthcare and life sciences"},
    {"value": "skilled_trades", "label": "Skilled trades and vocational work"},
    {"value": "not_sure", "label": "Not sure yet"},
]

# docs/UI.md "what matters most (affordable / near home / start work
# sooner / keep options open / a particular interest / not sure yet)" --
# verbatim, this is the one question whose options the contract itself
# names.
PRIORITY_OPTIONS: list[dict[str, str]] = [
    {"value": "affordable", "label": "Affordable"},
    {"value": "near_home", "label": "Near home"},
    {"value": "start_work_sooner", "label": "Start work sooner"},
    {"value": "keep_options_open", "label": "Keep options open"},
    {"value": "particular_interest", "label": "A particular interest"},
    {"value": "not_sure", "label": "Not sure yet"},
]


def _valid_or_none(value: str | None, options: list[dict[str, str]]) -> str | None:
    """A query param outside this question's own fixed option list is
    treated as not answered -- same "never guess, never invent" spirit
    as `app.web.common._int_or_none` -- rather than carried forward as
    an arbitrary string. This is also what keeps this flow to fixed,
    non-personal categories: there is no way to get free text into any
    of these four fields, tampered URL or not."""
    if value is None:
        return None
    allowed = {opt["value"] for opt in options}
    return value if value in allowed else None


def _label_for(value: str | None, options: list[dict[str, str]]) -> str | None:
    if value is None:
        return None
    for opt in options:
        if opt["value"] == value:
            return opt["label"]
    return None


def _hidden_answers(**answers: str | None) -> dict[str, str]:
    """Only the fields actually answered so far travel forward as hidden
    inputs / query params -- an unanswered (skipped) question is simply
    absent, never an empty-string placeholder."""
    return {key: value for key, value in answers.items() if value is not None}


def _with_query(path: str, params: dict[str, str]) -> str:
    if not params:
        return path
    return f"{path}?{urlencode(params)}"


@router.get("/start")
def start_stage(request: Request) -> Any:
    """Question 1 of 4 -- "studying now". No prior answers exist yet, so
    this page has nothing to carry forward."""
    return templates.TemplateResponse(
        request,
        "start_question.html",
        {
            "step": 1,
            "total_steps": TOTAL_STEPS,
            "heading": "What are you studying right now?",
            "field_name": "stage",
            "options": STAGE_OPTIONS,
            "hidden_answers": {},
            "next_action": "/start/decide",
            "skip_url": "/start/decide",
        },
    )


@router.get("/start/decide")
def start_decide(request: Request, stage: str | None = Query(default=None)) -> Any:
    """Question 2 of 4 -- "what to decide"."""
    stage_value = _valid_or_none(stage, STAGE_OPTIONS)
    hidden = _hidden_answers(stage=stage_value)
    return templates.TemplateResponse(
        request,
        "start_question.html",
        {
            "step": 2,
            "total_steps": TOTAL_STEPS,
            "heading": "What are you trying to decide right now?",
            "field_name": "goal",
            "options": GOAL_OPTIONS,
            "hidden_answers": hidden,
            "next_action": "/start/interest",
            "skip_url": _with_query("/start/interest", hidden),
        },
    )


@router.get("/start/interest")
def start_interest(
    request: Request,
    stage: str | None = Query(default=None),
    goal: str | None = Query(default=None),
) -> Any:
    """Question 3 of 4 -- "interests"."""
    stage_value = _valid_or_none(stage, STAGE_OPTIONS)
    goal_value = _valid_or_none(goal, GOAL_OPTIONS)
    hidden = _hidden_answers(stage=stage_value, goal=goal_value)
    return templates.TemplateResponse(
        request,
        "start_question.html",
        {
            "step": 3,
            "total_steps": TOTAL_STEPS,
            "heading": "What are you interested in?",
            "field_name": "interest",
            "options": INTEREST_OPTIONS,
            "hidden_answers": hidden,
            "next_action": "/start/priority",
            "skip_url": _with_query("/start/priority", hidden),
        },
    )


@router.get("/start/priority")
def start_priority(
    request: Request,
    stage: str | None = Query(default=None),
    goal: str | None = Query(default=None),
    interest: str | None = Query(default=None),
) -> Any:
    """Question 4 of 4 -- "what matters most"."""
    stage_value = _valid_or_none(stage, STAGE_OPTIONS)
    goal_value = _valid_or_none(goal, GOAL_OPTIONS)
    interest_value = _valid_or_none(interest, INTEREST_OPTIONS)
    hidden = _hidden_answers(stage=stage_value, goal=goal_value, interest=interest_value)
    return templates.TemplateResponse(
        request,
        "start_question.html",
        {
            "step": 4,
            "total_steps": TOTAL_STEPS,
            "heading": "What matters most to you right now?",
            "field_name": "priority",
            "options": PRIORITY_OPTIONS,
            "hidden_answers": hidden,
            "next_action": "/start/results",
            "skip_url": _with_query("/start/results", hidden),
        },
    )


@router.get("/start/results")
def start_results(
    request: Request,
    stage: str | None = Query(default=None),
    goal: str | None = Query(default=None),
    interest: str | None = Query(default=None),
    priority: str | None = Query(default=None),
) -> Any:
    """The chain's end -- UI-3's own plain "thanks, here's what you told
    us" summary. Matching real pathway suggestions to these answers is
    UI-4's job, not this one (see this module's own docstring)."""
    stage_value = _valid_or_none(stage, STAGE_OPTIONS)
    goal_value = _valid_or_none(goal, GOAL_OPTIONS)
    interest_value = _valid_or_none(interest, INTEREST_OPTIONS)
    priority_value = _valid_or_none(priority, PRIORITY_OPTIONS)
    answers = [
        {
            "question": "What you're studying right now",
            "answer": _label_for(stage_value, STAGE_OPTIONS),
        },
        {
            "question": "What you're trying to decide",
            "answer": _label_for(goal_value, GOAL_OPTIONS),
        },
        {
            "question": "What you're interested in",
            "answer": _label_for(interest_value, INTEREST_OPTIONS),
        },
        {
            "question": "What matters most to you",
            "answer": _label_for(priority_value, PRIORITY_OPTIONS),
        },
    ]
    all_skipped = all(row["answer"] is None for row in answers)
    return templates.TemplateResponse(
        request,
        "start_results.html",
        {"answers": answers, "all_skipped": all_skipped},
    )
