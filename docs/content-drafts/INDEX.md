# Content drafts index — coordination only, not a source of truth

Purpose: prevent duplicate/conflicting research across concurrent sessions
and agent batches. Every file in this directory is **unverified draft
research**, never a published fact (see CLAUDE.md non-negotiables and the
maker-checker workflow in `docs/BCION-Lite-Build-Pack.md` section 6). This
index tracks *what topic each file covers*, not its accuracy.

**Before starting new research on a topic, check here first.** If a topic
is listed as done or in-progress, don't re-research it — extend the
existing file or coordinate with whoever has it in progress instead.

**When you land a new draft, add a row here in the same commit/edit.**

## Status key
`done` = file exists, drafted. `in-progress` = a batch is actively
producing it. `planned` = named as upcoming but not started.

## Exams (eligibility rules)
| Topic | File | Status |
| --- | --- | --- |
| GUJCET | `gujcet-eligibility.md` | done |
| NEET (UG) | `neet-ug-eligibility.md` | done |
| JEE Main | `jee-main-eligibility.md` | done |
| CUET-UG | `cuet-ug-eligibility.md` | done |
| CLAT | `clat-eligibility.md` | done |
| SSC CGL | `ssc-cgl-eligibility.md` | done |
| CAT (MBA) | `cat-mba-eligibility.md` | done |
| NDA | — | in-progress (per 2026-09-21 ~100-agent batch) |
| IBPS PO | — | in-progress (per 2026-09-21 ~100-agent batch) |
| GPSC Class 1–2 | — | not yet claimed |

## Scholarships
| Topic | File | Status |
| --- | --- | --- |
| Gujarat state schemes | `gujarat-scholarships.md` | done |
| Maharashtra post-matric | `maharashtra-post-matric-scholarship.md` | done |
| Tamil Nadu post-matric | `tamil-nadu-post-matric-scholarship.md` | done |
| NMMSS | `nmmss-scholarship.md` | done |
| AICTE Pragati/Saksham | `aicte-pragati-saksham-scholarships.md` | done |
| 10 more central schemes | — | in-progress (per 2026-09-21 ~100-agent batch) |

## Institutions / NIRF
| Topic | File | Status |
| --- | --- | --- |
| Gujarat institutions | `gujarat-institutions.md` | done |
| NIRF top engineering | `nirf-top-engineering-institutions.md` | done |
| NIRF top medical | `nirf-top-medical-institutions.md` | done |
| NIRF management (possible overlap with CAT eligibility file — confirm scope before writing) | — | in-progress, **flagged for scope clarification** |
| NIRF law (possible overlap with CLAT eligibility file — confirm scope before writing) | — | in-progress, **flagged for scope clarification** |
| NIRF architecture/NATA | — | in-progress |
| NIRF pharmacy | — | in-progress |
| NIRF private-university comparison | — | in-progress |

## States/UTs — admission-rules + institutions/scholarships profiles
Gujarat is the only state with dedicated drafts so far (see above, folded
into the topic tables rather than duplicated here). All 33 remaining
states/UTs (2 topics each) are `in-progress` per the 2026-09-21 ~100-agent
batch — not itemised individually here yet to avoid this index becoming
another thing to keep in sync mid-batch; add a state's row once its first
file lands.

## Foreign / study-abroad (new scope, 2026-09-21)
| Topic | File | Status |
| --- | --- | --- |
| US, UK, Canada, Australia (first pass) | — | in-progress |
| 8 more countries | — | in-progress (per 2026-09-21 ~100-agent batch) |

## Known coordination note (2026-09-21) — resolved
Confirmed no collision, not just no-conflict-by-luck: checked the actual
running batch's script (mine, session "BCION project report review"). The
NIRF deep-dives were already named distinctly before this was flagged —
`nirf-top-management-institutions.md`, `nirf-top-law-institutions.md`,
`nirf-top-architecture-institutions.md`, `nirf-top-pharmacy-institutions.md`
— institution-ranking lists, same pattern as the existing
`nirf-top-engineering/medical-institutions.md`, genuinely distinct from
`cat-mba-eligibility.md`/`clat-eligibility.md` (exam rules). No file was
renamed; the two "flagged for scope clarification" rows above can be
read as resolved once this batch's files land.

## Full file list for the 2026-09-21 ~100-agent batch (session "BCION project report review")
Can't retroactively make this already-dispatched batch check this index
first (script was fixed and launched before this index existed) — but
every filename below was chosen to avoid the 18 files that existed before
this batch started, and the batch will not touch any file outside this
list. Committing to checking this index before any future batch.

**Exams (8):** `jee-advanced-eligibility.md`, `nata-eligibility.md`,
`uceed-eligibility.md`, `icar-aieea-eligibility.md`, `cmat-eligibility.md`,
`xat-eligibility.md`, `afcat-eligibility.md`, `cds-eligibility.md`.

**Scholarships (10):** `scholarship-inspire.md`, `scholarship-ntse.md`,
`scholarship-pm-special-jk-ladakh.md`, `scholarship-top-class-sc.md`,
`scholarship-national-fellowship-obc.md`, `scholarship-aicte-swanath.md`,
`scholarship-central-sector-st.md`, `scholarship-post-matric-minorities.md`,
`scholarship-ishan-uday.md`, `scholarship-national-overseas.md`.

**Foreign pathways (8):** `foreign-pathway-germany.md`,
`foreign-pathway-ireland.md`, `foreign-pathway-singapore.md`,
`foreign-pathway-new-zealand.md`, `foreign-pathway-uae.md`,
`foreign-pathway-netherlands.md`, `foreign-pathway-france.md`,
`foreign-pathway-japan.md`.

**NIRF/institutions (5):** `nirf-top-management-institutions.md`,
`nirf-top-law-institutions.md`, `nirf-top-architecture-institutions.md`,
`nirf-top-pharmacy-institutions.md`,
`notable-private-universities-overview.md`.

**Synthesis (2, index/comparison docs over this batch's own output, not
new primary research):** `foreign-pathways-comparison-summary.md`,
`nsp-scheme-catalog-index.md`.

**States/UTs (33 states, 2 files each = 66):** every state/UT except
Gujarat, Maharashtra, Tamil Nadu (already covered above). File pattern:
`state-admission-rules-<slug>.md` (board/counselling-body/domicile
profile) and `state-institutions-scholarships-<slug>.md` (one institution
+ one scholarship per state). Slug = lowercase, spaces/parens to hyphens
(e.g. `state-admission-rules-andhra-pradesh.md`,
`state-admission-rules-jammu-and-kashmir.md`). Full 33-state list:
Andhra Pradesh, Arunachal Pradesh, Assam, Bihar, Chhattisgarh, Goa,
Haryana, Himachal Pradesh, Jharkhand, Karnataka, Kerala, Madhya Pradesh,
Manipur, Meghalaya, Mizoram, Nagaland, Odisha, Punjab, Rajasthan, Sikkim,
Telangana, Tripura, Uttar Pradesh, Uttarakhand, West Bengal, Andaman and
Nicobar Islands, Chandigarh, Dadra and Nagar Haveli and Daman and Diu,
Delhi (NCT), Jammu and Kashmir, Ladakh, Lakshadweep, Puducherry.

I'll come back and mark each row `done` (or flag failures) once the batch
reports complete — this list is the authoritative "what's coming" in the
meantime, so anyone checking mid-batch knows exactly what not to
re-research.
