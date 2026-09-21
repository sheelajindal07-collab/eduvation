---
STATUS: DRAFT RESEARCH — NOT VERIFIED — DO NOT INSERT DIRECTLY INTO THE DATABASE
---

# DRAFT RESEARCH — Meghalaya: State Admission-Rules Profile (Class 12 board,
engineering counselling, medical counselling, domicile/state-quota basics)

This is unverified draft research collected by an AI agent from public web
sources. It is **not** a verified fact record under BCION Lite's
maker-checker process (see `CLAUDE.md` non-negotiables and
`docs/DATA.md`). Every fact below still needs a human verifier to confirm
against the primary source, record a verification date, and approve it
before it can be published or used to answer a student. Do not insert any
row below directly into the facts/records tables. No rank predictions or
suitability judgments are made here, in line with project rules.

Research date: 2026-09-21. Researcher: automated agent (session run for
carohitjin@gmail.com), web search only, no student data used or seen.

**Scope note:** per `docs/DECISIONS.md` (2026-09-21, pilot scope widened
to all-India admission rules), this file covers Meghalaya's *state-level
admissions infrastructure* — the board, the counselling bodies and the
domicile rules — one level up from individual institutions, mirroring the
depth of the existing `docs/content-drafts/gujarat-institutions.md` /
`gujcet-eligibility.md` pair for Gujarat. It does **not** attempt an
institution-by-institution list. It also does not re-research NEET-UG
itself (national exam, eligibility already drafted in
`docs/content-drafts/neet-ug-eligibility.md`) — only Meghalaya's *state
counselling* layer on top of it.

**Headline honest finding:** Meghalaya is a **mixed-infrastructure** case,
not a simple "has its own everything" or "borrows a neighbour's system"
answer. It has its own Class 12 board (MBOSE) and its own dedicated
NEET-UG state-quota medical counselling body (MSCAMA/DHS). But no evidence
was found this session of a distinct Meghalaya engineering entrance exam
(state CET) — engineering seats reserved for the state instead appear to
be allocated through a **central mechanism (CSAB-NEUT, using JEE Main
rank)**, confirmed by an official notice hosted on the state's own
education-department site. This is reported as a genuine finding, not
assumed, and is flagged below for a verifier to double-check with a fuller
search.

---

## 1. Class 12 board

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Board name | **Meghalaya Board of School Education (MBOSE)**, headquartered at Tura, Meghalaya. Conducts SSLC (Class 10) and **HSSLC — Higher Secondary School Leaving Certificate (Class 12)** examinations, across Arts, Science, Commerce and Vocational streams. | https://www.mbose.in/ (official site, fetched and read directly: "all the financial matters, relating with SSLC and HSSLC branch were being dealt by the Board itself") | 2026-09-21 | High — read directly from the official site |
| Legal basis / establishment | Founded 1973, operating under the **MBOSE Act, 1973** (as amended 2006); first SSLC exam conducted in 1974 | https://www.mbose.in/ (official site, fetched directly) | 2026-09-21 | High — read directly from the official site |
| History of the Class 12 exam specifically | Higher Secondary (Class 11–12) examinations were originally run by North Eastern Hill University (NEHU) as a Pre-University Course; after NEHU discontinued this in 1996, MBOSE took over full responsibility for Class 12 syllabus and examinations | https://www.mbose.in/ (official site, fetched directly) | 2026-09-21 | High — read directly from the official site |
| Domain-name caution | A general web search surfaced three similar-looking domains: `mbose.in` (official, successfully fetched and read this session), `mbose.in.` (a trailing-dot variant of the same address, not independently tested), and a **separate-looking `mbos.in`** domain (missing the "e"), which was **not fetched or verified** this session. Only `mbose.in` should be treated as confirmed; a verifier should not assume `mbos.in` is legitimate without checking it directly. | Search result listing only (no fetch performed on the two unverified domains) | 2026-09-21 | Not verified for the two alternate domains — flag only, not a confirmed fact |

## 2. Engineering-admission counselling body and process

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Relevant state directorate | **Directorate of Higher and Technical Education (DHTE)**, under the Meghalaya Department of Education — a *combined* directorate covering colleges, universities, engineering institutions and polytechnics (unlike some states that split this into a separate Directorate of Technical Education) | https://www.meghalaya.gov.in/dept/11 and http://megeducation.gov.in/ (both official Government of Meghalaya sites, fetched directly) | 2026-09-21 | High for DHTE's existence and combined scope (read directly); the DHTE-specific admissions sub-page itself returned HTTP 403 Forbidden when fetched directly, so its own detailed content could not be read this session |
| Whether Meghalaya has its own engineering entrance exam (state CET) | **No Meghalaya-specific engineering CET was found this session.** The state's own Education Department site hosts a notice titled **"Admission Notice for Degree Courses in Engineering/Technology/Architecture & Pharmacy against the seats reserved by the Govt of India for the State of Meghalaya"**, referencing **CSAB-NEUT** (Central Seat Allocation Board — North Eastern & UT states) as the process — i.e. **JEE Main rank**, allocated centrally, not a Meghalaya-run written test. | http://megeducation.gov.in/ (official Meghalaya Education Dept. site, fetched directly — notice title and filename read from the page); the linked PDF itself (`.../2025/Web admin Admission Notice csab.pdf`) was located but returned as unreadable binary/compressed content to the fetch tool used, so its full text was not read | 2026-09-21 | Medium-High for "no distinct Meghalaya CET, CSAB-NEUT is the named process" (the notice's own title, naming CSAB and "seats reserved by the Govt of India for the State of Meghalaya," was read directly from the official site); Low for the exact eligibility/date details inside that notice, since the PDF text itself could not be extracted this session |
| What CSAB-NEUT is (corroboration) | The Central Seat Allocation Board's own official site has a distinct "Go for NEUT" section/link, consistent with CSAB-NEUT being a real, separate JEE-Main-rank-based central process for North Eastern & Union Territory states (which includes Meghalaya) | https://csab.nic.in/ (official CSAB site, fetched directly — confirmed the "Go for NEUT" link exists) | 2026-09-21 | Medium — confirms CSAB-NEUT exists as a named process on CSAB's own site; the detailed mechanics (how Meghalaya-reserved seats specifically flow through it) were not read verbatim from a CSAB-NEUT information bulletin this session |
| Government engineering institutions in the state (as found) | **NEHU (North Eastern Hill University), Shillong** — a government/public institution offering B.Tech programmes (e.g. Biomedical Engineering, Electronics & Communication, Information Technology), admitting via **JEE Main**. Separately, **NIT Meghalaya** (a national, centrally-funded institute, not a state institution) exists in the state; its own site was fetched but did not itself state its admission mechanics on the pages read this session — nationally, all NITs are known to admit via JoSAA (JEE Main rank), but this specific claim was **not independently re-confirmed from NIT Meghalaya's own page** this session. | NEHU: https://engineering.careers360.com/colleges/list-of-government-engineering-colleges-in-meghalaya-accepting-jee-main (secondary aggregator); NIT Meghalaya: https://www.nitm.ac.in/ (official site, fetched directly, homepage only — no admission-process detail found on the pages read; a dedicated `/admission` path returned HTTP 404) | 2026-09-21 | Medium for NEHU accepting JEE Main (secondary source only, not independently confirmed on NEHU's own admissions page this session); Low/not verified for NIT Meghalaya's specific admission mechanics (plausible from general national knowledge of the JoSAA system, but not read from NIT Meghalaya's own site this session — do not treat as confirmed) |
| Polytechnic / diploma-level admission (context only, not the main ask) | DHTE's site hosts separate notices for polytechnic **diploma** admissions, including one specifically for Meghalaya students applying to diploma seats **outside the state** (and one for a diploma quota in Arunachal Pradesh) — suggesting diploma-level admission is handled by direct DHTE notice/merit-list rather than a distinct CET, but the **in-state** polytechnic diploma admission process itself was not read from a specific notice this session | http://megeducation.gov.in/ (official site, fetched directly — notice titles and filenames for 2024-25 read from the page) | 2026-09-21 | Medium for the notices' existence and titles (read directly); Low/not found for the in-state polytechnic admission mechanics specifically |

## 3. Medical-admission (NEET-UG) counselling body and process

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| State counselling body | **Meghalaya State Counselling Authority for Medical Education (MSCAMA)**, working with the Directorate of Health Services (DHS), Meghalaya — conducts state-quota MBBS/BDS counselling using NEET-UG 2026 All-India Rank | https://eastmojo.com/meghalaya/2026/09/16/meghalaya-issues-sop-for-138-mbbs-seats-for-2026-27-admissions/ and https://theshillongtimes.com/2026/09/17/govt-opens-counselling-for-138-mbbs-seats/ — two independent Meghalaya-based regional news outlets, consistent with each other; the department's own official site (`meghealth.gov.in`) could not be fetched this session (see note below), so this is **not** confirmed against a primary government page directly | 2026-09-21 | Medium — consistent across two independent regional-press sources describing the live 2026-27 admission cycle, but not read verbatim from an official `meghealth.gov.in`/DHS page this session; a verifier should confirm MSCAMA's exact name, legal basis and process directly from the government SOP document |
| Total 2026-27 seats and structure | **138 seats total**, split into **Part I (96 seats)** — Central Pool/inter-state allocations (53 Central Pool, 16 at RIMS Imphal, 14 at NEIGRIHMS, 10 in Assam government medical colleges, 3 in Tripura) — and **Part II (42 seats)** — the Meghalaya state-quota seats at **Shillong Medical College (SMC)** | Same two regional-news sources as above, cross-corroborated | 2026-09-21 | Medium — same sourcing caveat as above; figures match between the two independent reports, which raises confidence, but neither is the primary government notification |
| Reservation breakdown, Part II (42 SMC state-quota seats) | Khasi and Jaintia candidates: 40%; Garo candidates: 40%; Unreserved: 15%; SC/OST: 5% | Same two regional-news sources, cross-corroborated | 2026-09-21 | Medium — consistent across both sources; "OST" is reported as written but its full expansion (likely "Other Scheduled Tribes," i.e. Scheduled Tribes other than the state's two dominant Khasi-Jaintia/Garo groupings) was **not independently confirmed** from a primary document this session — flag for a verifier |
| Reservation breakdown, Part I (96 seats) | 39 seats each for Khasi-Jaintia and Garo categories, 14 Unreserved, 4 for SC/OST | Same two regional-news sources, cross-corroborated | 2026-09-21 | Medium — same sourcing caveat |
| Eligibility (as reported) | Pass Class XII with Physics, Chemistry, Biology/Biotechnology and English; minimum age 17 by 31 December 2026; qualify NEET-UG 2026; and separately, meet "state domicile and indigenous status/documentation" requirements to claim a reserved-category seat | Same two regional-news sources, cross-corroborated | 2026-09-21 | Medium — same sourcing caveat; the exact wording of the domicile/indigenous-status documentation requirement was not read from a primary SOP document this session |
| Process | Counselling runs over **four rounds, including a Stray Vacancy round**: online registration, choice-filling/rank-based allotment, and document verification, per MSCAMA's published schedule for 2026-27 | Same two regional-news sources, cross-corroborated | 2026-09-21 | Medium — same sourcing caveat |
| Service-bond condition | State-quota (Part II) admitted candidates must execute a bond committing to a minimum of 5 years' service in a government or recognised Mission hospital after graduation | Same two regional-news sources, cross-corroborated | 2026-09-21 | Medium — same sourcing caveat |
| Attempted primary-source check | Direct fetch of `https://meghealth.gov.in/` and `http://meghealth.gov.in/` both failed this session with a TLS/certificate error ("unable to get local issuer certificate") — this is a tool-side fetch limitation, not confirmation that the site is down; a human verifier with normal browser access should check it directly | n/a — fetch attempts, not a source | 2026-09-21 | n/a — documents a gap, not a fact |

## 4. Domicile / state-quota basics

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Relevant document | **Permanent Resident Certificate (PRC)**, issued by the Deputy Commissioner's office of the applicant's district — the primary document used across both engineering (Meghalaya-reserved seats under CSAB-NEUT) and medical (MSCAMA state quota) tracks to establish Meghalaya domicile | Secondary sources only this session (e.g. spmandlalans.com's Meghalaya NEET state-quota explainer); no official Government of Meghalaya PRC-rules page was successfully fetched this session (compare Assam's equivalent page, which was fetched directly in the Assam draft) | 2026-09-21 | Low-Medium — the existence and issuing authority of a PRC is consistently reported and plausible (matches the pattern confirmed directly for Assam), but was **not** read from an official Government of Meghalaya page this session; flag as "needs manual verification against a primary source" |
| Domicile is necessary but not sufficient for reserved seats | Multiple secondary sources state that **schooling in Meghalaya alone does not establish domicile** — proof of residence (electricity bills, land records/Patta, or a parent's employment certificate) is also required to obtain a PRC. Separately, reserved-category (Khasi-Jaintia / Garo / SC-OST) seats additionally require proof of **indigenous tribal status**, which is a distinct requirement from general domicile/PRC. | Secondary sources only (general Meghalaya NEET/domicile explainer articles); not independently confirmed against an official Government of Meghalaya document this session | 2026-09-21 | Low — directionally plausible and consistent with Meghalaya's Sixth Schedule / autonomous-district-council context, but **not confirmed from a primary source** this session; do not treat the specific documents listed (electricity bill, Patta, etc.) as an exhaustive or authoritative list without verification |
| Broader eligibility for NE-region candidates (medical, as reported) | One secondary source states candidates for Meghalaya MBBS/BDS admission must be "a permanent resident of any of the 8 North Eastern states," or alternatively have completed Class 11–12 from a state/centrally recognised school — which, if accurate, would mean the medical state-quota eligibility pool may be wider than "Meghalaya domicile only" and include other NE-state residents under some pathway. **This conflicts in scope with the stricter "Meghalaya domicile and indigenous status" wording reported elsewhere (section 3 above) and was not resolved this session.** | Secondary source only (spmandlalans.com); contrast with the eastmojo/Shillong Times wording in section 3 | 2026-09-21 | Low — flagged as an open contradiction, not resolved; a verifier must check the official MSCAMA/DHS eligibility notice directly rather than relying on either secondary account |
| Small-state / shared-infrastructure question | Meghalaya was **not** found to be a "borrows a neighbouring state's system" case in the simple sense — it runs its own board (MBOSE) and its own dedicated medical counselling authority (MSCAMA). The one area resembling a "no distinct infrastructure of its own" pattern is **engineering admission**, where — per the finding in section 2 — the state appears to rely on the central CSAB-NEUT/JEE Main mechanism rather than running its own entrance test. This is a genuine, partial finding (mixed, not uniform), not an assumption. | Based on sections 1–3 above (official sites for MBOSE and the state portal; regional press for MSCAMA; official notice title for CSAB-NEUT) | 2026-09-21 | Medium — grounded in what was actually read this session across the three tracks, though each individual track has its own confidence caveats noted above |

---

## What could not be confirmed this session (do not treat as settled)

1. **The full text of the CSAB-NEUT admission notice** hosted on
   `megeducation.gov.in` — its title and filename were read directly, but
   the PDF itself returned as unreadable binary/compressed content to the
   fetch tool used this session. This is the single most important
   document to open by hand (in a proper PDF reader) before publishing any
   Meghalaya engineering-admission fact, since it should state exact seat
   numbers, eligibility and dates.
2. **`meghealth.gov.in` (Directorate of Health Services / MSCAMA's likely
   home site)** could not be fetched this session — both `http://` and
   `https://` attempts failed with a TLS certificate error on the tool
   side. All MBBS/BDS counselling facts in section 3 rest on two
   consistent regional-press reports, not a primary government page. A
   verifier with normal browser access should check this site directly.
3. **The DHTE-specific admissions sub-page** on `megeducation.gov.in`
   (path `/dhte`) returned HTTP 403 Forbidden this session and could not
   be read.
4. **Whether NIT Meghalaya's B.Tech admission is JoSAA-based** — this is
   true for NITs nationally as general knowledge, but was **not**
   independently confirmed from NIT Meghalaya's own site this session (its
   homepage did not state admission mechanics on the pages read, and
   `/admission` returned 404).
5. **Whether NEHU Shillong's JEE-Main-based admission claim** is accurate
   — sourced from a secondary aggregator (careers360) only, not confirmed
   on NEHU's own admissions page this session.
6. **The exact expansion of "SC/OST"** in the Meghalaya medical
   reservation breakdown (likely "Other Scheduled Tribes," distinct from
   the Khasi-Jaintia/Garo categories) — not confirmed from a primary
   document.
7. **A contradiction on medical eligibility scope** — one secondary
   source suggests any-of-the-8-NE-states residency may qualify for some
   pathway, while the main sourcing (section 3) describes a stricter
   Meghalaya-domicile-and-indigenous-status requirement. Not resolved this
   session; flagged as an open question rather than guessed at.
8. **The exact rules for obtaining a Meghalaya PRC** (residency-duration
   thresholds, parental requirements, etc., analogous to what was
   confirmed directly for Assam in the Assam draft) — no official
   Government of Meghalaya PRC page was successfully fetched this session.
9. **Whether `mbos.in` (as distinct from the confirmed official
   `mbose.in`) is a legitimate alternate domain or something else** — not
   fetched or checked this session; treat only `mbose.in` as confirmed.

## Official / primary sources actually read this session

- https://www.mbose.in/ — Meghalaya Board of School Education (official)
- https://www.meghalaya.gov.in/departments — Government of Meghalaya state portal, department index
- https://www.meghalaya.gov.in/dept/11 — Education Department page (official)
- https://www.meghalaya.gov.in/dept/19 — Health & Family Welfare Department page (official)
- http://megeducation.gov.in/ — Department of Education, Government of Meghalaya (official) — source of the CSAB-NEUT notice title/filename and DHTE description
- https://csab.nic.in/ — Central Seat Allocation Board (official) — confirmed the CSAB-NEUT ("NEUT") process exists as a named link
- https://www.nitm.ac.in/ — NIT Meghalaya (official) — homepage only, admission mechanics not found on pages read

## Attempted but failed / unreadable this session

- http://megeducation.gov.in/edu_dept/notices_and_circulars/2025/Web admin Admission Notice csab.pdf — located, but binary/compressed, not text-extractable
- https://meghealth.gov.in/ and http://meghealth.gov.in/ — TLS certificate error, could not fetch
- http://megeducation.gov.in/dhte — HTTP 403 Forbidden
- https://www.nitm.ac.in/admission — HTTP 404 Not Found

## Secondary sources used only where explicitly flagged above as lower confidence

eastmojo.com, theshillongtimes.com (both Meghalaya-based regional news
outlets, used for section 3's MBBS/BDS counselling details in the absence
of a fetchable primary government page), engineering.careers360.com,
byjus.com, admission.aglasem.com, spmandlalans.com, studyriserr.com,
targetneet.com, affinityeducation.in. None of these were treated as
sufficient on their own to mark a fact "High" confidence — every row
sourced from them above is explicitly marked Medium or Low and flagged for
manual verification, per this task's instruction to prefer official
sources and disclose when only a secondary source was found.

## Next steps for a human reviewer

1. Open the CSAB-NEUT admission notice PDF directly (in a PDF reader, or
   OCR it) to confirm exact Meghalaya-reserved engineering seat numbers,
   institutions and dates.
2. Access `meghealth.gov.in` (or the correct current DHS/MSCAMA domain)
   directly with a normal browser to confirm MSCAMA's legal basis, the
   138-seat structure, the reservation breakdown, and the exact domicile/
   indigenous-status documentation required — none of this was read from
   a primary government page this session.
3. Resolve the open contradiction on medical-admission eligibility scope
   (Meghalaya-only domicile vs. any-of-8-NE-states residency).
4. Confirm NIT Meghalaya's and NEHU's actual admission mechanics from
   their own official admissions pages rather than a homepage or a
   secondary aggregator.
5. Confirm the official Meghalaya PRC issuance rules from a primary
   Government of Meghalaya page (Revenue Department or equivalent).
6. Record verifier name and verification date per `CLAUDE.md`
   non-negotiables ("every published fact has a source, a verification
   date and a verifier") before any fact from this draft reaches a
   student-facing answer.

No rank predictions, suitability judgments, or guaranteed outcomes are
made anywhere in this file, per `CLAUDE.md`'s non-negotiables.
