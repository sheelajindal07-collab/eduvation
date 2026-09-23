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

Same as `tests/db/conftest.py`, this needs a real, configured database
(careers/pathways/claims to seed, a real reviewer to sign in as) to be
genuinely useful -- since QA-2 that means the local, throwaway
`supabase start` stack, and the target guard below refuses to let this
directory run against anything that isn't loopback. It skips cleanly,
with a clear reason, when no stack is configured -- never silently
"passes" a check that didn't run -- or fails outright under
BCION_REQUIRE_LIVE=1. Mirrors that file's skip-reason style
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
import threading
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page

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
    RUN_ID,
    _announce_run_id,
    _mark_unavailable,
    _register_bcion_markers,
    _run_end_sweep,
    _service_role_configured,
    _target_guard_problem,
    admin_client,
    fail_if_unavailable,
    guest_client,
    reviewer,
    run_email,
    run_name,
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
    _announce_run_id(config)


def pytest_runtest_setup(item: pytest.Item) -> None:
    fail_if_unavailable(item)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Same QA-3 end-of-run sweep as tests/db/conftest.py, over the SAME
    RUN_ID (this module's `from tests.db.conftest import RUN_ID` above
    already forces that module to be imported, and with it its own
    `RUN_ID = _compute_run_id()` -- Python caches the module, so this is
    the identical value, not a second independently-generated one, even
    when tests/db and tests/e2e run in the same `pytest` invocation).
    Duplicated as a thin wrapper rather than imported as a hook for the
    same reason `pytest_configure` above already is -- see this module's
    docstring."""
    _run_end_sweep(session)


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

    QA-7 root-cause fix, found by bisecting a from-scratch equivalent of
    this exact fixture against this one (a real hang, not the
    click-triggered-navigation one this task was warned about -- that one
    is still open, tracked separately; this is a different bug this
    session actually diagnosed and fixed): `stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT` below was never paired with anything that
    reads that pipe during normal operation -- both call sites that
    touched `process.stdout` only ever ran on a startup failure. Uvicorn's
    own access log, this app's structured JSON access log
    (`app.core.logging`'s `bcion.access` logger) and supabase-py's own
    INFO-level `httpx` logging together write far more than a pipe's OS
    buffer (~64KB on Windows) over one session-scoped server's whole
    lifetime handling a real multi-page journey -- once that buffer
    filled, the CHILD
    process's own next log write blocked, freezing uvicorn's single
    worker mid-request. That surfaces to a test as `Page.goto` timing out
    on, say, the sixth navigation, having worked fine for the first five
    -- indistinguishable from a browser-side hang unless someone actually
    reads the child's blocked stdout. A background daemon thread drains
    it continuously for the fixture's entire life, so the child can never
    block on a full buffer again; the last `_STARTUP_LOG_LINES` lines are
    kept (not the unbounded full text) so the two failure paths below can
    still show real diagnostic output without this thread's own memory
    use growing over a long session.
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

    _STARTUP_LOG_LINES = 200
    log_lines: deque[str] = deque(maxlen=_STARTUP_LOG_LINES)

    def _drain_child_output() -> None:
        # QA-7: the ONLY reader of this pipe for the fixture's entire
        # life -- see the docstring above. Must never stop early (no
        # size cap on iteration itself, only on what's retained) or the
        # same deadlock returns the moment this thread would otherwise
        # exit.
        stdout = process.stdout
        if stdout is None:
            return
        for line in stdout:
            log_lines.append(line)

    drain_thread = threading.Thread(
        target=_drain_child_output, name="e2e-live-server-stdout-drain", daemon=True
    )
    drain_thread.start()

    try:
        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        became_healthy = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"uvicorn exited early (code {process.returncode}) while starting "
                    f"the e2e live_server fixture:\n{''.join(log_lines)}"
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
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise RuntimeError(
                "uvicorn never answered GET /healthz within 20s while starting the "
                f"e2e live_server fixture (last connection error: {last_error}):\n"
                f"{''.join(log_lines)}"
            )
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


# QA-7: the two viewports the inventory names -- a 360x740 phone and a
# 1280x800 desktop. Implemented with `Page.set_viewport_size()` rather
# than overriding pytest-playwright's own `browser_context_args` fixture
# (that fixture is session-scoped in the plugin; a fixture a per-test
# parametrized value needs to flow through would have to be pulled down
# to function scope, which pytest doesn't allow a session-scoped fixture
# to depend on) -- resizing the already-isolated per-test `page` fixture
# achieves the identical effect (a real viewport change Playwright itself
# reports back through `document.documentElement.clientWidth`) with no
# fixture-scope surgery.
_VIEWPORTS = [
    pytest.param({"width": 360, "height": 740}, id="mobile-360x740"),
    pytest.param({"width": 1280, "height": 800}, id="desktop-1280x800"),
]


@pytest.fixture(params=_VIEWPORTS)
def viewport_size(request: pytest.FixtureRequest) -> dict[str, int]:
    """One of QA-7's two required viewports. Parametrizing this fixture
    (rather than each test function individually) means every test that
    depends on it -- directly, or via `sized_page` below -- automatically
    runs once per viewport, with a readable `[mobile-360x740]` /
    `[desktop-1280x800]` id in `pytest -v` output, and reuse across any
    future e2e test that also needs both viewports (this task's own
    instruction: reuse this infrastructure rather than duplicating it)."""
    return dict(request.param)


@pytest.fixture
def sized_page(page: Page, viewport_size: dict[str, int]) -> Page:
    """pytest-playwright's own `page` fixture (a fresh, isolated context
    per test), resized to one of QA-7's two viewports before the test
    gets it. Tests that need the viewport parametrization take this
    fixture instead of `page` directly; every other guarantee `page`
    already gives (isolation, auto-close) is unchanged."""
    page.set_viewport_size(viewport_size)
    return page
