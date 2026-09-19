"""Shared FastAPI dependencies for route handlers.

Both dependencies below are `yield`-based, not plain return, so FastAPI
runs the `finally` cleanup after the response is sent (data-security-
reviewer finding, 2026-09-19): `app/db/client.py`'s fix for the
client-sharing bug makes every call construct a genuinely fresh,
unshared `Client` — correct for cross-user isolation, but each one owns
its own `httpx.Client` connection pool that nothing was closing. A
`supabase.Client` has no `.close()` of its own; the actual handle is
`client.postgrest.aclose()` (a synchronous method despite the name —
postgrest-py's sync client mirrors the async one's method names), which
closes the underlying `httpx.Client`/socket pool. Without this, every
DB-touching request leaked one connection-pool object, relying on
refcounting GC (which never proactively closes sockets) to reclaim it —
fine at pilot scale today, but exactly the kind of thing that degrades
under sustained load or a small VPS's file-descriptor limit.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Header, HTTPException
from supabase import Client

from app.db import get_anon_client, get_user_scoped_client


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def get_db_client(authorization: str | None = Header(default=None)) -> Iterator[Client]:
    """Guest (anon-key) client by default; a signed-in user's RLS-scoped
    client when a valid `Authorization: Bearer <token>` header is present.

    Never returns an owner/service-role client — that role has no path
    into request-handling code at all (docs/SECURITY.md).
    """
    token = _bearer_token(authorization)
    client = get_user_scoped_client(token) if token else get_anon_client()
    try:
        yield client
    finally:
        client.postgrest.aclose()


@dataclass(frozen=True)
class AuthedSession:
    """A signed-in caller's RLS-scoped client plus their raw access
    token. The token is carried alongside the client (not just baked
    into it) because `client.auth.get_user()` needs it passed explicitly
    — `get_user_scoped_client` only attaches the token to the postgrest
    (database) layer, not the auth client's own session state, so a bare
    `client.auth.get_user()` with no argument would look for a session
    that was never established on this fresh, unshared client."""

    client: Client
    access_token: str


def require_auth(authorization: str | None = Header(default=None)) -> Iterator[AuthedSession]:
    """For routes where guest access doesn't make sense at all (a guest
    has no plans to save) — 401s cleanly rather than silently falling
    back to anon and returning confusing empty results."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")
    client = get_user_scoped_client(token)
    try:
        yield AuthedSession(client=client, access_token=token)
    finally:
        client.postgrest.aclose()
