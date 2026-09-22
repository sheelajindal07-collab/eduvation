"""Comparison assembly — docs/UI.md "Comparison screen", docs/DATA.md
"Trust label <-> claim status mapping".

Pure functions only: given already-fetched Claims/Sources for a pathway
(published rows, or reviewer-visible drafts when the caller is a
reviewer — the RLS policies in db/migrations/0001_init.sql decide what a
given caller can even fetch), assemble the exact field set the Compare
screen shows. No I/O here — callers in app/api/ fetch via
app/db/client.py and pass the results in, which keeps this module fully
unit-testable without a live database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

from app.data.models import Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.rules.cost import (
    DEFAULT_CURRENCY,
    AssistanceItem,
    CostSummary,
    FeeComponent,
    Money,
    compute_cost_summary,
    sum_verified_charges,
    to_whole_rupees,
)

# Only these schemes are safe to render as a clickable evidence link
# (see `safe_source_url` below).
_SAFE_URL_SCHEMES = frozenset({"http", "https"})

# Tier-1-ish default freshness SLA for Lite, in days (docs/DATA.md S11
# scales this per tier; Lite uses one conservative default until the
# per-tier engine lands).
DEFAULT_FRESHNESS_SLA_DAYS = 180


def trust_label_for_claim(
    claim: Claim | None,
    source: Source | None,
    *,
    as_of: date,
    freshness_sla_days: int = DEFAULT_FRESHNESS_SLA_DAYS,
) -> TrustLabel:
    """docs/DATA.md's trust-label mapping table, as code.

    | UI label                         | Claim condition                                   |
    |-----------------------------------|----------------------------------------------------|
    | checked_against_official_source   | published, source.type=official, within SLA        |
    | institution_reported              | published, source.type=institution_self_declared    |
    | needs_rechecking                  | published but stale (or no source, defensively)     |
    | not_available                     | no published claim, or (defensively) a synthetic    |
    |                                    | source that should never have reached "published"   |

    "estimate" is intentionally never returned here — an estimate is a
    *derived* field computed from other claims plus a stated assumption,
    never itself backed by a single Claim row (docs/DATA.md). Callers that
    compute a derived value label it `TrustLabel.estimate` themselves.
    """
    if claim is None or claim.status != ClaimStatus.published:
        return TrustLabel.not_available
    if source is None:
        # A published claim always has a source per the schema's foreign
        # key (db/migrations/0001_init.sql) — this branch exists only so
        # the function can't silently mislabel if a caller passes
        # inconsistent data, e.g. a stale in-memory cache.
        return TrustLabel.needs_rechecking
    if source.source_type == SourceType.synthetic:
        # The DB trigger in 0001_init.sql forbids this state from ever
        # existing for real, but a unit test may still construct it —
        # never surface a synthetic-backed value as if it were a fact.
        return TrustLabel.not_available
    stale = (as_of - claim.verification_date) > timedelta(days=freshness_sla_days)
    if stale:
        return TrustLabel.needs_rechecking
    if source.source_type == SourceType.official:
        return TrustLabel.checked_against_official_source
    return TrustLabel.institution_reported


@dataclass(frozen=True)
class FieldValue:
    """One field on the comparison screen: a value plus its trust label
    and, when available, the evidence to show alongside it (docs/UI.md:
    "source authority, applicable cycle, verification date, official
    link, Report an issue" — the link/date/authority live here; the rest
    is assembled by the caller from the Source/claim it already has).

    `source_authority` was added after ux-qa-reviewer's first pass on the
    Compare screen (2026-09-19) found the HTML layer had nowhere to get
    the source's actual name from, so every evidence link rendered the
    same generic "Official source" text regardless of whether the field
    was actually `checked_against_official_source`,
    `institution_reported`, or `needs_rechecking` — three trust labels
    that exist specifically to be told apart, contradicted on the same
    line by identical link text. Additive field, existing callers
    unaffected."""

    value: str | int | float | bool | list[Any] | dict[str, Any] | None
    """Widened alongside `app.data.models.Claim.value` (RULES-3) so a
    structured claim (e.g. an any-of subject group, a per-category
    thresholds map) still type-checks all the way through
    `field_value_for` below. Every numeric consumer of `.value` already
    gates on `isinstance(value, int | float) and not isinstance(value, bool)`
    before doing arithmetic (see `_estimated_additional_expenses_hint` and
    `assemble_cost_summary` below), so a list/dict value degrades to "not
    a usable number" rather than raising -- this is a type-only widening,
    no behaviour change."""
    label: TrustLabel
    source_url: str | None = None
    verification_date: date | None = None
    source_authority: str | None = None
    currency: str | None = None
    """RULES-10 / docs/CONTRACTS.md "Money and currency": the backing
    claim's ISO 4217 currency, for a money-valued field. `None` both
    when there is no available claim (same gating as `value` etc. below)
    AND when the claim itself has a null currency — `app/rules/cost.py`
    treats the second case as "not available" too (a money claim with no
    stated currency must never be silently assumed to be INR). Additive
    field, existing non-money callers unaffected (they simply never read
    it)."""


def safe_source_url(raw_url: str | None) -> str | None:
    """Only ever return a URL that is safe to render as a clickable
    `<a href>` (app/web/templates/_trust_badge.html renders `source_url`
    directly into an anchor tag: `href="{{ fv.source_url }}"`). Jinja's
    autoescaping only HTML-entity-escapes angle brackets/quotes -- it
    does NOT block a dangerous scheme, so a `javascript:` or
    `data:text/html;...` URI in `source.official_url` would render as a
    fully clickable link framed as trustworthy evidence (security-review
    finding, 2026-09-20, reproduced live).

    Checked independently of trust label: even a genuinely published,
    official-source claim must have its URL scheme validated -- URL
    scheme safety is a separate axis from publication status, not a
    consequence of it.

    Whitespace is stripped and the scheme compared case-insensitively
    (`urlsplit` itself lowercases the scheme) so a padded or
    case-variant scheme like `"  JavaScript:alert(1)"` can't slip past a
    naive prefix check. Anything other than `http`/`https` -- some real
    Indian government sites are still http-only, so both are accepted --
    is treated exactly like "no URL at all" (`None`), the same "hide it"
    pattern already used for `not_available`, rather than raised or
    passed through unescaped.

    **Public since RULES-8** (it was `_safe_source_url`): this is now the
    ONE implementation of the check, imported by `app/api/eligibility.py`
    rather than copied there. That route used to carry its own
    `startswith(("http://", "https://"))` variant -- a strictly weaker
    test than the `urlsplit` one here, which is why the duplication was
    a live divergence and not just tidiness: the copy accepted nothing
    this one rejects, but it also had no `.strip()`, so a padded
    `" javascript:..."` was rejected there by accident rather than by
    design, and any future relaxation of one copy would silently not
    reach the other. See `docs/DECISIONS.md`'s 2026-09-20 entry, which
    recorded the two independent fixes and the reason they existed.
    """
    if not raw_url:
        return None
    stripped = raw_url.strip()
    scheme = urlsplit(stripped).scheme
    return stripped if scheme in _SAFE_URL_SCHEMES else None


_safe_source_url = safe_source_url
"""Back-compatible private alias for the now-public `safe_source_url`.

`tests/unit/test_comparison.py` imports this name directly (nine
assertions on the URL-scheme guard), and that file is outside RULES-8's
owned set -- renaming it there is a one-line change for whichever lane
next touches that test module, not a reason for this task to reach into
it. No behaviour of its own: it IS the same function object."""


def field_value_for(
    field: str,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> FieldValue:
    """Look up one field's claim (if any published claim exists for it)
    and assemble its display value with a trust label."""
    claim = claims_by_field.get(field)
    source = sources_by_id.get(claim.source_id) if claim else None
    label = trust_label_for_claim(claim, source, as_of=as_of)
    available = label != TrustLabel.not_available
    return FieldValue(
        value=claim.value if (claim and available) else None,
        label=label,
        source_url=safe_source_url(source.official_url) if (source and available) else None,
        verification_date=claim.verification_date if (claim and available) else None,
        source_authority=source.authority_name if (source and available) else None,
        currency=claim.currency if (claim and available) else None,
    )


def academic_cycle_for(
    field: str,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> str | None:
    """The admission/fee cycle label (`"2026-27"`, docs/CONTRACTS.md
    "Duration, dates, cycle, DOB") backing one field's claim, gated
    through the exact same publication check `field_value_for` already
    applies -- never a second, independently-written status test that
    could drift out of sync with it.

    `Claim.academic_cycle` is not itself part of `FieldValue` (adding it
    there would change what every existing caller of `field_value_for`
    receives, for a property only one screen needs so far: UI-5's
    pathway-detail page, the first caller to fill `_trust_badge.html`'s
    `evidence_line(... applicable_cycle=...)` slot with a real value
    instead of the literal demo string `components_gallery.html` has
    always passed it). This helper re-uses `field_value_for`'s own
    published/stale/synthetic-source decision rather than re-deriving
    it -- a claim `field_value_for` would hide must never leak its cycle
    label here either, even though the cycle itself lives on the raw
    `Claim` row this function still has to read to answer the question.

    `None` whenever `field_value_for` would say `not_available` for this
    field (no claim, draft, stale-and-sourceless, synthetic-sourced), OR
    when the published claim itself simply has no cycle
    (`Claim.academic_cycle` is `None` for a fact that is not
    cycle-scoped at all -- most fields today aren't).
    """
    fv = field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
    if fv.label == TrustLabel.not_available:
        return None
    claim = claims_by_field.get(field)
    return claim.academic_cycle if claim is not None else None


def _money_from_field_value(fv: FieldValue) -> Money | None:
    """Build a `Money` from one claim-backed `FieldValue`, applying
    docs/CONTRACTS.md's "Money and currency" rule that a money claim
    with a null currency renders not_available -- never silently
    assumed to be INR, which would invent a fact about a real fee
    (`app/data/models.py`'s `Claim.currency` docstring). A claim already
    `not_available` (unpublished, stale-and-sourceless, synthetic, ...)
    has `fv.value is None` by the time it reaches here, so that case
    falls out of the numeric check below without a separate label test.

    `None` when there is no usable numeric value or no currency -- each
    caller below decides what "no known amount" means for its own
    output: `Money(amount=0)` for an estimate with no hint at all,
    an omitted `AssistanceItem` for potential assistance that should
    simply not exist.
    """
    if (
        isinstance(fv.value, int | float)
        and not isinstance(fv.value, bool)
        and fv.currency is not None
    ):
        return Money(amount=to_whole_rupees(fv.value), currency=fv.currency)
    return None


def _money_field_value(
    field: str,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> FieldValue:
    """`field_value_for`, plus docs/CONTRACTS.md's currency rule for a
    field that holds MONEY: "a money claim with a null currency renders
    `not_available`".

    Without this, a published fee claim whose `currency` column was
    never filled in (the state of every claim written before
    db/migrations/0008_jurisdiction_currency.sql) rendered its number
    under a confident "Checked against official source" badge while the
    arithmetic layer -- which has applied this rule since RULES-10 --
    correctly refused to use it, so the computed total said "not
    available" right beside it (SCOPE-4; pinned until now by
    tests/db/test_api_explore_compare.py's null-currency test). A
    student cannot read that; it looks like the site is broken, or worse,
    like the fee is trustworthy and the total is not.

    Degrades to exactly the shape `field_value_for` returns for a
    missing claim -- no value, no evidence line -- because "we cannot
    say what this amount is" is the same answer either way, and showing
    an official link beside a withheld number would imply the number is
    published and merely hidden.
    """
    fv = field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
    if fv.label == TrustLabel.not_available or _money_from_field_value(fv) is not None:
        return fv
    if isinstance(fv.value, int | float) and not isinstance(fv.value, bool):
        return FieldValue(value=None, label=TrustLabel.not_available)
    # A non-numeric value on a money field (a range string, a structured
    # claim) is not this function's business -- it carries no currency to
    # check and is left exactly as `field_value_for` built it.
    return fv


def _charges_currency(components: list[FeeComponent]) -> str | None:
    """The one currency this pathway's verified charges are published
    in, or `None` when that is not a single known answer (no usable
    component, or components in more than one currency).

    SCOPE-4: an amount with no claim of its own -- a stated assumption,
    a student's typed-in override -- still has to be labelled with SOME
    currency before it can be shown or added, and the only non-inventing
    answer available is "the same currency this pathway's fees are
    published in". `None` here means the caller falls back to
    `DEFAULT_CURRENCY`, which is what an India-first pilot with no
    currency-selection UI means by "unspecified" (docs/CONTRACTS.md).
    """
    currencies = {
        money.currency
        for money in (_money_from_field_value(c.field_value) for c in components)
        if money is not None
    }
    return currencies.pop() if len(currencies) == 1 else None


@dataclass(frozen=True)
class ProgrammeCostBreakdown:
    """Three separate amounts — NEVER merged into one figure (docs/UI.md
    "Timeline and cost"; docs/DATA.md "Cost engine")."""

    verified_charges: FieldValue
    estimated_additional_expenses: FieldValue
    potential_assistance_not_yet_awarded: FieldValue


def _estimated_additional_expenses_hint(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> Money | None:
    """The "estimated_additional_expenses_hint" claim as `Money`, run
    through the same field_value_for() published/synthetic/freshness
    checks every other field gets — not a raw dict lookup. A hint claim
    still stuck in draft, or backed by a synthetic source, must never
    leak its value into a real cost figure just because this field is
    presentation-labelled TrustLabel.estimate downstream; that would let
    an unapproved number reach a published result, which CLAUDE.md's
    maker-checker rule forbids for every field, not just the ones that
    read as "facts". Returns None when there is no usable hint (no
    claim, unpublished, synthetic, or — SCOPE-4 — published with no
    currency) — the caller decides what "no hint" means for its own
    output.

    Rounded to whole rupees by `Money` itself (RULES-10:
    `app/rules/cost.py`'s `to_whole_rupees`) — a claim occasionally
    quotes a paise-level fraction, and every amount downstream is typed
    as a whole-unit `int`.

    Currency-gated via `_money_from_field_value` since SCOPE-4: this
    helper feeds BOTH `assemble_cost_breakdown`'s displayed line and
    `assemble_cost_summary`'s arithmetic, so the number on screen and
    the number in the total can no longer disagree about whether a
    hint counts (it used to be deliberately ungated, which showed a
    null-currency hint's figure on screen while the total ignored it).
    """
    hint = field_value_for(
        "estimated_additional_expenses_hint", claims_by_field, sources_by_id, as_of=as_of
    )
    return _money_from_field_value(hint)


def _additional_expenses(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
    override: float | None,
    charges_currency: str | None,
) -> tuple[Money, Money | None]:
    """`(computed estimate, this request's override or None)` — the two
    additional-expenses figures, derived ONCE for both the displayed
    line (`assemble_cost_breakdown`) and the arithmetic
    (`assemble_cost_summary`). Deriving them twice is how a screen ends
    up showing one assumption beside a total computed from another.

    The estimate is the published hint, or zero ("assume nothing
    extra"). SCOPE-4 — currency: the override and the zero have no claim
    of their own, so they inherit `charges_currency` (falling back to
    `DEFAULT_CURRENCY`). Before this, both were hard-coded INR, which
    silently turned every non-INR pathway's total into "mixed
    currencies" — a GBP fee plus a ₹0 assumption cannot be added, so a
    perfectly ordinary all-GBP pathway showed no total at all and blamed
    a currency mix the student never created. A published hint keeps its
    OWN currency (a claim states its own facts); if that genuinely
    differs from the charges', `net_to_arrange` still nulls out, which
    is now a real mismatch rather than an artefact of the default.
    """
    hint = _estimated_additional_expenses_hint(claims_by_field, sources_by_id, as_of=as_of)
    estimate = (
        hint if hint is not None else Money(amount=0, currency=charges_currency or DEFAULT_CURRENCY)
    )
    override_money = (
        Money(amount=to_whole_rupees(override), currency=charges_currency or DEFAULT_CURRENCY)
        if override is not None
        else None
    )
    return estimate, override_money


def _verified_charges_field_value(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    fee_components: list[FeeComponent],
    *,
    as_of: date,
) -> FieldValue:
    """The "Verified charges" display line — must always agree with
    whatever `sum_verified_charges(fee_components)` actually summed,
    since that is the exact call `assemble_cost_summary` feeds
    `net_to_arrange` from (`fee_components` here is the same list, built
    by the same `_fee_components` call, over the same claims/sources/
    as_of the caller passes to both functions).

    Before this, this line was always read straight off the single
    legacy "verified_charges" claim, regardless of whether the pathway
    actually used it. A pathway published with only itemised
    "fee_component:*" claims and no legacy claim then showed this line
    as "Not available" while `net_to_arrange` right below it, correctly,
    summed the components anyway — the total worked but its own main
    input claimed to be missing (docs/DECISIONS.md 2026-09-22, "known
    follow-up").

    No itemised "fee_component:*" FIELD exists at all (regardless of
    publish status — the same selection rule `_fee_components` itself
    uses) -> the single legacy claim, read exactly as before via
    `_money_field_value`: full evidence (source, date, authority), and a
    non-numeric value passed through as text, unchanged.

    One or more itemised fields exist -> the components are the more
    current source of truth (matching `_fee_components`'s own "itemised
    wins" rule), so this becomes a genuinely computed figure with no
    single backing claim — same shape as `estimated_additional_expenses`
    below: a value plus a trust label and currency, no source_url/
    verification_date/source_authority, since no ONE evidence link can
    honestly represent a sum of several claims that may each cite a
    different source. `not_available` exactly when
    `sum_verified_charges` itself gives `total=None` (a missing/
    unpublished component, or components that don't share a currency) —
    this line and the total below it can now never again disagree about
    whether the charges are known.

    Label: `needs_rechecking` when any included component is stale
    (matching `VerifiedChargesResult.stale`); else
    `checked_against_official_source` only when EVERY included
    component is — one institution-reported component among otherwise-
    official ones downgrades the whole sum to `institution_reported`,
    since a combined figure cannot honestly claim a stronger trust level
    than its weakest input.
    """
    has_itemised_fields = any(
        field.startswith(_FEE_COMPONENT_FIELD_PREFIX) for field in claims_by_field
    )
    if not has_itemised_fields:
        return _money_field_value(
            "verified_charges", claims_by_field, sources_by_id, as_of=as_of
        )

    result = sum_verified_charges(fee_components)
    if result.total is None:
        return FieldValue(value=None, label=TrustLabel.not_available)

    all_official = all(
        component.field_value.label == TrustLabel.checked_against_official_source
        for component in fee_components
    )
    label = (
        TrustLabel.needs_rechecking
        if result.stale
        else TrustLabel.checked_against_official_source
        if all_official
        else TrustLabel.institution_reported
    )
    return FieldValue(value=result.total.amount, label=label, currency=result.total.currency)


def assemble_cost_breakdown(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
    estimated_additional_expenses_override: float | None = None,
) -> ProgrammeCostBreakdown:
    """Assemble the three-amount cost display for one programme/pathway.

    "verified_charges" reflects itemised "fee_component:*" claims when
    the pathway publishes any, falling back to the single legacy
    "verified_charges" claim otherwise — see
    `_verified_charges_field_value`, which guarantees this line always
    agrees with what `assemble_cost_summary` actually totals.
    "potential_assistance_not_yet_awarded" is read through
    `_money_field_value` directly, so a money claim with no stated
    currency shows as not_available instead of as a confidently-badged
    number the total refuses to use (SCOPE-4).
    "estimated_additional_expenses" is always an estimate: it is computed
    from stated assumptions, never backed by a single Claim, so it is
    assembled directly as a TrustLabel.estimate FieldValue rather than
    looked up.

    No usable hint claim -> 0 ("assume nothing extra"), the same default
    assemble_cost_summary uses for net_to_arrange below — so the line
    item shown here always matches what the total was actually computed
    from, instead of showing a blank next to a total that silently
    assumed zero. `estimated_additional_expenses_override` is the same
    per-request assumption `assemble_cost_summary` takes, accepted here
    for the same reason: with an override in play the total is computed
    from the student's figure, so the line above it must show the
    student's figure too.

    Every money line carries the currency it is denominated in
    (`FieldValue.currency`), so the display layer can format it with
    `format_money` and never has to assume rupees.
    """
    fee_components = _fee_components(claims_by_field, sources_by_id, as_of=as_of)
    charges_currency = _charges_currency(fee_components)
    computed_estimate, override = _additional_expenses(
        claims_by_field,
        sources_by_id,
        as_of=as_of,
        override=estimated_additional_expenses_override,
        charges_currency=charges_currency,
    )
    # Exactly what `CostSummary.effective_additional_expenses` picks for
    # the arithmetic (app/rules/cost.py) -- the displayed line and the
    # total are the same figure by construction, not by coincidence.
    estimate = override if override is not None else computed_estimate

    return ProgrammeCostBreakdown(
        verified_charges=_verified_charges_field_value(
            claims_by_field, sources_by_id, fee_components, as_of=as_of
        ),
        estimated_additional_expenses=FieldValue(
            value=estimate.amount, label=TrustLabel.estimate, currency=estimate.currency
        ),
        potential_assistance_not_yet_awarded=_money_field_value(
            "potential_assistance_not_yet_awarded", claims_by_field, sources_by_id, as_of=as_of
        ),
    )


_FEE_COMPONENT_FIELD_PREFIX = "fee_component:"
"""RULES-10: a pathway may publish any number of itemised fee-component
claims (`"fee_component:tuition"`, `"fee_component:hostel"`, ...) instead
of (or, transitionally, as well as) the single `"verified_charges"`
claim `assemble_cost_summary` originally summed alone. The prefix is a
plain string convention rather than a new column — content authoring
picks the claim field name, this module just recognises the prefix."""


def _fee_component_display_name(field: str) -> str:
    """`"fee_component:exam_fee"` -> `"Exam fee"` — the line-item label
    shown next to each itemised charge. Falls back to a generic label
    for the degenerate `"fee_component:"` (empty suffix) case rather
    than showing a blank line item."""
    suffix = field[len(_FEE_COMPONENT_FIELD_PREFIX) :].replace("_", " ").replace("-", " ").strip()
    return suffix.capitalize() if suffix else "Fee component"


def _fee_components(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> list[FeeComponent]:
    """Every published `fee_component:*` claim on this pathway, each
    independently trust-labelled via `field_value_for` — never a raw
    dict lookup, so a draft, stale or synthetic-sourced component is
    handled by the exact same "missing -> None total" rule as everything
    else in this module. Falls back to the single legacy
    `"verified_charges"` claim when no itemised component exists at all,
    so a pathway published before RULES-10 keeps working unchanged
    (docs/DATA.md "Cost engine" is still the source of truth on the
    charges; this function only decides which claim field(s) to read
    them from).

    Sorted by field name for a deterministic component order — itemised
    fee components have no other ordering signal yet (a future
    content-workflow task may add one); alphabetical is at least stable
    across requests and tests.
    """
    fee_component_fields = sorted(
        field for field in claims_by_field if field.startswith(_FEE_COMPONENT_FIELD_PREFIX)
    )
    if not fee_component_fields:
        verified = field_value_for("verified_charges", claims_by_field, sources_by_id, as_of=as_of)
        return [FeeComponent(name="Verified charges", field_value=verified)]

    return [
        FeeComponent(
            name=_fee_component_display_name(field),
            field_value=field_value_for(field, claims_by_field, sources_by_id, as_of=as_of),
        )
        for field in fee_component_fields
    ]


def assemble_cost_summary(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
    estimated_additional_expenses_override: float | None = None,
) -> CostSummary:
    """Run `app/rules/cost.py`'s real arithmetic (including `net_to_arrange`)
    over the same claims `assemble_cost_breakdown` already displays.

    `verified_charges` is summed from every published `fee_component:*`
    claim on the pathway (`_fee_components` above), falling back to the
    single legacy `"verified_charges"` claim when no itemised component
    exists — either way it goes through the SAME `sum_verified_charges`
    call, so the "one missing component -> total is None, never a
    partial sum" guarantee `cost.py` already proves applies to the live
    figure too, now for as many components as a pathway actually
    publishes, in whatever currency each component's claim states
    (docs/CONTRACTS.md "Money and currency" — mixed currencies among
    components also null out the total, distinguishably; see
    `VerifiedChargesResult.mixed_currencies`).

    `estimated_additional_expenses_override` is the "assumption editing"
    Build Pack §6/docs/UI.md call for: a caller-supplied value for this
    one request only — never persisted, never a Claim. There is no
    currency-selection UI for a student's own typed-in assumption, so it
    is denominated in the currency this pathway's own charges are
    published in (`_charges_currency`, falling back to
    `DEFAULT_CURRENCY`) — SCOPE-4. Treating it as INR regardless, as it
    was before, made every non-INR pathway's total unavailable-with-a-
    currency-mismatch the moment a student edited the assumption, which
    reads as a broken site rather than as the deliberate no-FX rule it
    was meant to express; the amount is displayed with that currency
    beside it (`assemble_cost_breakdown`), so what was assumed is on
    screen rather than implied.

    Unlike the original wiring, the override no longer replaces the
    computed estimate outright: `CostSummary.estimated_additional_expenses`
    always stays the figure this function actually computed (the
    published hint, or a zero when there is none), and the override
    is carried separately as `CostSummary.additional_expenses_override`,
    so a caller/template can show BOTH "our estimate" and "your
    assumption" rather than one silently clobbering the other.
    `net_to_arrange`'s arithmetic still uses the override when one is
    supplied (`CostSummary.effective_additional_expenses` — see
    `app/rules/cost.py`), so the total a student sees continues to
    reflect their own edit exactly as before; only the two *displayed*
    lines are now distinct.

    `potential_assistance_not_yet_awarded` becomes at most one
    `AssistanceItem` — omitted entirely (not zero) when the claim is
    `not_available` OR has no usable currency, since "no known potential
    assistance" and "assumed zero potential assistance" are different
    facts. There is no `confirmed_assistance` source yet (that is
    student-specific award data, which does not exist before the M3
    sign-in/consent work), so it is always empty here — `net_to_arrange`
    correctly reduces to verified + effective additional expenses with
    nothing confirmed subtracted. Even once a source exists, it must
    only ever be a per-request input to this function, never read from
    or written to storage here — this module does no I/O at all (see
    module docstring).
    """
    fee_components = _fee_components(claims_by_field, sources_by_id, as_of=as_of)
    charges_currency = _charges_currency(fee_components)

    estimated_additional_expenses, additional_expenses_override = _additional_expenses(
        claims_by_field,
        sources_by_id,
        as_of=as_of,
        override=estimated_additional_expenses_override,
        charges_currency=charges_currency,
    )

    potential = field_value_for(
        "potential_assistance_not_yet_awarded", claims_by_field, sources_by_id, as_of=as_of
    )
    potential_money = _money_from_field_value(potential)
    potential_assistance = (
        [AssistanceItem(name="Potential assistance", amount=potential_money)]
        if potential_money is not None
        else []
    )

    return compute_cost_summary(
        fee_components=fee_components,
        estimated_additional_expenses=estimated_additional_expenses,
        confirmed_assistance=[],
        potential_assistance=potential_assistance,
        additional_expenses_override=additional_expenses_override,
    )
