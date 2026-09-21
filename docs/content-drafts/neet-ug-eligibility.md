DRAFT RESEARCH — not verified, not published, needs a named human reviewer
before any fact here can be used (docs/DATA.md maker-checker workflow).
Never insert directly into the database.

# NEET (UG) — eligibility research

Researched for BCION Lite content pipeline. Every fact below carries its
source URL, the date it was accessed, and a confidence note. Facts that
could not be confirmed on an official page are marked "not found, needs
manual verification" rather than estimated.

Access date for all entries below (unless noted otherwise): **2026-09-19**.

**Cycle warning — read first.** The only official bulletin available on
the access date is for **NEET (UG) 2026**, whose exam was held on
03 May 2026. A student using Lite today is planning for NEET (UG) 2027 or
later. Year-specific values below (the date-of-birth cutoff, fees, dates)
belong to the 2026 cycle only and must not be published as if they apply
to a later year. The NEET (UG) 2027 bulletin was not found on the access
date. A reviewer should set a short review-due date on anything published
from this draft and re-check when the 2027 bulletin appears.

## Official sources checked

- `https://neet.nta.nic.in/` — NTA's NEET (UG) site. Reached through a
  browser (the plain fetcher got HTTP 403). Its "Eligibility Criteria"
  page (`/eligibility-criteria/`) and "Information Bulletin" document
  category both rendered **"No Documents found."** on the access date.
  The bulletin itself is linked from the site's navigation menu, item
  "Information Bulletin for NEET(UG)-2026".
- `https://cdnbbsr.s3waas.gov.in/s37bc1ec1d9c3426357e69acd5bf320061/uploads/2026/02/202602231394640855.pdf`
  — **Information Bulletin NEET (UG)-2026**, the target of that menu
  link (government S3WaaS CDN). 124-page text PDF, fully readable; PDF
  metadata creation date 2026-02-08. **This is the source for every fact
  below.** Page references are given as *PDF page / printed page*.
- `https://www.nmc.org.in/neet/neet-ug/` — National Medical Commission's
  NEET-UG page specifically. **Not read**: redirected to a URL that
  returned HTTP 404 in this session.
- `https://nmc.org.in/page/rules-regulations-rules-regulations-nmc` —
  NMC's general Rules and Regulation index. Reached through a browser;
  its "Under-Graduate Medical Education Board (UGMEB)" section (an
  accordion, collapsed by default) links the two primary documents below.
- `https://nmc.org.in/storage/cms/rules-regulation-nmc/G83KmfBTvRKFfp99s6Vvjuuw3gJ7WM2ZP28Z3Zhk.pdf`
  — **Graduate Medical Education Regulations, 2023** ("GMER-23"), dated
  02.06.2023, published in the Gazette of India Part III Section 4
  (Extraordinary), No. CG-DL-E-02062023-246254. 9-page bilingual
  (Hindi/English) text PDF, fully readable. This is the primary
  regulation the bulletin's Chapter 6 summarises — an independent,
  higher-authority source than the bulletin itself.
- `https://nmc.org.in/storage/cms/rules-regulation-nmc/QwhpGdAJfo2yFLcbox9qHeAAJ4ZVhjAxq2CU2YlG.pdf`
  — **GMER-2023 Amendment/Corrigendum**, dated 16.06.2023, Gazette of
  India No. CG-DL-E-19062023-246659. 2-page bilingual text PDF, fully
  readable. This is the exact notification the bulletin cites for the
  minimum-age rule.

## Facts

### 1. Minimum age

- **Fact:** A candidate must have "completed the age of 17 years as on or
  before 31st December of the year that the candidate shall be appearing
  for NEET-UG examination." For the 2026 cycle the bulletin states the
  lower age limit as **born on or before 31.12.2009**, the same for
  General (UR)/General-EWS and for SC/ST/OBC-NCL/PwBD/PwD candidates.
- **Cited authority (per the bulletin):** Graduate Medical Education
  Regulation-2023 (Amendment) dated 16.06.2023.
- **Source:** Information Bulletin NEET (UG)-2026, Chapter 6, clause 1
  (i)–(ii), PDF page 30 / printed page 25.
- **Independently confirmed against the primary regulation.** GMER-2023's
  own Chapter III, Clause 11(a) (the base regulation, dated 02.06.2023)
  originally read: *"unless he has completed the age of 17 years as on
  or before 31st **January** of the year that the candidate shall be
  appearing for NEET-UG examination"* — note **January**, not December.
  The 16.06.2023 Corrigendum then substituted Clause 11(a) with: *"unless
  he has completed the age of 17 years as on or before 31st **December**
  of the year that the candidate shall be appearing for NEET-UG
  examination; and"* — this is the version in force and matches the
  bulletin exactly, verbatim, word for word. Worth recording because it
  shows the cutoff month was itself corrected once already (Jan → Dec)
  three months after the base regulation — a reason to treat any
  screenshot or secondary summary of this clause with caution and always
  check the current Gazette text.
- **Confidence:** confirmed twice, independently — the bulletin's own
  restatement and the actual Gazette of India regulation/corrigendum
  text agree exactly (2026 cycle framing; the underlying rule itself is
  not year-specific).
- **Mapping to Lite claim fields — GAP, do not paper over:**
  `minimum_age = 17` is the closest existing field, but
  `app/rules/eligibility.py::minimum_age` compares against the student's
  *current age as an integer*. NEET's rule is a **date-of-birth cutoff
  relative to 31 December of the exam year**. A 16-year-old who turns 17
  before that date is eligible, and the current criterion would tell them
  "does not meet". Publishing `minimum_age = 17` as-is would produce
  wrong answers for exactly the Class 11–12 students Lite serves. Needs
  either a new criterion type (age on a reference date) or an explicit
  decision recorded in `docs/DECISIONS.md` before this claim is published.

### 2. Upper age limit

- **Fact:** "there is no upper age limit."
- **Cited authority (per the bulletin):** NMC/UGMEB Letter No.
  U-11022/2/2022-UGMEB dated 09 March 2022; reaffirmed per Letter No.
  U-14023/19/NEET(UG Exam)/UGMEB dated 13.01.2026.
- **Source:** Bulletin, Chapter 6, clause 1 (iii), PDF page 30 / printed
  page 25.
- **Not independently confirmed.** GMER-2023 itself (the regulation just
  checked directly, see fact 1) states no upper age limit at all — it is
  silent on the point, in both the base text and the 16.06.2023
  corrigendum. The "no upper age limit" fact rests entirely on the two
  NMC/UGMEB letters the bulletin cites (09.03.2022 and 13.01.2026);
  neither letter was located or read directly in this session.
- **Confidence:** confirmed-in-official-bulletin only (2026 cycle); the
  cited underlying letters remain unverified.
- **Mapping:** publish **no** `maximum_age` claim for a NEET pathway. The
  eligibility route already treats an absent claim as "no criterion",
  which is the correct behaviour here.
- **Housekeeping flag:** `tests/unit/test_eligibility.py` uses a
  "NEET-UG-style" synthetic fixture with `maximum_age(25)`. It is a
  labelled synthetic composition and is fine as a rules-engine test, but
  the figure 25 does **not** match the 2026 bulletin and must never be
  copied into content.

### 3. Required subjects in the qualifying examination

- **Fact:** The qualifying-examination codes (01–07) require "Physics,
  Chemistry, Biology / Biotechnology along with English". Under Codes 01
  and 02, these subjects may have been studied "even as additional
  subjects after passing Class 12th from duly recognized boards", per
  NMC's Public Notice dated 22.11.2023. A candidate whose Class 12 result
  is awaited may appear (Code 01) but is not eligible for admission if
  they have not passed the qualifying examination by the first round of
  counselling.
- **Cited authority (per the bulletin):** NMC Letter
  CDN-20011/289/2024-Cordination-NMC dated 05.12.2025; Letter
  U-14023/19/NEET(UG Exam)/UGMEB dated 13.01.2026; NMC Public Notice
  dated 22.11.2023.
- **Source:** Bulletin, Chapter 6, clause 3, PDF pages 31–32 / printed
  pages 26–27.
- **Independently confirmed against the primary regulation.** GMER-2023,
  Chapter III, Clause 11(b): *"Has passed 10 +2 (or equivalent) with
  subjects of Physics, Chemistry Biology/ Biotechnology and English."*
  This is the base regulation's own eligibility-to-*appear* clause (sits
  right next to the age clause in fact 1) — a second, independent
  confirmation that Biology and Biotechnology are alternatives, not both
  required.
- **Confidence:** confirmed twice, independently (bulletin + primary
  Gazette regulation, exact match).
- **Mapping — GAP:** `required_subjects` is an **all-of** set. Encoding
  `"Physics,Chemistry,Biology,English"` would wrongly fail a student who
  took Biotechnology instead of Biology, and the bulletin explicitly
  allows either. The engine has no "one of" group today. Options for a
  reviewer/implementer: add an any-of subject group to the criterion, or
  publish only the unambiguous part (`Physics,Chemistry`) plus a
  plain-text note. Do not publish the all-of four-subject string.

### 4. Minimum marks percentage in Class 12 (PCB)

- **Fact:** **not found, needs manual verification.** The 2026 bulletin's
  eligibility chapter (Chapter 6) states **no minimum percentage** in
  Physics/Chemistry/Biology. A full-text search of all 124 pages for
  "50%", "45%", "40%", "aggregate" and "minimum marks" found only
  payment-gateway charges, disability thresholds (RPwD Act), and the
  qualifying *percentile* in fact 5 below.
- **Source checked:** Bulletin, whole document.
- **Independently checked against the primary regulation — still not
  found.** GMER-2023, Chapter III, Clause 9 ("Eligibility criteria"):
  *"No student shall be eligible to pursue graduate medical education...
  except by scoring the minimum eligible score at the NEET-UG exam;
  Provided the UGMEB shall by notification announce the list of eligible
  students from time to time."* The regulation ties eligibility to the
  NEET-UG *score* itself (see fact 5's percentile rule), not to any
  fixed Class 12 percentage. A full-text search of the 9-page regulation
  for "percentage" and "domicile" and "reservation" returned zero
  matches. This raises confidence that the commonly repeated "50% in
  PCB" figure is not a real Class-12-marks eligibility rule at all —
  likely a conflation with the *qualifying-percentile* rule in fact 5 —
  but it remains unconfirmed either way; a genuine floor could still
  exist in a different NMC notification not located in this session.
- **Confidence:** not found, needs manual verification. The commonly
  repeated "50% in PCB (40% reserved, 45% PwBD)" figure appears across
  third-party sites but is **not** in the bulletin or in GMER-2023
  itself, so it is not reproduced as a fact here.
- **Mapping:** publish **no** `minimum_marks_percentage` claim unless a
  reviewer finds it in a primary regulation. Absent claim → no criterion,
  which is honest; a guessed 50 would not be.

### 5. Qualifying percentile (for admission — NOT eligibility to appear)

- **Fact:** To be eligible for *admission*, General/General-EWS
  candidates must obtain minimum marks at the **50th percentile** in
  NEET (UG); SC/ST/OBC at the **40th percentile**; candidates with
  benchmark disabilities at the **45th percentile** (UR/GEN-EWS) or
  **40th percentile** (SC/ST/OBC-NCL). The Central Government may lower
  these for a given academic year.
- **Source:** Bulletin, Chapter 8, clause 1 (ii)(a)–(b), PDF page 44 /
  printed page 39.
- **Confidence:** confirmed-in-official-bulletin (2026 cycle).
- **Mapping — deliberately none.** This is a result of the exam, not an
  input a student has. It must **not** be mapped to
  `minimum_marks_percentage` (a percentile is not a Class 12 percentage),
  and Lite must not turn it into a score or rank prediction
  (CLAUDE.md non-negotiable). Suitable only as explanatory text on a
  "requirements" view, if at all.

### 6. Nationality and domicile

- **Fact (appearing in NEET):** Indian Nationals, NRIs, OCIs, Persons of
  Indian Origin and Foreign Nationals are eligible, "subject to the rules
  and regulations framed by respective State Governments, Institutions
  and The Government of India". **No domicile condition for appearing in
  the exam was found.**
- **Fact (state-quota seats):** "Admission under State Quota Seats shall
  be subject to reservation policy and eligibility criteria prevailing in
  the State/Union Territory as notified by the respective State/Union
  Territory from time to time." Counselling for 15% All India Quota seats
  is by MCC/DGHS; seats under state control are counselled by the state's
  designated authority under separately issued notifications.
- **Source:** Bulletin, Chapter 6 clause 2, PDF pages 30–31 / printed
  pages 25–26; Chapter 7 clauses 1(B) and 2, PDF pages 34–35 / printed
  pages 29–30.
- **Independently checked against the primary regulation.** GMER-2023
  contains no domicile, reservation, quota, or state-related admission
  clause at all (zero matches on a full-text search) beyond the single
  word "State" appearing once, in an unrelated sentence about training.
  This confirms the bulletin's own framing: domicile/reservation for
  state-quota seats is genuinely delegated to each State/UT's own
  notifications, not fixed anywhere in national NEET regulation.
- **Confidence:** confirmed-in-official-bulletin, and consistent with
  (not contradicted by) the primary regulation's silence (2026 cycle).
- **Mapping:** publish **no** `domicile_states` claim on a NEET *exam*
  pathway. Gujarat's state-quota domicile rule is a separate fact that
  belongs on a Gujarat-specific medical-admission pathway and is **not
  found, needs manual verification** — it was not researched in this
  session and the NTA bulletin does not state it.

### 7. Number of attempts at NEET-UG itself

- **Fact:** not found, needs manual verification. The bulletin text
  contains no statement on a limit (or absence of a limit) on the number
  of *exam* attempts; the only "attempt" matches are about attempted
  questions. GMER-2023 (the primary regulation, now checked directly)
  also contains no clause limiting how many times a candidate may sit
  NEET-UG.
- **Confidence:** not found. Do not publish "unlimited attempts" on the
  strength of either document's silence.
- **Related but distinct fact found — do not conflate with the above.**
  GMER-2023, Chapter V ("Competency Based Dynamic Curriculum at
  Undergraduate Level"), states:
  *"under no circumstances the student shall be allowed more than four
  (04) attempts for first year (First Professional MBBS) and no student
  shall be allowed to continue undergraduate medical course after nine
  (09) years from the date of admission into the course."* This is a
  limit on retaking the **first year of the MBBS course itself**, after
  a student is already admitted — it has nothing to do with how many
  times a student may sit the NEET-UG *entrance exam*. Flagging it so a
  reviewer doesn't later mistake it for an answer to this fact's
  question.
- **Source:** GMER-2023, Chapter V, Clause 21 ("Training period and
  maximum duration"), PDF page 9.

### 8. Application fee (2026 cycle — for the cost calculator)

- **Fact:** General ₹1700; General-EWS/OBC-NCL ₹1600;
  SC/ST/PwBD/PwD/Third Gender ₹1000; candidates outside India ₹9500.
  Bank/gateway processing charges and GST are additional.
- **Source:** Bulletin, "Important Information and Dates at a Glance",
  PDF page 7 / printed page 2.
- **Confidence:** confirmed-in-official-bulletin — **2026 cycle only**;
  fees are revised between cycles.

### 9. Exam pattern (2026 cycle — context only)

- **Fact:** 180 compulsory MCQs in 180 minutes — Physics 45, Chemistry
  45, Biology (Botany & Zoology) 90; 720 marks total; pen-and-paper mode.
- **Source:** Bulletin, PDF page 7 / printed page 2, and Chapter 4,
  PDF page 26.
- **Confidence:** confirmed-in-official-bulletin (2026 cycle).

## Summary: what a NEET pathway could safely carry today

| Lite claim field | Proposed value | Status |
| --- | --- | --- |
| `minimum_age` | 17 (as on 31 Dec of exam year) | Confirmed twice (bulletin + Gazette regulation/corrigendum), but **engine gap** — do not publish until reference-date handling is decided |
| `maximum_age` | *(no claim)* | Bulletin says no upper limit, sourced only to a cited NMC letter not yet read directly |
| `required_subjects` | Physics, Chemistry, Biology **or** Biotechnology, + English | Confirmed twice (bulletin + Gazette regulation), but **engine gap** — no any-of support |
| `minimum_marks_percentage` | *(no claim)* | Not found in bulletin **or** primary regulation (checked both) |
| `domicile_states` | *(no claim for the exam)* | Confirmed absent from both bulletin and regulation; Gujarat's state-quota rule is a separate, unresearched fact |

Nothing in this table is a published fact. Each row still needs a named
reviewer and the maker-checker flow (`docs/DATA.md`,
`db/migrations/0003_maker_checker.sql`).

## What was NOT used as a source

Third-party aggregator and coaching sites were not consulted. Figures
widely repeated there — "50% in PCB", "upper age 25", attempt limits —
are absent from both the 2026 official bulletin and the primary
GMER-2023 regulation (both checked directly in this session) and are not
reproduced as facts here.

## Corroboration done this session (2026-09-19, second pass)

The bulletin's eligibility chapter was cross-checked against the primary
regulation it summarises: **Graduate Medical Education Regulations,
2023** (dated 02.06.2023) and its **16.06.2023 Corrigendum**, both
official Gazette of India notifications, read in full text via NMC's own
site (`nmc.org.in` → Rules and Regulation → UGMEB — the direct links were
not exposed as visible anchors and needed a DOM inspection to find; see
"Official sources checked" above). Outcome: age (fact 1) and subjects
(fact 3) are now confirmed by two independent official documents, exact
verbatim match. The regulation's own silence on marks percentage (fact
4), domicile/reservation (fact 6), and exam-attempt limits (fact 7)
strengthens rather than weakens those "not found" conclusions — it is
not merely that the bulletin omits them, the primary law does too.

## Next steps for a human reviewer

1. Open the bulletin PDF and the two GMER-2023 PDFs (URLs above) and
   confirm each quoted clause against the references given.
2. Two things still genuinely unread, both cited by the bulletin but not
   located as primary text in this session:
   - **NMC's Public Notice dated 22.11.2023** (the notice that permits
     Biology/Biotechnology "even as additional subjects" post-NEP) —
     search `nmc.org.in`'s Public Notices/News section.
   - **The two "no upper age limit" letters** — Letter No.
     U-11022/2/2022-UGMEB dated 09.03.2022 and Letter
     U-14023/19/NEET(UG Exam)/UGMEB dated 13.01.2026 — fact 2 rests on
     the bulletin's restatement of these alone.
3. Research Gujarat's state-quota medical admission rules (domicile,
   reservation, any marks floor) from the state's official admission
   committee as a separate draft; confirmed absent from both national
   documents checked here, so it is genuinely a different source.
4. Decide the two engine gaps (age-on-reference-date; any-of subjects)
   before any NEET eligibility claim is published — otherwise the
   eligibility check will give some students a wrong "does not meet".
   These are now the strongest-sourced facts in this whole draft, so
   they're also the ones most ready to publish once the engine gaps are
   closed.
5. When the NEET (UG) 2027 bulletin is released, re-verify the
   2026-cycle-only values (DOB cutoff, fees, dates). The regulation's
   *rule* (17 by 31 Dec, subjects) is not itself year-specific and
   should carry forward, but re-check it wasn't amended again.
6. Only then route facts through maker-checker. Never insert from this
   draft directly.
