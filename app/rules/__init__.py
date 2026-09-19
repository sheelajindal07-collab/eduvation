"""Deterministic decision engines: eligibility, cost, timeline, reservation.

No model tokens. M2 ("deterministic intelligence", Lite Build Pack §9),
with test cases per exam from the content track. See docs/DATA.md for the
three-outcome eligibility model and the three-amount cost model this
module implements.

- `eligibility.py`: built. Composable, source-cited criteria; an unknown
  input is `insufficient_information`, never `does_not_meet`.
- Cost, timeline and reservation engines: not yet built.
"""
