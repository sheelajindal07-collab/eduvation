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


@pytest.fixture(scope="module")
def admin_client() -> Client:
    """Service-role client. TEST SETUP/TEARDOWN ONLY — never used to make
    an assertion about what a real user can or can't do; that would defeat
    the point of testing RLS."""
    settings = get_settings()
    key = _TestOnlySettings().supabase_service_role_key
    assert settings.supabase_url is not None
    assert key is not None
    return create_client(settings.supabase_url, key)


def _create_test_user(admin: Client) -> tuple[str, Client]:
    """Creates a throwaway confirmed user, returns (user_id, a client
    authenticated as that user via a fresh password sign-in)."""
    settings = get_settings()
    email = f"bcion-test-{uuid.uuid4().hex[:12]}@example.invalid"
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
                "authority_name": "TEST FIXTURE — not a real authority",
                "official_url": "https://example.invalid/not-a-real-source",
                "source_type": "synthetic",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()
