"""Shared FastAPI dependencies for route handlers."""

from __future__ import annotations

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


def get_db_client(authorization: str | None = Header(default=None)) -> Client:
    """Guest (anon-key) client by default; a signed-in user's RLS-scoped
    client when a valid `Authorization: Bearer <token>` header is present.

    Never returns an owner/service-role client — that role has no path
    into request-handling code at all (docs/SECURITY.md).
    """
    token = _bearer_token(authorization)
    if token:
        return get_user_scoped_client(token)
    return get_anon_client()


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


def require_auth(authorization: str | None = Header(default=None)) -> AuthedSession:
    """For routes where guest access doesn't make sense at all (a guest
    has no plans to save) — 401s cleanly rather than silently falling
    back to anon and returning confusing empty results."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return AuthedSession(client=get_user_scoped_client(token), access_token=token)
