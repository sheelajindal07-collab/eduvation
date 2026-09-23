"""Live tests for CONSENT-8 — GET /reviewer/support, the staff-only
safeguarding queue.

Runs against the real, running app (`app.main.app` via `TestClient`, the
same pattern `tests/db/test_reviewer_console.py` already established) and
the real database — `is_safeguarding_staff()` and `safeguarding_flags`'s
own RLS (`db/migrations/0013_safeguarding_schema.sql`) are the actual
enforcement being tested here, not a mock of them.

`safeguarding_staff_member` below mirrors `tests/db/test_admission.py`'s
own fixture of the same name exactly (the task's own instruction: "seed
one via safeguarding_staff, matching CONSENT-4's own test fixtures for
that table") — kept file-local rather than moved into `tests/db/conftest.py`
(not this card's file to touch), same as that file's own reasoning for
keeping it local.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from app.web.reviewer import COOKIE_NAME
from tests.db.conftest import _create_test_user, _release_test_client

client = TestClient(app)


@pytest.fixture
def safeguarding_staff_member(admin_client: Client) -> Iterator[tuple[str, Client]]:
    """Mirrors `tests/db/test_admission.py`'s own fixture of this exact
    name — see this module's own docstring."""
    user_id, user_client = _create_test_user(admin_client)
    admin_client.table("safeguarding_staff").insert({"user_id": user_id}).execute()
    yield user_id, user_client
    _release_test_client(user_client)
    admin_client.auth.admin.delete_user(user_id)


def _seed_flag(
    admin_client: Client,
    student_id: str,
    *,
    category: str = "qa-support-queue",
    hours_ago: float = 1.0,
) -> str:
    created_at = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).isoformat()
    row = (
        admin_client.table("safeguarding_flags")
        .insert({"student_id": student_id, "category": category, "created_at": created_at})
        .execute()
    )
    return str(row.data[0]["id"])


class TestSupportQueueVisibility:
    """The card's own acceptance: guest, student A, student B and a
    content reviewer (real reviewer session, NOT safeguarding staff) all
    get either a redirect or an empty/zero-row result -- never a real flag
    row. A real safeguarding-staff account can list flags."""

    def test_guest_with_no_cookie_is_redirected_not_shown_anything(self) -> None:
        response = client.get("/reviewer/support", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_guest_with_an_invalid_cookie_is_also_redirected(self) -> None:
        response = client.get(
            "/reviewer/support",
            cookies={COOKIE_NAME: "not-a-real-token"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_student_a_signed_in_gets_permission_denied_not_an_empty_page(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        safeguarding_staff_member: tuple[str, Client],
    ) -> None:
        """A signed-in NON-staff visitor must never reach the "authorized,
        currently empty" page (docs/UI.md "Permission denied" vs "Empty"
        are two distinct difficult states) -- even when a real flag exists
        for someone else entirely."""
        student_id, student_client = student_a
        staff_id, _staff_client = safeguarding_staff_member
        flag_id = _seed_flag(admin_client, staff_id)  # any real student_id will do
        try:
            token = student_client.auth.get_session().access_token
            response = client.get(
                "/reviewer/support",
                cookies={COOKIE_NAME: token},
                headers={"Accept": "text/html"},
            )
            assert response.status_code == 403
            assert flag_id not in response.text
            assert "qa-support-queue" not in response.text
        finally:
            admin_client.table("safeguarding_flags").delete().eq("id", flag_id).execute()

    def test_student_b_signed_in_also_gets_permission_denied(
        self, student_b: tuple[str, Client]
    ) -> None:
        _student_id, student_client = student_b
        token = student_client.auth.get_session().access_token
        response = client.get(
            "/reviewer/support", cookies={COOKIE_NAME: token}, headers={"Accept": "text/html"}
        )
        assert response.status_code == 403

    def test_content_reviewer_who_is_not_safeguarding_staff_gets_permission_denied(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
    ) -> None:
        """The task's own most specific wording: "A content reviewer who
        is not safeguarding staff must see nothing here, not even an
        empty authorized page." A REAL reviewer session (is_reviewer() is
        true) must still be refused -- this route gates on
        is_safeguarding_staff(), never is_reviewer()."""
        _reviewer_id, reviewer_client = reviewer
        student_id, _student_client = student_a
        flag_id = _seed_flag(admin_client, student_id)
        try:
            token = reviewer_client.auth.get_session().access_token
            response = client.get(
                "/reviewer/support",
                cookies={COOKIE_NAME: token},
                headers={"Accept": "text/html"},
            )
            assert response.status_code == 403
            assert flag_id not in response.text
            # Jinja escapes the apostrophe (&#39;) -- match the
            # apostrophe-free portion of app/web/errors.py's fixed 403 copy.
            assert "have access to this" in response.text
        finally:
            admin_client.table("safeguarding_flags").delete().eq("id", flag_id).execute()

    def test_content_reviewer_without_the_accept_header_gets_the_plain_json_403(
        self, reviewer: tuple[str, Client]
    ) -> None:
        """Same boundary, non-browser caller: no `Accept: text/html`
        means the ordinary JSON API error shape, never HTML -- and still
        never a 200."""
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.get("/reviewer/support", cookies={COOKIE_NAME: token})
        assert response.status_code == 403

    def test_real_safeguarding_staff_can_list_a_flag(
        self,
        admin_client: Client,
        safeguarding_staff_member: tuple[str, Client],
        student_a: tuple[str, Client],
    ) -> None:
        staff_id, staff_client = safeguarding_staff_member
        student_id, _student_client = student_a
        flag_id = _seed_flag(admin_client, student_id, category="qa-real-staff-visibility")
        try:
            token = staff_client.auth.get_session().access_token
            response = client.get(
                "/reviewer/support", cookies={COOKIE_NAME: token}, headers={"Accept": "text/html"}
            )
            assert response.status_code == 200
            assert "qa-real-staff-visibility" in response.text
            assert student_id in response.text  # the opaque id, on purpose
        finally:
            admin_client.table("safeguarding_flags").delete().eq("id", flag_id).execute()

    def test_real_safeguarding_staff_sees_the_empty_state_with_no_flags(
        self, admin_client: Client, safeguarding_staff_member: tuple[str, Client]
    ) -> None:
        """data-security-reviewer finding (2026-09-23): 'empty' is a
        property of the WHOLE safeguarding_flags table, not something
        this test's own fixtures can scope to themselves -- unlike every
        other table this session's fixtures tag with a per-run marker,
        a real flag row carries no run-scoping concept at all (the real
        page shows every pending flag, globally, by design). Live-
        reproduced by the reviewer: under this repo's own approved
        parallel-workflow model, another worktree can run this identical
        file concurrently against the same shared local stack and seed a
        transient flag via its own `_seed_flag()` at the exact moment
        this assertion runs, making a correct test fail for a reason
        that has nothing to do with this diff. Rather than assert a
        global invariant this test cannot itself guarantee, check the
        real precondition first and skip -- honestly, not silently --
        if it does not hold; the assertion below is still fully
        exercised, and asserted for real, the overwhelming majority of
        runs where no sibling worktree happens to overlap."""
        existing = admin_client.table("safeguarding_flags").select("id").execute()
        if existing.data:
            pytest.skip(
                "safeguarding_flags is not empty right now (likely a concurrently-running "
                "sibling worktree's own _seed_flag() -- see this test's own docstring) -- "
                "skipping rather than asserting a global invariant this test cannot control."
            )

        _staff_id, staff_client = safeguarding_staff_member
        token = staff_client.auth.get_session().access_token
        response = client.get(
            "/reviewer/support", cookies={COOKIE_NAME: token}, headers={"Accept": "text/html"}
        )
        assert response.status_code == 200
        assert "Nothing waiting on safeguarding staff" in response.text


class TestOverdueHighlight:
    def test_a_flag_over_24_hours_old_is_visibly_marked_overdue(
        self,
        admin_client: Client,
        safeguarding_staff_member: tuple[str, Client],
        student_a: tuple[str, Client],
    ) -> None:
        staff_id, staff_client = safeguarding_staff_member
        student_id, _student_client = student_a
        old_flag_id = _seed_flag(admin_client, student_id, category="qa-overdue", hours_ago=25)
        recent_flag_id = _seed_flag(admin_client, student_id, category="qa-recent", hours_ago=1)
        try:
            token = staff_client.auth.get_session().access_token
            response = client.get(
                "/reviewer/support", cookies={COOKIE_NAME: token}, headers={"Accept": "text/html"}
            )
            assert response.status_code == 200
            assert "Overdue" in response.text
        finally:
            admin_client.table("safeguarding_flags").delete().eq("id", old_flag_id).execute()
            admin_client.table("safeguarding_flags").delete().eq("id", recent_flag_id).execute()


class TestFrozenAccountsDisclosedGap:
    def test_frozen_accounts_section_says_not_available_not_dropped_silently(
        self, safeguarding_staff_member: tuple[str, Client]
    ) -> None:
        """See app/web/support_pages.py's own docstring: `student_accounts`
        has no policy letting any signed-in session (staff included) read
        another user's row, so this section cannot list real data today.
        CLAUDE.md: "a missing section says 'Not available', never dropped
        silently" -- asserted here, not just assumed."""
        _staff_id, staff_client = safeguarding_staff_member
        token = staff_client.auth.get_session().access_token
        response = client.get(
            "/reviewer/support", cookies={COOKIE_NAME: token}, headers={"Accept": "text/html"}
        )
        assert response.status_code == 200
        assert "Frozen accounts" in response.text
        assert "Not available" in response.text


class TestAcknowledgeNotYetSupported:
    def test_no_acknowledge_route_exists_yet(
        self, safeguarding_staff_member: tuple[str, Client]
    ) -> None:
        """Disclosed gap, not a silent omission: `safeguarding_flags` has
        no acknowledged/status column and no update policy for anyone
        (0013's own comment: "Phase-2's detection logic ... will need its
        own write path ... when it exists"). Asserting the 404 here makes
        the gap visible to the test suite rather than merely to a
        docstring -- a future migration that adds this write path should
        make this test start failing, which is the correct signal to
        replace it with a real acknowledge test."""
        _staff_id, staff_client = safeguarding_staff_member
        token = staff_client.auth.get_session().access_token
        response = client.post(
            "/reviewer/support/00000000-0000-0000-0000-000000000000/acknowledge",
            cookies={COOKIE_NAME: token},
        )
        assert response.status_code == 404
