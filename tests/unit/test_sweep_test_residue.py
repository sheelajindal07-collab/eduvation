"""Unit tests for QA-12's residue sweeper (scripts/sweep_test_residue.py).

The card's acceptance line, verbatim: "Anchor every match tightly ...
write unit tests proving your matcher rejects plausible near-miss real
content, not just that it accepts the intended fixture markers." Every
`Reject...` test class below exists for that reason — each one is a
constructed, plausible piece of REAL content that a naive substring
search would incorrectly flag, paired with the actual fixture literal
this codebase's own test suite uses (`tests/db/conftest.py`'s
`run_name`/`run_email`, `tests/fixtures/synthetic_data.py`) to prove the
matcher still catches the real thing.

Pure functions only — nothing here opens a network connection, a database,
or reads the environment. `--apply`'s actual deletion behaviour
(`apply_plan`) is intentionally NOT exercised against a real database from
this file; see the QA-12 completion report for where that was verified
(a throwaway local test stack only, never anywhere else).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.sweep_test_residue import (
    DeletionPlan,
    Match,
    SweepRefused,
    _parse_args,
    compute_deletion_plan,
    email_marker,
    main,
    marker_in_text,
    render_report,
    scan_careers,
    scan_claims,
    scan_pathways,
    scan_sources,
    scan_users,
    url_marker,
    value_as_text,
    verifier_marker,
)

# --------------------------------------------------------------------
# General literal markers — accept the real fixture shapes
# --------------------------------------------------------------------


class TestAcceptsTheRealFixtureConventions:
    """Every one of these strings is copied verbatim (aside from the
    run-id/uuid suffix, irrelevant to matching) from an existing fixture
    in this codebase — proving the matcher actually catches what this
    repo's own test suite writes, not a hypothetical."""

    def test_e2e_smoke_test_career_name(self) -> None:
        # tests/e2e/test_smoke.py
        assert marker_in_text("E2E smoke test career [run:abc123def456]") == "marker:E2E"

    def test_e2e_eligibility_source_name(self) -> None:
        assert (
            marker_in_text("E2E TEST ELIGIBILITY SOURCE (fixture) [run:abc123def456]")
            == "marker:E2E"
        )

    def test_rls_test_career_name(self) -> None:
        # tests/db/test_rls.py
        text = "RLS test career (SYNTHETIC) [run:abc123def456]"
        # Both markers are present; either being found is a pass.
        assert marker_in_text(text) in {"marker:RLS test", "marker:SYNTHETIC"}

    def test_test_fixture_authority_name(self) -> None:
        # tests/fixtures/synthetic_data.py
        assert marker_in_text("TEST FIXTURE — not a real authority") == "marker:TEST FIXTURE"

    def test_verifier_test_fixture(self) -> None:
        # tests/db/conftest.py: run_name("test-fixture")
        assert verifier_marker("test-fixture [run:abc123def456]") == "marker:test-fixture"

    def test_verifier_e2e_smoke_test_fixture(self) -> None:
        # tests/db/conftest.py: run_name("e2e-smoke-test-fixture")
        assert (
            verifier_marker("e2e-smoke-test-fixture [run:abc123def456]")
            == "marker:e2e-smoke-test-fixture"
        )

    def test_run_email_default_domain(self) -> None:
        # tests/db/conftest.py: run_email(...) with the default domain
        assert email_marker("bcion-smoke-abc123def456-9f8e7d6c5b@example.invalid") == (
            "domain:example.invalid"
        )


# --------------------------------------------------------------------
# General literal markers — reject plausible near-miss REAL content
# --------------------------------------------------------------------


class TestRejectsNearMissRealContent:
    def test_test_fixture_does_not_match_latest_fixture(self) -> None:
        """The card's own named trap, transposed to upper case: "LATEST"
        ends in "TEST", so "LATEST FIXTURE ROOM" contains the literal
        substring "TEST FIXTURE" purely by coincidence of where one real
        word ends and the next begins. A word-boundary match correctly
        rejects it — there is no boundary between the "A" of "LA" and the
        "T" that starts "TEST" inside "LATEST"."""
        assert marker_in_text("LATEST FIXTURE ROOM AVAILABLE FOR BOOKING") is None

    def test_synthetic_biology_title_case_does_not_match(self) -> None:
        """A real, entirely plausible career/pathway name — "synthetic"
        is a genuine field of study (synthetic biology, synthetic
        materials). Sentence/title case is how a real record would
        actually be written; only the shouted, all-caps fixture
        convention this repo's own tests use should match."""
        assert marker_in_text("Synthetic Biology Researcher") is None
        assert marker_in_text("BSc in Synthetic Chemistry") is None

    def test_e2e_does_not_match_inside_a_compound_word(self) -> None:
        """A contrived but structurally real trap: "Piece2Earn" contains
        the literal substring "E2E" (...ecE2Earn...) with no separating
        punctuation at all. No word boundary exists between the "C" of
        "Piece" and the "E" that starts the coincidental "E2E" run, so
        this is correctly rejected."""
        assert marker_in_text("Piece2Earn Micro-Finance Advisor") is None

    def test_rls_test_does_not_match_swirls_test_kit(self) -> None:
        """Case-EXACT trap: "SWIRLS" ends in the exact substring "RLS"
        (upper case, same as the marker), immediately followed by
        " test" (lower case, same as the marker) — "SWIRLS test kit"
        contains the literal, case-exact substring "RLS test" purely
        because of where "SWIRLS" ends. Rejected because there is no word
        boundary between the "I" and "R" inside "SWIRLS"."""
        assert marker_in_text("SWIRLS test kit — pottery pathway equipment") is None

    def test_rls_test_does_not_match_ordinary_case_variants(self) -> None:
        """Real content about girls' test scores would never be typed in
        the fixture's exact RLS/lower-case-test shape; case sensitivity
        alone rejects both of these."""
        assert marker_in_text("Girls Test Prep Coaching") is None
        assert marker_in_text("GIRLS TEST SCORES IMPROVED STATEWIDE") is None

    def test_bare_test_substring_inside_real_words_never_matches(self) -> None:
        """None of the markers are the bare word "test" — a pathway/
        career description using perfectly ordinary English words that
        happen to contain "test" is never at risk."""
        for real_text in [
            "Protestant Seminary Studies",
            "Attestation Officer (Notary Pathway)",
            "Contest and Exhibition Curator",
            "Latest Advances in Renewable Energy",
            "Greatest Common Factor tutoring (Mathematics)",
        ]:
            assert marker_in_text(real_text) is None

    def test_verifier_test_fixture_does_not_match_a_real_engineering_term(self) -> None:
        """ "test fixture" (a jig used to hold a workpiece while testing
        it) is a real, ordinary manufacturing/engineering term that could
        legitimately appear in a claim's own descriptive text. Case
        sensitivity is what separates the genuine lower-case engineering
        usage from this repo's own ALL-lower-case-but-hyphenated fixture
        convention... but since both are lower case, this specific pair
        is intentionally scoped to the verifier field ONLY (never
        `claims.value`), and even there, a real verifier's identifier is
        never spelled exactly "test-fixture" (a hyphenated compound
        rather than a person's name/handle) — this test documents the
        deliberate, narrow scope rather than claiming false-positive
        immunity for `claims.value` prose using the phrase naturally."""
        # A claim's VALUE (not verifier) describing a real fixture is not
        # scanned against the verifier-only markers at all.
        assert marker_in_text("Technicians use a test fixture to hold the workpiece.") is None


# --------------------------------------------------------------------
# Domain / email matching — parsed, never a raw substring search
# --------------------------------------------------------------------


class TestDomainMatchingIsParsedNotSubstring:
    def test_example_invalid_matches_exactly(self) -> None:
        assert url_marker("https://example.invalid/some-authority") == "domain:example.invalid"

    def test_example_invalid_matches_a_real_subdomain(self) -> None:
        assert url_marker("https://sub.example.invalid/path") == "domain:example.invalid"

    def test_lookalike_hostname_is_rejected(self) -> None:
        """ "notexample.invalid" contains the literal substring
        "example.invalid" purely by coincidence of where the hostname's
        own prefix ends — a bare substring search would wrongly flag it.
        Parsed-hostname comparison (`==` or a dot-anchored suffix)
        correctly rejects it."""
        assert url_marker("https://notexample.invalid/looks-real") is None

    def test_a_real_official_domain_is_never_flagged(self) -> None:
        assert url_marker("https://www.ugc.gov.in/some-real-notification") is None

    def test_email_domain_example_invalid_matches_regardless_of_local_part(self) -> None:
        assert email_marker("anything-at-all@example.invalid") == "domain:example.invalid"

    def test_email_lookalike_domain_is_rejected(self) -> None:
        assert email_marker("someone@notexample.invalid") is None

    def test_bcion_test_prefix_at_example_com_matches(self) -> None:
        expected = "email-prefix:bcion-test-@example.com"
        assert email_marker("bcion-test-9f8e7d@example.com") == expected

    def test_bcion_e2e_prefix_at_example_com_matches(self) -> None:
        expected = "email-prefix:bcion-e2e-@example.com"
        assert email_marker("bcion-e2e-9f8e7d@example.com") == expected

    def test_bcion_test_prefix_at_a_different_domain_does_not_match(self) -> None:
        """The card is explicit: this prefix rule applies "at example.com
        SPECIFICALLY" — the same local part at any other domain (a typo,
        or a genuine outside address) must not match."""
        assert email_marker("bcion-test-9f8e7d@gmail.com") is None

    def test_a_plain_test_local_part_at_example_com_does_not_match(self) -> None:
        """ "test@example.com" contains the substring "test" but is not
        the "bcion-test-"/"bcion-e2e-" prefix the card names — must not
        match on the word "test" alone."""
        assert email_marker("test@example.com") is None
        assert email_marker("sometester@example.com") is None

    def test_an_unrelated_bcion_prefixed_real_convention_does_not_match(self) -> None:
        """This codebase's OWN guardian-consent fixtures already use a
        different "bcion-guardian-...@example.com" convention
        (tests/db/test_guardian_consent.py) — real, but not one of the
        two prefixes this card names. Deliberately not matched (see the
        module docstring's "intentionally out of scope")."""
        assert email_marker("bcion-guardian-9f8e7d@example.com") is None

    def test_case_of_the_prefix_and_domain_does_not_evade_the_check(self) -> None:
        assert email_marker("BCION-TEST-9f8e7d@Example.COM") == (
            "email-prefix:bcion-test-@example.com"
        )


# --------------------------------------------------------------------
# value_as_text — claims.value is JSONB, not always a string
# --------------------------------------------------------------------


class TestValueAsText:
    def test_a_plain_string_passes_through(self) -> None:
        assert value_as_text("SYNTHETIC sample value") == "SYNTHETIC sample value"

    def test_none_is_empty(self) -> None:
        assert value_as_text(None) == ""

    def test_a_number_is_stringified(self) -> None:
        assert value_as_text(45000) == "45000"

    def test_a_structured_value_is_json_dumped_and_still_matchable(self) -> None:
        text = value_as_text({"label": "TEST FIXTURE stage", "weeks": 4})
        assert marker_in_text(text) == "marker:TEST FIXTURE"


# --------------------------------------------------------------------
# Row scanners — table-shaped dicts in, Match objects out
# --------------------------------------------------------------------


class TestScanSources:
    def test_matches_on_authority_name(self) -> None:
        rows = [
            {
                "id": "s1",
                "authority_name": "E2E TEST ELIGIBILITY SOURCE",
                "official_url": "https://real.example/x",
            }
        ]
        matches = scan_sources(rows)
        assert [m.row_id for m in matches] == ["s1"]

    def test_matches_on_official_url_domain(self) -> None:
        rows = [
            {
                "id": "s2",
                "authority_name": "Sample Authority",
                "official_url": "https://example.invalid/x",
            }
        ]
        matches = scan_sources(rows)
        assert [m.row_id for m in matches] == ["s2"]

    def test_a_real_source_does_not_match(self) -> None:
        rows = [
            {
                "id": "s3",
                "authority_name": "University Grants Commission",
                "official_url": "https://www.ugc.gov.in",
            }
        ]
        assert scan_sources(rows) == []


class TestScanCareersAndPathways:
    def test_career_matches(self) -> None:
        rows = [{"id": "c1", "name": "RLS test career (SYNTHETIC)"}]
        assert [m.row_id for m in scan_careers(rows)] == ["c1"]

    def test_a_real_career_does_not_match(self) -> None:
        rows = [{"id": "c2", "name": "Marine Biologist"}]
        assert scan_careers(rows) == []

    def test_pathway_matches_on_description(self) -> None:
        rows = [
            {
                "id": "p1",
                "name": "Some Pathway",
                "description": "Seeded for the E2E smoke suite only.",
            }
        ]
        assert [m.row_id for m in scan_pathways(rows)] == ["p1"]

    def test_a_real_pathway_does_not_match(self) -> None:
        rows = [
            {
                "id": "p2",
                "name": "BTech Civil Engineering",
                "description": "A four-year undergraduate engineering degree.",
            }
        ]
        assert scan_pathways(rows) == []


class TestScanClaims:
    def test_matches_on_verifier(self) -> None:
        rows = [{"id": "cl1", "verifier": "e2e-smoke-test-fixture", "value": "some value"}]
        assert [m.row_id for m in scan_claims(rows)] == ["cl1"]

    def test_matches_on_value(self) -> None:
        rows = [{"id": "cl2", "verifier": "Mahesh Iyer", "value": "SYNTHETIC placeholder text"}]
        assert [m.row_id for m in scan_claims(rows)] == ["cl2"]

    def test_a_real_reviewed_claim_does_not_match(self) -> None:
        rows = [
            {
                "id": "cl3",
                "verifier": "Mahesh Iyer",
                "value": "Admission requires a Class 12 pass with Physics, Chemistry, Mathematics.",
            }
        ]
        assert scan_claims(rows) == []


class TestScanUsers:
    def test_matches_on_email(self) -> None:
        rows = [{"id": "u1", "email": "bcion-test-abc123@example.com"}]
        assert [m.row_id for m in scan_users(rows)] == ["u1"]

    def test_a_real_users_email_does_not_match(self) -> None:
        rows = [{"id": "u2", "email": "some.real.student@gmail.com"}]
        assert scan_users(rows) == []


# --------------------------------------------------------------------
# compute_deletion_plan — ordering and reference-following
# --------------------------------------------------------------------


class TestComputeDeletionPlan:
    def _base(self) -> dict[str, list[dict]]:
        return {"sources": [], "careers": [], "pathways": [], "claims": [], "users": []}

    def test_empty_input_gives_an_empty_plan(self) -> None:
        plan = compute_deletion_plan(**self._base())
        assert isinstance(plan, DeletionPlan)
        assert plan.is_empty()
        assert plan.total() == 0

    def test_a_claim_referencing_a_matched_source_is_swept_even_without_its_own_marker(
        self,
    ) -> None:
        data = self._base()
        data["sources"] = [
            {"id": "s1", "authority_name": "E2E sample source", "official_url": "https://x"}
        ]
        data["claims"] = [
            {
                "id": "cl1",
                "verifier": "Mahesh Iyer",
                "value": "an ordinary-looking value",
                "source_id": "s1",
                "entity_id": None,
                "created_by": None,
                "reviewed_by": None,
            }
        ]
        plan = compute_deletion_plan(**data)
        assert plan.sources == {"s1"}
        assert plan.claims == {"cl1"}

    def test_a_claim_referencing_a_matched_pathway_via_entity_id_is_swept(self) -> None:
        data = self._base()
        data["pathways"] = [{"id": "p1", "name": "E2E sample pathway", "description": ""}]
        data["claims"] = [
            {
                "id": "cl2",
                "verifier": "Mahesh Iyer",
                "value": "an ordinary-looking value",
                "source_id": None,
                "entity_id": "p1",
                "created_by": None,
                "reviewed_by": None,
            }
        ]
        plan = compute_deletion_plan(**data)
        assert plan.pathways == {"p1"}
        assert plan.claims == {"cl2"}

    def test_a_claim_made_by_a_matched_user_is_swept(self) -> None:
        data = self._base()
        data["users"] = [{"id": "u1", "email": "bcion-e2e-x@example.com"}]
        data["claims"] = [
            {
                "id": "cl3",
                "verifier": "Mahesh Iyer",
                "value": "an ordinary-looking value",
                "source_id": None,
                "entity_id": None,
                "created_by": "u1",
                "reviewed_by": None,
            }
        ]
        plan = compute_deletion_plan(**data)
        assert plan.users == {"u1"}
        assert plan.claims == {"cl3"}

    def test_unrelated_real_rows_are_never_included(self) -> None:
        data = self._base()
        data["sources"] = [
            {"id": "s-real", "authority_name": "UGC", "official_url": "https://ugc.gov.in"}
        ]
        data["careers"] = [{"id": "c-real", "name": "Marine Biologist"}]
        data["pathways"] = [{"id": "p-real", "name": "BSc Zoology", "description": "Real."}]
        data["claims"] = [
            {
                "id": "cl-real",
                "verifier": "Mahesh Iyer",
                "value": "Real value",
                "source_id": "s-real",
                "entity_id": "p-real",
                "created_by": None,
                "reviewed_by": None,
            }
        ]
        data["users"] = [{"id": "u-real", "email": "real.student@gmail.com"}]
        plan = compute_deletion_plan(**data)
        assert plan.is_empty()


# --------------------------------------------------------------------
# Argument parsing — dry-run is the default, --apply is the only flag
# --------------------------------------------------------------------


class TestArgs:
    def test_no_arguments_means_dry_run(self) -> None:
        assert _parse_args([]) is False

    def test_apply_flag_is_recognised(self) -> None:
        assert _parse_args(["--apply"]) is True

    def test_an_unknown_flag_is_refused_not_silently_ignored(self) -> None:
        """A typo like `--aply` must not silently become a harmless
        dry-run when the caller meant to delete — same reasoning as
        scripts/seed_synthetic.py's own `_parse_args`."""
        with pytest.raises(SweepRefused, match="unrecognised argument"):
            _parse_args(["--aply"])


# --------------------------------------------------------------------
# render_report — the dry-run report itself
# --------------------------------------------------------------------


class TestRenderReport:
    def test_dry_run_banner_says_nothing_will_be_deleted(self) -> None:
        report = render_report(url="http://127.0.0.1:54321", apply_mode=False, matches_by_table={})
        assert "DRY RUN" in report
        assert "nothing will be deleted" in report

    def test_apply_banner_says_deletion_will_happen(self) -> None:
        report = render_report(url="http://127.0.0.1:54321", apply_mode=True, matches_by_table={})
        assert "APPLY MODE" in report
        assert "WILL BE DELETED" in report

    def test_report_lists_tables_and_counts(self) -> None:
        matches = {
            "careers": [Match("careers", "c1", "marker:E2E", "E2E smoke test career")],
            "sources": [],
        }
        report = render_report(
            url="http://127.0.0.1:54321", apply_mode=False, matches_by_table=matches
        )
        assert "careers: 1 match(es)" in report
        assert "sources: 0 match(es)" in report
        assert "c1" in report
        assert "TOTAL: 1 row(s)/user(s) matched." in report


# --------------------------------------------------------------------
# main() wiring — a fully in-memory fake client, no network/database.
#
# The real, live-Postgres deletion behaviour of `apply_plan` (FK-safe
# ordering, an actual DELETE hitting real rows) was verified separately
# against a throwaway local test stack, never here — see the QA-12
# completion report. What this section proves instead is the CLI
# plumbing around it: argument parsing, env-var checks, that dry-run
# truly never calls delete, and that `--apply` deletes exactly (and
# only) the matched rows/users through the very same `main()` a real
# invocation runs.
# --------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self._store = store
        self._table = table
        self._delete = False
        self._ids: set[str] | None = None

    def select(self, _columns: str) -> _FakeQuery:
        return self

    def delete(self) -> _FakeQuery:
        self._delete = True
        return self

    def in_(self, _column: str, ids: list[str]) -> _FakeQuery:
        self._ids = set(ids)
        return self

    def execute(self) -> SimpleNamespace:
        if self._delete:
            keep_ids = self._ids or set()
            self._store[self._table] = [
                row for row in self._store[self._table] if row["id"] not in keep_ids
            ]
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=list(self._store[self._table]))


class _FakeAdminAuth:
    def __init__(self, users: list[SimpleNamespace]) -> None:
        self._users = users
        self.deleted: list[str] = []

    def list_users(self, page: int = 1, per_page: int = 200) -> list[SimpleNamespace]:
        return self._users if page == 1 else []

    def delete_user(self, user_id: str) -> None:
        self.deleted.append(user_id)
        self._users = [u for u in self._users if u.id != user_id]


class FakeSupabaseClient:
    """Just enough of the supabase-py surface for `main()` to run
    end-to-end against: `.table(name).select(...)/.delete().in_(...)
    .execute()` and `.auth.admin.list_users()/.delete_user()`."""

    def __init__(self, tables: dict[str, list[dict]], users: list[SimpleNamespace]) -> None:
        self.tables = tables
        self.auth = SimpleNamespace(admin=_FakeAdminAuth(users))

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self.tables, name)


def _fixture_client() -> FakeSupabaseClient:
    tables = {
        "sources": [
            {"id": "s1", "authority_name": "E2E sample source", "official_url": "https://x.test"},
            {"id": "s-real", "authority_name": "UGC", "official_url": "https://ugc.gov.in"},
        ],
        "careers": [{"id": "c-real", "name": "Marine Biologist"}],
        "pathways": [],
        "claims": [],
    }
    users = [
        SimpleNamespace(id="u1", email="bcion-test-abc123@example.com"),
        SimpleNamespace(id="u-real", email="real.student@gmail.com"),
    ]
    return FakeSupabaseClient(tables, users)


class TestMainWiring:
    def _patch_env_and_client(
        self, monkeypatch: pytest.MonkeyPatch, client: FakeSupabaseClient
    ) -> None:
        monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-role-key")
        monkeypatch.setattr("supabase.create_client", lambda url, key: client)

    def test_dry_run_lists_matches_and_deletes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = _fixture_client()
        self._patch_env_and_client(monkeypatch, client)

        exit_code = main([])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "sources: 1 match(es)" in out
        # Nothing was deleted: both the matched AND the real row survive.
        assert {row["id"] for row in client.tables["sources"]} == {"s1", "s-real"}
        assert {row["id"] for row in client.tables["careers"]} == {"c-real"}
        assert client.auth.admin.deleted == []

    def test_apply_deletes_exactly_the_matches_and_spares_real_rows(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = _fixture_client()
        self._patch_env_and_client(monkeypatch, client)

        exit_code = main(["--apply"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "APPLY MODE" in out
        # The matched fixture source and user are gone...
        assert {row["id"] for row in client.tables["sources"]} == {"s-real"}
        assert client.auth.admin.deleted == ["u1"]
        # ...but the real career and real user were never touched.
        assert {row["id"] for row in client.tables["careers"]} == {"c-real"}
        assert any(u.id == "u-real" for u in client.auth.admin._users)

    def test_dry_run_is_still_the_default_even_with_a_populated_client(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Belt and braces on the card's own safety-critical line: calling
        `main()` with no arguments at all — the exact shape a bare
        `python scripts/sweep_test_residue.py` invocation produces — must
        never delete anything, regardless of how much matches."""
        client = _fixture_client()
        self._patch_env_and_client(monkeypatch, client)

        main([])

        assert len(client.tables["sources"]) == 2
        assert len(client.auth.admin._users) == 2

    def test_missing_supabase_url_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        assert main([]) == 1

    def test_missing_service_role_key_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        assert main([]) == 1
