"""Live tests for GET/POST /sign-in, GET/POST /sign-up, POST /sign-out
(AUTH-3) -- `app/web/account_pages.py`, the first real route to call
`app/web/session.py`'s `set_student_session_cookie` (AUTH-2, merged
earlier but never wired into a route until this task).

Conventions mirrored from elsewhere in this suite rather than invented
here: run-tagged emails and `admin_client` setup/teardown
(`tests/db/test_api_auth.py`'s `registered_user`), the exact cookie-flag
assertions `tests/db/test_student_session.py`'s
`TestSetStudentSessionCookie` already uses for this same cookie (this
file is the first to prove a REAL ROUTE produces them, not just the
helper function in isolation), the `_minor_dob`/`stub_email_sender`
shapes from `tests/db/test_guardian_consent.py` (kept as this file's own
copies rather than a cross-test-module import, same "no import-time
dependency on that one" reasoning that file's own docstring gives for
not reusing `test_api_auth.py`'s `registered_user`), and the `Origin`
header conventions `tests/db/test_reviewer_console.py` established for
this exact `OriginCheckMiddleware` (`app/main.py`).

`client` is a per-test FIXTURE, not a module-level singleton --
`tests/db/test_reviewer_console.py`'s own `signed_out_client()` docstring
names the exact hazard a shared client has: httpx persists any
`Set-Cookie` it receives, so one test's successful sign-in would leak
`bcion_student_session` into every LATER test's requests, turning a
plain `POST /sign-up` (which must never carry that cookie) into one
`OriginCheckMiddleware` genuinely, correctly blocks with 403 -- breaking
the very test it was meant to help. A fresh client per test removes the
hazard outright (found live, while first running this file: several
tests failed with an unexpected 403 for exactly this reason, fixed by
this fixture, not by adding an `Origin` header to routes that must not
need one).

No `/my-plan` (or any other real, wired-in protected student page)
exists yet -- AUTH-6/AUTH-14 are still open (see `tasks/INDEX.md`). To
prove the post-sign-out redirect+no-store behaviour, `TestPostSignOut`
below builds a tiny private probe app, the identical convention
`tests/db/test_student_session.py`'s own `_probe_app` already uses to
exercise `get_student_session` outside `app.main.app` -- this is genuinely
the only "protected page with a real test route" AUTH-2 has today.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from supabase import Client

import app.web.account_pages as account_pages
from app.api.deps import AuthedSession
from app.core.config import get_settings
from app.main import app
from app.notifications.logging_sender import LoggingEmailSender
from app.web.guest_session import COOKIE_NAME as GUEST_COOKIE_NAME
from app.web.session import COOKIE_NAME as STUDENT_COOKIE_NAME
from app.web.session import get_student_session, session_ended_redirect
from tests.db.conftest import admit_student, run_email

# Comfortably 18+ as of any date this suite will realistically run.
_ADULT_DOB = "1990-01-01"
_SAME_ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def client() -> TestClient:
    """A fresh client for every test -- see this module's own docstring
    for why a shared one is a real, previously-hit hazard here."""
    return TestClient(app)


def _minor_dob(age_years: int) -> str:
    today = date.today()
    try:
        return today.replace(year=today.year - age_years).isoformat()
    except ValueError:  # Feb 29 on a non-leap target year
        return today.replace(year=today.year - age_years, day=28).isoformat()


def _no_script_tag(html: str) -> bool:
    return "<script" not in html.lower()


@pytest.fixture
def registered_user(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed, ADMITTED 18+ user with a known password --
    mirrors `tests/db/test_api_auth.py`'s own `registered_user`, kept as
    this file's own copy rather than an import (same reasoning
    `tests/db/test_guardian_consent.py` gives for its own
    `confirmed_adult`)."""
    email = run_email("acctpage", domain="example.com")
    password = "correct-horse-battery-staple-1"
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    admit_student(admin_client, user_id)
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def stub_email_sender(monkeypatch: pytest.MonkeyPatch) -> LoggingEmailSender:
    """No real email provider is configured anywhere in this codebase
    (`app/notifications/logging_sender.py`) -- swapping in a
    `LoggingEmailSender` here just keeps this suite from depending on
    whatever the process-wide factory happens to resolve to, same as
    `tests/db/test_guardian_consent.py`'s identically-named fixture."""
    sender = LoggingEmailSender()
    monkeypatch.setattr("app.api.auth.get_email_sender", lambda: sender)
    return sender


class _EnabledSignupSettings:
    """A minimal stand-in for `Settings`, exposing only the one attribute
    `app/web/account_pages.py` actually reads (`signup_enabled`) --
    deliberately not `Settings(signup_enabled=True)` itself, since that
    real model is `frozen=True` and process-wide cached
    (`app.core.config.get_settings`); overriding the imported name in
    `account_pages`'s own namespace (the same pattern
    `tests/unit/test_csrf.py`'s `strict_allowed_hosts()` uses for a
    different settings field) is the narrowest possible change, and never
    touches the real cached singleton other modules still read."""

    signup_enabled = True


@pytest.fixture
def signup_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_pages, "get_settings", lambda: _EnabledSignupSettings())


def _delete_user_by_email(admin_client: Client, email: str) -> None:
    users = admin_client.auth.admin.list_users()
    match = next((u for u in users if u.email == email), None)
    if match:
        admin_client.auth.admin.delete_user(match.id)


class TestSignUpDefaultsDisabled:
    def test_signup_enabled_is_false_by_default(self) -> None:
        """Sanity check this suite's own premise: every environment ships
        with sign-ups off (app/core/config.py's fail-closed default) --
        the tests below that don't use the `signup_enabled` fixture are
        exercising the REAL default, not an assumed one."""
        assert get_settings().signup_enabled is False


class TestSignInForm:
    def test_renders_zero_js_and_no_store(self, client: TestClient) -> None:
        response = client.get("/sign-in")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert _no_script_tag(response.text)
        assert 'action="/sign-in"' in response.text
        assert 'href="/sign-up"' in response.text


class TestSignInSubmit:
    def test_wrong_password_renders_styled_401_not_raw_json(
        self, client: TestClient, registered_user: dict[str, str]
    ) -> None:
        response = client.post(
            "/sign-in",
            data={"email": registered_user["email"], "password": "definitely-wrong"},
        )
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("text/html")
        assert "Invalid email or password" in response.text
        assert '"detail"' not in response.text  # never the raw JSON error shape
        assert response.headers["cache-control"] == "no-store"

    def test_nonexistent_email_also_401s_not_404_no_enumeration_leak(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/sign-in",
            data={"email": "definitely-not-registered@example.com", "password": "whatever123"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text

    def test_valid_credentials_sets_the_real_cookie_and_redirects(
        self, client: TestClient, registered_user: dict[str, str]
    ) -> None:
        response = client.post(
            "/sign-in",
            data={"email": registered_user["email"], "password": registered_user["password"]},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/explore"

        set_cookie = response.headers.get("set-cookie", "")
        assert STUDENT_COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/" in set_cookie
        assert "Max-Age=" in set_cookie
        assert response.headers["Cache-Control"] == "no-store"

    def test_the_cookie_is_a_real_working_session_for_that_student(
        self, client: TestClient, registered_user: dict[str, str]
    ) -> None:
        """Not just correctly-flagged -- a real, live session. `/plans`
        is Bearer-only by contract
        (`tests/db/test_student_session.py::TestPlansStaysHeaderOnly`),
        so using the cookie's own token as a Bearer header is the
        strongest available proof this route handed out something real."""
        login = client.post(
            "/sign-in",
            data={"email": registered_user["email"], "password": registered_user["password"]},
            follow_redirects=False,
        )
        token = login.cookies.get(STUDENT_COOKIE_NAME)
        assert token
        plans_response = client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert plans_response.status_code == 200

    def test_rate_limited_renders_a_styled_message_not_raw_error_text(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A live 429 from Supabase Auth is not reliably reproducible
        against the local stack on purpose --
        `supabase/config.toml` raises every GoTrue rate limit far beyond
        what a test run can reach (`tests/db/test_api_auth.py`'s own
        `_tolerate_rate_limit` explains why, and refuses to accept a 429
        there as anything but a bug). What IS this route's own job -- and
        the only thing worth asserting -- is that whatever
        `HTTPException` `authenticate()` is documented to raise for a
        real Supabase rate-limit code renders as styled prose here, never
        a raw error body. Monkeypatching the one call this route makes is
        the direct, honest way to exercise that without faking a live
        provider response."""

        def _raise_rate_limited(*_args: Any, **_kwargs: Any) -> Any:
            raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")

        monkeypatch.setattr(account_pages, "authenticate", _raise_rate_limited)
        response = client.post(
            "/sign-in", data={"email": "someone@example.com", "password": "whatever"}
        )
        assert response.status_code == 429
        assert response.headers["content-type"].startswith("text/html")
        assert "Too many requests" in response.text
        assert '"detail"' not in response.text


class TestSignUpDisabled:
    def test_get_shows_the_invite_only_message_not_a_form(self, client: TestClient) -> None:
        response = client.get("/sign-up")
        assert response.status_code == 200
        assert "invite" in response.text.lower()
        assert 'action="/sign-up"' not in response.text
        assert _no_script_tag(response.text)
        assert response.headers["cache-control"] == "no-store"

    def test_post_creates_no_account_proven_live(
        self, client: TestClient, admin_client: Client
    ) -> None:
        """The load-bearing assertion: query Supabase Auth's own admin
        user list for this exact email AFTER the POST and confirm it
        genuinely does not exist -- proving `sign_up()` itself was never
        called, not merely that the HTML response looked right."""
        email = run_email("acctpage-disabled", domain="example.com")
        response = client.post(
            "/sign-up",
            data={
                "email": email,
                "password": "correct-horse-battery-staple-1",
                "date_of_birth": _ADULT_DOB,
            },
        )
        assert response.status_code == 200
        assert "invite" in response.text.lower()

        users = admin_client.auth.admin.list_users()
        assert not any(u.email == email for u in users), (
            "POST /sign-up must never call sign_up() while SIGNUP_ENABLED is "
            "false -- found an account that should not exist."
        )


@pytest.mark.usefixtures("signup_enabled")
class TestSignUpEnabled:
    def test_adult_sign_up_creates_a_real_account_and_shows_an_honest_message(
        self, client: TestClient, admin_client: Client
    ) -> None:
        email = run_email("acctpage-adult", domain="example.com")
        try:
            response = client.post(
                "/sign-up",
                data={
                    "email": email,
                    "password": "correct-horse-battery-staple-2",
                    "date_of_birth": _ADULT_DOB,
                },
            )
            assert response.status_code == 200
            assert "account created" in response.text.lower()
            assert "sign in" in response.text.lower()
            assert _no_script_tag(response.text)

            users = admin_client.auth.admin.list_users()
            assert any(u.email == email for u in users)
            # No cookie is ever set here -- see account_pages.py's own
            # module docstring, "Why this module never auto-signs-in
            # after a successful sign-up".
            assert STUDENT_COOKIE_NAME not in response.headers.get("set-cookie", "")
        finally:
            _delete_user_by_email(admin_client, email)

    def test_minor_sign_up_reports_pending_guardian_consent_not_active(
        self,
        client: TestClient,
        admin_client: Client,
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        email = run_email("acctpage-minor", domain="example.com")
        guardian_email = f"bcion-guardian-{uuid.uuid4().hex[:12]}@example.com"
        try:
            response = client.post(
                "/sign-up",
                data={
                    "email": email,
                    "password": "correct-horse-battery-staple-3",
                    "date_of_birth": _minor_dob(15),
                    "guardian_email": guardian_email,
                },
            )
            assert response.status_code == 200
            assert "guardian" in response.text.lower()
            assert STUDENT_COOKIE_NAME not in response.headers.get("set-cookie", "")
            assert len(stub_email_sender.sent) == 1  # the guardian confirmation email
        finally:
            _delete_user_by_email(admin_client, email)

    def test_a_bad_date_of_birth_degrades_to_a_friendly_message_not_a_raw_422(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/sign-up",
            data={
                "email": "someone@example.com",
                "password": "correct-horse-battery-staple-4",
                "date_of_birth": "not-a-date",
            },
        )
        assert response.status_code == 400
        assert response.headers["content-type"].startswith("text/html")
        assert '"detail"' not in response.text
        assert "check the values" in response.text.lower()

    def test_email_confirmation_pending_202_renders_a_styled_neutral_message(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The local stack's own `supabase/config.toml` disables email
        confirmation (`enable_confirmations = false`), so this specific
        `sign_up()` degrade state cannot be reproduced live here --
        monkeypatched the same direct way `TestSignInSubmit`'s rate-limit
        test is, exercising exactly the shape `app/api/auth.py`'s
        `sign_up()` documents for this status code."""

        def _raise_pending_confirmation(*_args: Any, **_kwargs: Any) -> Any:
            raise HTTPException(
                status_code=202,
                detail="Account created. Check your email to confirm before signing in.",
            )

        monkeypatch.setattr(account_pages, "sign_up", _raise_pending_confirmation)
        response = client.post(
            "/sign-up",
            data={
                "email": "someone@example.com",
                "password": "correct-horse-battery-staple-5",
                "date_of_birth": _ADULT_DOB,
            },
        )
        assert response.status_code == 202
        assert "check your email" in response.text.lower()
        assert '"detail"' not in response.text


class TestPostSignOut:
    def test_clears_both_cookies_and_is_no_store(self, client: TestClient) -> None:
        response = client.post(
            "/sign-out",
            cookies={STUDENT_COOKIE_NAME: "whatever-token", GUEST_COOKIE_NAME: "whatever-guest"},
            headers=_SAME_ORIGIN,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert response.headers["Cache-Control"] == "no-store"

        set_cookie_headers = response.headers.get_list("set-cookie")
        assert any(
            STUDENT_COOKIE_NAME in header and "Max-Age=0" in header
            for header in set_cookie_headers
        )
        assert any(
            GUEST_COOKIE_NAME in header and "Max-Age=0" in header
            for header in set_cookie_headers
        )

    def test_without_a_matching_origin_the_global_origin_check_blocks_it(
        self, client: TestClient
    ) -> None:
        """`app/main.py`'s `OriginCheckMiddleware` scopes itself to
        exactly `bcion_student_session` -- this is the FIRST route in the
        whole app a browser ever reaches while holding that cookie, so
        this is that middleware's own protection becoming live traffic
        for the first time, not a check this route re-implements itself.
        """
        response = client.post(
            "/sign-out",
            cookies={STUDENT_COOKIE_NAME: "whatever-token"},
            follow_redirects=False,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "origin_not_allowed"

    def test_sign_in_then_sign_out_then_a_protected_page_redirects_no_store(
        self, client: TestClient, registered_user: dict[str, str]
    ) -> None:
        """The exact sequence the task card's acceptance criteria asks
        for. No `/my-plan` (or any other real, wired-in protected
        student page) exists yet -- `tasks/INDEX.md` still lists AUTH-6/
        AUTH-14 as open, confirmed before writing this test, not assumed.
        The "protected page with a real test route" this proves against
        is a tiny private probe app built here, the identical convention
        `tests/db/test_student_session.py`'s own `_probe_app` already
        uses for exercising `get_student_session` outside `app.main.app`
        -- genuinely the only such route AUTH-2 has today. It differs
        from that file's probe only in ACTING like a real protected page
        would (calling `session_ended_redirect` on an absent session)
        rather than just reporting a boolean, since that is the exact
        behaviour this test needs to observe.
        """
        probe_app = FastAPI()

        @probe_app.get("/probe/protected")
        def _probe_protected(
            session: AuthedSession | None = Depends(get_student_session),
        ) -> Any:
            if session is None:
                return session_ended_redirect("/sign-in")
            return {"authenticated": True}

        probe_client = TestClient(probe_app, follow_redirects=False)

        login = client.post(
            "/sign-in",
            data={"email": registered_user["email"], "password": registered_user["password"]},
            follow_redirects=False,
        )
        token = login.cookies.get(STUDENT_COOKIE_NAME)
        assert token

        authenticated = probe_client.get(
            "/probe/protected", cookies={STUDENT_COOKIE_NAME: token}
        )
        assert authenticated.status_code == 200
        assert authenticated.json() == {"authenticated": True}

        sign_out = client.post(
            "/sign-out",
            cookies={STUDENT_COOKIE_NAME: token},
            headers=_SAME_ORIGIN,
            follow_redirects=False,
        )
        assert sign_out.status_code == 303
        assert "Max-Age=0" in sign_out.headers.get("set-cookie", "")

        # A signed-out browser no longer holds the cookie (this module's
        # own docstring discloses the token itself is not server-side
        # revoked before its natural expiry -- an already-accepted,
        # inherited residual risk, app/web/session.py's own docstring --
        # so this test proves the cookie-clearing/redirect mechanism, the
        # thing this card actually builds, not token revocation, which it
        # does not).
        after_sign_out = probe_client.get("/probe/protected")
        assert after_sign_out.status_code == 303
        assert after_sign_out.headers["location"] == "/sign-in?notice=session_ended"
        assert after_sign_out.headers["Cache-Control"] == "no-store"


class TestNavLinksHonourTheExistingHideMechanism:
    """`app/web/templates/base.html`'s new nav links were nested inside
    the EXISTING `utility_menu` block rather than added as a new one --
    this proves why that mattered: reviewer pages already override that
    whole block to empty, and this must keep hiding the new links there
    too, with no reviewer template needing to change."""

    def test_an_ordinary_student_page_shows_sign_in_and_sign_up(
        self, client: TestClient
    ) -> None:
        response = client.get("/explore")
        assert response.status_code == 200
        assert 'href="/sign-in"' in response.text
        assert 'href="/sign-up"' in response.text

    def test_the_reviewer_console_does_not_show_student_account_links(
        self, client: TestClient
    ) -> None:
        response = client.get("/reviewer/sign-in")
        assert response.status_code == 200
        assert 'href="/sign-in"' not in response.text
        assert 'href="/sign-up"' not in response.text

    def test_the_landing_page_keeps_its_settled_no_account_wall_promise(
        self, client: TestClient
    ) -> None:
        """`app/web/templates/landing.html`'s own docstring and
        `tests/unit/test_web_start.py::TestLandingPage` both settle this:
        the front door shows neither link. Caught live, before merge, by
        that existing unit test failing once these nav links were first
        added globally -- fixed in `base.html` by excluding exactly
        `current_path == "/"`, not by touching the landing template."""
        response = client.get("/")
        assert response.status_code == 200
        assert "sign in" not in response.text.lower()
        assert "sign up" not in response.text.lower()
