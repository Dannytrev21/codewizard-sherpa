# Story S2-02 — Pre-execute marker `record_pre_execute` + JSONL ordering (Gap 1)

**Step:** Step 2 — Implement `RetryLedger` and audit-chain extension
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0007, ADR-0005

## Context

`SandboxClient.execute` is **not** idempotent (image pulls, live grype, new `sandbox_run_id` on every call). If Phase 6's worker dies between `execute` returning and `RetryLedger.record` writing the attempt, a resume has no record an execute happened — and would re-run, paying full sandbox + LLM-token cost. ADR-0007 closes Gap 1 by introducing a two-phase write: a `"pre_execute"` JSONL marker chained into the BLAKE3 chain *before* `client.execute`, followed by the normal `"attempt"` line after. Phase 5 ships the marker; Phase 6 ships the resume policy (`SandboxResumeBehavior`). This story implements the marker surface and the ordering invariant; the `GateRunner` call-site that uses it lands in S5-02.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 1` — full gap statement and the `record_pre_execute` improvement spec.
  - `../phase-arch-design.md §Component design — RetryLedger` — `Internal structure` lists `record_pre_execute` alongside `record`.
  - `../phase-arch-design.md §Process view — Retry-recovers sequence` — order of operations between `RetryLedger`, `GateRunner`, and `SandboxClient`.
  - `../phase-arch-design.md §Open questions §8` — re-execute is the Phase 5 default; `SandboxResumeBehavior` is Phase 6's call.
- **Phase ADRs:**
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — the canonical contract for this story; pay attention to the row-type discrimination (`"pre_execute"` vs `"attempt"`) and the requirement that the marker is BLAKE3-chained.
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — the marker shape becomes part of the chain; chain-compat regen applies if the row shape changes.
- **Production ADRs:**
  - `../../../production/adrs/0016-checkpointer-backend.md` — the Phase 6 surface this contract serves.
- **Source design:**
  - `../final-design.md §New ADRs implied — ADR-P5-007`.
- **Existing code:**
  - `src/codegenie/gates/retry_ledger.py` (from S2-01) — extend with `record_pre_execute`; reuse `_canonical_json` and `_compute_chain_hash` module helpers.

## Goal

Add `RetryLedger.record_pre_execute(attempt_id, sandbox_spec_hash)` that writes a BLAKE3-chained `{"type": "pre_execute", ...}` JSONL line immediately before the matching `"attempt"` line, with golden-file ordering and chain-link tests.

## Acceptance criteria

- [ ] `RetryLedger.record_pre_execute(attempt_id: int, sandbox_spec_hash: str) -> None` writes one JSONL line of shape `{"type": "pre_execute", "attempt_id": <int>, "sandbox_spec_hash": <hex>, "started_at": <ISO-8601 UTC>, "prev_hash": <hex>, "chain_hash": <hex>}` (canonical sorted-keys JSON, fsynced like `record`).
- [ ] Existing `record(attempt)` continues to write `{"type": "attempt", ...}` — the `"type"` discriminator is added to every line by this story (golden file from S2-01 regenerated as part of this story's commit).
- [ ] `record_pre_execute` chains from `head()` and `record(attempt)` then chains from the just-written marker's `chain_hash` — i.e., the next `record(attempt)` sees `prev_hash == <marker_chain_hash>`.
- [ ] `RetryLedger.attempts() -> list[Attempt]` still returns only `"attempt"` rows. A new `RetryLedger.entries() -> list[LedgerEntry]` returns both `"pre_execute"` and `"attempt"` rows in file order, typed as a `LedgerEntry = PreExecuteMarker | Attempt` discriminated union on `"type"`.
- [ ] Golden-file ordering test (`tests/gates/test_pre_execute_marker.py::test_jsonl_ordering`) — calling `record_pre_execute(1, "<hash>")` then `record(attempt=Attempt(attempt_id=1, ...))` writes exactly two lines in that order, and the golden file `tests/golden/attempts_jsonl_pre_execute_then_attempt.jsonl` is byte-equal (after substituting deterministic timestamps + UUID + hash).
- [ ] A `record_pre_execute` followed by a *different* attempt's `record` (`attempt_id` mismatched) raises `LedgerAttemptOutOfOrder` before writing.
- [ ] An orphan `pre_execute` marker (no following `attempt`) is **not** corruption: `entries()` returns the marker; `attempts()` returns nothing extra; the chain is still verifiable.
- [ ] Calling `record_pre_execute` twice for the same `attempt_id` without an intervening `record` raises `LedgerAttemptOutOfOrder` (no double-marker).
- [ ] `tests/schema/test_objective_signals_static.py` and `tests/schema/test_audit_chain_tamper.py` remain green (no banned substring; tamper on marker line raises `AuditChainCorrupted` with `entry_type="pre_execute"`).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/gates`, `pytest tests/gates/test_pre_execute_marker.py` pass.

## Implementation outline

1. Add a frozen Pydantic model `PreExecuteMarker` to `src/codegenie/gates/retry_ledger.py` (or `contract.py` if S1-04's discriminated union already lives there): `type: Literal["pre_execute"] = "pre_execute"`, `attempt_id: int`, `sandbox_spec_hash: str`, `started_at: datetime`, `prev_hash: str`, `chain_hash: str`.
2. Update `Attempt` (in `gates/contract.py`) to add `type: Literal["attempt"] = "attempt"` as the first field so canonical JSON always serializes `"type"` first and the discriminator is unambiguous.
3. Define `LedgerEntry = Annotated[PreExecuteMarker | Attempt, Field(discriminator="type")]`.
4. Implement `RetryLedger.record_pre_execute`:
   - Validate `attempt_id == self._next_attempt_id` AND `self._marker_pending is False`; otherwise raise `LedgerAttemptOutOfOrder`.
   - Build `PreExecuteMarker(type="pre_execute", attempt_id, sandbox_spec_hash, started_at=now_utc(), prev_hash=self.head().hex(), chain_hash="00"*32)`.
   - Compute `chain_hash` via the shared helper, rewrite the field, append + fsync.
   - Set `self._marker_pending = True`; `_last_chain_hash` updates to the marker's hash.
5. Extend `record(attempt)`:
   - If `self._marker_pending`, allow `attempt_id` to equal the marker's `attempt_id`; the next `prev_hash` chains from the marker.
   - After successful append, set `self._marker_pending = False` and increment `_next_attempt_id`.
6. Add `entries() -> list[LedgerEntry]` reading every line and discriminating on `"type"`; reuse the chain-replay logic.
7. Add `attempts()` filter on `entry.type == "attempt"` (it already returns only attempts; just be explicit).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_pre_execute_marker.py`

```python
# tests/gates/test_pre_execute_marker.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from codegenie.gates.errors import AuditChainCorrupted, LedgerAttemptOutOfOrder
from codegenie.gates.retry_ledger import RetryLedger
from tests.gates.conftest import make_attempt  # factory from S2-01


def test_pre_execute_marker_precedes_attempt_and_chains(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)

    ledger.record_pre_execute(attempt_id=1, sandbox_spec_hash="ab" * 32)
    ledger.record(make_attempt(1, prev_hash=ledger.head().hex()))

    lines = (tmp_path / "gates" / "stage6_validate" / "attempts.jsonl").read_text().splitlines()
    assert len(lines) == 2, "marker + attempt = 2 lines"
    marker, attempt = json.loads(lines[0]), json.loads(lines[1])
    assert marker["type"] == "pre_execute"
    assert attempt["type"] == "attempt"
    assert marker["attempt_id"] == attempt["attempt_id"] == 1
    assert attempt["prev_hash"] == marker["chain_hash"], (
        "attempt must chain from the marker, not the marker's prev_hash"
    )


def test_orphan_marker_is_visible_via_entries_not_attempts(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record_pre_execute(attempt_id=1, sandbox_spec_hash="cd" * 32)

    assert ledger.attempts() == []
    entries = ledger.entries()
    assert [e.type for e in entries] == ["pre_execute"]
    assert entries[0].sandbox_spec_hash == "cd" * 32


def test_double_marker_without_matching_attempt_raises(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record_pre_execute(attempt_id=1, sandbox_spec_hash="ef" * 32)

    with pytest.raises(LedgerAttemptOutOfOrder):
        ledger.record_pre_execute(attempt_id=1, sandbox_spec_hash="ef" * 32)


def test_tampered_marker_is_caught_on_entries_replay(tmp_path: Path) -> None:
    ledger = RetryLedger(run_dir=tmp_path, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record_pre_execute(attempt_id=1, sandbox_spec_hash="11" * 32)

    jsonl = tmp_path / "gates" / "stage6_validate" / "attempts.jsonl"
    jsonl.write_text(jsonl.read_text().replace("11" * 32, "22" * 32))

    with pytest.raises(AuditChainCorrupted) as exc:
        ledger.entries()
    assert 'entry_type="pre_execute"' in str(exc.value) or "pre_execute" in str(exc.value)
```

### Green — make it pass

Add `PreExecuteMarker` model, the discriminated `LedgerEntry` union, the `record_pre_execute` method (chained via the shared helper), and the `entries()` reader. The shared `_compute_chain_hash` helper from S2-01 is reused unchanged; the only ordering invariant is the `_marker_pending` boolean preventing a second marker for the same `attempt_id`.

### Refactor — clean up

- Lock the golden file `tests/golden/attempts_jsonl_pre_execute_then_attempt.jsonl` after substituting deterministic timestamps (use `freezegun` or a fixed `datetime` injection).
- Add docstring on `record_pre_execute` citing ADR-0007 verbatim about the two-phase write.
- Emit structlog `gates.ledger.pre_execute_recorded` event with `gate_id`, `attempt_id`, `sandbox_spec_hash[:8]`.
- Verify `mypy --strict` is happy with the discriminated union (Pydantic v2 `Annotated[..., Field(discriminator="type")]`).
- Confirm `tests/schema/test_objective_signals_static.py` still passes (no `confidence`/`llm`/`self_reported`/`model_says` introduced).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/retry_ledger.py` | Add `PreExecuteMarker`, `LedgerEntry`, `record_pre_execute`, `entries`. |
| `src/codegenie/gates/contract.py` | Add `type: Literal["attempt"] = "attempt"` field to `Attempt`. |
| `tests/gates/test_pre_execute_marker.py` | Red + property + tamper tests. |
| `tests/golden/attempts_jsonl_pre_execute_then_attempt.jsonl` | Byte-equal golden file. |
| `tests/gates/conftest.py` | Optionally inject deterministic `now_utc` for golden stability. |

## Out of scope

- `GateRunner` call-site that invokes `record_pre_execute` before `client.execute` — that's S5-02.
- `SandboxResumeBehavior` enum on `GateContext` — Phase 6.
- Resume semantics ("re-execute" vs "skip") — Phase 6; this story's invariant is "the marker is *visible* on resume" and stops there.
- CLI surfacing of orphan markers in `codegenie sandbox inspect` — S8-01 (it just reads `entries()`).

## Notes for the implementer

- The `"type"` field must be **first** in canonical JSON output. Pydantic v2 preserves field declaration order; declare `type` first in both `Attempt` and `PreExecuteMarker`.
- Regenerating the golden file from S2-01: that file (if it existed) is now outdated because `"type": "attempt"` is added to every line. Delete and re-generate via the test, not by hand.
- `_marker_pending` is in-memory state. On a fresh process start, set it by replaying the file once in `__init__` and looking for a trailing `"pre_execute"` line with no following `"attempt"` of the same `attempt_id`. This recovery is necessary so a process restart after a crash between marker and attempt doesn't allow a second marker for the same `attempt_id`.
- Do **not** add a `started_at` to `Attempt` here as a duplicate of the marker — `Attempt` already has `started_at`; the marker's `started_at` is the *pre-execute* timestamp, the attempt's is when execute *returned*.
- The chain-tamper detection in `entries()` must surface *which row type* failed in the error message; reviewers need to distinguish marker tamper (rare) from attempt tamper (common adversarial target).
- Keep the marker payload minimal — no signals, no outcome — it is a "we're about to execute" lightweight record, not a verdict.
