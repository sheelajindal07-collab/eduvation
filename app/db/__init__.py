"""Supabase (Mumbai) client + RLS-aware session helper.

Built at M1 ("data foundation and RLS tests", Annex E.3). The application
must connect as a restricted role and pass the signed-in user's access
token on every request so RLS is actually enforced (docs/SECURITY.md,
Annex F.2) — never the Supabase owner/service role for user-facing
requests. No live connection exists yet; docs/DECISIONS.md tracks
provisioning status.
"""
