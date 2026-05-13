# Story S7-01 — HITL interrupt + resume integration test parametrized at `max_attempts ∈ {1, 2, 3}`

**Step:** Step 7 — HITL replay + Phase 5 parity + retry-feedback-distinct-bytes tests (G3 + G4 + G5)
**Status:** Ready
**Effort:** L
**Depends on:** S2-04 (`AuditedSqliteSaver` fsync-per-node durability proven, so `interrupt()` checkpoint survives a process boundary), S6-03 (`codegenie loop resume` constructs `HumanDecision` and calls `aupdate_state(as_node="await_human")` + `ainvoke(None, config)`). Transitively: S3-02 (`route_after_attempt` short-circuits on `retry_count >= max_attempts` / same-signature flake), S4-07 (`record_attempt` per-gate counter), S4-08 (`await_human` is the only `interrupt()` site), S5-01 (`build_vuln_loop(checkpointer=..., max_attempts=..., force_rebuild=False)` factory), S5-03 (`tools/policy/graph-thresholds.yaml` digest-pinned).
**ADRs honored:** ADR-0001 (lazy singleton — `force_rebuild=True` per parametrization so each `max_attempts` value compiles a fresh graph), ADR-0002 (`VulnLedger` frozen=False with after-node `id()`-diff hook; the test never mutates state in place), ADR-0003 (per-gate retry counter, same-signature flake short-circuit; HITL "continue" resets `retry_count=0`), ADR-0004 (retry re-enters `replan_with_phase4` with `prior_attempts` intact), ADR-0006 (per-workflow fsync — survives the HITL pause), ADR-0007 (BLAKE3 chain extends across `interrupt.raised` and `resume.injected` events), ADR-0008 (HITL operator-auth deferred — `HumanDecision` typed; no Ed25519), ADR-0010 (`GateRunner.run_one` consumed by `validate_in_sandbox`), production ADR-0014 (`max_attempts=3` default; parametrization covers the literal roadmap "twice in a row" reading too). Surfaces ADR-P6-008 if Gap 1 needs an explicit ADR resolution.

## Context

This story lands the integration test that proves Phase 6's central exit criterion — the one the roadmap names verbatim:

> *"HITL interrupt fires when trust gates fail twice in a row, and a mocked human approval continues the run."*
> — `docs/roadmap.md §Phase 6 Exit criteria`

The test drives **arch-design §Scenario 2** end-to-end through a real `build_vuln_loop()` compiled graph wired against a real `AuditedSqliteSaver` writing to `tmp_path`, with Phase 3/4/5 engines mocked at the import boundary so the test runs in ~10 s. Two consecutive gate failures at `current_gate_id="stage6_validate"` trip `interrupt_before=["await_human"]`; the CLI exits 12; a fresh process re-attaches, calls `aupdate_state(config, {"human_decision": HumanDecision(action="continue", ...).model_dump(mode="json")}, as_node="await_human")` followed by `ainvoke(None, config)`; the run resumes, the third (post-HITL) attempt passes, `emit_artifact` writes `report.json`, and the run exits 0.

The test is **parametrized at `max_attempts ∈ {1, 2, 3}`** — closing **Gap 1** (`phase-arch-design.md §"Two-consecutive vs three-strikes"`) and **Gap 5** (`phase-arch-design.md §Gap 5`). The three values cover:

- `max_attempts=1` — one failure → HITL (degenerate case; verifies the predicate doesn't require `>= 2` prior attempts to fire when the cap is `1`).
- `max_attempts=2` — two consecutive failures → HITL (roadmap's literal "twice in a row" wording).
- `max_attempts=3` — three consecutive failures → HITL (ADR-0014 production default; this is the path real operators hit).

The reason `max_attempts=3` is non-negotiable in the matrix: without it, the production-default code path is never exercised end-to-end through HITL — exactly the gap the arch design called out. The `max_attempts=2` case alone is necessary-but-not-sufficient.

The story does **not** ship the Phase 5 parity test (S7-02), the retry-feedback distinct-bytes test (S7-03), the malformed-decision adversarial (S7-04), or the contract export (S7-05). It ships **one integration test file** plus a single shared fixture module and the `tests/integration/conftest.py` rationale block that the rest of Step 7 will reuse.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenario 2` — the sequence diagram this test executes step-by-step.
  - `../phase-arch-design.md §"Two-consecutive vs three-strikes"` (line 448) — the parametrization rationale.
  - `../phase-arch-design.md §Component 6` "`HumanRequest` / `HumanDecision` / `await_human`" — the typed contract the test injects.
  - `../phase-arch-design.md §Gap 1` and `§Gap 5` — what the parametrization closes.
  - `../phase-arch-design.md §Edge case 9` — same-signature flake (S7-04 covers it; this story must *not* trip it).
  - `../phase-arch-design.md §Testing strategy → Layer 4 (HITL)` — ~10 s CI budget.
- **Phase ADRs:**
  - `../ADRs/0003-per-gate-retry-counter-scope.md` — the `retry_count` reset semantics on HITL `continue`.
  - `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — `HumanDecision` shape; no auth.
  - `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — checkpoint durability across the pause.
  - `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — `interrupt.raised` / `resume.injected` events.
- **Production ADRs:** `../../../production/adrs/0014-three-retry-default-per-gate.md` (the production `max_attempts=3` default), `../../../production/adrs/0009-humans-always-merge.md` (HITL is a triage gate, not a merge gate).
- **High-level-impl:** `../High-level-impl.md §Step 7` — feature list, done criteria, ~10 s budget, Gap 5 closure.
- **Source design:** `../final-design.md §Goals#3` (G3), `../final-design.md §Exit-criteria checklist`.
- **Prior phases:** `../../05-sandbox-trust-gates/final-design.md §"Retry feedback semantics"` (the `prior_attempts` kwarg that survives HITL).

## Goal

Land `tests/integration/test_hitl_interrupt_and_resume.py`, parametrized at `max_attempts ∈ {1, 2, 3}`, that compiles `build_vuln_loop` against a real `AuditedSqliteSaver` (`tmp_path`), runs `ainvoke(initial_ledger)` with a mocked-failing `GateRunner.run_one` for the first `max_attempts` calls, asserts `interrupt_before=["await_human"]` fires (the run pauses and the CLI process would exit 12), simulates a fresh process by closing-and-reopening the checkpointer, injects `HumanDecision(action="continue", operator="alice", at=fixed_ts)` via `aupdate_state(as_node="await_human")`, calls `ainvoke(None, config)` again, makes the post-HITL gate pass, and asserts `report.json` is written. The test verifies for **every** parametrized value that (a) HITL fires after exactly `max_attempts` failures at the same `current_gate_id`, (b) the audit chain contains a contiguous `interrupt.raised → resume.injected` event pair, (c) `retry_count` is `0` after the resume (HITL "continue" reset semantics — ADR-0003), (d) `prior_attempts` is **not** cleared by `continue` (Gap 4 — explicit non-clear), (e) the final `RemediationReport` is byte-for-byte stable across two consecutive runs of the same parametrized case (determinism gate folded in).

## Acceptance criteria

- [ ] `tests/integration/test_hitl_interrupt_and_resume.py` exists, is decorated `@pytest.mark.integration`, and is green for **all three** parametrized values.
- [ ] `pytest.mark.parametrize("max_attempts", [1, 2, 3], ids=["m=1", "m=2-roadmap-literal", "m=3-production-default"])` — IDs are operator-readable so a CI red-fail names which parametrization broke.
- [ ] **Phase 1 — `ainvoke` reaches `interrupt()`.**
  - For each `max_attempts`, `GateRunner.run_one` (mocked) returns `GateOutcome(passed=False, retryable=True, failing_signals=["tests"], duration_ms=20)` for the first `max_attempts` calls, then `GateOutcome(passed=True, retryable=True, failing_signals=[], duration_ms=18)` on call `max_attempts + 1`.
  - The first `await graph.ainvoke(initial, config)` returns with the graph paused at `await_human` (LangGraph surfaces this via the resulting state's `__interrupt__` marker on `graph.aget_state(config)`); the test asserts the state has `current_gate_id="stage6_validate"`, `retry_count == max_attempts`, `len(prior_attempts) == max_attempts`, and `human_request is not None`.
  - The test asserts `await_human` was the **last** node entered before the pause via `graph.aget_state_history(config)` inspection (no nodes executed past the interrupt).
- [ ] **Phase 2 — process-boundary simulation.**
  - The test closes the `AuditedSqliteSaver` (`await saver.aclose()`), reopens a fresh `AuditedSqliteSaver` against the same `tmp_path` workflow file, and rebuilds the graph via `build_vuln_loop(checkpointer=fresh_saver, max_attempts=max_attempts, force_rebuild=True)`. This simulates the operator running `codegenie loop resume` from a different shell.
  - The reopened state matches the pre-close state byte-for-byte: `model_dump_json(indent=None)` byte-equality asserted via `assert lhs == rhs` (no JSON-deep-equality fuzz; the bytes are the contract).
- [ ] **Phase 3 — injected `HumanDecision` + resume.**
  - The test constructs `decision = HumanDecision(action="continue", operator="alice", note=None, at=datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC))` and calls `await graph.aupdate_state(config, {"human_decision": decision.model_dump(mode="json")}, as_node="await_human")`.
  - The test calls `await graph.ainvoke(None, config)`; the run completes; the final state has `report` populated and `report.json` exists at `<run_dir>/report.json`.
  - **Post-resume invariants:**
    - `final_state.retry_count == 0` (ADR-0003: HITL `continue` resets).
    - `len(final_state.prior_attempts) == max_attempts` (Gap 4: `continue` does **not** clear `prior_attempts`).
    - `final_state.human_decision == decision` (the decision survives into the final ledger).
    - `final_state.last_outcome.passed is True` (post-HITL gate passed).
- [ ] **Audit chain integrity across the pause.**
  - The audit JSONL on disk (`<workflow>.sqlite3` chain rows) contains, in order: `…`, `record_attempt.exit` (the `max_attempts`-th failure), `await_human.enter`, `interrupt.raised`, `resume.injected`, `await_human.exit`, `replan_with_phase4.enter`, … — verified by reading the chain rows and asserting the event-type sequence.
  - `blake3` chain head matches between pre-pause `record_attempt.exit` and post-resume `await_human.exit` (no chain break).
- [ ] **Same-signature flake non-firing guard.** The mocked failures use **distinct** `failing_signals` per attempt (e.g., `["tests"]`, `["build"]`, `["install"]`) **or** distinct `prior_failure_summary` strings so that `_same_signature(prior_attempts[-1], prior_attempts[-2])` returns `False`. If the predicate fired, the run would short-circuit to `non_retryable` instead of `retry_exhausted` — a test would still see HITL fire but for the wrong reason. The test explicitly asserts `_same_signature(...)` is `False` at the pre-pause state to pin this.
- [ ] **Determinism gate.** Running the test twice end-to-end (within the same pytest session — invoke the test body twice manually, distinct `tmp_path`s) produces byte-identical `report.json` content after normalizing the two wall-clock fields (`at` and `started_at` in the report) per `tests/integration/conftest.py` `normalize_wallclock_fields()` helper this story introduces. The helper is the same primitive S7-02's parity test will reuse.
- [ ] **Performance budget.** Each parametrized case completes in ≤ 10 s on the CI runner (Layer 4 budget per arch §Testing strategy). The full file (3 params × determinism repeat = 6 invocations of the inner body) completes in ≤ 60 s. Asserted via `@pytest.mark.timeout(15)` per test + a session-end log line.
- [ ] **No real LLM, no real sandbox, no real Phase 5 retry loop.** `GateRunner.run_one`, `RecipeEngine.apply`, `FallbackTier.run`, `RagTier.lookup`, `RetryLedger.record` are all patched at their import paths via `monkeypatch.setattr` inside the test (or a `pytest` fixture in `tests/integration/conftest.py`). The test runs without docker, without an Anthropic API key, without network.
- [ ] **`tests/integration/conftest.py`** ships:
  - `normalize_wallclock_fields(report_dict: dict) -> dict` — sets `at` and `started_at` and any `duration_ms` to `0` (or a stable sentinel) for byte-diff stability across S7-02 / S7-03.
  - A module docstring naming the **parametrization rationale**: the literal roadmap wording "twice in a row" versus ADR-0014's `max_attempts=3` default; the parametrization closes Gap 1 + Gap 5; if the team later resolves Gap 1 via a new ADR-P6-008, the parametrization values may collapse but the test file shape stays.
- [ ] **No state mutation in place.** The `make_after_node_hook` (S1-04) is enabled on the compiled graph throughout the test; the test red-fails with `LedgerMutatedInPlace` if any node mutates the ledger instead of returning `state.model_copy(update={...})`.
- [ ] **`HumanDecision` shape.** The test asserts `decision.action == "continue"` is a `Literal` (`HumanDecision(action="approve")` would raise `ValidationError` — S7-04 covers that, not this story). The test uses `model_dump(mode="json")` (not `model_dump_json()`) so the `as_node="await_human"` payload is a `dict` matching what the CLI ships in S6-03.
- [ ] `mypy --strict tests/integration/test_hitl_interrupt_and_resume.py tests/integration/conftest.py` passes. `ruff check` + `ruff format --check` pass.
- [ ] The test file's top docstring names: (a) the roadmap exit criterion verbatim, (b) the three parametrization values + their meanings, (c) the four invariants the test enforces post-resume, (d) the legitimate amendment procedure ("if `max_attempts=2` ever stops being the literal roadmap reading, amend the parametrization in the same PR as the ADR-P6-008 amendment").

## Implementation outline

1. **Fixture: mocked engines.** `tests/integration/conftest.py` (or a new `tests/integration/mocks.py`) exposes:
   - `MockGateRunner` with a `run_one(transition, ctx) -> GateOutcome` that consumes a pre-scripted `Iterator[GateOutcome]` (constructor takes the list of outcomes).
   - `MockRecipeEngine.apply(ctx) -> RecipeApplication` returning a deterministic `PatchRef` (different bytes per call so distinct-bytes can be asserted by later stories without re-mocking).
   - `MockFallbackTier.run(...)` returning a `RecipeSelection` with `last_engine="phase4_llm"`.
   - `MockRagTier.lookup(...)` returning a hit with `score=0.95` (above threshold) so the test path is recipe→rag-hit→apply→validate, not recipe→rag-miss→replan. (The replan path is exercised in S7-03.)
   - All four mocks are wired via `monkeypatch.setattr` against the **import paths the Phase 6 nodes use** (e.g., `codegenie.graph.nodes.validate_in_sandbox.run_one`), not against the prior-phase source modules.
2. **Build the graph.** Inside the test, `build_vuln_loop(checkpointer=AuditedSqliteSaver(tmp_path / "wf.sqlite3"), max_attempts=max_attempts, force_rebuild=True)`. Capture `config = {"configurable": {"thread_id": workflow_id}}`.
3. **Construct the initial ledger.** A canonical `VulnLedger(schema_version="v0.6.0", advisory=...)` fixture lives in `tests/integration/fixtures/initial_ledger.py` (or inline; the inline form is fine for one story but factor out if S7-02/03 reuse).
4. **Phase 1 — drive to pause.** `await graph.ainvoke(initial, config)`. Capture the result. Assert the state-history shape via `graph.aget_state_history(config)`.
5. **Phase 2 — process-boundary simulation.** `await saver.aclose()`; reopen; rebuild graph with `force_rebuild=True`.
6. **Phase 3 — inject + resume.** Build the `HumanDecision`; `aupdate_state`; `ainvoke(None, config)`; assert final.
7. **Post-checks.** Audit chain row-walk via the `AuditedSqliteSaver.read_audit_rows(workflow_id)` accessor (S2-02). Determinism repeat with a fresh `tmp_path`.

## TDD plan — red / green / refactor

### Red

Path: `tests/integration/test_hitl_interrupt_and_resume.py`

```python
"""Roadmap §Phase 6 exit criterion: "HITL interrupt fires when trust gates fail twice in a
row, and a mocked human approval continues the run."

Parametrized at max_attempts in {1, 2, 3}:
- m=1: degenerate case; one failure trips HITL. Pins the predicate doesn't require >=2.
- m=2-roadmap-literal: the literal "twice in a row" reading.
- m=3-production-default: ADR-0014 default; the path real operators hit.

Post-resume invariants (ADR-0003 + Gap 4):
1. retry_count == 0 (HITL continue resets).
2. len(prior_attempts) == max_attempts (continue does NOT clear; Phase 4 sees all history).
3. human_decision is the injected decision.
4. last_outcome.passed is True (post-HITL gate passes).

Amendment procedure: if the team resolves Gap 1 via ADR-P6-008 and the parametrization
collapses to a single value, update both this test and the ADR in the same PR.
"""

import pytest
from datetime import datetime, UTC
from codegenie.graph import build_vuln_loop, AuditedSqliteSaver
from codegenie.graph.hitl import HumanDecision
from codegenie.graph.state import VulnLedger
# ... mock imports

@pytest.mark.integration
@pytest.mark.timeout(15)
@pytest.mark.parametrize(
    "max_attempts",
    [1, 2, 3],
    ids=["m=1", "m=2-roadmap-literal", "m=3-production-default"],
)
async def test_hitl_interrupt_after_max_attempts_failures_then_resume_continues(
    tmp_path, monkeypatch, max_attempts: int
) -> None:
    # Phase 1: drive to interrupt
    ...
    # Phase 2: process-boundary simulation
    ...
    # Phase 3: inject HumanDecision(continue) and resume
    ...
    # Post-resume invariants
    assert final.retry_count == 0  # ADR-0003
    assert len(final.prior_attempts) == max_attempts  # Gap 4
    ...

@pytest.mark.integration
@pytest.mark.parametrize("max_attempts", [1, 2, 3])
async def test_audit_chain_contains_interrupt_resume_pair_in_order(
    tmp_path, monkeypatch, max_attempts: int
) -> None:
    ...

@pytest.mark.integration
@pytest.mark.parametrize("max_attempts", [1, 2, 3])
async def test_report_json_byte_identical_across_two_runs(
    tmp_path_factory, monkeypatch, max_attempts: int
) -> None:
    # Determinism gate; uses normalize_wallclock_fields() from conftest.
    ...
```

Run the file. Every test red-fails (no implementation yet beyond Steps 1–6). Commit red.

### Green

- Run iteratively against an already-green Phase 6 stack (Steps 1–6 land first). The test is a *consumer* of the implementation; if a test red-fails, the right response is usually a fix in `cli/loop.py` or `await_human.py`, **not** a relaxation here.
- The most likely red signal is a LangGraph API shape change between `0.2.x` and `0.3.x` — the `aupdate_state(as_node="await_human")` injection may surface differently in newer versions. Pin `langgraph >= 0.2.x, < 0.3.x` in `pyproject.toml` (this is already mandated in `High-level-impl.md §Step 7 Risks`).

### Refactor

- **Factor out `normalize_wallclock_fields`** to `tests/integration/conftest.py` — S7-02 and S7-03 will reuse the exact same helper. The byte-diff discipline needs one single source of truth.
- **Do not over-extract the mocks** — if S7-02/03 need different `GateOutcome` sequences, each story builds its own scripted iterator. The shared piece is the `MockGateRunner` class, not the script.
- **Do not import `_same_signature` directly** — call it via `codegenie.graph.edges.route_after_attempt`'s observable behavior (route label). The predicate's purity is S3-03's concern.
- **Keep the test sync-friendly.** `pytest-asyncio` with `mode="auto"` is the standard; the test marks `async def`. No event-loop fixture gymnastics.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_hitl_interrupt_and_resume.py` | New — the load-bearing G3 + Gap 1 + Gap 5 gate. |
| `tests/integration/conftest.py` | New (or extend) — `normalize_wallclock_fields` + parametrization rationale docstring + shared `MockGateRunner`. |
| `tests/integration/mocks.py` | New — `MockGateRunner`, `MockRecipeEngine`, `MockFallbackTier`, `MockRagTier`, `MockRetryLedger` reusable across S7-02/03/04. |
| `tests/integration/fixtures/initial_ledger.py` | New — canonical `VulnLedger` constructor for Step 7 tests. |
| `tests/cassettes/` | Empty placeholder; S7-03 populates with real VCR cassettes for the LLM path. |
| `pyproject.toml` | Register `pytest.mark.integration` (if not yet registered by Phase 5); confirm `pytest-asyncio` config. |

## Out of scope

- **Phase 5 byte-parity** — S7-02 ships `test_retry_semantics_parity.py`. This story's test runs the LangGraph cycle only; the sync `GateRunner.run()` comparison is separate.
- **Retry-feedback distinct patch bytes** — S7-03 ships `test_phase4_retry_feedback_distinct_bytes.py`. This story does not assert distinct-patch-bytes (it doesn't even go through `replan_with_phase4` on the recipe-hit path).
- **Same-signature flake routing** — S7-04 ships `test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py`. This story actively *avoids* tripping `_same_signature` by varying `failing_signals`.
- **Malformed `HumanDecision`** — S7-04 covers `action="approve"` raising `ValidationError`.
- **HITL contract export** — S7-05 exports `docs/contracts/hitl-v0.6.0.json` and ships the CI gate.
- **Replay-after-kill** — Step 8 (`test_replay_after_kill.py`) covers SIGKILL during `validate_in_sandbox`. This story simulates a process boundary via `aclose()` + reopen, not a real kill.
- **Operator authentication** — ADR-0008 defers to Phase 11; `HumanDecision` has no `signature` field in v0.6.0.
- **CLI invocation through `CliRunner`** — S6-02 / S6-03 already test the CLI surface; this story is a *graph-level* integration test that bypasses the CLI for speed.

## Notes for the implementer

- **The three parametrization IDs are operator-facing.** A CI red-fail that says `test_…[m=3-production-default]` immediately tells the on-call who reads it which path broke. Do not collapse them to `[1, 2, 3]`.
- **Why `max_attempts=1` is in the matrix.** It's a degenerate case but it catches a real bug: a predicate written as `retry_count >= 2 and …` (instead of `retry_count >= max_attempts and …`) passes m=2 and m=3 but fails m=1. The Hypothesis property tests in S3-03 should catch this too, but the integration test is the belt-and-suspenders gate.
- **Why the `aclose()` + reopen step matters.** Without it, the test verifies "interrupt fires and resume works *in the same process*" — which is exactly what LangGraph's in-memory tests already do. The whole point of the `AuditedSqliteSaver` is that the pause survives a process exit. Skipping `aclose()` makes the test silently weaker; if a future change breaks WAL durability without breaking in-memory semantics, this test must catch it.
- **Why `prior_attempts` is **not** cleared on `continue`.** Gap 4 in `phase-arch-design.md` documents this explicitly: the operator's approval grants a fresh retry budget (resets `retry_count`) but leaves the prior failure history intact so Phase 4's next attempt sees fence-wrapped summaries of all prior failures. If this changes (the team adopts Gap 4 option (a) or (b)), the assertion `len(final.prior_attempts) == max_attempts` flips and the change ships as a Phase-6 ADR + this test's update in the same PR.
- **Why distinct `failing_signals` per attempt.** Without varying them, the same-signature flake detector (`_same_signature` in `edges.py`) fires after the second failure and routes to `non_retryable` → `await_human` instead of the intended `retry_exhausted` → `await_human`. HITL still fires, but for the wrong predicate. The test would be green-by-accident. Varying signals is the discipline; the post-state assertion `_same_signature(prior_attempts[-2:]) is False` (via the route label being `retry_exhausted`, not `non_retryable`) pins it.
- **Determinism gate is folded in, not separate.** S8-02 ships the cleaner reference replay-byte-identical test. This story's determinism check is the cheap version: two runs of the same parametrized case must produce byte-identical `report.json` after wall-clock normalization. If the cheap check fails, the cleaner test will too — failing here surfaces the bug faster.
- **`aupdate_state(as_node="await_human")` vs `Command(resume=…)`.** Phase 6 explicitly picks `aupdate_state` over `Command(resume=…)` because the latter requires the typed `Command` payload shape which LangGraph's API has churned on between 0.2.x and 0.3.x. ADR-0008's contract is the `dict` payload from `model_dump(mode="json")`; `aupdate_state` is the API that accepts it. Do not introduce `Command` here.
- **Pin the resume timestamp.** `HumanDecision.at=datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)` is hard-coded so the determinism gate's byte-diff stability isn't fighting wall-clock noise from the operator-decision side. Real operator runs vary `at`; that's covered by `normalize_wallclock_fields` for byte-diff but pinning here keeps the test's own assertions cleaner.
- **If the LangGraph `__interrupt__` marker shape changes,** the failure mode is a green-but-wrong test (the interrupt fires but the assertion that surfaces the pause looks at a different attribute). The defense: assert `await_human.exit` is **not** in the audit chain pre-resume — if it is, the interrupt didn't actually pause the run before the node body executed.
- **Effort sizing rationale.** L (not M) because (a) parametrization × three values means three sub-tests, each with three phases; (b) the audit-chain row-walk assertion is fiddly; (c) the determinism gate adds a repeat-run pass; (d) the conftest helper (`normalize_wallclock_fields`) is a shared primitive S7-02/03 will consume; (e) the LangGraph version-pin sensitivity makes the failure-mode analysis non-trivial. A junior implementer should expect 1–2 days; an experienced one ~half a day.
