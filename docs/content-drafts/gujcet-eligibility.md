DRAFT RESEARCH — not verified, not published, needs a named human reviewer
before any fact here can be used (docs/DATA.md maker-checker workflow).
Never insert directly into the database.

# GUJCET (Gujarat Common Entrance Test) — eligibility research

Researched for BCION Lite content pipeline. Every fact below carries its
source URL, the date it was accessed, and a confidence note. Facts that
could not be confirmed on an official page are marked "not found, needs
manual verification" rather than estimated.

Access date for all entries below (unless noted otherwise): **2026-09-19**.

## Official sources checked

- `https://gujcet.gseb.org/` — GSEB's GUJCET site. Homepage returned SSC
  Purak (supplementary) 2026 exam results content when fetched; no
  eligibility page was reachable at `/eligibility` (404). The domain is
  confirmed live and GSEB-run, but its eligibility content could not be
  located in this session.
- `https://www.gseb.org/` — GSEB main site. Fetched homepage; it also
  surfaced SSC Purak result content, not GUJCET eligibility.
- `https://acpc.gujarat.gov.in/` — ACPC (Admission Committee for
  Professional Courses), Gujarat's official body for centralized
  engineering/pharmacy admissions. This is the authority that actually
  publishes eligibility rules (GUJCET itself is the entrance test; ACPC
  sets the admission eligibility that uses GUJCET/JEE scores). Homepage,
  `be-b-tech`, `be-btech-rules`, and `degree-diploma-pharmacy` pages were
  fetched.
- `https://acpc.gujarat.gov.in/assets/uploads/media-uploader/notification-bachelor-of-engineering-and-technology-dated-140320241710491627.pdf`
  — official BE/B.Tech admission-rules notification dated 14.03.2024,
  linked from the `be-btech-rules` page. This is a scanned PDF (image-based,
  no extractable text with the tools available in this session), so its
  clauses could not be read and are not used as sources for any fact below.

## Facts

### 1. Required subjects — Engineering (PCM) and Pharmacy (PCB/PCM)

- **Fact:** ACPC's BE/B.Tech course page groups qualifying subject
  combinations as "Physics, Chemistry and Mathematics (Merit Group: PCM)"
  and "Physics, Chemistry and Biology (Merit Group: PCB)" for branch-wise
  eligibility documents.
- **Source URL:** https://acpc.gujarat.gov.in/be-b-tech
- **Access date:** 2026-09-19
- **Confidence:** unclear-needs-verification — the page references these
  merit-group labels in its list of branch-wise/qualifying-subject-wise
  eligibility documents, but the full clause text (e.g. exact minimum
  subject combinations per branch) sits inside a linked PDF that could not
  be read in this session (see PDF note above). Treat the PCM/PCB grouping
  itself as well-attested by the official page structure, but do not treat
  any more specific subject rule as confirmed.
- **Not verified:** the precise required-subject rule for Pharmacy
  (B.Pharm/D.Pharm) specifically — not found, needs manual verification
  from `https://acpc.gujarat.gov.in/degree-diploma-pharmacy`'s linked
  notifications or `https://acpc.gujarat.gov.in/deg-dip-pharmacy-rules`
  (neither notification PDF was read in this session).

### 2. Age limit

- **Fact:** not found, needs manual verification. No official GSEB or
  ACPC page reachable in this session stated a minimum or maximum age for
  GUJCET or for ACPC-administered admission. The only content located on
  official domains (GSEB homepage, GUJCET site, ACPC BE/B.Tech and
  Pharmacy pages) did not mention an age criterion at all.
- **Sources checked (no age information found):**
  https://gujcet.gseb.org/, https://www.gseb.org/,
  https://acpc.gujarat.gov.in/be-b-tech,
  https://acpc.gujarat.gov.in/be-btech-rules,
  https://acpc.gujarat.gov.in/degree-diploma-pharmacy
- **Access date:** 2026-09-19
- **Confidence:** not found, needs manual verification.

### 3. Minimum qualifying marks (percentage)

- **Fact:** not found, needs manual verification. No official GSEB or
  ACPC page reachable in this session stated a minimum qualifying
  percentage in Class 12 (general category or reserved-category) for
  GUJCET or ACPC admission. The specific figures (e.g. any percentage for
  general category, or a lower percentage for SC/ST/SEBC/EWS) exist only
  in third-party aggregator sites (CollegeDekho, Careers360, etc.), which
  are explicitly excluded as sources per this task's instructions, and in
  the scanned PDF notification that could not be read.
- **Sources checked (no marks-percentage information found in readable
  text):** https://acpc.gujarat.gov.in/be-b-tech,
  https://acpc.gujarat.gov.in/be-btech-rules,
  https://acpc.gujarat.gov.in/degree-diploma-pharmacy
- **PDF not read:** the 14.03.2024 BE/B.Tech notification PDF (linked
  above) likely contains this figure but is a scanned/image PDF that
  could not be OCR'd or text-extracted with the tools available in this
  session.
- **Access date:** 2026-09-19
- **Confidence:** not found, needs manual verification.

### 4. Domicile requirement

- **Fact:** not found, needs manual verification, as an explicit quoted
  clause. ACPC's site structure (a dedicated "J&K admission" page/category
  separate from the general BE/B.Tech and Pharmacy tracks) implies Gujarat
  domicile is a distinguishing factor in ACPC's admission categories, but
  no official page fetched in this session stated an explicit domicile
  rule (e.g. "must have studied Class 10/12 in Gujarat") in readable text.
- **Source URL (structural evidence only, not a quoted rule):**
  https://acpc.gujarat.gov.in/ (see "J&K admission" nav item)
- **Access date:** 2026-09-19
- **Confidence:** not found, needs manual verification.

### 5. Category/reservation facts (SC/ST/SEBC/EWS etc.)

- **Fact:** not found, needs manual verification. No specific reservation
  percentages, category list, or category-linked mark relaxation was
  found in readable text on any official page fetched in this session.
- **Access date:** 2026-09-19
- **Confidence:** not found, needs manual verification.

## What was NOT used as a source

Search results surfaced numerous third-party aggregator/coaching sites
(CollegeDekho, Careers360, CollegeBatch, TestPrepKart, UniversityKart,
BetterStudy, CampusOption, myexams.ai, collegereviewz, gujcom.com, and
similar) that state specific figures — commonly cited as "45% general /
40% reserved category" and "age not less than 17 years" — for GUJCET
eligibility. Per this task's instructions, these are excluded as sources
because they are not gseb.org, ACPC's official site, or an equivalent
government page. They are not reproduced as facts here. If a human
reviewer independently confirms these figures against an official GSEB
notification, GR, or the readable text of an ACPC notification PDF, they
can be added with a proper official citation.

## Next steps for a human reviewer

1. OCR or manually open the ACPC BE/B.Tech notification PDF (14.03.2024,
   linked above) and the "GR for eligibility and Merit for First Year
   Degree Engineering and Pharmacy 2021" (and its 2022 amendment),
   referenced from https://acpc.gujarat.gov.in/be-btech-rules, to extract
   the exact minimum-marks, age, domicile, and category-reservation
   clauses.
2. Check `https://acpc.gujarat.gov.in/deg-dip-pharmacy-rules` for the
   pharmacy-specific equivalent notification.
3. Check the current GUJCET information brochure/notification on
   `https://gujcet.gseb.org/` once its navigation/menu is located (the
   homepage fetched in this session returned unrelated SSC Purak result
   content, suggesting either a redirect, a CMS issue, or that the
   eligibility page lives at a URL not discovered in this session).
4. Once facts are confirmed against readable official text, route them
   through the normal maker-checker verification workflow
   (`docs/DATA.md`) before any fact from this draft is published.
