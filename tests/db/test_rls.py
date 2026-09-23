"""RLS access-matrix tests: guest / student A / student B / reviewer.

Exit proof for tasks/BCI-002.md (M1). Every assertion here runs as the
restricted role a real request would use — never as the database owner,
which bypasses RLS and would hide the very bug this file exists to catch.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from postgrest.exceptions import APIError
from supabase import Client

from tests.db.conftest import admit_student, run_name


def _career_row(admin: Client) -> dict[str, Any]:
    result = (
        admin.table("careers")
        .insert({"name": run_name("RLS test career (SYNTHETIC)")})
        .execute()
    )
    return result.data[0]


def _pathway_row(admin: Client, career_id: str) -> dict[str, Any]:
    result = (
        admin.table("pathways")
        .insert(
            {
                "career_id": career_id,
                "name": run_name("RLS test pathway (SYNTHETIC)"),
                "description": "PUB-3 RLS test fixture.",
            }
        )
        .execute()
    )
    return result.data[0]


class TestPublicKnowledgeBaseReads:
    """sources / careers / pathways / published claims: world-readable."""

    def test_guest_can_read_careers(self, admin_client: Client, guest_client: Client) -> None:
        career = _career_row(admin_client)
        try:
            seen = guest_client.table("careers").select("*").eq("id", career["id"]).execute()
            assert len(seen.data) == 1
        finally:
            admin_client.table("careers").delete().eq("id", career["id"]).execute()

    def test_guest_cannot_read_draft_claims(
        self,
        admin_client: Client,
        guest_client: Client,
        synthetic_source: str,
    ) -> None:
        career = _career_row(admin_client)
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Career",
                    "entity_id": career["id"],
                    "field": "name",
                    "value": "should not be visible to a guest",
                    "source_id": synthetic_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("test-fixture"),
                    "status": "draft",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
        )
        claim_id = claim.data[0]["id"]
        try:
            seen = guest_client.table("claims").select("*").eq("id", claim_id).execute()
            assert seen.data == [], "a draft claim must never be readable by a guest"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestWriteAccess:
    """Only a reviewer may write to the public knowledge base."""

    def test_guest_cannot_insert_career(self, guest_client: Client) -> None:
        try:
            guest_client.table("careers").insert({"name": "should be rejected"}).execute()
            raised = False
        except Exception:  # noqa: BLE001 — any rejection is the point; asserting on it below
            raised = True
        assert raised, "RLS must reject a guest insert into careers"

    def test_student_cannot_insert_career(self, student_a: tuple[str, Client]) -> None:
        _user_id, client = student_a
        try:
            client.table("careers").insert({"name": "should be rejected"}).execute()
            raised = False
        except Exception:  # noqa: BLE001
            raised = True
        assert raised, "RLS must reject a non-reviewer student's insert into careers"

    def test_reviewer_can_insert_career(self, reviewer: tuple[str, Client]) -> None:
        _user_id, client = reviewer
        result = (
            client.table("careers")
            .insert({"name": run_name("RLS test career (SYNTHETIC)")})
            .execute()
        )
        career_id = result.data[0]["id"]
        client.table("careers").delete().eq("id", career_id).execute()


class TestStudentProfileIsolation:
    """student_profiles: strictly own-row, no cross-student access.

    CONSENT-4 (0012): writing a profile now also requires
    `is_admitted(auth.uid())`, so every student whose OWN write must
    succeed here is admitted first via `admit_student()` — see that
    helper's own docstring in conftest.py.
    """

    def test_student_can_create_own_profile(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        user_id, client = student_a
        admit_student(admin_client, user_id)
        result = (
            client.table("student_profiles")
            .insert({"id": user_id, "current_class": "Class 10", "language": "en"})
            .execute()
        )
        assert result.data[0]["id"] == user_id

    def test_student_b_cannot_read_student_a_profile(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
    ) -> None:
        user_a_id, client_a = student_a
        _user_b_id, client_b = student_b
        admit_student(admin_client, user_a_id)
        client_a.table("student_profiles").insert(
            {"id": user_a_id, "current_class": "Class 10", "language": "en"}
        ).execute()

        seen = client_b.table("student_profiles").select("*").eq("id", user_a_id).execute()
        assert seen.data == [], "student B must not be able to read student A's profile"

    def test_student_b_cannot_update_student_a_profile(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
    ) -> None:
        user_a_id, client_a = student_a
        _user_b_id, client_b = student_b
        admit_student(admin_client, user_a_id)
        client_a.table("student_profiles").insert(
            {"id": user_a_id, "current_class": "Class 10", "language": "en"}
        ).execute()

        result = (
            client_b.table("student_profiles")
            .update({"current_class": "Class 12"})
            .eq("id", user_a_id)
            .execute()
        )
        assert result.data == [], "student B's update must affect zero rows of student A's profile"

    def test_reviewer_has_no_override_on_student_profiles(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
    ) -> None:
        """The reviewer role governs the public knowledge base, not the
        student vault (docs/SECURITY.md) — this must stay true even for a
        reviewer account."""
        user_a_id, client_a = student_a
        _reviewer_id, reviewer_client = reviewer
        admit_student(admin_client, user_a_id)
        client_a.table("student_profiles").insert(
            {"id": user_a_id, "current_class": "Class 10", "language": "en"}
        ).execute()

        seen = (
            reviewer_client.table("student_profiles").select("*").eq("id", user_a_id).execute()
        )
        assert seen.data == [], "a reviewer must not have cross-student read access"


# =====================================================================
# PUB-3 (db/migrations/0018_publish_functions.sql): review_events /
# audit_events are reviewer-readable, insert-only, and never updatable or
# deletable by any role; a saved_plans correction flag is exactly as
# private as the plan it hangs off.
# =====================================================================
@pytest.fixture
def official_source(admin_client: Client):
    """A real (non-synthetic) source — a published claim can never be
    backed by a synthetic one (0001_init.sql), and every fixture below
    needs a real published claim."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("PUB-3 RLS TEST FIXTURE (official)"),
                "official_url": "https://example.invalid/pub-3-rls-test-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


def _seed_review_event(admin: Client, claim_id: str, actor_id: str) -> dict[str, Any]:
    return (
        admin.table("review_events")
        .insert({"claim_id": claim_id, "actor_id": actor_id, "action": "published", "detail": {}})
        .execute()
        .data[0]
    )


def _seed_audit_event(admin: Client, claim_id: str, actor_id: str) -> dict[str, Any]:
    return (
        admin.table("audit_events")
        .insert(
            {
                "actor_id": actor_id,
                "action": "claim_superseded",
                "entity_type": "claim",
                "entity_id": claim_id,
                "detail": {},
            }
        )
        .execute()
        .data[0]
    )


class TestReviewAndAuditEventsAreInsertOnly:
    """Named acceptance line: "review_events and audit_events are
    provably not updatable or deletable by a reviewer (live RLS proof)".
    `publish_claim`/`supersede_claim` still write real rows here (tested
    in test_maker_checker.py) because they run SECURITY DEFINER and
    bypass RLS as the table owner — what is tested here is that the
    ordinary, RLS-scoped path everyone else uses cannot."""

    def test_guest_and_student_cannot_read_review_events(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        guest_client: Client,
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        _student_id, student_client = student_a
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": str(uuid.uuid4()),
                    "field": "verified_charges",
                    "value": 1,
                    "source_id": official_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("pub-3-rls-fixture"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                    "created_by": reviewer_id,
                }
            )
            .execute()
            .data[0]
        )
        event = _seed_review_event(admin_client, claim["id"], reviewer_id)
        try:
            seen_by_reviewer = (
                reviewer_client.table("review_events").select("*").eq("id", event["id"]).execute()
            )
            assert len(seen_by_reviewer.data) == 1

            seen_by_student = (
                student_client.table("review_events").select("*").eq("id", event["id"]).execute()
            )
            assert seen_by_student.data == [], (
                "a signed-in non-reviewer holds the raw grant, so RLS filters this to zero "
                "rows rather than erroring (DENY_EMPTY, access_matrix.py's own vocabulary)"
            )

            with pytest.raises(APIError):
                # `guest` (anon) holds NO grant at all on this table (this
                # migration's own `revoke all ... from anon` — reviewer-
                # only data, not the world-readable shape source_versions
                # has) — refused at the privilege check, before RLS is
                # even reached (DENY_ERROR, not DENY_EMPTY).
                guest_client.table("review_events").select("*").eq("id", event["id"]).execute()
        finally:
            admin_client.table("review_events").delete().eq("id", event["id"]).execute()
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()

    def test_reviewer_cannot_update_or_delete_a_review_event(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": str(uuid.uuid4()),
                    "field": "verified_charges",
                    "value": 1,
                    "source_id": official_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("pub-3-rls-fixture"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                    "created_by": reviewer_id,
                }
            )
            .execute()
            .data[0]
        )
        event = _seed_review_event(admin_client, claim["id"], reviewer_id)
        try:
            updated = (
                reviewer_client.table("review_events")
                .update({"action": "tampered"})
                .eq("id", event["id"])
                .execute()
            )
            assert updated.data == [], "RLS must reject the update as a no-op (no UPDATE policy)"

            deleted = (
                reviewer_client.table("review_events").delete().eq("id", event["id"]).execute()
            )
            assert deleted.data == [], "RLS must reject the delete as a no-op (no DELETE policy)"

            still_there = (
                admin_client.table("review_events").select("*").eq("id", event["id"]).execute()
            )
            assert len(still_there.data) == 1
            assert still_there.data[0]["action"] == "published", "the row must be untouched"
        finally:
            admin_client.table("review_events").delete().eq("id", event["id"]).execute()
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()

    def test_reviewer_cannot_insert_a_review_event_directly(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """Insert-only means via `publish_claim`/`supersede_claim` ONLY —
        a reviewer's own direct request must be refused outright, the
        same shape 0001_init.sql's `reviewers` table already has."""
        reviewer_id, reviewer_client = reviewer
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": str(uuid.uuid4()),
                    "field": "verified_charges",
                    "value": 1,
                    "source_id": official_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("pub-3-rls-fixture"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                    "created_by": reviewer_id,
                }
            )
            .execute()
            .data[0]
        )
        try:
            with pytest.raises(APIError):
                reviewer_client.table("review_events").insert(
                    {
                        "claim_id": claim["id"],
                        "actor_id": reviewer_id,
                        "action": "published",
                        "detail": {},
                    }
                ).execute()
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()

    def test_reviewer_cannot_update_or_delete_an_audit_event(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": str(uuid.uuid4()),
                    "field": "verified_charges",
                    "value": 1,
                    "source_id": official_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("pub-3-rls-fixture"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                    "created_by": reviewer_id,
                }
            )
            .execute()
            .data[0]
        )
        event = _seed_audit_event(admin_client, claim["id"], reviewer_id)
        try:
            updated = (
                admin_client.table("claims").select("id").eq("id", claim["id"]).execute()
            )
            assert updated.data  # sanity: fixture claim exists

            update_result = (
                reviewer_client.table("audit_events")
                .update({"action": "tampered"})
                .eq("id", event["id"])
                .execute()
            )
            assert update_result.data == []

            delete_result = (
                reviewer_client.table("audit_events").delete().eq("id", event["id"]).execute()
            )
            assert delete_result.data == []

            still_there = (
                admin_client.table("audit_events").select("*").eq("id", event["id"]).execute()
            )
            assert len(still_there.data) == 1
            assert still_there.data[0]["action"] == "claim_superseded"
        finally:
            admin_client.table("audit_events").delete().eq("id", event["id"]).execute()
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()


class TestSupersedeClaimFlagsPlansCrossUser:
    """Named acceptance line: "a plan flagged for student A is invisible
    to student B (live cross-user proof)". Runs the real function, over
    the real RLS-scoped clients, against a real pathway/saved_plans row —
    not an inspection of the policy text."""

    def test_flagged_plan_is_visible_only_to_its_own_student(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, _maker_client = reviewer
        checker_id, checker_client = second_reviewer
        student_a_id, client_a = student_a
        _student_b_id, client_b = student_b

        career = _career_row(admin_client)
        pathway = _pathway_row(admin_client, career["id"])
        admit_student(admin_client, student_a_id)
        plan = (
            client_a.table("saved_plans")
            .insert({"student_id": student_a_id, "pathway_id": pathway["id"]})
            .execute()
            .data[0]
        )
        assert plan["needs_review"] is False

        def claim_payload(**overrides: object) -> dict[str, Any]:
            payload = {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "fee_amount",
                "value": 1000,
                "source_id": official_source,
                "verification_date": "2026-01-01",
                "verifier": run_name("pub-3-cross-user-fixture"),
                "review_due_date": "2099-01-01",
                "status": "published",
                "created_by": maker_id,
                "reviewed_by": checker_id,
            }
            payload.update(overrides)
            return payload

        old_claim = admin_client.table("claims").insert(claim_payload()).execute().data[0]
        new_claim = (
            admin_client.table("claims").insert(claim_payload(value=1200)).execute().data[0]
        )
        try:
            result = checker_client.rpc(
                "supersede_claim", {"p_old_id": old_claim["id"], "p_new_id": new_claim["id"]}
            ).execute()
            assert result.data[0]["plans_flagged"] == 1

            # Student A sees her own flag, and only the flag columns
            # changed — the definer function's own "write only the flag
            # columns" discipline, proven from the OUTSIDE (a real
            # RLS-scoped read), not by reading the function body.
            own_view = (
                client_a.table("saved_plans").select("*").eq("id", plan["id"]).execute().data
            )
            assert len(own_view) == 1
            flagged = own_view[0]
            assert flagged["needs_review"] is True
            assert flagged["flagged_at"] is not None
            assert flagged["flagged_reason"] == "claim_superseded"
            assert flagged["student_id"] == student_a_id
            assert flagged["pathway_id"] == pathway["id"]
            assert flagged["notes"] == plan["notes"]
            assert flagged["estimated_additional_expenses"] == plan["estimated_additional_expenses"]

            # Student B cannot see student A's plan at all -- flagged or
            # not, exactly the same own-row RLS this table has always had.
            b_view = (
                client_b.table("saved_plans").select("*").eq("id", plan["id"]).execute().data
            )
            assert b_view == [], "student B must not see student A's flagged plan"
        finally:
            # audit_events.entity_id carries no cascading FK to claims
            # (0018's own header note) — must go before the claim/user
            # cleanup below, or `second_reviewer`'s teardown fails to
            # delete its own user (db/migrations/README.md's
            # "created_by/reviewed_by ... teardown ordering" gotcha).
            admin_client.table("audit_events").delete().eq("entity_id", old_claim["id"]).execute()
            admin_client.table("claims").delete().eq("id", old_claim["id"]).execute()
            admin_client.table("claims").delete().eq("id", new_claim["id"]).execute()
            admin_client.table("saved_plans").delete().eq("id", plan["id"]).execute()
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()
