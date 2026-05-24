"""Phase-4 S2-05 — Hypothesis properties for ``BudgetToken`` minting and
``reconcile`` idempotence.

AC-8 — every ``precharge`` mints a fresh ``uuid4().hex`` ``BudgetTokenId``;
no collisions and no MAC-leaking ``uuid1`` substitution (the 32-hex regex
catches both a constant id and a dashed-uuid str).

AC-9 — ``reconcile`` is idempotent on ``token.id``: the second call with
*different* actuals does not double-count and emits exactly one
:class:`BudgetReconciledDuplicate`.

**Footgun guard.** A pytest ``tmp_path`` fixture is resolved once per
test function and reused across every Hypothesis-generated example; an
``EventLog`` built on it would accumulate events across examples and the
"exactly one duplicate" assertion would see N. The ``_fresh_guard`` helper
opens a fresh ``tempfile.TemporaryDirectory()`` inside each example so the
log is isolated. The S2-05 hardening notes pin this discipline (the same
trap S2-01 / S2-02 / S2-03 / S2-04 each had to harden against).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.plugins.events import BudgetReconciledDuplicate, EventLog
from codegenie.types.identifiers import WorkflowId

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


@contextmanager
def _fresh_guard(**kwargs: object) -> Iterator[LlmInvocationGuard]:
    """A guard whose EventLog is isolated to a per-example temp dir."""
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(root=Path(d), workflow_id=WorkflowId("wf-budget-test"))
        yield LlmInvocationGuard(event_log=log, **kwargs)  # type: ignore[arg-type]


@given(n=st.integers(min_value=1, max_value=50))
@settings(max_examples=500, deadline=None)
def test_each_precharge_mints_a_fresh_unique_token_id(n: int) -> None:
    """AC-8 — `n` precharges yield `n` distinct 32-hex token ids."""
    with _fresh_guard(
        max_tokens=10_000_000,
        max_dollars=Decimal("100.00"),
        per_call_max_tokens=32_000,
    ) as guard:
        tokens = [guard.precharge(requested_tokens=1000) for _ in range(n)]
    # No collisions — catches a constant-id implementation.
    assert len({t.id for t in tokens}) == n
    # 32 lowercase hex — catches uuid1 (dashes), str(uuid4()) (dashes),
    # or a monotonic counter. ADR-0010 §Consequences names uuid4.
    assert all(_HEX32.match(t.id) for t in tokens)


@given(actual_pair=st.tuples(st.integers(0, 500), st.integers(0, 500)))
@settings(max_examples=500, deadline=None)
def test_reconcile_is_idempotent_on_token_id(actual_pair: tuple[int, int]) -> None:
    """AC-9 — second reconcile with different actuals is a no-op + one dup event."""
    actual_in, actual_out = actual_pair
    with tempfile.TemporaryDirectory() as d:
        log = EventLog(root=Path(d), workflow_id=WorkflowId("wf-budget-test"))
        guard = LlmInvocationGuard(
            max_tokens=100_000,
            max_dollars=Decimal("10.0"),
            per_call_max_tokens=32_000,
            event_log=log,
        )
        token = guard.precharge(requested_tokens=1000)

        guard.reconcile(
            token,
            actual_in=actual_in,
            actual_out=actual_out,
            actual_dollars=Decimal("0.001"),
        )
        snap_after_first = guard.running_total()
        # AC-9 (i) — first reconcile must actually move state.
        assert snap_after_first.consumed_tokens == actual_in + actual_out
        assert snap_after_first.consumed_dollars == Decimal("0.001")

        # AC-9 (ii) — second reconcile with DIFFERENT actuals must not double-count.
        guard.reconcile(
            token,
            actual_in=actual_in + 100,
            actual_out=actual_out + 100,
            actual_dollars=Decimal("0.999"),
        )
        snap_after_second = guard.running_total()
        events = list(log.replay())

    assert snap_after_second == snap_after_first
    # AC-9 (iii) — exactly one BudgetReconciledDuplicate fired.
    dupes = [e for e in events if isinstance(e, BudgetReconciledDuplicate)]
    assert len(dupes) == 1
