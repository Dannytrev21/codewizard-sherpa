# Story S10-01 — Adversarial: forged decision + out-of-order transition rejection

**Step:** Step 10 — Adversarial hardening + Layer-8 E2E + final polish
**Status:** Ready
**Effort:** S
**Depends on:** S7-05, S8-02
**ADRs honored:** ADR-0008 (HITL operator auth deferred — typed `HumanDecision` is the *only* contract), ADR-0002 (`VulnLedger` runtime hook backs the transition-rejection path), ADR-0005 (schema-version literal pinning is upstream of these tests but referenced for the failure mode taxonomy), ADR-0012 (pure-edge discipline — no operator-supplied label can bypass routing)

## Context

Phase 6's threat model is small but specific (arch §Adversarial tests, lines 1214–1222): the security stance is "typed Pydantic + `0600` file mode + BLAKE3 chain integrity" with no Ed25519 / HMAC / operator-key file (those are deferred to Phase 11 per ADR-0008). Step 2 / Step 8 already exercised the file-system threats (tampered DB, world-readable file, schema drift). This story closes the **two remaining Layer-6 (Adversarial) gaps in the threat model**:

1. **Forged HITL decision** — an operator (or a malicious caller of the HITL JSON contract exported by S7-05) submits a `HumanDecision` whose `action` is not in the `Literal["continue", "override", "abort"]` union. The only thing standing between the workflow and an arbitrary action label is `HumanDecision.model_validate`. If that validator fails to reject `action="merge"`, the entire HITL contract is compromised.
2. **Out-of-order transition** — a caller invokes `aupdate_state(..., as_node="emit_artifact")` against a checkpoint whose next paused node is `await_human`. LangGraph's checkpoint history must reject this as an illegal transition. The test pins LangGraph's behavior so a minor-version bump that silently loosens this surfaces in CI rather than at runtime.

The story is Layer-6 (Adversarial) per arch §Test pyramid (~10 s total time budget). Both tests are short, sharp, and named exactly as the arch design specifies (lines 1219–1220).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge-case matrix` (lines 1133–1140) — rows 3, 4, 5, **7** (forged decision), and the out-of-order-transition row implied by the discussion at line 1220.
  - `../phase-arch-design.md §Adversarial tests (Phase-6-scoped threat model)` (lines 1214–1222) — names both test files verbatim.
  - `../phase-arch-design.md §Component 6 — HumanRequest / HumanDecision / await_human` (lines 767–820) — the `action: Literal["continue", "override", "abort"]` union and the `model_validate` rejection contract (line 816).
- **Phase ADRs:**
  - `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` — explicit: typed `HumanDecision.model_validate` is the *only* trust check Phase 6 ships. This story is the test that proves it.
  - `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — the runtime hook is *not* what rejects out-of-order transitions (LangGraph does), but the test must not accidentally tolerate hook-bypassed mutation either.
  - `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — explains why no `as_node` ACL layer exists in `graph/`; LangGraph's own history is the gatekeeper.
- **High-level-impl:**
  - `../High-level-impl.md §Step 10 — Features delivered` — names both test files, fixes the threat-model scope.
- **Existing code (must read before writing):**
  - `src/codegenie/graph/hitl.py` — the `HumanDecision` model the forged-decision test exercises.
  - `src/codegenie/graph/vuln_loop.py` — `build_vuln_loop()` factory, called by the out-of-order-transition test to obtain a compiled graph paused at `await_human`.
  - `src/codegenie/graph/checkpointer.py` — `make_checkpointer()` used to give each test its own `tmp_path` workflow.
  - `tests/graph/fixtures/ledgers.py` (from S2-01) — `build_minimal_ledger()` helper used to seed state in both tests.

## Goal

Two adversarial tests land under `tests/adversarial/` that prove (a) `HumanDecision.model_validate({"action": "merge", ...})` raises `pydantic.ValidationError` with a message naming the unknown literal value, and (b) calling `aupdate_state(..., as_node="emit_artifact")` against a graph paused at `await_human` is rejected by LangGraph's checkpoint history with a clear runtime error and **without** silently advancing to `emit_artifact`.

## Acceptance criteria

- [ ] `tests/adversarial/__init__.py` exists (empty package marker, if not already present).
- [ ] `tests/adversarial/test_forged_human_decision_rejected.py` exists and contains a test that:
  - [ ] Submits `HumanDecision.model_validate({"action": "merge", "operator": "alice", "requested_at_iso": "2026-05-12T00:00:00Z"})` and asserts `pydantic.ValidationError` is raised.
  - [ ] Asserts the error message names the offending literal value (the string `"merge"`) so an operator can diagnose without printf-debugging.
  - [ ] Parametrizes the same rejection across at least three more invalid `action` values — `"approve"` (explicitly called out in arch line 1137), `"reject"`, `""` (empty string) — to demonstrate the Literal union is the gate, not an allow-list of known-bad strings.
  - [ ] Confirms the three valid `action` values — `"continue"`, `"override"`, `"abort"` — each validate cleanly when given the same surrounding payload (positive control).
- [ ] `tests/adversarial/test_out_of_order_transition_rejected.py` exists and contains a test that:
  - [ ] Builds a compiled graph via `build_vuln_loop(checkpointer=make_checkpointer(...), max_attempts=2)`.
  - [ ] Drives the graph to a state paused at `await_human` (use the same scripted-engine-outcome fixture S7-01 uses; do not re-implement, import from `tests/graph/fixtures/`).
  - [ ] Calls `await graph.aupdate_state(config, {"patch": None}, as_node="emit_artifact")` and asserts it raises (any of: `InvalidUpdateError`, `ValueError`, or whatever exception LangGraph surfaces; assert against the *type name* plus a substring match on the error message containing `"emit_artifact"` or `"as_node"` so a LangGraph rename is loud).
  - [ ] After the rejection, asserts the graph's `get_state(config).next` is still `("await_human",)` — i.e., the forged transition did **not** silently advance the checkpoint.
  - [ ] Asserts the BLAKE3 audit chain head has **not** advanced (read via the read accessor S2-02 ships) — a rejected transition must not write a checkpoint event.
- [ ] Both tests are `@pytest.mark.adversarial` (new pytest marker; register in `pyproject.toml` under `[tool.pytest.ini_options]` if not already present from S2-03).
- [ ] Layer-6 (Adversarial) suite stays under the ~10 s arch-budgeted time on a clean run.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check tests/adversarial/`, `ruff format --check tests/adversarial/`, `mypy --strict tests/adversarial/`, and `pytest tests/adversarial/ -m adversarial` all pass.

## Implementation outline

1. Read `src/codegenie/graph/hitl.py` to confirm `HumanDecision.action` is `Literal["continue", "override", "abort"]` exactly. If S1-03 shipped a different literal set, **stop** and surface — do not adapt the test to the wrong contract.
2. Read `src/codegenie/graph/vuln_loop.py` to confirm `interrupt_before=["await_human"]` is set at compile time (S5-01). The out-of-order test relies on the graph genuinely pausing at `await_human` rather than just exposing the node as a label.
3. Create `tests/adversarial/__init__.py` if absent.
4. Write `test_forged_human_decision_rejected.py`:
   - One `@pytest.mark.parametrize` over `["merge", "approve", "reject", ""]` → assert `ValidationError`.
   - One positive-control parametrize over `["continue", "override", "abort"]` → assert `HumanDecision.model_validate(...)` returns a model.
   - Use `pytest.raises(ValidationError) as exc_info` and assert the literal value appears in `str(exc_info.value)`.
5. Write `test_out_of_order_transition_rejected.py`:
   - Use the same in-process LangGraph drive pattern as S7-01 — build graph, `ainvoke` with a scripted-engine fixture that fails twice at the same gate, confirm the checkpoint is paused at `await_human`.
   - Try `aupdate_state(as_node="emit_artifact")`, capture the exception, assert state is unchanged.
   - Read the chain head via S2-02's accessor before and after; assert equality.
6. Register the `adversarial` marker in `pyproject.toml` if not already present (S2-03 may have added it; check first).
7. Update `tests/adversarial/conftest.py` (if it exists) only to share the scripted-engine fixture; do not duplicate it.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/adversarial/test_forged_human_decision_rejected.py`

```python
"""ADR-0008: typed HumanDecision is the only HITL trust check.

This test pins the contract: HumanDecision.model_validate rejects any
action value outside the Literal["continue", "override", "abort"] union.
If this test ever passes with action="merge", the Phase 6 -> Phase 11
HITL contract is compromised and Phase 11's signing layer would be
landing on top of an already-broken gate.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.graph.hitl import HumanDecision


@pytest.mark.adversarial
@pytest.mark.parametrize("forged_action", ["merge", "approve", "reject", ""])
def test_human_decision_rejects_forged_action(forged_action: str) -> None:
    payload = {
        "action": forged_action,
        "operator": "alice",
        "requested_at_iso": "2026-05-12T00:00:00Z",
    }
    with pytest.raises(ValidationError) as exc_info:
        HumanDecision.model_validate(payload)
    # Why: the operator needs to see WHICH value was rejected, not just that
    # validation failed. A bare "validation error" message defeats the audit
    # trail ADR-0008 leans on.
    assert forged_action in str(exc_info.value) or "Literal" in str(exc_info.value)


@pytest.mark.adversarial
@pytest.mark.parametrize("valid_action", ["continue", "override", "abort"])
def test_human_decision_accepts_documented_actions(valid_action: str) -> None:
    # Positive control: this test failing would mean we broke the Literal
    # union itself — surface that loudly instead of pretending the negative
    # test alone is sufficient.
    decision = HumanDecision.model_validate(
        {
            "action": valid_action,
            "operator": "alice",
            "requested_at_iso": "2026-05-12T00:00:00Z",
        }
    )
    assert decision.action == valid_action
```

Test file path: `tests/adversarial/test_out_of_order_transition_rejected.py`

```python
"""arch §Adversarial test row: aupdate_state(as_node="emit_artifact") from a
state paused at await_human must be rejected by LangGraph's checkpoint
history. We do not implement our own as_node ACL — ADR-0012 explicitly says
LangGraph's own history is the gatekeeper. This test pins that behavior so
a LangGraph minor-version bump that loosens it fails CI loudly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.graph.checkpointer import make_checkpointer
from codegenie.graph.vuln_loop import build_vuln_loop
from tests.graph.fixtures.scripted_engines import drive_to_await_human


@pytest.mark.adversarial
@pytest.mark.asyncio
async def test_aupdate_state_with_wrong_as_node_is_rejected(tmp_path: Path) -> None:
    checkpointer = make_checkpointer("workflow_oot_test", base=tmp_path)
    graph = build_vuln_loop(checkpointer=checkpointer, max_attempts=2, force_rebuild=True)
    config = {"configurable": {"thread_id": "workflow_oot_test"}}

    # Drive the graph to pause at await_human via the shared scripted-engine
    # fixture (same fixture S7-01 uses; do not reimplement here).
    await drive_to_await_human(graph, config)

    state_before = await graph.aget_state(config)
    assert state_before.next == ("await_human",), state_before.next
    chain_head_before = checkpointer.read_chain_head()  # S2-02 read accessor

    with pytest.raises(Exception) as exc_info:
        await graph.aupdate_state(
            config,
            {"patch": None},
            as_node="emit_artifact",
        )
    # We do not assert a specific LangGraph exception class — LangGraph
    # exception types are not part of its public API. We DO assert the
    # message names the forged as_node so a silent acceptance is impossible.
    msg = str(exc_info.value)
    assert "emit_artifact" in msg or "as_node" in msg, msg

    # Critical post-condition: state and chain are unchanged.
    state_after = await graph.aget_state(config)
    assert state_after.next == ("await_human",)
    assert checkpointer.read_chain_head() == chain_head_before
```

### Green — make it pass

No production code changes should be required if S1-03 (HumanDecision Literal union), S2-02 (chain read accessor), S5-01 (`interrupt_before=["await_human"]`), and S7-01 (`drive_to_await_human` fixture) all landed correctly. If a test fails because of a missing fixture or accessor, **surface it** — do not add a fresh one in this story; the dep is upstream and the manifest's DAG is wrong if it's missing.

The only production-shaped change is registering the `adversarial` pytest marker in `pyproject.toml` if S2-03 didn't:

```toml
[tool.pytest.ini_options]
markers = [
    "adversarial: Layer-6 adversarial / threat-model tests (arch §Test pyramid)",
    # ... existing markers
]
```

### Refactor — clean up

- Confirm both tests are < 1 s each. If `drive_to_await_human` is slow, that is an S7-01 problem, not this story's.
- Confirm `pytest tests/adversarial/ -m adversarial` collects exactly the five Phase 6 adversarial tests (3 from S2-03 + 2 from this story).
- Cross-reference the test file headers to the exact arch §Adversarial-tests lines so a future reader can trace the requirement.

## Files to touch

| Path | Why |
|---|---|
| `tests/adversarial/__init__.py` | Package marker (likely already exists from S2-03). |
| `tests/adversarial/test_forged_human_decision_rejected.py` | New — forged-action rejection. |
| `tests/adversarial/test_out_of_order_transition_rejected.py` | New — out-of-order transition rejection. |
| `pyproject.toml` | Register `adversarial` pytest marker if not already present from S2-03. |

## Out of scope

- **Tampered DB / world-readable file / schema drift** — already landed in S2-03.
- **Ed25519 / HMAC / operator-key signing** — explicitly deferred to Phase 11 per ADR-0008.
- **Multi-tenant key isolation** — Phase 16's territory (arch line 1222 + line 1259).
- **Adding a new `as_node` ACL layer in `graph/`** — ADR-0012 forbids it; LangGraph's history is the gatekeeper.
- **The Layer-8 E2E test** — S10-02.
- **ADR commit + Phase 5 regression gate** — S10-03.

## Notes for the implementer

- The forged-action test must use **`model_validate`**, not the constructor. The constructor would also reject the invalid action, but the contract exported to Phase 11 is the JSON-schema path, which goes through `model_validate`. Testing the constructor only would leave a gap on the contract surface.
- LangGraph's exception class for forged `as_node` is undocumented and may change between versions. Match on the **message substring**, not the exception type — the test docstring already calls this out. If you find yourself wanting `pytest.raises(InvalidUpdateError)`, look at LangGraph's source first; if it isn't in the public API, do not import it.
- `drive_to_await_human` should be in `tests/graph/fixtures/scripted_engines.py` after S7-01. If it landed in a different module, surface — do not copy it.
- The chain-head invariance check (chain unchanged after rejected transition) is the load-bearing assertion: it proves the rejection is truly atomic, not a "rejection followed by partial side-effects." If the chain *did* advance, that is a Phase 6 audit-trail bug, not a flake.
- ADR-0008 footnote: when Phase 11 lands the signing layer, this story's tests become the *baseline* — Phase 11's signing tests sit on top. Do not delete these tests when Phase 11 ships; they verify that even without signing, the typed contract holds.
