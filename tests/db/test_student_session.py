"""Live tests for `app/web/session.py` — the student-facing HTML cookie
session mechanism (AUTH-2), generalising `app/web/reviewer/auth.py`'s own
cookie pattern the same way that module's own test file
(`tests/db/test_reviewer_console.py`) verifies it.

Nothing in `app/web/session.py` is wired into a real route yet (no
student-facing HTML sign-in page exists) — so `TestGetStudentSession`
below mounts a tiny, self-contained probe app in THIS test file only,
purely to exercise `get_student_session` through FastAPI's real
dependency-injection lifecycle (the same yield/finally machinery
`get_reviewer_session` relies on), without touching or duplicating any
production route. This does not touch `app.main.app` at all.

`TestPlansStaysHeaderOnly` uses the real, fully-assembled app
(`app.main.app`) — the whole point of that class is that a brand new
cookie mechanism must not accidentally make `/plans` (Bearer-only JSON
API) start accepting a cookie instead.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.responses import Response as FastAPIResponse
from fastapi.testclient import TestClient
from supabase import Client

from app.api.deps import AuthedSession
from app.main import app as real_app
from app.web.session import (
    COOKIE_NAME,
    SESSION_ENDED_NOTICE,
    get_student_session,
    no_store,
    session_ended_redirect,
    set_student_session_cookie,
)

real_client = TestClient(real_app)


# ============================================================
# A tiny, private probe app -- exists only in this test file, exercises
# get_student_session through real FastAPI dependency resolution.
# ============================================================
_probe_app = FastAPI()


@_probe_app.get("/probe")
def _probe(session: AuthedSession | None = Depends(get_student_session)) -> dict[str, Any]:
    if session is None:
        return {"authenticated": False}
    user_response = session.client.auth.get_user(jwt=session.access_token)
    user_id = user_response.user.id if user_response and user_response.user else None
    return {"authenticated": True, "user_id": user_id}


probe_client = TestClient(_probe_app)


class TestGetStudentSession:
    """Guest, student A, student B, and a garbage/expired cookie -- the
    exact four cases the task card names."""

    def test_guest_with_no_cookie_is_unauthenticated(self) -> None:
        response = probe_client.get("/probe")
        assert response.status_code == 200
        assert response.json() == {"authenticated": False}

    def test_garbage_cookie_is_unauthenticated_not_a_crash(self) -> None:
        """Also stands in for an expired token: Supabase's own
        `get_user(jwt=...)` rejects an expired access token through the
        exact same exception path as a syntactically-bogus one, so this
        one case exercises both -- the identical convention
        `tests/db/test_reviewer_console.py`'s
        `test_queue_with_an_invalid_cookie_also_redirects_not_a_401`
        already uses for `get_reviewer_session`."""
        response = probe_client.get("/probe", cookies={COOKIE_NAME: "not-a-real-token"})
        assert response.status_code == 200
        assert response.json() == {"authenticated": False}

    def test_student_a_cookie_yields_a_working_session_for_student_a(
        self, student_a: tuple[str, Client]
    ) -> None:
        user_id, scoped_client = student_a
        token = scoped_client.auth.get_session().access_token
        response = probe_client.get("/probe", cookies={COOKIE_NAME: token})
        assert response.status_code == 200
        assert response.json() == {"authenticated": True, "user_id": user_id}

    def test_student_b_cookie_never_resolves_to_student_a(
        self, student_a: tuple[str, Client], student_b: tuple[str, Client]
    ) -> None:
        a_id, a_client = student_a
        b_id, b_client = student_b
        assert a_id != b_id  # sanity: two genuinely distinct identities

        a_token = a_client.auth.get_session().access_token
        b_token = b_client.auth.get_session().access_token

        a_response = probe_client.get("/probe", cookies={COOKIE_NAME: a_token})
        b_response = probe_client.get("/probe", cookies={COOKIE_NAME: b_token})

        assert a_response.json() == {"authenticated": True, "user_id": a_id}
        assert b_response.json() == {"authenticated": True, "user_id": b_id}


class TestSessionEndedRedirect:
    def test_carries_the_notice_clears_the_cookie_and_is_no_store(self) -> None:
        response = session_ended_redirect("/")
        assert response.status_code == 303
        assert response.headers["location"] == f"/?notice={SESSION_ENDED_NOTICE}"

        set_cookie = response.headers.get("set-cookie", "")
        assert f'{COOKIE_NAME}=""' in set_cookie
        assert "Max-Age=0" in set_cookie
        assert "Path=/" in set_cookie

        assert response.headers["Cache-Control"] == "no-store"

    def test_defaults_to_the_landing_page(self) -> None:
        response = session_ended_redirect()
        assert response.headers["location"] == f"/?notice={SESSION_ENDED_NOTICE}"


class TestNoStoreHelper:
    def test_sets_cache_control_no_store_on_a_plain_response(self) -> None:
        response = FastAPIResponse(content="ok")
        result = no_store(response)
        assert result is response  # mutates and returns the same object
        assert result.headers["Cache-Control"] == "no-store"


class TestSetStudentSessionCookie:
    """Same flags asserted the same way as
    `tests/db/test_reviewer_console.py`'s
    `TestReviewerSignInCookieFlags` — a real Supabase `Session`, not a
    fabricated stand-in, is what a future sign-in route will actually
    hand this function."""

    def test_sets_the_settled_cookie_flags(self, student_a: tuple[str, Client]) -> None:
        _user_id, scoped_client = student_a
        real_session = scoped_client.auth.get_session()

        response = FastAPIResponse()
        set_student_session_cookie(response, real_session)

        set_cookie = response.headers.get("set-cookie", "")
        assert COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/" in set_cookie
        assert "Max-Age=" in set_cookie
        # Development settings in this test run -- production's `Secure`
        # half of this same conditional is exercised the same way
        # tests/db/test_reviewer_console.py's own cookie-flags test
        # defers to tests/unit/test_csrf.py for, rather than duplicated
        # here against a real live-DB session.
        assert "Secure" not in set_cookie


class TestPlansStaysHeaderOnly:
    """The exact boundary the task card calls out: a brand new cookie
    mechanism existing anywhere in this app must not make `/plans` (the
    JSON API, Bearer-only by contract) start accepting a cookie in place
    of the `Authorization` header it requires today."""

    def test_a_cookie_alone_with_no_authorization_header_still_401s(
        self, student_a: tuple[str, Client]
    ) -> None:
        """Deliberately uses a genuinely VALID access token, carried only
        as a cookie -- the strongest version of this regression: even a
        real, live session token fails to authenticate `/plans` unless
        it travels the one way this route has ever accepted, as a Bearer
        header. A garbage cookie failing here would prove far less."""
        _user_id, scoped_client = student_a
        token = scoped_client.auth.get_session().access_token

        response = real_client.get("/plans", cookies={COOKIE_NAME: token})
        assert response.status_code == 401
        assert response.json()["detail"] == "Sign in required."

    def test_the_bearer_header_still_works_unaffected(
        self, student_a: tuple[str, Client]
    ) -> None:
        """Control for the test above: the same token, sent the way this
        route has always accepted it, still works -- so the 401 above is
        genuinely about the cookie being ignored, not some unrelated
        breakage."""
        _user_id, scoped_client = student_a
        token = scoped_client.auth.get_session().access_token

        response = real_client.get("/plans", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_no_credentials_at_all_also_401s(self) -> None:
        response = real_client.get("/plans")
        assert response.status_code == 401
