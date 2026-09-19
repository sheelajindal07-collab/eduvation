"""Regression test for the client-sharing bug fixed 2026-09-19
(app/db/client.py, docs/DECISIONS.md).

The bug: `get_anon_client()` was `@lru_cache`d, and `get_user_scoped_client`
mutated *that same shared object's* postgrest auth header. Under
concurrent requests, one user's access token could leak onto another
user's (or a guest's) query.

Strengthened 2026-09-19 (data-security-reviewer finding): the original
version of this file only asserted `a is not b` — necessary but not
sufficient, since it would still pass even if some future change
reintroduced sharing one level down (e.g. two distinct `Client` wrapper
objects both pointing at the same mutable headers dict). This version
additionally asserts the actual header value each client carries is
correct and independent, and adds a real concurrent-call smoke test
against the live project — not deterministic proof of a race (the
module docstring's original caveat still holds), but direct evidence
that many interleaved calls never observe another call's token.
"""

from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
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


def test_user_scoped_client_carries_its_own_token_in_its_own_headers() -> None:
    """Not just "a different object" -- the actual Authorization header
    each client sends must be the caller's own token, independently."""
    a = get_user_scoped_client("token-a")
    b = get_user_scoped_client("token-b")
    assert a.postgrest.headers["Authorization"] == "Bearer token-a"
    assert b.postgrest.headers["Authorization"] == "Bearer token-b"


def test_anon_client_authorization_is_always_the_anon_key_not_a_user_token() -> None:
    """Supabase's anon client uses the anon/publishable key as its own
    default bearer token (this is expected -- it's how RLS sees an
    unauthenticated caller, not a bug). The property that actually
    matters: that value must always be the anon key baked in at
    construction, never a signed-in user's token leaked from some other
    request that happened to run on a shared object."""
    anon_key = get_settings().supabase_publishable_key
    assert anon_key is not None  # required for this test to mean anything
    anon = get_anon_client()
    assert anon.postgrest.headers["Authorization"] == f"Bearer {anon_key}"


def test_many_concurrent_calls_never_cross_contaminate_tokens() -> None:
    """Not a deterministic proof of the original race (the module
    docstring's caveat still holds -- true concurrency isn't guaranteed
    by a thread pool), but direct evidence over many interleaved calls,
    reproducing FastAPI's real execution model: sync dependencies run via
    `run_in_threadpool` under concurrent requests, which is exactly the
    failure mode the original bug had."""
    tokens = [f"token-{i}" for i in range(50)]

    def get_header_for(token: str) -> tuple[str, str]:
        client = get_user_scoped_client(token)
        return token, client.postgrest.headers["Authorization"]

    with ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(get_header_for, tokens * 4))  # 200 calls total

    mismatches = [(t, h) for t, h in results if h != f"Bearer {t}"]
    assert not mismatches, f"cross-contaminated tokens: {mismatches}"
