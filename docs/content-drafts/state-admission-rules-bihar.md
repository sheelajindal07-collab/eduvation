---
STATUS: DRAFT RESEARCH — NOT VERIFIED — DO NOT INSERT DIRECTLY INTO THE DATABASE
---

# DRAFT RESEARCH — Bihar State Admission Rules (Class 12 Board, Engineering
   and Medical Admission Counselling, Domicile/State-Quota Basics)

This is unverified draft research collected by an AI agent from public web
sources. It is **not** a verified fact record under BCION Lite's
maker-checker process (see `CLAUDE.md` non-negotiables and
`docs/DATA.md`). Every fact below still needs a human verifier to confirm
against the primary source, record a verification date, and approve it
before it can be published or used to answer a student. Do not insert any
row below directly into the facts/records tables. No rank predictions,
suitability judgments, or guarantees are made here, in line with project
rules — this file states named assumptions and ranges only where a range
was found.

Research date: 2026-09-21. Researcher: automated agent, web search only, no student data used or seen.

Scope note: this mirrors the depth of `docs/content-drafts/gujarat-institutions.md`
and `gujcet-eligibility.md` — state admissions *infrastructure* (which
board, which counselling body, which process), not individual institution
listings, which would be a separate, later research pass.

---

## 1. Class 12 board

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Board name | Bihar School Examination Board (BSEB), Patna — conducts Secondary (Class 10) and Senior Secondary/Intermediate (Class 12) examinations for the state | https://biharboardonline.com/ | 2026-09-21 | Medium-High — the board's self-description ("Bihar School Examination Board, Patna") and Class 12/Intermediate exam functions were read directly from the live site's footer and navigation; a formal "About Us" statutory-status paragraph was not located/quoted this session, so a verifier should open that page directly. |
| Government domain note | A `.bihar.gov.in` subdomain for this board (`biharboardonline.bihar.gov.in`) was found referenced by secondary listings but did not resolve (DNS failure) when fetched directly this session. The working, actively-used site is the `biharboardonline.com` domain (a pattern common to several Indian state boards, which use non-`.gov.in` domains as their de facto official portal). | Attempted fetch of biharboardonline.bihar.gov.in (failed — DNS error); working site biharboardonline.com | 2026-09-21 | Low-Medium — a verifier should confirm which domain BSEB currently treats as canonical/official before this is cited as "the" official board URL in any student-facing answer. |
| Separate open/distance schooling body | Bihar Board of Open Schooling and Examination (BBOSE) exists as a distinct body for open/distance Class 10–12 schooling, separate from BSEB's regular-school Class 12. | https://bboseonline.bihar.gov.in/ (domain observed in search results; page itself not opened/read this session) | 2026-09-21 | Low — "not found" at read-verbatim level; name and existence only, from a search-result title, not confirmed by opening the page. |

## 2. Engineering-admission counselling body and process

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Counselling body | Bihar Combined Entrance Competitive Examination Board (BCECEB), Patna — a statutory board constituted under the Bihar Combined Entrance Competitive Examination Act, 1995, conducting admissions for Medical, Engineering and Agricultural professional courses in the state's institutions. | https://bceceboard.bihar.gov.in/ (self-description, read directly from the live homepage) | 2026-09-21 | High — read directly from the board's own official site. |
| No separate state engineering CET for B.Tech — confirmed | Bihar does **not** run a separate state-specific engineering entrance test analogous to Gujarat's GUJCET for undergraduate B.Tech admission. Instead, admission to B.Tech seats in Government Engineering Colleges of Bihar is allocated through JEE (Main) ranks, via BCECEB's own counselling process named **UGEAC** (Under Graduate Engineering Admission Counselling). The same UGEAC process also covers B.Architecture admission, using JEE (Main) plus NATA scores. | Live BCECEB homepage notice text, e.g. "...Under Graduate Engineering Admission Counselling [UGEAC-2026] ... on the basis of JEE(MAIN)-2026 ..." and "...Bachelor of Architecture Course ... on the basis of JEE(MAIN)-2026 and NATA" (Adv. Nos. BCECEB(UGEAC)-2026/01 through /10) | https://bceceboard.bihar.gov.in/ | 2026-09-21 | High — this exact "on the basis of JEE(MAIN)" wording was read directly, repeated across multiple dated official notices on the live site, for the current (2026) admission cycle. |
| Separate exam that *is* Bihar-specific (BCECE) | BCECEB separately conducts its own entrance exam called **BCECE** (and its lateral-entry variant BCECE[LE]), but per the board's own course grouping this covers Pharmacy, Paramedical, Agriculture-business (CBA/MBA/MCA/PCA) and PCM/PCB/PCMB group seats — not the main JEE-Main-based B.Tech engineering counselling (UGEAC). A further exam, **DCECE**/DECE[LE], covers polytechnic-diploma engineering and paramedical diploma admission (sub-degree level), not undergraduate B.Tech. | https://bceceboard.bihar.gov.in/ (examination list and notice board) | 2026-09-21 | Medium-High — the course groupings were read from the live site's exam list and notice titles; a verifier should open the BCECE-2026 prospectus/advertisement PDF directly to confirm the exact list of degree programmes covered, since this agent could not machine-extract the PDF's own text this session (see note below). |
| Application/counselling process pattern (2026 cycle, as observed) | UGEAC-2026 ran in multiple stages through 2026: online application (from advertisement dated 09.05.2026), rank card and choice filling (23.06.2026), first round counselling (22.07.2026), and a Round-2 application window (from 11.09.2026) — a multi-round, online choice-filling and seat-allotment counselling process. | Dated official notices on https://bceceboard.bihar.gov.in/ (Adv. Nos. BCECEB(UGEAC)-2026/01 through /10) | 2026-09-21 | Medium — dates read directly from one observed 2026 cycle's notice list, not from a multi-year historical pattern, so "typical" timing should not yet be asserted from this alone. |
| Full eligibility detail, seat-matrix numbers, and fee structure | Not confirmed this session. The board publishes a detailed UGEAC prospectus/advertisement as a PDF (e.g. `ADV_UGEAC25_01.pdf`), but this agent's web-fetch tooling could not machine-extract readable text from that PDF this session (it returned compressed/binary PDF stream data, not parsed text), and a PDF page-rendering tool was unavailable in this environment. A verifier must open that PDF directly. | https://bceceboard.bihar.gov.in/pdf_Adv/ADV_UGEAC25_01.pdf (link located; content not readable this session) | 2026-09-21 | Not verified — "not found" / needs manual verification. |

## 3. Medical-admission counselling body and process

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Counselling body | Same board, BCECEB, also runs medical-admission counselling under the name **UGMAC** (Under Graduate Medical Admission Counselling), for MBBS, BDS and B.V.Sc & A.H. (veterinary) courses, plus a separate **UGMAC[AYUSH]** track for AYUSH courses. | https://bceceboard.bihar.gov.in/ (examination list: "UGMAC[AYUSH]", "UGMAC" both listed as distinct exam/counselling tracks; notice titles reference "MBBS / BDS / BV Sc. & AH Courses") | 2026-09-21 | High — the existence of UGMAC and UGMAC[AYUSH] as distinct board functions, and the MBBS/BDS/BVSc course scope, were read directly from the live official site's exam list and prospectus filename (`PROS_UGMAC25.pdf`, titled "(UGMAC) – 2025 (MBBS / BDS / BV Sc. & AH Courses)" in the board's own document index). |
| Basis: NEET-UG | UGMAC admission is based on NEET-UG scores/rank (candidates register using their NEET-UG roll number). This is the standard, near-universal pattern for state MBBS/BDS counselling across India and is consistently and independently reported by multiple secondary sources (Careers360, Adda247, NeetSupport, and others) describing the 2025/2026 UGMAC cycle. | Not read verbatim from BCECEB's own UGMAC prospectus/notice text this session — same PDF-extraction limitation as above applies to `PROS_UGMAC25.pdf` and `ADV_UGMAC25_01.pdf`. Corroborated by secondary sources, e.g. summaries describing "NEET (UG) 2025 Roll Number" entry at UGMAC registration. | 2026-09-21 | Medium — highly consistent across independent secondary sources and matches the near-universal national pattern (all state MBBS/BDS counselling nationally is NEET-UG based since 2017), but not confirmed by this agent reading BCECEB's own primary document text directly this session. A verifier should open the primary PDF to remove this caveat. |
| Application/counselling process pattern (2026 cycle, as observed) | UGMAC-2026: registration/choice-filling notice dated 07.08.2026 (Round 1), first-round document verification around 25.08–31.08.2026, Round-2 application/choice-filling window opened from 11.09.2026 (with a further extension notice dated 17.09.2026) — again a multi-round online process. | Dated official notices on https://bceceboard.bihar.gov.in/ (Adv. Nos. BCECEB(UGMAC)-2026/01 through /08) | 2026-09-21 | Medium — one observed 2026-cycle timeline, not a multi-year pattern. |
| Full eligibility detail, seat-matrix numbers, fee structure, reservation category breakdown | Not confirmed this session for the same PDF-extraction reason as engineering above. A secondary source reported an aggregate 2026 seat count (1,392 government + 2,450 private MBBS seats = 3,842 total) but this was not independently verified against the board's own seat-matrix PDF this session. | Seat count: secondary source (careers360-linked search summary), not opened directly; primary seat-matrix PDF linked from https://bceceboard.bihar.gov.in/ but not read | 2026-09-21 | Low — seat numbers in particular should be treated as unverified until read from the board's own "Seat Matrix for UGMAC-2026" PDF. |

## 4. Domicile / state-quota basics for Bihar's government institutions

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| State-quota vs All-India-Quota split | Multiple independent secondary sources consistently describe an 85% state-quota / 15% All-India-Quota (AIQ) split for seats in Bihar's government medical (and, per one source, engineering) colleges, matching the standard national pattern for state government college seats. Bihar domicile is required only for the 85% state-quota seats; the 15% AIQ seats (medical) are centrally counselled by MCC and open to candidates from any state. | Multiple secondary sources (careers360-linked and other NEET-counselling aggregator summaries); not read verbatim from a BCECEB or Bihar government primary document this session | 2026-09-21 | Low-Medium — "not found" at primary-source level this session. This 85/15 split is the standard nationally-mandated pattern (per Supreme Court/MCC rules for state government medical colleges generally), so it is plausible, but this agent could not confirm the exact Bihar-specific percentage, or whether it applies identically to engineering seats, from a BCECEB or Bihar-government primary document. A verifier must confirm from BCECEB's own UGEAC/UGMAC prospectus or a Bihar Education/Health Department order. |
| Who qualifies for Bihar domicile/state-quota eligibility | Secondary sources describe eligibility pathways including: candidate domiciled/resident in Bihar (commonly stated as requiring a period of residence, e.g. "at least 10 years," or being born in the state); OR candidate's parent(s) are permanent residents of Bihar (even if the candidate's own schooling was outside Bihar); OR parent(s) are current Government of Bihar employees; OR parent(s) are Central Government/PSU employees currently posted within Bihar. One source specifically notes that, unlike some other states, merely completing Class 10 and 12 schooling in Bihar does **not** by itself establish domicile unless a parental-residence or parental-employment condition is also met. | Secondary sources only (NEET-counselling aggregator articles); not read verbatim from a BCECEB prospectus, Bihar government domicile-certificate rule, or gazette notification this session | 2026-09-21 | Low — "needs manual verification." This is a legally and practically important eligibility gate (it determines who can compete for the large majority of seats), and it must be confirmed from BCECEB's own current-year prospectus or a Bihar Department of General Administration domicile-certificate order before being used in any student-facing answer. The specific "10 years residence" figure in particular was not corroborated against a primary source and could be inaccurate or outdated. |
| Domicile certificate issuing authority | Not found this session — the general Indian pattern is that a residence/domicile certificate is issued by the local Circle Officer/Sub-Divisional Officer (Revenue) via the state's e-services portal (in Bihar, typically the RTPS — Right To Public Services — portal, `serviceonline.bihar.gov.in`), but this was not independently confirmed against a primary source this session. | Not found — general pattern only, no primary source opened | 2026-09-21 | Not verified — "not found." |
| Small-state/no-distinct-infrastructure caveat (per task framing) | Does not apply to Bihar as a finding — Bihar is a large state with its own distinct, actively-run admissions infrastructure (BSEB for Class 12; BCECEB for engineering/medical counselling), unlike some small states/UTs that follow a neighbouring state's system. This is noted here only to record that the "little or no distinct infrastructure" scenario was considered and explicitly does not describe Bihar. | Inference from the confirmed findings above (BSEB and BCECEB both independently, actively operating in 2026) | 2026-09-21 | High — this is a structural observation about what was found (an active, distinct board), not a new external fact requiring its own citation. |

---

## Verifier checklist before any fact above may be promoted to a verified record

1. Open `PROS_UGMAC25.pdf`, `ADV_UGEAC25_01.pdf`, `ADV_UGMAC25_01.pdf`, and the
   current-year seat-matrix PDFs directly (a PDF reader/renderer, not this
   agent's web-fetch tooling, which could not extract their text this
   session) and confirm: NEET-UG as UGMAC's basis in the board's own words;
   exact state-quota/AIQ percentage split for both UGEAC and UGMAC; exact
   domicile-eligibility clause wording; and current seat-matrix numbers.
2. Confirm BSEB's canonical official domain — the `.bihar.gov.in` subdomain
   referenced by some listings did not resolve this session; verify whether
   `biharboardonline.com` is BSEB's own operated domain or a
   privately-run mirror before citing it as "the official BSEB site" to a
   student.
3. Confirm the domicile "10 years residence" figure and the exact list of
   qualifying parental-employment conditions against a primary BCECEB
   prospectus clause or a Bihar government domicile-certificate order —
   this determines eligibility for the large majority of seats and was
   only found in secondary sources this session.
4. Confirm whether the 85/15 state-quota/AIQ split applies identically to
   BCECEB's engineering (UGEAC) seats, since the clearest secondary
   corroboration found was for the medical (UGMAC/NEET) side specifically.
5. Record verifier name and verification date per `CLAUDE.md`
   non-negotiables ("every published fact has a source, a verification
   date and a verifier") before any of this reaches a student-facing
   answer.
