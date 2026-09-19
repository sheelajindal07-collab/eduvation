"""Supabase client factory — RLS-aware, restricted role only.

Non-negotiable (docs/SECURITY.md, Lite Build Pack §4): the application never
connects as the Supabase owner/service role for a user-facing request.
Every request-scoped client carries the *signed-in user's own access
token*, so Postgres row-level security is what actually enforces access —
not application code. A client with no user token (e.g. for public
knowledge-base reads on behalf of a guest) uses the anon/publishable key
only, which the RLS policies in db/migrations/0001_init.sql already treat
as "no special access" (world-readable rows only).

**Every client returned here is freshly constructed, never cached or
shared** (fixed 2026-09-19, see docs/DECISIONS.md). The prior version
`@lru_cache`d a single anon client and had `get_user_scoped_client`
mutate *that same shared object's* postgrest auth header
(`client.postgrest.auth(token)`) on every call. Under concurrent
requests that is a real cross-user data-leak bug: request A sets the
shared client's token to A's, then before A's query executes, request B
overwrites it with B's token, and A's query runs under B's identity — or
a "guest" request that happens to run after any authenticated one
silently inherits whatever token was last set. A Supabase client is
cheap to construct (no network round-trip at construction time), so a
fresh instance per request is the correct trade, not a micro-optimisation
worth the risk.

Schema is applied via db/migrations/*.sql on the owner's own Supabase
project (see docs/DECISIONS.md) — never through an agent's management-API
access, and never by editing tables from a dashboard.
"""

from __future__ import annotations

from supabase import Client, create_client

from app.core.config import get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY are unset.

    Callers should catch this and degrade gracefully (docs/UI.md's
    "difficult states" — e.g. explore/compare can still show whatever is
    cached, or a clear "not available yet" rather than a stack trace).
    """


def _build_client() -> Client:
    """A fresh, unshared client using only the public/anon key. Never
    cache or share the return value across requests — see module
    docstring for why that would be a security bug, not a convenience."""
    settings = get_settings()
    if not settings.db_configured:
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY are not set. "
            "Copy .env.example to .env and fill in your project's values "
            "(docs/DECISIONS.md, docs/SECURITY.md)."
        )
    assert settings.supabase_url is not None
    assert settings.supabase_publishable_key is not None
    return create_client(settings.supabase_url, settings.supabase_publishable_key)


def get_anon_client() -> Client:
    """A fresh, unauthenticated client for guest reads of world-readable
    rows (published claims, careers, pathways, sources) per the RLS
    policies in the migration. Never use this for anything that should
    be scoped to a signed-in user, and never cache the result yourself."""
    return _build_client()


def get_user_scoped_client(user_access_token: str) -> Client:
    """A FRESH client acting AS the signed-in user, for this one request
    only, so RLS applies correctly.

    `user_access_token` is the token issued by Supabase Auth at sign-in —
    obtained per-request from the caller (e.g. an Authorization header),
    never stored, never logged. This is the "pass the signed-in user's
    access token on every request" contract from docs/SECURITY.md; without
    it, RLS `auth.uid()` checks silently evaluate as anonymous, which is a
    security bug, not a convenience default. Equally: never reuse this
    client for a different request or a different user, and never cache
    it — see module docstring for the concurrency bug that pattern caused.
    """
    client = _build_client()
    client.postgrest.auth(user_access_token)
    return client
