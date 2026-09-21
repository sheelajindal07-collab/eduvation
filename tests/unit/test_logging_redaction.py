"""OPS-2 — app/core/logging.py: JSON formatter, redaction filter,
request-id middleware.

The core acceptance bar (docs/plan/inventory-3-platform-launch.md
"### OPS-2"): a real email, a real-looking phone number and a
JWT-shaped string passed as a log call's ARGUMENT (never just avoided by
convention at the call site) never reach the emitted line, and the
access line the request-id middleware emits uses the route TEMPLATE,
never a literal path, query string, cookie value or Authorization
header value.
"""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import (
    EVENT_HTTP_REQUEST,
    EVENT_LOGIN_FAILED,
    EVENT_SAVE_FAILED,
    JsonFormatter,
    RedactionFilter,
    RequestIdLoggingMiddleware,
    log_event,
)
from app.main import app

# A realistic-shaped JWT: three dot-separated base64url segments. Not a
# real signed token (no real secret backs it) -- shape is all this test
# or the filter cares about.
_JWT_SHAPED_STRING = (
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dGhpc2lzbm90YXJlYWxzaWduYXR1cmU"
)
_REAL_LOOKING_EMAIL = "student.rohit@example.com"
_REAL_LOOKING_PHONE = "+91-9876543210"


def _make_record_and_filter_it(message: str, *args: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
    )
    RedactionFilter().filter(record)
    return record


class TestRedactionFilterStripsRealLookingSecrets:
    """Each case puts the sensitive string in the log call's ARGUMENTS
    (`logger.info("...%s...", value)` shape), not hand-built into the
    message string -- proving the filter redacts the rendered result
    regardless of how the call was made, not just when a call site
    happens to avoid it."""

    def test_email_argument_never_appears_in_the_rendered_message(self) -> None:
        record = _make_record_and_filter_it("Sign-up failed for %s", _REAL_LOOKING_EMAIL)
        rendered = record.getMessage()
        assert _REAL_LOOKING_EMAIL not in rendered
        assert "[redacted-email]" in rendered

    def test_phone_argument_never_appears_in_the_rendered_message(self) -> None:
        record = _make_record_and_filter_it(
            "Contact number on file: %s", _REAL_LOOKING_PHONE
        )
        rendered = record.getMessage()
        assert _REAL_LOOKING_PHONE not in rendered
        assert "[redacted-phone]" in rendered

    def test_jwt_shaped_argument_never_appears_in_the_rendered_message(self) -> None:
        record = _make_record_and_filter_it("Authorization: Bearer %s", _JWT_SHAPED_STRING)
        rendered = record.getMessage()
        assert _JWT_SHAPED_STRING not in rendered
        assert "[redacted-token]" in rendered

    def test_all_three_together_in_one_call(self) -> None:
        record = _make_record_and_filter_it(
            "user=%s phone=%s token=%s",
            _REAL_LOOKING_EMAIL,
            _REAL_LOOKING_PHONE,
            _JWT_SHAPED_STRING,
        )
        rendered = record.getMessage()
        for secret in (_REAL_LOOKING_EMAIL, _REAL_LOOKING_PHONE, _JWT_SHAPED_STRING):
            assert secret not in rendered

    def test_redaction_reaches_extra_fields_too_not_just_the_message(self) -> None:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="event happened",
            args=(),
            exc_info=None,
        )
        record.student_email = _REAL_LOOKING_EMAIL  # type: ignore[attr-defined]
        RedactionFilter().filter(record)
        assert record.student_email == "[redacted-email]"  # type: ignore[attr-defined]

    def test_args_are_cleared_so_a_plain_formatter_cannot_re_render_the_original(
        self,
    ) -> None:
        record = _make_record_and_filter_it("Sign-up failed for %s", _REAL_LOOKING_EMAIL)
        assert record.args is None
        formatted = logging.Formatter("%(message)s").format(record)
        assert _REAL_LOOKING_EMAIL not in formatted


class TestJsonFormatterOutput:
    def test_output_is_one_json_object_with_the_expected_keys(self) -> None:
        record = _make_record_and_filter_it("plain message")
        line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test.logger"
        assert payload["message"] == "plain message"
        assert "timestamp" in payload

    def test_extra_fields_become_top_level_json_keys(self) -> None:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="event happened",
            args=(),
            exc_info=None,
        )
        record.event = "auth.login_failed"  # type: ignore[attr-defined]
        record.request_id = "abc123"  # type: ignore[attr-defined]
        RedactionFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["event"] == "auth.login_failed"
        assert payload["request_id"] == "abc123"

    def test_a_secret_passed_through_the_full_pipeline_never_reaches_the_json_line(
        self,
    ) -> None:
        """End-to-end: a redaction-filter + json-formatter pair, wired
        the same way `configure_observability` wires them, with a real
        email address as a log call's argument."""
        record = _make_record_and_filter_it(
            "Guest->account plan migration failed for %s", _REAL_LOOKING_EMAIL
        )
        line = JsonFormatter().format(record)
        assert _REAL_LOOKING_EMAIL not in line
        assert "[redacted-email]" in line
        # The line itself must still be valid, parseable JSON.
        json.loads(line)


class TestNamedEvents:
    """Acceptance: 'Event names are listed in the module docstring.'"""

    def test_event_names_are_the_expected_stable_strings(self) -> None:
        assert EVENT_LOGIN_FAILED == "auth.login_failed"
        assert EVENT_SAVE_FAILED == "plan.save_failed"
        assert EVENT_HTTP_REQUEST == "http.request"

    def test_event_names_are_documented_in_the_module_docstring(self) -> None:
        import app.core.logging as logging_module

        docstring = logging_module.__doc__ or ""
        assert EVENT_LOGIN_FAILED in docstring
        assert EVENT_SAVE_FAILED in docstring

    def test_log_event_attaches_the_event_name_as_a_field(self) -> None:
        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        logger = logging.getLogger("test.named-events")
        logger.addHandler(_Capture())
        logger.setLevel(logging.INFO)
        logger.propagate = False
        try:
            log_event(logger, EVENT_LOGIN_FAILED, user_id="opaque-id-123")
        finally:
            logger.handlers.clear()

        assert len(captured) == 1
        assert captured[0].event == EVENT_LOGIN_FAILED  # type: ignore[attr-defined]
        assert captured[0].user_id == "opaque-id-123"  # type: ignore[attr-defined]


class TestRequestIdMiddlewareOnTheRealApp:
    """Exercised against the real, module-level `app` -- proves the
    `request_id_logging` slot really is wired to this middleware, not
    just unit tested in isolation (same pattern
    tests/unit/test_security_middleware.py uses for SEC-1's slots)."""

    def test_the_slot_is_filled_with_this_middleware(self) -> None:
        classes = [m.cls for m in app.user_middleware]
        assert RequestIdLoggingMiddleware in classes

    def test_response_carries_an_x_request_id_header(self) -> None:
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.headers["X-Request-Id"]

    def test_access_line_logs_the_route_template_not_a_literal_path_with_an_id(
        self,
    ) -> None:
        import logging as _logging

        # raise_server_exceptions=False: a "Bearer ..." Authorization
        # header on /plans/{plan_id} makes require_auth() reach for a
        # real Supabase client, which raises since no database is
        # configured in this test environment -- an unhandled 500, same
        # as any other bug would produce. That is exactly the case this
        # test wants to cover (does the access line still get logged,
        # with nothing from the request leaked, even on a 500), so the
        # exception is allowed to become an ordinary response instead of
        # propagating out of the test client.
        client = TestClient(app, raise_server_exceptions=False)
        records: list[_logging.LogRecord] = []

        class _Capture(_logging.Handler):
            def emit(self, record: _logging.LogRecord) -> None:
                records.append(record)

        access_logger = _logging.getLogger("bcion.access")
        handler = _Capture()
        access_logger.addHandler(handler)
        try:
            # A path with a dynamic segment (plan_id) AND a query string
            # carrying secret-shaped values, plus a cookie and an
            # Authorization header -- none of it may ever reach the
            # emitted access line.
            client.delete(
                f"/plans/not-a-real-plan-id?token={_JWT_SHAPED_STRING}"
                f"&email={_REAL_LOOKING_EMAIL}",
                headers={"Authorization": "Bearer some-real-token-value"},
                cookies={"session": "some-cookie-value"},
            )
        finally:
            access_logger.removeHandler(handler)

        assert len(records) == 1
        record = records[0]
        assert record.route == "/plans/{plan_id}"  # type: ignore[attr-defined]
        assert record.method == "DELETE"  # type: ignore[attr-defined]
        assert record.event == EVENT_HTTP_REQUEST  # type: ignore[attr-defined]
        assert isinstance(record.status, int)  # type: ignore[attr-defined]
        assert isinstance(record.latency_ms, float)  # type: ignore[attr-defined]

        # Nothing from the request -- not the fake plan id, not the
        # query string, not the token, not the email, not the cookie,
        # not the Authorization header value -- ever reaches the line,
        # whether read straight off the record or through the full
        # JSON-formatted + redacted pipeline.
        line = JsonFormatter().format(record)
        for leaked in (
            "not-a-real-plan-id",
            "token=",
            "email=",
            _JWT_SHAPED_STRING,
            _REAL_LOOKING_EMAIL,
            "some-real-token-value",
            "some-cookie-value",
            "?",
        ):
            assert leaked not in line, f"{leaked!r} leaked into the access log line: {line}"

    def test_a_non_http_scope_is_passed_through_untouched(self) -> None:
        """Lifespan/websocket scopes must never be logged as an HTTP
        access line -- same `scope["type"] != "http"` guard SEC-1's own
        middleware classes use."""
        import asyncio

        calls: list[str] = []

        async def _inner_app(scope: object, receive: object, send: object) -> None:
            calls.append("called")

        middleware = RequestIdLoggingMiddleware(_inner_app)  # type: ignore[arg-type]

        async def _run() -> None:
            await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

        asyncio.run(_run())
        assert calls == ["called"]
