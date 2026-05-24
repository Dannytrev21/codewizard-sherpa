"""Phase-4 S2-05 AC-10 — ``consumed_dollars`` is Decimal-exact (no float drift).

ADR-0010 §Tradeoffs row 5 — dollar arithmetic must be exact; ``Decimal``,
not ``float``. The property mints + reconciles 10–50 random Decimal
values per example and asserts the projected ``consumed_dollars`` equals
the Decimal sum exactly. Float-creep (e.g. a ``float`` cast anywhere in
the precharge/reconcile path) would round at the ~15th significant digit
and fail the exact-equality assertion.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.plugins.events import EventLog
from codegenie.types.identifiers import WorkflowId


@given(
    values=st.lists(
        st.decimals(
            min_value=Decimal("0.000001"),
            max_value=Decimal("0.5"),
            places=6,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=10,
        max_size=50,
    ),
)
@settings(max_examples=200, deadline=None)
def test_consumed_dollars_is_decimal_exact_no_float_drift(values: list[Decimal]) -> None:
    """The sum of N Decimal reconciles equals the Decimal sum of the inputs."""
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(root=Path(d), workflow_id=WorkflowId("wf-budget-test"))
        guard = LlmInvocationGuard(
            max_tokens=100_000_000,
            max_dollars=Decimal("100.0"),
            per_call_max_tokens=32_000,
            event_log=log,
        )
        for v in values:
            tok = guard.precharge(requested_tokens=1)
            guard.reconcile(
                tok,
                actual_in=1,
                actual_out=0,
                actual_dollars=v,
            )
        consumed = guard.running_total().consumed_dollars
    assert consumed == sum(values, Decimal("0"))
