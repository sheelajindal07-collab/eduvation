"""Integration tests for GET/POST /eligibility against the real database.

Seeds eligibility-shaped claims on a real pathway via the service-role
admin client, then checks the actual FastAPI route builds the right
criteria from them and returns the right outcome — end to end, not
mocked.

RULES-8 adds the second rule source: a published `rule_key` claim naming
a registered `RuleSet` from `app/rules/exams/` (whose thresholds live in
a reviewed case-table JSON in git, not in any database row —
docs/CONTRACTS.md "Rule approval lives in git JSON"). Both sources are
exercised here against real rows, including the cases where the data
itself is wrong.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.api.eligibility import RULE_KEY_FIELD
from app.api.eligibility import today_ist as _today_ist
from app.main import app
from tests.db.conftest import run_name

client = TestClient(app)

# The rule set these tests point a `rule_key` claim at. Read from the
# case table rather than re-typed, so this file can never drift from the
# reviewed JSON that actually defines the rule set (the same reason
# app/rules/exams/neet_ug.py holds no literal fact values either).
_NEET_UG_CASE_TABLE = json.loads(
    (Path(__file__).resolve().parents[2] / "tests/unit/rules/cases/neet_ug.json").read_text(
        encoding="utf-8"
    )
)
_NEET_UG_EXAM_KEY: str = _NEET_UG_CASE_TABLE["exam_key"]
_NEET_UG_CYCLE: str = _NEET_UG_CASE_TABLE["cycle"]
_NEET_UG_JURISDICTION: str = _NEET_UG_CASE_TABLE["jurisdiction"]
_NEET_UG_RULE_VERSION: str = _NEET_UG_CASE_TABLE["rule_version"]
_NEET_UG_MIN_AGE: int = _NEET_UG_CASE_TABLE["facts"]["minimum_age"]
_NEET_UG_MIN_AGE_CUTOFF = date.fromisoformat(
    _NEET_UG_CASE_TABLE["facts"]["minimum_age_cutoff"]
)

# QA-3: these two literals are asserted verbatim further down (not read
# back off the fixture's own returned dict, unlike every career/pathway
# name in this file), so each is tagged exactly once, here, and reused —
# never re-typed — everywhere it must match.
_ELIGIBILITY_SOURCE_NAME = run_name("API TEST ELIGIBILITY SOURCE (fixture)")
_MALICIOUS_SOURCE_NAME = run_name("MALICIOUS SOURCE (test)")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def eligibility_pathway(
    admin_client: Client,
) -> Iterator[dict[str, Any]]:
    """A career + pathway with a real official source and four
    eligibility claims published: minimum_age=17, maximum_age=25,
    minimum_marks_percentage=50, required_subjects=Physics,Chemistry,Biology.
    """
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": _ELIGIBILITY_SOURCE_NAME,
                "official_url": "https://example.invalid/eligibility-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Eligibility test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Eligibility test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_api_eligibility.py",
            }
        )
        .execute()
        .data[0]
    )

    claim_specs = [
        ("minimum_age", "17"),
        ("maximum_age", "25"),
        ("minimum_marks_percentage", "50"),
        ("required_subjects", "Physics,Chemistry,Biology"),
    ]
    claims = []
    for field, value in claim_specs:
        claims.append(
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": field,
                    "value": value,
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )

    yield {"career": career, "pathway": pathway, "source": official_source, "claims": claims}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestEligibilityEndpoint:
    def test_eligible_student_meets(self, eligibility_pathway: dict[str, Any]) -> None:
        # SEC-5: age/marks_percentage/subjects_studied are personal
        # inputs, POST-only (docs/CONTRACTS.md) -- never a query param.
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry,Biology,English",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert len(body["criteria"]) == 4
        assert all(c["source_claim_id"] is not None for c in body["criteria"])
        # ux-qa-reviewer finding, 2026-09-19: a bare claim UUID has
        # nowhere to get "source authority ... official link,
        # verification date" from (docs/UI.md) -- now resolved.
        assert all(c["source_authority"] == _ELIGIBILITY_SOURCE_NAME for c in body["criteria"])
        assert all(
            c["source_url"] == "https://example.invalid/eligibility-source"
            for c in body["criteria"]
        )
        assert all(c["verification_date"] == "2026-09-01" for c in body["criteria"])

    def test_missing_subject_gives_does_not_meet(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry",  # no Biology
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "does_not_meet"

    def test_no_student_facts_gives_insufficient_information(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/eligibility", params={"pathway_id": eligibility_pathway["pathway"]["id"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "insufficient_information"

    def test_get_ignores_a_personal_field_smuggled_into_the_query_string(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        """SEC-5: GET /eligibility only ever declares `pathway_id` --
        an `age` tacked onto the query string anyway (a hand-edited or
        legacy shared link) has no route parameter to bind to and is
        silently unused, never read into the eligibility check. This is
        the structural version of "GET never accepts a personal input":
        it isn't validated away, there is simply nothing on this route
        that would ever look at it."""
        response = client.get(
            "/eligibility",
            params={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry,Biology,English",
            },
        )
        assert response.status_code == 200
        body = response.json()
        # Every criterion is still unevaluated -- the smuggled fields
        # were never read, so this is identical to the pathway_id-only
        # GET case, not a partial or accidental "meets".
        assert body["outcome"] == "insufficient_information"

    def test_pathway_with_no_eligibility_claims_never_reports_meets(
        self, admin_client: Client
    ) -> None:
        """RULES-8 **behaviour change**, and the reason this route now
        goes through `app.rules.ruleset.evaluate_ruleset` instead of
        `evaluate_eligibility` alone.

        This test used to assert the opposite (`outcome == "meets"`, on
        the reasoning that a pathway with no published rules has nothing
        to fail, so `meets` is "vacuously" true). docs/CONTRACTS.md
        "Three eligibility outcomes" settles it the other way, and
        `app/rules/ruleset.py` was written to it: "a pathway with no
        published rules returns insufficient_information +
        no_verified_rules — never not_eligible". "Nothing failed" and
        "you meet the published requirements" are different facts, and a
        student reading the second when we mean the first is being told
        they are eligible for something nobody has verified anything
        about.

        Note `no_verified_rules` is what distinguishes this from an
        ordinary `insufficient_information` (which means "tell us more
        about yourself"): here, nothing the student could type would
        change the answer.
        """
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("No-criteria test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("No-criteria test pathway (SYNTHETIC)"),
                    "description": "No eligibility claims at all",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get("/eligibility", params={"pathway_id": pathway["id"]})
            assert response.status_code == 200
            body = response.json()
            assert body["outcome"] == "insufficient_information"
            assert body["no_verified_rules"] is True
            assert body["criteria"] == []
            # Not a named rule set, so there is no cycle/version/
            # jurisdiction to report -- and nothing invented in their
            # place.
            assert body["rule_version"] is None
            assert body["cycle"] is None
            assert body["jurisdiction"] is None

        finally:
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()

    def test_a_full_pass_still_meets_and_is_not_marked_stale(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        """The other half of the guard above: making an empty rule set
        fail safe must not make a REAL pass fail too. The fixture's four
        claims were verified this month, so nothing is stale and the
        would-be `meets` is not downgraded."""
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry,Biology",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert body["no_verified_rules"] is False
        assert body["stale"] is False
        assert body["not_checked"] == []
        # Server-computed Asia/Kolkata date (docs/CONTRACTS.md "Duration,
        # dates, cycle, DOB") -- present, and never taken from a client.
        assert body["as_of"] == _today_ist().isoformat()

    def test_malformed_pathway_id_is_422_not_500(self) -> None:
        """Reproduced live before the fix: `entity_id` is a `uuid`
        column (db/migrations/0001_init.sql), so an unvalidated garbled
        id reached PostgREST raw, came back 400 (Postgres 22P02) and
        propagated as an unhandled 500 on BOTH verbs. Same guard
        `app/api/compare.py` and `app/web/requirements_pages.py` already
        had; this route never got it."""
        get_response = client.get("/eligibility", params={"pathway_id": "not-a-uuid-at-all"})
        assert get_response.status_code == 422
        post_response = client.post(
            "/eligibility", json={"pathway_id": "not-a-uuid-at-all", "age": 18}
        )
        assert post_response.status_code == 422


class TestDangerousSourceUrlSchemeIsNeverRendered:
    """Security-review finding, 2026-09-20: nothing validated the URL
    scheme on Source.official_url before it reached a template's
    href="{{ ... }}" -- a javascript:/data: URI would render as a fully
    clickable, script-executing link on the evidence badge. Confirmed
    live and fixed with the same "degrade to unavailable" pattern
    app/planning/comparison.py's field_value_for() also uses -- this
    route builds source_url independently, so that fix doesn't cover it."""

    def test_javascript_scheme_source_url_is_never_returned(
        self, admin_client: Client
    ) -> None:
        dangerous_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": _MALICIOUS_SOURCE_NAME,
                    "official_url": "javascript:alert(document.cookie)",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("Dangerous-URL test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("Dangerous-URL test pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_api_eligibility.py",
                }
            )
            .execute()
            .data[0]
        )
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "minimum_age",
                    "value": "17",
                    "source_id": dangerous_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.post(
                "/eligibility", json={"pathway_id": pathway["id"], "age": 18}
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["criteria"]) == 1
            # The authority name (plain text, safe) still shows; the
            # dangerous URL itself must never reach the response.
            assert body["criteria"][0]["source_authority"] == _MALICIOUS_SOURCE_NAME
            assert body["criteria"][0]["source_url"] is None
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()
            admin_client.table("sources").delete().eq("id", dangerous_source["id"]).execute()


@pytest.fixture
def pathway_with_a_draft_criterion(
    admin_client: Client,
) -> Iterator[dict[str, Any]]:
    """One PUBLISHED minimum_age=17 claim, plus a DRAFT
    minimum_marks_percentage=90 claim never approved by anyone.
    db/migrations/0001_init.sql's `claims_select_published` policy lets
    a reviewer's own RLS-scoped client SELECT the draft row too (so they
    can review it) — that must not mean a reviewer calling /eligibility
    gets an outcome computed from it."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("API TEST DRAFT-CRITERION SOURCE (fixture)"),
                "official_url": "https://example.invalid/draft-criterion-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Draft-criterion test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Draft-criterion test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_api_eligibility.py",
            }
        )
        .execute()
        .data[0]
    )
    claims = [
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "minimum_age",
                "value": "17",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0],
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "minimum_marks_percentage",
                "value": "90",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "draft",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0],
    ]

    yield {"pathway": pathway}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestDraftClaimsNeverAffectEligibilityOutcome:
    """Regression test for a maker-checker bypass: _criteria_from_claims
    used to build a criterion from ANY row the caller's client could
    SELECT, trusting RLS alone to mean "this is a published fact" --
    true for a guest/student, false for a reviewer, who can also SELECT
    drafts. A student scoring 72% would fail a published-only check here
    (only minimum_age=17 exists) but would wrongly fail an unpublished
    minimum_marks_percentage=90 check if the draft leaked through."""

    def test_reviewer_gets_the_same_outcome_as_a_guest_draft_ignored(
        self,
        reviewer: tuple[str, Client],
        pathway_with_a_draft_criterion: dict[str, Any],
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": pathway_with_a_draft_criterion["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
            },
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert len(body["criteria"]) == 1
        assert body["criteria"][0]["name"] == "minimum_age"


# ---------------------------------------------------------------------
# RULES-8: the named-RuleSet path.
# ---------------------------------------------------------------------

# A student who turns exactly the rule set's minimum age ON its cutoff
# date, and one born a single day later (so they are one year short on
# that date). Both derived from the case table, never re-typed -- the
# point of these two is that a DOB one day apart flips a real outcome,
# which the pre-RULES-8 integer-age path could not express at all.
_DOB_JUST_OLD_ENOUGH = _NEET_UG_MIN_AGE_CUTOFF.replace(
    year=_NEET_UG_MIN_AGE_CUTOFF.year - _NEET_UG_MIN_AGE
)
_DOB_ONE_DAY_TOO_YOUNG = _DOB_JUST_OLD_ENOUGH + timedelta(days=1)
_NEET_UG_PASSING_SUBJECTS = ",".join(
    group[0] for group in _NEET_UG_CASE_TABLE["facts"]["required_subject_groups"]
)


def _seed_rule_key_pathway(
    admin_client: Client,
    *,
    label: str,
    cycle: str,
    extra_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A career + pathway + official source + ONE published `rule_key`
    claim pointing at a registered `RuleSet`, plus whatever extra claims
    a test wants alongside it.

    The claim's own `academic_cycle`/`jurisdiction` columns (SCOPE-3,
    db/migrations/0008) complete the registry lookup -- that is the
    convention RULES-8 established rather than packing three values into
    one string, because `academic_cycle` is already the contract's cycle
    LABEL and needs no parsing.
    """
    source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name(f"API TEST {label} SOURCE (fixture)"),
                "official_url": "https://example.invalid/rule-key-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name(f"{label} test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name(f"{label} test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_api_eligibility.py",
            }
        )
        .execute()
        .data[0]
    )
    specs: list[dict[str, Any]] = [
        {
            "field": RULE_KEY_FIELD,
            "value": _NEET_UG_EXAM_KEY,
            "status": "published",
            "academic_cycle": cycle,
            "jurisdiction": _NEET_UG_JURISDICTION,
        },
        *(extra_claims or []),
    ]
    claims = [
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "source_id": source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "review_due_date": "2099-01-01",
                **spec,
            }
        )
        .execute()
        .data[0]
        for spec in specs
    ]
    return {"career": career, "pathway": pathway, "source": source, "claims": claims}


def _purge(admin_client: Client, seeded: dict[str, Any]) -> None:
    for claim in seeded["claims"]:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", seeded["pathway"]["id"]).execute()
    admin_client.table("careers").delete().eq("id", seeded["career"]["id"]).execute()
    admin_client.table("sources").delete().eq("id", seeded["source"]["id"]).execute()


@pytest.fixture
def rule_key_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A pathway whose published `rule_key` claim names the registered
    NEET-UG rule set for its own cycle -- PLUS a published
    `minimum_marks_percentage` of 90 that the named rule set does not
    include.

    That second claim is the point: once a rule set is named, the
    registry decides the criteria, so a marks threshold that happens to
    be published on the same pathway must NOT quietly join them. A
    reviewed rule set that says nothing about marks is a decision (see
    the NEET-UG case table's `not_checked` entries and its source note),
    not an omission to be filled in from whatever else is lying around.
    """
    seeded = _seed_rule_key_pathway(
        admin_client,
        label="RULE-KEY",
        cycle=_NEET_UG_CYCLE,
        extra_claims=[
            {"field": "minimum_marks_percentage", "value": "90", "status": "published"}
        ],
    )
    yield seeded
    _purge(admin_client, seeded)


class TestNamedRuleSetViaARuleKeyClaim:
    """The registry lookup itself: a published `rule_key` claim ->
    `app.rules.ruleset.get_rule_set` -> `evaluate_ruleset`.

    These tests assume a non-production `APP_ENV` (`.env.test` ships
    `development`), because `discover_rule_sets` deliberately HIDES a
    rule set whose case table has no `reviewed_by`/`reviewed_on` from a
    production registry -- and none of the three shipped exam modules is
    human-reviewed yet (RULES-12). In production the same request would
    correctly report `no_verified_rules`; that is the point of the flag,
    not a gap in these tests.
    """

    def test_date_of_birth_drives_the_named_rule_sets_cutoff_criterion(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        """A real DOB-cutoff check, which the integer `age` input cannot
        express (app/rules/criteria_dates.py's whole reason for
        existing). The response also carries the applied rule set's
        identity, so a client can say WHICH cycle's rules this was."""
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": rule_key_pathway["pathway"]["id"],
                "date_of_birth": _DOB_JUST_OLD_ENOUGH.isoformat(),
                "subjects_studied": _NEET_UG_PASSING_SUBJECTS,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["rule_version"] == _NEET_UG_RULE_VERSION
        assert body["cycle"] == _NEET_UG_CYCLE
        assert body["jurisdiction"] == _NEET_UG_JURISDICTION
        assert body["no_verified_rules"] is False
        assert body["stale"] is False
        assert body["outcome"] == "meets"

        by_name = {c["name"]: c for c in body["criteria"]}
        assert by_name["minimum_age_on_date"]["outcome"] == "meets"
        # The named rule set decides the criteria: the pathway's own
        # published minimum_marks_percentage=90 claim is NOT folded in.
        assert "minimum_marks_percentage" not in by_name

        # What the reviewed rule set says it deliberately does not check
        # travels too -- a short criteria list must never read as "these
        # are all the requirements there are".
        assert len(body["not_checked"]) == len(_NEET_UG_CASE_TABLE["not_checked"])

    def test_a_date_of_birth_one_day_later_does_not_meet_the_cutoff(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        """One day of difference in the DOB flips the outcome, because
        the rule is "completed N years as on <cutoff>", not "is N years
        old today". Proves the submitted `date_of_birth` really reaches
        the rule engine rather than being accepted and ignored."""
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": rule_key_pathway["pathway"]["id"],
                "date_of_birth": _DOB_ONE_DAY_TOO_YOUNG.isoformat(),
                "subjects_studied": _NEET_UG_PASSING_SUBJECTS,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "does_not_meet"
        by_name = {c["name"]: c for c in body["criteria"]}
        assert by_name["minimum_age_on_date"]["outcome"] == "does_not_meet"

    def test_no_date_of_birth_is_insufficient_information_never_a_rejection(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        """The single most safety-critical rule in the engine, still true
        through the registry path: an unknown input is
        `insufficient_information`, NEVER `does_not_meet`."""
        response = client.get(
            "/eligibility", params={"pathway_id": rule_key_pathway["pathway"]["id"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "insufficient_information"
        # There ARE verified rules here -- the student just hasn't said
        # anything about themselves yet. The two states are distinct.
        assert body["no_verified_rules"] is False
        assert all(c["outcome"] == "insufficient_information" for c in body["criteria"])

    def test_a_rule_key_for_an_unregistered_cycle_is_never_answered_with_another(
        self, admin_client: Client
    ) -> None:
        """`get_rule_set`'s exact-match guard, through the route: a
        `rule_key` naming a real registered exam but a cycle nothing is
        registered for must report `no_verified_rules`, NOT quietly serve
        the one cycle that does exist. Serving last year's age cutoff
        under this year's label is the failure mode this whole registry
        exists to prevent."""
        seeded = _seed_rule_key_pathway(admin_client, label="STALE-CYCLE", cycle="1999")
        try:
            response = client.post(
                "/eligibility",
                json={
                    "pathway_id": seeded["pathway"]["id"],
                    "date_of_birth": _DOB_JUST_OLD_ENOUGH.isoformat(),
                    "subjects_studied": _NEET_UG_PASSING_SUBJECTS,
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["outcome"] == "insufficient_information"
            assert body["no_verified_rules"] is True
            assert body["criteria"] == []
            assert body["rule_version"] == "unregistered"
            # The cycle that was ASKED for is reported back, so it is
            # visible that the request was understood and simply has no
            # approved rule set.
            assert body["cycle"] == "1999"
        finally:
            _purge(admin_client, seeded)

    def test_a_rule_key_claim_with_no_cycle_is_declared_not_checked(
        self, admin_client: Client
    ) -> None:
        """More bad data already in the database: a published `rule_key`
        with no `academic_cycle` cannot be resolved, because
        `get_rule_set` matches an exact cycle and never a "closest" one.

        It does NOT silently fall back to whatever generic
        eligibility-shaped claims happen to be on the pathway (here, a
        `minimum_age` of 17 that the student would pass): content saying
        "use the NEET-UG rules" must never be answered with a different
        set of criteria. The `rule_key` field itself is declared
        `not_checked` so the reason is visible rather than inferred from
        an empty criteria list.
        """
        seeded = _seed_rule_key_pathway(
            admin_client,
            label="NO-CYCLE-RULE-KEY",
            cycle=_NEET_UG_CYCLE,
            extra_claims=[{"field": "minimum_age", "value": "17", "status": "published"}],
        )
        admin_client.table("claims").update({"academic_cycle": None}).eq(
            "id", seeded["claims"][0]["id"]
        ).execute()
        try:
            response = client.post(
                "/eligibility", json={"pathway_id": seeded["pathway"]["id"], "age": 18}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["outcome"] == "insufficient_information"
            assert body["no_verified_rules"] is True
            assert body["criteria"] == []
            assert [n["name"] for n in body["not_checked"]] == [RULE_KEY_FIELD]
        finally:
            _purge(admin_client, seeded)

    @pytest.mark.parametrize(
        ("later_cycle", "expected_cycle", "expected_rule_version"),
        [
            (_NEET_UG_CYCLE, _NEET_UG_CYCLE, _NEET_UG_RULE_VERSION),
            ("1999", "1999", "unregistered"),
        ],
    )
    def test_two_published_rule_key_claims_resolve_deterministically(
        self,
        admin_client: Client,
        later_cycle: str,
        expected_cycle: str,
        expected_rule_version: str,
    ) -> None:
        """Nothing in the schema stops a pathway having two published
        claims on one field (there is no unique index, which is why
        docs/CONTRACTS.md "Entity vocabulary" has a rule for the case),
        and taking whichever row PostgREST returned first would mean the
        same pathway could be evaluated against two different cycles'
        rules on two consecutive requests.

        Both parameter sets insert the SAME two claims in the SAME order
        and differ only in which one carries the later
        `verification_date` — so an implementation that just took the
        first row would return one identical answer for both and fail
        one of them.
        """
        seeded = _seed_rule_key_pathway(
            admin_client,
            label="TWO-RULE-KEYS",
            cycle="1999",
            extra_claims=[
                {
                    "field": RULE_KEY_FIELD,
                    "value": _NEET_UG_EXAM_KEY,
                    "status": "published",
                    "academic_cycle": _NEET_UG_CYCLE,
                    "jurisdiction": _NEET_UG_JURISDICTION,
                }
            ],
        )
        wanted = next(
            c for c in seeded["claims"] if c["academic_cycle"] == later_cycle
        )
        admin_client.table("claims").update({"verification_date": "2026-09-05"}).eq(
            "id", wanted["id"]
        ).execute()
        try:
            response = client.get(
                "/eligibility", params={"pathway_id": seeded["pathway"]["id"]}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["cycle"] == expected_cycle
            assert body["rule_version"] == expected_rule_version
        finally:
            _purge(admin_client, seeded)


@pytest.fixture
def pathway_with_a_draft_rule_key(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A DRAFT `rule_key` claim (never approved by anyone) beside a
    PUBLISHED `minimum_age` claim."""
    seeded = _seed_rule_key_pathway(
        admin_client,
        label="DRAFT-RULE-KEY",
        cycle=_NEET_UG_CYCLE,
        extra_claims=[{"field": "minimum_age", "value": "17", "status": "published"}],
    )
    # Demote the rule_key claim the helper published to a draft: it is
    # the first spec, so the first inserted row.
    admin_client.table("claims").update({"status": "draft"}).eq(
        "id", seeded["claims"][0]["id"]
    ).execute()
    yield seeded
    _purge(admin_client, seeded)


class TestAnUnpublishedRuleKeyClaimIsIgnored:
    """RULES-8 judgement call, recorded here because it is the one place
    the behaviour is observable: an UNPUBLISHED `rule_key` claim is
    ignored entirely and the pathway falls back to its own published
    claims — it does NOT switch the response into
    `not_checked`/`no_verified_rules` on the grounds that "a rule set is
    named".

    A reviewer's RLS-scoped client can SELECT draft rows
    (`claims_select_published` is `status = 'published' or
    is_reviewer()`). Honouring a draft `rule_key` would therefore let an
    unapproved row change what a reviewer sees — here by BLANKING the
    pathway's real published criteria rather than by adding fake ones,
    but it is the same maker-checker bypass
    `TestDraftClaimsNeverAffectEligibilityOutcome` above exists to catch,
    pointed the other way. A draft is not a fact in either direction, and
    "published" is the operative word in "falls back when no `rule_key`
    is published".
    """

    def test_guest_falls_back_to_the_published_generic_claims(
        self, pathway_with_a_draft_rule_key: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={"pathway_id": pathway_with_a_draft_rule_key["pathway"]["id"], "age": 18},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert [c["name"] for c in body["criteria"]] == ["minimum_age"]
        # The generic path reports no rule-set identity rather than
        # inventing the drafted one.
        assert body["rule_version"] is None
        assert body["cycle"] is None

    def test_reviewer_who_can_see_the_draft_gets_the_identical_answer(
        self,
        reviewer: tuple[str, Client],
        pathway_with_a_draft_rule_key: dict[str, Any],
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/eligibility",
            json={"pathway_id": pathway_with_a_draft_rule_key["pathway"]["id"], "age": 18},
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert [c["name"] for c in body["criteria"]] == ["minimum_age"]
        assert body["no_verified_rules"] is False


class TestAMalformedClaimValueDegradesOnlyThatCriterion:
    """Bad data ALREADY IN the database (not a bad request): a published
    `minimum_age` whose stored value is the word "seventeen" used to hit
    `int(row["value"])` and 500 the entire response — every other
    criterion on the pathway included. Same "one bad row must not kill
    the whole response" convention `app/web/reviewer/queue.py` and
    `app/planning/comparison.py` already follow.

    It degrades to a `not_checked` entry rather than to a criterion with
    an `insufficient_information` outcome, because those say different
    things: `insufficient_information` means "tell us X and we will check
    this", while an unreadable rule cannot be fixed by anything the
    student types.
    """

    @pytest.fixture
    def pathway_with_one_unreadable_claim(
        self, admin_client: Client
    ) -> Iterator[dict[str, Any]]:
        source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": run_name("API TEST MALFORMED-CLAIM SOURCE (fixture)"),
                    "official_url": "https://example.invalid/malformed-claim-source",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("Malformed-claim test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("Malformed-claim test pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_api_eligibility.py",
                }
            )
            .execute()
            .data[0]
        )
        claims = [
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "source_id": source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                    **spec,
                }
            )
            .execute()
            .data[0]
            # An unreadable number, a value in the wrong JSON shape
            # (a list where this route expects one figure), and one
            # perfectly good claim that must survive both.
            for spec in (
                {"field": "minimum_age", "value": "seventeen"},
                {"field": "minimum_marks_percentage", "value": ["fifty", "percent"]},
                {"field": "maximum_age", "value": "25"},
            )
        ]
        yield {"career": career, "pathway": pathway, "source": source, "claims": claims}
        _purge(
            admin_client,
            {"claims": claims, "pathway": pathway, "career": career, "source": source},
        )

    def test_the_good_criterion_still_answers_and_the_bad_ones_are_declared(
        self, pathway_with_one_unreadable_claim: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": pathway_with_one_unreadable_claim["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert [c["name"] for c in body["criteria"]] == ["maximum_age"]
        assert body["criteria"][0]["outcome"] == "meets"
        assert {n["name"] for n in body["not_checked"]} == {
            "minimum_age",
            "minimum_marks_percentage",
        }
        # One readable criterion, and the student passes it -- but the
        # two unreadable rules are surfaced, not silently absent.
        assert body["outcome"] == "meets"
        assert body["no_verified_rules"] is False

    def test_a_json_list_of_subjects_is_read_as_a_list_not_stringified(
        self, admin_client: Client, pathway_with_one_unreadable_claim: dict[str, Any]
    ) -> None:
        """`Claim.value` has allowed a real JSON list since RULES-3, and
        the old `str(value).split(",")` turned `["Physics", "Chemistry"]`
        into the subject names `"['Physics'"` and `"'Chemistry']"` — so a
        student who had studied both was told, in those words, that they
        were missing a subject called `['Physics'`. A wrong sentence in
        front of a student, from data that was perfectly well-formed."""
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway_with_one_unreadable_claim["pathway"]["id"],
                    "field": "required_subjects",
                    "value": ["Physics", "Chemistry"],
                    "source_id": pathway_with_one_unreadable_claim["source"]["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.post(
                "/eligibility",
                json={
                    "pathway_id": pathway_with_one_unreadable_claim["pathway"]["id"],
                    "age": 18,
                    "subjects_studied": "Physics,Chemistry,English",
                },
            )
            assert response.status_code == 200
            body = response.json()
            by_name = {c["name"]: c for c in body["criteria"]}
            assert by_name["required_subjects"]["outcome"] == "meets"
            assert "[" not in by_name["required_subjects"]["explanation"]
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()


class TestOutOfRangeInputsAreRejectedCleanly:
    """422, never 500, and never a criterion evaluated against nonsense.
    `marks_percentage` is the dangerous one: 900 would `meet` every
    published threshold there is, which is a false "you are eligible"
    built out of a typo."""

    def test_negative_age_is_422(self, eligibility_pathway: dict[str, Any]) -> None:
        response = client.post(
            "/eligibility",
            json={"pathway_id": eligibility_pathway["pathway"]["id"], "age": -5},
        )
        assert response.status_code == 422

    def test_absurd_age_is_422(self, eligibility_pathway: dict[str, Any]) -> None:
        response = client.post(
            "/eligibility",
            json={"pathway_id": eligibility_pathway["pathway"]["id"], "age": 9999},
        )
        assert response.status_code == 422

    def test_marks_percentage_over_100_is_422(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 101,
            },
        )
        assert response.status_code == 422

    def test_a_future_date_of_birth_is_422(self, rule_key_pathway: dict[str, Any]) -> None:
        """Checked against the SERVER's Asia/Kolkata today, never a
        client-supplied date (docs/CONTRACTS.md "Duration, dates, cycle,
        DOB"). Without this, `age_on()` returns a negative age and the
        minimum-age criterion reports a confident `does_not_meet`
        computed from a typo."""
        tomorrow = _today_ist() + timedelta(days=1)
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": rule_key_pathway["pathway"]["id"],
                "date_of_birth": tomorrow.isoformat(),
            },
        )
        assert response.status_code == 422

    def test_an_impossibly_old_date_of_birth_is_422(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={"pathway_id": rule_key_pathway["pathway"]["id"], "date_of_birth": "1700-01-01"},
        )
        assert response.status_code == 422

    def test_an_impossible_year_of_passing_is_422(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={"pathway_id": rule_key_pathway["pathway"]["id"], "year_of_passing": 20265},
        )
        assert response.status_code == 422

    def test_an_unparseable_date_of_birth_is_422(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/eligibility",
            json={"pathway_id": rule_key_pathway["pathway"]["id"], "date_of_birth": "not-a-date"},
        )
        assert response.status_code == 422

    def test_a_year_of_passing_a_few_years_ahead_is_accepted(
        self, rule_key_pathway: dict[str, Any]
    ) -> None:
        """The other side of the bound: a student may legitimately name
        the year they EXPECT to pass, so a near-future year must not be
        rejected as impossible."""
        response = client.post(
            "/eligibility",
            json={
                "pathway_id": rule_key_pathway["pathway"]["id"],
                "year_of_passing": _today_ist().year + 1,
            },
        )
        assert response.status_code == 200


class TestNoPersonalInputIsEverLogged:
    """docs/CONTRACTS.md "Duration, dates, cycle, DOB": a date of birth
    is "never logged, never in analytics". Same "opaque identifiers only"
    convention as `app/api/auth.py`'s `_migrate_pending_plan` failure
    logging (`user_id`/`pathway_id`, never `notes`).

    Asserted against the real log stream for the request that DOES log
    something -- the malformed-claim degradation path -- so this cannot
    pass merely because nothing was logged at all.
    """

    def test_the_malformed_claim_warning_names_ids_only(
        self,
        admin_client: Client,
        caplog: pytest.LogCaptureFixture,
        eligibility_pathway: dict[str, Any],
    ) -> None:
        bad_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": eligibility_pathway["pathway"]["id"],
                    "field": "domicile_states",
                    "value": {"states": "Gujarat"},
                    "source_id": eligibility_pathway["source"]["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "review_due_date": "2099-01-01",
                    "status": "published",
                }
            )
            .execute()
            .data[0]
        )
        dob = _DOB_JUST_OLD_ENOUGH.isoformat()
        try:
            with caplog.at_level("DEBUG", logger="app.api.eligibility"):
                response = client.post(
                    "/eligibility",
                    json={
                        "pathway_id": eligibility_pathway["pathway"]["id"],
                        "age": 18,
                        "marks_percentage": 72,
                        "date_of_birth": dob,
                        "category": "SC",
                        "year_of_passing": 2026,
                        "domicile_state": "GJ",
                    },
                )
            assert response.status_code == 200
            logged = "\n".join(r.getMessage() for r in caplog.records)
            # It really did log the degradation (otherwise the
            # assertions below would be vacuous).
            assert "domicile_states" in logged
            assert bad_claim["id"] in logged
            # ...and nothing personal. Only values that cannot occur by
            # accident inside a hex UUID are asserted on: a bare "2026"
            # or "72" could appear in a seeded row's own id and would
            # make this test flaky rather than meaningful.
            for personal in (dob, "SC", "GJ"):
                assert personal not in logged
        finally:
            admin_client.table("claims").delete().eq("id", bad_claim["id"]).execute()
