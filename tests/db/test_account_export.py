"""Live tests for GET /account (a signed-in-only page) and GET
/account/export (a JSON download of the signed-in student's own data) --
AUTH-9, `app/web/account_pages.py`.

Conventions mirrored from `tests/db/test_account_pages.py` rather than
invented here, for the exact same reasons that file's own docstring
gives: a fresh `TestClient` per test (a shared one leaks `Set-Cookie`
across tests), run-tagged emails, and this file's own copy of a
`registered_user`-shaped fixture rather than a cross-test-module import
("no import-time dependency on that one"). `admit_student`/`run_email`
are imported from `tests/db/conftest.py` the same way that file already
does.

The load-bearing test in this file is cross-user isolation
(`TestExportCrossUserIsolation`): two REAL signed-up students, each with
their OWN distinguishable profile/plan/plan-action/consent row, proving
student A's export never contains a byte of student B's data and vice
versa -- not by reading the query and assuming RLS works, but by actually
calling the route twice, as two different real accounts, against the
live stack.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from app.web.session import COOKIE_NAME as STUDENT_COOKIE_NAME
from app.web.session import SESSION_ENDED_NOTICE
from tests.db.conftest import admit_student, run_email, run_name

_PASSWORD = "correct-horse-battery-staple-export-1"


@pytest.fixture
def client() -> TestClient:
    """A fresh client per test -- see this module's own docstring."""
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def seeded_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A real career + pathway row, needed for `saved_plans.pathway_id`'s
    own foreign key -- same shape as `tests/db/test_api_auth.py`'s own
    `seeded_pathway_for_migration`, kept as this file's own copy for the
    same "no cross-test-module import" reasoning `test_account_pages.py`
    already gives."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Export test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Export test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_account_export.py",
            }
        )
        .execute()
        .data[0]
    )
    yield pathway
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


def _create_student_with_data(
    admin_client: Client, *, tag: str, pathway_id: str, marker: str
) -> dict[str, Any]:
    """A real, confirmed, ADMITTED student with one row in every table
    this export touches, each carrying `marker` somewhere distinguishable
    -- so a test can assert the exact marker string appears in the right
    export and nowhere else."""
    email = run_email(tag, domain="example.com")
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": _PASSWORD, "email_confirm": True}
    )
    user_id = created.user.id
    admit_student(admin_client, user_id)

    admin_client.table("student_profiles").insert(
        {"id": user_id, "current_class": "10", "interests": [marker], "language": "en"}
    ).execute()

    plan = (
        admin_client.table("saved_plans")
        .insert({"student_id": user_id, "pathway_id": pathway_id, "notes": marker})
        .execute()
        .data[0]
    )
    admin_client.table("plan_actions").insert(
        {"plan_id": plan["id"], "action_key": "check_entry_requirements", "done": True}
    ).execute()
    admin_client.table("consents").insert(
        {"student_id": user_id, "kind": marker, "action": "granted", "wording_version": "v1"}
    ).execute()

    return {"user_id": user_id, "email": email, "plan_id": plan["id"], "marker": marker}


@pytest.fixture
def student_a_data(
    admin_client: Client, seeded_pathway: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    data = _create_student_with_data(
        admin_client,
        tag="acctexport-a",
        pathway_id=seeded_pathway["id"],
        marker=f"MARKER-A-{run_name('x')}",
    )
    yield data
    admin_client.auth.admin.delete_user(data["user_id"])  # cascades every row above


@pytest.fixture
def student_b_data(
    admin_client: Client, seeded_pathway: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    data = _create_student_with_data(
        admin_client,
        tag="acctexport-b",
        pathway_id=seeded_pathway["id"],
        marker=f"MARKER-B-{run_name('x')}",
    )
    yield data
    admin_client.auth.admin.delete_user(data["user_id"])  # cascades every row above


def _sign_in(client: TestClient, email: str, password: str = _PASSWORD) -> str:
    response = client.post("/sign-in", data={"email": email, "password": password})
    assert response.status_code == 303, response.text
    token = response.cookies.get(STUDENT_COOKIE_NAME)
    assert token
    return token


class TestExportCrossUserIsolation:
    """The load-bearing proof for this whole task: two real accounts,
    two real signed-in sessions, two real live calls -- never inferred
    from reading the query."""

    def test_student_a_export_contains_only_as_own_data(
        self,
        client: TestClient,
        student_a_data: dict[str, Any],
        student_b_data: dict[str, Any],
    ) -> None:
        token = _sign_in(client, student_a_data["email"])
        response = client.get("/account/export", cookies={STUDENT_COOKIE_NAME: token})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-type"].startswith("application/json")
        raw_text = response.text
        body = response.json()

        # A's own data really is present.
        assert body["profile"]["id"] == student_a_data["user_id"]
        assert student_a_data["marker"] in body["profile"]["interests"]
        plan_ids = [p["id"] for p in body["plans"]]
        assert student_a_data["plan_id"] in plan_ids
        a_plan = next(p for p in body["plans"] if p["id"] == student_a_data["plan_id"])
        assert a_plan["notes"] == student_a_data["marker"]
        assert any(a["action_key"] == "check_entry_requirements" for a in a_plan["actions"])
        assert any(c["kind"] == student_a_data["marker"] for c in body["consents"])

        # None of B's data anywhere -- checked both structurally and as a
        # raw substring of the whole response body, so nothing B-shaped
        # could hide in a field this test didn't think to check by name.
        assert student_b_data["user_id"] not in json.dumps(body)
        assert student_b_data["marker"] not in raw_text
        assert student_b_data["plan_id"] not in raw_text

    def test_student_b_export_contains_only_bs_own_data(
        self,
        client: TestClient,
        student_a_data: dict[str, Any],
        student_b_data: dict[str, Any],
    ) -> None:
        """The mirror image of the test above -- isolation must hold in
        both directions, not just the one a lazier test might check."""
        token = _sign_in(client, student_b_data["email"])
        response = client.get("/account/export", cookies={STUDENT_COOKIE_NAME: token})
        assert response.status_code == 200
        raw_text = response.text
        body = response.json()

        assert body["profile"]["id"] == student_b_data["user_id"]
        plan_ids = [p["id"] for p in body["plans"]]
        assert student_b_data["plan_id"] in plan_ids
        b_plan = next(p for p in body["plans"] if p["id"] == student_b_data["plan_id"])
        assert b_plan["notes"] == student_b_data["marker"]

        assert student_a_data["user_id"] not in json.dumps(body)
        assert student_a_data["marker"] not in raw_text
        assert student_a_data["plan_id"] not in raw_text


class TestExportRequiresSignIn:
    def test_no_cookie_at_all_redirects_no_data(self, client: TestClient) -> None:
        response = client.get("/account/export")
        assert response.status_code == 303
        assert response.headers["location"] == f"/sign-in?notice={SESSION_ENDED_NOTICE}"
        assert response.headers["cache-control"] == "no-store"
        assert not response.headers.get("content-type", "").startswith("application/json")

    def test_garbage_cookie_redirects_no_data(self, client: TestClient) -> None:
        response = client.get(
            "/account/export", cookies={STUDENT_COOKIE_NAME: "not-a-real-token"}
        )
        assert response.status_code == 303
        assert response.headers["location"] == f"/sign-in?notice={SESSION_ENDED_NOTICE}"
        assert response.headers["cache-control"] == "no-store"


class TestAccountPageRequiresSignIn:
    def test_signed_out_redirects(self, client: TestClient) -> None:
        response = client.get("/account")
        assert response.status_code == 303
        assert response.headers["location"] == f"/sign-in?notice={SESSION_ENDED_NOTICE}"

    def test_signed_in_shows_the_download_link_zero_js(
        self, client: TestClient, student_a_data: dict[str, Any]
    ) -> None:
        token = _sign_in(client, student_a_data["email"])
        response = client.get("/account", cookies={STUDENT_COOKIE_NAME: token})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "<script" not in response.text.lower()
        assert 'href="/account/export"' in response.text


class TestExportRefusesAReviewerWithOnlyTheReviewerCookie:
    """The design decision this task left open, made and documented in
    `app/web/account_pages.py`'s own "AUTH-9" docstring section: a
    reviewer who only ever holds `bcion_reviewer_session` (the separate
    cookie `app/web/reviewer/auth.py` mints) is refused implicitly --
    `get_student_session` never reads that cookie name at all, so this
    request is indistinguishable from a guest's."""

    def test_reviewer_cookie_alone_is_treated_exactly_like_a_guest(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/account/export",
            cookies={"bcion_reviewer_session": "whatever-reviewer-token"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == f"/sign-in?notice={SESSION_ENDED_NOTICE}"


class TestExportForAReviewerWhoAlsoSignsInNormally:
    """The uncommon path this task's own acceptance criteria also names:
    if the same identity separately holds a real `bcion_student_session`
    (signing in at /sign-in like any other user), the export must still
    contain no OTHER student's rows -- the same own-row RLS guarantee
    proven for student A vs student B above, exercised here for an
    identity that is ALSO a reviewer."""

    def test_a_reviewers_own_export_never_contains_another_students_rows(
        self,
        client: TestClient,
        admin_client: Client,
        student_a_data: dict[str, Any],
    ) -> None:
        email = run_email("acctexport-reviewer", domain="example.com")
        created = admin_client.auth.admin.create_user(
            {"email": email, "password": _PASSWORD, "email_confirm": True}
        )
        reviewer_user_id = created.user.id
        admin_client.table("reviewers").insert({"user_id": reviewer_user_id}).execute()
        try:
            token = _sign_in(client, email)
            response = client.get("/account/export", cookies={STUDENT_COOKIE_NAME: token})
            assert response.status_code == 200
            body = response.json()
            # This reviewer has no student_profiles/saved_plans/consents
            # row of their own -- own-row RLS returns exactly nothing for
            # them, not student A's data or anyone else's.
            assert body["profile"] is None
            assert body["plans"] == []
            assert student_a_data["user_id"] not in json.dumps(body)
            assert student_a_data["marker"] not in response.text
        finally:
            admin_client.auth.admin.delete_user(reviewer_user_id)  # cascades reviewers row
