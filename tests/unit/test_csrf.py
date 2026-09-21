"""SEC-2: `app/core/csrf.py` — the Origin/Referer check for
cookie-authenticated state-changing requests, and its application to the
reviewer console's routes.

Split by design: the pure-function table below needs no app at all, the
route tests exercise the REAL `app` (so a regression in how the
dependency is attached is caught, not just the rule in isolation), and
`tests/db/test_reviewer_console.py` carries the one assertion this file
cannot make — that a rejected cross-origin approve leaves the claim's
status untouched in a real database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from app.core.config import Settings, get_settings
from app.core.csrf import (
    CSRF_ERROR_CODE,
    origin_is_allowed,
    request_is_guarded,
    require_same_origin,
)
from app.main import OriginCheckMiddleware, app
from app.web.reviewer import COOKIE_NAME

client = TestClient(app)

# A syntactically valid id for the action routes' `{claim_id}` — no row
# exists behind it, which is fine: every assertion in this file is about
# whether the request is rejected BEFORE the route body, so it never
# reaches a database lookup.
CLAIM_ID = str(uuid.uuid4())

DEV = Settings(_env_file=None, app_env="development", allowed_hosts="")
"""`allowed_hosts_list == ["*"]` — the permissive development fallback."""

STRICT = Settings(_env_file=None, allowed_hosts="testserver, bcion.example.com")
"""A configured allow-list. `app_env` is left at its default on purpose:
a non-empty ALLOWED_HOSTS wins in every environment, so this needs no
production-only settings and triggers none of their side effects."""

UNCONFIGURED_PROD = Settings(_env_file=None, app_env="production", allowed_hosts="")
"""SEC-1's fail-closed state: `allowed_hosts_list == []`, i.e. no host is
valid until somebody configures one."""


def _request(**headers: str) -> StarletteRequest:
    """A bare Starlette request carrying only the given headers."""
    return StarletteRequest(
        {
            "type": "http",
            "method": "POST",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
    )


@contextmanager
def _allowed_hosts(settings: Settings) -> Iterator[None]:
    """Point the real app's CSRF dependency at a narrower allow-list for
    one test.

    Overriding `get_settings` (which the dependency takes via `Depends`,
    precisely so this is possible) rather than mutating the process-wide
    cached singleton, and rather than rebuilding the app: the routes,
    routers and middleware under test stay the real ones. Note that
    TrustedHostMiddleware keeps the app's own (development, wildcard)
    settings, so `Host: testserver` still gets through — the only thing
    narrowed here is the origin check.
    """
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


class TestOriginIsAllowed:
    """The rule itself. See app/core/csrf.py's docstring for why each of
    these is what it is."""

    def test_matching_origin_is_allowed(self) -> None:
        assert origin_is_allowed(_request(origin="https://bcion.example.com"), STRICT) is True

    def test_foreign_origin_is_rejected(self) -> None:
        assert origin_is_allowed(_request(origin="https://evil.example.com"), STRICT) is False

    def test_referer_is_used_when_origin_is_absent(self) -> None:
        """Some browsers omit `Origin` on a same-site form navigation —
        the documented fallback, and the reason this check can't be
        Origin-only."""
        request = _request(referer="https://bcion.example.com/reviewer/queue")
        assert origin_is_allowed(request, STRICT) is True

    def test_foreign_referer_alone_is_rejected(self) -> None:
        request = _request(referer="https://evil.example.com/attack.html")
        assert origin_is_allowed(request, STRICT) is False

    def test_neither_header_is_rejected_not_allowed(self) -> None:
        """Fail closed. This is the single most important case in the
        file: "no Origin" must never read as "trusted"."""
        assert origin_is_allowed(_request(), STRICT) is False
        assert origin_is_allowed(_request(), DEV) is False

    def test_both_headers_present_and_agreeing_is_allowed(self) -> None:
        request = _request(
            origin="https://bcion.example.com",
            referer="https://bcion.example.com/reviewer/queue",
        )
        assert origin_is_allowed(request, STRICT) is True

    def test_good_origin_with_a_foreign_referer_is_rejected(self) -> None:
        """Both headers present but disagreeing. A browser does not
        produce this for an honest same-origin form post, so the safe
        reading is "reject", not "one of them passed"."""
        request = _request(
            origin="https://bcion.example.com",
            referer="https://evil.example.com/attack.html",
        )
        assert origin_is_allowed(request, STRICT) is False

    def test_foreign_origin_with_a_good_referer_is_rejected(self) -> None:
        """The mirror image — a forged `Referer` must not rescue a
        genuinely cross-origin `Origin`."""
        request = _request(
            origin="https://evil.example.com",
            referer="https://bcion.example.com/reviewer/queue",
        )
        assert origin_is_allowed(request, STRICT) is False

    def test_null_origin_is_rejected(self) -> None:
        """`Origin: null` (sandboxed iframe, some redirect chains) has no
        host at all."""
        assert origin_is_allowed(_request(origin="null"), STRICT) is False
        assert origin_is_allowed(_request(origin="null"), DEV) is False

    def test_empty_origin_header_falls_back_to_referer(self) -> None:
        request = _request(origin="", referer="https://bcion.example.com/x")
        assert origin_is_allowed(request, STRICT) is True

    def test_port_and_case_are_not_part_of_the_host_match(self) -> None:
        """`ALLOWED_HOSTS` is a host list, not an origin list — hostnames
        are case-insensitive and the port is not part of one."""
        request = _request(origin="https://BCION.Example.COM:8443")
        assert origin_is_allowed(request, STRICT) is True

    def test_development_wildcard_allows_any_declared_origin(self) -> None:
        """`allowed_hosts_list == ["*"]` on a developer's machine — but
        note the neither-header case above is STILL rejected here."""
        assert origin_is_allowed(_request(origin="https://anything.invalid"), DEV) is True

    def test_unconfigured_allowed_hosts_outside_development_rejects_everything(self) -> None:
        """SEC-1's fail-closed `allowed_hosts_list == []` must not
        degrade into "match nothing, so allow everything" here."""
        origin = _request(origin="https://bcion.example.com")
        referer = _request(referer="https://bcion.example.com/x")
        assert origin_is_allowed(origin, UNCONFIGURED_PROD) is False
        assert origin_is_allowed(referer, UNCONFIGURED_PROD) is False

    def test_a_wildcard_allowed_hosts_entry_is_not_expanded(self) -> None:
        """Documented, deliberate narrowing (docs/SECURITY.md): unlike
        TrustedHostMiddleware, this does NOT expand `*.example.com`. The
        failure direction is closed — such a host passes the Host check
        and fails this one — so a deployment that needs the CSRF check to
        pass must list exact hostnames."""
        wildcard = Settings(_env_file=None, app_env="production", allowed_hosts="*.example.com")
        assert origin_is_allowed(_request(origin="https://app.example.com"), wildcard) is False


class TestRequestIsGuarded:
    GUARDED = frozenset({COOKIE_NAME})

    def test_state_changing_request_with_the_cookie_is_guarded(self) -> None:
        request = _request(cookie=f"{COOKIE_NAME}=token")
        assert request_is_guarded(request, self.GUARDED) is True

    def test_state_changing_request_without_the_cookie_is_not_guarded(self) -> None:
        """The sign-in POST's case: the cookie is being created by this
        request, not sent by the browser."""
        assert request_is_guarded(_request(), self.GUARDED) is False

    def test_an_unrelated_cookie_does_not_guard_the_request(self) -> None:
        request = _request(cookie="some_analytics_cookie=1")
        assert request_is_guarded(request, self.GUARDED) is False

    def test_an_emptied_session_cookie_does_not_guard_the_request(self) -> None:
        """Signing out sets `<name>=""` with Max-Age=0. A client that
        keeps the emptied cookie instead of dropping it must still be
        able to sign in again — an empty cookie authenticates nobody, so
        guarding it would cost a lockout and buy nothing."""
        request = _request(cookie=f"{COOKIE_NAME}=")
        assert request_is_guarded(request, self.GUARDED) is False

    def test_a_safe_method_is_never_guarded(self) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "headers": [(b"cookie", f"{COOKIE_NAME}=token".encode())],
        }
        assert request_is_guarded(StarletteRequest(scope), self.GUARDED) is False


class TestRequireSameOriginFactory:
    def test_building_a_guard_with_no_cookie_names_is_refused(self) -> None:
        """A guard matching no cookie would never fire — a silent
        no-op is exactly the failure mode this check exists to prevent."""
        with pytest.raises(ValueError, match="at least one cookie name"):
            require_same_origin()


class TestReviewerActionRoutesOnTheRealApp:
    """The dependency as actually wired, against the real `app`.

    A request that passes the origin check but carries a junk session
    cookie is a 303 to /reviewer/sign-in (`get_reviewer_session` yields
    None for an unusable token). That 303 is therefore the signal for
    "the CSRF gate let this through" throughout this class; 403 is the
    signal for "it did not".
    """

    def test_cross_origin_cookie_post_is_rejected(self) -> None:
        with _allowed_hosts(STRICT):
            response = client.post(
                f"/reviewer/claims/{CLAIM_ID}/approve",
                cookies={COOKIE_NAME: "some-session-token"},
                headers={"Origin": "https://evil.example.com"},
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

    def test_cookie_post_with_neither_origin_nor_referer_is_rejected(self) -> None:
        """No allow-list narrowing needed: the absent-header case is
        rejected even under development's wildcard."""
        response = client.post(
            f"/reviewer/claims/{CLAIM_ID}/approve",
            cookies={COOKIE_NAME: "some-session-token"},
            follow_redirects=False,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

    def test_same_origin_cookie_post_passes_the_check(self) -> None:
        with _allowed_hosts(STRICT):
            response = client.post(
                f"/reviewer/claims/{CLAIM_ID}/approve",
                cookies={COOKIE_NAME: "some-session-token"},
                headers={"Origin": "http://testserver"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_referer_fallback_passes_the_check(self) -> None:
        with _allowed_hosts(STRICT):
            response = client.post(
                f"/reviewer/claims/{CLAIM_ID}/submit",
                cookies={COOKIE_NAME: "some-session-token"},
                headers={"Referer": "http://testserver/reviewer/queue"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_all_three_action_routes_carry_the_guard(self) -> None:
        """Submit, approve and reject — not just the one the regression
        test happens to use."""
        for action in ("submit", "approve", "reject"):
            response = client.post(
                f"/reviewer/claims/{CLAIM_ID}/{action}",
                cookies={COOKIE_NAME: "some-session-token"},
                follow_redirects=False,
            )
            assert response.status_code == 403, action

    def test_a_post_without_the_session_cookie_is_not_gated(self) -> None:
        """A signed-out visitor gets the friendly sign-in redirect, not a
        CSRF 403 — the check is about protecting a session, and there
        isn't one."""
        with _allowed_hosts(STRICT):
            response = client.post(
                f"/reviewer/claims/{CLAIM_ID}/approve",
                headers={"Origin": "https://evil.example.com"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_get_queue_with_the_cookie_and_no_origin_is_not_gated(self) -> None:
        """A safe method is never guarded — otherwise a reviewer
        following a bookmark would be met with a 403."""
        response = client.get(
            "/reviewer/queue",
            cookies={COOKIE_NAME: "some-session-token"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"


class TestSignInIsNotCsrfGated:
    """The lock-yourself-out case. The sign-in POST carries the
    dependency, but the browser submitting it has no session cookie yet,
    so it must never be rejected for want of an `Origin`."""

    def test_sign_in_without_a_cookie_is_never_a_csrf_403(self) -> None:
        with _allowed_hosts(STRICT):
            response = client.post(
                "/reviewer/sign-in",
                data={"email": "nobody@example.invalid", "password": "whatever"},
                headers={"Origin": "https://some-other-host.example"},
                follow_redirects=False,
            )
        # Whatever this returns (503 with no Supabase configured, 401
        # against a live local stack), it must not be the CSRF refusal.
        assert response.status_code != 403
        assert CSRF_ERROR_CODE not in response.text

    def test_sign_in_with_no_origin_at_all_is_never_a_csrf_403(self) -> None:
        response = client.post(
            "/reviewer/sign-in",
            data={"email": "nobody@example.invalid", "password": "whatever"},
            follow_redirects=False,
        )
        assert response.status_code != 403
        assert CSRF_ERROR_CODE not in response.text

    def test_an_already_signed_in_session_reposting_sign_in_IS_gated(self) -> None:
        """The other half of the same decision: once a session cookie
        exists, re-posting this form is a cookie-bearing state change
        like any other."""
        with _allowed_hosts(STRICT):
            response = client.post(
                "/reviewer/sign-in",
                data={"email": "nobody@example.invalid", "password": "whatever"},
                cookies={COOKIE_NAME: "some-session-token"},
                headers={"Origin": "https://evil.example.com"},
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == CSRF_ERROR_CODE


class TestBearerApiIsUnaffected:
    """docs/CONTRACTS.md: "the JSON API is Bearer-only; cookies belong to
    the web layer alone". `app/api/claims.py`'s own routes never attach
    this dependency and have no session cookie to trigger it.

    `raise_server_exceptions=False` because these requests get PAST the
    origin check and into `require_auth`, which — in a unit-test process
    with no Supabase configured — raises `SupabaseNotConfiguredError`.
    That 500 is pre-existing, unrelated to SEC-2, and is itself the
    evidence this class wants: the request reached the route's own
    dependency instead of being refused by the CSRF guard.
    tests/db/test_reviewer_console.py runs the same check against the
    live stack, where the bearer call genuinely succeeds.
    """

    no_raise_client = TestClient(app, raise_server_exceptions=False)

    def test_bearer_claims_route_is_never_csrf_rejected(self) -> None:
        with _allowed_hosts(STRICT):
            response = self.no_raise_client.post(
                f"/claims/{CLAIM_ID}/approve",
                headers={
                    "Authorization": "Bearer not-a-real-token",
                    "Origin": "https://evil.example.com",
                },
            )
        assert response.status_code != 403
        assert CSRF_ERROR_CODE not in response.text

    def test_bearer_claims_route_with_no_origin_header_is_never_csrf_rejected(self) -> None:
        response = self.no_raise_client.post(
            f"/claims/{CLAIM_ID}/approve",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code != 403
        assert CSRF_ERROR_CODE not in response.text


class TestSessionCookieFlagsUnchangedBySec2:
    """SEC-2's acceptance asked for the reviewer cookie's existing flags
    to be VERIFIED unchanged (`SameSite=Lax`, `HttpOnly`, `Secure` only
    in production), not modified — the origin check is a second layer
    added beside SameSite, never a replacement for it.

    tests/db/test_reviewer_console.py asserts the first two against a
    live sign-in. The production half of the `Secure` conditional has no
    live equivalent (the local stack runs APP_ENV=development), so it is
    exercised here with the Supabase call stubbed out — the only thing
    under test is the `set_cookie` call `reviewer_sign_in_submit` makes.
    """

    class _FakePostgrest:
        def aclose(self) -> None:
            return None

    class _FakeClient:
        def __init__(self) -> None:
            self.postgrest = TestSessionCookieFlagsUnchangedBySec2._FakePostgrest()

    class _FakeSession:
        access_token = "fake-access-token-for-a-cookie-flag-test"
        expires_in = 3600

    def _sign_in_with(self, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> str:
        from app.web.reviewer import auth as auth_module

        monkeypatch.setattr(auth_module, "get_anon_client", lambda: self._FakeClient())
        monkeypatch.setattr(
            auth_module, "authenticate", lambda _c, _e, _p: self._FakeSession()
        )
        monkeypatch.setattr(auth_module, "get_settings", lambda: settings)
        response = client.post(
            "/reviewer/sign-in",
            data={"email": "reviewer@example.invalid", "password": "irrelevant"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        return response.headers.get("set-cookie", "")

    def test_production_cookie_is_secure_httponly_lax_and_path_scoped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        production = Settings(
            _env_file=None,
            app_env="production",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            app_secret_key="a-real-generated-secret-key",
            allowed_hosts="testserver",
        )
        set_cookie = self._sign_in_with(monkeypatch, production)
        assert COOKIE_NAME in set_cookie
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/reviewer" in set_cookie

    def test_development_cookie_is_not_secure_so_plain_http_still_works(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        development = Settings(_env_file=None, app_env="development")
        set_cookie = self._sign_in_with(monkeypatch, development)
        assert "Secure" not in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie


class TestNoDriftFromSec1sMiddleware:
    """`app/main.py`'s `OriginCheckMiddleware` (SEC-1) implements the same
    rule for the future `bcion_student_session` cookie. The two are
    separate code paths today — SEC-2 does not own app/main.py — so this
    pins the relationship the csrf module's docstring claims: this
    dependency is never MORE PERMISSIVE than that middleware. If someone
    later loosens one, this fails.
    """

    CASES = (
        {"origin": "https://bcion.example.com"},
        {"origin": "https://evil.example.com"},
        {"referer": "https://bcion.example.com/reviewer/queue"},
        {"referer": "https://evil.example.com/attack.html"},
        {"origin": "https://bcion.example.com", "referer": "https://evil.example.com/x"},
        {"origin": "https://evil.example.com", "referer": "https://bcion.example.com/x"},
        {"origin": "null"},
        {},
    )

    def test_the_dependency_never_allows_what_the_middleware_would_reject(self) -> None:
        async def _unreachable(scope: object, receive: object, send: object) -> None:
            raise AssertionError("never called: only _origin_is_allowed is exercised")

        for settings in (STRICT, DEV, UNCONFIGURED_PROD):
            middleware = OriginCheckMiddleware(app=_unreachable, settings=settings)  # type: ignore[arg-type]
            for case in self.CASES:
                request = _request(**case)
                if origin_is_allowed(request, settings):
                    assert middleware._origin_is_allowed(request), (settings.allowed_hosts, case)
