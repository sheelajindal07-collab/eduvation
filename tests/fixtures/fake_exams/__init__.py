"""A tiny, fake `app.rules.exams`-shaped package used only by
tests/unit/test_ruleset.py to exercise `discover_rule_sets`'s real
`pkgutil` discovery and production-mode review filtering without
depending on any real exam module (RULES-5/6 land separately). Never
imported by application code."""
