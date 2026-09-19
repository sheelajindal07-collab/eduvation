"""AI provider adapter, retrieval, and server-owned citation binding.

Built at M5 ("bounded AI", Lite Build Pack §9) — grounded explanation over retrieved,
published Claims only; no model call before then. Provider is Gemini by
default (docs/DECISIONS.md, owner-confirmed, swappable via the adapter).
Non-negotiables:
no write access to the knowledge base, no access to the student vault, PII
redaction before any external call, 15s timeout, atomic per-request spend
reservation against the caps in docs/SECURITY.md.
"""
