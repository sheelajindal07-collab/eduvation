# Trial-subset curation checklist (CONTENT-5, dev part)

This is a **structure for the editor to fill in**, not a decision about
which pathways are in the trial. It does not select, verify or claim any
fact — every cell an editor has not yet filled says "not yet checked."

Built from `docs/content-drafts/INVENTORY.md` (CONTENT-3's real,
generated draft-file counts), which tells us what research material
already exists and how much of it is high-confidence -- it does not tell
us what is true, and it is not itself a source.

**Scope reminder (docs/CONTRACTS.md, "Scope phasing is NOT frozen
here"):** which states and countries the trial actually verifies is
SCOPE-1, still with the owner. Nothing in this checklist is a covered-set
list -- every row below is a *candidate* drawn from what has draft
research, not a commitment. Do not copy any row of this table into code,
fixtures or UI copy as "the trial subset" before SCOPE-1 is answered and
CONTENT-1 confirms the trial subset.

CONTENT-5's actual output, `content/curation/trial_subset.csv`, is a
separate, later, mixed (agent + editor) deliverable in the contract's
typed-row format -- not this file. This checklist exists to help the
editor decide, family by family, which of the ~100-130 rows CONTENT-5
budgets for should go toward a deadline, a backup route or a scholarship,
before that CSV is built.

## How to use this checklist

For each candidate pathway family below, the editor marks:

1. **Deadline sourced?** -- Is there (or can there be) a verified
   application/exam-cycle deadline claim (Tier 1, `docs/DATA.md`) for
   this family, with an allow-listed source and a verbatim quote?
2. **Backup route identified?** -- Per `docs/CONTRACTS.md`'s entity
   vocabulary, a backup is a `pathway_transition` row (from stage, to
   stage, transition type), never a second pathway or free text. Has one
   been identified and sourced for this family?
3. **Scholarship attached?** -- Is there at least one scholarship this
   family's students are plausibly eligible for, with its own sourced
   claim?
4. **Eligibility set complete or excluded?** -- Per CONTENT-5's
   acceptance criterion, a pathway's eligibility set publishes complete
   or not at all (see `docs/DATA.md` "A pathway with no published rules
   returns insufficient_information"). Mark "complete", "excluded (not
   this batch)" or "not yet checked" -- never a partial set.
5. **High-confidence rows available** is pre-filled from INVENTORY.md as
   a prioritisation aid only (more high-confidence draft rows makes a
   family cheaper to source-check first) -- it is not evidence of
   anything published.

A row with no editor entries yet is exactly that: not started. Do not
infer coverage from an empty checklist.

## Exam-eligibility families (candidates; `docs/content-drafts/*-eligibility.md`)

| Family (exam) | Draft file(s) | High-confidence rows (INVENTORY.md) | Deadline sourced? | Backup route identified? | Scholarship attached? | Eligibility set complete or excluded? | Editor notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AFCAT | `afcat-eligibility.md` | 34 | not yet checked | not yet checked | not yet checked | not yet checked | |
| CAT (MBA) | `cat-mba-eligibility.md` | 23 | not yet checked | not yet checked | not yet checked | not yet checked | |
| CDS | `cds-eligibility.md` | 24 | not yet checked | not yet checked | not yet checked | not yet checked | |
| CLAT | `clat-eligibility.md` | 18 | not yet checked | not yet checked | not yet checked | not yet checked | |
| CMAT | `cmat-eligibility.md` | 24 | not yet checked | not yet checked | not yet checked | not yet checked | |
| CUET-UG | `cuet-ug-eligibility.md` | 6 | not yet checked | not yet checked | not yet checked | not yet checked | Low high-confidence count -- expect more sourcing work |
| GUJCET | `gujcet-eligibility.md` | 0 (narrative format, no '---' front-matter) | not yet checked | not yet checked | not yet checked | not yet checked | Non-tabular draft; re-extract before curating |
| IBPS PO | `ibps-po-eligibility.md` | 0 (26 medium) | not yet checked | not yet checked | not yet checked | not yet checked | No high-confidence rows yet |
| ICAR AIEEA | `icar-aieea-eligibility.md` | 24 | not yet checked | not yet checked | not yet checked | not yet checked | |
| JEE Advanced | `jee-advanced-eligibility.md` | 8 (8 medium) | not yet checked | not yet checked | not yet checked | not yet checked | |
| JEE Main | `jee-main-eligibility.md` | 20 | not yet checked | not yet checked | not yet checked | not yet checked | 2027-cycle bulletin still pending per docs/plan gap note -- do not roll 2026 figures forward |
| NATA | `nata-eligibility.md` | 27 | not yet checked | not yet checked | not yet checked | not yet checked | |
| NDA | `nda-eligibility.md` | 24 | not yet checked | not yet checked | not yet checked | not yet checked | |
| NEET-UG | `neet-ug-eligibility.md` | 0 (narrative format, no '---' front-matter) | not yet checked | not yet checked | not yet checked | not yet checked | Non-tabular draft; NEET eligibility stays unpublished until the rules engine handles DOB cutoffs and OR-subjects (docs/plan open question) |
| SSC CGL | `ssc-cgl-eligibility.md` | 31 | not yet checked | not yet checked | not yet checked | not yet checked | |
| UCEED | `uceed-eligibility.md` | 15 (11 medium) | not yet checked | not yet checked | not yet checked | not yet checked | |
| XAT | `xat-eligibility.md` | 9 (18 medium) | not yet checked | not yet checked | not yet checked | not yet checked | |

## Foreign-pathway families (candidates; `docs/content-drafts/foreign-pathway-*.md`)

Per the open-question recommended default in
`docs/plan/inventory-2-trust-content.md`: for a foreign fact, "official"
means the destination government's immigration/education domain or the
institution's own domain only; aggregators, British Council and
Study-in-X portals are leads, never the cited source.

| Family (destination) | Draft file | High-confidence rows (INVENTORY.md) | Deadline sourced? | Backup route identified? | Scholarship attached? | Eligibility set complete or excluded? | Editor notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Australia | `foreign-pathway-australia.md` | 15 | not yet checked | not yet checked | not yet checked | not yet checked | |
| Canada | `foreign-pathway-canada.md` | 17 | not yet checked | not yet checked | not yet checked | not yet checked | |
| France | `foreign-pathway-france.md` | 24 | not yet checked | not yet checked | not yet checked | not yet checked | |
| Germany | `foreign-pathway-germany.md` | 8 (8 medium) | not yet checked | not yet checked | not yet checked | not yet checked | |
| Ireland | `foreign-pathway-ireland.md` | 17 | not yet checked | not yet checked | not yet checked | not yet checked | |
| Japan | `foreign-pathway-japan.md` | 24 | not yet checked | not yet checked | not yet checked | not yet checked | |
| Netherlands | `foreign-pathway-netherlands.md` | 7 (10 medium) | not yet checked | not yet checked | not yet checked | not yet checked | Lower high-confidence count |
| New Zealand | `foreign-pathway-new-zealand.md` | 11 | not yet checked | not yet checked | not yet checked | not yet checked | |
| Singapore | `foreign-pathway-singapore.md` | 14 (8 medium) | not yet checked | not yet checked | not yet checked | not yet checked | |
| UAE | `foreign-pathway-uae.md` | 8 (9 medium) | not yet checked | not yet checked | not yet checked | not yet checked | |
| UK | `foreign-pathway-uk.md` | 12 | not yet checked | not yet checked | not yet checked | not yet checked | UK draft's tuition figures are flagged British-Council-sourced in the plan's own risk note -- expect this to be dropped or re-sourced under the official-domain-only rule |

`foreign-pathways-comparison-summary.md` has 0 fact-table rows (narrative
synthesis only, per INVENTORY.md) -- not a candidate family on its own.

## State/UT and scholarship material (not itemised per-family here)

INVENTORY.md's States/UTs area (64 files, 1,255 fact rows) and
Scholarships area (16 files, 488 fact rows) are jurisdiction-scoped
admission rules and national/state scholarship schemes rather than
distinct "pathway families" with their own deadline/backup/scholarship
triad -- they instead supply the deadline and scholarship evidence the
exam and foreign-pathway families above need, and are themselves gated
by SCOPE-1 (which states are in the trial). Per-state curation is
deferred to a future CONTENT-5 pass once SCOPE-1 names the covered
states; listing all 36 states/UTs here now would look like a covered-set
commitment this document must not make.

## Summary counts (from INVENTORY.md, for prioritisation only)

| Area | Candidate families listed above | Total draft files | High-confidence fact rows |
| --- | --- | --- | --- |
| Exams (eligibility) | 17 | 17 | 287 |
| Foreign pathways | 11 (+1 non-family summary file) | 12 | 157 |

## Sign-off

- [ ] Owner or editor has reviewed this checklist and selected which
      families enter `content/curation/trial_subset.csv` (CONTENT-5's
      actual deliverable).
- [ ] Every selected family has a source_key or an "editor to source"
      marker for its deadline, backup route and scholarship (CONTENT-5
      acceptance: "no value without a source").
- [ ] Every selected family's eligibility set is marked complete or
      wholly excluded, never partial.
