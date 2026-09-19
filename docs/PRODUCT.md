# Product scope — BCION Lite

Source: `docs/BCION-DPR-v1.1.md`, Annex C.3 and Annex D.2. This file is the
scoped summary; the annex is authoritative on conflict.

## Objective
Within five minutes a student understands their options and knows their
next useful action. First result after quick start: three routes worth
comparing, each with "why am I seeing this".

## The one journey
Explore → compare three pathways → calculate time and cost → see
requirements → save next actions. Seven screens plus an admin area.

## Emotional progression
Uncertainty → exploration → comparison → provisional decision → action →
review. Never assessment → score → label.
- Use: "Explore this route", "Save as an option", "You can change this
  later."
- Never: "Your perfect career", "You are 92% suitable", "You must choose
  science."

## Navigation (four destinations + utility menu)
| Destination | Purpose |
| --- | --- |
| Explore | Discover careers and routes |
| Compare | Examine two or three shortlisted pathways |
| My Plan | Current decision, next three actions, saved alternatives, what changed |
| Saved | Careers, programmes and sources to revisit |

Account, language and privacy live in a utility menu — not a fifth
destination. No ten-tile home screen.

## Coverage ceilings (pilot)
| Item | Ceiling | Chosen around |
| --- | --- | --- |
| Career families | 20–30 | What the first 100 users actually ask about |
| Exams | 8–10 | JEE Main, JEE Advanced, NEET-UG, CUET-UG, CLAT, NDA, SSC CGL, IBPS PO, plus the pilot state's CET/recruitment exams and one on demand |
| Programme records | 50–100, sourced fees/seats/admission route | Government institutions in the pilot state, plus NIRF top-50 nationally |
| Scholarships | 10–20 | State schemes plus NSP and PM Vidyalaxmi |
| Admission rules | One state, in detail | Pilot state (see `docs/DECISIONS.md`) |
| Languages | English + Hindi; Hinglish accepted as input | Critical content reviewed in both |

## Explicitly out of scope for Lite
Mock tests, social features, native apps, an inbound WhatsApp bot (only one
opt-in outbound deadline template), voice, lender integrations, psychometric
scoring, autonomous web research, a counselling service.

## Users
Student (primary) · Parent (student-approved family summary, never a
dashboard) · Teacher (session guide + printable prompts + referral route,
no analytics at 100-user scale) · Support staff (authorised case summary
only, never a model-generated label) · Reviewer/editor (publishing console).

## Success measures (feed Annex C.4 / DPR Section 29)
- Share of interactions served without a model call (target: Tier 0 dominant)
- Support/escalation requests per 100 users per month
- Editor hours per verified programme record and per exam rule
- AI cost per Hindi-adjusted answer
- Pre/post decision-quality instrument (5 items, at sign-up and week 4):
  can name three pathways, total cost of first choice, next deadline, a
  backup option, one scholarship they're eligible for
- Whether one school lets ~30 Class 10–12 students use it under parental
  consent
- Return visits in weeks 2–4 after sign-up
