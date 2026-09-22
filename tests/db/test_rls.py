"""RLS access-matrix tests: guest / student A / student B / reviewer.

Exit proof for tasks/BCI-002.md (M1). Every assertion here runs as the
restricted role a real request would use — never as the database owner,
which bypasses RLS and would hide the very bug this file exists to catch.
"""

from __future__ import annotations

from typing import Any

from supabase import Client

from tests.db.conftest import admit_student, run_name


def _career_row(admin: Client) -> dict[str, Any]:
    result = (
        admin.table("careers")
        .insert({"name": run_name("RLS test career (SYNTHETIC)")})
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
