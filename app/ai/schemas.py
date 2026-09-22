"""The Ask BCION contract — statuses, request/answer shapes, typed errors
and the outbound-payload allow-list.

Pure schema module: Pydantic v2 models, enums, exception types and
constants. **No I/O of any kind** — no HTTP, no database, no file reads,
no provider call, no settings lookup. Every other AI module (the
two-pass runner, the banned-phrase guard, the eval set, the routes)
imports its vocabulary from here so that there is exactly one definition
of "what an Ask BCION answer is allowed to be", and a change to it is a
one-file diff rather than a hunt.

Why a contract module at all
----------------------------
CLAUDE.md's non-negotiable is "AI never invents facts. It explains and
personalises over retrieved, human-verified records." That is a claim
about a *boundary*, and a boundary is only real if crossing it is a type
error or a validation error. Three properties are made mechanically
checkable here rather than left to prose:

1. **Nothing free-typed leaves the building.** `OutboundPayload` is the
   only shape permitted on the wire to a hosted provider, and it has
   exactly four fields (`template_id`, `record_ids`, `record_values`,
   `lang`). `extra="forbid"` means a caller cannot smuggle a fifth —
   not a student's question, not a session id, not a "context" blob.
   Its validator then requires every entry in `record_values` to be
   namespaced by an id that is itself on `record_ids`, so a value with
   no allow-listed record behind it cannot be constructed at all. See
   `untraceable_values()` and `from_records()` below.

2. **The model never authors a sentence a student reads.** `Answer`
   separates `selection_ids` (pass one: which records the model chose)
   from `verification_ids` (pass two: which of *those* an adversarial
   second call confirmed) from `sentences` (built by ordinary code from
   the verified records). `verification_ids` must be a subset of
   `selection_ids` — pass two is allowed to shrink the selection, never
   to introduce a record pass one did not select — and `sentences` is
   non-empty only when `status is AIAnswerStatus.answered`.

3. **An unknown is never dressed up as a guess.** `AIAnswerStatus` has a
   distinct value for each way an answer can be withheld, so a caller
   cannot collapse "we have no record" into "the provider was down" and
   show the same vague shrug for both.

Relationship to `app/ai/grounding.py`
-------------------------------------
`grounding.py` (M5) already defines a three-member `AIAnswerStatus`
(`answered`, `not_available`, `insufficient_information`) for the
single-pass grounded-answer path. The enum here is a strict superset:
those three values are spelled identically and carry identical meaning,
plus the three failure modes the two-pass pipeline can hit that the M5
path could not express (`ai_unavailable`, `budget_exhausted`,
`unsupported_template`). Both names are deliberately left in place for
now — this module does not touch `grounding.py` — and converging them is
a later card's call, not this one's.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

#: Languages an Ask BCION request may be made in. Mirrors
#: `app.i18n.SUPPORTED_LOCALES`; duplicated as a literal rather than
#: imported so that this module stays import-free of anything that
#: touches the filesystem (the i18n package loads catalogue JSON).
SUPPORTED_LANGS: Final[tuple[str, ...]] = ("en", "hi")

#: The four field names an outbound provider payload may carry. Stated
#: as data as well as as model fields so a test can assert the two agree
#: and a future field addition cannot happen silently.
ALLOWED_OUTBOUND_FIELDS: Final[tuple[str, ...]] = (
    "template_id",
    "record_ids",
    "record_values",
    "lang",
)

#: Upper bounds. These are not performance tuning — they are the
#: difference between "a handful of short retrieved facts" and "a
#: paragraph of prose someone pasted in", which is the exact thing the
#: outbound allow-list exists to prevent.
MAX_RECORD_IDS: Final[int] = 50
MAX_RECORD_VALUE_CHARS: Final[int] = 1_000
MAX_ID_CHARS: Final[int] = 128

# An identifier this codebase actually issues: UUID strings and slugs
# (`app/data/models.py` types every id as `str`). Deliberately excludes
# whitespace, punctuation that reads as prose, and every control
# character, so "an id" cannot quietly become "a sentence".
_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

# A prompt-template id: lowercase slug. Templates are declared in code,
# never supplied by a student, and this keeps a bad one a 422 rather
# than a mystery downstream.
_TEMPLATE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# `record_values` keys are `<record_id>.<field_name>` — see
# `OutboundPayload`'s validator for why the namespacing is the whole
# point rather than a formatting preference.
_RECORD_VALUE_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<record_id>[A-Za-z0-9][A-Za-z0-9._:-]{0,127})\.(?P<field>[a-z][a-z0-9_]{0,63})$"
)


class AIAnswerStatus(StrEnum):
    """Every way an Ask BCION request can end. Exactly six, no default.

    - `answered` — pass one selected records, pass two confirmed them,
      code validation passed, and `Answer.sentences` is populated. The
      ONLY status that ever carries sentences.
    - `not_available` — no published record exists for what was asked.
      Mirrors `app.data.models.TrustLabel.not_available`. The provider
      is never called; there is nothing to ground on.
    - `insufficient_information` — records existed but no verified,
      fully-grounded answer survived the two passes plus validation.
      Mirrors `app.data.models.EligibilityOutcome.insufficient_information`.
    - `ai_unavailable` — the provider failed (timeout, transport error,
      malformed response after retries, or not configured at all). A
      system fault, not a statement about the student's question, and
      must never be rendered with the same copy as the two above.
    - `budget_exhausted` — the spend cap in `docs/SECURITY.md` was
      already reached. Distinct from `ai_unavailable` because it is
      expected, self-healing and an operator signal, not an incident.
    - `unsupported_template` — the requested `template_id` is not in the
      registry, or the record id the template requires was not supplied.
    """

    answered = "answered"
    not_available = "not_available"
    insufficient_information = "insufficient_information"
    ai_unavailable = "ai_unavailable"
    budget_exhausted = "budget_exhausted"
    unsupported_template = "unsupported_template"


class PromptTemplateRequirement(StrEnum):
    """The one record id a prompt template cannot run without.

    Each template answers a question about exactly one kind of thing, so
    "which id must be present" is a single value rather than a set — a
    template that needed two ids would be two templates.
    """

    pathway_id = "pathway_id"
    career_id = "career_id"
    claim_id = "claim_id"
    plan_id = "plan_id"


# --------------------------------------------------------------------------
# Banned phrases
# --------------------------------------------------------------------------

#: Phrases that must never appear in a sentence a student reads.
#:
#: Two families, both from CLAUDE.md's non-negotiables. **Hedges**
#: (`maybe`, `probably`, `शायद`, `ho sakta hai`, ...) are banned because
#: this product's answers are either grounded in a verified record or
#: withheld — a hedge is the linguistic form of guessing, and if a
#: sentence needs one it should have been `insufficient_information`
#: instead. **Guarantee, ranking and personality language** (`guarantee`,
#: `not suited`, `personality type`, `pakka milega`, ...) is banned
#: outright: "no rank predictions, no 'you are not suited', no
#: personality-type labels, no guarantees."
#:
#: Matching is **case-insensitive substring** (see
#: `find_banned_phrases`), which is why every entry is stored lowercase.
#: Substring rather than word-boundary matching is deliberate: it is the
#: more aggressive direction, and a false positive here costs a rewritten
#: sentence while a false negative costs a student a guess dressed up as
#: a fact.
#:
#: **This tuple is append-only.** AI-6's output guard and AI-9's eval set
#: both import it; removing an entry silently weakens a check neither of
#: them re-states. Add, never delete, never reorder destructively.
BANNED_PHRASES: Final[tuple[str, ...]] = (
    # --- English hedges ---
    "maybe",
    "probably",
    "might",
    "may be",
    "likely",
    "perhaps",
    "i think",
    "i believe",
    "should be",
    "could be",
    "it seems",
    "it appears",
    "possibly",
    "presumably",
    # --- Guarantee / ranking / personality language ---
    "guarantee",
    "guaranteed",
    "not suited",
    "you should become",
    "best choice for you",
    "you are the type",
    "personality type",
    "you will definitely",
    "certainly get",
    # --- Hindi (Devanagari) ---
    "शायद",
    "हो सकता है",
    "गारंटी",
    "संभवतः",
    "लगता है",
    # --- Hinglish (Roman-script Hindi) ---
    "ho sakta hai",
    "shayad",
    "guarantee hai",
    "pakka milega",
)


def find_banned_phrases(text: str) -> tuple[str, ...]:
    """Return every `BANNED_PHRASES` entry occurring in `text`.

    Case-insensitive substring match, in `BANNED_PHRASES` order. Empty
    tuple means clean. The text is NFC-normalised first so that a
    Devanagari phrase written with decomposed combining marks still
    matches the composed form stored in the tuple.

    Pure and side-effect free, so the guard, the eval set and the tests
    can all agree on one definition of "contains a banned phrase"
    instead of each re-implementing the loop slightly differently.
    """
    haystack = unicodedata.normalize("NFC", text).casefold()
    return tuple(phrase for phrase in BANNED_PHRASES if phrase.casefold() in haystack)


# --------------------------------------------------------------------------
# Typed errors
# --------------------------------------------------------------------------


class AIProviderError(RuntimeError):
    """Base class for every failure of the hosted provider itself.

    A caller that only wants "the provider let us down, degrade to
    `ai_unavailable`" catches this one type. The subclasses exist for
    callers that need to distinguish retry-worthy from not — they are
    never surfaced to a student, whose view of all of them is identical.
    """


class AIProviderTimeout(AIProviderError):
    """The provider did not answer inside the request deadline."""


class AIProviderQuota(AIProviderError):
    """The provider refused on quota/rate grounds (its limit, not ours).

    Distinct from this app's own spend cap, which is
    `AIAnswerStatus.budget_exhausted` and is decided before any call is
    made — this one means the call went out and came back refused.
    """


class AIProviderMalformed(AIProviderError):
    """The provider replied, but not in the shape the prompt demanded.

    Never repaired, never partially parsed, never "best effort"
    salvaged: a response that does not parse is discarded whole. Guessing
    at what a malformed response meant is exactly the invention this
    codebase refuses to do.
    """


class AINotConfigured(RuntimeError):
    """No provider is configured (missing key/model/endpoint setting).

    Deliberately NOT an `AIProviderError` — nothing failed, there is
    simply no provider. This is the normal state in local development
    and in every test run, so it must be distinguishable from a real
    outage in logs rather than inflating the incident count.
    """


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------


class PromptTemplate(BaseModel):
    """One registered Ask BCION question a student can pick from.

    Templates are the entire question surface: a student chooses one
    from a list, they never type a question. That is not a UI
    simplification, it is the reason `OutboundPayload` can have a closed
    field list at all — there is no free-typed string anywhere in the
    request for an allow-list to have to reason about.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    requires: PromptTemplateRequirement

    @field_validator("id")
    @classmethod
    def _valid_template_id(cls, value: str) -> str:
        if not _TEMPLATE_ID_RE.match(value):
            raise ValueError(f"not a valid template id: {value!r}")
        return value

    @field_validator("label")
    @classmethod
    def _non_empty_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label must not be blank")
        return stripped


#: A prompt-template registry: template id -> template. The registry
#: itself (which templates exist) is a later card's content; this is the
#: shape it must have, so the runner can be written against it now.
PromptTemplateRegistry = Mapping[str, PromptTemplate]


def _validated_id(value: str | None, *, field_name: str) -> str | None:
    """Shared id check: `None` passes through, a string must look like an
    id this codebase issues rather than like prose."""
    if value is None:
        return None
    if len(value) > MAX_ID_CHARS or not _ID_RE.match(value):
        raise ValueError(f"{field_name} is not a valid record id: {value!r}")
    return value


class AskRequest(BaseModel):
    """An inbound Ask BCION request.

    Note what is absent: there is no `question`, `text`, `prompt` or
    `notes` field. A student picks a template and the server resolves the
    records. `extra="forbid"` keeps it that way — a client that invents a
    field gets a validation error, not a silently ignored key that a
    later refactor might start honouring.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    pathway_id: str | None = None
    career_id: str | None = None
    claim_id: str | None = None
    plan_id: str | None = None
    lang: str = "en"

    @field_validator("template_id")
    @classmethod
    def _valid_template_id(cls, value: str) -> str:
        if not _TEMPLATE_ID_RE.match(value):
            raise ValueError(f"not a valid template id: {value!r}")
        return value

    @field_validator("pathway_id", "career_id", "claim_id", "plan_id")
    @classmethod
    def _valid_record_id(cls, value: str | None) -> str | None:
        return _validated_id(value, field_name="record id")

    @field_validator("lang")
    @classmethod
    def _supported_lang(cls, value: str) -> str:
        if value not in SUPPORTED_LANGS:
            raise ValueError(f"unsupported lang: {value!r} (expected one of {SUPPORTED_LANGS})")
        return value

    def record_id_for(self, template: PromptTemplate) -> str | None:
        """The id this `template` requires, or `None` if it was not
        supplied.

        `None` is what a caller turns into
        `AIAnswerStatus.unsupported_template` — the request named a real
        template but did not carry the one record it needs, so there is
        nothing to ground on and no call should be made.
        """
        record_id: str | None = getattr(self, template.requires.value)
        return record_id


class Answer(BaseModel):
    """What Ask BCION returns. Assembled by code, never by the provider.

    `sentences` is a list, not a blob, because each sentence is built
    separately from a verified record and can be dropped individually by
    the output guard without corrupting the rest.

    The `status`/`sentences` invariant below is the machine-checkable
    form of "no record -> the answer is 'not verified'": any status other
    than `answered` MUST come back with zero sentences, so there is no
    code path that can return a hedged half-answer alongside a failure
    status and have a template render it anyway.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AIAnswerStatus
    sentences: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    selection_ids: list[str] = Field(default_factory=list)
    verification_ids: list[str] = Field(default_factory=list)

    @field_validator("selection_ids", "verification_ids")
    @classmethod
    def _valid_ids(cls, value: list[str]) -> list[str]:
        for entry in value:
            _validated_id(entry, field_name="id")
        return value

    @model_validator(mode="after")
    def _check_invariants(self) -> Answer:
        if self.status is not AIAnswerStatus.answered and self.sentences:
            raise ValueError(
                f"status {self.status.value!r} must carry no sentences "
                f"(got {len(self.sentences)}); only 'answered' may"
            )
        unselected = [
            record_id for record_id in self.verification_ids if record_id not in self.selection_ids
        ]
        if unselected:
            raise ValueError(
                "verification pass may only confirm ids the selection pass chose; "
                f"not selected: {unselected}"
            )
        return self


class OutboundPayload(BaseModel):
    """The ONLY shape permitted to leave this system for a hosted model.

    Four fields, `extra="forbid"`, and a validator that ties every value
    back to an allow-listed record id. Together that is the enforceable
    version of "no free-typed text reaches the provider":

    - `template_id` — a registry key, declared in code.
    - `record_ids` — the allow-list itself: the ids the server retrieved
      and is willing to expose for this request.
    - `record_values` — the facts, keyed `<record_id>.<field_name>`. The
      namespacing is not cosmetic: it is what makes each value's
      provenance checkable, because a key whose id half is not on
      `record_ids` is rejected outright. A caller therefore cannot add a
      `"note"` or `"question"` entry, and cannot attach a value to a
      record it did not retrieve.
    - `lang` — one of `SUPPORTED_LANGS`.

    Values are additionally required to be single-line and bounded. A
    retrieved fact ("Rs 2,00,000 per year", "JEE Main") is short and has
    no line breaks; a multi-line value is the signature of pasted prose
    or an injected instruction block, so the shape check catches a whole
    class of smuggling without needing to understand the content.

    The structural rules are what the model can prove on its own.
    `untraceable_values()` closes the remaining gap for a caller that
    still holds the retrieved records: it re-checks each value against
    the actual record set, catching a value that was namespaced
    correctly but whose content does not come from that record.
    `from_records()` is the constructor that makes that impossible by
    building the payload out of the records in the first place.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    record_ids: list[str] = Field(default_factory=list)
    record_values: dict[str, str] = Field(default_factory=dict)
    lang: str = "en"

    @field_validator("template_id")
    @classmethod
    def _valid_template_id(cls, value: str) -> str:
        if not _TEMPLATE_ID_RE.match(value):
            raise ValueError(f"not a valid template id: {value!r}")
        return value

    @field_validator("lang")
    @classmethod
    def _supported_lang(cls, value: str) -> str:
        if value not in SUPPORTED_LANGS:
            raise ValueError(f"unsupported lang: {value!r} (expected one of {SUPPORTED_LANGS})")
        return value

    @field_validator("record_ids")
    @classmethod
    def _valid_record_ids(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_RECORD_IDS:
            raise ValueError(f"at most {MAX_RECORD_IDS} record ids may be sent (got {len(value)})")
        if len(set(value)) != len(value):
            raise ValueError("record_ids must not contain duplicates")
        for entry in value:
            _validated_id(entry, field_name="record_ids entry")
        return value

    @model_validator(mode="after")
    def _values_trace_to_allow_listed_records(self) -> OutboundPayload:
        allow_listed = set(self.record_ids)
        for key, value in self.record_values.items():
            match = _RECORD_VALUE_KEY_RE.match(key)
            if match is None:
                raise ValueError(
                    f"record_values key {key!r} is not '<record_id>.<field_name>'; "
                    "free-typed keys are not allowed on the wire"
                )
            record_id = match.group("record_id")
            if record_id not in allow_listed:
                raise ValueError(
                    f"record_values key {key!r} names record {record_id!r}, "
                    "which is not on record_ids; every value must be traceable "
                    "to an allow-listed record"
                )
            _check_value_shape(key, value)
        return self

    def untraceable_values(self, records: Mapping[str, Mapping[str, str]]) -> tuple[str, ...]:
        """Return the `record_values` keys whose value is not present in
        `records`, i.e. did not come from an allow-listed record.

        `records` is the retrieved record set the caller actually holds:
        record id -> field name -> value. A key is untraceable if its
        record is absent from `records`, its field is absent from that
        record, or the value does not match the record's own value for
        that field.

        Empty tuple means every value on this payload is accounted for.
        Callers should assert exactly that immediately before the wire
        call; the returned keys are for logs and tests, never for a
        student.
        """
        untraceable: list[str] = []
        for key, value in self.record_values.items():
            match = _RECORD_VALUE_KEY_RE.match(key)
            if match is None:  # pragma: no cover - the validator already rejects these
                untraceable.append(key)
                continue
            record = records.get(match.group("record_id"))
            if record is None or record.get(match.group("field")) != value:
                untraceable.append(key)
        return tuple(untraceable)

    @classmethod
    def from_records(
        cls,
        *,
        template_id: str,
        records: Mapping[str, Mapping[str, str]],
        lang: str = "en",
    ) -> OutboundPayload:
        """Build a payload out of retrieved records — the supported path.

        Every outbound value is copied from `records` here, so there is
        no parameter through which free-typed text could be introduced:
        the caller supplies records, not strings. A payload built this
        way satisfies `untraceable_values(records) == ()` by
        construction.
        """
        record_ids = list(records)
        record_values = {
            f"{record_id}.{field}": value
            for record_id, fields in records.items()
            for field, value in fields.items()
        }
        return cls(
            template_id=template_id,
            record_ids=record_ids,
            record_values=record_values,
            lang=lang,
        )


def _check_value_shape(key: str, value: str) -> None:
    """Reject a `record_values` value that is not shaped like a
    retrieved fact (empty, over-long, or containing a control character
    such as a newline)."""
    if not value.strip():
        raise ValueError(f"record_values[{key!r}] must not be blank")
    if len(value) > MAX_RECORD_VALUE_CHARS:
        raise ValueError(
            f"record_values[{key!r}] is {len(value)} chars; "
            f"at most {MAX_RECORD_VALUE_CHARS} may be sent"
        )
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError(
            f"record_values[{key!r}] contains a control character; "
            "retrieved facts are single-line values, not prose blocks"
        )
