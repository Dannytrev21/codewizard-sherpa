# S5-01 — Implement `build_vuln_loop()` lazy-singleton + topology wiring

**Step:** Step 5 — Implement `build_vuln_loop()` lazy-singleton factory + topology golden + `interrupt_before`
**Effort:** M
**Depends on:** S3-03 (edge property tests green), S4-02 (`ingest_cve` + `select_recipe` nodes shipped), S4-10 (ADR-P6-001 `run_one` promotion landed; all ten nodes wired)
**Status:** Backlog
**ADRs honored:** ADR-0001 (lazy-singleton factory), ADR-0002 (`VulnLedger` `extra="forbid", frozen=False`), ADR-0012 (pure-edge discipline — edges already shipped in Step 3), ADR-0009 (`cli/loop.py` parallel to `cli/remediate.py` — this story preserves the seam by not editing `cli/remediate.py`)

## Context

The previous four steps shipped every prerequisite: the `VulnLedger` contract, the HITL contracts, the after-node mutation hook, the `AuditedSqliteSaver`, the four `@pure_edge` conditional predicates, and the ten node bodies. They are still strangers: nothing has assembled them into a `StateGraph[VulnLedger]` yet. This story is that assembly.

Two non-trivial choices are baked in:

1. **The factory is a lazy singleton, not a module constant.** `critique.md performance.4` killed the module-level-constant pick: a constant bakes the checkpointer into module import time, so the CLI's `--checkpointer-db` flag and every test that swaps checkpointers becomes a no-op. The lazy singleton — a module-level `_COMPILED` populated on first call, keyed on `(id(checkpointer), max_attempts)`, bustable via `force_rebuild=True` — gives both the production worker (compile cost paid once) and the test suite (fresh checkpointer per test) what they need. ADR-0001 is the load-bearing decision.
2. **`interrupt_before=["await_human"]` is set at compile time.** The `await_human` node body never runs without an external resume. LangGraph fires the interrupt **before** the body executes, on the entry-checkpoint frame. The CLI inspects `aget_tuple` to detect the pause and exits 12. Setting `interrupt_before` at compile time (not at invocation time) is what makes the topology and the operator-visible behavior consistent.

This story does **not** ship the topology golden file (S5-02) or the cold-start perf canary (S5-03). It ships the factory, the `_build()` function that wires the topology per arch §Component 2, and a unit-level proof that the compile succeeds and the cache busts only when expected.

## References — where to look

- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Component 2 "build_vuln_loop()" — the canonical pseudo-code (lines 562–629); reproduce its `_build()` topology verbatim (10 nodes, 4 conditional edges via `add_conditional_edges`, 5 unconditional via `add_edge`, two `END`s).
- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Logical view (class diagram) — the `+build_vuln_loop()` signature.
- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Scenarios — Scenario 1 (happy path) and Scenario 2 (HITL pause + resume) name the exact call site shape; do not invent new shapes.
- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Edge cases #13 (non-conforming `BaseCheckpointSaver` → `compile()` raises) and #14 (`force_rebuild=False` with new checkpointer object — covered by `test_compile_cache_uses_force_rebuild`).
- `docs/phases/06-sherpa-state-machine/ADRs/0001-lazy-singleton-build-vuln-loop-factory.md` — the why; cite in PR description.
- `docs/phases/06-sherpa-state-machine/High-level-impl.md` §Step 5 — done criteria and risks.
- `docs/phases/06-sherpa-state-machine/final-design.md` §Synthesis ledger row 7 ("Module-level vs per-invocation") — the conflict and its resolution.

## Goal (one sentence)

Ship `src/codegenie/graph/vuln_loop.py` so that `build_vuln_loop(checkpointer=InMemorySaver())` returns a `CompiledGraph` whose topology is exactly the 10-node × 4-conditional × 5-unconditional shape in arch §Component 2, with `interrupt_before=["await_human"]` set, and a module-level `_COMPILED` cache keyed on `(id(checkpointer), max_attempts)` bustable via `force_rebuild=True`.

## Acceptance criteria

- [ ] `build_vuln_loop(*, checkpointer, max_attempts: int = 3, force_rebuild: bool = False) -> CompiledGraph` exists in `src/codegenie/graph/vuln_loop.py` with that exact signature (keyword-only after `*`).
- [ ] Internal `_build(max_attempts: int) -> StateGraph[VulnLedger]` registers the 10 nodes (`ingest_cve`, `select_recipe`, `apply_recipe`, `rag_lookup`, `replan_with_phase4`, `validate_in_sandbox`, `record_attempt`, `await_human`, `emit_artifact`, `escalate`), sets `ingest_cve` as the entry point, adds the four conditional edges (`select_recipe`, `rag_lookup`, `record_attempt`, `await_human`) with the label dicts exactly as arch §Component 2, adds the five unconditional edges, and terminates `emit_artifact` and `escalate` at `END`.
- [ ] `compile()` is invoked with `checkpointer=<arg>` and `interrupt_before=["await_human"]`; both are observable via `compiled.get_graph()` (interrupt) and a `compile_kwargs` capture in a test.
- [ ] Module-level `_COMPILED: CompiledGraph | None = None` and `_COMPILED_KEY: tuple[int, int] | None = None` are reused for cache hits; same `(id(checkpointer), max_attempts)` → same `id(compiled)` across two consecutive calls; `force_rebuild=True` or a key change → new `id(compiled)`.
- [ ] `__init__.py` exports `build_vuln_loop` (alongside `VulnLedger`, `HumanRequest`, `HumanDecision`) per arch §Development view.
- [ ] **Red test exists and was committed before the implementation** (see TDD plan); it now passes.
- [ ] `ruff format`, `ruff check`, `mypy --strict src/codegenie/graph/`, and `pytest tests/graph/` are clean. **No `Any`, no `cast`, no unjustified `# type: ignore`.**

## Implementation outline

1. **Create `src/codegenie/graph/vuln_loop.py`.** Imports: `from langgraph.graph import StateGraph, END`, `from langgraph.checkpoint.base import BaseCheckpointSaver`, and the ten node callables from `graph.nodes.*` plus the four edge predicates from `graph.edges`. `VulnLedger` from `graph.state`. **Do not import siblings of `graph.nodes` into other nodes — fence-CI from S1-01 enforces this.**
2. **Declare module-level cache state.** `_COMPILED: CompiledGraph | None = None` and `_COMPILED_KEY: tuple[int, int] | None = None`. Both `# noqa: <none>` — these are deliberate module-level mutables justified by ADR-0001.
3. **Write `_build(max_attempts: int) -> StateGraph[VulnLedger]`.** Reproduce arch §Component 2 pseudo-code verbatim. Register 10 nodes; set entry point `ingest_cve`; add the four `add_conditional_edges` calls with the exact label-dict shape; add the five `add_edge` calls; add `add_edge("emit_artifact", END)` and `add_edge("escalate", END)`. `max_attempts` is not consumed inside `_build` directly (it lives on `VulnLedger.max_attempts`) but the parameter exists so that the cache key changes when the default is overridden at CLI time — keep the parameter and document the design intent in a one-line comment.
4. **Write `build_vuln_loop(*, checkpointer, max_attempts=3, force_rebuild=False)`.** Body matches arch §Component 2 pseudo-code: compute `key = (id(checkpointer), max_attempts)`; if `force_rebuild or _COMPILED is None or _COMPILED_KEY != key`, recompile with `interrupt_before=["await_human"]` and update both module globals; return `_COMPILED`.
5. **Export from `__init__.py`.** Add `build_vuln_loop` to `__all__` and the explicit `from .vuln_loop import build_vuln_loop` line. Verify the package's existing exports (S1-02 / S1-03 shipped `VulnLedger`, `HumanRequest`, `HumanDecision`) are not disturbed — surgical edit, no reordering.
6. **Add `tests/graph/conftest.py` fixture docstring** (if not already present from S4-01) that documents the `force_rebuild=True` discipline for any fixture that swaps checkpointers. Per ADR-0001, the silent-stale-cache failure mode is the cost the discipline pays for; the docstring is the mitigation.
7. **Do not touch `src/codegenie/cli/remediate.py`.** ADR-0009 requires Phase 6 to ship `cli/loop.py` as a parallel command surface; this story does not even add `cli/loop.py` (Step 6 owns it). Verify post-merge: `git diff master -- src/codegenie/cli/remediate.py` is empty.

## TDD plan (red → green → refactor)

**Red — `tests/graph/test_build_vuln_loop_compiles.py`** (commit first, before the implementation file exists):

```python
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from codegenie.graph import build_vuln_loop


def test_build_vuln_loop_compiles_with_in_memory_saver():
    """The factory returns a CompiledGraph for a valid BaseCheckpointSaver."""
    compiled = build_vuln_loop(checkpointer=InMemorySaver(), force_rebuild=True)
    assert compiled is not None
    # LangGraph exposes the inspected graph form via get_graph()
    g = compiled.get_graph()
    node_ids = {n.id for n in g.nodes.values()}
    assert node_ids == {
        "__start__", "__end__",
        "ingest_cve", "select_recipe", "apply_recipe", "rag_lookup",
        "replan_with_phase4", "validate_in_sandbox", "record_attempt",
        "await_human", "emit_artifact", "escalate",
    }


def test_build_vuln_loop_sets_interrupt_before_await_human():
    """interrupt_before=['await_human'] is wired at compile time."""
    compiled = build_vuln_loop(checkpointer=InMemorySaver(), force_rebuild=True)
    # LangGraph stores this on the compiled object; the API surface
    # may be `compiled.interrupt_before_nodes` or `compiled.builder.interrupt_before`.
    # Probe at test time and pin the exact accessor.
    assert "await_human" in (
        getattr(compiled, "interrupt_before_nodes", None)
        or compiled.builder.interrupt_before
        or []
    )


def test_build_vuln_loop_caches_on_same_key():
    """Same (id(checkpointer), max_attempts) → same compiled object."""
    saver = InMemorySaver()
    first = build_vuln_loop(checkpointer=saver, force_rebuild=True)
    second = build_vuln_loop(checkpointer=saver)
    assert first is second  # id-equal; cache hit


def test_force_rebuild_busts_cache():
    """force_rebuild=True always recompiles, even on a key hit."""
    saver = InMemorySaver()
    first = build_vuln_loop(checkpointer=saver, force_rebuild=True)
    second = build_vuln_loop(checkpointer=saver, force_rebuild=True)
    assert first is not second


def test_changing_max_attempts_busts_cache():
    """Cache key includes max_attempts."""
    saver = InMemorySaver()
    a = build_vuln_loop(checkpointer=saver, max_attempts=3, force_rebuild=True)
    b = build_vuln_loop(checkpointer=saver, max_attempts=5)
    assert a is not b


def test_topology_has_four_conditional_edges():
    """The 4 conditional-edge sites are wired exactly once each."""
    compiled = build_vuln_loop(checkpointer=InMemorySaver(), force_rebuild=True)
    g = compiled.get_graph()
    # Sources that participate in conditional edges per arch §Component 2.
    conditional_sources = {
        "select_recipe", "rag_lookup", "record_attempt", "await_human",
    }
    actual_conditional_sources = {
        e.source for e in g.edges if e.conditional
    }
    assert actual_conditional_sources == conditional_sources
```

Commit message: `test(graph): red — build_vuln_loop factory + interrupt_before + cache (S5-01)`.

**Green — minimal implementation.** Implement `vuln_loop.py` per the outline. Don't golden-file the topology yet (S5-02), don't measure cold-start time (S5-03), don't ship the CLI (S6-01). Just enough for the five tests above plus mypy strict to pass.

**Refactor.** Two specific tidies, no more:

- If the LangGraph accessor for `interrupt_before` is awkward in the test (probe-time discovery), promote it to a tiny helper `_interrupt_before_of(compiled) -> list[str]` in `tests/graph/conftest.py` and use it from S5-02's reachability test as well. Single point of API drift.
- Verify `__init__.py`'s `__all__` is sorted (project convention). If S1-02 / S1-03 didn't sort, do **not** sort retroactively (Rule 3 — surgical).

## Files to touch

- **New:** `src/codegenie/graph/vuln_loop.py`
- **New:** `tests/graph/test_build_vuln_loop_compiles.py`
- **Edit (additive only):** `src/codegenie/graph/__init__.py` — append `build_vuln_loop` to `__all__` and re-export.
- **Edit (additive only, if not already present from S4-01):** `tests/graph/conftest.py` — `force_rebuild=True` discipline docstring; optional `_interrupt_before_of` helper.

## Out of scope

- **Topology golden file** — S5-02 ships `tests/golden/vuln_loop_topology.json` and the canonicalization machinery.
- **Reachability tests** — S5-02.
- **Cold-start perf canary** — S5-03 ships `tests/perf/test_compile_cold_start.py`.
- **`tools/policy/graph-thresholds.yaml`** — S5-03.
- **CLI `codegenie loop` group** — Step 6.
- **Anything that touches `cli/remediate.py`** — ADR-0009 prohibits.
- **Adding a `max_attempts` argument to `_build()` that mutates topology** — `max_attempts` lives on `VulnLedger` and is read by `route_after_attempt`; the parameter is in the cache key only so that operators can A/B different limits without stale-cache hits.

## Notes for the implementer

- **Probe LangGraph's `interrupt_before` accessor at the REPL first** before writing the test. Library minor versions move it (`compiled.interrupt_before_nodes` vs `compiled.builder.interrupt_before`). Pin the exact accessor your installed version uses; do not branch on `hasattr`.
- **The cache uses `id(checkpointer)`, not value equality.** Two structurally-identical `InMemorySaver()` instances have different `id()`s and will recompile. This is by design (ADR-0001 §Tradeoffs); call it out in the PR description and do not "improve" to value-equality.
- **`StateGraph(VulnLedger)` must accept the Pydantic state class directly.** If LangGraph's generic-parameterization API has shifted between minor versions (`StateGraph[VulnLedger]` vs `StateGraph(VulnLedger)`), use whatever the installed `langgraph >= 0.2.x` requires; document the chosen form with a one-line comment.
- **The five `add_edge` lines + two `END` lines + four `add_conditional_edges` lines are load-bearing.** Mistyping a label key (`"matched"` vs `"match"`) silently breaks routing without LangGraph complaining at compile time — the topology golden in S5-02 will catch it, but you should also eyeball the labels against arch §Component 2 before committing.
- **Do not pre-compute `_COMPILED` at module import.** That defeats ADR-0001. The first call to `build_vuln_loop()` populates it.
- **Fence-CI rule (from S1-01) will flag** any `import random / time / os / datetime` in `vuln_loop.py` — there shouldn't be any. `datetime.fromisoformat` is whitelisted but you have no reason to need it here.
- If you find the `langgraph` import surface has churned (e.g., `END` moved), surface that in the PR description and pin the import path with a comment citing the exact version — don't paper over it with a `try/except ImportError`.
- **mypy strict will probably complain about `_COMPILED: CompiledGraph | None`.** That's correct — the union is real. Don't `cast(CompiledGraph, _COMPILED)` to silence it; narrow with an explicit `assert _COMPILED is not None` after the populate branch.
