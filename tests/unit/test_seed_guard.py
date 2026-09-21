"""Unit tests for DATA-8's production guard (scripts/seed_synthetic.py).

Acceptance line: "exits non-zero under production". The card is explicit
that BOTH halves are checked, not just one — the environment AND the
project ref in the URL — so the tests below cover each half failing
independently, and the case where only one of them would have caught it.

Pure functions only; nothing here opens a connection or reads the
environment.
"""

from __future__ import annotations

import pytest

from scripts.seed_synthetic import (
    CAREERS,
    CLAIMS,
    PATHWAYS,
    SAMPLE_LABEL,
    SOURCES,
    SeedRefused,
    _parse_args,
    guard_problem,
    project_ref,
    seed_id,
)

LOCAL = "http://127.0.0.1:54321"
PROD = "https://prodref123456.supabase.co"
STAGING = "https://stagingref78901.supabase.co"


# --------------------------------------------------------------------
# project_ref
# --------------------------------------------------------------------


class TestProjectRef:
    def test_extracts_the_ref_from_a_hosted_url(self) -> None:
        assert project_ref(PROD) == "prodref123456"

    def test_a_loopback_url_has_no_ref(self) -> None:
        assert project_ref(LOCAL) is None
        assert project_ref("http://localhost:54321") is None

    def test_a_bare_hostname_has_no_ref(self) -> None:
        """No dot means no project-ref label to read; treated as "no ref"
        rather than mistaking the whole hostname for one."""
        assert project_ref("http://someserver:8000") is None

    def test_is_case_insensitive(self) -> None:
        assert project_ref("https://PRODREF123456.supabase.co") == "prodref123456"


# --------------------------------------------------------------------
# Guard 1: the declared environment
# --------------------------------------------------------------------


class TestEnvironmentGuard:
    def test_production_is_refused_even_against_a_local_url(self) -> None:
        """The environment check is independent of the target: a run that
        declares itself production is refused whatever it is pointed at."""
        problem = guard_problem(app_env="production", url=LOCAL, production_ref=None)
        assert problem is not None
        assert "APP_ENV=production" in problem

    @pytest.mark.parametrize("spelling", ["production", "PRODUCTION", " Production "])
    def test_case_and_whitespace_do_not_get_past_it(self, spelling: str) -> None:
        assert guard_problem(app_env=spelling, url=LOCAL, production_ref=None) is not None

    def test_development_against_a_local_url_is_allowed(self) -> None:
        assert guard_problem(app_env="development", url=LOCAL, production_ref=None) is None

    def test_staging_against_a_local_url_is_allowed(self) -> None:
        assert guard_problem(app_env="staging", url=LOCAL, production_ref=None) is None


# --------------------------------------------------------------------
# Guard 2: the actual target
# --------------------------------------------------------------------


class TestTargetGuard:
    def test_the_production_ref_is_refused_even_when_app_env_says_staging(self) -> None:
        """The case the second check exists for: somebody exports a
        production URL in a shell whose APP_ENV still says staging. The
        environment check alone would let this through."""
        problem = guard_problem(
            app_env="staging",
            url=PROD,
            production_ref="prodref123456",
            allowlisted={PROD},
        )
        assert problem is not None
        assert "production" in problem.lower()

    def test_the_production_ref_is_refused_when_app_env_is_unset(self) -> None:
        problem = guard_problem(
            app_env="", url=PROD, production_ref="prodref123456", allowlisted={PROD}
        )
        assert problem is not None

    def test_an_unknown_remote_target_is_refused(self) -> None:
        """Fail closed. An unrecognised non-loopback project is refused,
        never seeded on the assumption that it is probably disposable."""
        problem = guard_problem(app_env="staging", url=STAGING, production_ref=None)
        assert problem is not None
        assert "BCION_SEED_TARGET" in problem

    def test_an_explicitly_allowlisted_remote_target_is_permitted(self) -> None:
        assert (
            guard_problem(
                app_env="staging",
                url=STAGING,
                production_ref="prodref123456",
                allowlisted={STAGING},
            )
            is None
        )

    def test_the_allowlist_is_exact_not_a_suffix_match(self) -> None:
        """"endswith" allowlists are how `evil-supabase.co` gets accepted
        as `supabase.co`."""
        problem = guard_problem(
            app_env="staging",
            url="https://evil-stagingref78901.supabase.co",
            production_ref=None,
            allowlisted={STAGING},
        )
        assert problem is not None

    def test_an_empty_url_is_refused_rather_than_guessed(self) -> None:
        problem = guard_problem(app_env="development", url="", production_ref=None)
        assert problem is not None
        assert "SUPABASE_URL" in problem

    def test_allowlisting_cannot_override_the_production_ref(self) -> None:
        """Belt and braces: even if somebody adds the production origin to
        BCION_SEED_TARGET, the ref check still refuses it."""
        problem = guard_problem(
            app_env="development",
            url=PROD,
            production_ref="prodref123456",
            allowlisted={PROD},
        )
        assert problem is not None
        assert "prodref123456" in problem

    def test_a_mixed_case_production_ref_still_matches(self) -> None:
        """Security review, migration-lane merge (2026-09-21): `ref` (from
        `project_ref(url)`) is always lowercased, but `production_ref` was
        compared without lowercasing its own side — an operator setting
        BCION_PRODUCTION_PROJECT_REF with any uppercase character silently
        defeated this specific defense-in-depth check."""
        problem = guard_problem(
            app_env="development",
            url=PROD,
            production_ref="ProdRef123456",
            allowlisted={PROD},
        )
        assert problem is not None
        assert "prodref123456" in problem


# --------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------


class TestArgs:
    def test_no_flags(self) -> None:
        flags = _parse_args([])
        assert flags == {"--dry-run": False, "--purge": False, "--enable-demo-mode": False}

    def test_known_flags_are_accepted(self) -> None:
        flags = _parse_args(["--purge", "--dry-run"])
        assert flags["--purge"] is True
        assert flags["--dry-run"] is True

    def test_an_unknown_flag_is_refused(self) -> None:
        """Same reasoning as scripts/apply_migrations.py: a silently
        ignored `--porge` would run a real seed when a purge was meant."""
        with pytest.raises(SeedRefused, match="unrecognised argument"):
            _parse_args(["--porge"])

    def test_demo_mode_is_off_unless_asked(self) -> None:
        """DATA-8: "turns demo mode on only when asked"."""
        assert _parse_args([])["--enable-demo-mode"] is False
        assert _parse_args(["--purge"])["--enable-demo-mode"] is False


# --------------------------------------------------------------------
# The seeded content itself
# --------------------------------------------------------------------


class TestSeededContentIsUnmistakablySample:
    def test_every_source_is_synthetic(self) -> None:
        assert all(row["source_type"] == "synthetic" for row in SOURCES)

    def test_no_seeded_claim_is_published(self) -> None:
        """Acceptance, verbatim: "no seeded claim is published". The 0001
        trigger would refuse it anyway — this checks the script does not
        even try, so the guarantee does not rest on one mechanism."""
        assert all(row["status"] == "in_review" for row in CLAIMS)

    def test_no_seeded_claim_is_a_draft_either(self) -> None:
        """Draft rows are invisible even in demo mode
        (db/migrations/0007_demo_mode.sql), so a draft would seed
        content nobody could ever see."""
        assert all(row["status"] != "draft" for row in CLAIMS)

    def test_every_name_carries_the_sample_label(self) -> None:
        for row in SOURCES:
            assert SAMPLE_LABEL in row["authority_name"]
        for row in CAREERS:
            assert SAMPLE_LABEL in row["name"]
        for row in PATHWAYS:
            assert SAMPLE_LABEL in row["name"]

    def test_the_verifier_is_never_a_real_person(self) -> None:
        """A synthetic claim must not carry a real reviewer's name — that
        would attach a person's identity to something they never checked."""
        assert all(SAMPLE_LABEL in row["verifier"] for row in CLAIMS)

    def test_every_source_url_is_a_reserved_invalid_domain(self) -> None:
        """`.invalid` is reserved by RFC 2606 and can never resolve, so a
        sample source can never link a student to a real website."""
        assert all(".invalid" in row["official_url"] for row in SOURCES)

    def test_the_card_asked_for_three_to_five_careers_and_pathways(self) -> None:
        assert 3 <= len(CAREERS) <= 5
        assert 3 <= len(PATHWAYS) <= 5


class TestIdempotency:
    def test_ids_are_deterministic(self) -> None:
        """Acceptance, verbatim: "Two runs give identical row counts".
        That holds because the ids are a pure function of a stable key,
        so the second run upserts the same rows rather than inserting
        new ones."""
        assert seed_id("career:marine-biologist") == seed_id("career:marine-biologist")

    def test_different_keys_give_different_ids(self) -> None:
        assert seed_id("career:a") != seed_id("career:b")

    def test_every_seeded_id_is_unique(self) -> None:
        ids = [row["id"] for row in SOURCES + CAREERS + PATHWAYS + CLAIMS]
        assert len(ids) == len(set(ids))

    def test_pathway_career_ids_all_resolve_to_a_seeded_career(self) -> None:
        """A dangling career_id would fail the foreign key at run time;
        catching it here means the seed script cannot ship broken."""
        career_ids = {row["id"] for row in CAREERS}
        assert all(row["career_id"] in career_ids for row in PATHWAYS)

    def test_claim_source_ids_all_resolve_to_a_seeded_source(self) -> None:
        source_ids = {row["id"] for row in SOURCES}
        assert all(row["source_id"] in source_ids for row in CLAIMS)

    def test_claim_entity_ids_all_resolve_to_a_seeded_pathway(self) -> None:
        """`claims.entity_id` has no foreign key (0001_init.sql), so
        nothing but this test would catch a claim pointing at a pathway
        that does not exist — it would simply never render."""
        pathway_ids = {row["id"] for row in PATHWAYS}
        assert all(row["entity_id"] in pathway_ids for row in CLAIMS)
