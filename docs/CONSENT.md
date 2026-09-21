# Consent and safeguarding — design contract

Status: **frozen design, partly built.** Phase 1 of the pilot is
**adults-only and invite-only**; real minor accounts stay disabled
(`MINOR_ACCOUNTS_ENABLED` defaults false) until a person other than this
document's author has reviewed the workflow.

People are referred to by role placeholder throughout. The names are
CONSENT-2's (owner) to record in `docs/DECISIONS.md`; contact details
stay outside the repo.

- `<SAFEGUARDING-CONTACT>` — receives distress flags within 24 hours.
- `<SAFEGUARDING-BACKUP>` — covers when the first is unreachable.
- `<CONSENT-WORKFLOW-REVIEWER>` — non-author human reviewer; their
  sign-off is the gate that can flip `MINOR_ACCOUNTS_ENABLED`.

## 1. What already exists

Migrations `0004`–`0006` are merged, adversarially reviewed and
live-verified: a guardian-consent gate on sign-up. It is **not** the
build pack's verifiable-parental-consent mechanism; it is a weaker
interim gate, and this document treats it as such.

- `student_accounts(id, date_of_birth, account_status, created_at,
  updated_at)`; `account_status` is the enum
  `('active', 'pending_guardian_consent')`.
- `guardian_consents(id, student_id, guardian_email, token, status,
  created_at, confirmed_at, expires_at)`; `guardian_consent_status` is
  `('pending', 'confirmed', 'expired')`; 72-hour expiry.
- `enforce_account_status_matches_age()` — BEFORE INSERT trigger: an
  under-18 row can never be inserted `active`.
- `enforce_guardian_consent_server_token()` — BEFORE INSERT trigger:
  overwrites `token` and `expires_at` on every insert, so a client can
  never choose either.
- `create_guardian_consent_request(p_date_of_birth date,
  p_guardian_email text) returns text` — definer, needs `auth.uid()`.
- `confirm_guardian_consent(p_token text) returns boolean` — definer,
  executable by `anon`, flips the consent row to `confirmed` and the
  account to `active`.
- `my_guardian_consent_status()`, `account_active(uid uuid)`.
- `app/api/auth.py` requires `date_of_birth`; an under-18 sign-up
  additionally requires a `guardian_email` that is not the student's own
  address, and returns **no access token** for a pending account.
- `GET /consent/confirm?token=…` is the guardian's link target.

## 2. Account states

The plan's proposed names are superseded by what is merged. Settled:

| State | Meaning | Phase |
|---|---|---|
| *(no row)* | Guest, or a signed-up auth user with no `student_accounts` row yet. Not an enum value. | 1 |
| `pending_guardian_consent` | Under-18 sign-up awaiting the guardian's confirmation. No session issued. | 1 (built) |
| `active` | Consent state is settled. | 1 (built) |
| `frozen` | Withdrawn. Read-only, no new writes. | CONSENT-4 |
| `deletion_due` | Deletion scheduled, 30-day window running. | CONSENT-4 |

`active_adult` and `active_minor` are **not** separate states. Adult
versus minor is derived from `student_accounts.date_of_birth`, which the
BEFORE INSERT trigger already enforces against `account_status`. Adding
a status per age band would duplicate a fact the database already has and
create a way for the two to disagree.

**Admission is a separate axis from consent state.** `account_status`
answers "is this account's consent settled"; admission answers "has this
person been let into the pilot". Settled: CONSENT-4 adds
`student_accounts.admitted_at timestamptz`, writable only by
`redeem_invite`, and `is_admitted()` means
`admitted_at is not null and account_status = 'active'`. CONSENT-4's card
says it *creates* `account_status`; it must be rewritten to **extend the
existing enum additively** — the lead owns that edit.

## 3. Admission: the invite redemption sequence

Supabase returns **no session at sign-up** when email confirmation is on
(`app/api/auth.py` already handles `result.session is None`). Redemption
therefore cannot happen at sign-up: there is no `auth.uid()` to bind the
invite to. Settled sequence:

1. An invite code is issued out of band by the owner. Only its hash is
   stored, in `pilot_invites`. Codes never enter the repo.
2. At sign-up the code is checked advisory-only with
   `invite_is_valid(code)` — anon-executable, returns a bare boolean,
   returns no row and reveals nothing enumerable. This exists so a typo
   fails immediately rather than after an email round trip.
3. The student confirms their email and signs in for the first time.
4. An "enter your invite code" screen asks for the code **again**, and
   the app calls `redeem_invite(code)` with the real session.
   `redeem_invite` re-validates everything server-side; step 2 grants
   nothing.
5. Until redemption succeeds `is_admitted()` is false and RLS refuses
   every write to `saved_plans` and `student_profiles`.

The guardian gate solved the same no-session problem by parking
`date_of_birth` and `guardian_email` in Supabase user metadata. Invites
deliberately do **not** reuse that trick: user metadata is readable by
the user's own session and travels in the JWT, and a live invite code is
credential-like. Re-asking costs one screen and stores nothing.

## 4. Function contract (CONSENT-4)

All `security definer`, `set search_path = public`, `auth.uid()`-scoped.

- `invite_is_valid(p_code text) returns boolean` — stable; true only for
  an unused, unexpired hashed match.
- `redeem_invite(p_code text) returns boolean` — the **only** way to
  become admitted. Requires `auth.uid()`. Marks `used_by`/`used_at` and
  stamps `admitted_at`. Single-use, no re-redeem.
- `is_admitted(p_uid uuid default auth.uid()) returns boolean` — stable;
  used inside RLS write policies.
- `is_safeguarding_staff(p_uid uuid default auth.uid()) returns boolean`
  — stable.
- `withdraw_account() returns void` — sets `frozen`, stamps
  `deletion_due_at = now() + interval '30 days'`, appends a withdrawal
  row to `consents`. Never deletes inline.

Tables: `consents` (append-only, one row per grant or withdrawal),
`pilot_invites` (hashed code, expiry, `used_by`, `used_at`),
`safeguarding_staff`, `safeguarding_flags` (category and ids only — never
message text).

## 5. Data stored, and not stored

Stored: `date_of_birth` (once, in `student_accounts` — the server must be
able to re-check the age gate itself); the guardian's email address while
a request is live; consent wording version and timestamp per consent row.

Not stored, ever: identity documents, caste or category certificates,
counselling history, distress message text, a second copy of a date of
birth anywhere else, invite codes in plaintext, contact details of the
placeholder roles above.

The plan proposed storing an adult self-attestation *instead of* a birth
year. That is superseded: the merged gate already stores
`date_of_birth` for every account, and a per-age-band attestation on top
of it would be a second, divergent copy of the same fact. Consent rows
store the **wording version** consented to, not the person's age.

## 6. Safeguarding

- **Distress.** A keyword rule (Phase 2) returns the national
  tele-mental-health helpline and raises a `safeguarding_flags` row —
  category and ids only — notifying `<SAFEGUARDING-CONTACT>` within 24
  hours, `<SAFEGUARDING-BACKUP>` on failure. The helpline number is a
  verified claim like any other fact, checked at launch; it is never
  hardcoded from memory and never generated by AI. No counselling that
  does not exist is promised.
- **Staff-only visibility.** Students *and* content reviewers read zero
  rows of `safeguarding_flags`, `pilot_invites` and other people's
  `consents`. Proven by the guest / student A / student B / reviewer
  access matrix, rerun on every change.
- **Withdrawal.** Freezes immediately; deletion completes within 30 days
  (AUTH-10's narrow definer function). The append-only `consents` trail
  survives as the record that a withdrawal happened, carrying no personal
  content.

## 7. Anon-key bypass analysis

The Supabase anon key is public by design — it ships to the browser.
Every protection below is RLS or a definer trigger, never "the client
will not call that".

- **Anon key alone.** Can call `confirm_guardian_consent(token)` — it is
  granted to `anon` because a guardian has no account. Safety rests on
  the token being server-generated, unguessable, single-use by status
  and 72-hour expiring, never on the caller's identity. `guardian_consents`
  itself is unreadable, so tokens cannot be enumerated.
- **Own valid access token.** Own-row RLS permits inserting one's own
  `student_accounts` row directly against the REST API, bypassing the
  application entirely — which is exactly why
  `enforce_account_status_matches_age()` is a database trigger. Declaring
  yourself `active` while under 18 is refused by Postgres.
- **Token injection.** A client cannot set `token` or `expires_at`: the
  BEFORE INSERT trigger overwrites both unconditionally.
- **Gap CONSENT-4 must close.** Today an un-admitted account with a
  confirmed email can still write `saved_plans`. `is_admitted()` must be
  added to those write policies, and `admitted_at` must never be
  client-writable.
- **Accepted Phase 1 residual.** The guardian address is self-declared.
  The self-check blocks only the same-address case (with Gmail dot and
  plus normalisation); a determined minor could use a second address they
  control. This is the specific reason real minors stay disabled until
  `<CONSENT-WORKFLOW-REVIEWER>` signs off — the gate raises the effort,
  it does not verify a parent.

## 8. Build pack section 6 sentence map

| Build pack sentence | Where it lands | Phase |
|---|---|---|
| Public tools need no consent (no personal data) | Guest journey collects nothing; quick-start answers are stateless query params | 1 (rule, built) |
| Under-18 accounts need verifiable parental consent via DigiLocker token or a school-mediated route | Interim: emailed guardian confirmation (`0004`–`0006`). DigiLocker / school route not built | Later |
| No identity documents, caste certificates or counselling histories collected | §5 "not stored, ever" | 1 (rule) |
| Separate revocable consents for marks, category/income, parent summary, contacting an institution | `consents`, append-only, one row per grant or withdrawal | CONSENT-4 / Phase 2 |
| Withdrawal freezes the account; deletion within 30 days | `frozen` → `deletion_due`, `withdraw_account()`, AUTH-10 | CONSENT-4 / Phase 2 |
| At 18, consent is re-obtained from the student | Not built. Needs a scheduled re-consent prompt keyed on `date_of_birth` | Later |
| Support-queue and distress content is visible only to staff | `is_safeguarding_staff()`, staff-only RLS, access matrix | CONSENT-4 / Phase 2 |
| Distress keyword rule as in section 3 | §6 "Distress" | Phase 2 |
| Parent summary: consent screen states the parent consents to the account and the student controls what the summary shows (§5) | A `consents` row plus a student-controlled visibility setting | Later |

## 9. Open, for the owner and the reviewer

1. CONSENT-2 must name `<SAFEGUARDING-CONTACT>`, `<SAFEGUARDING-BACKUP>`
   and `<CONSENT-WORKFLOW-REVIEWER>`, and confirm the trial cohort has no
   real minors.
2. CONSENT-4's card still describes creating `account_status`; it must be
   rewritten to extend the merged enum additively. Lead-owned.
3. Whether the advisory `invite_is_valid` check at sign-up is worth its
   small enumeration surface, or whether the code should only ever be
   asked for after first sign-in.
