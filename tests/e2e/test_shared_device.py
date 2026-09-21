"""A11Y-4: shared-device hygiene for the reviewer console, in a REAL
browser (`make test-e2e`) -- BCION Lite runs on shared/borrowed phones
(docs/PRODUCT.md), so a cached page from a previous reviewer session is a
real leak, not a performance nitpick.

Sign in, load the queue, sign out, then simulate pressing the browser's
own Back button -- the queue must not reappear. Two independent
mechanisms are supposed to make that true together (docs/CONTRACTS.md,
"Reviewer sign-out also sends Clear-Site-Data: 'cache', the shared-
device state's mechanism"):

1. `CachePolicyMiddleware` (app/web/cache_policy.py) marks every
   `/reviewer/*` response `Cache-Control: no-store` -- which also means
   the browser's OWN back-forward cache (bfcache) is not eligible to
   restore that page at all (Chromium and Firefox both refuse to bfcache
   a `no-store` response), so "Back" is forced to make a fresh request
   rather than instantly repainting a stale, in-memory snapshot.
2. `POST /reviewer/sign-out` (app/web/reviewer/auth.py) clears the
   session cookie server-side AND sends `Clear-Site-Data: "cache"`, so
   even a browser that ignored (1) has nothing left to serve.

This test does not try to distinguish which of the two actually fired --
either one defeating the stale page is a pass, and if a future change
weakens one of them, the other is still a real, live guard, this test
still legitimately fails only if BOTH would have to fail for the queue
to reappear.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from supabase import Client

from tests.db.conftest import run_email, run_name


@pytest.fixture
def reviewer_credentials(admin_client: Client) -> Iterator[dict[str, str]]:
    """Same pattern as tests/e2e/test_smoke.py's fixture of the same name
    -- a real, pre-confirmed reviewer with a KNOWN password, needed here
    because this test signs in through the real HTML form, not an API
    token. Kept as this file's own copy rather than imported from
    test_smoke.py: fixtures defined directly in a test module (not
    conftest.py) are that module's own, and this codebase's convention
    (see tests/e2e/conftest.py's own docstring on
    `pytest_collection_modifyitems`) is a small, local duplicate over a
    cross-test-file import."""
    email = run_email("shared-device")
    password = uuid.uuid4().hex
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)  # cascades to the reviewers row


@pytest.fixture
def seeded_draft_claim(
    admin_client: Client, synthetic_source: str, reviewer_credentials: dict[str, str]
) -> Iterator[dict[str, Any]]:
    """A concrete, identifiable value seeded into the queue -- so if the
    "no-store + Clear-Site-Data" guard ever regressed and a stale queue
    page DID reappear after sign-out, this test would have something
    distinctive to have failed to find, not just a generically-different
    heading. Same shape as tests/e2e/test_smoke.py's fixture of the same
    name."""
    claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": str(uuid.uuid4()),
                "field": "verified_charges",
                "value": 909090,
                "source_id": synthetic_source,
                "verification_date": "2026-09-01",
                "verifier": run_name("shared-device-test-fixture"),
                "review_due_date": "2099-01-01",
                "status": "draft",
                "created_by": reviewer_credentials["user_id"],
            }
        )
        .execute()
        .data[0]
    )
    yield claim
    admin_client.table("claims").delete().eq("id", claim["id"]).execute()


def _sign_in(page: Page, live_server: str, reviewer_credentials: dict[str, str]) -> None:
    page.goto(f"{live_server}/reviewer/sign-in")
    page.locator("#email").fill(reviewer_credentials["email"])
    page.locator("#password").fill(reviewer_credentials["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/reviewer/queue")


def _press_back(page: Page, wait_for_url_glob: str) -> None:
    """Simulates the browser's own Back button WITHOUT Playwright's
    `page.go_back()` wrapper.

    Diagnosed against this exact suite, 2026-09-22 (five isolated,
    controlled repros outside pytest, none involving any other process or
    system load): `page.go_back()` reliably hangs -- Playwright's own
    "waiting for scheduled navigations to finish" step never resolves --
    specifically when going back to a page reached via a real,
    cookie-setting sign-in whose session was then ended by a response
    carrying `Clear-Site-Data: "cache"` (POST /reviewer/sign-out). The
    exact same flow with the sign-out response's `Clear-Site-Data` header
    removed (simulated via `context.clear_cookies()` + a plain
    `page.goto`) does NOT hang; neither does plain repeated navigation to
    a page whose static assets carry the new long-max-age
    `Cache-Control`, nor a `Clear-Site-Data` response with no prior real
    session at all. So this is a genuine Playwright/headless-Chromium
    interaction between `go_back()`'s own navigation-wait heuristic and a
    `Clear-Site-Data`-bearing response earlier in the same tab's history
    -- not a flaw in this app's behaviour (independently confirmed
    correct: the server always answers a fresh `GET /reviewer/queue`
    with a 303 to sign-in once the cookie is gone, whether reached via
    `go_back()`, `history.back()` or a plain reload).

    `window.history.back()` -- the same browser-native API `go_back()`
    itself calls -- triggers an identical, real back-navigation without
    going through the Playwright wrapper that hangs; waiting for it via
    `page.wait_for_url` afterwards (rather than `go_back()`'s own
    built-in wait) reproduced the correct, fast result in all five of
    those repros. This is the same "pressing Back" action from the
    browser's perspective, so it still exercises exactly what
    docs/CONTRACTS.md's shared-device requirement is actually about.
    """
    page.evaluate("() => { window.history.back(); }")
    page.wait_for_url(wait_for_url_glob)


class TestReviewerSignOutDefeatsSharedDeviceCaching:
    def test_back_after_sign_out_does_not_show_the_queue_again(
        self,
        page: Page,
        live_server: str,
        reviewer_credentials: dict[str, str],
        seeded_draft_claim: dict[str, Any],
    ) -> None:
        _sign_in(page, live_server, reviewer_credentials)
        expect(page.locator("h1")).to_have_text("Review queue")
        # Prove the queue really did load the seeded claim -- otherwise a
        # broken fixture could make this test pass for the wrong reason
        # (nothing to leak in the first place).
        expect(page.get_by_text("909090")).to_be_visible()

        page.get_by_role("button", name="Sign out").click()
        page.wait_for_url("**/reviewer/sign-in")
        expect(page.locator("h1")).to_have_text("Reviewer sign-in")

        # Simulates pressing the browser's own Back button -- see
        # `_press_back`'s own docstring for why this goes through
        # `window.history.back()` rather than `page.go_back()`.
        _press_back(page, "**/reviewer/sign-in")

        # Whether the browser was forced to re-request the page (no-store
        # defeating bfcache) or served nothing because Clear-Site-Data
        # already wiped what little it might have cached, the end state
        # is the same: back on the sign-in screen, never the queue.
        expect(page.locator("h1")).to_have_text("Reviewer sign-in")
        expect(page.get_by_text("Review queue", exact=False)).not_to_be_visible()
        expect(page.get_by_text("909090")).not_to_be_visible()

    def test_sign_out_response_carries_clear_site_data(
        self,
        page: Page,
        live_server: str,
        reviewer_credentials: dict[str, str],
    ) -> None:
        """Direct assertion on the header itself (docs/CONTRACTS.md:
        "Reviewer sign-out also sends Clear-Site-Data: 'cache'"),
        independent of whatever a particular browser's bfcache heuristics
        do or don't do -- this is the second, server-owned mechanism the
        test above's docstring describes, and it should hold even if a
        future browser changed its bfcache rules."""
        _sign_in(page, live_server, reviewer_credentials)

        with page.expect_response(f"{live_server}/reviewer/sign-out") as response_info:
            page.get_by_role("button", name="Sign out").click()
        response = response_info.value
        assert response.headers.get("clear-site-data") == '"cache"'
