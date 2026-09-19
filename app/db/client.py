"""Supabase client factory — RLS-aware, restricted role only.

Non-negotiable (docs/SECURITY.md, Lite Build Pack §4): the application never
connects as the Supabase owner/service role for a user-facing request.
Every request-scoped client carries the *signed-in user's own access
token*, so Postgres row-level security is what actually enforces access —
not application code. A client with no user token (e.g. for public
knowledge-base reads on behalf of a guest) uses the anon/publishable key
only, which the RLS policies in db/migrations/0001_init.sql already treat
as "no special access" (world-readable rows only).

Schema is applied via db/migrations/*.sql on the owner's own Supabase
project (see docs/DECISIONS.md) — never through an agent's management-API
access, and never by editing tables from a dashboard.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY are unset.

    Callers should catch this and degrade gracefully (docs/UI.md's
    "difficult states" — e.g. explore/compare can still show whatever is
    cached, or a clear "not available yet" rather than a stack trace).
    """


@lru_cache
def _anon_client() -> Client:
    """A client using only the public/anon key — no user context.

    Suitable for guest reads of world-readable rows (published claims,
    careers, pathways, sources) per the RLS policies in the migration.
    Never use this for anything that should be scoped to a signed-in user.
    """
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
    """Public-zone reads only. See `_anon_client` docstring."""
    return _anon_client()


def get_user_scoped_client(user_access_token: str) -> Client:
    """A client acting AS the signed-in user, for RLS to apply correctly.

    `user_access_token` is the token issued by Supabase Auth at sign-in —
    obtained per-request from the caller (e.g. an Authorization header),
    never stored, never logged. This is the "pass the signed-in user's
    access token on every request" contract from docs/SECURITY.md; without
    it, RLS `auth.uid()` checks silently evaluate as anonymous, which is a
    security bug, not a convenience default.
    """
    client = get_anon_client()
    client.postgrest.auth(user_access_token)
    return client
