# Data — BCION Lite

Source: `docs/BCION-DPR-v1.1.md` Annex C.2/C.3, Section 10 (national DPR),
Annex D's trust labels. This is the authoritative claims model for Lite.

## Core principle
A fact without provenance cannot be published. "Last fetched" is never
displayed as "verified." A changed source is not automatically a changed
rule (a human decides whether the source change is a rule change).

## Entities (Lite subset of the national taxonomy, DPR §10)
`Career`, `Pathway`, `Exam`, `ExamCycle`, `Institution`, `Programme`,
`Scholarship`, `Source`, `Claim`, `Consent`, `StudentProfile`.

## Claims table (the provenance mechanism)
Every fact-bearing field is backed by a row here, not embedded loose in the
entity table:
- `id`, `entity_type`, `entity_id`, `field`
- `value` (typed)
- `source_id` → `Source` (official URL, authority name)
- `verification_date`, `verifier` (person, never "AI")
- `status`: `draft` → `in_review` → `published` → `superseded`
- `review_due_date`
- `superseded_by` (claim id, nullable) — history is never deleted, only
  superseded
- `approved_draft_version` — approval is bound to the **exact** draft
  version; any edit after approval invalidates it and returns the claim to
  `in_review`

## Trust label ↔ claim status mapping (feeds `docs/UI.md`)
| UI label | Claim condition |
| --- | --- |
| Checked against official source | `published`, `source.type = official`, within freshness SLA |
| Institution-reported | `published`, `source.type = institution_self_declared` |
| Estimate | Derived field, computed from other claims + stated assumptions, never itself a `Claim` row |
| Needs rechecking | `published` but `verification_date` older than the tier's SLA, or a newer conflicting extraction is `in_review` |
| Not available | No `published` claim exists for that field |

## Eligibility — three outcomes only (never four, never a probability)
`meets` · `does_not_meet` · `insufficient_information`. Never a percentage,
never "likely."

## Cost engine — three separate amounts (never merged into one figure)
`verified_charges` (from published `Claim`s) · `estimated_additional_expenses`
(explicit assumption, labelled) · `potential_assistance_not_yet_awarded`
(scholarship/loan matches not yet confirmed). Confirmed and potential
assistance are never summed into one "you'll pay" number.

## Publishing workflow (maker-checker, enforced server-side)
1. **Draft**: editor or AI-assisted extraction creates a candidate `Claim`
   (`status = draft`). An AI-authored extraction is flagged
   `extracted_by = 'ai'` and can never carry `status = published` directly.
2. **Review**: a second, different person reviews against the source.
   The author of a claim cannot approve their own claim — enforced by a DB
   constraint / RLS policy, not a UI button.
3. **Publish**: reviewer approval binds to the exact draft content
   (hash/version). Any subsequent edit invalidates the approval.
4. **Correction**: a published claim can be superseded; corrections
   invalidate caches and flag any saved student plan that used the old
   value.

## Source allowlist
Only allow-listed official sources are monitored/extracted from. Conflicting
sources are flagged and held, never silently merged.

## Freshness tiers (Lite subset of DPR §11)
| Tier | Data | Review-due cadence |
| --- | --- | --- |
| 1 Critical | Exam dates, deadlines, eligibility, fees | Short (days) |
| 2 Cycle | College fees, seats, admission routes | Per admission cycle |
| 3 Annual | Rankings/accreditation (if shown) | Annual |

## Minimisation
Quick start needs only: class, interests, language, broad location. Marks,
category, income are optional, used only for eligibility calculation,
encrypted separately, deletable at any time, never used for recommendations
beyond eligibility, never shared with institutions.

## Synthetic fixtures
Every fixture used before real content lands is prefixed/tagged so it can
never be confused with a published claim (e.g. `source.type = 'synthetic'`,
which the publishing console refuses to ever set to `published`).
