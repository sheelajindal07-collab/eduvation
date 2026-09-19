"""Supabase client + RLS-aware session helper.

M1 ("data foundation and RLS tests", Annex E.3). See `client.py` for the
factory functions and the restricted-role/user-token contract
(docs/SECURITY.md, Annex F.2), and `../../db/migrations/0001_init.sql` for
the schema and RLS policies this module assumes. No live connection is
exercised from this repo or by any agent — docs/DECISIONS.md records why
(owner-managed Supabase account, MCP management tools not used here).
"""

from app.db.client import (
    SupabaseNotConfiguredError,
    get_anon_client,
    get_user_scoped_client,
)

__all__ = [
    "SupabaseNotConfiguredError",
    "get_anon_client",
    "get_user_scoped_client",
]
