
# BCION — Bharat Career Intelligence & Opportunity Network


## Detailed Project Report (DPR) and White Paper — Version 1.1

Sep 19, 2026 · @Someone

## Read this first

This is the consultation draft for steering-committee review. It supersedes v1.0 and absorbs an external critique; every material change is logged in Annex B.
Status. Not ready for funding approval. Ready for a sponsor decision and a Phase −1 appraisal.
Evidence labels. Every number in this document carries one of six tags:
| Tag | Meaning | How to treat it |
| --- | --- | --- |
| [OF] | Official current fact | Re-verify against the current official text before commitment |
| [HF] | Historical official figure | Correct at the stated date; may have moved |
| [PA] | Planning assumption | Our estimate; must be replaced by Phase 0 data |
| [PT] | Pilot or phase target | A goal we commit to, not a forecast |
| [CE] | Cost estimate, ±30% | Top-down; bottom-up model due in Phase 0 |
| [UH] | Unvalidated hypothesis | Came from the simulated workshops; needs field validation |

Sponsor assumption. No sponsor has been named. The base case in this DPR is a central anchor (Ministry of Education, Department of School Education and Literacy) with states as instance owners and existing state career-portal programmes as migration partners. If the real sponsor is a single state, Annex A gives the state-instance variant with its own scope and numbers. The sponsor question is the first Phase −1 decision and changes scale, governance and cost.
Lite pilot. The 10–100 user software pilot ("BCION Lite") has its own consolidated plan: `docs/BCION-Lite-Build-Pack.md`. It is a proof of concept that precedes Phase −1. Its budget is thousands of rupees a month plus development time; the crore-level figures in this DPR describe a national organisation and do not apply to it.
Simulations. All consultations in Part 2 are simulated design workshops with fictional composite personas. They produce hypotheses, not evidence. Institutions appear only as roles.
Rules move. References to the DPDP Act 2023 and Rules, NEP 2020, CERT-In directions, NSQF, NCO-2015, NSP, PM Vidyalaxmi and similar must be re-verified against the current official text before any commitment.
What changed from v1.0 in one paragraph. The pilot is cut by roughly 80%. "Full coverage" is replaced by readiness-based coverage with published readiness levels. Five-year cost falls from ₹385–470 crore to ₹210–270 crore in the recommended scenario, because scale targets are cut, not because unit costs fell. Earned revenue is assumed at zero in the base case. A counsellor capacity model, a governance options analysis, a pre-approval phase and an incumbent analysis are added. The incumbent analysis matters most: state-level career portals already exist in more than a dozen states, and v1.0 did not mention them.

## Verdict in brief

Conditional GO for a pilot, not for a national programme. Approve Phase −1 (sponsor and appraisal) and, on approval, Phases 0–1 as a single ₹26–34 crore [CE] tranche. Everything after Month 18 is contingent on gate results.
Works at national scale: a verified-data platform with deterministic decision tools and an AI interface, human counsellors for high-stakes cases, funded as a public good, rolled out state by state with published readiness levels, and built to absorb rather than compete with the state career portals that already exist.
Does not work: a free, fully AI-driven, real-time, all-India, all-exams, all-colleges, lifelong system. It fails on cost, data accuracy, child safety and stakeholder conflict. v1.0 correctly rejected this, then rebuilt most of it in Phase 3. v1.1 removes that.
Core design rule: AI is the interface and explainer, never the source of truth. The moat is the verified knowledge base, the provenance model and the neutrality charter, not the chatbot.
Funding shape: ₹210–270 crore [CE] over five years in the recommended scenario, released in three milestone-gated tranches (Section 27). Earned revenue is assumed at zero in the base case; any revenue is upside.
Three decisions the steering committee must take before anything else:
- Who is the sponsor, and is the scope national or one state?
- Does BCION absorb existing state career portals or run beside them?
- Which governance model (Section 20): government mission, independent Section 8, or federated consortium?

# PART 1 — CONCEPT STRESS TEST


## 1.1 Strengths of the original concept

The problem is real and the shift from information to decision support is the right one. Career information is fragmented across dozens of official sites; stream and course choices are made late, on hearsay and family pressure; government colleges, ITI and polytechnic routes, scholarships and credit-guarantee schemes stay hidden from the families who need them most. NEP 2020 pushes career exposure from the middle stage, and public digital infrastructure (DigiLocker, APAAR, NSP, PM Vidyalaxmi, NCS, SWAYAM, DIKSHA) exists to plug into. Falling model prices make a tiered AI design affordable. The biggest beneficiaries are first-generation, rural and low-income students with no informal advisers.

## 1.2 Weaknesses

- Scope: crores of students plus parents, schools and institutions, across 28 states, 8 union territories, 22 scheduled languages, thousands of exams and roughly 45,000 colleges [HF, AISHE].
- Data ownership is scattered. No authority publishes clean, current, machine-readable fees, cut-offs, seats and reservation rules.
- Value depends on trust. One widely shared wrong deadline damages credibility for years.
- Adoption is not automatic. Students already have YouTube, Telegram, WhatsApp groups, coaching apps and Careers360-type portals.
- The brief assumed nothing like this exists. It does (1.3).

## 1.3 The incumbents nobody checked

State career portals already exist and v1.0 did not mention them. Rajasthan launched India's first state career portal with UNICEF support in February 2019, listing 237 professional and 200 vocational careers, 955 competitive exams, 960 scholarships and 10,000 institutions for Classes IX–XII [HF, Drishti IAS]. Maharashtra followed in May 2020 with a Marathi–English portal for an estimated 66 lakh students, built with MSCERT and offering 500+ career options [HF, Careers360]. By July 2021, 14 state career portals had been built with UNICEF support by iDreamCareer's non-profit arm, covering 21 million+ students, free to states and students, with two trained teachers per school and a live programme dashboard for each state education department [HF, Millennium Post, Anil Swarup].
| Incumbent type | What it already has | Gap BCION must prove it fills |
| --- | --- | --- |
| UNICEF-supported state career portals (14+ states) | Career, exam, scholarship and institution catalogues in state language; school-linked; teacher training; state dashboards; psychometric assessment | Undated content without provenance; no decision engines (cost, eligibility, timeline, reservation); no national exam layer; no cross-state portability; maintenance depends on a single vendor and donor |
| Private portals (Careers360, Shiksha, CollegeDekho) | Coverage of 30,000+ colleges and 500+ exams, Q&A, rank predictors | Lead-driven, paid placement, unverified claims, predictions presented as fact |
| NCS (National Career Service) | Jobs, some counselling | Not school-stage; no decision tooling |
| NCERT Tamanna | Aptitude test for Classes 9–12 | A test, not a journey |
| SWAYAM, DIKSHA, NPTEL | Free content | Not linked to decisions |
| NSP, PM Vidyalaxmi | Official schemes and loans | Discovery, eligibility matching, total-cost view |
| NIRF, NAAC, NBA, AISHE | Official ratings and data | Not student-facing; no fee or cost integration |
| DigiLocker, APAAR, ABC | Verified records | Not a guidance layer |
| NTA, boards, commissions | Authoritative notices, often PDF | No unified calendar or alerts |
| Coaching apps | Test series, video | Commercial bias, cost |
| YouTube, Telegram, WhatsApp | Reach | Unverified, rumour-prone |

Implication. BCION's original pitch, a decision layer over public infrastructure, is already partly built at state level by a donor-funded vendor. Any steering committee with a state-education official present will ask why not fund the existing programme. The DPR answers in Section 7: BCION adds provenance and freshness SLAs, deterministic decision engines, a national exam and reservation layer, multi-channel access, a neutrality charter and open data. The strategic posture is absorb, not compete: existing portals are offered a migration path, and at least one pilot state must be one that already has a portal, so the pilot measures BCION's marginal value rather than the value of career guidance in general.

## 1.4 Contradictions in the brief

| # | Brief says | But | Resolution |
| --- | --- | --- | --- |
| 1 | Free for students | Verified data at national scale needs a large human workforce | Public-good funding; no earned revenue assumed (Section 27) |
| 2 | Lightweight system | Monitoring hundreds of official sources with human-grade accuracy is heavy | Light compute, heavy data operations |
| 3 | Real-time | Official sources publish irregularly, often as scanned PDFs | Tiered freshness SLAs with visible timestamps (Section 11) |
| 4 | No information without verification | 45,000 colleges and every state exam cannot be verified on day one | Coverage in waves; unverified fields shown as "not verified", never guessed |
| 5 | Life-span calculator "like a SIP" | SIP maths is deterministic; careers are not | Scenario ranges with named assumptions (Section 13) |
| 6 | Neutral guidance | Coaching, universities and lenders all have commercial interests | Neutrality Charter: no paid placement, no lead sales (Section 20) |
| 7 | Connect students with everyone | Minors and unverified adults do not mix safely | Structured, moderated channels only; no open chat (Section 19) |
| 8 | AI-generated mock tests | Unvalidated questions can be wrong or unfair | Human-reviewed item bank, calibrated before adaptive testing (Section 18) |
| 9 | Every student from Class 8 | Many students have no personal phone or stable data | Multi-channel: WhatsApp, voice (Phase 2), school-based access, offline packs |
| 10 | Government alignment | Independence is needed for credibility | Governance options compared, not pre-decided (Section 20) |
| 11 | National platform | 14+ states already run career portals | Absorb, not compete; federated design |


## 1.5 What v1.0 got wrong

- It criticised the super-app, then rebuilt it in Phase 3: full coverage, 22 languages, 5 crore registered, adaptive testing, alumni mentors, industry integration. Phase 3 was a storage room for unrejected features.
- The pilot was a programme, not a pilot: 10 lakh registered, 2,000–3,000 schools, five languages, three channels. Failure would not have shown whether the concept or the execution was wrong.
- Human-in-the-loop was a slogan: 100 counsellors at 100 cases each is 10,000 cases, exactly 1% of 10 lakh registered. At 2% referral it collapses.
- Earned revenue of 15–20% had no named buyer. Institutions already file the same data with AISHE and NIRF for free.
- 99.9% availability with a four-hour RTO is arithmetically incoherent; one outage consumes the month.
- Data residency was framed as a legal mandate; it is a policy choice.
- Cryptographic signing was presented as data quality; it proves only that a record was not altered after publication.
- No sponsor, no appraisal timeline, no governance option analysis, no incumbent analysis.

# PART 2 — SIMULATED DESIGN WORKSHOPS

Every session below is a simulated design workshop. Its outputs are hypotheses requiring field validation, not evidence. Ten sessions, 1–14 September 2026 (illustrative dates). Personas are fictional composites; institutions appear only as roles. Each session ends with the decisions taken and the validation still owed.

## Workshop 1 — Students (Tue 1 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: Riya (Class 10, urban private school); Arjun (Class 12, small-town government school, JEE aspirant); Sunita (Class 11, rural, first-generation, shares a family phone); Vikram (23, graduate preparing for SSC and a state exam).
Riya wants a stream-to-career map, not a personality test, and will quit anything that opens with 40 questions. Arjun knows JEE but not state counselling or fee differences; he wants an instant Plan B and distrusts anything that looks like a coaching ad. Sunita has evening-only phone access, limited data and an English barrier; she wants voice in her language and a small app. Vikram misses form dates, age relaxations and attempt limits; his Telegram groups are full of unverified news.
Opposing views: Riya likes a "career score"; Sunita and Arjun fear being told they are "not suited". Arjun would use a rank predictor daily; Vikram warns predictions will be wrong and cause panic. Reasons they may not use it: too many apps, OTP friction, ads, fear that marks and phone numbers are sold to coaching, generic advice, no way to check AI answers.
Decisions: 5-minute quick start with progressive profiling; core tools usable without login; WhatsApp and a lite app as first-class channels, voice in Phase 2; every pathway shows Plan B and Plan C; ranges, never single-number predictions; no ads, no lead selling; opt-in alerts that always show source and date.

## Workshop 2 — Parents (Wed 2 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: a government-employee father (tier-2 city); a small-business owner mother; a farmer father (rural); an IT-professional mother (metro); the father of a Class 10 girl.
Trust: "Who runs this? A private company will sell my child's data." Government association builds trust but raises fears of glitches. "Free" sounds suspicious; parents fear upselling into coaching. Strong preference for medicine, engineering and government jobs; newer careers raise doubt. The farmer father's first question is total cost and whether a nearby government college exists. For girls, hostel safety, distance and fee waivers shape decisions more than interest does. Privacy: the government-employee father wants full visibility; the IT mother wants her child's autonomy; the girl's father fears strangers contacting his daughter.
Decisions: age-tiered visibility (linked parent view for younger students, shared summaries with the student's knowledge for older ones); a Parent Guide mode leading with cost, risk and stable-pathway comparisons; verifiable parental consent for under-18s per the DPDP Act; no third-party contact; transparent funding and governance disclosure; hostel, safety, distance and fee-support information in every institution profile.

## Workshop 3 — Teachers (Thu 3 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: a government secondary-school teacher (55 students per class); a private-school Class 11–12 commerce teacher; a state-board principal.
The government teacher has no career period, guides from dated personal knowledge, and fears blame for AI errors more than replacement. The private teacher notes that school management often has informal arrangements with coaching centres and would resist neutral advice. The principal needs an official circular, near-zero administrative burden, and school-level insight without exposing individual students to management. One teacher in the room has used a UNICEF-type state portal: "Good catalogue, nobody updates it, and it does not know our state's counselling rounds."
Decisions: "AI assists, teachers facilitate, counsellors escalate." Teacher dashboard with anonymised class-level insights by default; a ready 40-minute Career Period kit with offline PDFs; no extra data entry; a 4-hour micro-training; onboarding through the state or board channel; individual data never visible to management without consent; where a state portal exists, BCION appears inside the same teacher workflow rather than as a second login.

## Workshop 4 — Counsellors (Fri 4 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: an urban school counsellor; a clinical psychologist and psychometrician; an independent career counsellor (25 years); an NGO student-wellbeing lead.
Interest inventories are useful; imported aptitude tests for minors mislead without Indian norming; labels such as "you are type X so not medicine" are harmful. Exam stress and self-harm risk are real; AI must detect distress language and route to humans. Family conflict, financial limits and ability–ambition mismatch need conversation. The psychologist wants no personality claims; the independent counsellor says students want a structured profile; the NGO lead insists on family-level counselling; independent counsellors may see the platform as competition. The counsellors also challenge the capacity plan: "How many of us, for how many students, at what referral rate?" (answered in Section 19).
Decisions: "exploration, not diagnosis"; validated, normed interest and values tools only; language of possibilities, never "not suited"; a crisis protocol with immediate helpline information and human follow-up; four tiers (self-serve, teacher-facilitated, certified counsellor, crisis) with funded slots for low-income students; a certified counsellor network with standards, supervision and honorarium; assessment data never reused.

## Workshop 5 — Coaching industry (Mon 7 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: founder of a national coaching chain; founder of a small regional institute; a senior physics faculty member; a senior civil-services and SSC faculty member.
Coaching reaches students directly and holds syllabus and trend expertise; faculty acknowledge many students cannot afford coaching. The national founder: "If your AI says free resources are enough, enrolment drops." He wants lead access, prominent placement and topper showcases. The regional founder fears favouritism toward national brands. Selection claims are often inflated (counting test-series students); fees, batch sizes and refund terms are opaque. Lead access stays unresolved.
Decisions: no commercial inputs to the recommendation engine; no paid placement; no student data or leads shared; coaching appears only as standardised disclosure profiles (fee, batch size, refund policy, audited outcome definitions) and only in Phase 3; openly licensed contributions under editorial review; honest "Do you need coaching?" guidance stays.

## Workshop 6 — Universities (Tue 8 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: a Vice-Chancellor (state university); a Dean (private university, engineering); an Admission Head (centrally funded institution).
Institutions already report to AISHE, NIRF, NAAC and AICTE and resent duplicate reporting; they cooperate if BCION reuses submitted data. The Dean wants visibility and leads; the Vice-Chancellor fears unfavourable comparison; the Admission Head wants accurate public information to cut helpdesk load. Rankings differ by method and can be gamed; placement figures are inconsistent. Public institutions lack staff to maintain profiles. The VC on paying for data services: "We already give this to AISHE for free. Why would we pay you?" This kills the v1.0 revenue line (Section 27).
Decisions: a named Institution Data Steward per institution and a claim-and-verify portal; two data tracks, "Official/verified" and "Self-declared (unverified)"; third-party rankings shown with source, year and method; BCION never makes its own composite rank; standard definitions for median placement, percentage placed and total programme cost; alignment with regulatory datasets; anonymised aggregate demand analytics for institutions; enquiries only when a student initiates.

## Workshop 7 — Government (Wed 9 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: a state school-education official; a UGC representative; an AICTE representative; a central skill-development official.
Strong NEP 2020 fit. Officials do not want another silo beside NCS, SWAYAM, DIKSHA, NSP, PM Vidyalaxmi, DigiLocker and Skill India Digital Hub. The state official: "We already have a career portal with UNICEF. Are you replacing it, or asking us to run two?" Who is accountable for errors? Endorsement cannot be automatic. Regulators say the highest-value function is showing recognition and approval status prominently, because fake universities and unapproved courses trap students. Domicile rules, local reservations, exam calendars and medium of instruction differ by state; some states will see a central platform as overreach. Skills officials insist ITI, polytechnic and apprenticeship routes must not be sidelined. The central voice suggests mandating use through schools; the state official cautions against mandates without capacity.
Decisions: position BCION as a decision layer that integrates by API or deep link; governance model to be chosen from three options after legal assessment (Section 20); verification-partner protocols with regulators and exam authorities; state instances with state data stewards; migration path for existing state portals; recognition and approval status prominent for every programme; parity for vocational pathways; clear disclaimers and a public correction SLA; a pre-approval phase for sponsor decision and scheme appraisal.

## Workshop 8 — Banks and finance (Thu 10 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: head of education loans (public-sector bank); a product head (private bank); an NBFC representative; a CSR-funded scholarship foundation head.
Rates, collateral thresholds, moratoriums, interest subvention and credit-guarantee schemes are poorly understood. Banks want informed demand and fewer document rejections. A "course risk score" would attract lenders but could red-line courses and colleges unfairly. Students over-borrow for low-outcome courses. Scholarship uptake is low because of awareness and documentation gaps; providers want student-level data to disburse, which conflicts with privacy. The NBFC wants lead sharing; the public-sector bank calls lead selling inappropriate.
Decisions: neutral loan comparison showing total repayment and EMI against sourced income ranges, labelled "not financial advice"; identical fields for all lender types, no lender-paid ranking; no lead sales; applications through official portals or deep links; scholarship matching with document checklists and deadline alerts; providers publish schemes after verification and receive aggregate analytics only; a "cost before choice" nudge in every college flow.

## Workshop 9 — Industry (Fri 11 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: an IT-services HR head; a manufacturing group skills head; an AI startup founder; a sector skill council representative; an apprenticeship-platform lead.
Skills in demand: AI literacy, data, cybersecurity, allied healthcare, electronics manufacturing, EV, green energy, logistics, skilled trades. The founder warns against promising "AI jobs"; entry-level roles are being reshaped and forecasts are unreliable. Graduates lack practical and communication skills; internships are poorly distributed. The founder says skills change too fast for fixed pathway maps; the HR head says degrees still filter hiring; the skill council says trades pay well but carry stigma.
Decisions: labour-market signals shown as ranges with source and date, refreshed at least annually; skill clusters aligned to NSQF and NCO-2015 instead of job-title promises; internship and apprenticeship listings only from verified employers, initially via government portals; future-proofing comparisons, not predictions; no salary or job guarantees; industry may contribute openly licensed skill maps but cannot influence recommendations.

## Workshop 10 — Technology team (Mon 14 Sep 2026)

Simulated design workshop — hypotheses requiring field validation.
Participants: chief architect; AI/ML lead; data-engineering lead; security and privacy lead; FinOps/DevOps lead; accessibility and multilingual UX lead.
A chat-first design that sends every query to a large model costs several times the affordable budget; the alternative is deterministic tools, retrieval and model routing. Dates, fees, eligibility and cut-offs must come from the database, never from model memory. Result days and deadlines create spikes of millions of users within hours; the answer is CDN, pre-rendered public pages and queues. Minors' data and sensitive attributes need strict handling. AI agents propose data changes from monitored official sources; humans approve critical ones. Voice quality is weaker in lower-resource languages. The AI lead wants autonomous data updates; security and data leads insist on maker-checker for critical fields. FinOps wants hard budget caps. The FinOps lead also flags what v1.0 left out of the cost model: WhatsApp conversation charges, telephony minutes, peak-season support staff and translation QA.
Decisions: deterministic engines for eligibility, cost, reservation and lifespan maths; verified database plus retrieval with mandatory citations; a model gateway with a small-model-first cascade and a per-user daily token budget; precomputed pathway templates; semantic caching, structured outputs, context compression, offline batch generation; model-agnostic, multi-vendor design with self-hosted open-weight models for routine work; human maker-checker for all Tier-1 data; an AI cost cap per monthly active user reviewed quarterly; messaging and telephony costed as separate lines.

## Hypotheses produced by the workshops and how each will be validated

| Workshop conclusion | Status | Required validation | When |
| --- | --- | --- | --- |
| Students reject long assessments; 5-minute quick start works | [UH] plausible | Usability testing across age, language and device groups | Phase 0 baseline; Phase 1 A/B |
| Parents prefer linked visibility for younger students | [UH] disputed | Consent and family research; DPDP-compliant consent flow testing | Phase 0 |
| WhatsApp will be the dominant access channel | [UH] unproven | Channel-cost and adoption pilot; message-charge measurement | Phase 1 |
| Schools adopt only with an official circular | [UH] highly plausible | State-specific administrative interviews | Phase 0 |
| Teachers will run a 40-minute Career Period with a kit | [UH] unproven | Classroom trials in 30 schools before the pilot | Phase 0–1 |
| Institutions will maintain self-declared profiles | [UH] doubtful | Claim-and-verify trial with 200 institutions | Phase 1 |
| Institutions will pay for data services | [UH] rejected | None; assumed zero revenue | — |
| Tier-3 counselling referral rate is 1–1.5% of registered per year | [PA] | Measured in the pilot | Phase 1 |
| Tier-0 handles 65–70% of interactions | [PA] | Measured from pilot logs | Phase 1 |
| Existing state portals will accept a migration path | [UH] unknown | Talks with 3 state education departments and the portal vendor | Phase −1 |
| A federated governance model is acceptable to states | [UH] unknown | Legal and institutional assessment; state consultations | Phase −1 |
| Distress detection can route safely without false alarms flooding counsellors | [UH] unproven | Red-team and precision/recall testing on Indian-language text | Phase 0–1 |


# PART 3 — CONSOLIDATED WORKSHOP OUTPUTS


## 3.1 Stakeholder feedback report

| Stakeholder | Top need | Top concern | Red line |
| --- | --- | --- | --- |
| Students | Fast, trusted answers and Plan B | Ads, data misuse, being labelled | No ads, no lead sales |
| Parents | Cost clarity, safety, trust | Child privacy, upselling | No third-party contact |
| Teachers | Ready material, low workload, one login | Blame for AI errors, replacement | No extra admin burden |
| Counsellors | Validity, referral pathways, realistic caseload | Labelling, distress missed | No diagnosis by AI |
| Coaching | Visibility, fair field | Loss of students | Leads not shareable |
| Universities | Fair representation, low reporting burden | Unfair ranking comparison | No duplicate reporting, no paid data services |
| Government (central) | No duplication, governance clarity | Errors, political sensitivity | Independence with accountability |
| Government (state) | Keep the existing portal's investment | Central overreach, two systems | No mandate without capacity |
| Banks and finance | Informed borrowers, fewer rejections | Mis-selling, over-borrowing | No lender-paid ranking |
| Industry | Skills pipeline | Hype, false promises | No guaranteed "AI jobs" |
| Technology | Sustainable cost, safety | Hallucination, spikes, breaches | Human check on critical data |


## 3.2 Major agreements

- Free for students, no ads, no sale of data.
- Every fact carries source, date and verification status.
- AI explains and personalises; databases and rules decide facts.
- Teachers and counsellors stay in the loop; AI extends them.
- Recognition and approval status is prominent for every programme.
- Vocational and skill pathways have parity with degrees.
- Ranges and scenarios replace predictions.
- A public correction channel with an SLA.
- Existing state portals are partners with a migration path, not competitors.

## 3.3 Major disagreements and decisions

| Issue | For | Against | Decision |
| --- | --- | --- | --- |
| Lead sharing with coaching and NBFCs | Coaching, NBFC, private university | Students, parents, PSU bank, privacy | Refused; student-initiated contact only |
| Parental visibility | Government-employee father, principal | IT mother, counsellors | Age-tiered visibility [UH] |
| Autonomous AI data updates | AI lead | Security and data leads | Autonomy for low-risk fields only |
| Personality profiling | Independent counsellor, some students | Psychologist | Interest and values exploration only |
| Central mandate for schools | Central official | State official | Opt-in via state channels |
| Promoted listings | Private university, coaching | Regional coaching, public universities | Refused |
| Course risk scoring for lenders | Banks | Students, counsellors | Refused |
| Paid institutional data services | v1.0 revenue plan | Vice-Chancellor, admission head | Dropped from base case |
| Replace or run beside state portals | Central official (replace) | State official (keep) | Absorb with migration path; federated governance |
| Speed of coverage | Product, government | Data ops, security | Readiness-based coverage with published levels |


## 3.4 Top project risks (detail in Section 28)

Wrong critical data; funding gap; neutrality erosion; child safety and privacy breach; low adoption; institution non-cooperation; AI misguidance; governance capture; result-day outages; digital divide; state non-participation; counsellor capacity shortfall.

## 3.5 Features removed or deferred

| Feature in brief | Decision | Reason |
| --- | --- | --- |
| Every exam, every state at launch | Readiness-based waves | Verification capacity |
| Every college in India at launch | Readiness-based waves | ~45,000 colleges; verification cost |
| "Full coverage" by Month 60 | Removed | Some states, authorities and regulators will not cooperate on schedule |
| All 22 scheduled languages by Month 60 | Target 15–18; 22 as readiness goal | Translation QA and speech quality per language |
| Open student-to-student chat | Removed | Child safety, moderation cost |
| Direct messaging with unverified adults | Removed | Child safety |
| Coaching marketplace and ranking | Removed (disclosure profiles, Phase 3) | Neutrality |
| Direct loan origination | Removed (deep links to official portals) | Regulation, mis-selling |
| AI-generated mock tests served directly | Removed | Quality; reviewed item bank instead |
| Predicted rank or career score | Removed | Panic, false precision |
| Personality type claims | Removed | Validity, labelling harm |
| Lifelong salary forecasting | Removed | Unreliable; scenario ranges instead |
| Full "real-time" promise | Reframed | Freshness SLAs |
| Alumni networking | Phase 3, conditional on verification capacity | Moderation, verification |
| Voice and IVR in the pilot | Deferred to Phase 2 | Cost, speech quality, pilot focus |
| Earned revenue in the financial base case | Removed | No named buyer |
| Independent Section 8 as the pre-decided legal form | Replaced by options analysis | Governance not yet assessed |


## 3.6 Features prioritised

Must have (Phase 1 pilot): quick-start profile and pathway explorer (40 career families); Career Life Span Calculator (40 careers); Exam Intelligence for 15 exams; institution profiles with recognition status, fees and cost calculator (500–700 programme records); reservation and counselling explainer (national plus pilot states); scholarship and loan finder with document checklists; personal dashboard and calendar with source-dated alerts; PWA plus WhatsApp; offline packs; coverage-readiness page per module.
Should have (Phase 2): reviewed mock-test bank and study planner; teacher dashboard and Career Period kit; counsellor network at scale; voice and IVR; 8 languages; bank and scholarship-provider integrations; state-portal migration tooling.
Later (Phase 3, each conditional on a readiness gate): adaptive testing once items are calibrated; coaching disclosure profiles; verified alumni mentors; industry internship integration; open APIs; longitudinal outcome study.

## 3.7 Phase-wise plan (summary; detail in Section 25)

| Phase | Months | Focus | Gate to next phase |
| --- | --- | --- | --- |
| −1 Pre-approval | −12 to 0 | Sponsor decision, legal form, scheme appraisal, state talks | Sponsor named; appraisal approved; Tranche 1 sanctioned |
| 0 Foundation | 0–6 | Governance, data model, legal, pilot design, core team | MoUs signed; schema approved; privacy assessment passed |
| 1 Pilot | 7–18 | 3 states, 150–250 schools, 100k–150k invited students | Critical-field accuracy ≥ 99%; MAU ≥ 30% of registered; decision-quality uplift shown |
| 2 Multi-state | 19–36 | 8–12 states, 8 languages, counsellor network | Cost per MAU on trajectory; safety audit passed; 2 state-portal migrations done |
| 3 National availability | 37–60 | All states offered; readiness-based coverage | Independent impact evaluation; funding renewal |


# PART 4 — DETAILED PROJECT REPORT


## 1. Executive summary

What. BCION is a free, multilingual platform that helps students from Class 8 onward make career decisions by combining verified data with provenance, deterministic decision tools (cost, eligibility, timeline, reservation) and AI-assisted explanation, with certified counsellors for high-stakes cases and a crisis protocol.
Why. Families make life-shaping decisions on fragmented, undated and often commercially influenced information. Existing public platforms are strong in their own domains but do not connect into one decision journey. State career portals exist in 14+ states [HF, 2021] but are static catalogues without provenance, decision engines or a national exam layer.
How v1.1 differs from the brief and from v1.0.
- AI is the interface, not the source of truth.
- Coverage grows by readiness level with published transparency, never "full coverage".
- "Real-time" becomes visible freshness SLAs with human verification of critical data.
- Open chat, lead sales, coaching marketplace, rank predictions and personality typing are removed.
- The pilot is small enough to fail informatively: 3 states, 150–250 schools, 100k–150k invited students.
- Existing state portals are absorbed through a migration path, not competed with.
- Governance is chosen from three assessed options; a pre-approval phase handles sponsor and scheme appraisal.
- Earned revenue is assumed at zero.
Scale targets [PT], all gated. Month 18: 50,000–70,000 registered, 15,000–25,000 monthly active. Month 36: 30 lakh registered, 8–10 lakh MAU. Month 60: 1.5–2 crore registered, 40–60 lakh MAU.
Cost [CE]. ₹210–270 crore over five years in the recommended scenario (lean ₹150–190 crore; high-service ₹310–390 crore). Year-5 run-rate ₹80–105 crore, or ₹150–200 per MAU per year. AI inference target ₹10–15 per MAU per year, hard cap ₹20.
Funding. Government grant-in-aid as anchor (75–85%), CSR and philanthropy (15–25%), earned revenue zero in the base case. Students never pay.
Recommendation. Conditional GO for Phase −1 and, on appraisal, Phases 0–1 as a ₹26–34 crore [CE] tranche. Later tranches contingent on gate results (Section 30).

## 2. Vision and mission

Vision. Every Indian student, regardless of language, location or income, can see the whole map of their options and the true cost of each route before deciding.
Mission.
- Give every student trustworthy, sourced and current career information.
- Convert information into decisions: time, cost, risk, backup.
- Keep teachers, counsellors and families in the loop.
- Stay neutral, free and safe for children.
- Strengthen what states have already built rather than duplicate it.
Design tests, applied to every feature before it ships. Would a first-generation rural student in a low-bandwidth area benefit? Would a wrong answer be catchable and correctable? Could a commercial actor buy influence? Does a state already do this well enough that BCION should integrate instead of build? The required answers are yes, yes, no, no.

## 3. Problem statement

- Fragmentation. Career information, exams, colleges, fees, reservation, scholarships, loans and skills sit on dozens of unconnected sites.
- Late and uninformed decisions. Stream choice at Class 10 and course choice after Class 12 are made on family pressure, social trends and hearsay.
- Hidden options. Government colleges, ITI and polytechnic routes, scholarships, credit-guarantee schemes and alternative careers are poorly known outside cities.
- Commercial influence. Much guidance comes from parties who benefit from a particular choice.
- No decision layer. Time, attempts, cost and risk are dimensions that no single tool shows together.
- Scarce counselling. Most schools lack a trained career counsellor [UH; a 2021 opinion piece cites 93% of schools without one, Millennium Post; Phase 0 baseline must establish the current figure].
- Stale state portals. Where portals exist, content is undated, provenance is absent and maintenance depends on a single vendor and donor [UH; validate with 3 states in Phase −1].

## 4. Market need analysis

Order-of-magnitude figures; every row must be replaced by the current official number in Phase 0.
| Indicator | Approximate scale | Tag | Source to verify |
| --- | --- | --- | --- |
| Students in Classes 8–12 | 8–10 crore | [PA] | UDISE+ |
| Higher-education enrolment | over 4 crore | [HF] | AISHE |
| NEET-UG candidates per year | over 20 lakh | [HF] | NTA |
| JEE Main candidates per year | over 10 lakh | [HF] | NTA |
| Recruitment-exam applicants | tens of lakhs per exam cycle | [PA] | SSC, RRB, IBPS, state commissions |
| Universities and colleges | ~1,100+ universities; ~45,000 colleges | [HF] | AISHE |
| Students already covered by state career portals | 21 million+ across 14 states (2021) | [HF] | UNICEF, state education departments |

Demand signals from the workshops [UH]. Students want fast "what after this?" answers; parents want cost and risk clarity; schools want ready material and one login; regulators want visible recognition status; states want their existing investment respected.
Reachable users [PA]. 15–25% of the Class 8–12 population at Month 60 (not the 40–50% in v1.0), reached primarily through schools and WhatsApp, with 25–35% monthly activity among registered users. This is the population that drives the 1.5–2 crore registered target.

## 5. Stakeholder consultation report

Ten simulated workshops (Part 2) and their synthesis (Part 3) shaped this DPR. The six findings that changed the design most:
- Trust beats features. Students and parents will use only what is ad-free, sourced and not selling data.
- Humans stay in the loop. Teachers and counsellors are the adoption channel, and their capacity must be modelled, not assumed.
- Neutrality is the product. Refusing lead sales and paid placement is a design constraint.
- Integrate, do not duplicate. Government wants a decision layer over existing platforms, including the state portals it already funds or hosts.
- Cost forces architecture. Tiered routing and precomputation are mandatory.
- Nobody will pay for what they already give away. Earned revenue leaves the base case.
All six are hypotheses. The Phase 0 baseline survey (students, parents, teachers in the three pilot states) and the Phase −1 state consultations are where they become evidence or get dropped.

## 6. Current ecosystem and incumbent analysis

The missing piece is a neutral, verified, connected decision layer with a national exam and reservation spine, not another content or listing site, and not another state catalogue.
| Category | Examples (types) | Strength | Gap BCION fills |
| --- | --- | --- | --- |
| State career portals | UNICEF-supported portals in 14+ states, built by one vendor | State language, school-linked, teacher training, state dashboards, free | No provenance or dates; no decision engines; no national exam layer; single-vendor and donor dependency |
| Public career portals | National Career Service | Jobs and career info | Little school-stage guidance or decision tooling |
| Aptitude assessment | NCERT Tamanna | Normed for Indian students | A test, not a journey |
| Public learning platforms | SWAYAM, DIKSHA, NPTEL | Free content | Not linked to decisions |
| Scholarship and loan portals | NSP, PM Vidyalaxmi | Official schemes | Discovery, eligibility matching, total-cost view |
| Ranking and accreditation data | NIRF, NAAC, NBA | Official ratings | Not student-friendly; no fee integration |
| Identity and credentials | DigiLocker, APAAR, ABC | Verified records | Not a guidance layer |
| Exam authorities | NTA, boards, commissions | Authoritative notices | PDF-heavy, no unified calendar |
| Private college-listing portals | Careers360, Shiksha, CollegeDekho | Broad coverage, Q&A | Lead-driven, paid placement, unverified |
| Coaching apps | Test series, video classes | Content and community | Commercial bias, cost |
| Social media | YouTube, Telegram, WhatsApp | Reach | Unverified, rumour-prone |

What BCION does that the state portals do not (the differentiator the steering committee will be asked for).
- Provenance on every fact: source, official URL, verification date, verifier, version history.
- Freshness SLAs with visible timestamps and a public correction channel.
- Deterministic decision engines: total cost, eligibility, attempts-and-age runway, reservation, scholarship match, EMI reality check.
- A national exam and reservation spine that a student keeps when they move states or apply outside their state.
- Multi-channel access: WhatsApp, offline packs, later voice; not only a web portal.
- A neutrality charter with published methodology and audits.
- Open data and APIs so state portals, NGOs and researchers can build on the verified base.
- A migration path: a state portal's catalogue is imported, deduplicated against the verified base, and its teacher workflow is preserved.
What BCION should not do. Build a psychometric assessment from scratch (license or partner), host video, run its own coaching, or ask any state to switch off a working portal before BCION's readiness level in that state exceeds it.

## 7. Proposed solution

Three layers, in build order: trust first, decisions second, guidance last.
- Trust layer. A verified knowledge base with provenance on every fact and a published readiness level per module and state.
- Decision layer. Deterministic engines: eligibility, cost, timeline and lifespan, reservation, scholarship match, EMI reality check. Versioned, testable, no model tokens.
- Guidance layer. AI explanation and personalisation over retrieved records; teachers with a Career Period kit; certified counsellors; crisis protocol.
Channels. Phase 1: lite Android app or PWA (under 10 MB), WhatsApp assistant, school-based access, printable and offline packs. Phase 2: voice (IVR and in-app) in regional languages. A text-only 2G mode is defined in Section 21.
Coverage transparency. Every module shows four counts for the student's state: records available, records verified, records within freshness SLA, records awaiting authority confirmation. This is the mechanism that replaces "full coverage".
Module mapping (original ten modules to final scope).
| # | Original module | Final scope | Phase |
| --- | --- | --- | --- |
| 1 | Career Discovery Engine | Quick-start profile, pathway explorer, licensed interest and values exploration | 1 |
| 2 | Career Life Span Calculator | Scenario-range calculator, 40 careers in pilot, ~300 at maturity | 1 |
| 3 | Exam Intelligence | 15 exams in pilot; readiness-based waves after | 1–3 |
| 4 | College Intelligence | 500–700 programme records in pilot; verified and self-declared tracks | 1–3 |
| 5 | Admission and Reservation | Explainers plus eligibility engine; national plus pilot states | 1–2 |
| 6 | Financial Intelligence | Cost calculator, scholarship finder, loan comparison, EMI check | 1–2 |
| 7 | Free Learning | Curated, reviewed, linked resources | 1–2 |
| 8 | AI Exam Prep | Reviewed mock bank and planner (Phase 2); adaptive only when calibrated (Phase 3) | 2–3 |
| 9 | Dashboard | Student, parent view, teacher dashboards | 1–2 |
| 10 | Stakeholder Network | Moderated structured channels; capacity-modelled counsellor network | 2–3 |


## 8. Platform architecture

```
flowchart TD  CH["Channels<br/>PWA · WhatsApp · School · Offline · Voice (P2)"] --> EDGE["Edge<br/>CDN · WAF · Bot protection · API gateway"]  EDGE --> EXP["Experience<br/>Student · Parent · Teacher · Counsellor · Steward · Admin"]  EXP --> DEC["Decision layer<br/>Eligibility · Cost · Timeline · Reservation · Scholarship"]  EXP --> GUI["Guidance layer<br/>Model gateway · RAG with citations · Guardrails · Crisis"]  DEC --> KB["Knowledge base<br/>Verified DB · Search · Vector · Source registry"]  GUI --> KB  OPS["Data ops<br/>Monitor → Extract → Maker-checker → Publish"] --> KB  STATE["State portal import<br/>Catalogue → dedupe → verify"] --> OPS  EXP --> VAULT["Student vault<br/>Encrypted · Consent ledger · Anonymised analytics"]
```

Reading: public tools hit the decision layer and knowledge base without touching the student vault; the guidance layer reads the knowledge base but has no write access to it and no access to the vault; existing state portals feed the data-ops pipeline as a source, not as a bypass.
Principles. Database-first; stateless services; API-first; open standards; model-agnostic; India-region hosting as policy (Section 23); open-source where practical; observability by default; a state instance is configuration plus data stewards, not a fork.

## 9. AI architecture

Rule. AI never invents facts. It retrieves, explains, translates, summarises and plans around verified records. If no record exists, the answer is "not verified".
Query routing (target mix at maturity [PA]; the pilot measures the real mix).
| Tier | Handles | Share of interactions | Method |
| --- | --- | --- | --- |
| 0 | Lookups, calculators, calendars, eligibility, cost | 65–70% | Database and rules; no model tokens |
| 1 | Simple Q&A, translation, summarisation, intent detection | 20–25% | Small model with retrieval |
| 2 | Personalised roadmap or study plan | 5–8% | Mid model with retrieval, cached templates |
| 3 | Complex counselling synthesis, unusual cases | 1–3% | Large model; human-escalation option |

Token optimisation. Precomputed pathway templates (careers × variants), so personalisation is parameter-filling; semantic cache and prompt caching; structured outputs and short system prompts; offline batch generation of explanations per language; a daily per-user token budget with graceful degradation to Tier 0; distillation of frequent Tier-2 tasks into small models after 12 months of real usage.
Cost model, stated honestly. v1.0 quoted ₹15 and ₹400 per million tokens for small and large models. Those are snapshots, not five-year prices. The bottom-up AI cost model in Phase 0 must include, separately: input and output token prices; Indian-language tokenisation overhead (often 2–4× English for the same content [PA]); retrieval and embedding costs; safety and distress-classifier calls; speech recognition and synthesis (Phase 2); GPU hosting utilisation for self-hosted models; vendor minimum commitments; evaluation and observability; failed and retried generations. Target ₹10–15 per MAU per year [PA]; hard cap ₹20, reviewed quarterly; automatic fallback to Tier 0 when the cap is approached. Price assumptions are re-quoted every quarter.
Guardrails. No guarantees; no "you are not suited"; no rank predictions as fact; answers must cite retrieved records; bias audits by gender, region, category and language; red-team testing before each release; distress detection routes to helpline information and human follow-up, with precision and recall measured in the pilot so counsellors are not flooded by false alarms; PII redaction before any external model call; student data never used to train models.
Interest and values exploration. Licensed or partnered, not built: a validated, openly licensed interest-inventory approach normed on an Indian sample with a university partner. It is exploration, not psychological testing. Where a pilot state already runs a normed assessment through its portal, BCION uses it.

## 10. Data architecture

Core entities. Career, Pathway, Exam, ExamCycle, Institution, Programme, CutoffSeatMatrix, Fee, Scholarship, LoanScheme, Resource, Skill, Source, Consent, StudentProfile, StateInstance, ReadinessLevel.
Provenance on every fact. Source, official URL, verification date, last-updated date, verifier (agent or human), confidence, version history. A fact without provenance cannot be published.
Career taxonomy. A "career" is an occupation family anchored to one or more NCO-2015 unit groups plus a qualification route, with 2–6 named pathway variants. Pilot: 40 careers. Maturity: about 300. The number is bounded by the taxonomy, not by what can be written.
Data zones.
- Public knowledge zone: open, versioned, exposed through public APIs and bulk downloads.
- Student vault: minimal, encrypted, consent-tagged, retention-limited.
- Analytics zone: anonymised and aggregated with minimum cohort sizes to prevent re-identification.
Minimisation. The quick start needs only class, interests, language and broad location. Marks, category and income are optional, used for eligibility only, encrypted separately, never used for recommendations beyond eligibility, never shared with institutions, deletable at any time.
Integrations (consent-based). DigiLocker and APAAR for records; NSP and PM Vidyalaxmi by deep link or API; exam-authority feeds under MoU; state portal catalogues imported as a source through the data-ops pipeline.

## 11. Freshness and verification system

"Real-time" is replaced by tiered freshness SLAs, visible timestamps and a public readiness page.
| Tier | Data | Monitoring | Publication SLA |
| --- | --- | --- | --- |
| 1 Critical | Exam notices, dates, deadlines, eligibility, application fees | Hourly in active windows, daily otherwise | Human-verified within 24 h (target 6 h in application windows) |
| 2 Cycle | College fees, seats, cut-offs, counselling rounds | Per admission cycle | Within 7 days of official release |
| 3 Annual | Rankings, accreditation, syllabus revisions | Monthly | Within 30 days |
| 4 Market | Skills demand, salary ranges, career trends | Quarterly | Refreshed at least annually |

Pipeline. Monitor (crawlers, RSS, change detection, MoU feeds, state-portal imports) → Extract (AI proposes structured changes) → Verify (rules checks; human maker-checker for Tier 1; sampling for lower tiers) → Publish (versioned, signed) → Notify (opted-in students by channel).
Controls. Allow-listed official sources only; conflicting sources flagged and held; signing of critical records to prove they were not altered after publication (this is tamper evidence, not accuracy; accuracy comes from authority matching, maker-checker and correction); a public "recently changed" log; a one-tap "report an error" with a correction SLA; a monthly data-quality dashboard.
Coverage transparency (per module, per state, published monthly).
| Count | Definition |
| --- | --- |
| Available | Records present in the knowledge base |
| Verified | Records matched to an official source with provenance |
| Within SLA | Verified records whose last verification is inside the tier's SLA |
| Awaiting confirmation | Records with a proposed change held for authority or maker-checker confirmation |

A readiness level (0–4) per module and state is derived from these counts and shown to students and to the steering committee. No state moves to "BCION recommended" status until Tier-1 exam data for that state is at level 4.

## 12. Student journey design

| Stage | Student need | BCION support |
| --- | --- | --- |
| Class 8–9 | Explore | Career awareness, subject-to-career links, interest exploration, stream preview |
| Class 10 | Choose stream | Stream-to-career map, cost and time comparison, Parent Guide |
| Class 11–12 | Prepare | Exam roadmaps, calendar, backup plans; mock tests from Phase 2 |
| After 12 | Choose course and college | Eligibility, counselling, reservation, cost, scholarships, loans |
| Undergraduate | Build | Skills, internships, PG and exam options |
| Early career | Transition | Skill clusters, apprenticeships, upskilling, government and private options |
| Gap, dropout, re-entry | Second chance | Bridge courses, ITI, open schooling, re-entry routes |

Entry and retention. Public tools work without login; login unlocks saved plans and alerts. Quick start in 5 minutes; the profile deepens gradually. Alerts are opt-in and relevant: deadlines, counselling rounds, scholarship windows. The pilot measures which of these actually drives return visits [UH]. Support beyond the first job is limited to transitions and upskilling; "lifelong" is out of scope for this DPR.

## 13. Career Life Span Calculator

Purpose. Show the time, attempt and cost runway for a pathway, with backups. It is a planning map, not a prediction, and the first screen says so.
Inputs. Current age and class; target career or exam; expected attempts; budget and financing choice; state (for domicile and state-quota effects).
Outputs. Timeline of stages with age ranges; cumulative cost range; first-earning age range; backup pathways with their own timelines; what changes if an attempt fails.
Example: doctor (illustrative; verify current rules before publication).
| Stage | Duration | Age range |
| --- | --- | --- |
| Class 12 completed | — | 17–18 |
| Preparation and attempts (NEET-UG) | 1–3 years | 18–21 |
| MBBS including internship | about 5.5 years | 23–27 at completion |
| PG preparation and MD/MS | 1–2 + 3 years | 27–32 |
| Specialist stage begins | — | about 27–32 |

Backups shown: allied health, BDS, biomedical and life-science degrees, other healthcare routes, each with its own timeline and cost.
Example: engineer. Class 12 → entrance or state counselling (0–2 years) → degree (4 years) → skill and internship phase → industry role; first-earning age about 21–25.
Design rules. Ranges and named assumptions only; every duration links to an official rule or cited dataset; salary shown only as sourced bands with survey and year; no guarantee language anywhere. Each career record carries its NCO-2015 anchor and its pathway variants (Section 10), so the count of careers cannot drift.

## 14. Exam Intelligence System

Per exam record. Eligibility; age limit and relaxations; attempt limits; syllabus (versioned); pattern; calendar (notification, application, exam, result, counselling); fee; seat or vacancy trends from official data; competition level as a transparent measure such as applicants per seat, only when officially available; reservation rules; a preparation roadmap template.
Coverage by readiness, not by promise.
| Wave | Phase | Exams | Condition |
| --- | --- | --- | --- |
| 1 | 1 (pilot) | 15: JEE Main, JEE Advanced, NEET-UG, CUET-UG, CLAT, NDA, UPSC CSE, SSC CGL, SSC CHSL, IBPS PO, RRB NTPC, GATE, CAT, plus the main state CET of each pilot state | Tier-1 fields verified with the authority's notification as the only source |
| 2 | 2 | About 100, adding major state public service commission and recruitment exams in participating states | State steward in place; authority feed or MoU where possible |
| 3 | 3 | National and state exams added as each reaches readiness level 4 | Published per state; no completion date promised |

Quality rules. The official notification is the only source for dates and eligibility. "Previous trends" use official statistics only; where none exist the field says "not available". Personal alerts and an "attempts and age runway" tracker per exam. A student's exam calendar follows them across states.

## 15. Institution Intelligence System

Per programme record. Recognition and approval status (UGC, AICTE, NMC, BCI and others as applicable); accreditation (NAAC, NBA); third-party rankings with source, year and method; courses; fees (tuition, hostel, other charges); total programme cost; admission route and counselling; cut-off history; hostel, safety and distance information; placement with standard definitions (median, percentage placed, sample size); research.
Verification model. Verified (matched to an official source or document evidence); Self-declared (entered by the institution, labelled unverified); Not available (shown honestly). The label is always visible; no design trick hides it.
Coverage by readiness.
| Phase | Records | Scope |
| --- | --- | --- |
| 1 (pilot) | 500–700 programme records | Central and state universities, institutes of national importance and government medical, engineering and polytechnic institutions in the three pilot states; plus NIRF top-100 nationally |
| 2 | About 8,000 | Participating states; state-portal catalogues imported and verified |
| 3 | Added as verified | Published per state; no total promised |

Protection features. Prominent "recognised or not" status; alerts for institutions on official fake-university or unapproved-course lists; a warning banner where fee or placement claims cannot be verified.
Rules. BCION never generates its own composite institution ranking and never accepts payment for placement or prominence. Institution Data Stewards maintain profiles by self-attestation with evidence, verified by sampling; the pilot tests whether they actually do [UH].

## 16. Financial Assistance System

Components.
- Cost engine: full-programme cost including tuition, hostel, exam, travel and other charges, with a government versus private comparison.
- Scholarship finder: rule-based matching on income cap, category, marks, gender, state, discipline and institution type; document checklist; deadline alerts; links to NSP and state portals.
- Loan comparator: public-sector, private and NBFC lenders with identical fields (rate, collateral threshold, moratorium, subvention and guarantee schemes), each with source and date; PM Vidyalaxmi and similar schemes shown first where the student is eligible.
- Repayment reality check: EMI and total repayment against sourced starting-income ranges; a warning when EMI exceeds a configurable share of the lower end of the range (default 30%).
- Scam alerts: fake scholarship messages and fee-collection agents.
Rules. "Cost before choice": every programme view shows total cost first. No lender-paid ranking, no lead sales. Applications happen on official portals via deep links. The tool provides information, not financial advice, and says so. Income and category are optional, encrypted and used only for eligibility.

## 17. Learning ecosystem

Sources. Government platforms (SWAYAM, NPTEL, DIKSHA, National Digital Library) linked, not copied. Curated online courses and playlists that pass editorial review for accuracy, pedagogy, language, absence of coaching upsell and stable availability. Previous-year papers only from official publication. Openly licensed content hosted directly; permissioned content labelled with attribution.
Quality control. Each resource card shows reviewer, review date, language, level and a "last checked" link test. Broken or degraded resources are removed automatically after failed checks.
Access. Offline packs for low-connectivity areas; low-bandwidth text mode; audio summaries from Phase 2.
Principle. Link out and respect copyright. BCION curates and verifies; it does not become a video host or a coaching platform.

## 18. Mock test engine (Phase 2 onward)

Content. Official previous-year questions where publication permits; expert-authored items; AI-assisted drafts reviewed by at least two subject experts; numeric and logical items checked with a solver; tagged by exam, topic, difficulty and language.
Calibration. Difficulty is calibrated with real response data (item-response methods) before adaptive testing is enabled. Adaptive testing ships only when the calibrated bank for an exam exceeds a published threshold; it is not a Phase 3 promise.
Phasing. Phase 2: fixed-form mock tests and topic tests, weakness analysis, a study planner (exam date, available hours, mastery), about 15,000 reviewed items across Wave-1 exams. Phase 3: adaptive tests per exam as calibrated.
Design choices. Test delivery uses no model tokens; explanations are pre-generated and reviewed for high-volume items; a budgeted AI tutor covers the rest; results show performance bands and topic gaps, never rank predictions; no public leaderboards for minors; integrity controls and faulty-item reporting.

## 19. Stakeholder network and human-service capacity model

The network is structured and moderated, not an open social network.
| Party | Channel | Safeguards |
| --- | --- | --- |
| Institutions, scholarship providers, lenders | Verified "Ask an official" desks with published FAQs | Public answers; no private chat with minors |
| Teachers | Dashboards, class groups, Career Period kit | Anonymised class-level data by default |
| Counsellors | Booked sessions (remote or in person) | Certified, background-checked, logged, supervised; funded slots for low-income students |
| Peers | Class-band moderated communities, pseudonymous, no direct messages (Phase 2) | Trained moderators, reporting, automated filters |
| Alumni mentors (Phase 3, conditional) | Scheduled group sessions and Q&A | Verified via institution, background-checked, no unsupervised 1:1 with minors |
| Industry | Verified employer profiles; internships via government portals first | Employer verification |
| Government | Notice feed, grievance channel | Official-source labelling |
| Coaching (Phase 3) | Standard disclosure profiles | No paid placement, no leads |

Child-protection policy. Mandatory training for moderators and mentors; reporting and escalation process; clear links to emergency and child-helpline services.

### Human-service capacity model

This replaces the v1.0 slogan with arithmetic. Every assumption is [PA] until the pilot measures it.
Four tiers.
| Tier | Who | What | Share of registered students per year |
| --- | --- | --- | --- |
| 1 Self-serve | Platform | Tools, explanations, alerts | All |
| 2 Teacher-facilitated | Trained teacher | 40-minute Career Period, group Q&A, first-line escalation | 2–3% escalate here |
| 3 Certified counsellor | Part-time certified counsellor | 45-minute remote 1:1 plus 15 minutes documentation | 1–1.5% reach here |
| 4 Crisis | Helpline plus designated counsellor | Immediate helpline information; human follow-up within 24 h | Measured, not assumed |

Capacity assumptions. A part-time counsellor delivers about 150 sessions per year on average (full-time equivalent 350); supervision ratio 1 supervisor per 12 counsellors; honorarium ₹600–800 per completed session [PA]; no-show rate 25%; appointment SLA 7 working days, 3 in application windows; crisis follow-up 24 hours; every pilot-state language covered by at least three counsellors.
Demand and supply by phase.
| Point | Registered | Tier-3 sessions per year (at 1–1.5%) | Counsellors needed | Counsellors planned | Annual cost [CE] |
| --- | --- | --- | --- | --- | --- |
| Month 18 | 50,000–70,000 | 500–1,050 | 4–7 | 15–20 (language and geography spread; measurement) | ₹0.3–0.5 crore |
| Month 36 | 30 lakh | 30,000–45,000 | 200–300 | 250 | ₹3–4 crore |
| Month 60 | 1.5–2 crore | 1.5–3 lakh | 1,000–2,000 | 1,200 | ₹11–16 crore including supervision and training |

Sensitivity. If the measured Tier-3 rate is 2% instead of 1–1.5%, Month-60 demand is 3–4 lakh sessions and cost rises to ₹22–30 crore. The response is not to promise more counsellors: funded slots are capped and prioritised for government-school and low-income students, Tier 2 absorbs more, and the cap is a published number. If the pilot measures a rate above 2%, the Month-36 gate requires a redesign of Tier 2 before scaling.

## 20. Governance model

v1.0 pre-decided an independent Section 8 company with a government MoU. That is one of three options, and the choice belongs to a Phase −1 legal and institutional assessment. The nine questions any option must answer: who owns the platform and its data; who carries liability for wrong guidance; who appoints and removes the CEO; who controls funding flows; whether government nominees can block publication; whether private donors can shape priorities; who has authority over state-specific rules; whether public audit and procurement rules apply; whether government branding can be used without implying legally binding advice.
| Model | Advantage | Main weakness | Fit with existing state portals |
| --- | --- | --- | --- |
| A. Government mission or SPV under the Ministry of Education | Statutory authority, data access, direct grant funding, easy state adoption through official channels | Political control of editorial content; procurement rigidity; slow hiring; every error becomes a government error | Can absorb portals by direction, but states may read it as central overreach |
| B. Independent Section 8 company with a government MoU | Neutrality, agility, hiring flexibility, credible editorial independence | No statutory authority; grant dependency; liability unclear; must negotiate with each state and with the current portal vendor and donor | Weakest: nothing obliges a state to migrate |
| C. Federated public consortium: central anchor, member states, a Section 8 operating company, an independent Data Integrity Council | State legitimacy; a natural migration path for existing portals as member assets; shared cost; editorial independence held by the council, not the company | Slow decisions; complex accountability; needs a strong charter and a decisive chair | Best: existing portals join as members with their vendor relationships intact or renegotiated |

Recommendation, subject to Phase −1 assessment: Option C, with the operating company's editorial independence, the Neutrality Charter and the Data Integrity Council written into the consortium agreement and into every state's accession document.
Structure under Option C. Governing Council with an independent chair and no government majority; Data Integrity and Source Council owning the source registry and verification standards, with liaison seats for regulators and exam authorities; Ethics, Child Safety and Privacy Board; Technology and Security Committee; Finance and Audit Committee; Counselling Standards Committee; Youth Advisory Panel; State Steering Group of member-state nodal officers.
Neutrality Charter (non-negotiable under any option).
- No paid placement or paid ranking of any institution, coaching centre, lender or employer.
- No sale or sharing of student data or leads.
- No advertising.
- Recommendation logic uses no commercial inputs; methodology is published.
- Every fact has a source; unverified information is labelled.
- No prediction presented as certainty.
- Conflicts of interest are declared; conflicted members recuse.
- Errors are corrected publicly within stated timelines.
Accountability. Annual public report; quarterly data-quality and readiness dashboard; independent financial, security and algorithmic audits; a grievance officer as required under the data-protection law; audited accounts and a public cost-per-MAU figure.

## 21. Technology plan

Stack (indicative). Cloud-native containers on an India-region, MeitY-empanelled or government cloud; relational database for verified data; search and vector indexes; object storage; event bus; PWA front end; WhatsApp Business API; speech services from Phase 2; open-source first.
Build versus buy. Build the decision engines, data-ops pipeline, model gateway, readiness dashboard and governance tooling. Buy commodity infrastructure (cloud, speech, messaging). License or partner for the interest inventory.
Availability and recovery, by service tier (replaces the v1.0 single 99.9% figure).
| Tier | Services | Availability | RTO | RPO | How |
| --- | --- | --- | --- | --- | --- |
| A | Public read-only pages, exam calendar, alert dispatch | 99.9% monthly | 30 min | 15 min | Pre-rendered on CDN, multi-zone within India, read replicas |
| B | Logged-in tools, decision engines, dashboards | 99.5% | 2 h | 15 min | Autoscaled services, warm standby |
| C | AI chat, counsellor booking, admin, data-ops console | 99.0% | 4 h | 1 h | Standard failover; degraded mode falls back to Tier A content |

Peak capacity: 20× baseline on result and deadline days, load-tested before each admission season.
Performance. Pages usable on mid-range phones on 4G in under 3 seconds. 2G mode, defined: text-only public pages under 50 KB; compressed static pathway cards; no live conversational AI; deferred synchronisation of saved plans; SMS fallback for deadline alerts in the pilot; IVR fallback funded from Phase 2. Accessibility to WCAG 2.1 AA with screen-reader support.
Languages. Phase 1: Hindi, English, plus one or two pilot-state languages (3–4 total). Phase 2: 8. Phase 3: 15–18, with all 22 scheduled languages as a readiness goal, not a commitment. Each language is added only after translation QA of academic and administrative terminology, speech tuning (where voice is offered) and testing; each adds a costed line (Section 26).
Model gateway. Model-agnostic, multi-vendor, self-hosted open-weight models for routine tasks, cost and latency dashboards, per-tenant budgets, automatic fallback to Tier 0.
Engineering practice. CI/CD with automated tests for rules engines (every rule versioned with source citation); feature flags; staged rollouts; public changelogs for data and algorithms; state instance as configuration, never a fork.

## 22. Cyber security

Threats considered. Account takeover; scraping and bot abuse; DDoS on peak days; phishing and lookalike sites; insider misuse; tampering with critical data; prompt injection or data poisoning through monitored web content and imported state-portal catalogues.
Controls. Zero-trust access; MFA for all staff; least-privilege roles; secrets management. Encryption in transit and at rest; field-level encryption for sensitive attributes; keys under strict custody. WAF, DDoS protection, bot management, API rate limits. Signed and versioned critical records; immutable audit logs. Retrieved external text is treated as data, never as instructions; the LLM has no write access to databases and no access to the student vault. Vulnerability assessment and penetration tests at least twice a year; bug-bounty programme from Phase 2; a managed 24×7 security operations centre from Phase 2 (business-hours plus on-call in the pilot).
Standards and compliance. ISO 27001 certification path; CERT-In incident-reporting and log-retention directions (verify current requirements); independent annual security audit; GIGW conformance where government branding applies.
Brand protection. Register lookalike domains; publish the list of official channels; a "how to recognise official BCION messages" guide.
Incident response. Tested playbooks; quarterly tabletop exercises; breach notification to authorities and affected users as the law requires.

## 23. Data privacy

Legal basis. Compliance with the Digital Personal Data Protection Act 2023 and the DPDP Rules 2025, including their phased commencement (re-verify current text and dates before launch).
Residency. Student data is stored and processed in India as a BCION policy and risk-control decision, subject to current legal review. This is not presented as a blanket statutory mandate.
Children first. Most users are minors. No behavioural tracking or targeted advertising to children; privacy-protective defaults; verifiable parental consent for under-18 accounts.
Verifiable parental consent, operational design (a major dependency, not a bullet).
| Question | Design answer [PA; validate against DPDP Rules 2025 mechanisms] |
| --- | --- |
| What needs no consent at all | Public tools with no personal data: explorer, calculators, exam calendar, institution profiles |
| How is the parent linked to the child | Guardian identity via a DigiLocker-issued token, or a school-mediated route where the school already holds verified parent records and acts within its own data-fiduciary role |
| Student with no reachable parent | Public tools plus school-facilitated access under the school's records; no personal account until a guardian or lawful guardian is confirmed |
| Consent granularity | Separate, revocable consents for saving marks, category or income, sharing a parent view, contacting an institution |
| Renewal and withdrawal | Annual re-consent prompt; withdrawal freezes the account, deletion follows within 30 days |
| Turning 18 | Consent re-obtained from the student; parent link downgraded to shared summaries unless the student re-enables it |
| Which activities count as essential public services | To be determined with the sponsor's legal team; nothing in this DPR assumes an exemption |

Minimisation and purpose limitation. Collect only what a feature needs; sensitive fields optional.
No sale, no lead sharing, no advertising. Institutions receive individual information only when a student initiates contact for that specific institution.
Rights. Access, correction, erasure and grievance in plain language and regional languages, with a named grievance officer.
Retention. Limited; inactive accounts deleted after notice; deletion cascades to backups within a defined period.
Assessments. Privacy impact assessment before launch and annually; ethics review for any research use of anonymised data.
Sensitive conversations. Distress-related content is minimally retained, restricted to authorised staff, used only for safety.

## 24. Team structure

Recommended scenario, core team headcount [PA]. Data operations and state partnerships dominate; engineering does not.
| Function | Month 12 | Month 36 | Month 60 |
| --- | --- | --- | --- |
| Leadership and governance office | 6 | 10 | 12 |
| Product, design and engineering | 18 | 40 | 55 |
| AI/ML and data science | 5 | 10 | 14 |
| Data verification and content operations | 12 | 55 | 105 |
| Counselling, psychometrics and pedagogy | 4 | 14 | 24 |
| State partnerships, outreach and school onboarding | 5 | 25 | 60 |
| Support, moderation and grievance | 2 | 10 | 22 |
| Security, privacy, legal and compliance | 3 | 8 | 12 |
| Finance, HR, admin, research and evaluation | 4 | 8 | 10 |
| Total core team | ~59 | ~180 | ~314 |

Extended network. Certified part-time counsellors: 15–20 at Month 18, 250 at Month 36, 1,200 at Month 60 (Section 19). State data stewards: nodal officers in each member state, largely government-deputed. Institution data stewards; teacher facilitators (two per school, matching the existing state-portal model); subject reviewers on honorarium.
Why 105 data-operations staff is enough at Month 60 and 175 was not needed. Coverage is readiness-based, so the team verifies what states and authorities actually supply rather than chasing 45,000 colleges. State stewards and institution stewards carry first-line maintenance; BCION staff verify by sampling and own Tier-1 exam data outright. If the pilot shows that stewards do not maintain profiles [UH], the Month-36 gate revises this table upward and the cost with it.
Leadership roles. CEO; Chief Data and Trust Officer; CTO; Chief Counselling and Pedagogy Officer; CISO and privacy officer; Chief Partnerships Officer (states and portal migration); CFO.

## 25. Implementation roadmap

```
flowchart LR  P0["Phase −1<br/>Pre-approval<br/>M −12 to 0"] --> P1["Phase 0<br/>Foundation<br/>M 0–6"]  P1 --> P2["Phase 1<br/>Pilot, 3 states<br/>M 7–18"]  P2 -->|Gate M18| P3["Phase 2<br/>Multi-state<br/>M 19–36"]  P3 -->|Gate M36| P4["Phase 3<br/>National availability<br/>M 37–60"]  P4 -->|Gate M60| P5["Renewal or wind-down"]
```

Each gate releases the next tranche; a failed gate pauses spend, it does not stop the platform.

### Phase −1 — Pre-approval (Months −12 to 0; elapsed time depends on the sponsor)

- Sponsor decision: central anchor or single state (Annex A).
- Governance option chosen after legal and institutional assessment (Section 20).
- Talks with three candidate pilot states and with the current state-portal vendor and donor on a migration path.
- Scheme appraisal through the sponsor's standard route (for a central scheme of this size, SFC or EFC-level appraisal; verify the current thresholds and process). Budget 9–15 months of elapsed time for appraisal and sanction; it is not in v1.0's roadmap and it is real.
- Independent evaluator identified.
- Cost: ₹1.5–2.5 crore [CE], carried by the sponsor's preparatory budget; outside the five-year total.
Gate: sponsor named; governance model chosen; appraisal approved; Tranche 1 sanctioned; three pilot states agreed in principle.

### Phase 0 — Foundation (Months 0–6)

- Incorporate the operating entity; seat the Governing Council and the Data Integrity Council; sign MoUs with the sponsor, three pilot states and the main exam authorities for Tier-1 data.
- Approve data schema and source registry v1 (about 200 official sources for the pilot scope).
- Pilot states, final: one with an existing UNICEF-type portal (to measure marginal value), one large Hindi-belt state without one, one southern or tribal-population state. Steering committee decides.
- Privacy impact assessment; threat model; architecture spike (Tier-0 engines plus retrieval with citations on a small verified dataset); model-gateway cost simulation and the cost-per-MAU cap.
- Baseline survey of students, parents and teachers in the pilot states; classroom trial of the Career Period kit in 30 schools.
- Interest-inventory licensing or norming partnership.
- Hire the first ~35 core staff; procure cloud, messaging and model-gateway vendors.
Gate: MoUs signed; schema approved; privacy assessment passed; baseline complete; kit trial results in.

### Phase 1 — Pilot (Months 7–18)

- Content: 40 careers in the lifespan calculator; 15 exams; 500–700 programme records; national and three-state reservation and counselling explainers; scholarship and loan finder.
- Channels: PWA and WhatsApp; offline packs; SMS deadline fallback; 3–4 languages. No voice.
- Access: 150–250 schools or access centres; 100,000–150,000 invited students; 15–20 certified counsellors; data pipeline with maker-checker running from Month 9.
- Security: first penetration test; incident drills.
- Evaluation: stepped rollout across schools so comparison groups exist; decision-quality survey at Month 17.
Targets [PT]: 50,000–70,000 registered; 15,000–25,000 monthly active; readiness level 4 for Tier-1 exam data in all three states.
Gate (Month 18): critical-field accuracy ≥ 99% on audited samples; Tier-1 freshness SLA met ≥ 95%; MAU ≥ 30% of registered; decision-quality uplift of at least 15 points over comparison schools; AI cost ≤ ₹20 per MAU; measured Tier-3 referral rate published; no serious privacy incident; at least one pilot state confirms it wants to continue on its own budget line or the consortium's.

### Phase 2 — Multi-state expansion (Months 19–36)

- Coverage: 8–12 member states, prioritising states with existing portals ready to migrate; about 100 exams; about 8,000 verified programme records; 8 languages.
- Features: reviewed mock-test bank (about 15,000 items) and study planner; teacher dashboard; counsellor network to 250; voice and IVR; bank and scholarship-provider integrations; state-portal migration tooling; open API beta; bug bounty; 24×7 SOC.
- Schools: 1,500–2,500.
Targets [PT]: 30 lakh registered; 8–10 lakh MAU; at least two completed state-portal migrations.
Gate (Month 36): cost per MAU on trajectory to the Month-60 figure; independent safety audit passed; evaluation shows improved decision outcomes against comparison schools; Tier-3 referral rate within the capacity model or Tier 2 redesigned; institution-steward maintenance rate measured.

### Phase 3 — National availability, readiness-based (Months 37–60)

- Every state is offered membership; coverage per state is published by readiness level; no completion date is promised for any state that has not joined.
- Languages to 15–18.
- Features, each behind its own readiness gate: adaptive testing per exam once calibrated; coaching disclosure profiles; verified alumni mentors; industry and internship integration; open data and APIs; longitudinal outcome study.
Targets [PT]: 1.5–2 crore registered; 40–60 lakh MAU; 1,200 counsellors.
Gate (Month 60): independent impact evaluation; sustainability review and funding renewal.

### Stage-gate stop or pivot criteria

- Critical-field accuracy below 97% after two remediation quarters: pause scaling until fixed.
- MAU below 25% of registered after Month 18 or below 20% after Month 36: redesign engagement before more spend.
- Neutrality Charter compromised, or governance cannot be kept independent: stop.
- Serious child-safety or privacy incident without a verified fix: suspend the affected feature.
- Fewer than two states willing to migrate their portal by Month 30: revisit the absorb-not-compete strategy before Phase 3.
- Measured Tier-3 referral rate above 2% with no viable Tier-2 redesign: cap funded counselling and re-scope before Phase 3.

## 26. Cost estimate

All figures [CE], ±30%, top-down. A bottom-up model with vendor quotes and salary benchmarks is a Phase 0 deliverable; nothing here should be read as a sanctioned budget.

### 26.1 Three scenarios, five-year total (₹ crore)

| Scenario | What it is | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Five-year total |
| --- | --- | --- | --- | --- | --- | --- |
| Lean public utility | Tier-0 tools, WhatsApp and PWA only, Tier-2 counselling only, 6–8 states by M60, 10 languages | 6–8 | 13–17 | 42–55 | 90–110 | 150–190 |
| Recommended assisted model | This DPR: pilot, 8–12 states by M36, all states offered by M60, Tier-3 counselling capped, 15–18 languages | 8–10 | 18–24 | 60–80 | 125–155 | 210–270 |
| High-service national model | Voice from Phase 1, uncapped Tier-3 counselling, 22 languages, in-person centres in every district | 11–14 | 28–36 | 95–120 | 180–220 | 310–390 |

Phase −1 (₹1.5–2.5 crore) sits outside these totals and is carried by the sponsor.

### 26.2 Recommended scenario, annual run-rate at Month 60 (₹ crore per year)

| Category | ₹ crore | Notes |
| --- | --- | --- |
| Cloud, storage, CDN, search | 7–9 | India-region government or empanelled cloud |
| AI inference, embeddings, safety classifiers, speech | 5–7 | ₹10–15 per MAU at 40–60 lakh MAU; cap ₹20 |
| Messaging and telephony | 4–6 | WhatsApp conversation charges, SMS fallback, IVR minutes; absent from v1.0 |
| Data verification and content operations | 12–15 | 105 staff plus tooling and subject-reviewer honoraria |
| Product, engineering, AI teams | 13–16 | 69 staff |
| Counsellor network | 13–16 | 1.5–2 lakh funded sessions, supervision, training, certification |
| State partnerships, outreach, school facilitation | 9–12 | 60 staff plus teacher-facilitator honoraria and school kits |
| Support, moderation, grievance | 3–4 | Peak-season helpdesk staffing; absent from v1.0 |
| Security, privacy, legal, audits, state rules review | 4–5 | Includes state-specific reservation and domicile legal review; absent from v1.0 |
| Translation QA and speech tuning | 2–3 | Per-language academic and administrative terminology review; absent from v1.0 |
| Governance, admin, research, independent evaluation | 3–4 | Includes field audits |
| Contingency (about 7%) | 5–7 | Institutional non-cooperation, procurement overhead |
| Total | 80–105 |  |


### 26.3 Unit economics, recommended scenario

| Point | Annual run-rate | MAU | Cost per MAU per year |
| --- | --- | --- | --- |
| Month 18 | ₹18–24 crore | 15,000–25,000 | ₹7,000–16,000 (pilot; fixed costs dominate; not a meaningful unit figure) |
| Month 36 | ₹40–48 crore | 8–10 lakh | ₹400–600 |
| Month 60 | ₹80–105 crore | 40–60 lakh | ₹150–200 |

Reading: v1.0's ₹80–105 per MAU depended on 1.5 crore MAU. At the scale this DPR is willing to commit to, the honest figure is ₹150–200 per MAU per year, roughly the price of one or two tutoring sessions. Per-MAU cost falls only with adoption, which is why funding is gated to it.

### 26.4 Cost lines v1.0 omitted, now included

WhatsApp conversation charges; telephony and voice minutes; school-level facilitation honoraria; state-specific legal and reservation-rule review; translation QA across academic and administrative terminology; counsellor supervision and quality assurance; peak-season customer support; source-document licensing; independent field audits; procurement overhead; contingency for institutional non-cooperation; grievance and content-moderation staffing.

### 26.5 Main cost sensitivities

- Data-operations headcount is the largest driver. If institution stewards do not maintain profiles [UH], add 30–50 staff and ₹4–6 crore per year.
- Tier-3 counselling referral rate: each 0.5 percentage point above 1.5% adds ₹5–8 crore per year at Month-60 scale; the funded-slot cap is the control.
- Model prices and usage mix: a doubling of the Tier-3 AI share adds ₹2–4 crore per year; the cap and Tier-0 fallback are the control.
- Each additional language adds ₹0.5–1 crore per year in QA, speech tuning and testing.
- Messaging volume: each additional opted-in alert per student per year adds roughly ₹0.5–0.7 crore at 50 lakh MAU.

## 27. Sustainability and funding

Reality check. A free, neutral, verified national service is a public good. It cannot fund itself through student fees or advertising without destroying the trust that gives it value, and the institutions it serves will not pay for data they already file elsewhere for free. The base case therefore assumes zero earned revenue.
Funding mix targeted by Month 60.
| Source | Share of run-rate | What it is |
| --- | --- | --- |
| Government grant-in-aid and programme funding (central and member states) | 75–85% | Public digital good; member states contribute to the consortium in proportion to coverage |
| CSR and philanthropy | 15–25% | Education-focused CSR, foundations, scholarship sponsors, the existing state-portal donor if it chooses to continue |
| Earned revenue | 0% in the base case; up to 10% as upside | Only the permitted lines below, and only once a signed contract exists |

Permitted earned revenue (upside only). Managed state instances for non-member governments and boards; anonymised aggregate analytics for policymakers and researchers; scholarship administration on flat fees; teacher and counsellor certification paid by schools or governments; open API licensing on identical terms for all users. Institutional data-quality services, which v1.0 counted on, are dropped: the workshops rejected them and no buyer is named.
Forbidden revenue. Per-lead or per-enrolment fees; paid placement or ranking; advertising; student-data sale; commissions on loans or courses; any revenue tied to which choice a student makes.
Funding mechanics.
| Tranche | Covers | Amount [CE] | Released on |
| --- | --- | --- | --- |
| 1 | Phases 0–1 | ₹26–34 crore | Phase −1 gate |
| 2 | Phase 2 | ₹60–80 crore | Month-18 gate |
| 3 | Phase 3 | ₹125–155 crore | Month-36 gate |

An endowment or corpus target from Year 3 cushions funding cycles. Annual audited accounts and a public cost-per-MAU figure are published from Month 18.

## 28. Risk analysis

L = likelihood, I = impact (H/M/L).
| # | Risk | L | I | Mitigation | Owner |
| --- | --- | --- | --- | --- | --- |
| 1 | Wrong critical data (dates, fees, eligibility) published | M | H | Maker-checker on Tier 1, signed records, freshness SLAs, public correction channel | Chief Data and Trust Officer |
| 2 | Sponsor not secured or appraisal delayed | H | H | Phase −1 as an explicit phase; single-state fallback (Annex A) | Steering committee |
| 3 | Funding shortfall or delay | M | H | Milestone tranches, corpus, phased spend, zero-revenue base case | CEO and CFO |
| 4 | States refuse to migrate or run two systems | H | H | Absorb-not-compete strategy, federated governance, migration tooling, pilot in a portal state | Chief Partnerships Officer |
| 5 | Commercial pressure erodes neutrality | M | H | Neutrality Charter, independent council, published methodology, audits | Governing Council |
| 6 | Breach or misuse of minors' data | L | H | Privacy-by-design, encryption, minimal data, audits, incident drills | CISO |
| 7 | Low adoption or high churn | M | H | School channel, WhatsApp, no-login tools, alerts, youth panel, engagement gate | Chief Partnerships Officer |
| 8 | Institutions do not maintain profiles | H | M | Reuse regulatory data, stewards, "not verified" labelling, measured in pilot, headcount contingency | Data Integrity Council |
| 9 | AI hallucination or biased advice | M | H | RAG with citations, deterministic engines, guardrails, bias audits, red-teaming | AI lead |
| 10 | Harmful output to a distressed student | L | H | Distress detection with measured precision, helpline routing, human follow-up | Chief Counselling Officer |
| 11 | Counsellor capacity shortfall | M | H | Capacity model, funded-slot cap, Tier-2 absorption, gate on measured referral rate | Chief Counselling Officer |
| 12 | Political or legal challenge on reservation or domicile errors | M | H | Rules versioned with legal review, state stewards, disclaimers, correction SLA | Legal and state teams |
| 13 | Traffic spikes and outages on result days | H | M | Tiered availability, CDN pre-rendering, autoscaling, load tests, degraded mode | CTO |
| 14 | Digital divide leaves target users behind | H | H | WhatsApp, offline packs, SMS, school-based access, voice from Phase 2, equity KPIs | Partnerships and Product |
| 15 | Scams and lookalike sites impersonate BCION | H | M | Domain protection, official-channel list, user education, takedown process | CISO |
| 16 | AI vendor price or policy change | M | M | Multi-vendor gateway, self-hosted models, cost cap, quarterly re-quote | CTO and FinOps |
| 17 | Data-ops scale-up too slow | M | H | Readiness-based coverage, tooling, sampling for lower tiers | Data Ops head |
| 18 | Counsellor quality or misconduct | L | H | Certification, background checks, logs, supervision, complaint process | Counselling Standards Committee |
| 19 | Mock-test errors damage credibility | M | M | Two-expert review, solver checks, error reporting, item retirement | Pedagogy head |
| 20 | Governance capture or perceived political bias | L | H | Independent chair, editorial independence clause, transparency | Governing Council |
| 21 | Regulatory change (data protection, education rules) | M | M | Legal watch, modular consent and data handling, regular reviews | Legal |
| 22 | Single-vendor dependency inherited from state portals | M | M | Open data formats on import, contractual data portability, in-house capability | CTO and Partnerships |


## 29. Impact measurement

Independent evaluation at Months 18, 36 and 60, using stepped rollout across schools for comparison groups and a consented longitudinal panel. The evaluator is appointed in Phase 0, not at the end.
| Dimension | Indicator | Target [PT] |
| --- | --- | --- |
| Reach | Registered and monthly active students | 50–70k / 15–25k (M18); 30 lakh / 8–10 lakh (M36); 1.5–2 crore / 40–60 lakh (M60) |
| Equity | Share of users from government schools; girls; rural students | Government-school share ≥ 50%; girls ≥ 48%; rural share tracked against population |
| Decision quality | Students able to name three pathways and compare costs | ≥ 15 points over comparison schools at M18; ≥ 25 at M36 |
| Marginal value | Uplift in the pilot state that already has a portal versus states that do not | Uplift measurable in the portal state; if not, the differentiator claim is wrong |
| Opportunity uptake | Eligible students applying for scholarships and schemes | Measurable uplift versus comparison schools |
| Timeliness | Missed application deadlines (self-reported) | Reduction versus baseline |
| Satisfaction and regret | Stream and course satisfaction after 12 months | Improvement versus comparison |
| Data quality | Accuracy on audited critical fields; Tier-1 SLA compliance; correction time | ≥ 99%; ≥ 95%; 90% of reports resolved within 48 hours |
| Coverage transparency | Readiness level per module per state published monthly | 100% of live states |
| Human service | Appointment SLA met; measured referral rate | ≥ 90%; published |
| Safety | Confirmed data sale or misuse; harmful-output rate in audits; crisis-escalation response | Zero data sale; audited thresholds met |
| Trust | Trust score among students, parents and teachers | Above baseline and rising |
| Financial | AI cost per MAU; cost per MAU; grant-dependency ratio | ≤ ₹20; trajectory per Section 26; published |

Transparency: an annual public impact report with methodology and negative findings, not only successes.

## 30. Final recommendation

Can this project work at national scale? Yes, as a verified decision-support layer built state by state on top of, and eventually in place of, the career portals states already run: Tier-0 tools plus retrieval, human maker-checker on critical data, state stewards, a school and WhatsApp channel, a capacity-modelled counsellor network and federated governance can realistically reach 40–60 lakh monthly active students at ₹150–200 per MAU per year by Month 60.
No, as originally imagined: free, fully AI-driven, real-time, all-India, all-exams, all-colleges, lifelong on day one, with open networking and commercial partners in the loop. And no, as a national programme launched on a 10-lakh-student "pilot".
Recommendation: Conditional GO for Phase −1 and, on appraisal, Tranche 1 (Phases 0–1, ₹26–34 crore [CE]). Later tranches contingent on gate results.
Conditions precedent.
- A named sponsor and a chosen governance model after legal assessment, with the Neutrality Charter adopted before any partner integration.
- A funding commitment for at least Phases 0–2 in the sponsor's approved scheme, with an editorial-independence clause.
- Data-access agreements with the main exam authorities for Tier-1 data.
- Agreement in principle from three pilot states, at least one with an existing career portal.
- Privacy impact assessment, child-safety framework, verifiable-consent design and crisis protocol approved before launch.
- A funded data-operations team with maker-checker in place before public launch.
- An independent evaluator appointed in Phase 0.
First 100 days after sanction. Constitute the Governing Council and the Ethics, Child Safety and Privacy Board; finalise the data schema, source registry v1 and Tier-1 verification SOP; open talks with pilot-state stewards and the existing portal vendor on migration; run the baseline survey; build the technical spike; complete the model-gateway cost simulation and set the cost-per-MAU cap; appoint the evaluator.
What would make us stop. Loss of neutrality; uncorrectable data quality; an unresolved child-safety failure; persistent non-adoption after redesign; fewer than two states willing to migrate by Month 30.
Closing view. The lasting value of BCION is not its chatbot. It is a trusted, verified, connected map of India's education and opportunity landscape, owned jointly by the states that use it and governed so that it stays neutral. States have already built the first draft of that map. Build the trust layer on it; let AI make it easy to use.

# ANNEX A — State-instance variant

Use this annex if the sponsor is a single state government rather than a central anchor. The product is the same; the scope, governance and numbers change.
Scope. The state board and its Class 8–12 population; the state's own CET and recruitment exams; the 12–15 national exams most taken by the state's students; all recognised institutions in the state (typically 1,500–3,500 programme records for a large state [PA]); state scholarships plus NSP and PM Vidyalaxmi; state reservation, domicile and counselling rules; the state's official languages plus Hindi and English.
Relationship to an existing state portal. If the state already runs a UNICEF-type career portal, the state instance is that portal's successor: catalogue imported, provenance added, decision engines layered on, teacher workflow preserved, vendor contract renegotiated for data portability. If no portal exists, the state instance is built directly on the BCION base.
Governance. A state SPV or society under the school education department, with SCERT as the pedagogy owner, the directorates of higher and technical education as data stewards, and an advisory board with independent, youth and parent members. The Neutrality Charter applies unchanged. If a central BCION consortium exists, the state joins it and inherits the national exam spine; if not, the state instance builds a minimal national exam layer for the 12–15 exams above and licenses it to other states at cost.
Roadmap and cost [CE].
| Phase | Months | Scope | Cost |
| --- | --- | --- | --- |
| Pre-approval | −6 to 0 | State cabinet or department approval; vendor and donor talks; legal form | ₹0.5–1 crore |
| Foundation | 0–4 | Governance, schema, source registry (about 80 sources), privacy assessment, baseline | ₹2–3 crore |
| Pilot | 5–14 | 3–5 districts, 100–150 schools, 40,000–60,000 invited students, 40 careers, 12–15 exams, 400–600 programme records, PWA plus WhatsApp, 10–12 counsellors | ₹6–9 crore |
| State rollout | 15–36 | All districts, all state-board schools offered, mock bank for state CET, voice in the state language, 100–150 counsellors | ₹18–26 crore |
| Three-year total |  |  | ₹26–39 crore |

Targets [PT]. Pilot: 20,000–30,000 registered, 6,000–10,000 MAU. Month 36: 15–25 lakh registered for a large state, 4–7 lakh MAU, cost per MAU ₹250–400 per year.
Gates. Same as the national DPR, scaled: critical-field accuracy ≥ 99%; MAU ≥ 30% of registered; decision-quality uplift ≥ 15 points over comparison schools; measured referral rate published; no serious privacy incident.
What a state gets that a central programme cannot give quickly. Its own reservation and domicile rules verified first; its CET counselling rounds live within the SLA; its language and its teachers' existing workflow; a budget line it controls. What it loses: the national exam spine and cross-state portability until a consortium exists.
Decision rule. If a state sponsor is available now and a central sponsor is not, start with the state instance. The national DPR then becomes the plan for turning two or three state instances into a consortium, which is a stronger starting position than a central scheme with no state buy-in.

# ANNEX B — Change log against v1.0 and the external critique

| # | Critique point | Accepted? | What v1.1 does | Where |
| --- | --- | --- | --- | --- |
| 1 | Phase 3 rebuilds the super-app | Yes | "Full coverage" removed; readiness-based coverage with published levels; each Phase-3 feature behind its own gate | 3.5, 11, 25 |
| 2 | Pilot too large | Yes | Cut to 3 states, 150–250 schools, 100k–150k invited, 40 careers, 15 exams, 500–700 records, 3–4 languages, PWA plus WhatsApp | 25 |
| 3 | Budget presented with false confidence; cost lines missing | Yes | Three scenarios; twelve omitted lines added; every figure tagged [CE]; bottom-up model made a Phase 0 deliverable | 26 |
| 4 | Staffing does not match promised coverage | Yes, by cutting coverage | Team sized to readiness-based coverage; explicit contingency if stewards fail | 24, 26.5 |
| 5 | Counsellor network not operationally explained | Yes | Four-tier capacity model with referral rate, session length, capacity, supervision, honorarium, SLA, no-show and sensitivity | 19 |
| 6 | Earned revenue weak | Yes, further than proposed | Base case 0%, not 5–10%; institutional data services dropped entirely | 27 |
| 7 | Governance not a complete solution | Yes | Three options compared against nine questions; Option C recommended subject to Phase −1 assessment | 20 |
| 8 | Data residency framed as legal mandate | Yes | Restated as policy choice subject to legal review | 23 |
| 9 | DPDP child consent needs operational detail | Yes | Seven-question consent design table | 23 |
| 10 | 2G target vague | Yes | 2G mode defined | 21 |
| 11 | 99.9% availability vs 4-hour RTO | Yes | Availability and RTO by service tier | 21 |
| 12 | Signing is not data quality | Yes | Restated as tamper evidence only | 11 |
| 13 | Model prices treated as durable | Yes | Prices treated as quarterly-requoted ranges; full cost-component list; cap | 9 |
| 14 | "600 careers" has no taxonomy | Yes | Career defined against NCO-2015 unit groups; 40 in pilot, ~300 at maturity | 10, 13 |
| 15 | Simulated consultations could be mistaken for evidence | Yes | Repeating label on every workshop; hypothesis-status-validation table | Part 2 |
| 16 | Evidence labels on every number | Yes | Six-tag scheme applied throughout | Read this first |
| 17 | Critique's own ₹28–36 crore pilot figure was also top-down | Noted | Tranche 1 set at ₹26–34 crore [CE], explicitly labelled top-down | 26, 27 |
| 18 | Not in the critique: state career portals already exist in 14+ states | Added | Incumbent analysis, absorb-not-compete strategy, pilot in a portal state, migration tooling, vendor-dependency risk | 1.3, 6, 25, 28 |
| 19 | Not in the critique: no sponsor named | Added | Sponsor assumption stated; Phase −1; state-instance variant | Read this first, 25, Annex A |
| 20 | Not in the critique: scheme appraisal timeline absent | Added | Phase −1 with 9–15 months elapsed time for appraisal and sanction | 25 |
| 21 | Not in the critique: scale targets | Reduced | 5 crore / 1.5 crore MAU cut to 1.5–2 crore / 40–60 lakh; per-MAU cost restated honestly at ₹150–200 | 1, 26.3 |

Sources opened for this version. Millennium Post, "A guiding light", 28 July 2021 (14 state portals, 21 million+ students, programme design); Careers360, 22 May 2020 (Maharashtra portal); Drishti IAS, 7 February 2019 (Rajasthan portal). All three are secondary reports; Phase −1 must obtain the current position from UNICEF India and the state education departments directly.
End of document. This DPR is a consultation draft; all figures and legal references must be validated during Phases −1 and 0.

# ANNEX C — Glossary

| Term | Meaning in this document |
| --- | --- |
| ABC | Academic Bank of Credits, the national credit-record system linked to APAAR |
| ACPC, ACPUGMEC, GCAS | Gujarat's admission committees for professional courses, undergraduate medical courses, and the common admission service for general degrees (verify current names) |
| AICTE, UGC, NMC, BCI | Regulators for technical, university, medical and legal education whose approval status must appear on every programme |
| AISHE, UDISE+ | Official surveys of higher education and school education; sources for population figures |
| APAAR, DigiLocker | National student identifier and document wallet; consent-based record sources |
| CBSE Career Guidance portal | National career portal launched in 2021 by CBSE, UNICEF and iDreamCareer; an incumbent |
| CERT-In | National cyber-security agency whose incident-reporting and log-retention directions apply |
| CET | A state common entrance test (GUJCET, MHT-CET and similar) |
| Coverage transparency | Four published counts per module and state: available, verified, within SLA, awaiting confirmation |
| CSR | Corporate social responsibility funding |
| CUET, JEE, NEET, CLAT, NDA, GATE, CAT | National entrance exams in Wave 1 |
| Data Integrity Council | Governance body owning the source registry and verification standards |
| DPDP Act 2023, DPDP Rules 2025 | India's personal-data law and its rules; verifiable parental consent for minors comes from here |
| EMI | Equated monthly instalment on an education loan |
| Evidence tags | [OF] official fact; [HF] historical figure; [PA] planning assumption; [PT] target; [CE] cost estimate ±30%; [UH] unvalidated hypothesis |
| Fact card | A server-rendered block showing a date, cost or eligibility outcome from the database, so generated prose never carries the number |
| Federated consortium | Governance Option C: central anchor, member states, a Section 8 operating company, an independent Data Integrity Council |
| ITI, polytechnic, apprenticeship | Vocational pathways given parity with degrees |
| Lite | BCION Lite, the 10–100 user software pilot planned in `docs/BCION-Lite-Build-Pack.md` |
| Maker-checker | Two-person publication: the author of a critical claim cannot approve it |
| MAU | Monthly active users, the unit for cost and adoption targets |
| MoU | Memorandum of understanding with a sponsor, state, regulator or exam authority |
| NCO-2015 | National Classification of Occupations; the anchor for the career taxonomy |
| NCS | National Career Service portal |
| NEP 2020 | National Education Policy 2020 |
| NIRF, NAAC, NBA | National ranking and accreditation bodies; shown with source, year and method, never merged into a BCION rank |
| NSP, PM Vidyalaxmi | National Scholarship Portal and the education-loan scheme; linked, not replicated |
| NSQF | National Skills Qualifications Framework; skill clusters map to it |
| NTA | National Testing Agency |
| Phase −1, −2 | Pre-approval (sponsor, governance, appraisal) and the Lite proof of concept that precede Phase 0 |
| PWA | Progressive web app, the lite app under 10 MB |
| Readiness level | 0–4 score per module and state derived from coverage transparency; level 4 required before a state is "BCION recommended" |
| RLS | Row-level security in Postgres; the mechanism that keeps one student's data from another |
| RPO, RTO | Recovery point objective and recovery time objective, set per service tier |
| Section 8 company | Indian not-for-profit company form |
| SFC, EFC | Standing and Expenditure Finance Committees that appraise central schemes (verify current thresholds) |
| SLA | Service-level agreement, used here for freshness and correction commitments |
| SWAYAM, DIKSHA, NPTEL | Public learning platforms, linked not copied |
| TALASH | 2025 UNICEF and Ministry of Tribal Affairs platform for Eklavya schools; an incumbent |
| Tele-MANAS | National tele-mental-health service; the helpline shown in the crisis protocol (verify the current number at launch) |
| Tier 0–3 (AI) | Query routing: database and rules; small model; mid model; large model with human escalation |
| Tier 1–4 (data) | Freshness tiers: critical, cycle, annual, market |
| Tier 1–4 (human service) | Self-serve; teacher-facilitated; certified counsellor; crisis |
| Tranche | Funding released on a gate: 1 for Phases 0–1, 2 for Phase 2, 3 for Phase 3 |

# ANNEX D — Assumptions register

Every [PA] and [UH] item in one place, with what replaces it and when. Items are closed when the validation column is done, not when someone agrees with them.

| # | Assumption | Tag | Section | Validation | When |
| --- | --- | --- | --- | --- | --- |
| 1 | Class 8–12 population 8–10 crore; other market figures | [PA] [HF] | 4 | Current UDISE+, AISHE, NTA figures | Phase 0 |
| 2 | Reachable users 15–25% of the population at M60; 25–35% monthly activity among registered | [PA] | 4 | Pilot registration and retention | M18 |
| 3 | Tier 0 serves 65–70% of interactions | [PA] | 9 | Lite logs, then pilot logs | Lite; M18 |
| 4 | AI cost ₹10–15 per MAU per year, cap ₹20; Hindi token overhead 2–4× | [PA] | 9 | Model-gateway cost simulation; Lite cost per Hindi answer | Phase 0; Lite |
| 5 | Tier-3 counselling referral 1–1.5% of registered per year; Tier 2 absorbs half of escalations | [PA] | 19 | Measured in Lite and pilot | Lite; M18 |
| 6 | Counsellor 150 sessions per year; honorarium ₹600–800; 25% no-show; supervision 1:12 | [PA] | 19 | Pilot operations | M18 |
| 7 | Institution data stewards maintain self-declared profiles | [UH] doubtful | 15, 24 | Claim-and-verify trial with 200 institutions | M18 |
| 8 | Editor hours per verified record and per exam rule | [PA] | 24, 26 | Lite content track, then pilot | Lite; M18 |
| 9 | Students reject long assessments; a 5-minute quick start works | [UH] | 12 | Usability testing across age, language and device | Phase 0; Lite |
| 10 | Parents prefer linked visibility for younger students | [UH] disputed | 23 | Consent and family research | Phase 0 |
| 11 | WhatsApp is the dominant access channel | [UH] | 7, 12 | Channel-cost and adoption pilot | M18 |
| 12 | Schools adopt only with an official circular | [UH] | 12, 25 | State administrative interviews | Phase 0 |
| 13 | Teachers run a 40-minute Career Period from a kit | [UH] | 19 | Trial in 30 schools | Phase 0–1 |
| 14 | Existing state portals accept a migration path | [UH] unknown | 1.3, 6, 25 | Talks with three state departments and the portal vendor | Phase −1 |
| 15 | State portals are still maintained in 2026 | [UH] | 1.3 | State-by-state check with UNICEF India, CBSE and departments | Phase −1 |
| 16 | A federated consortium is acceptable to states | [UH] unknown | 20 | Legal and institutional assessment; state consultations | Phase −1 |
| 17 | Distress detection routes safely without flooding counsellors | [UH] | 9, 19 | Red-team precision and recall on Indian-language text | Phase 0–1; Lite |
| 18 | Institutions will pay for data services | [UH] rejected | 27 | None; revenue assumed zero | Closed |
| 19 | All cost figures are top-down and ±30% | [CE] | 26 | Bottom-up model with vendor quotes and salary benchmarks | Phase 0 |
| 20 | Scheme appraisal takes 9–15 months of elapsed time | [PA] | 25 | Sponsor confirms the route and thresholds | Phase −1 |
| 21 | Messaging cost per opted-in alert | [PA] | 26 | Vendor quote | Phase 0 |
| 22 | About 300 careers at maturity under the NCO-2015 taxonomy | [PA] | 10, 13 | Taxonomy work | Phase 0 |
| 23 | Monthly active users at least 30% of registered | [PT] | 25 | Pilot | M18 |
| 24 | DPDP consent mechanisms as designed in Section 23 | [PA] | 23 | Legal review against the DPDP Rules 2025 text | Phase 0 |
| 25 | Data residency by policy is achievable with the chosen vendors | [PA] | 23 | Data-flow map with confirmed regions | Phase 0; Lite |
| 26 | Gujarat as the Lite pilot state; English and Hindi suffice for the cohort | [PA] | Lite pack | Owner decision on the cohort | Lite Step 0 |

# ANNEX E — Lite build pack

The 10–100 user pilot, its interface brief, operating rules for Claude Code, data-flow map, 16-step schedule, budget, gates and ready-to-paste Step 1 prompt are in `docs/BCION-Lite-Build-Pack.md` (mirrors the "Lite build pack" tab of the living DPR/White Paper doc).

*End of document. This DPR is a consultation draft; all figures and legal references must be validated during Phases −1 and 0.*
