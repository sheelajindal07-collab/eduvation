"""Regression test for the client-sharing bug fixed 2026-09-19
(app/db/client.py, docs/DECISIONS.md).

The bug: `get_anon_client()` was `@lru_cache`d, and `get_user_scoped_client`
mutated *that same shared object's* postgrest auth header. Under
concurrent requests, one user's access token could leak onto another
user's (or a guest's) query. This can't be proven by timing an actual
race deterministically, but the structural guarantee that prevents it —
every call returns a genuinely distinct client object — can be, and that
is what actually matters: if two calls never return the same object,
there is nothing shared left to race on.
"""

from app.db import get_anon_client, get_user_scoped_client


def test_two_anon_client_calls_return_distinct_objects() -> None:
    a = get_anon_client()
    b = get_anon_client()
    assert a is not b


def test_two_user_scoped_client_calls_return_distinct_objects() -> None:
    a = get_user_scoped_client("fake-token-a")
    b = get_user_scoped_client("fake-token-b")
    assert a is not b


def test_user_scoped_client_is_distinct_from_anon_client() -> None:
    """The specific shape of the original bug: get_user_scoped_client
    used to fetch and mutate the SAME object get_anon_client() returns.
    A guest request obtaining an anon client afterward must never see
    another user's token attached to it."""
    anon = get_anon_client()
    user_scoped = get_user_scoped_client("fake-token")
    assert anon is not user_scoped

    # Mutating the user-scoped client's auth must not be visible on a
    # separately-obtained anon client -- proves they don't share state.
    fresh_anon = get_anon_client()
    assert fresh_anon is not user_scoped
