# Story S4-09 — Implement `emit_artifact` + `escalate` terminal nodes

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** S
**Depends on:** S4-01
**ADRs honored:** ADR-0002 (`model_copy(update=...)`), ADR-0012 (per-node tests)

## Context

The two terminal nodes of the vuln loop. Both flow to `END`; both produce observable side effects that the CLI exit-code matrix (S6-02) reads to pick `0` (artifact emitted) vs `11` (escalation):

- **`emit_artifact`** is the success terminal. It delegates to Phase 3's `RemediationReport.write(...)` (or whichever helper actually persists the artifact — verify against Phase 3's shipped code) to materialize `.codegenie/remediation/<run-id>/report.json`. The CLI exit code on this terminal is `0`.
- **`escalate`** is the failure terminal hit on `HumanDecision.action="abort"`. It emits a `GraphEvent(kind="escalate", fields={"reason": ...})` and otherwise does nothing — no artifact, no further chain extension beyond the standard `checkpoint.write` event. The CLI maps this to exit `11`.

Both nodes are deterministic and fast (≤ 100 ms / ≤ 10 ms respectively). Neither should perform LLM calls, sandbox boots, or chain mutations — they're just "stamp the end-state and let the CLI return."

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5` — `emit_artifact` and `escalate` rows; `../phase-arch-design.md §Control flow Step 14`; `../phase-arch-design.md §Component 8 "cli/loop.py — exit codes"` (0/11/12/13/1)
- **Phase ADRs:** `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md`
- **Prior phases:** `../../03-vuln-deterministic-recipe/final-design.md` — `RemediationReport` schema; the `RemediationReport.write(report, path)` (or equivalent) helper; the canonical `.codegenie/remediation/<run-id>/report.json` path
- **Source design:** `../final-design.md §Component 5`

## Goal

Land `graph/nodes/emit_artifact.py` and `graph/nodes/escalate.py` as `@audited_node` terminal nodes that produce the correct disk artifact (or none, for escalate) and emit the correct `GraphEvent` so the CLI can pick the right exit code.

## Acceptance criteria

- [ ] `graph/nodes/emit_artifact.py` exports `emit_artifact(state: VulnLedger) -> VulnLedger` that calls Phase 3's `RemediationReport.write(...)` (or equivalent) writing to `.codegenie/remediation/<state.workflow_id>/report.json`; emits one `GraphEvent(kind="exit", fields={"report_path": str, "report_blake3": str})`.
- [ ] `graph/nodes/escalate.py` exports `escalate(state: VulnLedger) -> VulnLedger` that emits a single `GraphEvent(kind="escalate", fields={"reason": <from human_decision.action or last_outcome>})` and otherwise returns `state.model_copy(update={"events": [...], "last_node": "escalate"})`. **No file writes**, no further state mutation.
- [ ] TDD red tests: (1) `emit_artifact` writes to the expected path (use `tmp_path` + monkey-patched workflow root); (2) the emitted event carries the report's blake3 digest; (3) `escalate` writes no files (assert `tmp_path` is empty after the call); (4) `escalate` emits exactly one event with `kind="escalate"`.
- [ ] Both nodes propagate exceptions from upstream (e.g., disk-full from `RemediationReport.write`).
- [ ] `mypy --strict`, `ruff`, `pytest`, fence-CI all green.

## Implementation outline

1. Locate Phase 3's `RemediationReport` writer — likely `src/codegenie/recipes/report.py` or similar. Read its signature: it probably accepts a constructed `RemediationReport` Pydantic model + a path. Confirm.
2. Write the four red TDD tests in `tests/graph/test_nodes/test_emit_artifact.py` and `tests/graph/test_nodes/test_escalate.py`.
3. Implement `emit_artifact.py` (~ 30 LOC):
   - Build the `RemediationReport(...)` Pydantic instance from `state` fields (workflow_id, advisory, patch, prior_attempts, ...). Phase 3's contract dictates the exact constructor — adapt.
   - Compute destination path: `state.repo_path / ".codegenie" / "remediation" / state.workflow_id / "report.json"` (or whatever Phase 3 documents — read).
   - Call the writer; capture the bytes-on-disk digest for the event.
4. Implement `escalate.py` (~ 15 LOC):
   - Determine `reason`: prefer `state.human_decision.action` if present (will be `"abort"` on this path), else fall back to `state.last_outcome.failing_signals[0]` (e.g., a non-retryable signal).
   - Emit one event; return.
5. Confirm both nodes are decorated with `@audited_node`.
6. Run tests; confirm green.

## TDD plan — red / green / refactor

```python
# tests/graph/test_nodes/test_emit_artifact.py
import json
from unittest.mock import MagicMock
import pytest
from codegenie.graph.nodes.emit_artifact import emit_artifact
from tests.graph.test_nodes.conftest import make_ledger


def test_emit_artifact_writes_report_to_canonical_path(tmp_path, mock_phase3):
    """INTENT: CLI exit-0 path requires report.json on disk at the documented path."""
    ledger = make_ledger(repo_path=tmp_path, workflow_id="abc1234567890def",
                         patch=MagicMock(path="patch-1.diff", blake3="deadbeef"))

    out = emit_artifact(ledger)

    expected_path = tmp_path / ".codegenie" / "remediation" / "abc1234567890def" / "report.json"
    assert expected_path.exists(), "CLI exit 0 path is unreachable without this file"
    # The writer must produce valid JSON
    json.loads(expected_path.read_text())


def test_emit_artifact_event_carries_blake3(tmp_path, mock_phase3):
    ledger = make_ledger(repo_path=tmp_path, workflow_id="x" * 16,
                         patch=MagicMock(path="p", blake3="ab"))
    out = emit_artifact(ledger)
    evt = next(e for e in out.events if e.node_name == "emit_artifact")
    assert evt.fields.get("report_blake3"), "Phase 13 cost ledger reads this"
    assert evt.fields.get("report_path")


# tests/graph/test_nodes/test_escalate.py
def test_escalate_writes_no_files(tmp_path):
    """INTENT: escalate is NOT a synonym for emit_artifact-with-failure-flag.
    The CLI maps it to exit 11; no report.json is produced."""
    ledger = make_ledger(repo_path=tmp_path,
                         human_decision=MagicMock(action="abort", operator="bob"))

    out = escalate(ledger)

    files = list(tmp_path.rglob("*"))
    assert files == [], f"escalate must not write files; wrote: {files}"


def test_escalate_emits_single_event_with_kind_escalate():
    decision = MagicMock(action="abort", operator="alice")
    ledger = make_ledger(human_decision=decision, events=[])

    out = escalate(ledger)

    new_events = [e for e in out.events if e.node_name == "escalate"]
    assert len(new_events) == 1
    assert new_events[0].kind == "escalate"


def test_escalate_propagates_outcome_reason_when_no_decision():
    """Non-retryable signal can route to escalate via override; carry the reason forward."""
    outcome = MagicMock(passed=False, retryable=False, failing_signals=["policy_violation"])
    ledger = make_ledger(last_outcome=outcome, human_decision=None, events=[])
    out = escalate(ledger)
    evt = next(e for e in out.events if e.kind == "escalate")
    assert "reason" in evt.fields
```

**Red:** Modules missing → all fail.
**Green:** Implement both nodes; tests pass.
**Refactor:** Confirm `emit_artifact`'s path-building logic is hoisted into a tiny helper (`_report_path(state) -> Path`) — Phase 13's cost-ledger pipeline (and S6-04's `inspect` command) will want the same calculation. Confirm `escalate`'s `reason` extraction is one expression, not a sprawling if/else.

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/nodes/emit_artifact.py` | New |
| `src/codegenie/graph/nodes/escalate.py` | New |
| `tests/graph/test_nodes/test_emit_artifact.py` | New (TDD red) |
| `tests/graph/test_nodes/test_escalate.py` | New (TDD red) |

## Out of scope

- Real PR opening — Phase 11.
- Notifying the operator — Phase 11.
- Changing `RemediationReport` schema — Phase 3 contract.
- Recording cost/token totals on the report — Phase 13's `LlmInvocationGuard` already produces a `CostReport` Phase 4 attaches; Phase 6 just persists.
- A "soft escalation" that opens a draft PR for review — that's Phase 11's territory and an `override` action (not `abort`) per ADR-0009.

## Notes for the implementer

- **The CLI exit code matrix (S6-02) reads the *event stream*, not the node name** — that's the whole point of emitting structured events. If `escalate` emits the wrong `kind` or the wrong `fields`, the CLI silently routes to exit `1` and operators wonder why. The TDD assertions on `kind="escalate"` are the canary.
- `emit_artifact` is the success terminal; `escalate` is the failure terminal. They are *not* symmetrical — only `emit_artifact` writes a file. Don't be tempted to also write a "failure report" from `escalate`; the audit chain plus the inspect-able state history is the failure surface.
- `RemediationReport.write` likely accepts a `Path` and a constructed model. Pydantic's `model_dump_json(...)` is the canonical serializer per Phase 3.
- The fence-CI gate from S1-01 forbids `os` / `time` / `random` / `datetime` imports in `graph/edges.py` *only*; nodes are unrestricted on `datetime` (you'll likely want `datetime.now(timezone.utc)` for the event timestamp — `emit_event` already handles this).
- Per `../phase-arch-design.md §Component 5`, p50 budgets: `emit_artifact` ≤ 100 ms (disk write + JSON serialize), `escalate` ≤ 10 ms.
- Both nodes are terminals — they edge to `END` in `_build()` (S5-01). After them, no more nodes run. The audit chain extension from the *final* checkpoint write is what makes the state durable; no extra fsync needed here.
- Resist the temptation to "double-extend" the chain from inside these nodes. The chain writer is the checkpointer alone (S2-02); adding a write from the node would create exactly the dual-writer drift the design forbids.
