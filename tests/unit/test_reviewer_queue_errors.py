"""SEC-2: the reviewer queue's fixed `?error=` code vocabulary
(`app/web/reviewer/queue.py`).

Before SEC-2 the console redirected to `/reviewer/queue?error=<the
failure's own free-text message>` and rendered whatever came back in the
query string. Jinja's autoescaping meant no markup could be injected, but
any sentence a stranger put in that parameter was still reproduced
verbatim inside an authenticated page's error alert. These tests pin the
replacement: a short code travels on the wire, a fixed dict turns it into
one of a known set of messages, and anything unrecognised becomes the
generic message instead of itself.

The live end of the same guarantee (an attacker string really does not
reach the rendered page, with a real session and a real database) is in
tests/db/test_reviewer_console.py's TestReviewerQueueErrorCodes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.web.reviewer.queue import (
    _DETAIL_PREFIX_CODES,
    _GENERIC_ERROR_CODE,
    _GENERIC_ERROR_MESSAGE,
    QUEUE_ERROR_MESSAGES,
    _redirect_to_queue_with_error,
    error_code_for_detail,
    queue_error_message,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKER_CHECKER_SQL = REPO_ROOT / "db" / "migrations" / "0003_maker_checker.sql"


def _trigger_messages() -> list[str]:
    """Every `raise exception '...'` message in the maker-checker
    trigger, read from the migration itself rather than copied here.

    That is the point: these strings arrive at the console as
    `HTTPException.detail` (app/api/claims.py relays a P0001 trigger
    error's message as-is), so if the migration lane ever adds or
    rewords one, the test below fails instead of the console silently
    degrading that failure to "something went wrong".
    """
    sql = MAKER_CHECKER_SQL.read_text(encoding="utf-8")
    return [m.strip() for m in re.findall(r"raise exception\s+'([^']*)'", sql, re.IGNORECASE)]


class TestTriggerMessagesAllMapToACode:
    def test_the_migration_actually_yielded_messages(self) -> None:
        """Guards the regex itself — a silently empty list would make
        every assertion below vacuously true."""
        assert len(_trigger_messages()) >= 8

    @pytest.mark.parametrize("message", _trigger_messages())
    def test_every_trigger_message_has_a_specific_code(self, message: str) -> None:
        code = error_code_for_detail(message)
        assert code != _GENERIC_ERROR_CODE, message
        assert code in QUEUE_ERROR_MESSAGES

    def test_the_interpolated_transition_message_still_matches(self) -> None:
        """Two of the trigger's messages end in `%` (the offending
        status, substituted by Postgres at raise time), so the classifier
        has to match on a prefix, not on equality."""
        real = (
            "A draft may only stay draft or move to in_review (submitted) "
            "-- not directly to published."
        )
        assert error_code_for_detail(real) == "invalid_transition"


class TestClaimsApiDetailsMapToACode:
    """The non-trigger `HTTPException.detail` strings app/api/claims.py
    raises — checked against that module, not guessed."""

    @pytest.mark.parametrize(
        ("detail", "expected"),
        [
            ("Only a reviewer can do this.", "not_a_reviewer"),
            ("Referenced source not found.", "source_not_found"),
            ("Claim not found.", "claim_not_found"),
            ("Sign in required.", "sign_in_required"),
            ("Could not process this claim.", "could_not_process"),
        ],
    )
    def test_detail_maps_to_its_code(self, detail: str, expected: str) -> None:
        assert error_code_for_detail(detail) == expected

    def test_an_unrecognised_detail_becomes_the_generic_code(self) -> None:
        assert error_code_for_detail("something nobody has seen before") == _GENERIC_ERROR_CODE

    def test_a_non_string_detail_does_not_crash(self) -> None:
        """`HTTPException.detail` is typed `Any` — a dict-shaped detail
        (docs/CONTRACTS.md's own error shape, which other routes are
        migrating to) must classify, not raise."""
        assert error_code_for_detail({"code": "x", "message": "y"}) == _GENERIC_ERROR_CODE
        assert error_code_for_detail(None) == _GENERIC_ERROR_CODE


class TestQueueErrorMessageLookup:
    def test_no_error_code_means_no_alert(self) -> None:
        assert queue_error_message(None) is None
        assert queue_error_message("") is None

    def test_a_known_code_renders_its_own_message(self) -> None:
        assert queue_error_message("self_approval") == QUEUE_ERROR_MESSAGES["self_approval"]

    @pytest.mark.parametrize(
        "hostile",
        [
            "<script>alert(1)</script>",
            "Your session expired -- call +91 00000 00000 to restore it",
            "../../etc/passwd",
            "already_published; drop table claims",
            "SELF_APPROVAL",  # codes are exact, not case-folded
        ],
    )
    def test_an_arbitrary_string_is_never_echoed_back(self, hostile: str) -> None:
        message = queue_error_message(hostile)
        assert message == _GENERIC_ERROR_MESSAGE
        assert hostile not in (message or "")


class TestTheCodeVocabularyIsSelfConsistent:
    def test_every_classified_code_has_a_message(self) -> None:
        for _prefix, code in _DETAIL_PREFIX_CODES:
            assert code in QUEUE_ERROR_MESSAGES, code

    def test_codes_are_url_safe_and_carry_no_prose(self) -> None:
        """They travel in a query string unencoded — and a code that
        looked like a sentence would defeat the point of having codes."""
        for code in QUEUE_ERROR_MESSAGES:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code

    def test_the_already_published_message_keeps_fix_8s_guarantee(self) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 8): the console must
        not relay the trigger's "supersede it with a new claim instead"
        — that points a reviewer at a feature this console doesn't have.
        Carried over from the pre-SEC-2 translation, now pinned as a
        property of the message dict itself."""
        message = QUEUE_ERROR_MESSAGES["already_published"]
        assert "already published" in message.lower()
        assert "supersede" not in message.lower()


class TestRedirectCarriesOnlyACode:
    def test_a_known_code_is_placed_in_the_query_string_as_is(self) -> None:
        response = _redirect_to_queue_with_error("self_approval")
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/queue?error=self_approval"

    def test_an_unknown_code_can_never_reach_the_url(self) -> None:
        """Defense in depth: even if some future caller passed a raw
        message here, nothing but a vetted code is emitted."""
        response = _redirect_to_queue_with_error("<script>alert(1)</script>")
        assert response.headers["location"] == f"/reviewer/queue?error={_GENERIC_ERROR_CODE}"
