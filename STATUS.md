# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
sign-in + saved plans + guest→account migration DONE** (BCI-004). **M4
maker-checker enforcement + publishing-console API DONE and verified
live** (BCI-005) — migration applied, every test that was skipping now
actually passes. **First real UI shipped** — Explore → Compare, the
first screens anyone could actually click through (BCI-006). **Reviewer
console shipped** — the publishing-console API now has a browser UI
(sign-in + review queue), not just curl/Postman. **Pilot scope widened**
(2026-09-21) — all-India admission rules, foreign/study-abroad pathways
added; see `docs/DECISIONS.md`. **Guardian-consent gate hardened**
(2026-09-21, this worktree/branch, NOT yet merged to `main`) — two
independent adversarial reviews of `0004_guardian_consent.sql` found a
CRITICAL complete bypass and two HIGH gaps; all fixed, see "Guardian-
consent gate: adversarial-review fixes" below.
**Commit:** see `git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green. **Hosting:** live on the Oracle VM (`eduvation.service`,
verified healthy, talking to the real database).

## What works right now — live routes, all verified
- `GET /careers` — published careers/pathways.
- `GET /compare?pathway_id=X&pathway_id=Y` — trust-labelled fields plus
  a real computed `net_to_arrange`; assumption editing via query param.
- `GET /eligibility?pathway_id=X&age=..&...` — criteria built
  dynamically from a pathway's own published claims.
- `POST /timeline` — stateless Career Life Span Calculator.
- `POST /auth/sign-up`, `POST /auth/sign-in` — real Supabase Auth,
  proven to actually authenticate against RLS. Sign-up optionally
  accepts a `pending_plan` and saves it as the new account's first plan
  in the same request — the guest→account migration. **`date_of_birth`
  is now required** (see the guardian-consent section below) — no
  regression for the existing 18+ behaviour, verified live this session.
- `GET /consent/confirm?token=...` — the guardian-consent confirmation
  page (new this session; not yet live-verifiable, see the ⚠️ section
  above and the dedicated section below).
- `POST/GET/PATCH/DELETE /plans` — save/list/edit/delete a plan, fully
  verified live, including student B provably unable to see or edit
  student A's plan through the real API.
- Deployed on your Oracle VM alongside `hisab`/`lekha`/`attendance-app`,
  nothing else touched.
- **`GET /explore`, `GET /compare/view` — an actual UI, for the first
  time, now reviewed and fixed.** Every route before this was JSON-only;
  nobody could click through any of it. Real Tailwind-styled pages: pick
  2-3 pathways on Explore (works with zero JavaScript — a plain HTML
  form), see them compared with trust-labelled fields and the four cost
  figures kept visually distinct, closing with docs/UI.md's exact
  required prompt. `ux-qa-reviewer` — unusable until now, its own
  trigger condition never having been met in this project — walked every
  scenario live (0/1/2/4 pathways, malformed/nonexistent ids,
  zero-claims pathways, an XSS probe) and found real issues, all fixed
  same session: a malformed `pathway_id` crashed to a bare 500 with no
  way back (very plausible given this product's WhatsApp-shared-link
  reality); every evidence link said "Official source" regardless of the
  actual trust label, directly contradicting the badge next to it for
  institution-reported/stale fields; the comparison grid never actually
  stacked on mobile despite a comment claiming it did; field order
  didn't match docs/UI.md; money figures were inconsistently formatted;
  a color-contrast pair measured just under WCAG AA; checkbox tap
  targets were 16px against ~44px guidance. No XSS found (Jinja
  autoescaping confirmed on); the zero-JS claim confirmed genuinely true.
  9 new regression tests plus the original 6, all live.
- **Maker-checker, enforced at the database, plus the publishing console
  API on top of it — now live and genuinely proven, not just written.**
  You applied `db/migrations/0003_maker_checker.sql`: a claim must always
  be inserted as a draft, the author of a claim can never approve their
  own, a published claim's recorded content is frozen (a correction
  means a new claim, never an in-place edit). `app/api/claims.py`
  (`POST /claims`, `/submit`, `/approve`, `/reject`, `/supersede`,
  `GET /claims`) sits on top of it, all wired to the real, live database.
- **Reviewer console (2026-09-21) — the publishing-console API now has a
  human-usable browser UI.** Until now every claims.py route was
  curl/Postman-only; nothing let a reviewer actually sign in and act on
  the queue. `GET/POST /reviewer/sign-in`, `POST /reviewer/sign-out`,
  `GET /reviewer/queue`, `POST /reviewer/claims/{id}/{submit,approve,
  reject}` — zero-JS plain forms, calling straight into claims.py's own
  route functions (one code path, not a second reimplementation).
  **First browser-reachable authenticated session this app has ever
  had**: every prior route only ever read an `Authorization: Bearer`
  header, which no plain browser GET/form-POST can attach — a new
  cookie-based session (`app/web/reviewer_pages.py`) fixes this,
  deliberately scoped to `/reviewer/*` only; `app/api/deps.py`'s
  header-only contract backing the JSON API and the student-facing pages
  is untouched. Cookie: httponly always, `samesite=lax` always (the CSRF
  defense for the zero-JS forms, since there's no script to carry a
  separate token), `secure` only in production, sized to Supabase's own
  token lifetime rather than an invented longer session, scoped to
  `/reviewer` only, never logged.
  Built via a workflow (implementer + a `data-security-reviewer` pass +
  a `ux-qa-reviewer` pass), then one fix round after review found a real
  HIGH-severity bug: the three write actions had no error handling, so
  self-approval (the first thing any reviewer would try, on their own
  draft) — or any other rejected transition — dead-ended in a raw
  unstyled JSON blob with no way back to the queue. Fixed: all three now
  redirect to the queue with a visible, styled error. Also fixed:
  missing aria-labels on identical per-claim buttons, a touch target
  under 44px, a raw `None` shown for a null claim value, an unhandled
  500 if the DB client itself failed to construct, and a hardcoded
  test-fixture password. Independently re-verified before merging — read
  every diff directly, ran the full suite myself, and live-reproduced
  the self-approval fix against the real database (303 redirect, styled
  error, claim status genuinely unchanged). 10 new live tests
  (`tests/db/test_reviewer_console.py`).

## The migration landing found 4 real bugs — in the tests, not the trigger
The moment `0003` was applied, every test that had been correctly
skipping (never run against real enforcement before) actually ran for
the first time — and found genuine problems, all in test fixtures that
had never been exercised live, not in the migration/trigger logic
itself:
1. Two tests set `superseded_by`/`created_by` to a fabricated random
   UUID. Both are real foreign keys (`superseded_by → claims(id)`,
   `created_by → auth.users(id)`, `db/migrations/0001_init.sql`) — a
   made-up id fails that constraint before the trigger under test is
   even reached. Fixed by using a real replacement claim / `None`
   (nullable) respectively.
2. Two tests' cleanup deleted a "replacement" claim before the claim
   that referenced it via `superseded_by` — Postgres's default `NO
   ACTION` (not `CASCADE`) on that foreign key blocks deleting a row
   that's still referenced. Fixed by reordering cleanup to delete the
   referencing row first.
3. `tests/db/test_api_claims.py` used a `second_reviewer` fixture
   defined only inside `tests/db/test_maker_checker.py` — invisible to
   any other file, and invisible to pytest's own fixture-not-found check
   while every test using it was being skipped. Moved to
   `tests/db/conftest.py`, alongside `reviewer`/`student_a`/`student_b`,
   where it always should have lived.
None of these were bugs a human or an agent could have caught by
reading the code — they only exist at the intersection of "this test
runs for real" and "this specific foreign key/fixture-scoping rule
applies," which is exactly why the task card said not to treat M4 as
verified until this exact moment.

**239 tests passing, zero skipped** — verified live, this session
(includes the reviewer console's 10 new live tests). Lint/typecheck
clean, CI green on every push this session.

**Fixed** (commit `1919c4d`): the flaky `test_sign_up_new_email_
succeeds_or_requires_confirmation` above — root cause found, not
papered over with a retry. `app/api/auth.py`'s sign-up handler caught
every Supabase Auth error as a bare `Exception` and flattened it to a
plain 400, discarding the structured status Supabase's own
`AuthApiError` carries. The test then had to guess whether a 400 was
"the known rate-limit case" by string-matching "rate limit" in the
free-text message — fragile, since Supabase has more than one
rate-limit error code (`over_email_send_rate_limit`,
`over_request_rate_limit`, confirmed live by inspecting
`supabase_auth.errors`) and nothing guarantees every variant's message
contains that exact substring. Fixed by propagating Supabase's real
`exc.status` (429 for a rate limit, confirmed against the actual
project, which is currently saturated from this session's own testing)
instead of hardcoding 400; the three affected tests now check
`status_code == 429` directly. Full suite rerun clean after the fix.

## Background UX review findings — both now fixed
A read-only `ux-qa-reviewer` pass this session (separate from the two
maker-checker bugs above) flagged two gaps; both closed:
1. **HIGH, fixed** — `GET /eligibility`'s `CriterionResultOut` was a bare
   `source_claim_id` UUID with no route resolving it to a displayable
   source, unlike `GET /compare`. Fixed the same way: fetches the
   claim/source rows it already has and resolves each criterion's
   `source_authority`/`source_url`/`verification_date`, same
   `_row_to_source`/`sources_by_id` pattern as `compare.py`. Draft claims
   still can't leak a source either — the existing published-only filter
   already covers the new fields since a criterion never exists for an
   unpublished claim in the first place. `POST /timeline` intentionally
   still doesn't resolve sources — it's stateless by design (no DB access
   at all), so resolution belongs to whatever builds its stage list, not
   to the route itself; noted for whoever builds that UI screen.
   **Caught while building this, same day, by a concurrent session's
   independent security review**: nothing validated the URL scheme on
   `Source.official_url` before it reached `href="{{ ... }}"` in a
   template — a `javascript:`/`data:` URI would render as a fully
   clickable, script-executing link on the evidence badge. Reviewer-
   write-only today, but the same "trusted-role write reaches render
   with no independent check" shape as the maker-checker bugs above.
   Fixed here with a `_safe_source_url()` guard (degrade a non-http(s)
   scheme to `None`, same pattern as any other "unavailable" field); the
   other session fixed the equivalent gap in `app/planning/comparison.py`
   (this route builds its URL independently, so neither fix covered the
   other). 3 new tests total across both fixes
   (`tests/db/test_api_eligibility.py`).
2. **LOW, fixed** (commit `86cffce`, other session) —
   `app/api/auth.py`'s docstring accuracy gap closed.

## Dedicated security review of the new UI surface — 6 real findings, all fixed
Separate from the UX review above: a security/correctness pass (4
independent reviewers, one dimension each — maker-checker/provenance,
XSS, cross-user/RLS, general correctness — every finding adversarially
re-verified 3x before being trusted) over `app/api/compare.py`'s
`assemble_comparisons()` refactor, `app/web/pages.py`, the Jinja
templates, and `app/planning/comparison.py`. 9 candidates, all survived
verification; 6 were real bugs/gaps (3 informational — confirmed no
regression from the earlier refactor, confirmed no RLS-bypass exists,
confirmed the reviewer role is currently unreachable through this UI at
all, which is fail-safe not a leak). All 6 real ones fixed same
session, independently re-verified again (2 more adversarial passes,
plus hand-tested against 13 bypass strings myself before merging).
Commits `fb776a2`, `39e4782`.
1. **HIGH, XSS** — `field_value_for()`'s `source_url` had no scheme
   check before reaching `href="{{ fv.source_url }}"` in
   `_trust_badge.html`. A `javascript:`/`data:` URI on `Source.official_url`
   rendered as a fully clickable, script-executing link on an evidence
   badge explicitly framed as "official source" — same class the other
   session independently caught in `eligibility.py`'s own copy of this
   pattern the same day. Fixed with `_safe_source_url()`: allowlists
   `http`/`https` only, via `urlsplit` (robust against
   case/whitespace/embedded-control-character bypasses).
2. **LOW** — `verification_date` was the one field in `field_value_for()`
   not gated on `label != not_available` — an unpublished/synthetic
   claim's date leaked even though its value/source were correctly
   hidden. Now gated identically to the other three fields.
3. **MEDIUM** — `GET /compare` (JSON) had zero UUID-shape validation;
   a malformed `pathway_id` crashed to an unhandled 500. `GET
   /compare/view` (HTML) already had this fix from the UX review, but
   the refactor that shared `assemble_comparisons()` between both
   routes never carried it to the JSON side. Now both return a clean
   422, matching `plans.py`'s established convention.
4. **LOW** — requesting the same `pathway_id` twice passed validation
   and silently rendered the same pathway twice as a fake comparison.
   JSON route now 400s; HTML route degrades to the existing friendly
   message.
5. **MEDIUM, test coverage** — no test authenticated as a reviewer
   against `/compare`/`/explore`/`/compare/view`. The reviewer role is
   the *only* one whose RLS-scoped client can fetch a draft claim row
   at all, so a guest-only test suite was only proving RLS filters
   correctly, never actually exercising `field_value_for()`'s own
   independent status re-check end-to-end. Added, mirrors the existing
   pattern in `test_api_eligibility.py`.
6. **MEDIUM, test coverage** — `/compare/view` (HTML) had no live
   regression pinning its draft/synthetic-claim protection, unlike the
   JSON route. Added.

## Design mockup (2026-09-19, separate session — no repo code touched)
A design canvas of the whole app now exists, built from `docs/UI.md` and
`docs/PRODUCT.md`: the seven student screens at phone width (quick start,
explore, compare with a working route switch, time and cost, programme
detail, my plan, Ask BCION), the comparison screen on desktop, the
reviewer publishing console, and a difficult-states sheet.
Link (private to the owner until shared):
https://claude.ai/artifact/UfLEdwJgiswwBPGu8cbXVo
Every figure on it is sample data under a "not verified facts" ribbon;
bracketed items are blanks for real records. Not rendered or reviewed by
a person yet — it is a starting point for usability round 1, not a frozen
component set.

## Blockers
**One real blocker remains, below — narrower than before, not gone.**

## ⚠️ Read this one — guardian-consent gate is BUILT, needs two owner actions before it protects anyone
Per your decision this session (on the mechanism: an age gate at
sign-up, and for anyone under 18, a guardian email that must confirm via
a separate emailed link before the account activates), the gate
described as a hard blocker in this section previously is now built —
schema, sign-up/sign-in enforcement, the confirmation endpoint, a
pluggable email sender, and live regression tests. **Two things still
need you, specifically, before it provides real protection:**

1. **Apply `db/migrations/0004_guardian_consent.sql`** to the live
   Supabase project — same manual step as 0001/0002/0003 (SQL Editor, or
   `python scripts/apply_migrations.py` once `DATABASE_URL` is in your
   own `.env`; see `db/migrations/README.md`). **I could not do this
   myself this session** — this worktree's `.env` has real
   `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` values (copied from the
   repo root, same as prior sessions) but no `DATABASE_URL`, so
   `scripts/apply_migrations.py` has nothing to connect with, and I did
   not use the Supabase MCP tool (off-limits for this project per
   `docs/DECISIONS.md` "Infrastructure accounts"). Confirmed live,
   this session: `app.api.guardian_consent.guardian_consent_schema_is_live()`
   returns `False` against your real project right now.
   **Until this is applied, the app fails CLOSED, not open**: an
   under-18 sign-up is refused outright (503, "not yet available") rather
   than silently let through active — verified live this session (see
   below). Nothing about existing (adult) sign-up/sign-in changes either
   way.
2. **Provision a real email provider** (any SMTP relay — SendGrid, SES,
   Mailgun, Resend, a plain mailbox — all expose one) and put the
   credentials in your own `.env` (`SMTP_HOST`/`SMTP_USERNAME`/
   `SMTP_PASSWORD`/`SMTP_FROM_ADDRESS`, see `.env.example`). Until then,
   `app/notifications/logging_sender.py`'s `LoggingEmailSender` is what
   actually runs — it logs what would be sent (including the real
   confirmation link/token) and reaches no real inbox. **This was
   deliberately not done for you this session** — the task was explicitly
   scoped not to sign up for or configure a real provider account, the
   same way `GEMINI_API_KEY` needed you to provision Gemini yourself.
   `app/notifications/smtp_sender.py`'s `SmtpEmailSender` is a complete,
   working implementation (stdlib `smtplib`, no new dependency) gated
   exactly like `app/ai/gemini_provider.py` — flip `Settings.
   email_configured` true by setting those four values and it's live,
   nothing else to build. **Note (adversarial review, 2026-09-21,
   documentation only):** while `LoggingEmailSender` is what's running,
   its `INFO`-level log line includes the raw confirmation token — see
   `docs/SECURITY.md` "Consent & safeguarding" for the full note. Drop
   that line to `DEBUG` or redact it before any real log
   aggregation/shipping is wired up, not after.

**Why this split matters, concretely**: right now, the database half of
this gate is real and tested (once #1 is applied) — a pending account
genuinely cannot sign in, genuinely cannot self-activate, and the
under-18 sign-up path is closed rather than silently bypassed while #1
is outstanding. But without #2, a real guardian's confirmation email
never reaches them — the mechanism would look complete and quietly
provide no actual protection if #2 were mistaken for optional. Full
design writeup and the residual, named risks (self-declared age with no
identity verification, same limitation `docs/SECURITY.md`'s consent
section already accepts pilot-wide) are in `db/migrations/
0004_guardian_consent.sql`'s own docstring and `app/api/guardian_consent.py`'s.

**What I verified live this session** (real Supabase project, this
worktree's copied `.env`): `db_configured` is `True` (a real project is
reachable); `guardian_consent_schema_is_live()` is `False` (0004 not
applied yet); a minor sign-up attempt against the real project correctly
returns `503` rather than creating an unusable-but-unprotected account
(confirmed via `python -m app` locally, not a unit-test mock). **What I
could NOT verify live**: the actual gate behaviour that needs the new
tables/functions to exist (`tests/db/test_guardian_consent.py` — the
full sign-up/sign-in/confirm/RLS suite) — it correctly SKIPS with a
clear reason (`tests/db/conftest.py`'s `_guardian_consent_migration_
applied` check, mirroring 0003's own established pattern) rather than
silently passing or erroring. Re-run `pytest tests/db -q` after applying
0004 to get a real pass/fail on all of it — see the task summary for the
full list of scenarios it covers.

Previously, this section described `POST /auth/sign-up` as fully open
with no code path disabling a minor's account at all — that gap is
closed at the code level now; what remains is deployment, not design.

### What was built this session, file by file
- `db/migrations/0004_guardian_consent.sql` — `student_accounts`
  (`date_of_birth`, `account_status`), `guardian_consents` (`token`,
  `status`, `expires_at`), two enforcement triggers (age-vs-status on
  insert; insert-must-be-pending, mirroring `0003`'s "insert must be
  draft"), two security-definer functions (`my_guardian_consent_status`,
  `confirm_guardian_consent`), RLS with no SELECT policy at all on
  `guardian_consents` (the token is unreadable through the normal API,
  by anyone, ever) and no UPDATE policy on either table (only the
  security-definer confirm function can transition status). Own docstring
  has the full reasoning, including why two new tables rather than
  columns on `student_profiles`.
- `app/api/guardian_consent.py` (new) — age arithmetic
  (`MINOR_AGE_THRESHOLD_YEARS = 18`, named assumption), the sign-up-time
  request creator, and `enforce_guardian_consent_gate` — the actual
  sign-in-time enforcement, called from `app.api.auth.authenticate()` so
  both `POST /auth/sign-in` and the reviewer console's sign-in get it for
  free. Also `guardian_consent_schema_is_live()`, the "has 0004 been
  applied yet" probe that lets the rest of the app degrade safely (fail
  CLOSED for a minor sign-up, no-op for everyone else) while it hasn't.
- `app/api/auth.py` — `SignUpRequest.date_of_birth` (required),
  `.guardian_email` (required only when under 18); `AuthResponse` gained
  `account_status`/`message`, `access_token` is now optional (null on a
  pending account). `authenticate()` calls the gate above.
- `app/notifications/` (new package) — `sender.py` (the `EmailSender`
  Protocol), `logging_sender.py` (`LoggingEmailSender`, what actually
  runs everywhere today), `smtp_sender.py` (`SmtpEmailSender`, real and
  working but gated exactly like `GeminiProvider`, unconfigured
  everywhere), `factory.py` (`get_email_sender()`, picks between the
  two), `guardian_consent_email.py` (the email's actual text).
- `app/web/consent_pages.py` + `templates/consent_confirm.html` (new) —
  `GET /consent/confirm?token=...`, zero-JS, one generic failure message.
- `app/core/config.py` — `app_base_url`, `smtp_*` fields (all unset by
  default), `email_configured` property. `.env.example` documents the
  new names (values still nowhere in the repo).
- `tests/db/test_guardian_consent.py` (new, 14 tests, all correctly
  SKIP today — see above), `tests/unit/test_guardian_consent.py` (new,
  age-arithmetic + EmailSender-gating unit tests, all passing).
  `tests/db/test_api_auth.py` updated (`date_of_birth` added to every
  existing sign-up call) and `tests/db/conftest.py` gained the 0004
  skip-detection, mirroring 0003's own pattern exactly.
- **Verified this session, live, against the real (unmigrated) project**:
  `ruff check app tests` clean; `mypy` clean on every file this task
  touched (`mypy app --follow-imports=skip` — whole-app baseline, 41
  files, clean; a plain `mypy app` currently fails on an unrelated,
  pre-existing environment issue — numpy 2.5.2's own type stub uses
  Python-3.12-only syntax, reproduced identically on `app/ai/
  gemini_provider.py` alone, a file this task never touched — not caused
  by or specific to this session's changes); `pytest tests/unit -q` — 185
  passed; `pytest tests/db -q` — **110 passed, 14 skipped (the new
  guardian-consent tests, for the documented reason above), 0 failed** —
  i.e. every pre-existing live test still passes unchanged, including the
  adult sign-up/sign-in paths this task's own instructions called out as
  important not to regress.

## Guardian-consent gate: adversarial-review fixes (2026-09-21, this
## worktree/branch — NOT yet merged to `main`)
Two independent adversarial reviews of the migration above (`1a714d5` in
this worktree) found a **CRITICAL complete bypass** and **two HIGH
gaps**, all closed this session, plus one MEDIUM and two LOW/doc-only
items. All fixes live in `db/migrations/0004_guardian_consent.sql` itself
(still unapplied anywhere, so editing it in place is correct — see the
file's own "append-only" note), `app/api/guardian_consent.py`,
`app/api/auth.py`, `docs/SECURITY.md`, and `tests/db/test_guardian_consent.py`.

1. **CRITICAL — complete bypass, `guardian_consents.token`.** The INSERT
   RLS policy constrained only `student_id`; nothing forced `token` to be
   server-generated. A caller could INSERT their own pending-consent row
   with a SELF-CHOSEN `token`/`guardian_email`, then call the
   anon-grantable `confirm_guardian_consent(p_token)` RPC with that same
   token to activate their own account with zero real guardian
   involvement. The migration's own comments *claimed* a trigger already
   prevented this — no such trigger existed. **Fixed**: a new BEFORE
   INSERT trigger (`enforce_guardian_consent_server_token`, mirroring
   `enforce_account_status_matches_age`'s existing pattern) unconditionally
   overwrites `token` (via `pgcrypto`'s `gen_random_bytes`, hex-encoded)
   and `expires_at` on every insert — a client-supplied value is silently
   replaced, never merely rejected, so the row is still usefully created.
   `app/api/guardian_consent.py`'s `create_guardian_consent_request` no
   longer generates the token client-side (dead code removed,
   `secrets.token_urlsafe` import gone) — it reads the real token back
   from the INSERT's own response instead, the same "trust what the
   database actually wrote" pattern `_migrate_pending_plan` already uses
   for a saved plan's id. **New tests**:
   `TestTokenAndExpiryAreServerGenerated` (2 tests) — proves a
   client-supplied token is overwritten and the attacker's chosen value
   can never confirm anything; same for `expires_at`.
2. **MEDIUM — no DB-level rate limit on `guardian_consents` inserts.**
   Idempotency was only ever enforced in Python (catching a unique-
   violation on the *`student_accounts`* insert). A direct API caller
   could otherwise INSERT unlimited `guardian_consents` rows with
   arbitrary `guardian_email` values — a spam vector once a real email
   provider exists. **Fixed**: a partial unique index
   (`guardian_consents_one_pending_per_student`, on `student_id` where
   `status = 'pending'`) enforces "at most one outstanding pending
   request per student" at the database layer regardless of caller;
   `create_guardian_consent_request` also now catches this
   unique-violation gracefully (same idempotent-return shape as the
   existing `student_accounts` case). **New test**:
   `TestOnlyOnePendingConsentPerStudent`.
3. **HIGH — a minor could name themselves as their own guardian.**
   Nothing stopped `guardian_email` from case-insensitively equalling the
   student's own sign-up `email`. Not exploitable today (no real email
   provider configured) but a complete, trivial defeat the moment one is.
   **Fixed**: `POST /auth/sign-up` now rejects this with a 400, same
   posture as the adjacent "guardian_email is required" check. **New
   test**: `test_under_18_sign_up_with_guardian_email_same_as_own_email_is_rejected`.
4. **HIGH — the gate wasn't backed by RLS on the tables that actually
   hold student data.** `enforce_guardian_consent_gate` is the ONLY place
   that ever blocked a pending account — real for every session this
   app's own `authenticate()` issues, but not a database guarantee: any
   future auth path that mints/accepts a session without going through
   `authenticate()` (password reset, magic link, OAuth, a future browser
   client talking to Supabase directly) would silently bypass this gate
   completely for `saved_plans`/`student_profiles`, which had zero
   reference to `account_status` in their own RLS. **Fixed**: a new
   `account_active(uid)` security-definer function (mirrors `is_reviewer()`
   exactly; default-open when a uid has no `student_accounts` row at all,
   since not every account is gated) is now ANDed into both
   `student_profiles_own_row` and `saved_plans_own_row`'s USING/WITH
   CHECK clauses. **New tests**: `TestAccountActiveGatesOtherOwnRowTables`
   (2 tests) — a pending account's own, validly-obtained-outside-the-app
   token can no longer read its own `saved_plans`/`student_profiles` row.
5. **LOW — no cross-user access-matrix coverage on this migration's own
   tables.** `tests/db/test_guardian_consent.py` never exercised
   `student_b`/`guest_client`/`reviewer` at all — CLAUDE.md requires this
   "every time auth, RLS or publication changes." **Fixed**: new
   `TestCrossUserAccessMatrix` (6 tests), mirroring
   `tests/db/test_api_plans.py`'s own pattern exactly.
6. **LOW, documentation only — no code change.** `app/notifications/
   logging_sender.py` logs the full email body, including the raw
   confirmation token, at `INFO` level — deliberate today (nowhere else
   for the token to go), but must be dropped to `DEBUG` or redacted
   before any real log aggregation/shipping exists. Noted in
   `docs/SECURITY.md` and above.

**Verified this session** (`ruff check app tests` clean; `mypy app
--follow-imports=skip` clean, 41 files — the same pre-existing,
unrelated numpy/3.12 stub issue on a plain `mypy app` noted above
recurred and was worked around the same way; `pytest tests/unit -q` —
185 passed): `pytest tests/db -q` — **110 passed, 26 skipped, 0 failed**
(26 = the prior 14 plus 12 new tests for the fixes above — every one of
them correctly SKIPS, for the same documented reason as before: migration
`0004` is still not applied to the live project). **What I could NOT
verify live**: the actual trigger/index/RLS behaviour these fixes add —
same limitation as the original build, unchanged by this session. I did
not attempt to apply the migration myself (no `DATABASE_URL` in this
worktree's `.env`; the Supabase MCP tool remains off-limits per
`docs/DECISIONS.md` "Infrastructure accounts"). Committed to this
worktree's own branch (`worktree-wf_7ee1927f-553-1`); not pushed, not
merged — that decision is left to the orchestrating session, per its own
instructions. **Owner action needed before any of this is real**: apply
the (now-fixed) `0004_guardian_consent.sql` to the live project, then
re-run `pytest tests/db -q` for a genuine pass/fail on all 26
guardian-consent tests plus the pre-existing 110.

## Other bugs found and fixed this session (not assumed away)
1. **Security**: the database client was a shared singleton — under real
   concurrent traffic, one user's access token could have leaked onto
   another user's request. Found, fixed, regression-tested. An
   independent review then found and fixed a follow-on connection-leak
   issue in the same area, plus hardened the regression tests and config.
2. The guest→account plan migration silently failed every call at
   first — an insert that forgot to set `student_id` was correctly
   rejected by RLS, invisible because the function's own "never fail
   sign-up over a bad plan" design swallows the exception. Fixed; **now
   also logs the failure** (`user_id`/`pathway_id` only — never the
   student-supplied notes/figures) so a recurrence won't be invisible
   again.
3. **Fixed**: `POST /plans`'s error handling mislabelled two distinct
   failures (a nonexistent `pathway_id`, a malformed UUID) as "already
   saved" — now 404 and 422 respectively, 409 reserved for a genuine
   duplicate. A malformed `plan_id` on update/delete used to crash to a
   raw 500 — now a clean 422, checked before any query runs.
4. **Test-coverage gaps closed**: the review's live probes (reviewer vs.
   saved_plans, delete cross-user) were correct but had no permanent
   regression test — 6 new tests added, all passing
   (`tests/db/test_api_plans.py`).
5. **Fixed** (commit `1d92af3`): `app/planning/comparison.py`'s cost
   assembly read `estimated_additional_expenses_hint` straight out of
   the claims dict for both the displayed breakdown and
   `net_to_arrange`'s arithmetic — the one field on the whole comparison
   screen that skipped `field_value_for()`'s published/synthetic-source
   checks. A draft or synthetic-sourced hint could have leaked into a
   real total. Found by a background UX-review agent, independently
   re-verified, fixed with a shared `_estimated_additional_expenses_hint()`
   helper both call sites now use. Also fixed the adjacent display
   inconsistency the same review flagged: the breakdown used to show
   blank/`None` for "no hint" while the total below it silently assumed
   ₹0 for the same case — the breakdown now shows 0.0 too, so the line
   item always matches what the total was computed from. 6 new
   regression tests in `tests/unit/test_comparison.py`.
6. **Fixed, more serious** (commit `0e57606`): `GET /eligibility`
   trusted RLS visibility as a proxy for "this claim is published" —
   true for a guest/student, but a reviewer's own RLS-scoped client can
   also SELECT draft/in_review/superseded claims (by design, so they
   can review them; `db/migrations/0001_init.sql`'s
   `claims_select_published` policy is `status = 'published' or
   is_reviewer()`). `_criteria_from_claims` built a criterion from
   whatever came back with no status check, so a reviewer calling
   `/eligibility` on a pathway with an unapproved draft criterion got
   an actual **eligibility outcome** computed from it — not just a
   wrong displayed number, a wrong "meets"/"does_not_meet". Fixed by
   filtering to published claims first. Proved the test catches the
   real bug, not just green-by-luck: reverted the fix locally, confirmed
   the new regression test in `tests/db/test_api_eligibility.py` fails,
   restored the fix, confirmed it passes again.

Full details on all of these in `docs/DECISIONS.md`.

## Next task
**The consent-gate decision above is the one that actually matters right
now** — everything else is normal backlog. All engineering milestones
through M4 are done and genuinely verified (migration applied, zero
tests skipping). Candidates for what's next, all your call: more UI
screens (quick start, timeline/cost calculator, a reviewer console for
the publishing API — see `tasks/BCI-006.md`'s full "not done yet" list,
including that Playwright e2e still isn't wired), M5 (bounded AI), or a
content/design pass.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`). Schema `0001`/`0002`/`0003` applied and verified. **`0004_guardian_consent.sql` written this session, NOT yet applied** — see the ⚠️ section above; `tests/db/test_guardian_consent.py` correctly skips until it is. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input
1. **Consent/safeguarding gate — see the ⚠️ section above.** The
   mechanism is built; **two concrete actions remain**: apply
   `db/migrations/0004_guardian_consent.sql`, and provision a real email
   provider (SMTP credentials in your own `.env`). Blocks item 2 below.
   Not blocking engineering elsewhere, but blocking any move toward
   public reachability — arguably more so than before, since a
   not-yet-merged worktree (`.claude/worktrees/wf_9b7797a4-e76-1`,
   confirmed still present via `git worktree list` this session, branch
   `worktree-wf_9b7797a4-e76-1` — its contents were not read or touched;
   this session is isolated to its own worktree) is building a browser-
   facing student sign-up UI on `app/web/student_pages.py`, a file that
   does not exist on this session's own base branch. **That UI's own
   `student_sign_up_submit()` will need a `date_of_birth` field (and a
   `guardian_email` field, shown conditionally once age is known) added
   to its form and forwarded to `POST /auth/sign-up` exactly as the JSON
   API now requires — whoever merges that work next should read this
   entry and `app/api/auth.py`'s `SignUpRequest` before wiring the
   form**, or that screen will 400 on every under-18 submission (or, if
   it hand-builds its own request body without the new fields, silently
   422 with FastAPI's own "field required" error) until it's updated.
2. **Public domain** — hold until item 1 is resolved (both parts). Once
   it is, send a domain/subdomain and I'll add an nginx site.
3. **Pilot scope widened (2026-09-21, resolved)** — admission rules now
   all-India (was one-state/Gujarat), plus foreign/study-abroad pathways
   for Indian students added as new scope. See `docs/DECISIONS.md`
   2026-09-21. **Open follow-up**: whether the numeric ceilings (20–30
   career families, 50–100 programme records, 12-week schedule) also
   change or whether the wider scope is phased in within them — not yet
   answered.
4. **Named content reviewers**, **Gemini model** — not blocking.

## Content drafts — NEET (UG) added and cross-checked (2026-09-19)
`docs/content-drafts/neet-ug-eligibility.md` — draft research only, same
rules as the GUJCET draft: unverified, unpublished, nothing inserted into
the database. Two independent official sources now, not one: NTA's
official NEET (UG)-2026 Information Bulletin (124-page text PDF), plus a
same-session follow-up that reached NMC's own site (retrying past the
earlier redirect/404) and read the actual primary law it's based on —
**Graduate Medical Education Regulations, 2023** and its 16.06.2023
Corrigendum, both official Gazette of India notifications, full text.
Age and required-subjects are now confirmed by both documents, verbatim,
independently. Worth knowing the regulation's original text said the age
cutoff was 31 **January**, corrected to 31 **December** three months
later by the corrigendum — the version now in force matches the
bulletin. The regulation's own silence on a Class-12 marks floor,
domicile and exam-attempt limits strengthens (not just repeats) those
three "not found" conclusions from the bulletin alone. Full corroboration
log in the draft's own "Corroboration done this session" section. Three
things worth knowing before anyone builds a NEET pathway on it:
1. **The bulletin has no Class 12 marks floor and no upper age limit.**
   The widely repeated "50% PCB" / "age 25" figures are not in it — the
   draft publishes no claim for either rather than guessing. (The
   `maximum_age(25)` in `tests/unit/test_eligibility.py`'s NEET-style
   fixture is synthetic and fine as an engine test, but must never be
   copied into content.)
2. **Two rules-engine gaps would give students wrong answers** if NEET
   claims were published as-is: minimum age is "17 by 31 Dec of the exam
   year" (a DOB cutoff — today's integer-age check would wrongly reject a
   16-year-old who qualifies), and subjects are "Biology **or**
   Biotechnology" (`required_subjects` is all-of only). No code changed
   this session; both need a decision first.
3. **It's the 2026 cycle, already sat (03 May 2026).** The 2027 bulletin
   wasn't out; DOB cutoff and fees are 2026-only.
No tests run this session — docs-only change, no code touched.

## Not claimed
No e2e test, no live AI call, no public exposure of the deployed app
yet. No real content exists — every test uses clearly-labelled synthetic
fixtures; nothing has been published as a verified fact for an actual
student to see.

## Concurrent sessions — multiple sessions worked this repo today
This session shared the repo with at least one other active Claude
session for a significant stretch (same machine, same working
directory). Coordination happened via direct cross-session messaging
throughout: file-touch lists exchanged before editing, commits kept
separate when both sides had uncommitted work, a circular-import bug and
later a resource-leak bug each caught and fixed collaboratively, a
second independent security-review pass run on request. See
`docs/DECISIONS.md` for the full log. If you're running multiple
sessions on purpose, this worked cleanly; if not, worth knowing.
