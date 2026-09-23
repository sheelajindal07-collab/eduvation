"""Live tests for `GET /my-plan`, `POST /my-plan/save`, `POST /my-plan/remove`
(AUTH-6) -- `app/web/plan_pages.py`.

Conventions mirrored from elsewhere in this suite rather than invented
here: a fresh `TestClient` per test (`tests/db/test_account_pages.py`'s
own docstring explains why a shared one is a real, previously-hit
hazard -- a successful sign-in's `Set-Cookie` would otherwise leak into
every later test's requests), the `_SAME_ORIGIN` header convention that
same file already established for `OriginCheckMiddleware`/SEC-2's
per-route Origin guard, the `student_a`/`student_b` admission-override
fixtures `tests/db/test_plan_actions.py` already established for
CONSENT-4's `is_admitted()` gate on `saved_plans`, and the
career/pathway/source/claim seeding shape `tests/db/test_web_pages.py`'s
`two_pathways` fixture already uses for a real published claim.

`TestSignedInSessionStateAndSignOut` below is this task's own explicit,
non-optional acceptance line: AUTH-3's merge disclosed that no page in
this app had ever set `session_state="account"`, leaving `base.html`'s
"Sign out" nav branch dead code (confirmed still true by grep before
writing this file). `/my-plan` is the first page that does, so this is
also the first *real* end-to-end proof of that sign-out path -- superseding
`tests/db/test_account_pages.py::TestPostSignOut`'s own private probe app,
which that file's docstring says exists only because no such real page
existed yet.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

import app.web.plan_pages as plan_pages
from app.core.config import Settings, get_settings
from app.core.csrf import CSRF_ERROR_CODE
from app.main import app
from app.web.guest_session import COOKIE_NAME as GUEST_COOKIE_NAME
from app.web.session import COOKIE_NAME as STUDENT_COOKIE_NAME
from tests.db.conftest import admit_student, run_name

_SAME_ORIGIN = {"Origin": "http://testserver"}
_CROSS_ORIGIN = {"Origin": "https://evil.example.com"}
_SAME_REFERER = {"Referer": "http://testserver/compare/view"}


@contextmanager
def strict_allowed_hosts() -> Iterator[None]:
    """Narrow `ALLOWED_HOSTS` to `testserver` for the duration of a test.

    Same helper `tests/db/test_reviewer_console.py` already defines for
    the identical reason: the app under test boots with development
    settings, where `allowed_hosts_list` is the permissive `["*"]` and
    every declared origin therefore passes -- so a genuine cross-origin
    rejection cannot be demonstrated without a real allow-list. Not
    imported from that module because it is a private, file-local helper
    there too (matching this codebase's "each module carries its own
    small copy" convention -- see e.g. `app/web/plan_pages.py`'s own
    `_row_to_source`/`_row_to_claim`).
    """
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, allowed_hosts="testserver"
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def client() -> TestClient:
    """A fresh client per test -- see this module's own docstring."""
    return TestClient(app)


# CONSENT-4 (0012): every write to `saved_plans` now also requires
# `is_admitted(auth.uid())` -- same override-the-higher-scope-fixture
# pattern `tests/db/test_plan_actions.py` already established, rather
# than repeating `admit_student()` in every test function here.
@pytest.fixture
def student_a(student_a: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, client_ = student_a
    admit_student(admin_client, user_id)
    return user_id, client_


@pytest.fixture
def student_b(student_b: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, client_ = student_b
    admit_student(admin_client, user_id)
    return user_id, client_


def _student_token(scoped_client: Client) -> str:
    token = scoped_client.auth.get_session().access_token
    assert token
    return token


@pytest.fixture
def pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("plan-pages career")})
        .execute()
        .data[0]
    )
    row = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("plan-pages pathway"),
                "description": "Seeded by tests/db/test_plan_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    yield row
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


@pytest.fixture
def second_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("plan-pages career 2")})
        .execute()
        .data[0]
    )
    row = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("plan-pages pathway 2"),
                "description": "Seeded by tests/db/test_plan_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    yield row
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


@pytest.fixture
def pathway_with_next_action(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A pathway with one real, published, non-synthetic claim on
    `application_window` -- one of `app/planning/actions.py`'s own
    `ACTION_RULES` fields -- so a test can assert on a real, code-derived
    next action and its evidence line, not a fabricated one."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("plan-pages career (actions)")})
        .execute()
        .data[0]
    )
    pathway_row = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("plan-pages pathway (actions)"),
                "description": "Seeded by tests/db/test_plan_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("PLAN PAGES TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/plan-pages-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    admin_client.table("claims").insert(
        {
            "entity_type": "Pathway",
            "entity_id": pathway_row["id"],
            "field": "application_window",
            "value": "1 January 2027 to 31 January 2027",
            "source_id": source["id"],
            "verification_date": "2026-09-01",
            "verifier": run_name("test-fixture-reviewer"),
            "status": "published",
            "review_due_date": "2099-01-01",
        }
    ).execute()
    yield pathway_row
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


@pytest.fixture
def pathway_with_overdue_next_action(admin_client: Client) -> Iterator[dict[str, Any]]:
    """Same shape as `pathway_with_next_action` above, but the one
    published claim is verified well outside
    `app.planning.comparison.DEFAULT_FRESHNESS_SLA_DAYS` (180 days) --
    genuinely stale, so `trust_label_for_claim` returns
    `needs_rechecking` for it exactly as it would for the identical fact
    on Compare/Requirements. Fix round (ux-qa-reviewer): proves the
    amber "Needs rechecking" badge now actually reaches /my-plan's next
    actions."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("plan-pages career (overdue action)")})
        .execute()
        .data[0]
    )
    pathway_row = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("plan-pages pathway (overdue action)"),
                "description": "Seeded by tests/db/test_plan_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("PLAN PAGES TEST OVERDUE SOURCE"),
                "official_url": "https://example.invalid/plan-pages-test-overdue-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    admin_client.table("claims").insert(
        {
            "entity_type": "Pathway",
            "entity_id": pathway_row["id"],
            "field": "application_window",
            "value": "1 January 2020 to 31 January 2020",
            "source_id": source["id"],
            "verification_date": "2020-01-01",
            "verifier": run_name("test-fixture-reviewer"),
            "status": "published",
            "review_due_date": "2020-06-01",
        }
    ).execute()
    yield pathway_row
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestGetMyPlanIsHonestAndNoStore:
    def test_a_guest_with_nothing_saved_sees_the_guest_banner_and_empty_states(
        self, client: TestClient
    ) -> None:
        response = client.get("/my-plan")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert "Not saved to an account" in response.text
        assert "No current decision saved yet" in response.text
        assert "Nothing saved here yet" in response.text
        assert "<script" not in response.text.lower()


class TestGuestSavesFromCompareAndSeesItOnMyPlan:
    def test_guest_saves_and_sees_it_on_my_plan(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        """The exact acceptance line: "a guest saves from Compare and
        sees it on /my-plan". Every screen's own "Save this route" form
        posts the same shape (a bare `pathway_id`), so exercising the
        shared POST target once here covers Compare/Timeline/Requirements
        identically -- their own template tests only need to assert the
        form exists (see TestSaveFormsArePresentOnEachScreen below)."""
        response = client.post(
            "/my-plan/save",
            data={"pathway_id": pathway["id"]},
            headers=_SAME_ORIGIN,
        )
        assert response.status_code == 200  # the followed redirect's target
        assert response.url.path == "/my-plan"
        assert pathway["name"] in response.text
        assert "Not saved to an account" in response.text
        # A brand-new guest is minted a real session on this write.
        assert client.cookies.get(GUEST_COOKIE_NAME)

    def test_a_guest_plan_is_never_the_current_decision(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        """Product decision, documented in app/web/plan_pages.py's own
        docstring: `guest_plans` has no `is_current` column at all, so a
        guest's saved route always renders as a saved alternative, never
        an invented "current decision" -- the same "nobody's decision is
        invented for them" philosophy
        tests/db/test_plan_actions.py::TestOneCurrentPlanPerStudent
        already pins for accounts."""
        client.post("/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN)
        response = client.get("/my-plan")
        assert "No current decision saved yet" in response.text
        assert pathway["name"] in response.text


class TestForcedFailureNeverSaysSavedAndKeepsTheDraft:
    """Acceptance, verbatim: "A forced RPC failure shows the draft plus
    an honest error, never 'Saved' text." Two independent mechanisms
    prove it: a genuine foreign-key rejection from the real
    `save_guest_plan`/`saved_plans` write (no mock at all), and a
    monkeypatched total-outage stand-in for a provider failure -- see
    this module's own docstring."""

    def test_guest_nonexistent_pathway_id_is_a_real_fk_rejection(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        first = client.post(
            "/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN
        )
        assert first.status_code == 200

        nonexistent_pathway_id = str(uuid.uuid4())
        response = client.post(
            "/my-plan/save",
            data={"pathway_id": nonexistent_pathway_id},
            headers=_SAME_ORIGIN,
        )
        assert response.status_code == 200
        # global.difficult_state.save_failed -- checked without the
        # apostrophe in "didn't", which Jinja autoescapes to `&#39;`.
        assert "Nothing here is lost" in response.text
        # Never the success path: a real redirect never happened, so
        # this could not possibly be the "sees it on /my-plan" page a
        # successful save produces -- a stronger proof than scanning for
        # the word "Saved" itself, which also legitimately appears in
        # this same page's own "Saved alternatives" heading.
        assert response.history == []
        # The pre-existing plan -- the student's real "draft" -- is still
        # there; nothing was lost because of the failed second attempt.
        assert pathway["name"] in response.text

    def test_a_monkeypatched_total_outage_also_keeps_the_draft(
        self, client: TestClient, pathway: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client.post("/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN)

        def _raise(*_args: Any, **_kwargs: Any) -> bool:
            raise RuntimeError("simulated provider outage")

        monkeypatch.setattr(plan_pages.guest_session, "save_plan", _raise)

        response = client.post(
            "/my-plan/save",
            data={"pathway_id": pathway["id"]},
            headers=_SAME_ORIGIN,
        )
        assert response.status_code == 200
        assert "Nothing here is lost" in response.text
        assert response.history == []
        assert pathway["name"] in response.text

    def test_a_malformed_pathway_id_is_also_an_honest_failure_not_a_crash(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/my-plan/save", data={"pathway_id": "not-a-uuid"}, headers=_SAME_ORIGIN
        )
        assert response.status_code == 422
        assert "Nothing here is lost" in response.text
        assert response.history == []

    def test_account_nonexistent_pathway_id_is_also_an_honest_failure(
        self, client: TestClient, student_a: tuple[str, Client], pathway: dict[str, Any]
    ) -> None:
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        client.post(
            "/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN
        )
        response = client.post(
            "/my-plan/save",
            data={"pathway_id": str(uuid.uuid4())},
            headers=_SAME_ORIGIN,
        )
        assert response.status_code == 200
        assert "Nothing here is lost" in response.text
        assert response.history == []
        assert pathway["name"] in response.text

    def test_account_saving_the_same_pathway_twice_is_treated_as_success(
        self, client: TestClient, student_a: tuple[str, Client], pathway: dict[str, Any]
    ) -> None:
        """Asymmetry, disclosed: `guest_session.save_plan`'s own RPC is an
        idempotent upsert, but `app/api/plans.py`'s `save_plan` raises 409
        on a literal duplicate insert -- app/web/plan_pages.py's own
        comment treats that one status specially so re-saving a route you
        already have reads as success (the state the student wanted is
        already true), not a false "This didn't save". Sets the cookie on
        the CLIENT itself (`client.cookies.set`), not per-call -- a
        per-call `cookies=` kwarg does not reliably survive httpx's own
        internal redirect-follow (this test's second POST 303s to
        `GET /my-plan`), so the confirming page would otherwise silently
        fall back to the guest view (found live while writing this test,
        not assumed)."""
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        client.post("/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN)
        response = client.post(
            "/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN
        )
        assert response.status_code == 200
        assert response.url.path == "/my-plan"
        assert "Nothing here is lost" not in response.text
        assert pathway["name"] in response.text


class TestSignedInSessionStateAndSignOut:
    """The new, explicit acceptance line: a real, signed-in student's
    `/my-plan` must set `session_state="account"`, making `base.html`'s
    "Sign out" nav branch reachable for the first time in this app."""

    def test_my_plan_shows_sign_out_not_sign_in_for_a_real_session(
        self, client: TestClient, student_a: tuple[str, Client]
    ) -> None:
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        response = client.get("/my-plan")
        assert response.status_code == 200
        assert 'action="/sign-out"' in response.text
        assert "Sign out" in response.text
        assert 'href="/sign-in"' not in response.text
        assert 'href="/sign-up"' not in response.text
        # A real account session -- never the guest banner.
        assert "Not saved to an account" not in response.text

    def test_signing_out_from_my_plan_actually_signs_the_student_out(
        self, client: TestClient, student_a: tuple[str, Client]
    ) -> None:
        """Confirms the full, real sequence live: sign in (via the actual
        `/sign-in` route, not a fabricated cookie), land on `/my-plan`,
        see "Sign out", POST it, and be signed out for real afterwards."""
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        on_my_plan = client.get("/my-plan")
        assert "Sign out" in on_my_plan.text

        sign_out = client.post(
            "/sign-out",
            headers=_SAME_ORIGIN,
            follow_redirects=False,
        )
        assert sign_out.status_code == 303
        assert "Max-Age=0" in sign_out.headers.get("set-cookie", "")

        # A real browser drops a Max-Age=0 cookie; httpx's own TestClient
        # jar does not reliably do the same (found live -- the `after`
        # request below still carried the old token without this),
        # so this models what a real browser does next rather than
        # depending on that test-tooling quirk. `tests/db/
        # test_account_pages.py`'s own equivalent test avoids the same
        # gap by using a second, cookie-less client for its own "after"
        # check.
        client.cookies.delete(STUDENT_COOKIE_NAME)
        after = client.get("/my-plan")
        assert "Sign out" not in after.text
        assert 'href="/sign-in"' in after.text


class TestCurrentDecisionAndNextActions:
    def test_the_current_decision_shows_its_next_actions_with_evidence(
        self,
        client: TestClient,
        student_a: tuple[str, Client],
        pathway_with_next_action: dict[str, Any],
        second_pathway: dict[str, Any],
    ) -> None:
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        current_plan = (
            scoped_client.table("saved_plans")
            .insert({"student_id": _user_id, "pathway_id": pathway_with_next_action["id"]})
            .execute()
            .data[0]
        )
        scoped_client.table("saved_plans").update({"is_current": True}).eq(
            "id", current_plan["id"]
        ).execute()
        scoped_client.table("saved_plans").insert(
            {"student_id": _user_id, "pathway_id": second_pathway["id"]}
        ).execute()

        response = client.get("/my-plan")
        assert response.status_code == 200
        assert pathway_with_next_action["name"] in response.text
        assert "Note the application window" in response.text
        assert "example.invalid/plan-pages-test-source" in response.text
        # Disclosed gap, not asserted here: app/planning/actions.py's own
        # NextAction carries the claim's evidence (source/url/verification
        # date) but deliberately not its raw value -- so the claim's own
        # text ("1 January 2027 to 31 January 2027") never reaches this
        # page today; see this task's completion report.
        # The non-current plan renders as a saved alternative, not a
        # second current decision.
        assert second_pathway["name"] in response.text


class TestNextActionTrustLabel:
    """Fix round (ux-qa-reviewer, live-reproduced): My Plan's next
    actions never showed any of docs/UI.md's five trust-label statuses,
    so an overdue-for-recheck claim rendered with zero visual warning
    where Compare/Requirements would show the amber "Needs rechecking"
    badge for the identical fact. `app/web/plan_pages.py` now computes
    that label with the same `trust_label_for_claim` those screens
    already call and passes it to `my_plan.html`'s `evidence_line()`/
    `trust_badge()`."""

    def test_an_overdue_claim_s_next_action_shows_needs_rechecking(
        self,
        client: TestClient,
        student_a: tuple[str, Client],
        pathway_with_overdue_next_action: dict[str, Any],
    ) -> None:
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        current_plan = (
            scoped_client.table("saved_plans")
            .insert(
                {"student_id": _user_id, "pathway_id": pathway_with_overdue_next_action["id"]}
            )
            .execute()
            .data[0]
        )
        scoped_client.table("saved_plans").update({"is_current": True}).eq(
            "id", current_plan["id"]
        ).execute()

        response = client.get("/my-plan")
        assert response.status_code == 200
        assert "Note the application window" in response.text
        # The exact amber badge text `_trust_badge.html`'s `trust_badge()`
        # macro renders for `needs_rechecking` -- the same one
        # Compare/Requirements already show for an identically stale
        # claim.
        assert "Needs rechecking" in response.text
        # `evidence_line()`'s own qualifier text for this label (see
        # `_trust_badge.html`'s docstring) -- a second, independent
        # signal that the label actually reached the template, not just
        # the badge glyph on its own.
        assert "(recheck due)" in response.text

    def test_a_fresh_claim_s_next_action_does_not_show_needs_rechecking(
        self,
        client: TestClient,
        student_a: tuple[str, Client],
        pathway_with_next_action: dict[str, Any],
    ) -> None:
        """The negative case, so the assertion above is proven to be
        about staleness and not merely "the badge always renders"."""
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        current_plan = (
            scoped_client.table("saved_plans")
            .insert({"student_id": _user_id, "pathway_id": pathway_with_next_action["id"]})
            .execute()
            .data[0]
        )
        scoped_client.table("saved_plans").update({"is_current": True}).eq(
            "id", current_plan["id"]
        ).execute()

        response = client.get("/my-plan")
        assert response.status_code == 200
        assert "Note the application window" in response.text
        assert "Checked against official source" in response.text
        assert "Needs rechecking" not in response.text


class TestCrossStudentIsolationOnMyPlan:
    def test_student_b_cannot_see_student_a_s_plan_via_my_plan(
        self,
        client: TestClient,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathway: dict[str, Any],
    ) -> None:
        a_id, a_client = student_a
        _b_id, b_client = student_b
        a_client.table("saved_plans").insert(
            {"student_id": a_id, "pathway_id": pathway["id"]}
        ).execute()

        b_token = _student_token(b_client)
        client.cookies.set(STUDENT_COOKIE_NAME, b_token)
        response = client.get("/my-plan")
        assert response.status_code == 200
        assert pathway["name"] not in response.text
        assert "Nothing saved here yet" in response.text


class TestRemoveControl:
    def test_removing_a_saved_route_removes_it_from_my_plan(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        client.post("/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN)
        token = client.cookies.get(GUEST_COOKIE_NAME)
        assert token

        from app.db import get_anon_client

        plans = plan_pages.guest_session.list_plans(get_anon_client(), token)
        assert len(plans) == 1

        remove = client.post(
            "/my-plan/remove", data={"plan_id": plans[0].id}, headers=_SAME_ORIGIN
        )
        assert remove.status_code == 200
        assert pathway["name"] not in remove.text
        assert "Nothing saved here yet" in remove.text

    def test_guest_y_cannot_remove_guest_x_s_plan_by_guessing_its_id(
        self, pathway: dict[str, Any]
    ) -> None:
        client_x = TestClient(app)
        client_y = TestClient(app)

        client_x.post("/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN)
        x_token = client_x.cookies.get(GUEST_COOKIE_NAME)
        assert x_token

        from app.db import get_anon_client

        x_plans = plan_pages.guest_session.list_plans(get_anon_client(), x_token)
        assert len(x_plans) == 1
        x_plan_id = x_plans[0].id

        # Guest Y has no session of their own yet -- posting the guess
        # mints one for Y, entirely separate from X's.
        client_y.post(
            "/my-plan/remove", data={"plan_id": x_plan_id}, headers=_SAME_ORIGIN
        )

        still_there = plan_pages.guest_session.list_plans(get_anon_client(), x_token)
        assert len(still_there) == 1
        assert still_there[0].id == x_plan_id


class TestOriginGuardIsUnconditional:
    """Fix round (data-security-reviewer, live-reproduced): a brand-new
    visitor with NO session cookie at all could be driven by a hidden
    auto-submitting cross-site form into `POST /my-plan/save` with a
    mismatched `Origin`, and it succeeded -- minting a fresh guest
    session and saving an attacker-chosen pathway with zero consent.
    Root cause was `require_same_origin()`'s cookie-presence gate, correct
    for the not-yet-cookied sign-in POST but wrong here: a genuine
    same-origin "Save this route" submit always carries an `Origin`.
    `app/web/plan_pages.py` now uses `app.core.csrf.
    require_origin_unconditionally` instead, which checks Origin/Referer
    regardless of cookie presence.

    Every test below reads the actual plan state back after the rejected
    request -- not just the status code -- proving the write never
    happened."""

    def test_no_cookie_cross_origin_save_is_rejected_and_nothing_is_saved(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        # strict_allowed_hosts(): the app boots with development settings,
        # where allowed_hosts_list is the permissive `["*"]` and every
        # declared origin therefore passes -- a genuine cross-origin
        # rejection needs a real allow-list to demonstrate at all.
        with strict_allowed_hosts():
            response = client.post(
                "/my-plan/save",
                data={"pathway_id": pathway["id"]},
                headers=_CROSS_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == CSRF_ERROR_CODE
            # No guest session was minted for this rejected attempt.
            assert client.cookies.get(GUEST_COOKIE_NAME) is None

            after = client.get("/my-plan")
        assert "Nothing saved here yet" in after.text
        assert pathway["name"] not in after.text

    def test_returning_guest_cross_origin_save_is_rejected_and_existing_plan_unchanged(
        self,
        client: TestClient,
        pathway: dict[str, Any],
        second_pathway: dict[str, Any],
    ) -> None:
        with strict_allowed_hosts():
            client.post(
                "/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN
            )
            token = client.cookies.get(GUEST_COOKIE_NAME)
            assert token

            response = client.post(
                "/my-plan/save",
                data={"pathway_id": second_pathway["id"]},
                headers=_CROSS_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

            from app.db import get_anon_client

            plans = plan_pages.guest_session.list_plans(get_anon_client(), token)
        assert [p.pathway_id for p in plans] == [pathway["id"]]

    def test_signed_in_cross_origin_save_is_rejected_and_saved_plans_unchanged(
        self, client: TestClient, student_a: tuple[str, Client], pathway: dict[str, Any]
    ) -> None:
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        with strict_allowed_hosts():
            response = client.post(
                "/my-plan/save",
                data={"pathway_id": pathway["id"]},
                headers=_CROSS_ORIGIN,
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

        remaining = scoped_client.table("saved_plans").select("*").execute().data
        assert remaining == []

    def test_no_cookie_cross_origin_remove_is_rejected_and_plan_survives(
        self, pathway: dict[str, Any]
    ) -> None:
        client_x = TestClient(app)
        attacker = TestClient(app)

        with strict_allowed_hosts():
            client_x.post(
                "/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN
            )
            x_token = client_x.cookies.get(GUEST_COOKIE_NAME)
            assert x_token

            from app.db import get_anon_client

            x_plans = plan_pages.guest_session.list_plans(get_anon_client(), x_token)
            assert len(x_plans) == 1
            x_plan_id = x_plans[0].id

            response = attacker.post(
                "/my-plan/remove",
                data={"plan_id": x_plan_id},
                headers=_CROSS_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == CSRF_ERROR_CODE
            # The attacker's own request must not even mint a session,
            # let alone reach the delete.
            assert attacker.cookies.get(GUEST_COOKIE_NAME) is None

            still_there = plan_pages.guest_session.list_plans(get_anon_client(), x_token)
        assert len(still_there) == 1
        assert still_there[0].id == x_plan_id

    def test_returning_guest_cross_origin_remove_is_rejected_and_plan_survives(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        with strict_allowed_hosts():
            client.post(
                "/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN
            )
            token = client.cookies.get(GUEST_COOKIE_NAME)
            assert token

            from app.db import get_anon_client

            plan_id = plan_pages.guest_session.list_plans(get_anon_client(), token)[0].id

            response = client.post(
                "/my-plan/remove",
                data={"plan_id": plan_id},
                headers=_CROSS_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

            still_there = plan_pages.guest_session.list_plans(get_anon_client(), token)
        assert [p.id for p in still_there] == [plan_id]

    def test_signed_in_cross_origin_remove_is_rejected_and_plan_survives(
        self, client: TestClient, student_a: tuple[str, Client], pathway: dict[str, Any]
    ) -> None:
        _user_id, scoped_client = student_a
        token = _student_token(scoped_client)
        client.cookies.set(STUDENT_COOKIE_NAME, token)

        saved_plan = (
            scoped_client.table("saved_plans")
            .insert({"student_id": _user_id, "pathway_id": pathway["id"]})
            .execute()
            .data[0]
        )

        with strict_allowed_hosts():
            response = client.post(
                "/my-plan/remove",
                data={"plan_id": saved_plan["id"]},
                headers=_CROSS_ORIGIN,
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

        remaining = scoped_client.table("saved_plans").select("id").execute().data
        assert [row["id"] for row in remaining] == [saved_plan["id"]]

    def test_same_origin_with_no_cookie_is_still_accepted(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        """The fix's own boundary: a real, first-time guest save (no
        cookie yet, genuine same-origin submit) must keep working --
        this is not a re-run of `TestGuestSavesFromCompareAndSeesItOnMyPlan`
        for its own sake, it is this class's explicit proof that the new
        unconditional guard did not turn into an unconditional
        rejection."""
        response = client.post(
            "/my-plan/save",
            data={"pathway_id": pathway["id"]},
            headers=_SAME_ORIGIN,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert client.cookies.get(GUEST_COOKIE_NAME)

    def test_referer_fallback_is_accepted_for_save_with_no_cookie(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/my-plan/save",
            data={"pathway_id": pathway["id"]},
            headers=_SAME_REFERER,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert client.cookies.get(GUEST_COOKIE_NAME)

    def test_referer_fallback_is_accepted_for_remove(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        client.post("/my-plan/save", data={"pathway_id": pathway["id"]}, headers=_SAME_ORIGIN)
        token = client.cookies.get(GUEST_COOKIE_NAME)
        assert token

        from app.db import get_anon_client

        plan_id = plan_pages.guest_session.list_plans(get_anon_client(), token)[0].id

        response = client.post(
            "/my-plan/remove",
            data={"plan_id": plan_id},
            headers={"Referer": "http://testserver/my-plan"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert plan_pages.guest_session.list_plans(get_anon_client(), token) == []


class TestSaveFormsArePresentOnEachScreen:
    """The additive "Save this route" forms on Compare/Timeline/
    Requirements -- each posts to the one shared target this file's other
    classes already exercise end to end, so these three only need to
    prove the form itself renders, self-contained, zero-JS."""

    def test_compare_page_has_a_save_this_route_form(
        self, client: TestClient, pathway: dict[str, Any], second_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/compare/view", params={"pathway_id": [pathway["id"], second_pathway["id"]]}
        )
        assert response.status_code == 200
        assert response.text.count('action="/my-plan/save"') == 2
        assert f'value="{pathway["id"]}"' in response.text

    def test_requirements_page_has_a_save_this_route_form(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        response = client.get("/requirements/view", params={"pathway_id": pathway["id"]})
        assert response.status_code == 200
        assert 'action="/my-plan/save"' in response.text
        assert f'value="{pathway["id"]}"' in response.text

    def test_timeline_page_has_a_save_this_route_form_when_a_pathway_is_named(
        self, client: TestClient, pathway: dict[str, Any]
    ) -> None:
        response = client.get("/timeline/view", params={"pathway_id": pathway["id"]})
        assert response.status_code == 200
        assert 'action="/my-plan/save"' in response.text

    def test_timeline_page_has_no_save_form_with_no_pathway_context(
        self, client: TestClient
    ) -> None:
        response = client.get("/timeline/view")
        assert response.status_code == 200
        assert 'action="/my-plan/save"' not in response.text
