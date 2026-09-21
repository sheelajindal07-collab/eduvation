---
STATUS: DRAFT RESEARCH — NOT VERIFIED — DO NOT INSERT DIRECTLY INTO THE DATABASE
---

# DRAFT RESEARCH — Madhya Pradesh: State Admission-Rules Profile (Board, Engineering Counselling, Medical Counselling, Domicile/State-Quota Basics)

This is unverified draft research collected by an AI agent from public web
sources. It is **not** a verified fact record under BCION Lite's
maker-checker process (see `CLAUDE.md` non-negotiables and
`docs/DATA.md`). Every fact below still needs a human verifier to confirm
against the primary source, record a verification date, and approve it
before it can be published or used to answer a student. Do not insert any
row below directly into the facts/records tables. No rank predictions,
suitability judgments or guarantees are made here, in line with project
rules.

Research date: 2026-09-21. Researcher: automated agent, web search only, no student data used or seen.

Scope note: this file covers state-level admissions *infrastructure*
(which board, which counselling body, which process, what domicile means)
for Madhya Pradesh, one level up from individual-institution profiles —
mirroring the depth of `docs/content-drafts/gujarat-institutions.md` /
`gujcet-eligibility.md`, not replacing a future institution-level file.

---

## 1. Class 12 board

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Board name | Madhya Pradesh Board of Secondary Education (MPBSE) | https://mpbse.mponline.gov.in/ | 2026-09-21 | High — read directly on the board's own MPOnline portal page, which headers itself "Madhya Pradesh Board of Secondary Education – MPOnline Portal" |
| Headquarters | Link Road 1, M.P. Nagar, Behind DB Mall, Shivaji Nagar, Bhopal, Madhya Pradesh 462011 | https://mpbse.mponline.gov.in/ | 2026-09-21 | High — address string read directly on the official portal page |
| Classes/exams covered | References to "Main Exam Form – Class X" and "Main Exam Form – Class XII" confirm the board conducts Class 10 and Class 12 board exams; the page also references Class IX and XI enrolment | https://mpbse.mponline.gov.in/ | 2026-09-21 | High for Class 10/12 exam conduct; Medium for the full IX–XII scope, since a complete exam list was not enumerated on the fetched page |
| Establishing act/year | Not confirmed from a primary source this session. A secondary aggregator summary (search-engine synthesis, not opened as a primary document) states MPBSE "was established in 1965 under the Madhya Pradesh Secondary Education Act" | Secondary aggregator synthesis only | 2026-09-21 | Low — needs manual verification against the Act text or an official "About us" page |
| Domain note | The board's `.nic.in` domain (`mpbse.nic.in`), which is normally the more authoritative government domain, returned a connection error (`ECONNREFUSED`) on every fetch attempt this session. All facts above were instead confirmed on `mpbse.mponline.gov.in`, the board's MPOnline-hosted portal, which is also an official Madhya Pradesh government service (MPOnline is the state's public e-governance portal operator) but is a distinct domain from `.nic.in`. A verifier should re-check `mpbse.nic.in` directly, since this session's inability to reach it may be transient. | Attempted: https://mpbse.nic.in/ (failed both attempts) | 2026-09-21 | Not verified — connectivity issue, not a content finding |

## 2. Engineering-admission counselling

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Conducting body | Directorate of Technical Education, Madhya Pradesh (DTE MP) — the counselling portal's own header identifies it as "तकनीकी शिक्षा संचालनालय" (Directorate of Technical Education) | https://dte.mponline.gov.in/ | 2026-09-21 | High — read directly on the official DTE MP counselling portal |
| No separate state CET | Madhya Pradesh does **not** appear to run its own engineering entrance test (no MP PET/PEPT-style exam was found). The DTE MP portal itself references cutoffs "based on JEE Main" (Hindi text: "बीपीएल / क्लास फोर कट ऑफ (जेई.ई. मेन के आधार पर) - बी. टेक") and did not mention any state-specific entrance exam. A secondary source (Careers360's DTE MP admission article) states this explicitly: "Admission will be based on marks secured by the candidates in JEE Main [and] Class 12" | https://dte.mponline.gov.in/ (primary, partial); https://engineering.careers360.com/articles/mp-be-admission (secondary, explicit statement) | 2026-09-21 | Medium-High — the primary portal's own cutoff-list language is consistent with JEE-Main-based admission and the absence of any state CET reference, and a secondary source states this outright, but neither source is a single authoritative "admission policy" document read end-to-end this session |
| Admission basis | JEE Main score/rank, and/or Class 12 marks (for courses/categories that admit on Class 12 merit alone, e.g. some diploma/lateral-entry or BPL-quota seats) | https://engineering.careers360.com/articles/mp-be-admission | 2026-09-21 | Medium — secondary source; not read verbatim from a single DTE MP policy document this session |
| Process (as observed) | Centralised online counselling at dte.mponline.gov.in: online registration, merit list based on JEE Main/Class 12, multiple counselling rounds including a "CLC" (seat-upgradation) phase, seat allotment, document verification and college reporting | https://dte.mponline.gov.in/ ; https://engineering.careers360.com/articles/mp-be-admission | 2026-09-21 | Medium — process steps corroborated across the primary portal's structure and a secondary walkthrough, but not confirmed against a single official "how counselling works" document |
| Programmes covered by DTE MP counselling | UG: B.Tech, B.Arch, BCA, B.Pharm, and management degrees (BBA/BMS/BBM); PG: M.Tech, MBA, MCA, M.Pharm, M.Arch; Diploma: regular diploma, lateral entry, and SC/ST-specific schemes | https://dte.mponline.gov.in/ | 2026-09-21 | Medium — programme list read from the portal's navigation/category structure, not from a single consolidated official list |
| State-quota / home-state seat percentage for engineering | Not found this session — no percentage figure (equivalent to the 85%/15% figure below for medical) was located on the DTE MP portal or in the secondary source consulted; the Careers360 article explicitly does not specify a seat-category breakdown by domicile | https://engineering.careers360.com/articles/mp-be-admission | 2026-09-21 | Not verified — "not found"; needs manual verification against a DTE MP information brochure/seat matrix |
| JEE-route central institutes in MP (e.g. MANIT Bhopal, IIIT/NIT-type institutes) | Out of scope for this file — those seats are allotted via JoSAA on an all-India basis, not through DTE MP state counselling; not researched in this session | Not researched this session | 2026-09-21 | Not verified — "not found", flagged as a scope boundary rather than a missing fact |

## 3. Medical-admission counselling (NEET-UG based)

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Conducting body — name discrepancy flagged | The official counselling portal (dme.mponline.gov.in) self-identifies, on a departmental-home fetch, as the **"Department of Public Health and Medical Education"**. Secondary sources uniformly refer to the counselling authority as the **"Department of Medical Education (DME), Madhya Pradesh"**. These may be the same body under a longer formal name plus a common short name ("DME"), or DME may be a directorate within the larger department — this was **not resolved** from a primary document this session. | https://dme.mponline.gov.in/ (primary, partial); multiple secondary sources using "DME" | 2026-09-21 | Medium — body's existence and portal are confirmed; the exact formal-name relationship needs manual verification |
| Basis of admission | NEET-UG score/rank, for MBBS/BDS seats in government and private medical/dental colleges in Madhya Pradesh | Secondary sources only this session (e.g. vedantu.com/neet/mp-neet-counselling); attempts to fetch a primary DME MP page with this statement returned an error page with no substantive content | 2026-09-21 | Medium — NEET-UG as the basis is extremely well-established nationally and stated consistently by secondary sources for MP specifically, but was not read verbatim on a primary DME MP page this session |
| State quota vs All-India Quota split | Reported as **85% Madhya Pradesh State Quota / 15% All-India Quota (AIQ, via the central Medical Counselling Committee, MCC)** — this matches the national-standard 85/15 split used by most states for government medical/dental college seats | https://www.vedantu.com/neet/mp-neet-counselling (secondary) | 2026-09-21 | Medium — plausible and matches the known national pattern, but not confirmed verbatim against a primary DME MP prospectus this session; attempts to fetch DME MP department pages directly did not return this figure |
| Additional quota detail (unconfirmed, single-source) | The same secondary source reports a distinct **"5% Government School Quota"** within MP NEET counselling, for students who completed Classes 9–12 in an MP government school, requiring a government-school certificate | https://www.vedantu.com/neet/mp-neet-counselling (secondary, single source only) | 2026-09-21 | Low — this specific quota was seen in only one secondary source this session and was not cross-checked against any second source or a primary document; needs manual verification before being treated as fact |
| State-quota eligibility (domicile requirement) | State quota seats require a **Madhya Pradesh Domicile Certificate**; candidates without one are stated to be eligible only for All-India Quota counselling (via MCC), not MP state quota | https://www.vedantu.com/neet/mp-neet-counselling (secondary) | 2026-09-21 | Medium — consistent with the domicile-certificate mechanism described in section 4, but the precise eligibility text (e.g. whether Class 11–12 schooling in MP is also required, as is common in other states) was **not confirmed** from a primary DME document this session |
| Counselling schedule (single observed cycle) | Round 1 reported as 13–22 August 2026, followed by Round 2, Mop-Up and Stray Vacancy rounds, all conducted online via dme.mponline.gov.in | Secondary sources (e.g. vedantu.com, and similar aggregator listings seen in search results) | 2026-09-21 | Low-Medium — single-cycle, secondary-sourced dates; not confirmed against a primary DME MP counselling schedule notice this session |

## 4. Domicile / state-quota basics

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Two distinct certificate types found | Madhya Pradesh's e-governance service catalogue (as listed on official district `.nic.in` pages) distinguishes a **"Residence Certificate"** from a **"Domicile Certificate"** — these are not the same service, which matters because admission bodies may require one specific type | https://rewa.nic.in/en/service/residence-certificate-domicile/ ; https://maihar.nic.in/en/scheme/residence-or-domicile-certificate-in-mp/ | 2026-09-21 | High — read directly and consistently on two independent official district government (`.nic.in`) pages |
| Residence Certificate eligibility | "Only permanent residents of Madhya Pradesh state can apply for residence certificate" (as worded on the official pages) | Same two official district pages | 2026-09-21 | High — consistent wording confirmed on both official pages |
| Domicile Certificate eligibility | "Residents of last five years in Madhya Pradesh state are eligible to apply for Domicile Certificate" (as worded on the official pages) | Same two official district pages | 2026-09-21 | High — consistent 5-year figure confirmed on both official pages |
| Residency-length discrepancy flagged | A separate secondary-source synthesis (not opened as a primary document) reported a conflicting figure of **10 years** residency for "domicile," alongside the 5-year figure. Since both official `.nic.in` district pages independently and consistently state 5 years for the Domicile Certificate specifically, 5 years is treated as the higher-confidence figure here, but the 10-year claim is **not resolved** — it may refer to a different certificate, an older rule, or simply be an aggregator error. | Secondary aggregator synthesis (10-year claim) vs. https://rewa.nic.in and https://maihar.nic.in (5-year claim) | 2026-09-21 | Low for the 10-year claim specifically; the 5-year figure is High confidence as noted above. Needs manual verification to resolve the conflict. |
| Marriage-related provision | "If a woman does not originally belong to Madhya Pradesh, but married to a man who is a permanent resident of Madhya Pradesh, then she will be eligible to apply for residence certificate" (as worded on the official pages) | Same two official district pages | 2026-09-21 | High — consistent wording on both official pages |
| Issuing mechanism | Applications are processed through the **Lok Seva Kendra** (public service centre) at the district level, via the state e-district portal (referenced as `mpedistrict.gov.in`); this portal link itself was **not independently opened** this session, so its current eligibility/document-list detail was not verified | https://rewa.nic.in/ ; https://maihar.nic.in/ | 2026-09-21 | Medium — issuing mechanism confirmed on two official district pages; underlying portal detail not separately verified |
| Documents required | Not found this session — neither official district page fetched enumerated the specific document checklist for either certificate type | https://rewa.nic.in/ ; https://maihar.nic.in/ | 2026-09-21 | Not verified — "not found" |
| Role in admissions | A Madhya Pradesh Domicile Certificate is the document that both the medical state-quota (section 3) and, by general inference, the engineering counselling process (section 2) rely on to define a "state" candidate — direct confirmation that DTE MP's own counselling rules specifically require this exact certificate (as opposed to some other domicile proof) was **not found** on the DTE MP portal this session | Cross-referenced from sections 2 and 3 above | 2026-09-21 | Medium for medical (directly stated by a secondary source in section 3); Low for engineering (inferred, not confirmed against a DTE MP document) |
| Small-state/infrastructure caveat check | Madhya Pradesh is a large state with its own board (MPBSE), its own technical-education directorate running centralised engineering counselling (DTE MP), and its own medical-education department running NEET-UG state counselling (dme.mponline.gov.in). It does **not** rely on a neighbouring state's admissions infrastructure. This is a genuine, directly observed finding: all bodies were independently confirmed to operate distinct official MP government portals this session. | https://mpbse.mponline.gov.in/ ; https://dte.mponline.gov.in/ ; https://dme.mponline.gov.in/ | 2026-09-21 | High — existence of all three distinct bodies/portals is confirmed directly; this is the specific "does MP have its own infrastructure" question the task asked to check |

---

## Verifier checklist before any fact above may be promoted to a verified record

1. Re-attempt `https://mpbse.nic.in/` directly (this session got `ECONNREFUSED`
   on two attempts) and confirm the board's establishing Act/year, which
   this draft only sourced from an unopened secondary synthesis.
2. Open an official DTE MP information brochure or seat-matrix document
   (not the counselling portal's live pages) to confirm: (a) that there is
   truly no separate MP state engineering entrance exam, (b) the exact
   home-state/domicile seat percentage for engineering, which this draft
   could not find at all, and (c) whether Class 12 marks alone (without
   JEE Main) is a genuine separate admission route or only applies to
   specific quotas (BPL, lateral entry, etc.).
3. Open an official DME/Department of Public Health and Medical Education
   MP prospectus or counselling-information PDF directly to confirm the
   85%/15% state/AIQ split, the reported "5% Government School Quota"
   (seen in only one secondary source — treat as unverified until then),
   and the exact domicile/schooling eligibility conditions for state
   quota seats.
4. Resolve the "Department of Public Health and Medical Education" vs.
   "Department of Medical Education (DME)" naming question against an
   official document (e.g. a government order or the department's own
   letterhead/notification), since this draft could not confirm whether
   these are the same body.
5. Resolve the 5-year vs. 10-year domicile-residency discrepancy noted in
   section 4 against an official rule/notification, not another district
   page (both district pages checked this session already agree on 5
   years, so a third official source or the underlying state rule/GR
   would help confirm which figure, if either, is wrong).
6. Confirm the exact document checklist for both the Residence Certificate
   and the Domicile Certificate via `mpedistrict.gov.in` or the current
   Lok Seva Kendra service list, which this session did not open.
7. Record verifier name and verification date per `CLAUDE.md`
   non-negotiables ("every published fact has a source, a verification
   date and a verifier") before any of this reaches a student-facing
   answer.
