"""PII-free structured logging + a request-id middleware (OPS-2).

## What this module provides

- `JsonFormatter` — renders one JSON object per emitted log line
  (`timestamp`, `level`, `logger`, `message`, plus whatever `extra=`
  fields a call site attached, e.g. `event`, `request_id`, `route`,
  `status`, `latency_ms`).
- `RedactionFilter` — a `logging.Filter` that rewrites a record's
  rendered message (and any string-valued `extra=` field) so that an
  email address, a phone number, or a JWT/cookie-shaped token never
  reaches a handler, regardless of how the call site built the string.
  This is enforcement, not convention: a call site that carelessly logs
  `f"user {email} failed"` still comes out redacted.
- `configure_observability(app)` — wires the two above onto the root
  logger. Called once from `app.main.create_app()`. Idempotent, so
  building more than one `FastAPI` app in one process (every test that
  calls `create_app()` again) never stacks up duplicate handlers.
- `RequestIdLoggingMiddleware` — fills `app/main.py`'s reserved
  `request_id_logging` slot (DEPLOY-18). Logs exactly one line per HTTP
  request: method, the route's TEMPLATE (`/plans/{plan_id}`, never the
  literal id/path), status and latency in milliseconds. Never a query
  string, a request or response body, a cookie value, an Authorization
  header value, or the client's IP — none of those are ever read by
  this class. Also stamps the generated id onto the response as
  `X-Request-Id`, so a support conversation can name one request
  without any of the above.
- `log_event()` — a thin helper other lanes use to emit a named,
  structured event (`log_event(logger, EVENT_LOGIN_FAILED, user_id=...)`)
  through the same JSON + redaction pipeline as every other log line.

## Running uvicorn

Always run uvicorn with `--no-access-log`. Uvicorn's own default access
log writes an unredacted line straight to its own stream for every
request (method, full path *and* query string) — it does not go through
`logging`'s handler/filter chain the way this module's own access line
does, so it both duplicates `RequestIdLoggingMiddleware`'s line and
bypasses `RedactionFilter` entirely. `mk/dev.mk`'s `make dev` target and
any production launch command must pass the flag; see `mk/logging.mk`.

## Named events

Two reserved, canonical event names other lanes emit through
`log_event()` — this module does not call either one itself, it only
defines and documents them so every future call site agrees on the
exact string instead of inventing its own:

- `EVENT_LOGIN_FAILED = "auth.login_failed"` — a sign-in attempt that
  did not produce a session (wrong credentials, rate-limited, blocked by
  the guardian-consent gate, provider error). Never logged with the
  attempted email or password — an opaque identifier only, if any.
- `EVENT_SAVE_FAILED = "plan.save_failed"` — a save (a plan, a plan
  action, a claim) that did not persist. Never logged with the saved
  content itself, only opaque ids already used elsewhere in this
  schema's own RLS policies (e.g. `user_id`, `pathway_id`).

`EVENT_HTTP_REQUEST = "http.request"` is the access-line event
`RequestIdLoggingMiddleware` emits for every request.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# --------------------------------------------------------------------
# Named events (see module docstring)
# --------------------------------------------------------------------
EVENT_HTTP_REQUEST = "http.request"
EVENT_LOGIN_FAILED = "auth.login_failed"
EVENT_SAVE_FAILED = "plan.save_failed"


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: object
) -> None:
    """Emit one named, structured event through the ordinary `logging`
    pipeline (so it still passes through `RedactionFilter`/
    `JsonFormatter` once `configure_observability` has run).

    `fields` become top-level keys in the JSON line via `logging`'s own
    `extra=` mechanism. The redaction filter is a safety net for a
    string that slips through, not a licence to pass personal data here
    on purpose — never pass an email, a phone number, a token, a name, a
    date of birth, or free-form student text as a field value.
    """
    logger.log(level, event, extra={"event": event, **fields})


# --------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------
# Order matters: the JWT pattern is the most specific (three dot-
# separated base64url segments) and must run before anything that could
# otherwise chew into it. Phone separators are deliberately limited to
# space/hyphen (never `.`) so this never fires on a decimal number, a
# version string, or a dotted IP.
_EMAIL_RE = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+")
_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+\d{1,3}[-\s]?)?(?:\d[-\s]?){9,13}\d(?!\w)")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+\S+")

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_JWT_RE, "[redacted-token]"),
    (_BEARER_RE, "Bearer [redacted-token]"),
    (_EMAIL_RE, "[redacted-email]"),
    (_PHONE_RE, "[redacted-phone]"),
)


def _redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


# The attribute names a bare `logging.LogRecord` already carries --
# anything else found on a record is a caller-supplied `extra=` field.
_RESERVED_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
) | {"message", "asctime"}


class RedactionFilter(logging.Filter):
    """Strips emails, phone numbers, and JWT/cookie-shaped tokens from
    every record this filter sees, before any handler formats it.

    Deliberately does not rely on call sites formatting safely: it calls
    `record.getMessage()` (the already `msg % args`-merged string),
    redacts THAT, and writes it back as `record.msg` with `record.args`
    cleared — so a downstream `Formatter` has no unredacted `args` left
    to re-render, no matter how the original call was structured
    (`logger.info("...%s...", value)`, an f-string, or otherwise). Any
    string-valued `extra=` field on the record is redacted the same way,
    since those become top-level fields in `JsonFormatter`'s JSON output
    too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.getMessage())
        record.args = None
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED_LOG_RECORD_ATTRS:
                continue
            if isinstance(value, str):
                record.__dict__[key] = _redact(value)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per emitted log line: `timestamp`, `level`,
    `logger`, `message`, plus any `extra=` fields a call site attached
    (e.g. `event`, `request_id`, `route`, `status`, `latency_ms`).

    Assumes `RedactionFilter` has already run on this record (both are
    always installed together by `configure_observability`) — this
    class only serialises, it does not itself scan for PII.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS or key in payload:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_observability(app: FastAPI) -> None:
    """Wire `JsonFormatter` + `RedactionFilter` onto the root logger.

    Called once from `create_app()`. Idempotent: replaces whatever
    handlers the root logger already has (e.g. `logging`'s own
    "no handlers configured" lastResort handler, which writes plain,
    unredacted text straight to stderr) rather than adding to them, so
    repeated calls — every test that builds its own app via
    `create_app()` — never stack up duplicate handlers and never leave a
    stale, unredacted handler installed from an earlier call.

    Every module in this codebase that does `logging.getLogger(__name__)`
    propagates up to the root logger by default, so this one call covers
    them too, not just `RequestIdLoggingMiddleware`'s own access line.

    Does not touch uvicorn's own loggers (`uvicorn.access`,
    `uvicorn.error`) — see this module's docstring: run uvicorn with
    `--no-access-log` instead of trying to reformat its access line.

    `app` is accepted (rather than this being a bare no-argument
    function) to match the hook shape `create_app()` calls and to leave
    room for a future per-app setting (e.g. log level from `Settings`)
    without changing every call site again.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)


def _route_template(scope: Scope) -> str:
    """The route's PATTERN (`/plans/{plan_id}`), never the literal path
    with a real id or other value substituted in — FastAPI/Starlette set
    `scope["route"]` once routing has matched, and `.path` on that route
    object is the declared pattern, not the resolved path.

    Falls back to the raw path only when nothing matched at all (a
    404) — this app's personal inputs are POST-only
    (docs/CONTRACTS.md), so an unmatched GET path here is never more
    than a static prefix, and the query string (never part of
    `scope["path"]`) is never included either way.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return str(scope.get("path", "")) or "unknown"


class RequestIdLoggingMiddleware:
    """Fills the `request_id_logging` slot DEPLOY-18 reserved (OPS-2).

    Logs exactly one line per HTTP request/response, carrying only:
    method, route template, status code, latency in milliseconds, and a
    generated request id. Never a query string, a request or response
    body, a cookie value, an Authorization header value, or the client's
    IP — this class never reads any of those. The same generated id is
    also stamped onto the response as `X-Request-Id`, so a specific
    request can be named in a support conversation without any of the
    above ever leaving the server.

    Wraps `send` rather than using Starlette's `BaseHTTPMiddleware` for
    the same reason `SecurityHeadersMiddleware` does (see that class's
    own docstring in `app/main.py`) — this never needs the response
    body, only the status code off `http.response.start`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = logging.getLogger("bcion.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        started_at = time.monotonic()
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = status_code or 500
            raise
        finally:
            latency_ms = (time.monotonic() - started_at) * 1000
            self._logger.info(
                EVENT_HTTP_REQUEST,
                extra={
                    "event": EVENT_HTTP_REQUEST,
                    "request_id": request_id,
                    "method": scope.get("method", ""),
                    "route": _route_template(scope),
                    "status": status_code,
                    "latency_ms": round(latency_ms, 2),
                },
            )
