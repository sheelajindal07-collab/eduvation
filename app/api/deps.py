"""Shared FastAPI dependencies for the explore/compare routes."""

from __future__ import annotations

from fastapi import Header
from supabase import Client

from app.db import get_anon_client, get_user_scoped_client


def get_db_client(authorization: str | None = Header(default=None)) -> Client:
    """Guest (anon-key) client by default; a signed-in user's RLS-scoped
    client when a valid `Authorization: Bearer <token>` header is present.

    Never returns an owner/service-role client — that role has no path
    into request-handling code at all (docs/SECURITY.md).
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return get_user_scoped_client(token.strip())
    return get_anon_client()
