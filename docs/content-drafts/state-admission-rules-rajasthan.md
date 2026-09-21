---
STATUS: DRAFT RESEARCH — NOT VERIFIED — DO NOT INSERT DIRECTLY INTO THE DATABASE
---

# DRAFT RESEARCH — Rajasthan State Admission-Rules Profile (Board, Engineering
   Counselling, Medical Counselling, Domicile/State-Quota Basics)

This is unverified draft research collected by an AI agent from public web
sources. It is **not** a verified fact record under BCION Lite's
maker-checker process (see `CLAUDE.md` non-negotiables and
`docs/DATA.md`). Every fact below still needs a human verifier to confirm
against the primary source, record a verification date, and approve it
before it can be published or used to answer a student. Do not insert any
row below directly into the facts/records tables. No rank predictions,
suitability judgments or guarantees are made here, in line with project
rules.

Research date: 2026-09-21. Researcher: automated agent (session run for
carohitjin@gmail.com), web search only, no student data used or seen.

Scope note: this file covers state-level admissions *infrastructure* (which
board, which counselling body, which process, what domicile means) for
Rajasthan, one level up from individual-institution profiles — mirroring
the depth of `docs/content-drafts/gujarat-institutions.md` /
`gujcet-eligibility.md`, not replacing a future institution-level file.

Tooling note: this session's general web-search tool was unavailable for
most of this research (budget exhausted), so findings below were gathered
by directly fetching individual URLs (official domains where they
resolved, secondary sources where they did not). Several official
Rajasthan government domains returned DNS or connection errors this
session (noted per row below) — these are flagged as tooling limitations,
not evidence that the body/site does not exist.

---

## 1. Class 12 board

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Board name | "Board of Secondary Education, Rajasthan" (BSER), headquartered at Ajmer — read directly from the official site's own page title | https://rajeduboard.rajasthan.gov.in/ | 2026-09-21 | High — official name and Ajmer location read directly from the live site's title/frameset; the site is an older frameset-based design, so a full "About Us" statutory paragraph could not be extracted this session. |
| Classes/exams covered | The board's own site references "scholarship programs for secondary and senior secondary students" and publishes "Main and Supplementary" exam results, consistent with it conducting both Class 10 (Secondary) and Class 12 (Senior Secondary) board examinations | https://rajeduboard.rajasthan.gov.in/main.asp | 2026-09-21 | Medium-High — the Secondary/Senior-Secondary wording was read directly, but an explicit sentence stating "BSER conducts Class 10 and Class 12 exams" was not located verbatim this session. |
| Establishing act/year, exact statutory status | Not found this session — the site's "About Us"-type subpage(s) could not be located/opened (an attempted direct path, `AboutUs.aspx`, returned 404) | Attempted: https://rajeduboard.rajasthan.gov.in/rbse/AboutUs.aspx (404) | 2026-09-21 | Not verified — "not found"; needs manual verification. |

## 2. Engineering-admission counselling body and process

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Process name | Rajasthan runs a named state engineering-admission counselling process called **REAP** (Rajasthan Engineering Admission Process), covering B.E./B.Tech and B.Arch seats at engineering colleges in the state | Two independent secondary sources agree on the name and course scope: careers360-linked summary and https://www.getmyuni.com/exams/reap | 2026-09-21 | Medium — name and course scope corroborated by two independent secondary sources, but not read verbatim on a primary government REAP page this session (see conducting-body discrepancy below). |
| Conducting body — **discrepancy flagged, not resolved** | Two secondary sources disagree on who conducts REAP: one (careers360-linked summary) states the **Centre for Electronic Governance (CEG), Rajasthan** administers the counselling portal; another (getmyuni) states **Rajasthan Technical University (RTU), Kota** is the conducting body, giving a physical "REAP Office" address at RTU, Kota. This agent could not resolve the discrepancy this session: an attempted fetch of `ceg.rajasthan.gov.in` returned HTTP 401 (Unauthorized), and an attempted fetch of `rtu.ac.in` returned HTTP 403 (Forbidden) — neither primary site's content was actually read. It is possible RTU is the statutory/administrative authority while CEG operates the technical counselling portal on its behalf, but this is this agent's inference, not a confirmed fact. | Careers360-linked summary (CEG claim); https://www.getmyuni.com/exams/reap (RTU claim); attempted https://ceg.rajasthan.gov.in/ (401) and https://rtu.ac.in/ (403) | 2026-09-21 | Low — needs manual verification. A verifier should open RTU's or CEG's own site directly (this agent's tooling was blocked) to determine the actual statutory conducting authority before this is used in a student-facing answer. |
| No separate state written entrance exam for B.Tech — likely, not fully confirmed | Neither secondary source describes REAP as including its own written entrance test; both describe it as a counselling/seat-allocation process layered on external scores. The official Directorate of Technical Education, Rajasthan (DTE) site, fetched directly this session, described only diploma and non-engineering-degree admissions on its landing page and did not mention B.Tech/REAP at all, so DTE's own role (if any) in degree-engineering admission was **not confirmed**. | https://dte.rajasthan.gov.in/ (primary, partial — no REAP/B.Tech mention found); secondary sources above | 2026-09-21 | Medium — absence of a named state written exam is consistent across sources, but DTE's exact role (or non-role) was not confirmed from its own site. |
| Admission basis | Reported as a combined-merit model: JEE Main rank/score (and NATA score for B.Arch) is given first priority, with remaining/unfilled seats allocated by Class 12 (10+2) percentile merit | Both secondary sources agree on this description; direct quotes: "The counselling process will be conducted on the basis of JEE Main and 10+2 scores" and "marks obtained in JEE Main or NATA exams on first priority" followed by Class 12 percentile | 2026-09-21 | Medium — consistent across two independent secondary sources, but not read verbatim from a primary REAP document this session. |
| Portal/domain names found | Secondary sources cite portal domains `reapbtech24.com` and `reapadm.in` (year-versioned naming, e.g. the "24" suggests these domains are reissued/renamed each admission cycle). Both domains failed or were unreachable when this agent attempted to fetch them directly this session (`reapadm.in` returned a DNS resolution failure; `reapbtech24.com` was not attempted directly, as it is explicitly a prior-year (2024) domain name). | https://www.getmyuni.com/exams/reap; attempted fetch of https://reapadm.in/ (DNS failure) | 2026-09-21 | Low — a verifier should search for the *current* (2026-27 cycle) REAP portal domain directly, since this pattern of year-specific domain names means last year's URL is very likely already stale. |
| Current-cycle status | One secondary source (careers360-linked) states REAP 2026 counselling was active, citing "The Centre for Electronic Governance (CEG), Rajasthan, has released the REAP seat allotment for TFWS candidates on July 09, 2026," with rounds continuing through August 2026 | Careers360-linked summary | 2026-09-21 | Low-Medium — single secondary source, single observed data point; not cross-checked against a second source or any primary notice. |

## 3. Medical-admission counselling body and process (NEET-UG based)

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Conducting body (as reported) | A secondary source states **Rajasthan University of Health Sciences (RUHS), Jaipur** manages the state's NEET-UG-based MBBS/BDS counselling process | https://www.vedantu.com/neet/rajasthan-neet-counselling (secondary) | 2026-09-21 | Medium — RUHS itself is confirmed as a genuine official Rajasthan state university (see next row), but this agent could **not** independently confirm, on RUHS's own site, that RUHS specifically runs MBBS/BDS NEET-UG counselling (see discrepancy note below). |
| RUHS institutional identity — confirmed directly | RUHS is confirmed as "a state health sciences university established under The Rajasthan University of Health Sciences Act, 2005," overseeing constituent/affiliated colleges in medicine, dentistry, pharmacy, nursing, physiotherapy and paramedical sciences | https://ruhsraj.org/ (read directly) | 2026-09-21 | High — establishing Act, year and institutional scope read directly from RUHS's own official site. |
| MBBS/BDS NEET-UG counselling on RUHS's own portal — **not found, discrepancy flagged** | This agent directly fetched RUHS's own admissions portal (`admissions.ruhsraj.org`) and found it displaying only CUET-UG-based undergraduate admission, PGET (postgraduate entrance), and nursing-programme admission notices — **no mention of NEET-UG, MBBS or BDS counselling appeared on that page this session.** This does not necessarily mean RUHS is uninvolved (MBBS/BDS counselling may run on a separate sub-portal not linked from this landing page, or via a different department — the state's Directorate of Medical Education), but it means the secondary source's claim above was **not corroborated** by this agent reading RUHS's own live content. | https://admissions.ruhsraj.org/ (read directly, MBBS/BDS/NEET absent) | 2026-09-21 | Low for "RUHS conducts NEET-UG counselling" specifically — needs manual verification. |
| Directorate of Medical Education, Rajasthan — could not reach | The Directorate of Medical Education (DME), which in many other states is the specific body running NEET-UG state counselling (separately from a health-sciences university), likely exists for Rajasthan too, but this agent's attempted fetch of `dme.rajasthan.gov.in` failed with a DNS resolution error this session and no working alternate domain was found. | Attempted: https://dme.rajasthan.gov.in/ (DNS failure) | 2026-09-21 | Not verified — "not found"; a verifier should locate DME Rajasthan's actual working domain and confirm whether DME or RUHS (or both, in different roles) runs NEET-UG state counselling. |
| Basis of admission | NEET-UG score/rank, for MBBS/BDS seats — stated by the secondary source above; this is also the near-universal national pattern for state MBBS/BDS counselling since 2017 (consistent with what this project's Bihar and Madhya Pradesh draft-research files independently found for those states) | https://www.vedantu.com/neet/rajasthan-neet-counselling (secondary); cross-referenced against national pattern | 2026-09-21 | Medium — plausible and consistent with the national pattern and with this project's other state drafts, but not read verbatim from a Rajasthan primary source this session. |
| Process description (as reported) | Online registration, fee/security-deposit payment, choice filling and locking, seat allotment, document verification, and college reporting, across multiple rounds (Round 1, 2, 3 and Mop-Up) | https://www.vedantu.com/neet/rajasthan-neet-counselling (secondary) | 2026-09-21 | Low-Medium — single secondary source; process shape matches the general national pattern but round names/dates were not cross-checked. |
| State quota vs All-India Quota split | Reported as **85% Rajasthan state quota / 15% All-India Quota (AIQ)** — matching the same 85/15 split this project's Bihar and Madhya Pradesh draft-research files found for those states (a nationally-common pattern for state government medical college seats) | https://www.vedantu.com/neet/rajasthan-neet-counselling (secondary) | 2026-09-21 | Low-Medium — plausible and consistent with the cross-state pattern, but not confirmed against a Rajasthan primary prospectus or seat-matrix document this session. |
| Domicile requirement for state-quota seats | The same secondary source states a "Rajasthan domicile certificate is compulsory for government medical college seats," with non-domicile candidates limited to private-college seats (subject to institutional policy) or All-India Quota seats | https://www.vedantu.com/neet/rajasthan-neet-counselling (secondary) | 2026-09-21 | Low-Medium — single secondary source; exact eligibility wording (e.g. required residence duration, parental-employment routes) not confirmed. |
| Full eligibility detail, seat-matrix numbers, fee structure, reservation breakdown | Not confirmed this session for any of the reasons above (primary DME domain unreachable; RUHS's own admissions portal did not show MBBS/BDS content) | — | 2026-09-21 | Not verified — "not found." |

## 4. Domicile / state-quota basics for Rajasthan's government institutions

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| General mechanism | A Rajasthan domicile certificate is the document that determines eligibility for the state-quota share of medical seats (per section 3 above); by inference (not directly confirmed) it likely plays a similar role for REAP engineering state-quota seats, since this is the standard pattern across the other states this project has researched (Bihar, Madhya Pradesh) | Cross-referenced from section 3; not independently confirmed for engineering | 2026-09-21 | Low for the engineering side specifically (inferred, not confirmed against a REAP/DTE document); Medium for the medical side (stated by a secondary source in section 3). |
| Exact eligibility conditions (residency length, parent-based routes, documents required) | Not found this session. Multiple attempts to reach a primary or secondary source describing Rajasthan's domicile-certificate eligibility rules in detail failed or returned no usable content: a Rajasthan government portal page (`sso.rajasthan.gov.in`) loaded but exposed no service-level detail to this agent's fetch tooling (JavaScript-rendered content); a district government page (`jaipur.rajasthan.gov.in`) likewise exposed no relevant text; and two attempted secondary sources (paisabazaar.com; rajras.in) returned 403/404 errors. | Attempted: https://sso.rajasthan.gov.in/, https://jaipur.rajasthan.gov.in/, https://www.paisabazaar.com/tax/domicile-certificate/ (403), https://rajras.in/rajasthan-domicile-certificate/ (404) | 2026-09-21 | Not verified — "not found." This is a legally and practically important eligibility gate and must be confirmed from a primary Rajasthan government order or e-Mitra/SSO service description before use in any student-facing answer. |
| Issuing authority / application channel | The general Indian pattern (also seen in this project's Bihar and Madhya Pradesh drafts) is a Tehsildar/SDM-issued residence or domicile certificate via the state's e-governance/e-Mitra service portal. Rajasthan's own e-Mitra portal (`emitra.rajasthan.gov.in`) was reached but returned no extractable service-detail text to this agent's fetch tooling this session (likely a JavaScript-rendered portal). | Attempted: https://emitra.rajasthan.gov.in/ (loaded, no usable content extracted) | 2026-09-21 | Low — "not found" at the Rajasthan-specific level; the general-pattern claim is an inference from other states' documented processes, not a Rajasthan-specific confirmation. |
| Small-state/no-distinct-infrastructure caveat (per task framing) | Does not apply to Rajasthan as a finding — Rajasthan is a large state with its own named board (BSER), its own named engineering counselling process (REAP), and its own named health-sciences university (RUHS) that at minimum is confirmed to be a genuine, independently-operating Rajasthan institution. This is a genuine structural observation, though (per sections 2–3 above) several *operational details* of how these bodies actually run current admissions could not be confirmed this session due to tooling limitations (search budget exhausted; several official domains unreachable), not because the infrastructure itself appears to be absent or borrowed from another state. | Inference from confirmed findings in sections 1–3 | 2026-09-21 | Medium-High for "Rajasthan has its own distinct named infrastructure"; explicitly lower confidence for the operational details underneath each body, as noted throughout. |

---

## Verifier checklist before any fact above may be promoted to a verified record

1. Resolve the REAP conducting-body discrepancy (Centre for Electronic
   Governance vs. Rajasthan Technical University, Kota) by opening RTU's
   own site (`rtu.ac.in`, blocked this session with HTTP 403) and/or CEG's
   own site (`ceg.rajasthan.gov.in`, blocked this session with HTTP 401)
   directly, or the current-year REAP portal itself once its domain is
   located.
2. Locate the *current* (2026-27 cycle) REAP portal domain — the two
   domains found this session (`reapbtech24.com`, `reapadm.in`) are
   year-versioned and likely stale; neither could be reached this session.
3. Resolve whether RUHS, a separate Directorate of Medical Education, or
   both in different roles, actually conducts Rajasthan's NEET-UG MBBS/BDS
   state counselling — RUHS's own admissions portal did not show MBBS/BDS
   content this session, which directly contradicts the secondary source's
   claim and must be checked against a primary document before use.
   `dme.rajasthan.gov.in` failed to resolve this session; find its correct
   current domain.
4. Confirm the 85%/15% state-quota/AIQ split and the domicile-certificate
   requirement for both REAP (engineering) and the medical counselling
   process against a primary prospectus or seat-matrix document — this
   session only found the medical-side figure, from one secondary source.
5. Confirm BSER's establishing Act/year and exact statutory description,
   and re-attempt a working "About Us"-equivalent page (the
   `AboutUs.aspx` path guessed this session returned 404).
6. Confirm Rajasthan's domicile-certificate eligibility conditions
   (residency length, parental-employment routes, documents required) and
   issuing authority against a primary Rajasthan government order or a
   working e-Mitra/SSO service description — this session's attempts were
   blocked by JavaScript-rendered portals and dead secondary-source links.
7. Record verifier name and verification date per `CLAUDE.md`
   non-negotiables ("every published fact has a source, a verification
   date and a verifier") before any of this reaches a student-facing
   answer.
