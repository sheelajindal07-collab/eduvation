# Content editor and checker handbook (CONTENT-15)

Fulfils CONTENT-15's deliverable (named `docs/CONTENT-HANDBOOK.md` in
`docs/plan/inventory-2-trust-content.md`'s own touches list; created here
at the path this task card names -- rename or symlink at merge time if
the lead wants the plan's exact filename). This is a procedure document
for the two named human roles doing real content work; it does not
itself verify, publish or claim anything, and it names no facts.

**Audience:** the named editor (maker) and the named second reviewer
(checker) from CONTENT-1. If those roles are still unassigned, read
`docs/DECISIONS.md` before using this handbook for real claims -- per
the build-pack §12 gate, no one may publish without a named person
owning source review and corrections.

**Acceptance for this document (CONTENT-15):** the editor and second
reviewer each read it and complete one dry-run claim on staging; the
owner signs off the corrections procedure in `docs/DECISIONS.md`. Both
of those are human steps this document cannot perform on its own.

---

## 1. What counts as an official source

An official source is one of, in priority order:

1. The exam, regulator or scheme's own government/statutory domain
   (e.g. an `.gov.in`/`.nic.in` body, `nta.ac.in`, `ugc.gov.in`,
   `aicte-india.org`) -- the notification, bulletin or scheme page
   itself, not a summary of it.
2. For a state fact: that state's own counselling-authority prospectus
   PDF or portal.
3. For a foreign pathway: the destination country's own government
   immigration/education domain, or the institution's own domain --
   *only* these two. British Council, "Study in X" portals and
   education-marketing aggregators are **leads to find the real page**,
   never the cited source (`docs/plan` recommended default, still
   pending final owner confirmation, but already enforced mechanically:
   `scripts/content/check_sources.py`'s aggregator block-list rejects
   exactly this class of domain).
4. An institution's own domain for a fact about only that institution
   (fees, seats, its own admission page) -- `source_type =
   institution_self_declared`, which is its own trust label, never
   silently upgraded to "checked against official source."

Not official, ever, regardless of how it reads: Wikipedia, comparison
sites (Careers360, Shiksha, CollegeDunia, GetMyUni, CollegeDekho,
LeverageEdu and similar), forums, and news coverage of a notification
(the notification itself is the source, not the article about it). See
`scripts/content/check_sources.py`'s `AGGREGATOR_DOMAINS` for the
current explicit block-list -- it is a proposed starting list, not
closed; if you find a new aggregator being cited, add it there and say
so to the editor lead, don't just skip it silently.

A domain not on `content/allowed_domains.txt` is rejected even if it
looks official to you. Getting a genuinely official new domain added is
an editor decision (that file's sign-off), not a per-claim workaround.

## 2. Always navigate from the official homepage

Never trust a deep link found in a draft file, a search result or an
aggregator page at face value. For every claim:

1. Start at the organisation's own homepage (typed by hand or from a
   bookmark you trust, not clicked from an unverified page).
2. Navigate to the actual notification/page yourself.
3. Confirm the URL you land on is the one you are about to cite --
   copy that address bar URL, not the one from wherever you started.

This catches stale links, redirects to a different (possibly outdated
or unofficial) page, and mirrors/impersonation domains. It also means
"I found this exact page by browsing the real site" is something you can
personally attest to when you sign as `checked_by`.

## 3. Quote capture

Every claim needs a **verbatim quote**: the exact sentence or table cell
from the source that states the fact, copied character-for-character
(not paraphrased, not translated, not summarised). This is one of
`scripts/content/validation.py`'s four automated checks
(`missing_verbatim_quote`) -- a row with an empty or whitespace-only
quote field is rejected before it ever reaches a human queue.

Rules:

- Quote only the sentence/cell that actually supports the value you are
  entering, not a whole paragraph -- the second reviewer needs to be
  able to find it fast.
- If the source states the fact only implicitly (e.g. a table you have
  to read two cells of), quote both cells and note how they combine.
- Record the section reference (heading, table name or page number) the
  quote came from, alongside the quote itself.
- Never quote an aggregator's paraphrase of an official source as if it
  were the official wording.

## 4. Freshness tiers and review_due rules

From `docs/DATA.md` (the authoritative claims model):

| Tier | Data | Review-due cadence |
| --- | --- | --- |
| 1 Critical | Exam dates, deadlines, eligibility, fees | Short (days) |
| 2 Cycle | College fees, seats, admission routes | Per admission cycle |
| 3 Annual | Rankings/accreditation (if shown) | Annual |

`review_due_on` is derived from the tier, never typed by hand
(`docs/CONTRACTS.md`, "Settled -- per-tier review-due"). The specific
day counts are a **recommended default, not yet owner-confirmed**
(`docs/plan/inventory-2-trust-content.md` open question): Tier 1 -- 14
days in-cycle; Tier 2 -- 180 days or next cycle start; Tier 3 -- 365
days. Use these as the working assumption and check `docs/DECISIONS.md`
for whether the owner has since fixed different numbers.

Past due is *stale*, not unverified: the value keeps showing with a
"last checked `<date>`" qualifier -- it is not pulled from public view
just because a review is late. Getting a Tier-1 (critical) claim
re-checked before it goes stale is the highest-priority queue item.

## 5. The eligibility completeness rule

A pathway's eligibility claims publish as a **complete documented set or
not at all** (`docs/plan` open question, adopted default; see also
`docs/DATA.md`: a pathway with no published rules returns
`insufficient_information`, never `not_eligible`). Concretely:

- Before publishing any eligibility criterion for a pathway, list every
  criterion that pathway's rule needs (age, marks percentage, subjects,
  domicile, category, qualification, year-of-passing -- whichever apply,
  per `app/rules/eligibility.py`'s criterion builders).
- Either every one of those criteria has a published, sourced claim, or
  none of them do for that pathway yet. Do not publish three of five
  criteria and leave the rest for later -- a partial set makes an
  eligibility outcome for the missing criteria which the engine cannot
  actually compute, and the resulting `insufficient_information` display
  would look like a gap rather than the honest "not sourced yet" it is.
- `scripts/content/validation.py`'s `incomplete_eligibility_set` check
  enforces this mechanically at import time by grouping rows per pathway
  and checking the full field set is present together, but the decision
  of *which* fields a given pathway's rule actually needs is a human
  judgement call against `app/rules/eligibility.py` and the exam's own
  notification -- the automated check cannot know that on its own if the
  field list itself is wrong or incomplete.
- NEET-UG specifically stays unpublished until the rules engine handles
  DOB cutoffs and OR-subject groups (`docs/plan` open question) --
  do not publish a partial NEET-UG eligibility set to work around this.

## 6. Handling conflicting sources

Two sources (or two claims) disagreeing about the same fact are never
silently merged or averaged (`docs/DATA.md` "Source allowlist": conflicts
are flagged and held). If you find two official sources stating
different values for the same field:

1. Do not publish either until resolved.
2. Prefer the more specific and more recent authority (e.g. the exam's
   own notification over a general ministry page; the latest bulletin
   over an older one) -- but record why you chose one, don't just pick
   silently.
2. If two *published* claims ever exist for one field (should not happen
   under maker-checker, but the contract has a rule for it anyway): the
   later `checked_at` wins, tie broken by later source publication date,
   then lower claim id (`docs/CONTRACTS.md`, "Settled -- two published
   claims on one field"). The losing claim is flagged for review, never
   silently discarded -- someone still has to look at it.
3. When in doubt, escalate to the corrections owner (Section 10) rather
   than guessing.

## 7. Forbidden wording (no ranks, suitability or guarantees)

CLAUDE.md's non-negotiables: "No rank predictions, no 'you are not
suited', no personality-type labels, no guarantees." The machine-
enforced version of this list lives in `docs/COPY.md` section 5
("Banned patterns") and is checked automatically against every rendered
template by `tests/unit/test_copy_rules.py` (DESIGN-3) -- but that scan
only covers `app/web/templates/**/*.html`, not editor-written claim
values, quotes or notes. When writing a claim's value, unit or any free
text an editor contributes (not the verbatim quote, which must stay
exactly as the source wrote it), never phrase it as:

- A rank prediction or predicted/likely score ("your predicted rank",
  "you will score in the top X").
- A suitability verdict ("you are/are not suited", a percentage match,
  "this is your best option").
- A personality-type label ("you are an analytical type", "your
  personality type").
- A guarantee of outcome ("guaranteed admission/selection/a seat", "100%
  guarantee", "sure-shot").
- An imperative telling the student what they must do ("you must
  choose/pick/become").

An accurate, sourced disclaimer that uses one of these words honestly
(e.g. a college's own published "no guarantee of admission" policy line,
quoted verbatim) is not itself banned -- the rule targets an *affirmative
claim of certainty, rank, suitability or personality*, not the presence
of a word. See `docs/COPY.md` section 5 for the exact regex list if
unsure.

## 8. Checker checklist (second reviewer)

Before approving any claim in the review queue, confirm:

- [ ] The source URL is on `content/allowed_domains.txt` and is not on
      the aggregator block-list (or has a *dated, editor-approved*
      exception recorded, if that mechanism exists yet).
- [ ] You personally opened the source from its own homepage (Section 2)
      and can see the quoted text on the live page today.
- [ ] The verbatim quote actually supports the entered value, unit and
      jurisdiction -- not a nearby but different figure.
- [ ] `checked_by` and `checked_on` are filled in and are not you (the
      author) -- maker ≠ checker is enforced server-side, but you should
      never even attempt to approve your own claim.
- [ ] The tier and `review_due` look right for this kind of fact
      (Section 4).
- [ ] If this claim is part of a pathway's eligibility set, the whole
      set is present, not a partial one (Section 5).
- [ ] No forbidden wording (Section 7) in any editor-written value, unit
      note or free text.
- [ ] The academic cycle label matches what the source itself states
      (e.g. `2026-27`), never rolled forward from a prior cycle.
- [ ] If this is a foreign-pathway money field, the currency is present
      and correct -- a money claim with a null currency renders
      `not_available`, never a silently-assumed INR figure.

Only after every box is checked does the claim get approved. If any box
fails, reject (Section 9) rather than approving with a private mental
note to "fix it later."

## 9. How to reject

Rejecting a claim always needs a stated reason (`PUB-7`'s contract: PATCH
requires a reason on reject). Write a specific, actionable reason a
different editor could act on without re-asking you what was wrong --
"source doesn't match" is not enough; "quote is from the 2025-26
notification, this claim is labelled 2026-27" is. A rejected claim
returns to the editor as `draft`; it is never silently deleted (claims
history is never deleted, only superseded once published).

## 10. How to supersede a published claim

A published claim is never edited in place once approved -- editing a
value while `in_review` already drops it back to `draft`
(`docs/CONTRACTS.md`), and a *published* claim can only be corrected by
superseding it:

1. Create a new claim for the same entity and field with the corrected
   value, its own source, quote and `checked_by`.
2. It goes through the same maker-checker review as any new claim.
3. On approval, the supersede function requires the new claim to already
   be published and to reference the same entity/field as the old one;
   critical (Tier 1) supersessions require a critical-authorised
   checker.
4. The old claim's `superseded_by` points at the new claim id -- history
   is kept, never deleted.
5. Superseding invalidates any cache and flags any saved student plan
   that used the old value for review (`saved_plans.needs_review` +
   reason) -- this happens automatically in the same transaction, not as
   a separate manual step.

## 11. The corrections owner's response time

Per CONTENT-1, the corrections owner is a **named person** (initially
the owner themself, doubling as editor, per the plan's recommended
default) responsible for triaging a reported wrong fact. **No specific
response-time SLA is settled in `docs/DECISIONS.md` yet** -- until the
owner records one, use this as the working default and flag it for
confirmation:

- Acknowledge a reported correction within **1 business day**.
- For a Tier-1 (critical: exam dates, deadlines, eligibility, fees)
  correction: investigate and either supersede or explain why the
  original stands within **3 business days**.
- For Tier 2/3 corrections: within **5 business days**.
- Every correction, whether it changes anything or not, gets a one-line
  note in the batch time-log (Section 12) so response times are
  auditable, not just promised.

## 12. Batch time-logging

The DPR measurement "editor hours per verified programme record and per
exam rule" (build pack §13) and the batch-expansion check "reviewer
hours per record" (`docs/research/batch-expansion-checklist.md`,
TRIAL-10) both need real numbers, not an estimate. For every batch of
claims reviewed in one sitting, the editor and the second reviewer each
log:

| Date | Batch (source or family) | Role (editor/checker) | # claims in batch | Minutes spent | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

Log this even for a small or a dry-run batch -- the pilot planning
estimate (roughly 15 minutes per claim for the editor, 5 minutes per
claim for the checker, per `docs/plan`) is explicitly provisional and
meant to be corrected from real wave-0 timing, not treated as accurate
in advance.

## 13. What the automated checks catch, and what only a human can catch

`scripts/content/validation.py` (CONTENT-6) runs four deterministic
checks over an import batch before anything reaches a human review
queue:

| Automated check | What it catches | What it cannot catch |
| --- | --- | --- |
| `missing_checked_by` | An empty/blank `checked_by` field | Whether the *named* checker is actually a different person from the author, or whether they actually looked at the source (that's the maker≠checker DB constraint plus your own honesty, not this check) |
| `missing_verbatim_quote` | An empty/blank quote field | Whether the quote is real, accurate, or actually supports the value -- a fabricated or mismatched quote passes this check every time |
| `aggregator_domain` | A source URL on the known aggregator block-list, or off `content/allowed_domains.txt` entirely, or not http(s) | A genuinely wrong official source (right domain, wrong page or wrong year); a redirect to an unofficial mirror that keeps the same domain in the URL you were shown |
| `incomplete_eligibility_set` | A pathway missing one or more fields from its declared required-field set | Whether the *declared* required-field set itself is correct for that exam/programme -- if the field list is wrong, this check will happily pass an incomplete-in-reality set |

In short: the automated checks catch **missing structure** (blank
fields, banned domains, an incomplete row set). They cannot catch
**wrong content that is structurally well-formed** -- a real-looking
quote that doesn't say what the value claims, a plausible but outdated
figure, a subtly wrong number transcribed from a real official page. That
judgement is exactly what Sections 1-6 and the checker checklist
(Section 8) exist for, and it is why maker-checker (a human second
reviewer) is not optional even when every automated check is green.

## 14. Dry run and sign-off

Before either named role reviews real content:

1. Both the editor and the second reviewer read this handbook in full.
2. Each completes one dry-run claim end-to-end on staging (draft ->
   review -> publish or reject), using a clearly synthetic or already-
   public low-stakes fact so a mistake costs nothing.
3. The owner records sign-off of the corrections procedure (Sections
   9-11) with a dated `docs/DECISIONS.md` entry.

None of the three steps above can be completed by an agent -- they are
CONTENT-15's human part, tracked separately from this document.
