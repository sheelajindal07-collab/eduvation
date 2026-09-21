"""Shared fixtures for real-browser smoke tests (`make test-e2e`).

Unlike `tests/db/` (FastAPI's `TestClient` — no real HTTP server, no real
browser) this directory runs Playwright against a REAL running instance
of the app (`uvicorn`, a genuine subprocess listening on a local port),
navigated by a real browser. Its whole job is proving the pages actually
render and the zero-JS flows actually work outside a test client's
simulation -- `tests/db/test_web_pages.py` and
`tests/db/test_reviewer_console.py` already prove the same journeys are
*correct* at the HTTP-request level; nothing before this directory ever
launched a real browser at all.

Same as `tests/db/conftest.py`, this needs a real, configured Supabase
project (careers/pathways/claims to seed, a real reviewer to sign in as)
to be genuinely useful, so this whole directory skips cleanly, with a
clear reason, when that project isn't configured -- never silently
"passes" a check that didn't run. Mirrors that file's skip-reason style
rather than reusing its `pytest_collection_modifyitems` hook directly:
this hook's own skip reason is e2e-specific (a real running app + a real
browser, not just RLS-scoped queries), and none of `tests/db/conftest
.py`'s narrower per-migration skips (saved_plans, maker_checker) are
relevant here -- every fixture this directory seeds with was already
proven to exist by the time `tests/db/` itself stopped skipping.

Data fixtures (`admin_client`, `reviewer`, `synthetic_source`, ...) are
imported from `tests/db/conftest.py` and re-exported here, not
reimplemented -- same seeding mechanism, one place it's defined, per
this task's own instruction not to invent a parallel one. A hook
function's or fixture's presence in THIS module's namespace is what
pytest actually scans for (conftest.py files, not test_*.py files) --
see `tests/db/conftest.py`'s own docstring for the same point about
per-file hooks being invisible to pytest.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings

# Re-exported for tests/e2e/test_smoke.py -- same fixtures tests/db/ uses
# to seed/tear down throwaway users and rows against the local stack,
# not a second, parallel seeding mechanism.
#
# Importing this module is also what loads `.env.test` into the process
# environment (tests/db/conftest.py does it at import time), which is
# what makes `pytest tests/e2e` on its own target the local stack -- and
# what the `live_server` fixture below silently depends on, since it
# hands its own os.environ straight to the uvicorn subprocess.
from tests.db.conftest import (  # noqa: F401
    _mark_unavailable,
    _register_bcion_markers,
    _service_role_configured,
    _target_guard_problem,
    admin_client,
    fail_if_unavailable,
    guest_client,
    reviewer,
    second_reviewer,
    student_a,
    student_b,
    synthetic_source,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

_SKIP_REASON = (
    "SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY / SUPABASE_SERVICE_ROLE_KEY "
    "not fully set. e2e smoke tests need a real running app talking to a "
    "real database (same requirement as tests/db/, plus a real browser "
    "to drive) so Playwright has real pages and real seeded rows to "
    "navigate. Run `make test-db-up` to bring up the local stack -- see "
    "supabase/config.toml, .env.test.example and db/migrations/README.md."
)


def pytest_configure(config: pytest.Config) -> None:
    """Same target guard as tests/db/conftest.py, applied independently.

    Deliberately a second definition rather than an import of that
    module's hook: pytest discovers hooks by NAME in a conftest's own
    namespace, so importing it would register the identical function
    twice under two plugins. The shared body lives in tests/db/conftest
    .py; only this thin wrapper is duplicated. (Same reason the module
    docstring gives for this file having its own
    `pytest_collection_modifyitems`.)
    """
    _register_bcion_markers(config)
    problem = _target_guard_problem()
    if problem is not None:
        raise pytest.UsageError(problem)


def pytest_runtest_setup(item: pytest.Item) -> None:
    fail_if_unavailable(item)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip every test collected under tests/e2e/ when no local Supabase
    stack is configured -- or fail them, under BCION_REQUIRE_LIVE=1.
    See module docstring for why this is its own hook rather than a
    reuse of tests/db/conftest.py's."""
    own_directory = Path(__file__).resolve().parent
    own_items = [item for item in items if own_directory in Path(str(item.fspath)).parents]
    if not own_items:
        return
    if not (get_settings().db_configured and _service_role_configured()):
        _mark_unavailable(own_items, _SKIP_REASON)


def _free_port() -> int:
    """Ephemeral-port trick: bind to port 0, read back what the OS
    assigned, then release it. A small, accepted race (another process
    could grab it before uvicorn binds) -- the standard approach for
    this (e.g. Django's `live_server` fixture does the same)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    """Starts the real app (`uvicorn`, a genuine OS subprocess -- not
    FastAPI's `TestClient`, which never opens a real socket a browser
    could connect to) on a local ephemeral port, for the whole e2e
    session. Session-scoped: one real server for every test in this
    directory, not one per test -- starting uvicorn is not free, and
    nothing about this fixture's state is test-specific (each test seeds
    and tears down its OWN rows via the imported admin_client-based
    fixtures instead).

    Runs with `cwd=REPO_ROOT` because the app resolves paths relative to
    the process's working directory, not to this file's location —
    `app.main` mounts `app/static` that way, and
    `app.core.config.Settings` resolves its `env_file` that way.

    The child inherits this process's os.environ, which
    tests/db/conftest.py has already loaded `.env.test` into at import
    time. That inheritance is the ONLY thing pointing the server at the
    local stack: the repo no longer carries a `.env` for it to fall back
    on, and it must never grow one. So the server under test and the
    test process always agree on the target, and the target has already
    been proven to be loopback by `pytest_configure`'s guard above.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.setdefault("APP_ENV", "development")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        became_healthy = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(
                    f"uvicorn exited early (code {process.returncode}) while starting "
                    f"the e2e live_server fixture:\n{output}"
                )
            try:
                response = httpx.get(f"{base_url}/healthz", timeout=1)
                if response.status_code == 200:
                    became_healthy = True
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(0.25)
        if not became_healthy:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=5)
            raise RuntimeError(
                "uvicorn never answered GET /healthz within 20s while starting the "
                f"e2e live_server fixture (last connection error: {last_error}):\n{output}"
            )
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
