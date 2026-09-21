"""Shared fixtures for RLS/policy tests (`make test-db`).

These tests run against a real Postgres with db/migrations/*.sql applied
— never against the owner/service role for the assertions themselves
(that would bypass RLS and hide a real bug; docs/SECURITY.md).

Since QA-2 that Postgres is a LOCAL, THROWAWAY `supabase start` stack
(supabase/config.toml, `make test-db-up`), never the owner's real
project. The target guard below makes that non-negotiable rather than
conventional: if `SUPABASE_URL` is anything but a loopback address, the
whole run aborts before a single row is written. Real student data is
never a test fixture (CLAUDE.md).

The whole directory still skips, with a clear reason, when no stack is
configured — never silently "passes" a check that didn't run. Set
`BCION_REQUIRE_LIVE=1` (CI, and before any merge) to turn each of those
skips into a hard failure instead, so "green" cannot mean "skipped".

The service-role key is used ONLY here, to create and tear down throwaway
test users for the guest / student A / student B / reviewer access
matrix. It is intentionally kept out of `app/core/config.py` — the
running application must never read it (docs/SECURITY.md).
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import Client, create_client

from app.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]

# Loaded in order, later file wins, and BOTH override whatever is already
# exported in the shell. That direction is deliberate and is a safety
# property, not a convenience: a live SUPABASE_URL left over in someone's
# terminal must not be able to out-rank the file whose entire purpose is
# to pin the suite to localhost.
#
# `.env.test` is what `make test-db-env` generates. `.env.test.local` is
# for a personal override and is already covered by .gitignore's
# `.env.*.local` pattern.
#
# The real `.env` (the owner's live project) is deliberately NOT in this
# list and must never be added to it.
_TEST_ENV_FILES = (".env.test", ".env.test.local")


def _load_test_env() -> list[str]:
    """Minimal dotenv reader, run at import time.

    Deliberately not python-dotenv: that is not a dependency of this
    repo, and the format in play here is a handful of `NAME=value` lines
    this can parse in twenty lines without adding one.

    Runs at import so it lands before any test module is imported —
    tests/db/test_api_auth.py builds a `TestClient(app)` at ITS import
    time, and `app.main` reads settings while doing so. `cache_clear()`
    afterwards covers the one ordering this cannot get ahead of: a
    combined `pytest tests/unit tests/db` run, where a unit test may
    already have populated the `get_settings` lru_cache from a bare
    environment before this directory was collected at all.
    """
    loaded: list[str] = []
    for name in _TEST_ENV_FILES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            line = line.removeprefix("export ").strip()
            key, separator, value = line.partition("=")
            if not separator:
                continue
            key = key.strip()
            value = value.lstrip()
            if value[:1] in {'"', "'"}:
                # Quoted: take exactly what is between the quotes, so a
                # '#' inside a value (a URL fragment, a password) is
                # kept. `supabase status -o env` always quotes.
                closing = value.find(value[0], 1)
                value = value[1:closing] if closing != -1 else value[1:]
            else:
                # Unquoted: drop a trailing inline comment, which
                # .env.test.example uses in the same style
                # .env.example does ("APP_ENV=development   # ..."), so
                # that copying that file by hand gives 'development'
                # and not the whole rest of the line. A '#' only starts
                # a comment at the value's start or after whitespace,
                # so FOO=a#b keeps 'a#b'; `NAME=   # only a comment`
                # correctly yields an empty value.
                value = re.split(r"(?:^|\s)#", value, maxsplit=1)[0].strip()
            os.environ[key] = value
        loaded.append(name)
    if loaded:
        get_settings.cache_clear()
    return loaded


LOADED_TEST_ENV_FILES = _load_test_env()


# --------------------------------------------------------------------
# RUN_ID and end-of-run cleanup (QA-3)
# --------------------------------------------------------------------
# Two things changed that made the previous "just use uuid4() per row"
# story incomplete: (1) genuinely CONCURRENT runs against the SAME local
# stack are now a real usage pattern (two `make test-db` invocations at
# once, or `pytest -n N`), not just sequential CI runs one after another,
# and (2) QA-2 confirmed the local stack has no GoTrue rate limit to work
# around, so every user-creating fixture is (and must stay) function-
# scoped rather than shared across a module to conserve sign-ups — see
# each fixture below. Neither of those changes anything about how a
# single test creates rows; what they DO require is a way to tell "my
# run's rows" apart from "some other, concurrently-running invocation's
# rows" well enough that a crash can be cleaned up after the fact without
# ever touching a still-running sibling's data.
#
# RUN_ID is that tag: a short id, embedded in every seeded name/email
# this suite creates (test_*.py files, tests/e2e/test_smoke.py), shared
# by every pytest-xdist WORKER of one `pytest -n N` invocation (they are
# separate OS processes, but all descend from the same controller
# process, so they inherit whatever is already in os.environ at the
# moment xdist spawns them) and DIFFERENT between two independent
# `pytest`/`make test-db` invocations (each starts from its own shell
# environment, so each generates its own).
def _compute_run_id() -> str:
    """The active run's tag. Reuses `BCION_RUN_ID` if already set in the
    environment — that is both how xdist workers pick up the SAME value
    the controller already generated (see module docstring above) and
    the documented way to point the standalone sweeper at a specific,
    already-finished run (`sweep_run_id` below; `make test-db-sweep
    RUN_ID=...`). Otherwise generates a fresh one and exports it, so any
    subprocess this process itself goes on to spawn — xdist workers,
    tests/e2e/conftest.py's own `live_server` uvicorn — inherits it too.
    """
    existing = os.environ.get("BCION_RUN_ID", "").strip()
    if existing:
        return existing
    generated = uuid.uuid4().hex[:12]
    os.environ["BCION_RUN_ID"] = generated
    return generated


RUN_ID: str = _compute_run_id()

# Appended, verbatim, to every seeded name/email below — distinctive
# enough that `_sweep_leftover_rows` below can never mistake ordinary
# app data (or another run's own tag) for this run's.
_RUN_TAG = f"[run:{RUN_ID}]"


def run_email(tag: str, domain: str = "example.invalid") -> str:
    """A run-tagged, per-call-unique email for a throwaway test user.
    Every email this suite creates is built through this (never a bare
    `uuid4()`), so `_sweep_leftover_rows` can find and delete every user
    this run created, and two concurrent runs' users can never collide
    even if they otherwise picked the same local-part."""
    return f"bcion-{tag}-{RUN_ID}-{uuid.uuid4().hex[:10]}@{domain}"


def run_name(label: str) -> str:
    """A run-tagged seeded row name/title (careers, pathways, sources,
    claims.verifier, ...) — same purpose as `run_email` above, for rows
    that aren't a Supabase Auth user."""
    return f"{label} {_RUN_TAG}"


def _build_admin_client() -> Client | None:
    """Service-role client, or None if the stack isn't configured. Split
    out of the `admin_client` fixture so `sweep_run_id`/`pytest_
    sessionfinish` below can build one too without depending on a
    fixture (they run outside, or after, normal fixture teardown)."""
    settings = get_settings()
    key = _TestOnlySettings().supabase_service_role_key
    if not settings.supabase_url or not key:
        return None
    return create_client(settings.supabase_url, key)


def _paginated_users(admin: Client) -> Iterator[Any]:
    """Every Supabase Auth user, not just GoTrue's default first page.
    `admin.auth.admin.list_users()` (no args) silently truncates past
    its default per_page — fine for the rest of this suite, which always
    filters by one already-known email, but a sweep genuinely needs
    every user that might carry this run's tag."""
    page = 1
    per_page = 200
    while True:
        batch = admin.auth.admin.list_users(page=page, per_page=per_page)
        if not batch:
            return
        yield from batch
        if len(batch) < per_page:
            return
        page += 1


def _sweep_leftover_rows(admin: Client, run_id: str) -> None:
    """Best-effort cleanup of every row/user tagged with `run_id` that
    ordinary fixture teardown did not reach — the safety net for an
    interrupted run (Ctrl-C, a crashed worker, a fixture that raised
    before its own `yield`). Every fixture in this suite already deletes
    its own rows in the success path (each `test_*.py`'s own try/finally
    or fixture teardown); this only mops up what that could not.

    Order matters: `claims.created_by`/`reviewed_by` reference
    `auth.users(id)` with no `on delete cascade` (db/migrations/
    0001_init.sql), so a tagged claim must go before the user that made
    it. `pathways.career_id` and every guardian-consent/student table DO
    cascade from their own parent (careers, auth.users respectively —
    db/migrations 0001/0002/0004), so deleting the tagged career/user is
    enough for those; no separate pathway/student_profiles/reviewers/
    saved_plans/guardian_consents/student_accounts pass is needed.

    Users are matched on the bare `run_id`, NOT the bracketed
    `[run:...]` tag `run_name` uses for everything else: an email
    address's local-part can't safely carry literal `[`/`]` (RFC 5322
    requires quoting), so `run_email` embeds `RUN_ID` plain — matching
    on the same bare value here is what actually finds those users
    (confirmed live, 2026-09-21: the bracketed-tag check here originally
    matched zero users, ever, regardless of whether cleanup ran, because
    no real email could ever contain it — every "0 leftover users"
    reading it produced was true only by accident, since ordinary
    fixture teardown deletes its own user directly in the non-interrupted
    case; the orphan-simulation check below is what exposed it).
    """
    tag = f"[run:{run_id}]"

    for row in admin.table("claims").select("id, verifier").execute().data:
        if tag in (row.get("verifier") or ""):
            admin.table("claims").delete().eq("id", row["id"]).execute()

    for row in admin.table("careers").select("id, name").execute().data:
        if tag in (row.get("name") or ""):
            admin.table("careers").delete().eq("id", row["id"]).execute()

    for row in admin.table("sources").select("id, authority_name").execute().data:
        if tag in (row.get("authority_name") or ""):
            admin.table("sources").delete().eq("id", row["id"]).execute()

    for user in _paginated_users(admin):
        if run_id in (user.email or ""):
            # Any claim this user made/reviewed that wasn't itself
            # tagged (so the pass above missed it) would otherwise fail
            # this delete outright via the FK noted above — defensive,
            # since every claims-seeding fixture in this suite already
            # tags `verifier` via `run_name`/its own literal.
            admin.table("claims").delete().eq("created_by", user.id).execute()
            admin.table("claims").delete().eq("reviewed_by", user.id).execute()
            admin.auth.admin.delete_user(user.id)


def sweep_run_id(run_id: str | None = None) -> None:
    """Standalone entry point: `python -c "from tests.db.conftest import
    sweep_run_id; sweep_run_id()"` (with `BCION_RUN_ID` set), or `make
    test-db-sweep RUN_ID=...` (mk/testdb.mk). For finishing the cleanup
    of a run that was interrupted before `pytest_sessionfinish` below
    ever got to run — that hook handles every normal (uninterrupted) run
    automatically.

    Re-applies the same local-only target guard `pytest_configure` below
    enforces for a normal test run: this deletes real rows by service-
    role, so it must refuse exactly like the suite itself would rather
    than trust that whoever invokes it by hand already checked
    SUPABASE_URL (CLAUDE.md: real student data is never a test fixture).
    """
    problem = _target_guard_problem()
    if problem is not None:
        raise SystemExit(problem)
    target = (run_id or RUN_ID).strip()
    if not target:
        raise SystemExit("sweep_run_id: no RUN_ID given and BCION_RUN_ID is unset.")
    admin = _build_admin_client()
    if admin is None:
        raise SystemExit(_SKIP_REASON)
    _sweep_leftover_rows(admin, target)
    print(f"[tests/db] swept every row/user tagged [run:{target}]")  # noqa: T201


def _run_end_sweep(session: pytest.Session) -> None:
    """Shared body of `pytest_sessionfinish`; also called from
    tests/e2e/conftest.py's own copy of that hook (same reasoning as
    `fail_if_unavailable` above: a hook function is only ever discovered
    in a conftest.py's OWN namespace, never via a plain import, so each
    directory needs its own thin wrapper calling this).

    Runs exactly once per whole `pytest` invocation — never inside an
    xdist worker. Every worker of one `pytest -n N` invocation shares
    this run's RUN_ID by construction (see `_compute_run_id`), so
    sweeping from a worker's own sessionfinish (which fires the moment
    THAT worker's slice of the work finishes, at a different wall-clock
    time than its siblings) would delete rows a still-running sibling
    worker is actively using. `session.config.workerinput` exists only
    on a worker (pytest-xdist's own documented distinction) — its
    absence is what "the controller, or a plain non-xdist run" means.
    """
    if hasattr(session.config, "workerinput"):
        return
    if _target_guard_problem() is not None:
        return  # never touched a live stack in the first place
    if not (get_settings().db_configured and _service_role_configured()):
        return
    admin = _build_admin_client()
    if admin is None:
        return
    try:
        _sweep_leftover_rows(admin, RUN_ID)
    except Exception as exc:  # noqa: BLE001 — never fail the run over cleanup
        print(f"[tests/db] end-of-run sweep for [run:{RUN_ID}] hit an error: {exc}")  # noqa: T201


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _run_end_sweep(session)


# --------------------------------------------------------------------
# Target guard (QA-2)
# --------------------------------------------------------------------
# Hostnames that mean "a stack running on this machine". Note the
# absence of 0.0.0.0: it is a bind-any address, not a destination, and
# accepting it would let a URL that actually resolves off-box through.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _target_host(url: str) -> str:
    return (urlsplit(url).hostname or "").strip().lower()


def _allowlisted_targets() -> set[str]:
    """`BCION_TEST_TARGET`: comma-separated exact origins.

    The single documented escape hatch, for a future disposable staging
    database the owner has explicitly approved. It is exact-origin
    matching, never a substring or suffix test — "endswith" style
    allowlists are how `evil-supabase.co` gets accepted as
    `supabase.co`.
    """
    raw = os.environ.get("BCION_TEST_TARGET", "")
    return {entry.strip().rstrip("/") for entry in raw.split(",") if entry.strip()}


def target_is_localhost() -> bool:
    """True when the configured target is a loopback stack.

    Used by tests that behave differently against a cloud project — see
    tests/db/test_api_auth.py, where a 429 from a shared cloud rate
    limiter is tolerable and a 429 from a local stack is a bug.
    """
    url = os.environ.get("SUPABASE_URL") or (get_settings().supabase_url or "")
    return _target_host(url) in _LOOPBACK_HOSTS


def _target_guard_problem() -> str | None:
    """The reason this run must not proceed, or None if it may."""
    url = (os.environ.get("SUPABASE_URL") or (get_settings().supabase_url or "")).strip()
    if not url:
        # Nothing configured at all. Not a guard violation — the
        # skip/require-live path below reports that far more usefully.
        return None
    if _target_host(url) in _LOOPBACK_HOSTS:
        return None
    if url.rstrip("/") in _allowlisted_targets():
        return None
    return (
        f"REFUSING TO RUN: SUPABASE_URL is {url!r}, which is not a local "
        "stack.\n"
        "These suites create, mutate and DELETE users and rows. They are "
        "only ever safe against the throwaway `supabase start` stack "
        "described in supabase/config.toml — never against the real "
        "project, which holds real student data (CLAUDE.md).\n"
        "Run `make test-db-up` and re-run, or unset SUPABASE_URL. If a "
        "non-loopback target really is disposable and the owner has "
        "approved it, add its exact origin to BCION_TEST_TARGET."
    )


def _require_live() -> bool:
    """`BCION_REQUIRE_LIVE=1` — skips become hard failures.

    For CI and for any pre-merge run, where "110 passed, 118 skipped" is
    indistinguishable from "nothing ran" unless something refuses to let
    it be green.
    """
    return os.environ.get("BCION_REQUIRE_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _register_bcion_markers(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "bcion_unavailable(reason): under BCION_REQUIRE_LIVE=1, a test that "
        "would otherwise have been skipped for a missing stack or migration. "
        "Fails in pytest_runtest_setup instead of skipping.",
    )


def _mark_unavailable(items: list[pytest.Item], reason: str) -> None:
    """Skip these items, or fail them when BCION_REQUIRE_LIVE=1.

    Failing per-item rather than aborting the session keeps this working
    under pytest-xdist (a hook that raises inside a worker is reported
    as a worker crash, which hides the actual reason) and names every
    test that did not really run.
    """
    marker = (
        pytest.mark.bcion_unavailable(reason)
        if _require_live()
        else pytest.mark.skip(reason=reason)
    )
    for item in items:
        item.add_marker(marker)


def fail_if_unavailable(item: pytest.Item) -> None:
    """Shared body of `pytest_runtest_setup`; also called from
    tests/e2e/conftest.py's own copy of that hook."""
    marker = item.get_closest_marker("bcion_unavailable")
    if marker is not None:
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {marker.args[0]}", pytrace=False)


def _items_under(items: list[pytest.Item], directory: Path) -> list[pytest.Item]:
    """Only this directory's items.

    `pytest_collection_modifyitems` is handed the WHOLE session's item
    list, not just the items under the conftest that defines it. Without
    this filter a combined `pytest tests/unit tests/db` run would skip
    the unit tests too, for a Supabase reason that has nothing to do
    with them.
    """
    return [item for item in items if directory in Path(str(item.fspath)).parents]


class _TestOnlySettings(BaseSettings):
    """Test-only: reads the service-role key that the app itself never
    touches. Kept separate from app.core.config.Settings on purpose.

    `env_file` is deliberately None, unlike app.core.config.Settings:
    this class must read nothing but the process environment, which
    `_load_test_env` above has already populated from `.env.test`. It
    must never be the thing that opens the owner's real `.env` looking
    for a service-role key.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    supabase_service_role_key: str | None = None


def _service_role_configured() -> bool:
    return bool(_TestOnlySettings().supabase_service_role_key)


_SKIP_REASON = (
    "SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY / SUPABASE_SERVICE_ROLE_KEY "
    "not fully set. RLS tests need a local Supabase stack with "
    "db/migrations/*.sql applied, plus a service-role key to create "
    "throwaway test users. Run `make test-db-up` (it starts the stack, "
    "applies the migrations and writes .env.test) — see "
    "supabase/config.toml, .env.test.example and db/migrations/README.md."
)


def _saved_plans_table_exists() -> bool:
    from app.db import get_anon_client

    try:
        get_anon_client().table("saved_plans").select("id").limit(1).execute()
        return True
    except Exception:  # noqa: BLE001 — any error here means "not ready yet"
        return False


_PLANS_SKIP_REASON = (
    "saved_plans table not found — db/migrations/0002_saved_plans.sql "
    "not yet applied to this stack. Run `make test-db-up` (or "
    "`make test-db-reset`); see db/migrations/README.md. If the file has "
    "been applied, PostgREST is probably still serving a stale schema "
    "cache — `make test-db-migrate` reloads it."
)


def _maker_checker_migration_applied() -> bool:
    """0003 adds no new table (only a trigger + a tightened policy on the
    existing `claims` table), so there's nothing to `select` the way
    `_saved_plans_table_exists` does. `maker_checker_schema_version()` is
    a tiny marker function the migration itself creates purely so this
    check has something to call."""
    from app.db import get_anon_client

    try:
        get_anon_client().rpc("maker_checker_schema_version", {}).execute()
        return True
    except Exception:  # noqa: BLE001 — any error here means "not ready yet"
        return False


_MAKER_CHECKER_SKIP_REASON = (
    "db/migrations/0003_maker_checker.sql not yet applied to this "
    "stack. Run `make test-db-up`; see db/migrations/README.md. A stale "
    "PostgREST schema cache looks identical — `make test-db-migrate` "
    "reloads it."
)


def _guardian_consent_migration_applied() -> bool:
    """Same marker-function pattern as `_maker_checker_migration_applied`
    — 0004 adds new tables too (`student_accounts`/`guardian_consents`),
    but also functions/triggers a bare table-existence check wouldn't
    cover, so it gets its own marker the same way 0003 does.

    Checks BOTH 0004's and 0005's markers (mirrors
    `app.api.guardian_consent.guardian_consent_schema_is_live`'s
    identical fix, same day, same reasoning): 0005 adds the RPC this
    test file's RPC-specific tests call directly, so if only 0004's
    marker were checked here, those tests would attempt to run (and
    fail noisily) rather than cleanly skip in the real, live window
    where 0004 is applied but 0005 isn't yet."""
    from app.db import get_anon_client

    try:
        client = get_anon_client()
        client.rpc("guardian_consent_schema_version", {}).execute()
        client.rpc("guardian_consent_request_rpc_schema_version", {}).execute()
        client.rpc("guardian_consent_token_fix_schema_version", {}).execute()
        return True
    except Exception:  # noqa: BLE001 — any error here means "not ready yet"
        return False


_GUARDIAN_CONSENT_SKIP_REASON = (
    "db/migrations/0004_guardian_consent.sql (or 0005/0006) not yet "
    "applied to this stack. Run `make test-db-up`; see "
    "db/migrations/README.md. A stale PostgREST schema cache looks "
    "identical — `make test-db-migrate` reloads it. Until it is applied, "
    "app.api.guardian_consent.guardian_consent_schema_is_live() is False "
    "and the sign-up/sign-in gate degrades to a no-op — see STATUS.md."
)


def _demo_mode_migration_applied() -> bool:
    """Same marker-function pattern as 0003/0004/0005/0006 — 0007 adds a
    new table (`app_settings`), but that table is deliberately
    unreadable through PostgREST by every role the tests can use
    (`revoke all ... from anon, authenticated`, plus RLS with no
    policies), so `_saved_plans_table_exists`'s "select from it" check
    could never work here and would report "not applied" forever."""
    from app.db import get_anon_client

    try:
        get_anon_client().rpc("demo_mode_schema_version", {}).execute()
        return True
    except Exception:  # noqa: BLE001 — any error here means "not ready yet"
        return False


_DEMO_MODE_SKIP_REASON = (
    "db/migrations/0007_demo_mode.sql not yet applied to this stack. Run "
    "`make test-db-up`; see db/migrations/README.md. A stale PostgREST "
    "schema cache looks identical — `make test-db-migrate` reloads it."
)


def _scope_migration_applied() -> bool:
    """Same marker-function pattern as 0003-0007, for
    0008_jurisdiction_currency.sql. That migration adds no new table —
    only columns, constraints, an index and a re-created trigger
    function — so there is nothing for `_saved_plans_table_exists`'s
    "select from it" shape to check."""
    from app.db import get_anon_client

    try:
        get_anon_client().rpc("scope_schema_version", {}).execute()
        return True
    except Exception:  # noqa: BLE001 — any error here means "not ready yet"
        return False


_SCOPE_SKIP_REASON = (
    "db/migrations/0008_jurisdiction_currency.sql not yet applied to this "
    "stack. Run `make test-db-up`; see db/migrations/README.md. A stale "
    "PostgREST schema cache looks identical — `make test-db-migrate` "
    "reloads it."
)


def pytest_configure(config: pytest.Config) -> None:
    """Enforce the target guard before anything is collected or run.

    This is the earliest hook available to a directory conftest: pytest
    calls it historically, the moment this module is registered as a
    plugin, which is before any test module in this directory is even
    imported. Nothing has opened a connection yet, so aborting here is
    genuinely "before the first write".
    """
    _register_bcion_markers(config)
    problem = _target_guard_problem()
    if problem is not None:
        raise pytest.UsageError(problem)
    _announce_run_id(config)


def _announce_run_id(config: pytest.Config) -> None:
    """Print this run's RUN_ID once, so an interrupted run can be swept
    later (`make test-db-sweep RUN_ID=...`, QA-3) without having to guess
    it. Controller/plain-run only — see `_run_end_sweep`'s docstring for
    why an xdist worker must never repeat what the controller already
    did; every worker shares the same RUN_ID anyway, so printing it
    again would be noise, not new information."""
    if hasattr(config, "workerinput"):
        return
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    message = (
        f"[tests/db] BCION_RUN_ID={RUN_ID} — if this run is interrupted, "
        f"finish cleanup with `make test-db-sweep RUN_ID={RUN_ID}`"
    )
    if reporter is not None:
        reporter.write_line(message)
    else:
        print(message)  # noqa: T201 — no terminalreporter (e.g. -p no:terminal)


def pytest_runtest_setup(item: pytest.Item) -> None:
    fail_if_unavailable(item)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip every test collected under tests/db/ when unconfigured —
    or, under BCION_REQUIRE_LIVE=1, fail it instead.

    A bare module-level `pytestmark` in a test file does NOT apply to
    sibling test modules, and a hook function defined INSIDE a test_*.py
    file is never picked up by pytest at all — hook implementations are
    only discovered in conftest.py files and registered plugins (caught
    for real: a first attempt defined this per-file in
    test_api_plans.py, and it silently did nothing; verified by running
    the suite before and after moving it here). So this conftest.py is
    the only place either skip can actually live.
    """
    own_items = _items_under(items, Path(__file__).resolve().parent)
    if not own_items:
        return

    if not (get_settings().db_configured and _service_role_configured()):
        _mark_unavailable(own_items, _SKIP_REASON)
        return

    def _in(names: tuple[str, ...]) -> list[pytest.Item]:
        return [item for item in own_items if any(n in str(item.fspath) for n in names)]

    # A narrower, additional skip: test_api_plans.py needs a second
    # migration (0002) beyond what the check above already confirms.
    if not _saved_plans_table_exists():
        _mark_unavailable(_in(("test_api_plans.py",)), _PLANS_SKIP_REASON)

    # Same pattern, for 0003_maker_checker.sql -- both the trigger-level
    # tests and the HTTP-layer tests over app/api/claims.py depend on it.
    if not _maker_checker_migration_applied():
        _mark_unavailable(
            _in(("test_maker_checker.py", "test_api_claims.py")), _MAKER_CHECKER_SKIP_REASON
        )

    # Same pattern, for 0004_guardian_consent.sql (and 0005/0006 -- see
    # `_guardian_consent_migration_applied`'s own docstring for why all
    # three markers are checked, not just 0004's).
    if not _guardian_consent_migration_applied():
        _mark_unavailable(_in(("test_guardian_consent.py",)), _GUARDIAN_CONSENT_SKIP_REASON)

    # Same pattern, for 0007_demo_mode.sql.
    if not _demo_mode_migration_applied():
        _mark_unavailable(_in(("test_demo_mode.py",)), _DEMO_MODE_SKIP_REASON)

    # Same pattern, for 0008_jurisdiction_currency.sql.
    if not _scope_migration_applied():
        _mark_unavailable(_in(("test_scope_columns.py",)), _SCOPE_SKIP_REASON)


@pytest.fixture(scope="module")
def admin_client() -> Client:
    """Service-role client. TEST SETUP/TEARDOWN ONLY — never used to make
    an assertion about what a real user can or can't do; that would defeat
    the point of testing RLS.

    Module-scoped for the CLIENT WRAPPER ONLY (a stateless REST/HTTP
    handle, cheap to share within one module's tests) — never mistake
    this for a shared/reused USER: every fixture below that actually
    creates a real Supabase Auth user (`student_a`, `student_b`,
    `reviewer`, `second_reviewer`, `synthetic_source`'s row) stays
    function-scoped, on purpose (QA-3). `student_profiles.id` and
    `reviewers.user_id` are the user's own id AS their primary key, so
    two tests sharing one real user (module/session-scoped) would
    collide on that PK the moment both tried to create their own
    profile/reviewer row — a real risk now that QA-2 confirmed the local
    stack has no sign-up rate limit to justify sharing one for
    efficiency, unlike the old cloud target.
    """
    admin = _build_admin_client()
    assert admin is not None
    return admin


def _create_test_user(admin: Client) -> tuple[str, Client]:
    """Creates a throwaway confirmed user, returns (user_id, a client
    authenticated as that user via a fresh password sign-in)."""
    settings = get_settings()
    email = run_email("test")
    password = uuid.uuid4().hex
    created = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id

    assert settings.supabase_url is not None
    assert settings.supabase_publishable_key is not None
    user_client = create_client(settings.supabase_url, settings.supabase_publishable_key)
    session = user_client.auth.sign_in_with_password({"email": email, "password": password})
    user_client.postgrest.auth(session.session.access_token)
    return user_id, user_client


@pytest.fixture
def guest_client() -> Client:
    """Anon-key client, no user session — the 'guest' row of the access
    matrix (docs/SECURITY.md)."""
    from app.db import get_anon_client

    return get_anon_client()


@pytest.fixture
def student_a(admin_client: Client) -> Iterator[tuple[str, Client]]:
    user_id, client = _create_test_user(admin_client)
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def student_b(admin_client: Client) -> Iterator[tuple[str, Client]]:
    user_id, client = _create_test_user(admin_client)
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def reviewer(admin_client: Client) -> Iterator[tuple[str, Client]]:
    user_id, client = _create_test_user(admin_client)
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)  # cascades to reviewers row


@pytest.fixture
def second_reviewer(admin_client: Client) -> Iterator[tuple[str, Client]]:
    """A distinct reviewer from the `reviewer` fixture -- pytest fixtures
    are function-scoped by default, so requesting `reviewer` twice under
    different names would give the SAME instance, which is useless for
    testing "a DIFFERENT person reviews" (docs/DATA.md). Moved here from
    tests/db/test_maker_checker.py (2026-09-20): a fixture defined inside
    one test file is invisible to every other file, which
    tests/db/test_api_claims.py's own use of this fixture surfaced as a
    real `fixture 'second_reviewer' not found` error the moment
    db/migrations/0003_maker_checker.sql was applied and those tests
    stopped being skipped -- invisible while skipped, same shape as the
    per-file-hook bug this conftest.py's own docstring already warns
    about above."""
    user_id, client = _create_test_user(admin_client)
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def synthetic_source(admin_client: Client) -> Iterator[str]:
    """A source row tagged synthetic, for tests that must never risk
    touching anything that looks like a real, verified fact."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("TEST FIXTURE — not a real authority"),
                "official_url": "https://example.invalid/not-a-real-source",
                "source_type": "synthetic",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()
