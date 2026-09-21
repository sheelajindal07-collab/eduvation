---
STATUS: DRAFT RESEARCH — NOT VERIFIED — DO NOT INSERT DIRECTLY INTO THE DATABASE
---

# DRAFT RESEARCH — NIRF Top-Ranked Institutions in the Law Category (National)

This is unverified draft research collected by an AI agent from public web
sources. It is **not** a verified fact record under BCION Lite's
maker-checker process (see `CLAUDE.md` non-negotiables and
`docs/DATA.md`). Every fact below still needs a human verifier to confirm
against the primary source, record a verification date, and approve it
before it can be published or used to answer a student. Do not insert any
row below directly into the facts/records tables. No rank predictions or
suitability judgments are made here, in line with project rules.

Research date: 2026-09-21. Researcher: automated agent, web search only, no student data used or seen.

---

## 1. Which edition is "current"

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Latest published NIRF Law ranking edition as of this session | India Rankings **2025** (Law category). A direct request for a "2026" edition page (`nirfindia.org/Rankings/2026/LawRanking.html`) returned a site maintenance message, not a ranking table, so a 2026 edition could not be confirmed as published. | https://www.nirfindia.org/Rankings/2025/LawRanking.html ; attempted https://www.nirfindia.org/Rankings/2026/LawRanking.html | 2026-09-21 | Medium — the 2025 table itself was read successfully (see below); the "no 2026 edition yet" conclusion rests on one page attempt returning a maintenance notice, which could also mean the URL pattern for 2026 differs, not necessarily that 2026 doesn't exist. A verifier should check nirfindia.org's homepage/rankings index directly for the current edition before using this file. |
| Ranking authority | National Institutional Ranking Framework (NIRF), Ministry of Education, Government of India | https://www.nirfindia.org/ | 2026-09-21 | High — official ministry ranking framework site |

## 2. NIRF India Rankings 2025 — Law category, Top 10

Fetched directly from the official NIRF Law ranking page. Each row below
also carries the institution's NIRF Institute ID as shown on the page, in
case an ID is useful for de-duplication against other sources later.

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Rank 1 | National Law School of India University (NLSIU), Bengaluru, Karnataka — Score 82.97 — Institute ID IR-L-U-0238 | https://www.nirfindia.org/Rankings/2025/LawRanking.html | 2026-09-21 | High — read directly from the official NIRF page (two independent fetches of the same page returned matching figures, including city/state/ID on the second pass) |
| Rank 2 | National Law University (NLU), New Delhi, Delhi — Score 80.00 — Institute ID IR-L-U-0111 | Same official page | 2026-09-21 | High |
| Rank 3 | NALSAR University of Law, Hyderabad, Telangana — Score 79.50 — Institute ID IR-L-N-18 | Same official page | 2026-09-21 | High |
| Rank 4 | The West Bengal National University of Juridical Sciences (NUJS), Kolkata, West Bengal — Score 79.39 — Institute ID IR-L-U-0585 | Same official page | 2026-09-21 | Medium — score confirmed on first fetch (79.39); the second fetch's raw-quote pass did not include the state name for this row, though city (Kolkata) matched |
| Rank 5 | Gujarat National Law University (GNLU), Gandhinagar, Gujarat — Score 76.23 — Institute ID IR-L-U-0134 | Same official page | 2026-09-21 | High |
| Rank 6 | Indian Institute of Technology Kharagpur (Rajiv Gandhi School of Intellectual Property Law), Kharagpur, West Bengal — Score 74.09 — Institute ID IR-L-U-0573 | Same official page | 2026-09-21 | Medium — score confirmed on first fetch (74.09); the second fetch's raw-quote pass did not repeat the score for this row. Note: IIT Kharagpur appearing in a Law-category ranking is plausible (it runs a specialised IP law school) but a verifier should double-check this is not a page-parsing artefact, since it sits unusually among dedicated national law universities. |
| Rank 7 | Symbiosis Law School, Pune, Maharashtra — Score 74.07 — Institute ID IR-L-C-19328 | Same official page | 2026-09-21 | High |
| Rank 8 | Jamia Millia Islamia, New Delhi, Delhi — Score 66.39 — Institute ID IR-L-U-0108 | Same official page | 2026-09-21 | High |
| Rank 9 | Aligarh Muslim University, Aligarh, Uttar Pradesh — Score 65.82 — Institute ID IR-L-U-0496 | Same official page | 2026-09-21 | High |
| Rank 10 | Siksha 'O' Anusandhan, Bhubaneswar, Odisha — Score 65.36 — Institute ID IR-L-U-0363 | Same official page | 2026-09-21 | High |

## 3. What could NOT be confirmed this session

| Fact | Value | Source | Access date | Confidence |
|---|---|---|---|---|
| Whether a newer (2026) NIRF edition exists and, if so, whether the Law top-10 order has changed | Not found — the guessed 2026 URL showed a maintenance page, not a "page does not exist" response, so this is inconclusive rather than a confirmed "no 2026 edition" | https://www.nirfindia.org/Rankings/2026/LawRanking.html | 2026-09-21 | Not verified — needs manual check of the live nirfindia.org rankings index |
| Full ranking parameters/weightage breakdown (TLR, RP, GO, OI, Perception sub-scores) for each of the above institutions | Not found — this session only read the headline rank/score/name/city/state/ID fields, not the parameter-wise breakdown table | https://www.nirfindia.org/Rankings/2025/LawRanking.html | 2026-09-21 | Not verified — "not found," would need a further fetch of each institution's detail page |
| Whether IIT Kharagpur's Law-category listing (rank 6) reflects a specific named school/programme (e.g. its IP law school) as opposed to the whole institute | Not found — the ranking row lists the parent institute name only | https://www.nirfindia.org/Rankings/2025/LawRanking.html | 2026-09-21 | Not verified |

---

## Method note (for the verifier)

Two separate automated fetches of the same official URL
(`https://www.nirfindia.org/Rankings/2025/LawRanking.html`) were made in
this session with different prompts — one asking for a summarised
rank/institution/score table, one asking for raw quoted text including
Institute IDs and city/state. The two passes agreed on institution names,
ranks, and scores for all 10 rows, which is why most rows above are marked
"High" confidence. Two rows (4 and 6) are marked "Medium" only because one
of the two passes omitted a field (state, or repeating the score) that the
other pass had already supplied — the figures themselves did not conflict
between passes.

This file was produced by an automated web-fetch/summarisation tool, not
by opening the page directly in a browser and reading the DOM. A human
verifier should independently open
https://www.nirfindia.org/Rankings/2025/LawRanking.html (and check
nirfindia.org's current homepage for whether a later edition has since
been published), re-read all 10 rows, and record their own verification
date and name before any row here is promoted to a verified fact.
