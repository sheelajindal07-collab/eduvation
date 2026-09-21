#!/usr/bin/env python
"""Read-only smoke check for a running BCION Lite deployment (DEPLOY-5).

Issues GET requests only -- never writes anything, never signs in, never
touches a real student's data. Meant to run right after a deploy
(scripts/deploy.sh, DEPLOY-6) against staging or production, and against
`make dev` locally.

Usage:
    python scripts/smoke.py http://localhost:8000
    python scripts/smoke.py https://staging.example.com --expected-env staging

Basic-auth credentials for a gated environment (DEPLOY-7's staging
htpasswd) come from the environment, never a command-line argument
(which would land in shell history): set SMOKE_BASIC_AUTH_USER and
SMOKE_BASIC_AUTH_PASS.

Exits 0 only if every check passes; exits 1 (and prints every failing
check, not just the first) otherwise.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import httpx


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _client(base_url: str, timeout: float) -> httpx.Client:
    user = os.environ.get("SMOKE_BASIC_AUTH_USER")
    password = os.environ.get("SMOKE_BASIC_AUTH_PASS")
    auth = (user, password) if user and password else None
    # follow_redirects=False: several checks below assert on a redirect
    # response itself (e.g. /reviewer/queue -> /reviewer/sign-in), not on
    # wherever it points.
    return httpx.Client(base_url=base_url, timeout=timeout, auth=auth, follow_redirects=False)


def _get(client: httpx.Client, path: str) -> httpx.Response | None:
    try:
        return client.get(path)
    except httpx.HTTPError as exc:
        print(f"  (request to {path} failed: {exc})", file=sys.stderr)
        return None


def check_healthz(client: httpx.Client) -> CheckResult:
    response = _get(client, "/healthz")
    if response is None:
        return CheckResult("healthz", False, "request failed")
    if response.status_code != 200:
        return CheckResult("healthz", False, f"expected 200, got {response.status_code}")
    return CheckResult("healthz", True, "200 OK")


def check_readyz(client: httpx.Client) -> CheckResult:
    """DEPLOY-5: /readyz is allowed to report 503 (e.g. Supabase not yet
    provisioned on a brand-new environment) -- what matters here is that
    it answers at all, with the expected shape, not a hard requirement
    that the database happens to be reachable at smoke-check time."""
    response = _get(client, "/readyz")
    if response is None:
        return CheckResult("readyz", False, "request failed")
    if response.status_code not in (200, 503):
        return CheckResult("readyz", False, f"unexpected status {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        return CheckResult("readyz", False, "response was not JSON")
    expected_fields = ("status", "app_env", "ai_enabled", "database_reachable")
    missing = [key for key in expected_fields if key not in body]
    if missing:
        return CheckResult("readyz", False, f"response missing field(s): {missing}")
    reachable = body["database_reachable"]
    return CheckResult("readyz", True, f"{response.status_code}, database_reachable={reachable}")


def check_explore_renders(client: httpx.Client) -> CheckResult:
    response = _get(client, "/explore")
    if response is None:
        return CheckResult("explore_renders", False, "request failed")
    if response.status_code != 200:
        return CheckResult("explore_renders", False, f"expected 200, got {response.status_code}")
    if "<html" not in response.text.lower():
        return CheckResult("explore_renders", False, "response body doesn't look like HTML")
    return CheckResult("explore_renders", True, "200, HTML body")


def check_careers_json(client: httpx.Client) -> CheckResult:
    response = _get(client, "/careers")
    if response is None:
        return CheckResult("careers_json", False, "request failed")
    if response.status_code != 200:
        return CheckResult("careers_json", False, f"expected 200, got {response.status_code}")
    try:
        response.json()
    except ValueError:
        return CheckResult("careers_json", False, "response was not JSON")
    return CheckResult("careers_json", True, "200, JSON body")


def check_plans_requires_auth(client: httpx.Client) -> CheckResult:
    response = _get(client, "/plans")
    if response is None:
        return CheckResult("plans_requires_auth", False, "request failed")
    if response.status_code != 401:
        detail = f"expected 401 without a token, got {response.status_code}"
        return CheckResult("plans_requires_auth", False, detail)
    return CheckResult("plans_requires_auth", True, "401 without a token")


def check_reviewer_queue_redirects(client: httpx.Client) -> CheckResult:
    response = _get(client, "/reviewer/queue")
    if response is None:
        return CheckResult("reviewer_queue_redirects", False, "request failed")
    if response.status_code not in (302, 303, 307, 308):
        return CheckResult(
            "reviewer_queue_redirects",
            False,
            f"expected a redirect without a session, got {response.status_code}",
        )
    location = response.headers.get("location", "")
    if "sign-in" not in location:
        return CheckResult(
            "reviewer_queue_redirects", False, f"redirected to {location!r}, not a sign-in page"
        )
    return CheckResult("reviewer_queue_redirects", True, f"redirected to {location}")


def check_docs_state(client: httpx.Client, expected_env: str) -> CheckResult:
    response = _get(client, "/docs")
    if response is None:
        return CheckResult("docs_state", False, "request failed")
    if expected_env == "production":
        if response.status_code != 404:
            detail = f"expected /docs 404 in production, got {response.status_code}"
            return CheckResult("docs_state", False, detail)
        return CheckResult("docs_state", True, "404 in production")
    if response.status_code != 200:
        detail = f"expected /docs 200 outside production, got {response.status_code}"
        return CheckResult("docs_state", False, detail)
    return CheckResult("docs_state", True, f"200 outside production ({expected_env})")


def check_app_env(client: httpx.Client, expected_env: str) -> CheckResult:
    response = _get(client, "/healthz")
    if response is None:
        return CheckResult("app_env", False, "request failed")
    try:
        actual_env = response.json().get("app_env")
    except ValueError:
        return CheckResult("app_env", False, "response was not JSON")
    if actual_env != expected_env:
        detail = f"expected APP_ENV={expected_env!r}, got {actual_env!r}"
        return CheckResult("app_env", False, detail)
    return CheckResult("app_env", True, f"APP_ENV={actual_env!r}")


def run_checks(
    base_url: str,
    *,
    expected_env: str | None,
    timeout: float,
    client: httpx.Client | None = None,
) -> list[CheckResult]:
    """`client`, when given, is used as-is instead of building a new one
    from `base_url` (tests only — lets these checks run in-process
    against a TestClient rather than over a real socket; ordinary
    callers, including `main()` below, never pass it)."""
    owns_client = client is None
    active_client = client if client is not None else _client(base_url, timeout)
    try:
        results = [
            check_healthz(active_client),
            check_readyz(active_client),
            check_explore_renders(active_client),
            check_careers_json(active_client),
            check_plans_requires_auth(active_client),
            check_reviewer_queue_redirects(active_client),
        ]
        if expected_env is not None:
            results.append(check_docs_state(active_client, expected_env))
            results.append(check_app_env(active_client, expected_env))
    finally:
        if owns_client:
            active_client.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="e.g. http://localhost:8000 or https://staging.example.com")
    parser.add_argument(
        "--expected-env",
        default=None,
        help="APP_ENV /healthz should report (e.g. development, staging, production). "
        "Also gates the /docs 404-in-production check.",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    results = run_checks(args.base_url, expected_env=args.expected_env, timeout=args.timeout)

    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    failed = [r for r in results if not r.ok]
    if failed:
        print(f"\n{len(failed)} of {len(results)} check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nAll {len(results)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
