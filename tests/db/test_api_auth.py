"""Integration tests for POST /auth/sign-up and POST /auth/sign-in
against the real Supabase Auth (same project as everything else).

`date_of_birth` became required on every sign-up this session (the
guardian-consent gate, tasks tracked in STATUS.md/docs/DECISIONS.md) —
every sign-up call in this file uses `_ADULT_DOB` unless it is
specifically testing the under-18 path, so these tests keep proving "no
regression for adults" rather than silently exercising a code path this
task's own instructions call out as important to verify explicitly. The
under-18/guardian-consent-specific tests live in
`tests/db/test_guardian_consent.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from tests.db.conftest import admit_student, run_email, run_name, target_is_localhost

client = TestClient(app)

# Comfortably 18+ as of any date this suite will realistically run.
_ADULT_DOB = "1990-01-01"


def _tolerate_rate_limit(response: Any) -> bool:
    """Whether this response's 429 may be shrugged off (QA-2).

    Against the owner's cloud project, a 429 from Supabase Auth was a
    real, observed condition with nothing to do with the code under
    test: that project has a shared, per-project email-sending rate
    limit these tests genuinely tripped, so tolerating it was the only
    way to keep the suite usable.

    Against the local stack that accommodation is a bug in disguise.
    supabase/config.toml raises every GoTrue rate limit far beyond
    anything a test run can reach, so a 429 on localhost means something
    is actually wrong — a stale config that was never `supabase stop`ped
    and restarted, or a genuine regression in app/api/auth.py's error
    propagation — and quietly returning would hide it while showing a
    green tick. So on localhost this refuses to tolerate it, and says
    which of those two to go and look at.

    The escape hatch stays open for a non-loopback target reached
    through BCION_TEST_TARGET, where the shared-limiter reasoning still
    applies.
    """
    if response.status_code != 429:
        return False
    if target_is_localhost():
        pytest.fail(
            "Supabase Auth returned 429 against the LOCAL stack. That is "
            "not an acceptable outcome here: supabase/config.toml sets "
            "[auth.rate_limit] sign_in_sign_ups/token_refresh to 30000 per "
            "5 minutes precisely so a test run cannot reach them. Either "
            "the running stack predates that config (`make test-db-down && "
            "make test-db-up` to reload it — the CLI only reads config.toml "
            "at start), or app/api/auth.py has started propagating the "
            "wrong status. Do not re-add a 429 tolerance to make this pass.",
            pytrace=False,
        )
    return True


@pytest.fixture
def registered_user(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed user with a known password, for testing
    sign-in without depending on the project's email-confirmation
    setting (sign-up itself is tested separately, tolerant of either
    setting)."""
    email = run_email("authtest", domain="example.com")
    password = "correct-horse-battery-staple-1"
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)


class TestSignIn:
    def test_valid_credentials_return_access_token(
        self, registered_user: dict[str, str]
    ) -> None:
        response = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == registered_user["user_id"]
        assert len(body["access_token"]) > 20  # a real JWT, not a placeholder

    def test_wrong_password_returns_401(self, registered_user: dict[str, str]) -> None:
        response = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": "definitely-wrong"},
        )
        assert response.status_code == 401

    def test_nonexistent_email_also_returns_401_not_404(self) -> None:
        """No account-enumeration leak: a nonexistent email must look
        identical to a wrong password, not a distinguishable error."""
        response = client.post(
            "/auth/sign-in",
            json={"email": "definitely-not-registered@example.com", "password": "whatever123"},
        )
        assert response.status_code == 401

    def test_returned_access_token_actually_works_for_rls(
        self, admin_client: Client, registered_user: dict[str, str]
    ) -> None:
        """The token isn't just well-formed — it genuinely authenticates
        against the live database, proven by successfully creating a
        student_profile row scoped to this exact user (RLS would reject
        a bad or mismatched token)."""
        response = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        token = response.json()["access_token"]

        from app.db import get_user_scoped_client

        # CONSENT-4 (0012): student_profiles' own-row INSERT policy now
        # also requires is_admitted(auth.uid()). This test's actual point
        # is "the token genuinely authenticates for RLS", not admission,
        # so admit the user first rather than letting an unrelated gate
        # fail this test for the wrong reason.
        admit_student(admin_client, registered_user["user_id"])

        scoped_client = get_user_scoped_client(token)
        try:
            result = (
                scoped_client.table("student_profiles")
                .insert(
                    {
                        "id": registered_user["user_id"],
                        "current_class": "Class 11",
                        "language": "en",
                    }
                )
                .execute()
            )
            assert result.data[0]["id"] == registered_user["user_id"]
        finally:
            admin_client.table("student_profiles").delete().eq(
                "id", registered_user["user_id"]
            ).execute()


class TestSignUp:
    def test_sign_up_new_email_succeeds_or_requires_confirmation(
        self, admin_client: Client
    ) -> None:
        """Tolerant of the project's email-confirmation setting (201 with
        a session, or 202 pending confirmation) — and of Supabase's own
        project-level email-sending rate limit, which this specific
        request genuinely can trigger since it exercises the real
        email-sending path. That last tolerance now applies ONLY to a
        non-loopback target: on the local stack a 429 fails the test
        outright (see `_tolerate_rate_limit`), because the limits in
        supabase/config.toml put it out of reach.

        Checks the real HTTP status (429) Supabase Auth itself returns
        for a rate limit, not a guess at the message's wording
        (app/api/auth.py propagates exc.status from the underlying
        AuthApiError). The previous version of this test pattern-matched
        "rate limit" in the flattened-to-400 detail string, which flaked
        under the full suite's own combined sign-up load: Supabase has
        more than one rate-limit error code (`over_email_send_rate_limit`,
        `over_request_rate_limit`, confirmed live 2026-09-19) and not
        every variant's message necessarily contains that exact
        substring — the status code doesn't have that ambiguity."""
        email = run_email("signuptest", domain="example.com")
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-2",
                "date_of_birth": _ADULT_DOB,
            },
        )
        if _tolerate_rate_limit(response):
            return

        assert response.status_code in (201, 202)
        if response.status_code == 201:
            user_id = response.json()["user_id"]
            admin_client.auth.admin.delete_user(user_id)
        else:
            # Pending confirmation: clean up via admin lookup by email
            # rather than leaving an orphaned unconfirmed account behind.
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)

    def test_sign_up_with_already_registered_confirmed_email_does_not_error(
        self, registered_user: dict[str, str]
    ) -> None:
        """Re-attempting sign-up with an already-registered, confirmed
        email must never create a second account, and must never crash.

        What Supabase Auth returns beyond that is decided by ONE server
        setting, not by this codebase, and the two values disagree:

        * `enable_confirmations = true` (the owner's cloud project):
          GoTrue's anti-enumeration design returns the SAME ambiguous
          "pending confirmation" 202 as a genuinely new email, never a
          distinguishing error. Same principle sign-in's error handling
          already applies — never reveal whether an email exists.
        * `enable_confirmations = false` (the local stack —
          supabase/config.toml): there is no confirmation step to hide
          behind, so GoTrue answers honestly, 422 "User already
          registered", and app/api/auth.py faithfully propagates that
          status.

        Confirmations are deliberately OFF locally, and this test is the
        price of that choice rather than a reason to reverse it: turning
        them on would make three other sign-up tests in this file and
        tests/db/test_guardian_consent.py take their early-return 202
        branch and stop exercising the one true end-to-end path
        (sign-up -> session -> plan migration) at all. A test that
        returns early is not a test that passed. Paying for that
        coverage with an explicitly weaker assertion HERE, in one place,
        with the divergence written down, beats paying for it silently
        in three.

        So this asserts what holds in both configurations, and narrows
        to the exact expected status per configuration. The cloud's
        anti-enumeration property genuinely cannot be proven on the
        local stack — that gap is the local-vs-cloud GoTrue divergence
        the plan tracks separately (QA-16), not something to paper over
        by accepting any status at all.
        """
        response = client.post(
            "/auth/sign-up",
            json={
                "email": registered_user["email"],
                "password": "another-password-123",
                "date_of_birth": _ADULT_DOB,
            },
        )
        # Holds everywhere: no second real account, and no 5xx.
        assert response.status_code != 201
        assert response.status_code < 500
        if _tolerate_rate_limit(response):
            return

        if target_is_localhost():
            assert response.status_code == 422, (
                "Local GoTrue with enable_confirmations=false is expected to "
                "reject a duplicate sign-up outright. A 202 here would mean "
                "the local stack has confirmations ON, which silently guts "
                "three other sign-up tests in this suite — check "
                "supabase/config.toml's [auth.email] and restart the stack."
            )
            # Even when it admits the account exists, it must not hand
            # back the address itself or anything else about the holder.
            assert registered_user["email"] not in response.text
        else:
            assert response.status_code == 202


@pytest.fixture
def seeded_pathway_for_migration(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Migration test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Migration test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_api_auth.py",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway": pathway}
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestGuestToAccountPlanMigration:
    """Tests app.api.auth._migrate_pending_plan directly against an
    already-confirmed, already-signed-in user (via POST /auth/sign-in,
    which sends no email) rather than through POST /auth/sign-up itself
    — sign-up's own email-sending path has a real, already-observed rate
    limit (see TestSignUp above), and re-triggering it here would make
    this test flaky for a reason that has nothing to do with the
    migration logic being tested. The one true end-to-end path (sign-up
    WITH a pending_plan, in a single request) is covered separately
    below, tolerant of the same rate limit as TestSignUp's tests."""

    def test_migrate_pending_plan_creates_a_real_row(
        self,
        admin_client: Client,
        registered_user: dict[str, str],
        seeded_pathway_for_migration: dict[str, Any],
    ) -> None:
        from app.api.auth import PendingPlan, _migrate_pending_plan
        from app.db import get_anon_client

        sign_in = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]

        # CONSENT-4 (0012): saved_plans' own-row INSERT policy now also
        # requires is_admitted(auth.uid()). This test's actual point is
        # "_migrate_pending_plan writes the right row", not admission, so
        # admit the user first — see TestSignUpWithPendingPlan below for
        # the test that instead proves what happens through the REAL
        # sign-up route today, where nothing admits the user yet.
        admit_student(admin_client, registered_user["user_id"])

        fresh_client = get_anon_client()
        try:
            plan_id = _migrate_pending_plan(
                fresh_client,
                access_token,
                registered_user["user_id"],
                PendingPlan(
                    pathway_id=seeded_pathway_for_migration["pathway"]["id"],
                    estimated_additional_expenses=8000,
                    notes="Migrated from a guest session",
                ),
            )
        finally:
            fresh_client.postgrest.aclose()

        assert plan_id is not None
        row = admin_client.table("saved_plans").select("*").eq("id", plan_id).execute().data[0]
        assert row["student_id"] == registered_user["user_id"]
        assert row["pathway_id"] == seeded_pathway_for_migration["pathway"]["id"]
        assert row["notes"] == "Migrated from a guest session"
        admin_client.table("saved_plans").delete().eq("id", plan_id).execute()

    def test_migrate_pending_plan_for_nonexistent_pathway_returns_none_not_an_exception(
        self, admin_client: Client, registered_user: dict[str, str]
    ) -> None:
        """The core resilience property: a bad pending_plan must never
        raise up through sign-up and fail account creation.

        Admitted first (CONSENT-4, 0012) so the None this asserts is
        genuinely attributable to the bad pathway_id, not to the
        is_admitted() gate this test isn't about."""
        import uuid as uuid_module

        from app.api.auth import PendingPlan, _migrate_pending_plan
        from app.db import get_anon_client

        admit_student(admin_client, registered_user["user_id"])

        sign_in = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        access_token = sign_in.json()["access_token"]

        fresh_client = get_anon_client()
        try:
            plan_id = _migrate_pending_plan(
                fresh_client,
                access_token,
                registered_user["user_id"],
                PendingPlan(pathway_id=str(uuid_module.uuid4())),  # does not exist
            )
        finally:
            fresh_client.postgrest.aclose()
        assert plan_id is None


class TestSignUpWithPendingPlan:
    """The full end-to-end path: one real sign-up call that includes a
    pending_plan. Tolerant of the same email-sending rate limit as
    TestSignUp — this test's job is proving the wiring, and
    TestGuestToAccountPlanMigration above already proves the migration
    logic itself reliably without that dependency.

    CONSENT-4 (0012) REGRESSION, deliberately asserted rather than hidden:
    a brand-new adult sign-up now DOES get a `student_accounts` row
    (`account_status='active'`, `admitted_at` still null —
    `app.api.guardian_consent.ensure_active_student_account`, added by
    the adversarial-review fix that closed the "every adult permanently
    inadmissible" finding — see 0012's own header), but that row alone
    does not admit anyone: `is_admitted()` still correctly fails closed
    until a real invite code is redeemed via `POST /auth/redeem-invite`.
    `saved_plans`' INSERT policy therefore still refuses this migration,
    and `_migrate_pending_plan`'s own by-design resilience (log a
    warning, return None, never fail the sign-up itself) is exactly what
    fires — same observable outcome as before this fix, for a different,
    now-fixable reason. Before 0012 this assertion was `is not None`;
    today a real sign-up's pending plan is silently NOT carried over
    until the account actually redeems an invite — this test pins that
    down as a known, intentional gap rather than letting it regress
    further unnoticed."""

    def test_sign_up_with_pending_plan_does_not_migrate_before_admission(
        self, admin_client: Client, seeded_pathway_for_migration: dict[str, Any]
    ) -> None:
        email = run_email("migrationtest", domain="example.com")
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-3",
                "date_of_birth": _ADULT_DOB,
                "pending_plan": {
                    "pathway_id": seeded_pathway_for_migration["pathway"]["id"],
                    "notes": "From the sign-up flow itself",
                },
            },
        )
        if _tolerate_rate_limit(response):
            return
        if response.status_code == 202:
            # Email confirmation required by this project's settings —
            # migration can't happen without a session; already covered
            # by the direct-function tests above.
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)
            return

        assert response.status_code == 201
        body = response.json()
        assert body["migrated_plan_id"] is None, (
            "a brand-new, not-yet-admitted adult's pending plan must NOT be migrated "
            "(CONSENT-4's is_admitted() gate) — see this class's own docstring"
        )
        no_plan = (
            admin_client.table("saved_plans")
            .select("id")
            .eq("student_id", body["user_id"])
            .execute()
        )
        assert not no_plan.data, "no saved_plans row should exist for this brand-new user"
        admin_client.auth.admin.delete_user(body["user_id"])


class TestSignUpCreatesAdmissionAxisRow:
    """HIGH, adversarial-review finding (this session): before this fix,
    NOTHING in this codebase ever created a `student_accounts` row for an
    adult, which meant `redeem_invite()` (db/migrations/
    0012_admission_axis.sql) had no row to check/stamp for ANY adult,
    ever — every real adult account was permanently inadmissible no
    matter how valid an invite code they held. `app.api.guardian_consent.
    ensure_active_student_account`, called from `sign_up()`'s adult
    branch, closes this. Proven end-to-end through the real route, not
    just the helper function directly."""

    def test_adult_sign_up_creates_an_active_not_yet_admitted_row(
        self, admin_client: Client
    ) -> None:
        email = run_email("admissionrowtest", domain="example.com")
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-4",
                "date_of_birth": _ADULT_DOB,
            },
        )
        if _tolerate_rate_limit(response):
            return
        if response.status_code == 202:
            # No session at sign-up — the row is created on first sign-in
            # instead (enforce_guardian_consent_gate's own bootstrap);
            # covered separately by TestSignIn-adjacent live behaviour,
            # not re-proven here without a confirmed email to sign in
            # with.
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)
            return

        assert response.status_code == 201
        user_id = response.json()["user_id"]
        try:
            row = (
                admin_client.table("student_accounts")
                .select("account_status, admitted_at")
                .eq("id", user_id)
                .execute()
                .data
            )
            assert row, "sign_up() must create a student_accounts row for a real adult"
            assert row[0]["account_status"] == "active"
            assert row[0]["admitted_at"] is None, (
                "creating the row must never itself admit anyone — only redeem_invite() "
                "may ever set admitted_at"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()
            admin_client.auth.admin.delete_user(user_id)


class TestRedeemInviteRoute:
    """`POST /auth/redeem-invite` — the app-layer half of docs/CONSENT.md
    section 3 step 4, added by the same adversarial-review fix as
    `TestSignUpCreatesAdmissionAxisRow` above: without a route calling
    `redeem_invite()` (db/migrations/0012_admission_axis.sql), no caller
    could EVER become admitted, however valid their invite code."""

    def test_requires_sign_in(self) -> None:
        response = client.post("/auth/redeem-invite", json={"code": "anything"})
        assert response.status_code == 401

    def test_happy_path_admits_a_real_signed_up_adult(self, admin_client: Client) -> None:
        email = run_email("redeemroutetest", domain="example.com")
        signup = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-5",
                "date_of_birth": _ADULT_DOB,
            },
        )
        if _tolerate_rate_limit(signup):
            return
        if signup.status_code == 202:
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)
            pytest.skip(
                "email confirmation required by this project's Auth settings — no "
                "session available to redeem an invite with in this test run"
            )

        assert signup.status_code == 201
        body = signup.json()
        user_id = body["user_id"]
        access_token = body["access_token"]
        code = f"redeem-route-{user_id[:8]}"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        expires_at = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat()
        admin_client.table("pilot_invites").insert(
            {"code_hash": code_hash, "expires_at": expires_at}
        ).execute()
        try:
            response = client.post(
                "/auth/redeem-invite",
                json={"code": code},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert response.status_code == 200
            assert response.json()["admitted"] is True

            row = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert row["admitted_at"] is not None

            # A second redemption attempt (same code, same caller) must
            # fail cleanly rather than 500 — redeem_invite()'s own
            # single-use guard (0012) returns false, not an error.
            again = client.post(
                "/auth/redeem-invite",
                json={"code": code},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert again.status_code == 200
            assert again.json()["admitted"] is False
        finally:
            admin_client.table("pilot_invites").delete().eq("code_hash", code_hash).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()
            admin_client.auth.admin.delete_user(user_id)

    def test_wrong_code_returns_false_not_an_error(self, admin_client: Client) -> None:
        email = run_email("redeemroutewrong", domain="example.com")
        signup = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-6",
                "date_of_birth": _ADULT_DOB,
            },
        )
        if _tolerate_rate_limit(signup):
            return
        if signup.status_code == 202:
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)
            pytest.skip("email confirmation required — no session available")

        assert signup.status_code == 201
        body = signup.json()
        user_id = body["user_id"]
        try:
            response = client.post(
                "/auth/redeem-invite",
                json={"code": "definitely-not-a-real-code"},
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )
            assert response.status_code == 200
            assert response.json()["admitted"] is False
        finally:
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()
            admin_client.auth.admin.delete_user(user_id)
