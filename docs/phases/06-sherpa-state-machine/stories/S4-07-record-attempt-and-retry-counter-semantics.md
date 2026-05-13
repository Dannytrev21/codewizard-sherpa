# Story S4-07 — Implement `record_attempt` node + per-gate retry-counter semantics

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0003 (per-gate retry counter; same-signature flake short-circuit at the EDGE, but counter writes here), ADR-0007 (BLAKE3 chain extension on every Phase 6 chain write), ADR-0002 (`model_copy(update=...)`)

## Context

`record_attempt` is the **load-bearing semantic node** of the retry loop. Three rules must hold simultaneously, and a misfire in any one breaks both Phase 5 parity (S7-02) and the HITL exit-criterion test (S7-01):

1. **Per-gate scoping** (ADR-0003 / ADR-0014). `retry_count` is `1` on the first attempt at a given `current_gate_id`, then `2`, `3`, ... incrementally. When the *previous* node (`validate_in_sandbox`) wrote a *different* `current_gate_id` than is currently on the ledger's prior history, `record_attempt` resets the counter to `1`.
2. **Cumulative within the same gate.** Three consecutive failures at `stage6_validate` produce `retry_count = 1, 2, 3` (matching Phase 5's `for attempt in range(1, max_attempts + 1)`).
3. **Append to `prior_attempts` and extend the BLAKE3 chain.** Delegates to Phase 5's `RetryLedger.record(Attempt(attempt_id=retry_count, ...))`. Result: new `prior_attempts` list (immutable, `[*old, AttemptSummary(...)]`), new `chain_head` bytes.

Same-signature flake detection is **not** done here — it's the responsibility of `route_after_attempt` (S3-02). Don't put it in two places.

The parametrized TDD test enumerates the cartesian of (`current_gate_id` change vs same, `outcome.passed`, `outcome.retryable`, prior `retry_count`) to make sure the semantics survive a future refactor.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5` — `record_attempt` row; `../phase-arch-design.md §Control flow Step 12`; `../phase-arch-design.md §Data model — VulnLedger.retry_count` (reads/writes annotations)
- **Phase ADRs:** `../ADRs/0003-per-gate-retry-counter-scope.md` — read in full; `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — explains chain extension on `record` and `put`
- **Production ADRs:** ADR-0014 (three-retry default per gate transition) — the title literally says "per gate"; that's the contract this story honors
- **Prior phases:** `../../05-sandbox-trust-gates/final-design.md §7 RetryLedger` — `RetryLedger.record(Attempt(...))` shape and BLAKE3 chain extension semantics; `../../05-sandbox-trust-gates/final-design.md` — `AttemptSummary` shape (`attempt_id`, `sandbox_run_id`, `failing_signals: list[Literal[...]]`, `prior_failure_summary: str`, `evidence_paths: dict[str, Path]`)
- **Source design:** `../final-design.md §Synthesis ledger row 2 "Retry-counter scope"`; `../final-design.md §Component 5`

## Goal

Land `graph/nodes/record_attempt.py` that delegates to Phase 5's `RetryLedger.record(...)`, implements **per-gate retry-counter scope semantics** (reset on `current_gate_id` change, increment otherwise), appends to `prior_attempts`, and extends `chain_head`.

## Acceptance criteria

- [ ] `graph/nodes/record_attempt.py` exports `record_attempt(state: VulnLedger) -> VulnLedger`, decorated with `@audited_node`, calling `RetryLedger.record(Attempt(attempt_id=new_retry_count, sandbox_run_id=..., signals=..., outcome=state.last_outcome, prior_failure_summary=...))` and threading the returned new `chain_head` onto the ledger.
- [ ] `retry_count` semantics: `state.retry_count + 1` when the gate id is unchanged from `prior_attempts[-1]`'s gate id; `1` when changed (or when `prior_attempts` is empty).
- [ ] A **parametrized** TDD test enumerates these branches: `(prior_gate_id, current_gate_id) ∈ {(None, "g1"), ("g1", "g1"), ("g1", "g2")}` crossed with `(prior_retry_count) ∈ {0, 1, 2}`. Expected results table written in the test as the assertion data.
- [ ] `prior_attempts` on the returned ledger is `state.prior_attempts + [new_summary]` (new list, not mutation; the audit hook from S4-01 would catch otherwise).
- [ ] `chain_head` is updated to whatever `RetryLedger.record` returns.
- [ ] Emits one `GraphEvent(kind="exit", fields={"attempt_id": str, "passed": str, "retry_count": str, "current_gate_id": str})`.
- [ ] `mypy --strict`, `ruff`, `pytest`, fence-CI all green.

## Implementation outline

1. Read `src/codegenie/gates/retry_ledger.py` to confirm `RetryLedger.record(...)` signature and return type (should return either the new `chain_head` or an `Attempt` carrying it). If `RetryLedger.record` does *not* return the chain head, surface it — S2-02 already needed `head_from_phase5(run_id)`; combine the read.
2. Build a helper `_compute_next_retry_count(state) -> int`:
   ```python
   def _compute_next_retry_count(state: VulnLedger) -> int:
       if not state.prior_attempts:
           return 1
       prev_gate = state.prior_attempts[-1].current_gate_id  # if AttemptSummary carries it
       if prev_gate != state.current_gate_id:
           return 1
       return state.retry_count + 1
   ```
   If `AttemptSummary` does **not** carry `current_gate_id`, surface — this is a Phase 5 design gap that must be closed before this story ships (otherwise the parity test can't pass).
3. Write the parametrized red TDD test first.
4. Implement the node (~ 45 LOC): compute next retry_count, build `AttemptSummary(...)`, call `RetryLedger.record(...)`, build new state via `model_copy(update={"prior_attempts": [*state.prior_attempts, new_summary], "retry_count": next_count, "chain_head": new_head, "last_node": "record_attempt", "events": [...]})`.
5. Run the parametrized test; confirm green at all parametric rows.

## TDD plan — red / green / refactor

```python
# tests/graph/test_nodes/test_record_attempt.py
import pytest
from unittest.mock import MagicMock
from codegenie.graph.nodes.record_attempt import record_attempt
from tests.graph.test_nodes.conftest import make_ledger, fake_attempt_summary


# Expected: (prior_gate_id, current_gate_id, prior_retry_count) -> expected_next_retry_count
RETRY_TABLE = [
    # No prior attempts: always 1
    (None,  "g1", 0, 1),
    # Same gate: increment
    ("g1",  "g1", 1, 2),
    ("g1",  "g1", 2, 3),
    # Gate change: reset to 1
    ("g1",  "g2", 1, 1),
    ("g1",  "g2", 2, 1),
]


@pytest.mark.parametrize("prior_gate,curr_gate,prior_count,expected_next", RETRY_TABLE)
def test_retry_count_per_gate_semantics(mock_phase5, prior_gate, curr_gate, prior_count, expected_next):
    """ADR-0003 INTENT: counter must reset on gate change, increment within.
    This test is the parity canary against Phase 5's for-loop."""
    # Arrange
    if prior_gate is None:
        prior_attempts = []
    else:
        prior_attempts = [fake_attempt_summary(n=prior_count, current_gate_id=prior_gate)]

    outcome = MagicMock(passed=False, retryable=True, failing_signals=["tests"])
    ledger = make_ledger(
        prior_attempts=prior_attempts,
        retry_count=prior_count,
        current_gate_id=curr_gate,
        last_outcome=outcome,
        chain_head=b"\x01" * 32,
    )
    mock_phase5["RetryLedger"].return_value.record.return_value = b"\x02" * 32

    # Act
    out = record_attempt(ledger)

    # Assert
    assert out.retry_count == expected_next
    # And the new attempt is on prior_attempts
    assert len(out.prior_attempts) == len(prior_attempts) + 1
    # And the chain head advanced (BLAKE3 chain property)
    assert out.chain_head == b"\x02" * 32 and out.chain_head != b"\x01" * 32


def test_record_attempt_appends_not_mutates(mock_phase5):
    """Audit hook (S4-01) would catch in-place .append, but verify model_copy semantics."""
    outcome = MagicMock(passed=True, retryable=False, failing_signals=[])
    ledger = make_ledger(prior_attempts=[], last_outcome=outcome, current_gate_id="g1")
    mock_phase5["RetryLedger"].return_value.record.return_value = b"\xff" * 32

    out = record_attempt(ledger)

    assert out is not ledger
    assert out.prior_attempts is not ledger.prior_attempts  # different list object
    assert len(ledger.prior_attempts) == 0  # original untouched


def test_passed_outcome_increments_but_does_not_reset(mock_phase5):
    """A passing attempt is still an attempt; counter continues to advance until next gate."""
    outcome = MagicMock(passed=True, retryable=False, failing_signals=[])
    ledger = make_ledger(prior_attempts=[fake_attempt_summary(n=2, current_gate_id="g1")],
                         retry_count=2, current_gate_id="g1", last_outcome=outcome,
                         chain_head=b"a" * 32)
    mock_phase5["RetryLedger"].return_value.record.return_value = b"b" * 32

    out = record_attempt(ledger)
    assert out.retry_count == 3  # same gate, so +1 — even on a pass
```

**Red:** Module missing → all parametric rows fail.
**Green:** Implement; all rows pass.
**Refactor:** Confirm `_compute_next_retry_count` is named cleanly and exported (might also be useful in `await_human` for the HITL-continue reset; review against S4-08 before committing).

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/nodes/record_attempt.py` | New |
| `tests/graph/test_nodes/test_record_attempt.py` | New (TDD red, parametrized) |
| `tests/graph/test_nodes/conftest.py` | Extend `fake_attempt_summary` to accept `current_gate_id` if not already |

## Out of scope

- Same-signature flake detection — owned by `route_after_attempt` (S3-02). Do NOT put it here.
- HITL `continue` resetting `retry_count` to 0 — owned by `await_human` (S4-08).
- BLAKE3 chain *integrity* check on read — owned by `AuditedSqliteSaver.aget_tuple` (S2-03). This node only *extends* the chain on write.
- Changing `RetryLedger.record`'s signature — Phase 5's contract; additive only.
- Concurrency safety of the chain-write — the shared `threading.Lock` is set up in S2-02.

## Notes for the implementer

- **This is the single node where retry-counter bugs hide silently.** A failing `_compute_next_retry_count` produces a Phase 5 parity diff that won't surface until S7-02 runs (slow, integration-tier). Get the parametric table green here first.
- If `AttemptSummary` (Phase 5 Pydantic model) doesn't carry `current_gate_id`, this is a Phase 5 gap — surface it. The parity test S7-02 *requires* that the gate id is reproducible from `prior_attempts` alone (otherwise the byte-identical comparison fails on the second gate transition).
- The `prior_failure_summary` field on `AttemptSummary` is sanitized text from Phase 5 (`FenceWrapper`, ≤ 4 KB). Do not modify in this node — pass through whatever Phase 5 produced.
- `evidence_paths` is `dict[str, Path]` — Pydantic will JSON-serialize via `model_dump(mode="json")` at checkpoint time; S1-02's golden fixture should cover this.
- The new `chain_head` returned from `RetryLedger.record` is the canonical "next link" — it must be threaded into `state.chain_head` so that `AuditedSqliteSaver.put` reads it on the next checkpoint write. Forgetting this breaks chain continuity, and S2-03's adversarial test fires `AuditChainCorrupted` on resume.
- p50 ≤ 20 ms per `../phase-arch-design.md §Component 5` — most of that is the BLAKE3 hash + `O_APPEND` line write.
