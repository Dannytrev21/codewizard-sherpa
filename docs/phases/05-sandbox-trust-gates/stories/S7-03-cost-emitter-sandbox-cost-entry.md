# Story S7-03 — `CostEmitter` + `SandboxCostEntry` schema (Gap 5)

**Step:** Step 7 — Adversarial test suite + performance regression gates
**Status:** Ready
**Effort:** S
**Depends on:** S5-02
**ADRs honored:** ADR-0010, ADR-0014 (`extra="forbid", frozen=True` discipline)

## Context

`phase-arch-design.md §Gap 5` documents that Phase 13 reads `cost.sandbox.run` ledger entries from `.codegenie/cost/sandbox.jsonl` but Phase 5 never defined the shape, file path, or contract test — Phase 13 would silently undercount if the shapes drift. ADR-0010 makes the schema a Phase 5 contract. This story lands `sandbox/cost.py` with the `SandboxCostEntry` Pydantic model and the `CostEmitter`, wires `CostEmitter.emit()` into `GateRunner.run` post-`RetryLedger.record`, and ships the byte-stable golden-file contract test Phase 13 will pin against.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Gap 5` — the schema is given verbatim in the gap
- **Architecture:** `../phase-arch-design.md §Component 6 CostEmitter` — wiring point
- **Phase ADRs:** `../ADRs/0010-cost-sandbox-run-ledger-schema.md` — full Decision, Tradeoffs, Consequences
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — frozen/extra=forbid discipline applies here too
- **Production ADRs:** `../../../production/adrs/0024-cost-observability-end-to-end.md` — downstream consumer context
- **Production ADRs:** `../../../production/adrs/0025-per-workflow-cost-cap.md` — Phase 13 will sum from this ledger
- **Implementation plan:** `../High-level-impl.md §Step 7` — lists `sandbox/cost.py` and `tests/sandbox/test_cost_emitter.py`
- **Existing code:** `src/codegenie/gates/runner.py` (from S5-02) — wiring point post-`RetryLedger.record`
- **Existing code:** `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxRun.microvm_seconds`, `image_pull_bytes` fields the emitter reads

## Goal

Land `src/codegenie/sandbox/cost.py` with a frozen `SandboxCostEntry` Pydantic model and a `CostEmitter` that writes one append-only JSONL row per `GateRunner` attempt to `.codegenie/cost/sandbox.jsonl`, with a byte-stable golden-file contract test.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/cost.py` exists and exports `SandboxCostEntry` and `CostEmitter`.
- [ ] `SandboxCostEntry` is a `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)` and exactly these fields (no more, no less): `entry_type: Literal["cost.sandbox.run"]`, `workflow_id: str`, `run_id: str`, `gate_id: str`, `sandbox_run_id: str`, `backend: Literal["docker_in_docker", "firecracker"]`, `gate_isolation_class: Literal["shared_kernel", "microvm"]`, `microvm_seconds: float`, `image_pull_bytes: int`, `build_cache_hit: bool`, `emitted_at: datetime`.
- [ ] `CostEmitter.emit(entry: SandboxCostEntry) -> None` appends one canonical-JSON line (sorted keys, ISO-8601 UTC `emitted_at`) to `.codegenie/cost/sandbox.jsonl` and fsyncs before return.
- [ ] `CostEmitter` creates the parent dir lazily on first emit; subsequent emits do not stat the directory.
- [ ] `GateRunner.run` is amended to call `CostEmitter.emit(entry)` immediately after `RetryLedger.record(attempt)` returns; the order is asserted by `tests/gates/test_runner_cost_order.py` (cost row written iff ledger row written).
- [ ] For `backend == "docker_in_docker"`, `microvm_seconds = 0.0` always; for `backend == "firecracker"`, `microvm_seconds = SandboxRun.microvm_seconds` (default 0.0 if not yet populated by Phase 6). `image_pull_bytes` reads `SandboxRun.image_pull_bytes` (default 0).
- [ ] `tests/sandbox/test_cost_emitter.py` asserts: (a) emitting an entry produces a byte-identical line vs `tests/golden/cost_entry_canonical.json`; (b) two emits append two lines (not overwrite); (c) an entry that violates `extra="forbid"` raises `ValidationError`; (d) a `model_copy(update={"microvm_seconds": 1.5})` succeeds and produces a different byte-stream.
- [ ] `tests/sandbox/test_cost_emitter_order.py` asserts that emission happens after `RetryLedger.record` (call-order golden via spy/mocks).
- [ ] Adding any field to `SandboxCostEntry` requires updating `tests/golden/cost_entry_canonical.json` AND the ADR-0010 amendment note — guarded by a comment in the model class.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Create `src/codegenie/sandbox/cost.py`. Define `SandboxCostEntry` first, then `CostEmitter`.
2. Define `CostEmitter` with a single attribute `ledger_path: Path` (default `.codegenie/cost/sandbox.jsonl` resolved relative to the workflow root). Constructor takes the path explicitly so tests can redirect to `tmp_path`.
3. Implement `emit(entry)`. Serialize via `entry.model_dump_json(by_alias=False)` — but `model_dump_json` is not sorted; instead use `json.dumps(entry.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))` to guarantee byte-stability.
4. Add `mkdir(parents=True, exist_ok=True)` lazily; open `ledger_path` with `mode="ab"` and `os.fsync(fd)` before close on each emit (matches `RetryLedger.record` durability).
5. Amend `gates/runner.py`: after the existing `self._ledger.record(attempt)` call, build the entry from `attempt`, `gate_context`, and `sandbox_run`, then call `self._cost.emit(entry)`. Inject `self._cost: CostEmitter` via `__init__` with a default constructor.
6. Author golden file `tests/golden/cost_entry_canonical.json` by running the emitter once with fixed inputs (a docstring at the top of the test names the inputs); commit the resulting bytes verbatim.
7. Write the three tests (`test_cost_emitter.py`, `test_cost_emitter_order.py`, optional `test_cost_extra_forbidden.py`).
8. Verify `mypy --strict` is happy with `Literal[...]` field types and `datetime` import.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/sandbox/test_cost_emitter.py`

```python
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.sandbox.cost import CostEmitter, SandboxCostEntry


def _fixed_entry() -> SandboxCostEntry:
    return SandboxCostEntry(
        entry_type="cost.sandbox.run",
        workflow_id="wf-fixed",
        run_id="run-fixed",
        gate_id="stage6_validate",
        sandbox_run_id="sb-fixed",
        backend="docker_in_docker",
        gate_isolation_class="shared_kernel",
        microvm_seconds=0.0,
        image_pull_bytes=0,
        build_cache_hit=True,
        emitted_at=datetime(2026, 5, 12, 0, 0, 0, tzinfo=timezone.utc),
    )


def test_cost_entry_canonical_byte_stable(tmp_path: Path) -> None:
    """ADR-0010 — Phase 13 will pin this exact byte sequence.

    Why this matters: Phase 13 reads .codegenie/cost/sandbox.jsonl and aggregates
    by gate_isolation_class for the ROI dashboard. A schema drift in Phase 5 that
    silently changes field order or omits emitted_at will silently undercount the
    workflow's true cost — the canonical failure mode this test exists to prevent.
    """
    ledger = tmp_path / "sandbox.jsonl"
    emitter = CostEmitter(ledger_path=ledger)

    emitter.emit(_fixed_entry())

    golden = Path("tests/golden/cost_entry_canonical.json").read_bytes()
    assert ledger.read_bytes() == golden  # byte-for-byte


def test_cost_entry_extra_field_rejected() -> None:
    """ADR-0014 / ADR-0010 — extra=forbid prevents silent contract drift."""
    with pytest.raises(ValidationError):
        SandboxCostEntry.model_validate(
            {**json.loads(_fixed_entry().model_dump_json()), "future_field": 1.0}
        )


def test_cost_emit_appends_does_not_overwrite(tmp_path: Path) -> None:
    """ADR-0010 §Consequences — append-only contract."""
    emitter = CostEmitter(ledger_path=tmp_path / "sandbox.jsonl")
    emitter.emit(_fixed_entry())
    emitter.emit(_fixed_entry())
    lines = (tmp_path / "sandbox.jsonl").read_text().splitlines()
    assert len(lines) == 2
```

### Green

1. Land `SandboxCostEntry` and `CostEmitter`.
2. Run the test; capture the actual produced bytes and write them to `tests/golden/cost_entry_canonical.json` exactly once (with a `tools/regen_cost_golden.py` script committed alongside so regen is auditable).
3. Re-run; bytes match.
4. Amend `GateRunner.__init__` and `GateRunner.run` to wire the emitter.
5. Write `tests/gates/test_runner_cost_order.py` using a spy `CostEmitter` and `RetryLedger`; assert `ledger.record` is called before `cost.emit` per attempt.

### Refactor

- Move the canonicalization helper out of `emit()` if more than one caller will need it (likely not in Phase 5 — leave inline).
- Confirm `tests/sandbox/test_cost_emitter.py` runs in `< 100 ms`.
- Add a one-line `# WARNING: any field change here requires an ADR-0010 amendment.` comment above the `SandboxCostEntry` class body.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/cost.py` | New module — model + emitter |
| `src/codegenie/sandbox/__init__.py` | Export `SandboxCostEntry`, `CostEmitter` |
| `src/codegenie/gates/runner.py` | Wire `CostEmitter.emit` after `RetryLedger.record` |
| `tests/sandbox/test_cost_emitter.py` | Byte-stable + append + extra-forbid |
| `tests/gates/test_runner_cost_order.py` | Ledger-then-cost ordering assertion |
| `tests/golden/cost_entry_canonical.json` | Phase 13 contract anchor |
| `tools/regen_cost_golden.py` | Auditable golden regeneration |

## Out of scope

- Phase 13's cost dashboard, aggregation, or per-workflow cap enforcement.
- A `CostReader` for Phase 13 to consume — Phase 13 owns its reader.
- Token-cost emission (Phase 4's LLM-side cost is a separate ledger; Phase 13 will combine).
- Any backend-specific field (e.g., Firecracker kernel feature flag); ADR-0010 requires an amendment for additions.
- Migrating prior `.codegenie/cost/sandbox.jsonl` content — the file is new in Phase 5.

## Notes for the implementer

1. **`model_dump_json()` does NOT sort keys.** Use `json.dumps(model_dump(mode="json"), sort_keys=True, separators=(",", ":"))` for byte-stability. The golden test will fail loudly if you forget — that is the point.
2. **`datetime` must be serialized as ISO-8601 with explicit `+00:00`.** Phase 13's reader parses with `datetime.fromisoformat`; naive datetimes will fail. The model's `emitted_at: datetime` field accepts aware datetimes; the test fixture pins `tzinfo=timezone.utc`.
3. **`extra="forbid"` is contractually load-bearing.** If you "loosen" it to `extra="ignore"` because a Phase 6 test wants to pass an extra key, you have silently re-opened Gap 5. Bounce that test back.
4. **The append-only invariant is `mode="ab"`, not `"a"`.** Binary append guarantees no surprise text-mode encoding on Windows runners (none in scope today; future-proofing).
5. **Wiring order in `GateRunner.run` is non-negotiable** — ledger first, cost second. The contract test for ordering is small but mandatory; if cost emission fails (e.g., disk full), the attempt is still in the ledger and a reviewer can reconcile.
6. **Do not gate the runner on cost-emission success.** A `CostEmitter` IOError must log structured `cost.emit.failed` and continue; the gate result is the source of truth. (Confirm with a unit test that an `IOError` raised by a fake emitter does not propagate.)
