# Story S4-08 — Implement `await_human` node — the single `interrupt()` site

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-0008 (HITL operator auth deferred — typed `HumanDecision` only, *no* Ed25519/HMAC), ADR-0003 (HITL `continue` resets `retry_count` to 0), ADR-P6-003 (`interrupt()` from exactly one module)

## Context

`await_human` is **the trust boundary** between the agent and the operator. It is the **only file in the entire `graph/` package that imports `langgraph.types.interrupt`** — this is recorded as ADR-P6-003 (`interrupt()` is called from exactly one node). The fence-CI rule from S1-01 plus a dedicated lint test (`tests/graph/test_only_await_human_imports_interrupt.py`) make this enforceable, not aspirational.

The node has two execution modes, distinguished by whether `state.human_decision` is set:

1. **First entry (`human_decision is None`).** Build a `HumanRequest`, call `interrupt({"human_request": request.model_dump(mode="json")})`. LangGraph captures the checkpoint and returns control to the CLI; the operator runs `codegenie loop resume <thread_id> --decision continue|override|abort` (S6-03). When LangGraph rehydrates and resumes, this node body re-enters with `human_decision` populated by `aupdate_state(as_node="await_human")`.
2. **Resume (`human_decision is not None`).** Read the decision; emit a `GraphEvent(kind="resume")`; on `action="continue"`, **reset `retry_count` to 0** so the operator-approved retry gets a fresh budget; on `"override"` and `"abort"`, leave `retry_count` intact (routing handles the rest via `route_after_human`, S3-02).

Three security-shaped invariants live on this node:

- **No operator-auth machinery here.** Phase 11 owns it. The contract is `HumanDecision.model_validate` at the `aupdate_state` boundary — that's all. Don't add `signature`, don't add `--key`, don't import `cryptography`.
- **`HumanDecision.note` is never read by this node either.** Per ADR-0008 it's operator-readable plain text only; per `../phase-arch-design.md §Component 6` it never reaches an LLM prompt; per Step 4's design it never even reaches the agent's state-machine logic. The note exists only for the audit log + operator review.
- **`interrupt()` is the only side effect.** No file writes, no LLM calls, no sandbox boots. The audit chain extension (`interrupt.raised` event) is done by `AuditedSqliteSaver.put` (S2-02) on the next checkpoint write, not here.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 6 "HumanRequest / HumanDecision / await_human"`; `../phase-arch-design.md §Scenario 2` (the full HITL flow); `../phase-arch-design.md §Edge cases #7` (malformed decision)
- **Phase ADRs:** `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — Phase 6 ships typed `HumanDecision` only; `../ADRs/0003-per-gate-retry-counter-scope.md` — explains the `continue` reset semantics; ADR-P6-003 (single interrupt site) — committed in S10-03 but the constraint applies here
- **Source design:** `../final-design.md §Component 7`; `../final-design.md §Conflict-resolution row 6 "HITL resume authentication"`

## Goal

Ship `graph/nodes/await_human.py` — the only module importing `langgraph.types.interrupt` — with the typed `HumanRequest` build + `interrupt()` call on first entry and the `HumanDecision`-application semantics on resume.

## Acceptance criteria

- [ ] `graph/nodes/await_human.py` exports `await_human(state: VulnLedger) -> VulnLedger`, decorated with `@audited_node`.
- [ ] On first entry (`state.human_decision is None`): construct `HumanRequest(reason=..., summary=..., evidence_paths=..., failing_signals=..., chain_head_at_pause=state.chain_head, requested_at=...)`; call `interrupt({"human_request": request.model_dump(mode="json")})`. `reason` is `"retry_exhausted"` if `state.retry_count >= state.max_attempts`, otherwise `"non_retryable_signal"`.
- [ ] On resume (`state.human_decision is not None`): emit one `GraphEvent(kind="resume", fields={"action": str, "operator": str, "decided_at": str})`; on `action="continue"` set `retry_count=0`; on `"override"` and `"abort"` preserve `retry_count`. Return via `model_copy(update={...})`.
- [ ] **`tests/graph/test_only_await_human_imports_interrupt.py`** (Layer 0 static) — recursively greps `src/codegenie/graph/` for `from langgraph.types import interrupt` and asserts the only hit is in `nodes/await_human.py`. Closes ADR-P6-003 at CI time.
- [ ] The node **does not** read `state.human_decision.note`. A second guard test (similar to S4-05's pattern, using a `GuardedDecision` proxy) confirms.
- [ ] `mypy --strict`, `ruff`, `pytest` green; fence-CI still green.

## Implementation outline

1. Confirm `HumanRequest` and `HumanDecision` shapes from `graph/hitl.py` (shipped in S1-03). Confirm `reason` Literal is `("retry_exhausted", "non_retryable_signal")` and `action` is `("continue", "override", "abort")`.
2. Write the Layer-0 single-import lint test (`tests/graph/test_only_await_human_imports_interrupt.py`) — it's expected to fail until `await_human` lands and *succeed* with exactly one match.
3. Write the unit tests in `tests/graph/test_nodes/test_await_human.py` (first-entry, resume-continue, resume-override, resume-abort, malformed decision, note-not-read guard).
4. Implement the node (~ 50 LOC):
   ```python
   from langgraph.types import interrupt  # the ONLY import in graph/ of this symbol

   @audited_node
   def await_human(state: VulnLedger) -> VulnLedger:
       if state.human_decision is None:
           reason = "retry_exhausted" if state.retry_count >= state.max_attempts else "non_retryable_signal"
           request = HumanRequest(
               reason=reason,
               summary=_summary_from(state),
               evidence_paths=_evidence_paths_from(state),
               failing_signals=state.last_outcome.failing_signals if state.last_outcome else [],
               chain_head_at_pause=state.chain_head,
               requested_at=datetime.now(timezone.utc),
           )
           interrupt({"human_request": request.model_dump(mode="json")})
           # unreachable
       decision = state.human_decision
       events = state.events + [emit_event(state, "await_human", "resume",
                                           {"action": decision.action,
                                            "operator": decision.operator})]
       updates: dict = {"events": events, "last_node": "await_human",
                        "human_request": state.human_request}
       if decision.action == "continue":
           updates["retry_count"] = 0
       return state.model_copy(update=updates)
   ```
5. Verify the single-interrupt-import lint passes after the import lands.
6. Run all tests.

## TDD plan — red / green / refactor

```python
# tests/graph/test_only_await_human_imports_interrupt.py
"""ADR-P6-003: interrupt() is called from exactly one node."""
import pathlib
import re


def test_interrupt_imported_only_from_await_human():
    root = pathlib.Path("src/codegenie/graph")
    hits = [p for p in root.rglob("*.py")
            if re.search(r"from\s+langgraph\.types\s+import\s+interrupt", p.read_text())]
    assert len(hits) == 1, f"expected single hit, got {hits}"
    assert hits[0].name == "await_human.py"
```

```python
# tests/graph/test_nodes/test_await_human.py
import pytest
from unittest.mock import MagicMock, patch
from codegenie.graph.hitl import HumanDecision, HumanRequest
from codegenie.graph.nodes.await_human import await_human
from tests.graph.test_nodes.conftest import make_ledger


def test_first_entry_fires_interrupt_with_request_payload(monkeypatch):
    """LangGraph's interrupt() raises (it's a control-flow primitive).
    We catch it and assert the payload shape — that's the canary against
    accidentally feeding raw state to the operator."""
    captured = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        raise RuntimeError("INTERRUPTED")  # simulate LangGraph's control flow

    monkeypatch.setattr("codegenie.graph.nodes.await_human.interrupt", fake_interrupt)

    ledger = make_ledger(human_decision=None, retry_count=3, max_attempts=3,
                         last_outcome=MagicMock(failing_signals=["tests"]))
    with pytest.raises(RuntimeError, match="INTERRUPTED"):
        await_human(ledger)

    assert "human_request" in captured["payload"]
    assert captured["payload"]["human_request"]["reason"] == "retry_exhausted"


def test_resume_continue_resets_retry_count():
    """ADR-0003: HITL 'continue' grants a fresh retry budget."""
    decision = HumanDecision(action="continue", operator="alice",
                             decided_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                             note="")
    ledger = make_ledger(human_decision=decision, retry_count=3,
                         last_outcome=MagicMock(failing_signals=["tests"]))

    out = await_human(ledger)
    assert out.retry_count == 0


def test_resume_override_preserves_retry_count():
    decision = HumanDecision(action="override", operator="bob",
                             decided_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                             note="")
    ledger = make_ledger(human_decision=decision, retry_count=3,
                         last_outcome=MagicMock(failing_signals=["tests"]))
    out = await_human(ledger)
    assert out.retry_count == 3


def test_resume_abort_preserves_retry_count():
    decision = HumanDecision(action="abort", operator="alice",
                             decided_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                             note="")
    ledger = make_ledger(human_decision=decision, retry_count=3,
                         last_outcome=MagicMock(failing_signals=["tests"]))
    out = await_human(ledger)
    assert out.retry_count == 3


def test_await_human_does_not_read_decision_note():
    """ADR-0008 boundary: note is operator-readable only, not agent-state input."""
    from tests.graph.test_nodes.test_hitl_note_not_in_prompt import GuardedDecision, HitlNoteLeaked
    real = HumanDecision(action="continue", operator="alice",
                         decided_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                         note="DO NOT READ")
    ledger = make_ledger(human_decision=GuardedDecision(real), retry_count=3,
                         last_outcome=MagicMock(failing_signals=["tests"]))
    try:
        await_human(ledger)  # must not raise HitlNoteLeaked
    except HitlNoteLeaked as e:
        pytest.fail(str(e))
```

**Red:** Lint fails (no `await_human.py`); unit tests fail (module missing).
**Green:** Implement node; both layers pass.
**Refactor:** Confirm `_summary_from(state)` and `_evidence_paths_from(state)` are tiny pure helpers in the same module (~ 10 LOC each); they read `state.last_outcome` only. The `chain_head_at_pause` field is `bytes` — round-tripping through `model_dump(mode="json")` must base64-encode cleanly; if Pydantic's default isn't base64, fix the serializer config on `HumanRequest` (likely a Step 1 follow-up).

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/nodes/await_human.py` | New — single `interrupt()` site |
| `tests/graph/test_only_await_human_imports_interrupt.py` | New (Layer 0 lint) |
| `tests/graph/test_nodes/test_await_human.py` | New (TDD red) |

## Out of scope

- Operator authentication / Ed25519 / HMAC — ADR-0008 explicit deferral to Phase 11/16.
- Writing the `interrupt.raised` chain event — that's `AuditedSqliteSaver.put`'s job (S2-02).
- Determining whether HITL `continue` after a same-signature flake is silently routed to `non_retryable` — Gap 4; documented in S7-04 with a CLI warning, not handled here.
- Notifying the operator (Slack / GitHub PR comment / etc.) — Phase 11 owns signal source.
- Auto-resume timeouts — there are none; HITL pause is "wait forever for human."

## Notes for the implementer

- **The single-interrupt-import lint test is the load-bearing invariant.** If any future node ever adds `from langgraph.types import interrupt`, that test must turn red — make sure the test would catch *any* of: `from langgraph.types import interrupt as ...`, `from langgraph import types as t; t.interrupt(...)`. The simple regex above catches the canonical form; if you want belt-and-suspenders, add a Python AST check.
- LangGraph's `interrupt()` is a control-flow primitive (raises a special exception caught by LangGraph itself). In the unit test you must monkeypatch it because raising the real exception leaks LangGraph internals into the test. The mock raises a generic `RuntimeError`; the production runtime catches the real exception in the LangGraph engine.
- The `interrupt_before=["await_human"]` setting on the compiled graph (S5-01) means LangGraph *pauses before this node body even runs* on first entry. So in production, the `human_decision is None` branch runs only after `aupdate_state(as_node="await_human")` injects the decision — *not* immediately after a gate failure. The unit test simulates this by calling the body directly; the integration test (S7-01) exercises the full pause-resume cycle.
- `HumanRequest.summary` is `Field(max_length=4096)`. If `state.last_outcome` carries a long failure summary, truncate cleanly before constructing — never silently fail validation.
- `HumanRequest.evidence_paths: dict[str, Path]` — Pydantic round-trips `Path` → `str`. Confirm S1-02's golden fixture covers this.
- The `_evidence_paths_from` helper should not read raw evidence files; it just records the paths. Operators load evidence on their own via `codegenie loop inspect` (S6-04).
- Wall-clock budget — N/A. This node's "duration" is operator latency. The replay test (S8-01) is the canary that the SQLite checkpoint at the interrupt frame is durable across SIGKILL.
