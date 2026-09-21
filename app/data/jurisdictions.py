"""Canonical Indian states/UTs and pilot-country jurisdiction codes —
SCOPE-5.

A static reference table, not a "which states/countries does the trial
cover" claim: docs/CONTRACTS.md's "Entity vocabulary" section explicitly
leaves that scope-phasing question (SCOPE-1) open and forbids hardcoding
a *covered* set anywhere. This module does something narrower and
already-settled — it enumerates the complete, exhaustive ISO 3166-2:IN
list of all 36 Indian states/union territories (every one of them, not a
subset) plus the countries the content track has already started
drafting pilot research for (`docs/content-drafts/foreign-pathway-*.md`),
purely so a domicile value — from a claim or a student — can be resolved
to one unambiguous code. Whether a given jurisdiction actually has any
*published, verified* facts is a completely separate question, answered
by the claims table, never by this module (docs/CONTRACTS.md's
"coverage" rule: absence of a published claim reads "not verified yet").

Both ISO 3166-1 alpha-2 (country) and ISO 3166-2 (`IN-XX` subdivision)
codes are "jurisdiction" values per docs/CONTRACTS.md's "Entity
vocabulary" section — this module is the one place either kind is
resolved from free text/aliases, for both the Requirements screen's
`<select>` (SCOPE-5) and `app.rules.eligibility.domicile_in`'s claim vs.
student-input comparison.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Jurisdiction:
    code: str
    """ISO 3166-2:IN for a state/union territory (`IN-XX`), ISO 3166-1
    alpha-2 for a country (docs/CONTRACTS.md "Entity vocabulary")."""
    name: str
    """Canonical display name — always what's shown, never the code
    itself (a student picks 'Gujarat' from the select, not 'IN-GJ')."""
    kind: str
    """'state' or 'country' — lets a template group the `<select>`
    into two `<optgroup>`s without re-deriving it from the code."""


# ---------------------------------------------------------------------
# All 36 Indian states and union territories (current ISO 3166-2:IN —
# post-2019-reorganisation: Jammu and Kashmir/Ladakh split, Dadra and
# Nagar Haveli/Daman and Diu merged). Exhaustive by construction: this
# is simply "every state and UT of India", not a chosen subset, so it
# carries none of docs/CONTRACTS.md's scope-phasing ambiguity.
# ---------------------------------------------------------------------
INDIAN_STATES_AND_UTS: tuple[Jurisdiction, ...] = (
    Jurisdiction("IN-AN", "Andaman and Nicobar Islands", "state"),
    Jurisdiction("IN-AP", "Andhra Pradesh", "state"),
    Jurisdiction("IN-AR", "Arunachal Pradesh", "state"),
    Jurisdiction("IN-AS", "Assam", "state"),
    Jurisdiction("IN-BR", "Bihar", "state"),
    Jurisdiction("IN-CH", "Chandigarh", "state"),
    Jurisdiction("IN-CT", "Chhattisgarh", "state"),
    Jurisdiction("IN-DH", "Dadra and Nagar Haveli and Daman and Diu", "state"),
    Jurisdiction("IN-DL", "Delhi", "state"),
    Jurisdiction("IN-GA", "Goa", "state"),
    Jurisdiction("IN-GJ", "Gujarat", "state"),
    Jurisdiction("IN-HR", "Haryana", "state"),
    Jurisdiction("IN-HP", "Himachal Pradesh", "state"),
    Jurisdiction("IN-JH", "Jharkhand", "state"),
    Jurisdiction("IN-JK", "Jammu and Kashmir", "state"),
    Jurisdiction("IN-KA", "Karnataka", "state"),
    Jurisdiction("IN-KL", "Kerala", "state"),
    Jurisdiction("IN-LA", "Ladakh", "state"),
    Jurisdiction("IN-LD", "Lakshadweep", "state"),
    Jurisdiction("IN-MP", "Madhya Pradesh", "state"),
    Jurisdiction("IN-MH", "Maharashtra", "state"),
    Jurisdiction("IN-MN", "Manipur", "state"),
    Jurisdiction("IN-ML", "Meghalaya", "state"),
    Jurisdiction("IN-MZ", "Mizoram", "state"),
    Jurisdiction("IN-NL", "Nagaland", "state"),
    Jurisdiction("IN-OR", "Odisha", "state"),
    Jurisdiction("IN-PY", "Puducherry", "state"),
    Jurisdiction("IN-PB", "Punjab", "state"),
    Jurisdiction("IN-RJ", "Rajasthan", "state"),
    Jurisdiction("IN-SK", "Sikkim", "state"),
    Jurisdiction("IN-TN", "Tamil Nadu", "state"),
    Jurisdiction("IN-TG", "Telangana", "state"),
    Jurisdiction("IN-TR", "Tripura", "state"),
    Jurisdiction("IN-UP", "Uttar Pradesh", "state"),
    Jurisdiction("IN-UT", "Uttarakhand", "state"),
    Jurisdiction("IN-WB", "West Bengal", "state"),
)

# ---------------------------------------------------------------------
# Pilot countries — exactly the ones the content track has already
# drafted research for (docs/content-drafts/foreign-pathway-*.md file
# names, checked 2026-09-21: singapore, uae, uk, australia, canada,
# france, germany, ireland, japan, netherlands, new-zealand). Not this
# module's call which countries the pilot "covers" (SCOPE-1, still
# open) — only which ones already have a source file to resolve a code
# for; docs/CONTRACTS.md: "Fields on a non-IN pathway are display-only
# ... never fed to the eligibility engine or into a total."
# ---------------------------------------------------------------------
PILOT_COUNTRIES: tuple[Jurisdiction, ...] = (
    Jurisdiction("AU", "Australia", "country"),
    Jurisdiction("CA", "Canada", "country"),
    Jurisdiction("FR", "France", "country"),
    Jurisdiction("DE", "Germany", "country"),
    Jurisdiction("IE", "Ireland", "country"),
    Jurisdiction("JP", "Japan", "country"),
    Jurisdiction("NL", "Netherlands", "country"),
    Jurisdiction("NZ", "New Zealand", "country"),
    Jurisdiction("SG", "Singapore", "country"),
    Jurisdiction("AE", "United Arab Emirates", "country"),
    Jurisdiction("GB", "United Kingdom", "country"),
)

ALL_JURISDICTIONS: tuple[Jurisdiction, ...] = INDIAN_STATES_AND_UTS + PILOT_COUNTRIES

_BY_CODE: dict[str, Jurisdiction] = {j.code.lower(): j for j in ALL_JURISDICTIONS}
_BY_NAME: dict[str, Jurisdiction] = {j.name.lower(): j for j in ALL_JURISDICTIONS}

# Common aliases/older names/abbreviations that are not the canonical
# display name above -- resolved to the same code. Not exhaustive (this
# is free text with no dropdown history), just the plausible ones a
# claim author or a student is likely to type.
_ALIASES: dict[str, str] = {
    "nct of delhi": "IN-DL",
    "national capital territory of delhi": "IN-DL",
    "new delhi": "IN-DL",
    "orissa": "IN-OR",
    "pondicherry": "IN-PY",
    "uttaranchal": "IN-UT",
    "jammu & kashmir": "IN-JK",
    "j&k": "IN-JK",
    "andaman & nicobar islands": "IN-AN",
    "dadra & nagar haveli and daman & diu": "IN-DH",
    "dadra and nagar haveli": "IN-DH",
    "daman and diu": "IN-DH",
    "uae": "AE",
    "united arab emirates": "AE",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "britain": "GB",
}


def resolve_jurisdiction(raw: str | None) -> str | None:
    """Resolve free text (a code, a canonical name or a known alias) to
    a canonical jurisdiction code, or `None` if it isn't recognised.

    Case- and whitespace-insensitive throughout — the same tolerance
    `app.rules.eligibility.domicile_in` already gave a bare state name
    before this module existed. `None` (never a guess, never an
    exception) is deliberate: the caller decides what an unresolved
    value means, and `domicile_in` treats it as
    `insufficient_information`, not `does_not_meet` (Build Pack §6 /
    docs/CONTRACTS.md's three-outcomes rule — an unrecognised domicile
    is unknown, not a rejection).
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    lowered = text.lower()
    if match := _BY_CODE.get(lowered):
        return match.code
    if match := _BY_NAME.get(lowered):
        return match.code
    return _ALIASES.get(lowered)
