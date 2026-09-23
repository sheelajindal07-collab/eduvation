# Security & privacy — BCION Lite

Source: `docs/BCION-Lite-Build-Pack.md` §3 (Decisions — Residency), §4
(Stack), §8 (Data-flow map).

## Access model
- Application connects to Postgres as a **restricted role**, never the
  Supabase owner/service role, for any user-facing request.
- Row-level security (RLS) is enforced by passing the **signed-in user's
  access token** to Postgres on every request (`supabase-py` with the
  user's token, or per-request role/claims on a direct connection) — not by
  relying on a JS client's defaults. This is a Step-4/M1 contract, and it
  is tested (`make test-db`) on every table, view and storage bucket that
  is exposed.
- Access matrix tested on every auth/RLS/publication change: **guest,
  student A, student B, reviewer** × read/write/delete/export/storage.
  Cross-user reads/writes must fail; tests must NOT run as the database
  owner (owner bypasses RLS and would hide a real bug).

### Grants and exposure hardening (SEC-6, `db/migrations/0016_grants_hardening.sql`)
RLS is enforced at the POLICY layer; the GRANT layer underneath it is a
second, independent line of defence, and this Supabase stack's own
defaults leave it wide open unless a migration explicitly narrows it —
confirmed live before writing 0016, not assumed:
- **Every table** gets ALL SEVEN privileges (SELECT/INSERT/UPDATE/
  DELETE/TRUNCATE/REFERENCES/TRIGGER) granted to `anon` AND
  `authenticated` by default. 0016 revokes every non-SELECT privilege
  from `anon` on the public-knowledge tables (`sources`, `careers`,
  `pathways`, `claims` — a guest may only ever read these) and ALL
  privileges from `anon` on `student_profiles`, `saved_plans` and
  `reviewers` (a guest has no legitimate reason to touch the student
  vault or the reviewer-identity table at all). `authenticated` is
  untouched — RLS, not the grant layer, is what scopes a signed-in
  student to their own row.
- **Every `SECURITY DEFINER` function** gets EXECUTE via TWO
  independent defaults on this stack (the SQL-standard PUBLIC grant, and
  this stack's own `alter default privileges` direct grant to
  `anon`/`authenticated`) — see `db/migrations/README.md`'s "two
  gotchas" entry. A bare `grant execute ... to authenticated` in an
  older migration does NOT by itself stop `anon` from calling the same
  function; 0016 revokes PUBLIC everywhere except `is_reviewer()`
  (needed by every anon-readable RLS policy) and, function by function,
  either confirms the existing `anon` grant is deliberate (guest
  sessions, guardian-consent confirmation, invite validation, AI usage —
  all restated explicitly rather than left default-shaped) or closes it
  where it was never meant to exist. **Two functions were found
  genuinely anon-callable despite never being meant to be**:
  `my_guardian_consent_status()` and `create_guardian_consent_request()`
  (both 0004/0005) — neither had ever revoked PUBLIC or `anon`, the
  exact class of gap `is_admitted()`/`is_safeguarding_staff()`/
  `redeem_invite()`/`withdraw_account()`/`account_active()` had each
  already had fixed on their own turn. Both are `authenticated`-only now.
- `search_path` is pinned explicitly on every function in this schema —
  0016 closes the last two, `forbid_publishing_synthetic_claims()` and
  `touch_updated_at()` (both ordinary trigger functions, not `SECURITY
  DEFINER` — this app's only write path is PostgREST/RPC, which cannot
  inject a raw `SET search_path`, so this is deliberate, cheap insurance
  against a future direct-SQL access path rather than a closure of a
  currently exploitable one).
- `tests/db/test_exposure_catalogue.py` is a standing catalogue guard,
  independent of the access matrix (`tests/db/test_access_matrix.py`,
  which already separately guards "every table has RLS enabled" as part
  of its own declarative coverage check): it additionally fails if ANY
  view is not `security_invoker` — with one named, reviewed exception,
  `ai_usage_daily_totals` (0011: a deliberate RLS bypass for a
  reviewer-only aggregate, gated by its own internal `where
  is_reviewer()` clause, the same design family as a SECURITY DEFINER
  function) — or if ANY storage bucket lacks an RLS policy on
  `storage.objects` naming it. Zero storage buckets exist in this pilot
  today (`supabase/config.toml` leaves the Storage service off
  entirely) — confirmed live by the test itself, not assumed.

## Web sessions & CSRF (SEC-2)

The JSON API is Bearer-only and has no session cookie, so it has no CSRF
exposure and nothing below applies to it (`docs/CONTRACTS.md`: "cookies
belong to the web layer alone"). The cookie-authenticated **web** layer —
today `bcion_reviewer_session` on `/reviewer`, tomorrow the planned
`bcion_student_session` — is protected by two independent layers:

1. **`SameSite=Lax` on the cookie itself**, alongside `HttpOnly` and
   `Secure` in production only (plain http still works for local dev).
   A genuinely cross-*site* POST does not carry the cookie at all in any
   browser that honours the attribute.
2. **A server-side origin check on every state-changing request that
   carries one of those cookies** (`app/core/csrf.py`, applied as a
   FastAPI dependency; `app/main.py`'s `OriginCheckMiddleware` is the
   same rule as middleware for the student cookie). There is no CSRF
   *token*: the console's forms are deliberately zero-JS, so there is no
   client-side script to carry one, and inventing one would mean giving
   up the zero-JS requirement.

**The rule.** A `POST`/`PUT`/`PATCH`/`DELETE` carrying a session cookie
is rejected with **403** unless every origin-declaring header it sends
names a host in `ALLOWED_HOSTS` (`Settings.allowed_hosts_list`, the same
list `TrustedHostMiddleware` uses), and it sends at least one:

- `Origin` present → its host must be allowed.
- `Referer` present → its host must be allowed too. It is the fallback
  for browsers that omit `Origin` on a same-site navigation; when both
  are present **both** are checked, because two disagreeing values are
  not something an honest same-origin form post produces.
- **Neither present → rejected.** Fail closed, never open: "declares no
  origin" is exactly the shape this check exists to refuse.
- `Origin: null` has no host and is rejected by the same rule.

**Configuration requirement.** `ALLOWED_HOSTS` must list **exact**
hostnames. `TrustedHostMiddleware` additionally understands a
`*.example.com` prefix pattern and this check deliberately does not, so a
wildcard entry passes the Host check and fails the origin check — a
closed failure, but one that will look like "the console stopped
accepting form posts" if nobody reads this paragraph. An unset
`ALLOWED_HOSTS` outside development is already the fail-closed empty list
(DEPLOY-18/SEC-1), which here means every guarded POST is refused, never
that every one is accepted.

**Interaction with `Referrer-Policy: no-referrer`** (set on every
response by SEC-1): real browsers therefore send no `Referer` to this
app at all, so `Origin` is the header actually doing the work. The
`Referer` fallback stays for clients and intermediaries that behave
differently; it is not what a browser relies on here.

**Accepted residual risk — login CSRF.** The sign-in POST does not yet
carry the cookie (it is the request that creates it), so it is not
guarded, and an attacker can in principle cause a victim's browser to
sign in as the attacker. Gating it would lock a reviewer out of signing
in, which is the worse failure. The route still carries the dependency,
so an *already signed-in* session re-posting the form is checked like any
other state change; if that ever strands somebody, `POST
/reviewer/sign-out` is deliberately unguarded and every expired-session
bounce clears the cookie, so the unguarded, cookie-free state is always
reachable.

**Error surfaces carry codes, not prose.** `/reviewer/queue?error=` takes
a short code looked up in a fixed dict (`QUEUE_ERROR_MESSAGES`); an
unrecognised code renders a generic message. Nothing a stranger puts in
that URL is rendered, escaped or otherwise — the query parameter is used
as a dict key and never as content.

## Rate limiting (SEC-3)

Two independent layers, neither a substitute for the other. No Redis, no
in-app/Python-level limiter anywhere in either layer — consistent with the
stack decision (no Redis/broker).

### Layer 1 — nginx, per-IP, in front of the app

`deploy/nginx/ratelimit.conf` is a config **snippet**, not a running
deployment: there is no nginx in front of this app yet in dev (the app
runs directly). It is meant to be `include`d into a future site's `http {}`
block by whoever stands up nginx (DEPLOY-4/DEPLOY-7); its own header
comment has the exact wiring instructions. It protects, per client IP:
`/auth/*` (`POST /auth/sign-up`, `POST /auth/sign-in`) and
`/reviewer/sign-in` together, `/plans` write methods, and `GET /ask` (the
current, confirmed route for the "Ask BCION" canned-prompt answer — read
`app/api/ask.py` if this ever changes; it is deterministic-only today, no
model call, but is the route the DPR's Tier-0/Tier-1 AI spend-control
language is aimed at).

**Thresholds chosen** (a judgement call for the owner to review, not a
measured fact — reasoning in full in `deploy/nginx/ratelimit.conf`'s own
header, since that is where anyone actually deploying this will look):

| Zone | Protects | Sustained rate | Burst | Why |
| --- | --- | --- | --- | --- |
| `bcion_auth` | `/auth/*`, `/reviewer/sign-in` | 30 requests/minute per IP | 20, nodelay | Highest-value target for credential stuffing/enumeration. 30/min is far below any real human's retry pace; the 20-request burst absorbs a school/carrier NAT sending many independent students' sign-ins within the same couple of seconds without a false 429. |
| `bcion_plans_write` | `/plans` writes (POST/PATCH/DELETE, and PUT on the actions sub-route — see the scope note in the config file) | 60 requests/minute per IP | 30, nodelay | Authenticated, everyday traffic — looser than auth. A lab of students saving plans concurrently needs a bigger burst; 60/min sustained is still well above normal per-user pace. |
| `bcion_ask` | `GET /ask` | 30 requests/minute per IP | 15, nodelay | Canned templates only today, but the route future AI work deepens. 15-request burst covers several students' pages each firing 2-3 canned prompts on one shared IP. |
| `bcion_perip_conn` | all three groups above | n/a (concurrent connections, not a rate) | 20 simultaneous connections per IP per protected location | Bounds connection-exhaustion abuse without touching normal multi-tab, multi-student-per-IP browsing. |

The core tension driving every one of these numbers: a school or carrier
NAT can put many real students behind one public IP, and that is exactly
who this pilot is for — thresholds have to tolerate a burst of genuinely
simultaneous, independent humans on one IP without meaningfully slowing a
real automated attack down. Rejections return **429** (nginx's own default
for both `limit_req`/`limit_conn` is 503, explicitly overridden here — a
misconfigured server error is the wrong signal for "you're being
throttled"), served with the friendly static page `app/static/429.html`
(no template engine — nginx serves it directly off disk, not proxied, so
it still works even when the app or DB is what is under load).

**Verification of this config in this session:** `nginx -t` is not
runnable directly in this dev environment (no nginx binary installed), so
the config was checked in a local `nginx:stable` Docker container instead
— both `nginx -t` syntax validation and a full live functional test (real
concurrent request bursts against every protected location, confirming
the exact pass/reject counts the burst values above predict, and the 429
page's body actually being returned on rejection). Live `nginx -t` against
whatever real site file eventually `include`s this snippet is still
DEPLOY-4/DEPLOY-7's job at actual deploy time — this only proves the
snippet itself is syntactically and functionally correct in isolation.

### Layer 2 — Supabase Auth's own rate limiting (independent, not this app's to configure)

Supabase Auth enforces its own server-side rate limits on the auth
endpoints this app calls (sign-up, sign-in, and related), entirely
independent of anything in this repository or Layer 1 above — nginx
throttling a request before it reaches this app does not know or care
about these, and these do not know or care about nginx. **Confirmed live
in this codebase, 2026-09-19** (`app/api/auth.py`): Supabase returns a
structured `429` with `AuthApiError.code` set to `over_email_send_rate_limit`
(email-sending limits, e.g. confirmation emails on sign-up) or
`over_request_rate_limit` (general request-rate limits), and this app
propagates the provider's real HTTP status and message for both rather
than flattening them to a generic 400 (`sign_up`) or the generic
anti-enumeration 401 (`authenticate`, shared by `POST /auth/sign-in` and
the reviewer console) — see `_RATE_LIMIT_ERROR_CODES` in that module for
the exact, deliberately narrow allow-list, and its surrounding comment for
why only these two codes are ever allowed to escape the generic 401.

The exact current numeric thresholds behind those two error codes are
**configurable per Supabase project** (Authentication → Rate Limits in the
dashboard) and change over time on Supabase's side — this file does not
assert a specific requests-per-hour figure as fact, because nobody
re-verified one against Supabase's current documentation or this
project's actual dashboard settings in this session, and this project's
own non-negotiable is that an unverified number is not a fact. What is
verified is the *behaviour*: these limits exist, they bite in practice,
and this app already surfaces them correctly rather than masking them.
**Action for the owner:** confirm the current thresholds for this
project's Supabase instance in its dashboard, and keep Layer 1's `nginx`
numbers above generous enough that a legitimate shared-IP burst hits
nginx's own, more forgiving limits first rather than needlessly forcing
real users into Supabase's stricter, provider-side wall.

## Consent & safeguarding (a launch gate, not a checkbox)
Real accounts for minors stay **disabled** until this workflow is built and
reviewed by a person (not model review alone):
- Guardian identity via a verifiable route (school-mediated consent using
  the school's own records, or another route confirmed in Phase 0/−1 of
  the national DPR) — no identity documents collected by Lite itself.
- Consent is separate and revocable per purpose (saving marks/category/
  income, sharing a parent view, contacting an institution).
- A named staff member reviews the consent design before any real minor
  account is enabled.
- **Distress rule**: a keyword rule (Hindi + Hinglish + English) returns
  the national tele-mental-health helpline info and flags a named staff
  member within 24 hours. No counselling is promised by the software.

### Interim mechanism built for Lite's sign-up
(this session — additive, not a substitute for the paragraph above; see
STATUS.md for status)

`POST /auth/sign-up` now requires `date_of_birth`. **Named assumption**
(no threshold was stated anywhere in this file, the build pack or the
DPR): 18, India's legal majority age (Indian Majority Act, 1875) — see
`app/api/guardian_consent.py`'s `MINOR_AGE_THRESHOLD_YEARS`, the one
place to change it if the owner names a different figure. Under 18
additionally requires `guardian_email` (self-declared — consistent with
"no identity documents collected by Lite itself" above, not a new kind
of collection) and creates the account as `account_status =
'pending_guardian_consent'`, never immediately usable. A single-use,
72-hour, server-generated token is emailed to the guardian; confirming it
(`GET /consent/confirm?token=...`) is the only way the account becomes
`active`. Enforced at sign-in (`app.api.auth.authenticate`, the one
function both `POST /auth/sign-in` and the reviewer console's sign-in
share) and, defense-in-depth, at the database: an under-18
`student_accounts` row can never be inserted as `active` even via a
direct, otherwise-legitimate authenticated request (a trigger — see
`db/migrations/0004_guardian_consent.sql`), and the row's own RLS grants
no UPDATE to its owner at all, so a signed-in student cannot self-
activate their own pending account by any client-side call. The
confirmation token itself is never readable through the normal API by
anyone, including the owning student (own-row RLS on `guardian_consents`
grants INSERT only, never SELECT) — a student's consent *status* is
exposed instead through a security-definer function
(`my_guardian_consent_status()`) that never selects the token column.

**Real email delivery is NOT wired to a real provider.** `app/notifications/`
is a pluggable adapter (mirrors `app/ai/`'s provider split); the only
implementation actually running anywhere today is `LoggingEmailSender`,
which logs what would be sent and reaches no real inbox — see that
module's docstring. This means the database bookkeeping above is real
and correctly enforced, but **no guardian will actually receive a
confirmation link until the owner provisions a real SMTP/transactional
provider and sets the matching `.env` values** (`app/notifications/
smtp_sender.py`, gated exactly like `app/ai/gemini_provider.py`). Treat
this mechanism as "the database half of the launch gate is built and
tested"; the paragraphs above it (verifiable guardian identity,
per-purpose revocable consent, staff review, distress rule) remain the
fuller workflow this interim mechanism does not replace.

**Before any real log aggregation/shipping exists** (adversarial review,
2026-09-21, documentation-only — no code change): `app/notifications/
logging_sender.py`'s `LoggingEmailSender.send()` logs the full email body
— including the raw, unexpired guardian-consent confirmation token — at
`INFO` level. This is deliberate for now (the token has nowhere else to
go while no real provider is configured, and process logs are the only
place a developer running this locally can see the link to click it) but
it is a live secret in a log line. **Before this app's logs are shipped
to any aggregator, dashboard or third party, that line must be dropped to
`DEBUG` or the token redacted** — do not carry it forward unexamined.

## Publishing security
- Author ≠ approver, enforced server-side (DB constraint / RLS policy),
  never just a disabled UI button.
- Approval binds to the exact draft content (hash/version); any edit after
  approval invalidates it.
- AI may extract a candidate claim; it can never set `status = published`.

## AI / LLM controls
- No write access to the database from the AI/guidance layer.
- No access to the student vault from the AI/guidance layer.
- PII redaction before any external model call — no names, phone numbers,
  identifiers; only retrieved records + stated interests/constraints go out.
- 15-second timeout; atomic per-request spend reservation; global + per-
  account spend caps; graceful fallback to deterministic tools at the cap.
- Retrieved external text (sources, imported catalogues) is treated as
  **data, never as instructions** — prompt-injection and data-poisoning
  resistance for the extraction pipeline.
- SSRF controls on the source fetcher (allow-listed domains only).

## Quality gates (must pass before any release)
- **Calculators:** zero values, boundaries, missing inputs, overlapping
  durations, rounding.
- **Eligibility:** cycle/jurisdiction, unknowns, cut-off dates, rule
  version.
- **Access:** guest/student A/student B/reviewer × read/write/delete/
  export/storage.
- **CSRF (SEC-2):** for every cookie-authenticated state-changing route —
  cross-origin rejected **and the record unchanged afterwards** (read it
  back; a status code alone proves nothing), same-origin accepted, the
  `Referer` fallback accepted, neither header rejected, and sign-in still
  reachable with no cookie from any origin.
- **Publication:** separate maker/checker, exact draft approval,
  invalidation on edit.
- **AI:** wrong source IDs, unsupported claims, stale evidence, prompt
  injection, timeout, overspend.
- **Privacy:** PII-free logs, logout/cache behaviour, authorised
  export/deletion.
- **UI:** mobile + desktop, keyboard, screen-reader spot checks, Hindi text
  expansion, every error state.
- **Operations:** fresh migration, staging deploy, monitoring alert,
  backup restore.

No known critical/high security issue ships. A lower-severity exception
needs a named owner, a rationale and an expiry. **Model review alone never
signs off child data or production security** — a person does.

## Data-flow map (residency — replaces any blanket "India-only" claim)
| Flow | Where | Personal data? | Control |
| --- | --- | --- | --- |
| Database, auth, file storage | Supabase, South Asia (Mumbai, `ap-south-1`) — confirmed 2026-09-19, see `docs/DECISIONS.md` | Yes | RLS, restricted role, field-level encryption for optional sensitive fields |
| Application + worker | VPS, Mumbai (once provisioned) | Yes, in transit/memory | No personal data in logs; isolated containers; staging separate |
| Database backups | Supabase-managed; region to confirm at provisioning | Yes | Daily backups; point-in-time recovery only if a day's loss is unacceptable |
| Runtime AI requests | Hosted model provider; region may be outside India | No — PII redacted; retrieved records + stated interests/constraints only | Provider terms reviewed for retention/training; restricted key; spend cap |
| Error tracking / uptime | Monitoring vendor; region recorded at sign-up | No — payloads scrubbed, no session replay | Vendor region + retention noted here once chosen |
| WhatsApp reminders | Meta Cloud API | Phone number + deadline template | Opt-in only; template carries no personal field beyond first name |
| Transactional email (if used) | Provider; region recorded | Email address | Domain verified, delivery tested |
| Development agents (Claude Code) | Owner's machine | **Never** | Synthetic fixtures only; staging keys only |

**Rule:** a real minor's personal data does not enter the system until every
row above has a confirmed region and the owner has accepted this map in
writing. "India-only" is a statement about this table, not about the
database region alone.

## Standards (aspirational for Lite scale, tracked for the national plan)
CERT-In incident-reporting awareness; no production credential in the
everyday Claude Code development environment; secrets via provider
dashboards only, never committed or written to memory files.
