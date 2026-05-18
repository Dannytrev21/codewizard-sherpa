# Story S6-03 — `SubgraphNode` Protocol + `NodeTransition` sum type (Gap 1 fix)

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** Ready
**Effort:** S
**Depends on:** S6-01
**ADRs honored:** ADR-0010 (tagged-union sum type on every state machine — `NodeTransition`), [Phase 5 ADR-0006](../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md) (Protocol vs ABC: Protocol when no shared default behavior), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (make illegal states unrepresentable)

## Context

The architecture spec's **Gap 1** (`../phase-arch-design.md §Gap analysis & improvements §Gap 1`) called out that the synthesis described the 5-node subgraph (`ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`) as "typed step functions Phase 6 wraps 1-to-1" but **left the transition contract between nodes implicit**. What does "short-circuit" mean? If `match_recipe` returns `RecipeOutcome.NotApplicable`, does the orchestrator skip `apply_recipe` and `stage6_validate`, or does the subgraph emit and the outer loop checks? If `apply_recipe` fails, does Stage 6 still run against an empty transform?

The architecture spec's improvement: specify a `SubgraphNode` Protocol with a typed return — `async def run(self, state: SubgraphState) -> NodeTransition` where `NodeTransition = Advance(state) | ShortCircuit(outcome) | Escalate(reason)`. The orchestrator's outer loop becomes a single `match` over the three transitions:

```python
for node in subgraph.nodes:
    match await node.run(state):
        case Advance(s):       state = s
        case ShortCircuit(o):  return self._finalize(o)
        case Escalate(r):      return self._escalate(r)
```

This eliminates implicit ordering knowledge from individual nodes, gives Phase 6's LangGraph wrap a single pattern to lift (the three `match` arms become three edge types), and makes node-level testability trivial (every node is a function from state to transition).

This story is **small but load-bearing**: every node in S6-04's orchestrator implements this Protocol; S6-04's outer loop is the `match` block above (verbatim, modulo logging); Phase 6's LangGraph migration depends on the `NodeTransition` tagged union being **the** seam, not one of three competing patterns. ADR-0010 §3 commits to tagged-union sum types on every state machine; `NodeTransition` is the state-machine-of-state-machines for the subgraph itself.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 1` — the full gap statement + the resolution this story implements. **Required reading.**
  - `../phase-arch-design.md §Component design C1` — `RemediationOrchestrator`'s 5-stage internal structure ("plain async `for` over typed step-functions" — this story makes those step-functions explicit).
  - `../phase-arch-design.md §Design patterns applied` row 5 — "Tagged union (sum type) on every state machine — `... AdapterConfidence, JailedSubprocessResult, Applicability, ScopeDim (Concrete | Wildcard)`" — `NodeTransition` joins this list.
  - `../phase-arch-design.md §Control flow` step 7 — "Plugin subgraph (5 nodes, sequential): `ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`" — these five names are the concrete nodes S6-04 implements against this Protocol.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision (3) — "Tagged-union sum types on every state machine: ... `Applicability (Applies(plan) | NotApplies(reason))`, `ScopeDim`. Every dispatch site uses `match` + `assert_never`." `NodeTransition` follows the same pattern.
- **Cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md` — Protocol over ABC when there's no shared default behavior; subgraph nodes are textbook (each node is task-specific; nothing is shared).
  - `../../06.5-per-task-class-eval-harness/stories/S1-04-rubric-protocol.md` — already-shipped precedent for a one-method `@runtime_checkable` Protocol that orchestrator-style code dispatches against. Same shape, different domain.
- **This phase, parallel stories:**
  - S6-01 — the `EventLog` nodes use to emit per-stage events (`PluginResolved`, `BundleBuilt`, `RecipeMatched`, etc.).
  - S6-04 — the consumer: the orchestrator's 5 nodes implement this Protocol; the outer loop is the `match` block.
  - S1-03 — `RemediationOutcome` (one of the three `NodeTransition` payloads via `ShortCircuit`).

## Goal

Land `src/codegenie/plugins/subgraph.py` exposing the `SubgraphNode` Protocol, the `SubgraphState` dataclass, and the `NodeTransition = Advance | ShortCircuit | Escalate` Pydantic discriminated union. Cover the Protocol with structural-conformance tests (a duck-typed node passes `isinstance`) and `match`/`assert_never` exhaustiveness tests for `NodeTransition`.

## Acceptance criteria

- [ ] `src/codegenie/plugins/subgraph.py` exists; `from codegenie.plugins.subgraph import SubgraphNode, SubgraphState, NodeTransition, Advance, ShortCircuit, Escalate` succeeds.
- [ ] `SubgraphNode` is `@runtime_checkable` and inherits from `typing.Protocol`. Single method: `async def run(self, state: SubgraphState) -> NodeTransition: ...`. No other methods on the Protocol (any addition requires an ADR amendment).
- [ ] A duck-typed class with `async def run(self, state) -> NodeTransition` passes `isinstance(instance, SubgraphNode)` at runtime.
- [ ] A class missing `run`, or with a synchronous `def run`, or with a wrong-arity `run` fails structural conformance (Protocol catches it).
- [ ] `SubgraphState` is a `frozen=True, extra="forbid"` Pydantic model carrying the subgraph's per-node accumulating state: `workflow_id: WorkflowId`, `cve: CveId`, `resolution: PluginResolution | None`, `bundle: Bundle | None`, `recipe_outcome: RecipeOutcome | None`, `transform: Transform | None`, `trust_outcome: TrustOutcome | None`, `branch: BranchName | None`. Each field starts `None` and is populated as a node advances; `.model_copy(update={...})` is the only mutation pattern.
- [ ] `NodeTransition` is a Pydantic discriminated union (`Discriminator("kind")`) over three variants:
  - `Advance(kind="advance", state: SubgraphState)` — proceed to next node with updated state.
  - `ShortCircuit(kind="short_circuit", outcome: RemediationOutcome)` — orchestrator returns the outcome (e.g., `RemediationOutcome.NotApplicable` from `match_recipe`).
  - `Escalate(kind="escalate", reason: EscalateReason)` — orchestrator escalates (writes partial report + raises). `EscalateReason` is a sealed Literal: `Literal["filesystem_race", "subprocess_jail_unavailable", "audit_chain_corrupted", "vuln_index_corrupted"]`.
- [ ] `assert_never` exhaustiveness test: a `match` over `NodeTransition` with all three arms type-checks; removing one arm and falling through with `case _:` triggers `assert_never` at runtime when that variant is constructed.
- [ ] mypy `--strict` is clean: a stub class implementing `async def run(state: SubgraphState) -> NodeTransition` type-checks as `SubgraphNode` *without* explicit inheritance.
- [ ] The Protocol's `run` body is `...` (literal ellipsis) — not `pass`, not `raise NotImplementedError`. Phase 5 ADR-0006 convention.
- [ ] `SubgraphState.model_copy(update={...})` round-trips through `match` without losing field-level types (regression-tested with a mypy-only test or a `reveal_type` smoke test).
- [ ] A test stub `_StubAdvanceNode`, `_StubShortCircuitNode`, `_StubEscalateNode` exists in the test module; each returns one of the three transitions; each is verified to conform to `SubgraphNode` via `isinstance`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Write `tests/unit/plugins/test_subgraph_protocol.py` (red); confirm `ImportError`.
2. Create `src/codegenie/plugins/subgraph.py`:
   - Imports: `from collections.abc import Awaitable`, `from typing import Annotated, Literal, Protocol, runtime_checkable`, `from pydantic import BaseModel, ConfigDict, Discriminator`, identifiers + outcomes from sibling modules.
   - `SubgraphState` Pydantic model (frozen, extra=forbid).
   - `class Advance(BaseModel): kind: Literal["advance"] = "advance"; state: SubgraphState`. Same for `ShortCircuit` and `Escalate`. All `frozen=True, extra="forbid"`.
   - `EscalateReason: TypeAlias = Literal["filesystem_race", "subprocess_jail_unavailable", "audit_chain_corrupted", "vuln_index_corrupted"]`.
   - `NodeTransition: TypeAlias = Annotated[Advance | ShortCircuit | Escalate, Discriminator("kind")]`.
   - `@runtime_checkable class SubgraphNode(Protocol): async def run(self, state: SubgraphState) -> NodeTransition: ...`.
   - Module docstring naming `Gap 1` from `../phase-arch-design.md` and ADR-0010.
   - `__all__ = [...]` listing every export.
3. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/plugins/test_subgraph_protocol.py`.

```python
# tests/unit/plugins/test_subgraph_protocol.py
from typing import assert_never

import pytest

from codegenie.plugins.subgraph import (
    SubgraphNode, SubgraphState, NodeTransition,
    Advance, ShortCircuit, Escalate,
)
from codegenie.transforms.transform import RemediationOutcome
from codegenie.types.identifiers import WorkflowId, CveId


def _state() -> SubgraphState:
    return SubgraphState(workflow_id=WorkflowId("01HFEEDFACE0000000000000000"),
                         cve=CveId("CVE-2024-21501"))


class _AdvanceNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return Advance(state=state.model_copy(update={"branch": None}))


class _ShortCircuitNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return ShortCircuit(outcome=_failed_outcome())


class _EscalateNode:
    async def run(self, state: SubgraphState) -> NodeTransition:
        return Escalate(reason="filesystem_race")


class _MissingRunNode:
    async def evaluate(self, state):  # wrong name — should fail isinstance
        ...


class _SyncRunNode:
    def run(self, state: SubgraphState) -> NodeTransition:  # not async
        return Advance(state=state)


def _failed_outcome() -> RemediationOutcome:
    # Construct a minimal Failed variant (signature TBD by S1-03).
    ...


def test_protocol_is_runtime_checkable():
    assert isinstance(_AdvanceNode(), SubgraphNode)
    assert isinstance(_ShortCircuitNode(), SubgraphNode)
    assert isinstance(_EscalateNode(), SubgraphNode)


def test_missing_run_fails_isinstance():
    assert not isinstance(_MissingRunNode(), SubgraphNode)


def test_sync_run_fails_isinstance():
    # @runtime_checkable Protocols can't structurally check async-vs-sync;
    # this test asserts the typing expectation via mypy (revealed_type smoke).
    # At runtime, isinstance returns True for any class with `run`; the type
    # check is the enforcement (mypy --strict).
    # We exercise an actual await to confirm the contract at runtime:
    import asyncio
    node: SubgraphNode = _SyncRunNode()  # type: ignore[assignment]
    with pytest.raises(TypeError):
        asyncio.get_event_loop().run_until_complete(node.run(_state()))


@pytest.mark.asyncio
async def test_advance_returns_advance_variant():
    transition = await _AdvanceNode().run(_state())
    assert isinstance(transition, Advance)
    assert transition.kind == "advance"


@pytest.mark.asyncio
async def test_short_circuit_returns_short_circuit_variant():
    transition = await _ShortCircuitNode().run(_state())
    assert isinstance(transition, ShortCircuit)
    assert transition.kind == "short_circuit"


@pytest.mark.asyncio
async def test_escalate_returns_escalate_variant():
    transition = await _EscalateNode().run(_state())
    assert isinstance(transition, Escalate)
    assert transition.kind == "escalate"
    assert transition.reason == "filesystem_race"


@pytest.mark.asyncio
async def test_orchestrator_outer_loop_pattern_match_is_exhaustive():
    """The outer loop is a single `match` over all three NodeTransition arms.

    This is the pattern S6-04's orchestrator implements verbatim. If a future
    refactor adds a fourth variant without updating consumers, this test
    triggers the assert_never fall-through and fails loud.
    """
    nodes: list[SubgraphNode] = [_AdvanceNode(), _ShortCircuitNode(), _EscalateNode()]
    for node in nodes:
        transition = await node.run(_state())
        match transition:
            case Advance(state=s):
                assert s.workflow_id == _state().workflow_id
            case ShortCircuit(outcome=o):
                assert o is not None
            case Escalate(reason=r):
                assert r in {"filesystem_race", "subprocess_jail_unavailable",
                             "audit_chain_corrupted", "vuln_index_corrupted"}
            case _:
                assert_never(transition)


def test_subgraph_state_is_frozen():
    s = _state()
    with pytest.raises(Exception):
        s.workflow_id = WorkflowId("other")  # type: ignore[misc]


def test_subgraph_state_model_copy_preserves_workflow_id():
    s = _state()
    s2 = s.model_copy(update={"cve": CveId("CVE-9999-9999")})
    assert s2.workflow_id == s.workflow_id
    assert s2.cve == CveId("CVE-9999-9999")
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

The body of `subgraph.py` is ~40 lines: three `BaseModel` variants, one Protocol, one TypeAlias, one `SubgraphState` model. No clever code. The Protocol's body is `...`. The discriminated union uses the same `Annotated[... | ... | ..., Discriminator("kind")]` pattern as `RecipeOutcome` and `RemediationOutcome` (S1-03).

### Refactor — clean up

- Module docstring cites Gap 1 + ADR-0010 + Phase 5 ADR-0006.
- One-line class docstrings on each of `Advance`, `ShortCircuit`, `Escalate` explaining what the orchestrator does in response.
- Confirm mypy `--strict` resolves all forward references (use `from __future__ import annotations` if needed).
- Verify the `EscalateReason` Literal is closed — adding a new reason requires an ADR amendment (document this expectation in the module docstring).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/subgraph.py` | New file — `SubgraphNode` Protocol, `SubgraphState`, `NodeTransition` discriminated union, `Advance`/`ShortCircuit`/`Escalate`, `EscalateReason` Literal |
| `tests/unit/plugins/test_subgraph_protocol.py` | New file — structural conformance, async/sync rejection, three-variant exhaustiveness via `match` + `assert_never`, `SubgraphState` immutability |

## Out of scope

- **The 5 concrete node implementations** (`ingest_cve`, `match_recipe`, `apply_recipe`, `stage6_validate`, `write_branch`) — S6-04 lands them as classes implementing this Protocol.
- **The orchestrator's outer `match` loop** — S6-04 lands it. This story only proves the loop is `match`-able.
- **LangGraph integration** — Phase 6 wraps these arms as LangGraph edges; out of scope here.
- **`SubgraphState` field additions for Phase 4 (LLM-fallback)** — Phase 4 adds optional fields additively (e.g., `llm_attempts: list[LLMAttempt] = Field(default_factory=list)`); zero edits to this story's code.
- **Cancellation / timeout semantics on `await node.run(state)`** — the orchestrator (S6-04) owns timeouts via `asyncio.wait_for`; the Protocol carries no cancellation contract.
- **Per-node retry policy** — Phase 3 alone does NOT retry (ADR-0007); Phase 5's `GateRunner` is the retry envelope.

## Notes for the implementer

- This story is **deceptively small**. The Protocol body is one method; the discriminated union has three variants. But the *shape* is the load-bearing decision: every node in S6-04 implements this Protocol, every outer-loop `match` arm consumes one of the three transitions, every Phase 6 LangGraph edge is one of the three. Wide influence per LOC.
- Resist the urge to add methods to `SubgraphNode`. A reviewer might suggest `name: str` (for logging) or `requires_capabilities: set[Capability]` (for pre-flight checks). **Reject both.** Logging is the orchestrator's concern; node identity comes from `type(node).__name__`. Capability pre-flight is `CapabilityBundle` on `ApplyContext` (already part of S1-04). Widening the Protocol forces every existing node + every future Phase 6 LangGraph edge to update — exactly the anti-pattern the open-registry design avoids.
- The `NodeTransition` discriminator is `"kind"` — same field name as `RecipeOutcome`, `RemediationOutcome`, `PluginResolution`. Uniformity matters (ADR-0010 §Decision: "Every dispatch site uses `match` + `assert_never`"). A reviewer suggesting `"transition_type"` instead is wrong; convention beats local taste.
- The Protocol body must be `...`, not `pass`, not `raise NotImplementedError`. Phase 5 ADR-0006 convention. The S1-04 rubric-protocol story carries the same rationale verbatim.
- `EscalateReason` is a closed `Literal[...]` of exactly 4 values. If a sixth concrete node (Phase 7's distroless plugin?) needs a new escalation reason, that's an additive `Literal[...]` change with an ADR amendment. The Literal is the closed-for-modification surface.
- `SubgraphState` is `frozen=True`. Nodes return `state.model_copy(update={"recipe_outcome": ...})` to advance; they never mutate. This is the same pattern Phase 5's `GateContext` uses (per `../../05-sandbox-trust-gates/final-design.md`). Reviewers who suggest `state.recipe_outcome = ...` for "convenience" should be redirected to the immutability contract.
- The `async def run` signature is intentionally async even though some nodes (e.g., `ingest_cve` if the data is already in memory) might be synchronous. Uniformity wins — the orchestrator's outer loop is one `await`, not a conditional dispatch on `asyncio.iscoroutine`.
- The runtime `isinstance(node, SubgraphNode)` check is *only* used in tests. Production code (the orchestrator) takes a `SubgraphNode` parameter; mypy `--strict` does the structural verification at type-check time. Do NOT add a registry-time `isinstance` check in S6-04 — the S1-04 precedent explicitly notes this (registries don't `isinstance`-check Protocols).
- The "sync run rejected" test exercises the runtime contract (`await` raises `TypeError` on a non-coroutine). The Protocol itself can't structurally check async-vs-sync at `isinstance` time (PEP 544 limitation). The combination — mypy `--strict` at type-check + runtime `TypeError` at call — is the enforcement.
- Phase 6's LangGraph wrap is the natural next step. Each `match` arm becomes an edge: `Advance` → next-node edge; `ShortCircuit` → finalize edge; `Escalate` → error-handler edge. Phase 6's design depends on this story's three-arm shape being the **only** outer-loop shape. Adding a fourth arm later means Phase 6 re-architects.
