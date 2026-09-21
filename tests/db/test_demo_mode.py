"""Live tests for db/migrations/0007_demo_mode.sql (DATA-12).

The one property this whole file exists to defend: **demo mode must
never make a real, non-synthetic draft visible.** Everything else here
is supporting detail.

`claims_select_demo_synthetic` ANDs three conditions — demo mode on,
status `in_review`, Source `synthetic`. Each of the three gets a test
that removes exactly one of them and asserts the row stays invisible, so
the suite fails if any single condition is ever dropped from the policy,
not only if all three are.

Every assertion about what a guest/student can see runs as a real
anon-key or user-authenticated client. `admin_client` (service_role)
appears only to seed rows and to flip the flag — the one thing that is
supposed to be able to write `app_settings` — never to make an assertion
about visibility, which would bypass the RLS being tested.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from postgrest.exceptions import APIError
from supabase import Client

from tests.db.conftest import run_name

TODAY = date.today()
DUE = TODAY + timedelta(days=365)


# --------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    """A real (non-synthetic) source. The whole point of several tests
    below is that a draft backed by THIS never becomes visible, however
    demo mode is set."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("DEMO-MODE TEST FIXTURE (official)"),
                "official_url": "https://example.invalid/demo-mode-official",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


@pytest.fixture
def demo_mode_on(admin_client: Client) -> Iterator[None]:
    """Turn the database flag on for one test, then put it back.

    Restores in a `finally` rather than trusting the test body, because
    leaving this on would silently widen what every LATER test in the
    session can see — the kind of shared-state leak that turns one bug
    into a suite-wide mystery.
    """
    admin_client.table("app_settings").update({"demo_mode": True}).eq("id", True).execute()
    try:
        yield
    finally:
        admin_client.table("app_settings").update({"demo_mode": False}).eq("id", True).execute()


def _claim_payload(source_id: str, status: str, **overrides: object) -> dict:
    payload: dict = {
        "entity_type": "Pathway",
        "entity_id": str(uuid.uuid4()),
        "field": "verified_charges",
        "value": 50000,
        "source_id": source_id,
        "verification_date": TODAY.isoformat(),
        "verifier": run_name("demo-mode-test-fixture"),
        "review_due_date": DUE.isoformat(),
        "status": status,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def seeded_claims(
    admin_client: Client, synthetic_source: str, official_source: str
) -> Iterator[dict[str, str]]:
    """One claim of each shape that matters, seeded by service_role.

    service_role is exempt from 0003's `enforce_claims_workflow` trigger
    (that migration's own documented carve-out), which is what lets this
    seed rows straight into `in_review`/`superseded` instead of walking
    the whole draft -> review cycle just to set up a visibility test.
    It is NOT exempt from 0001's synthetic-publish trigger — see
    `TestSyntheticPublishTriggerStillIntact` below, which relies on
    exactly that.
    """
    rows = {
        "synthetic_in_review": _claim_payload(synthetic_source, "in_review"),
        "synthetic_draft": _claim_payload(synthetic_source, "draft"),
        "synthetic_superseded": _claim_payload(synthetic_source, "superseded"),
        "official_in_review": _claim_payload(official_source, "in_review"),
        "official_draft": _claim_payload(official_source, "draft"),
        "official_published": _claim_payload(official_source, "published"),
    }
    created = {
        key: admin_client.table("claims").insert(payload).execute().data[0]["id"]
        for key, payload in rows.items()
    }
    try:
        yield created
    finally:
        for claim_id in created.values():
            admin_client.table("claims").delete().eq("id", claim_id).execute()


def _visible_ids(client: Client, claim_ids: dict[str, str]) -> set[str]:
    """Which of the seeded claims this client can actually SELECT."""
    result = client.table("claims").select("id").in_("id", list(claim_ids.values())).execute()
    return {row["id"] for row in result.data}


def _visible_keys(client: Client, claim_ids: dict[str, str]) -> set[str]:
    """The same, as the readable fixture key names."""
    visible = _visible_ids(client, claim_ids)
    return {key for key, claim_id in claim_ids.items() if claim_id in visible}


# --------------------------------------------------------------------
# demo_mode() itself
# --------------------------------------------------------------------


class TestDemoModeFunction:
    def test_defaults_to_off(self, guest_client: Client) -> None:
        """The seeded row is explicitly false, and `demo_mode()`
        coalesces a missing row to false as well — two independent
        reasons the answer is "off" unless somebody turned it on."""
        assert guest_client.rpc("demo_mode", {}).execute().data is False

    def test_a_guest_may_call_it(self, guest_client: Client) -> None:
        """Anonymous callers need the answer so the Explore screen can
        show its sample-data banner (app/api/explore.py). The flag's
        value is not sensitive; the TABLE is, and stays unreadable."""
        assert guest_client.rpc("demo_mode", {}).execute().data in (True, False)

    def test_reflects_the_flag_when_on(
        self, guest_client: Client, demo_mode_on: None
    ) -> None:
        assert guest_client.rpc("demo_mode", {}).execute().data is True


# --------------------------------------------------------------------
# app_settings is owner-writable only
# --------------------------------------------------------------------


class TestAppSettingsIsNotReachable:
    """RLS with zero policies, plus a table-level revoke. Either alone
    would deny; both are present because this is a kill switch."""

    def test_guest_cannot_read_it(self, guest_client: Client) -> None:
        with pytest.raises(APIError):
            guest_client.table("app_settings").select("*").execute()

    def test_guest_cannot_flip_it(self, guest_client: Client) -> None:
        with pytest.raises(APIError):
            guest_client.table("app_settings").update({"demo_mode": True}).eq(
                "id", True
            ).execute()

    def test_student_cannot_read_it(self, student_a: tuple[str, Client]) -> None:
        _, client = student_a
        with pytest.raises(APIError):
            client.table("app_settings").select("*").execute()

    def test_student_cannot_flip_it(self, student_a: tuple[str, Client]) -> None:
        """The acceptance line verbatim: "authenticated users cannot flip
        demo_mode"."""
        _, client = student_a
        with pytest.raises(APIError):
            client.table("app_settings").update({"demo_mode": True}).eq("id", True).execute()

    def test_student_cannot_insert_a_second_row(
        self, student_a: tuple[str, Client]
    ) -> None:
        """Belt and braces on the single-row invariant: even if the
        update path were somehow opened, adding a second row with
        demo_mode=true must not be a way in."""
        _, client = student_a
        with pytest.raises(APIError):
            client.table("app_settings").insert({"id": True, "demo_mode": True}).execute()

    def test_a_reviewer_cannot_flip_it_either(
        self, reviewer: tuple[str, Client]
    ) -> None:
        """A reviewer is trusted to publish claims, not to change how the
        whole deployment behaves. `is_reviewer()` appears nowhere in this
        migration, deliberately."""
        _, client = reviewer
        with pytest.raises(APIError):
            client.table("app_settings").update({"demo_mode": True}).eq("id", True).execute()

    def test_the_single_row_invariant_holds_for_the_owner_too(
        self, admin_client: Client
    ) -> None:
        """`id boolean primary key check (id)` means there is exactly one
        possible key, so a second row is a PK violation rather than a
        silently-ignored row `demo_mode()` might or might not pick."""
        with pytest.raises(APIError):
            admin_client.table("app_settings").insert(
                {"id": True, "demo_mode": True}
            ).execute()


# --------------------------------------------------------------------
# Visibility with demo mode OFF (the default, fail-closed state)
# --------------------------------------------------------------------


class TestDemoModeOff:
    def test_guest_sees_zero_in_review_claims(
        self, guest_client: Client, seeded_claims: dict[str, str]
    ) -> None:
        """Acceptance, verbatim: "With demo_mode false anon sees zero
        in_review claims"."""
        assert _visible_keys(guest_client, seeded_claims) == {"official_published"}

    def test_guest_sees_no_synthetic_row_at_all(
        self, guest_client: Client, seeded_claims: dict[str, str]
    ) -> None:
        visible = _visible_keys(guest_client, seeded_claims)
        assert not any(key.startswith("synthetic") for key in visible)

    def test_student_sees_zero_in_review_claims(
        self, student_a: tuple[str, Client], seeded_claims: dict[str, str]
    ) -> None:
        _, client = student_a
        assert _visible_keys(client, seeded_claims) == {"official_published"}


# --------------------------------------------------------------------
# Visibility with demo mode ON — the three ANDed conditions
# --------------------------------------------------------------------


class TestDemoModeOn:
    def test_guest_sees_the_synthetic_in_review_claim(
        self, guest_client: Client, seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        assert "synthetic_in_review" in _visible_keys(guest_client, seeded_claims)

    def test_guest_sees_ONLY_synthetic_in_review_plus_published(
        self, guest_client: Client, seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        """Acceptance, verbatim: "with true anon sees only
        synthetic-sourced in_review claims, never official drafts".

        An exact set comparison, not a membership check: the failure this
        guards against is the policy accidentally widening, and a
        membership check cannot see a row that should not be there.
        """
        assert _visible_keys(guest_client, seeded_claims) == {
            "synthetic_in_review",
            "official_published",
        }

    def test_an_official_draft_never_becomes_visible(
        self, guest_client: Client, seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        """Condition 3 (source must be synthetic). Drop it from the
        policy and this is the test that fails."""
        visible = _visible_keys(guest_client, seeded_claims)
        assert "official_in_review" not in visible
        assert "official_draft" not in visible

    def test_a_synthetic_draft_is_not_demo_material(
        self, guest_client: Client, seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        """Condition 2 (status must be `in_review`). A claim nobody has
        even submitted for review is not sample content to show off —
        widening this to "any non-published status" is the mistake this
        test exists to catch."""
        assert "synthetic_draft" not in _visible_keys(guest_client, seeded_claims)

    def test_a_synthetic_superseded_claim_stays_hidden(
        self, guest_client: Client, seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        assert "synthetic_superseded" not in _visible_keys(guest_client, seeded_claims)

    def test_a_signed_in_student_still_never_sees_a_real_draft(
        self, student_a: tuple[str, Client], seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        """Demo mode is deployment-wide, not role-scoped, so a student
        sees the sample rows too — but the guarantee that matters is
        unchanged for them as well."""
        visible = _visible_keys(client=student_a[1], claim_ids=seeded_claims)
        assert "official_in_review" not in visible
        assert "official_draft" not in visible

    def test_student_b_sees_the_same_as_student_a(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        seeded_claims: dict[str, str],
        demo_mode_on: None,
    ) -> None:
        """Cross-user line (CLAUDE.md: guest / A / B / reviewer tested
        every time a policy changes). This policy is not user-scoped, so
        A and B must agree exactly — a difference would mean it had
        picked up some per-user dependency it has no business having."""
        assert _visible_keys(student_a[1], seeded_claims) == _visible_keys(
            student_b[1], seeded_claims
        )

    def test_a_reviewer_still_sees_everything(
        self, reviewer: tuple[str, Client], seeded_claims: dict[str, str], demo_mode_on: None
    ) -> None:
        """0001's `claims_select_published` ("... or is_reviewer()") is
        untouched; this migration only ever ORs an extra permissive
        policy alongside it, so a reviewer's view cannot narrow."""
        _, client = reviewer
        assert _visible_keys(client, seeded_claims) == set(seeded_claims)


class TestTurningItBackOffCloses:
    def test_the_window_closes_again(
        self, guest_client: Client, seeded_claims: dict[str, str], admin_client: Client
    ) -> None:
        """Not a one-way door: the flag is the whole control, so turning
        it off must immediately hide the sample rows again (`demo_mode()`
        is `stable`, not `immutable` — it is re-read per statement, never
        constant-folded at policy-creation time, which is the specific
        bug this test would catch)."""
        admin_client.table("app_settings").update({"demo_mode": True}).eq("id", True).execute()
        try:
            assert "synthetic_in_review" in _visible_keys(guest_client, seeded_claims)
        finally:
            admin_client.table("app_settings").update({"demo_mode": False}).eq(
                "id", True
            ).execute()
        assert "synthetic_in_review" not in _visible_keys(guest_client, seeded_claims)


# --------------------------------------------------------------------
# The 0001 guarantee this migration must not have weakened
# --------------------------------------------------------------------


class TestSyntheticPublishTriggerStillIntact:
    """CLAUDE.md non-negotiable, and DATA-8's own risk line: "Never
    weaken the 0001 synthetic trigger to make the demo work." 0007 does
    not touch it; these tests are what proves that claim rather than
    asserting it in a comment."""

    def test_service_role_cannot_publish_a_synthetic_claim(
        self, admin_client: Client, synthetic_source: str
    ) -> None:
        """Not even the owner connection. `forbid_publishing_synthetic_
        claims()` (0001) has no service_role carve-out, unlike 0003's
        workflow trigger — deliberately."""
        with pytest.raises(APIError):
            admin_client.table("claims").insert(
                _claim_payload(synthetic_source, "published")
            ).execute()

    def test_cannot_publish_a_synthetic_claim_with_demo_mode_on(
        self, admin_client: Client, synthetic_source: str, demo_mode_on: None
    ) -> None:
        """Demo mode is not a back door to publishing: it widens what can
        be READ, and changes nothing about what can be WRITTEN."""
        with pytest.raises(APIError):
            admin_client.table("claims").insert(
                _claim_payload(synthetic_source, "published")
            ).execute()

    def test_a_synthetic_in_review_claim_cannot_be_promoted_to_published(
        self, admin_client: Client, synthetic_source: str, demo_mode_on: None
    ) -> None:
        """The path an operator would actually reach for: the row is
        already there and visible on the demo, now "just publish it"."""
        claim_id = (
            admin_client.table("claims")
            .insert(_claim_payload(synthetic_source, "in_review"))
            .execute()
            .data[0]["id"]
        )
        try:
            with pytest.raises(APIError):
                admin_client.table("claims").update({"status": "published"}).eq(
                    "id", claim_id
                ).execute()
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()
