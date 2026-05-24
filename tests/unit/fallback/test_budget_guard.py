"""Phase-4 S2-05 — happy/sad-path unit tests for ``LlmInvocationGuard``.

Covers AC-4 (constructor + defaults), AC-5 (precharge with all four failure
branches + no-partial-mint), AC-6 (reconcile's three branches +
non-negative actuals), AC-7 (running_total conservation laws), AC-14
(deterministic exhaustion boundary), AC-17 (BudgetExceeded structured
typed exception with per-reason numeric typing). The Hypothesis
properties (AC-8/9/10) live next door under ``tests/property/``.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from codegenie.fallback.budget import (
    _DEFAULT_DOLLARS_PER_TOKEN,
    _DEFAULT_MAX_DOLLARS,
    _DEFAULT_MAX_TOKENS,
    _DEFAULT_PER_CALL_MAX_TOKENS,
    BudgetExceeded,
    BudgetReconcileUnknownToken,
    BudgetToken,
    LlmInvocationGuard,
)
from codegenie.plugins.events import (
    BudgetCapExceeded,
    BudgetPrecharged,
    BudgetReconciled,
    BudgetReconciledDuplicate,
    BudgetUnknownTokenReconcile,
    EventLog,
)
from codegenie.types.identifiers import BudgetTokenId, TokenCount, WorkflowId

# --- helpers ----------------------------------------------------------------


@pytest.fixture
def event_log(tmp_path: Path) -> EventLog:
    return EventLog(root=tmp_path, workflow_id=WorkflowId("wf-budget-test"))


def _guard(
    event_log: EventLog,
    *,
    max_tokens: int = 100_000,
    max_dollars: Decimal = Decimal("10.0"),
    per_call_max_tokens: int = 1000,
    dollars_per_token: Decimal = Decimal("0.0001"),
) -> LlmInvocationGuard:
    return LlmInvocationGuard(
        max_tokens=max_tokens,
        max_dollars=max_dollars,
        per_call_max_tokens=per_call_max_tokens,
        event_log=event_log,
        dollars_per_token=dollars_per_token,
    )


def _events_of(log: EventLog, kind: type) -> list[object]:
    return [e for e in log.replay() if isinstance(e, kind)]


# --- AC-4 — constructor + defaults ------------------------------------------


def test_default_construction_uses_adr_0010_values(event_log: EventLog) -> None:
    """ADR-0010 §Decision: max_tokens=250_000, max_dollars=$1.50, per_call_max=32_000."""
    g = LlmInvocationGuard(event_log=event_log)
    snap = g.running_total()
    assert snap.max_tokens == _DEFAULT_MAX_TOKENS == 250_000
    assert snap.max_dollars == _DEFAULT_MAX_DOLLARS == Decimal("1.50")
    # per_call_max isn't on the snapshot; assert via behavioural probe — a
    # request exactly at the per-call cap succeeds, +1 fails.
    g.precharge(_DEFAULT_PER_CALL_MAX_TOKENS)
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(_DEFAULT_PER_CALL_MAX_TOKENS + 1)
    assert exc.value.reason == "per_call_max_exceeded"


def test_constructor_rejects_negative_max_tokens(event_log: EventLog) -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        LlmInvocationGuard(max_tokens=-1, event_log=event_log)


def test_constructor_rejects_negative_max_dollars(event_log: EventLog) -> None:
    with pytest.raises(ValueError, match="max_dollars"):
        LlmInvocationGuard(max_dollars=Decimal("-1"), event_log=event_log)


def test_constructor_rejects_zero_per_call_max(event_log: EventLog) -> None:
    with pytest.raises(ValueError, match="per_call_max_tokens"):
        LlmInvocationGuard(per_call_max_tokens=0, event_log=event_log)


# --- AC-5 — precharge failure branches --------------------------------------


def test_precharge_zero_requested_rejected_as_value_error(event_log: EventLog) -> None:
    g = _guard(event_log)
    with pytest.raises(ValueError, match="requested_tokens"):
        g.precharge(0)


def test_precharge_negative_requested_rejected_as_value_error(event_log: EventLog) -> None:
    g = _guard(event_log)
    with pytest.raises(ValueError, match="requested_tokens"):
        g.precharge(-1)


def test_precharge_per_call_max_exceeded_raises_and_emits(event_log: EventLog) -> None:
    g = _guard(event_log, per_call_max_tokens=500)
    snap_before = g.running_total()
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(501)
    assert exc.value.reason == "per_call_max_exceeded"
    assert exc.value.projected == 501
    assert exc.value.max == 500
    caps = _events_of(event_log, BudgetCapExceeded)
    assert len(caps) == 1
    assert caps[0].reason == "per_call_max_exceeded"  # type: ignore[attr-defined]
    # No partial mint.
    assert g.running_total() == snap_before


def test_precharge_workflow_max_tokens_exceeded(event_log: EventLog) -> None:
    g = _guard(event_log, max_tokens=1000, per_call_max_tokens=1000)
    g.precharge(800)
    snap_before = g.running_total()
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(300)  # within per-call, but 800 + 300 > 1000
    assert exc.value.reason == "workflow_max_tokens_exceeded"
    assert exc.value.projected == 1100
    assert exc.value.max == 1000
    assert g.running_total() == snap_before


def test_precharge_workflow_max_dollars_exceeded(event_log: EventLog) -> None:
    """AC-5 / AC-17 — dollar cap is a hard cap, not decorative.

    Tighten dollars_per_token so the dollar cap fires *before* either
    token cap. This is the regression guard for the previously-missing
    dollar enforcement.
    """
    g = _guard(
        event_log,
        max_tokens=1_000_000,
        max_dollars=Decimal("0.01"),
        per_call_max_tokens=10_000,
        dollars_per_token=Decimal("0.001"),
    )
    # 5 tokens × $0.001 = $0.005 — under $0.01 cap (OK).
    g.precharge(5)
    snap_before = g.running_total()
    # 10 more tokens × $0.001 = $0.010; total projected = $0.015 > $0.01.
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(10)
    assert exc.value.reason == "workflow_max_dollars_exceeded"
    assert isinstance(exc.value.projected, Decimal)
    assert isinstance(exc.value.max, Decimal)
    assert exc.value.max == Decimal("0.01")
    assert g.running_total() == snap_before


def test_precharge_cap_ordering_per_call_beats_workflow(event_log: EventLog) -> None:
    """A request violating both per_call and workflow_max surfaces per_call_max first.

    max_tokens=150, per_call_max=100. Outstanding after the first precharge: 80.
    Request 120:
      per_call: 120 > 100 → first
      workflow: 80 + 120 = 200 > 150 → second (would be) — never surfaced.
    """
    g = _guard(event_log, max_tokens=150, per_call_max_tokens=100)
    g.precharge(80)
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(120)
    assert exc.value.reason == "per_call_max_exceeded"


def test_precharge_cap_ordering_workflow_tokens_beats_dollars(event_log: EventLog) -> None:
    """A request violating workflow_max_tokens AND workflow_max_dollars surfaces
    workflow_max_tokens first."""
    g = _guard(
        event_log,
        max_tokens=100,
        max_dollars=Decimal("0.0001"),
        per_call_max_tokens=500,
        dollars_per_token=Decimal("1.00"),  # tight dollar budget too
    )
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(200)  # exceeds workflow_max_tokens (200>100) AND dollars (200*1=$200>$0.0001)
    assert exc.value.reason == "workflow_max_tokens_exceeded"


def test_precharge_success_emits_one_event_and_mints(event_log: EventLog) -> None:
    g = _guard(event_log)
    tok = g.precharge(100)
    pre = _events_of(event_log, BudgetPrecharged)
    assert len(pre) == 1
    assert pre[0].token_id == tok.id  # type: ignore[attr-defined]
    assert pre[0].precharged_tokens == 100  # type: ignore[attr-defined]


# --- AC-6 — reconcile three branches ----------------------------------------


def test_reconcile_first_call_folds_into_consumed(event_log: EventLog) -> None:
    g = _guard(event_log)
    tok = g.precharge(100)
    g.reconcile(tok, actual_in=40, actual_out=30, actual_dollars=Decimal("0.005"))
    snap = g.running_total()
    assert snap.consumed_tokens == 70
    assert snap.consumed_dollars == Decimal("0.005")
    assert snap.outstanding_tokens == {}
    rec = _events_of(event_log, BudgetReconciled)
    assert len(rec) == 1


def test_reconcile_duplicate_is_noop_and_emits_duplicate_event(event_log: EventLog) -> None:
    g = _guard(event_log)
    tok = g.precharge(100)
    g.reconcile(tok, actual_in=10, actual_out=10, actual_dollars=Decimal("0.001"))
    snap_after_first = g.running_total()
    g.reconcile(tok, actual_in=999, actual_out=999, actual_dollars=Decimal("99"))
    assert g.running_total() == snap_after_first
    dups = _events_of(event_log, BudgetReconciledDuplicate)
    assert len(dups) == 1
    # Exactly one BudgetReconciled — the second call must NOT have emitted one.
    assert len(_events_of(event_log, BudgetReconciled)) == 1


def test_reconcile_unknown_token_raises_and_emits(event_log: EventLog) -> None:
    """AC-6 third branch — a never-precharged token raises + emits."""
    g = _guard(event_log)
    forged = BudgetToken(
        id=BudgetTokenId("0" * 32),
        precharged_tokens=TokenCount(1),
        precharged_dollars=Decimal("0"),
        issued_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    with pytest.raises(BudgetReconcileUnknownToken) as exc:
        g.reconcile(forged, actual_in=1, actual_out=0, actual_dollars=Decimal("0"))
    assert exc.value.token_id == "0" * 32
    unk = _events_of(event_log, BudgetUnknownTokenReconcile)
    assert len(unk) == 1


@pytest.mark.parametrize(
    "field,bad",
    [("actual_in", -1), ("actual_out", -1)],
)
def test_reconcile_negative_int_actuals_rejected(event_log: EventLog, field: str, bad: int) -> None:
    g = _guard(event_log)
    tok = g.precharge(100)
    kwargs: dict[str, int | Decimal] = {
        "actual_in": 1,
        "actual_out": 1,
        "actual_dollars": Decimal("0"),
    }
    kwargs[field] = bad
    with pytest.raises(ValueError, match=field):
        g.reconcile(tok, **kwargs)  # type: ignore[arg-type]


def test_reconcile_negative_actual_dollars_rejected(event_log: EventLog) -> None:
    g = _guard(event_log)
    tok = g.precharge(100)
    with pytest.raises(ValueError, match="actual_dollars"):
        g.reconcile(tok, actual_in=1, actual_out=1, actual_dollars=Decimal("-0.01"))


# --- AC-7 — running_total conservation --------------------------------------


def test_running_total_token_conservation_invariant(event_log: EventLog) -> None:
    g = _guard(event_log, max_tokens=10_000, per_call_max_tokens=5_000)
    g.precharge(2_000)
    tok2 = g.precharge(1_500)
    g.reconcile(tok2, actual_in=1_000, actual_out=400, actual_dollars=Decimal("0.001"))
    snap = g.running_total()
    outstanding_sum = sum(snap.outstanding_tokens.values())
    assert snap.consumed_tokens + outstanding_sum + snap.remaining_tokens == snap.max_tokens


def test_running_total_dollar_conservation_invariant(event_log: EventLog) -> None:
    g = _guard(event_log, max_dollars=Decimal("1.00"), per_call_max_tokens=500)
    g.precharge(200)  # outstanding dollars added
    tok2 = g.precharge(100)
    g.reconcile(tok2, actual_in=50, actual_out=50, actual_dollars=Decimal("0.02"))
    snap = g.running_total()
    assert (
        snap.consumed_dollars + snap.outstanding_dollars + snap.remaining_dollars
        == snap.max_dollars
    )


def test_running_total_is_pure_no_mutation(event_log: EventLog) -> None:
    """AC-7 (iv) — two successive calls return equal snapshots; mutation needs a
    real op."""
    g = _guard(event_log)
    snap_a = g.running_total()
    snap_b = g.running_total()
    assert snap_a == snap_b
    g.precharge(100)
    snap_c = g.running_total()
    assert snap_c != snap_a


def test_running_total_consumed_dollars_is_decimal_exact(event_log: EventLog) -> None:
    """AC-7 (iii) — pin Decimal exactness with a deliberately float-unrepresentable value."""
    g = _guard(event_log)
    tok = g.precharge(100)
    g.reconcile(tok, actual_in=1, actual_out=0, actual_dollars=Decimal("0.000123"))
    assert g.running_total().consumed_dollars == Decimal("0.000123")


# --- AC-14 — deterministic exhaustion boundary ------------------------------


def test_deterministic_exhaustion_first_k_succeed_then_one_raises(
    event_log: EventLog,
) -> None:
    """``max_tokens = k × per_call_max_tokens`` ⇒ exactly k precharges succeed."""
    k = 5
    per_call = 100
    g = _guard(event_log, max_tokens=k * per_call, per_call_max_tokens=per_call)
    minted_ids: list[str] = []
    for _ in range(k):
        snap_before = g.running_total()
        consumed_plus_outstanding = snap_before.consumed_tokens + sum(
            snap_before.outstanding_tokens.values()
        )
        # AC-14 (ii) — invariant holds at every step BEFORE precharge.
        assert consumed_plus_outstanding + per_call <= snap_before.max_tokens
        tok = g.precharge(per_call)
        minted_ids.append(tok.id)
    assert len(minted_ids) == k
    snap_at_cap = g.running_total()
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(per_call)
    assert exc.value.reason == "workflow_max_tokens_exceeded"
    # AC-14 (iii) — rejected call leaves running_total byte-identical.
    assert g.running_total() == snap_at_cap


# --- AC-17 — BudgetExceeded structured typing -------------------------------


def test_budget_exceeded_per_call_carries_int_fields(event_log: EventLog) -> None:
    g = _guard(event_log, per_call_max_tokens=10)
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(100)
    assert exc.value.reason == "per_call_max_exceeded"
    assert isinstance(exc.value.projected, int)
    assert isinstance(exc.value.max, int)


def test_budget_exceeded_workflow_tokens_carries_int_fields(event_log: EventLog) -> None:
    g = _guard(event_log, max_tokens=10, per_call_max_tokens=100)
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(50)
    assert exc.value.reason == "workflow_max_tokens_exceeded"
    assert isinstance(exc.value.projected, int)
    assert isinstance(exc.value.max, int)


def test_budget_exceeded_workflow_dollars_carries_decimal_fields(
    event_log: EventLog,
) -> None:
    """AC-17 — the dollar-cap regression guard: must be impossible to pass without
    a real projected-dollars check."""
    g = _guard(
        event_log,
        max_dollars=Decimal("0.001"),
        dollars_per_token=Decimal("0.01"),
        per_call_max_tokens=1000,
        max_tokens=1_000_000,
    )
    with pytest.raises(BudgetExceeded) as exc:
        g.precharge(5)
    assert exc.value.reason == "workflow_max_dollars_exceeded"
    assert isinstance(exc.value.projected, Decimal)
    assert isinstance(exc.value.max, Decimal)
    assert exc.value.max == Decimal("0.001")
    # AC-17 (iii) — matching BudgetCapExceeded event with same reason emitted
    # BEFORE the raise (replay() shows it).
    caps = _events_of(event_log, BudgetCapExceeded)
    assert len(caps) == 1
    assert caps[0].reason == "workflow_max_dollars_exceeded"  # type: ignore[attr-defined]


# --- Defaults reachable as constants for downstream stories -----------------


def test_default_dollars_per_token_constant_exposed() -> None:
    """S7-04's ``plugin.yaml`` overrides this; the constant must exist."""
    assert _DEFAULT_DOLLARS_PER_TOKEN > Decimal("0")
