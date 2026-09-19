"""Deterministic decision engines: eligibility, cost, timeline, reservation.

No model tokens. M2 ("deterministic intelligence", Lite Build Pack §9),
with test cases per exam from the content track. See docs/DATA.md for the
three-outcome eligibility model and the three-amount cost model this
module implements.

- `eligibility.py`: built. Composable, source-cited criteria; an unknown
  input is `insufficient_information`, never `does_not_meet`.
- `cost.py`: built. Four amounts that never merge — verified charges
  (summed from fee-component claims, `None` if any is missing, never a
  silently-partial sum), estimated extras, confirmed assistance (the
  only thing that reduces what a student owes), and potential
  assistance (informational only — never subtracted).
- Timeline and reservation engines: not yet built.
"""
