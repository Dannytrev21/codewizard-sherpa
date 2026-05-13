# Story S5-04 — `build_distroless_loop` factory + edges + topology golden

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** M
**Depends on:** S5-03, S2-07
**ADRs honored:** ADR-P7-001 (parallel ledger; parallel factory), ADR-P7-005 (no shared dispatcher), Phase 6 ADR-0001 (lazy-singleton factory pattern reused verbatim), Phase 6 ADR-0012 (pure-edge discipline — extends to `route_after_resolve_target`)

## Context

This story assembles the 11 distroless nodes (from S5-02 and S5-03) into a compiled `StateGraph[DistrolessLedger]` and ships the factory + topology golden file. It mirrors Phase 6's `build_vuln_loop()` shape *verbatim* — same lazy-singleton pattern, same `(id(checkpointer), max_attempts)` cache key, same `interrupt_before=["await_human"]`, same `@pure_edge` discipline. The deliberate divergence from vuln is the one extra node (`resolve_target_image`) and its companion conditional edge predicate (`route_after_resolve_target` returning `Literal["ok","catalog_miss"]`).

Per `phase-arch-design.md §Component 7` and ADR-P7-001's "parallel factory" decision, this story does **not** introduce a shared base factory or extract common compile logic. Phase 8's supervisor is the right place for unification (ADR-0022 strike two).

The topology golden file (`tests/golden/distroless_loop_topology.json`) is the mechanical check that Phase 8 or any later phase has not silently re-wired the graph. It's also the artifact Step 8's snapshot-discipline rehearsals (S8-04) target.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 — build_distroless_loop()` (lines 682–711) — the canonical pseudo-code; 11-node list; cache-key shape; `interrupt_before`.
  - `../phase-arch-design.md §Logical view` — class diagram; `+build_distroless_loop()` signature.
  - `../phase-arch-design.md §Process view` — fsync/checkpoint discipline; per-node boundary.
  - `../phase-arch-design.md §Decision points` table — `route_after_resolve_target` returns `Literal["ok","catalog_miss"]`.
  - `../phase-arch-design.md §Development view` — `graph/edges.py` *additive* extension note: "Note: this is an *additive function in an existing file* — verify against ADR-P7-001..006 to confirm it falls under the seam set; if not, file under `graph/edges_distroless.py`".
  - `../phase-arch-design.md §Edge cases #13` (non-conforming `BaseCheckpointSaver` → `compile()` raises), `#15` (`python -O` strips `@pure_edge`).
- **Phase ADRs:**
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-001 — parallel factory; no shared base.
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-005 — CLI dispatch parallel; factory is the integration seam Phase 8's supervisor consumes.
- **Source design:**
  - `../final-design.md §Synthesis ledger row 7` — module-level vs per-invocation; same as Phase 6.
- **Existing code:**
  - `src/codegenie/graph/vuln_loop.py` (Phase 6 S5-01) — the canonical factory pattern; mirror byte-for-byte except for node list, edge predicates, and the new `_COMPILED_DL`/`_COMPILED_KEY_DL` symbol names.
  - `src/codegenie/graph/edges.py` (Phase 6 S3-02) — existing `@pure_edge` predicates; `route_after_resolve_target` lives here as an additive function *if* ADR-P7-001..006 permits, *or* in `graph/edges_distroless.py` (new file) otherwise.
  - `tests/golden/vuln_loop_topology.json` (Phase 6 S5-02) — mirror the canonicalization scheme.

## Goal

Land `src/codegenie/graph/distroless_loop.py` with `build_distroless_loop(*, checkpointer, max_attempts=3, force_rebuild=False) -> CompiledGraph`; wire the 11-node topology + the new `route_after_resolve_target` `@pure_edge` predicate; ship `tests/golden/distroless_loop_topology.json` as the canonical topology canary.

## Acceptance criteria

- [ ] `build_distroless_loop(*, checkpointer: BaseCheckpointSaver, max_attempts: int = 3, force_rebuild: bool = False) -> CompiledGraph` exists in `src/codegenie/graph/distroless_loop.py` with that exact signature (keyword-only after `*`).
- [ ] Internal `_build(max_attempts: int) -> StateGraph[DistrolessLedger]` registers the 11 nodes (`ingest_target`, `resolve_target_image`, `select_recipe`, `rag_lookup`, `replan_with_phase4`, `apply_recipe`, `validate_in_sandbox`, `record_attempt`, `await_human`, `emit_artifact`, `escalate`); sets `ingest_target` as the entry point; wires the conditional edges per arch §Component 7 (including the new `route_after_resolve_target`); wires the unconditional edges; terminates `emit_artifact` and `escalate` at `END`.
- [ ] `compile()` is invoked with `checkpointer=<arg>` and `interrupt_before=["await_human"]`; both are observable via `compiled.get_graph()` + a `compile_kwargs` capture in a test.
- [ ] Module-level `_COMPILED: CompiledGraph | None = None` and `_COMPILED_KEY: tuple[int, int] | None = None` (or analogously-named to avoid collision with `vuln_loop.py`'s symbols) — same `(id(checkpointer), max_attempts)` → same `id(compiled)` across two consecutive calls; `force_rebuild=True` or a key change → new `id(compiled)`.
- [ ] `route_after_resolve_target` exists, decorated with `@pure_edge`, and returns `Literal["ok", "catalog_miss"]`. Decision: located either in `src/codegenie/graph/edges.py` (additive function — *only* if covered by an ADR-P7-001..006 seam) OR `src/codegenie/graph/edges_distroless.py` (new file — preferred per arch §Development view note).
- [ ] `tests/golden/distroless_loop_topology.json` is committed: `compiled.get_graph().to_json()` canonicalized (sorted keys, fixed separators); a test compares byte-for-byte and updates via `pytest --update-golden`.
- [ ] `src/codegenie/graph/__init__.py` exports `build_distroless_loop` (alongside `DistrolessLedger` from S5-01 and `build_vuln_loop` from Phase 6).
- [ ] Red tests exist, are committed, and now pass.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/distroless_loop.py src/codegenie/graph/edges_distroless.py`, and `pytest tests/graph/test_build_distroless_loop*.py tests/golden/` all pass.

## Implementation outline

1. Decide where `route_after_resolve_target` lives. Per arch §Development view: "verify against ADR-P7-001..006 to confirm it falls under the seam set; if not, file as a new file under `graph/edges_distroless.py`". The cautious choice is the new file — no ambiguity, no ADR-0028 amendment exposure. Pick `graph/edges_distroless.py`.
2. Write `route_after_resolve_target(state: DistrolessLedger) -> Literal["ok", "catalog_miss"]` with the `@pure_edge` decorator; returns `"ok"` when `state.target_image_recommendation is not None` else `"catalog_miss"`.
3. Create `src/codegenie/graph/distroless_loop.py`. Mirror `vuln_loop.py`'s shape: module-level `_COMPILED`, `_COMPILED_KEY`; `_build` function; `build_distroless_loop` public factory.
4. In `_build`: register 11 nodes via `StateGraph(DistrolessLedger).add_node(...)`; set entry point `ingest_target`; add conditional edges:
   - `resolve_target_image` → `{"ok": "select_recipe", "catalog_miss": "await_human"}` (via `route_after_resolve_target`)
   - `select_recipe` → `{"matched": "apply_recipe", "miss": "rag_lookup"}` (Phase 6 reused)
   - `rag_lookup` → `{"hit": "apply_recipe", "miss": "replan_with_phase4"}` (Phase 6 reused)
   - `record_attempt` → `{"passed": "emit_artifact", "retry_phase4": "replan_with_phase4", "retry_exhausted": "await_human", "non_retryable": "await_human"}` (Phase 6 reused)
   - `await_human` → `{"continue": "apply_recipe", "override": "apply_recipe", "abort": "escalate"}` (Phase 6 reused)
5. Add unconditional edges: `ingest_target → resolve_target_image`, `replan_with_phase4 → apply_recipe`, `apply_recipe → validate_in_sandbox`, `validate_in_sandbox → record_attempt`. Terminate `emit_artifact` and `escalate` at `END`.
6. In `build_distroless_loop`: compute `key = (id(checkpointer), max_attempts)`; if `force_rebuild or _COMPILED is None or _COMPILED_KEY != key`, recompile with `interrupt_before=["await_human"]`; return `_COMPILED`.
7. Generate the topology golden — run `build_distroless_loop(InMemorySaver(), force_rebuild=True).get_graph().to_json()`, canonicalize, write to `tests/golden/distroless_loop_topology.json`. Commit.
8. Tests: factory compile, interrupt_before wiring, cache hit/miss, `route_after_resolve_target` predicate, topology golden match.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test files: `tests/graph/test_build_distroless_loop.py`, `tests/graph/test_distroless_edges.py`, `tests/golden/test_distroless_loop_topology_golden.py`.

```python
# tests/graph/test_build_distroless_loop.py
def test_build_distroless_loop_compiles_with_in_memory_saver() -> None:
    compiled = build_distroless_loop(checkpointer=InMemorySaver(), force_rebuild=True)
    assert compiled is not None
    g = compiled.get_graph()
    node_ids = {n.id for n in g.nodes.values()}
    assert node_ids == {
        "__start__", "__end__",
        "ingest_target", "resolve_target_image", "select_recipe", "rag_lookup",
        "replan_with_phase4", "apply_recipe", "validate_in_sandbox",
        "record_attempt", "await_human", "emit_artifact", "escalate",
    }


def test_build_distroless_loop_sets_interrupt_before_await_human() -> None:
    compiled = build_distroless_loop(checkpointer=InMemorySaver(), force_rebuild=True)
    assert "await_human" in (
        getattr(compiled, "interrupt_before_nodes", None)
        or compiled.builder.interrupt_before
        or []
    )


def test_build_distroless_loop_caches_on_same_key() -> None:
    saver = InMemorySaver()
    first = build_distroless_loop(checkpointer=saver, force_rebuild=True)
    second = build_distroless_loop(checkpointer=saver)
    assert first is second


def test_force_rebuild_busts_cache() -> None:
    saver = InMemorySaver()
    a = build_distroless_loop(checkpointer=saver, force_rebuild=True)
    b = build_distroless_loop(checkpointer=saver, force_rebuild=True)
    assert a is not b


def test_distroless_factory_distinct_from_vuln_factory() -> None:
    """ADR-P7-001 — parallel factories, no shared base."""
    saver = InMemorySaver()
    dl = build_distroless_loop(checkpointer=saver, force_rebuild=True)
    vl = build_vuln_loop(checkpointer=saver, force_rebuild=True)
    assert dl is not vl
    # And the node sets differ
    dl_nodes = {n.id for n in dl.get_graph().nodes.values()}
    vl_nodes = {n.id for n in vl.get_graph().nodes.values()}
    assert "resolve_target_image" in dl_nodes
    assert "resolve_target_image" not in vl_nodes
```

```python
# tests/graph/test_distroless_edges.py
def test_route_after_resolve_target_ok_when_recommendation_present() -> None:
    state = _make_state(target_image_recommendation=_make_rec())
    assert route_after_resolve_target(state) == "ok"


def test_route_after_resolve_target_catalog_miss_when_none() -> None:
    state = _make_state(target_image_recommendation=None)
    assert route_after_resolve_target(state) == "catalog_miss"


def test_route_after_resolve_target_is_pure_edge() -> None:
    """Decorated with @pure_edge per Phase 6 ADR-0012 discipline."""
    assert getattr(route_after_resolve_target, "__pure_edge__", False) is True
```

```python
# tests/golden/test_distroless_loop_topology_golden.py
def test_distroless_loop_topology_matches_golden() -> None:
    compiled = build_distroless_loop(checkpointer=InMemorySaver(), force_rebuild=True)
    canonical = canonical_json(compiled.get_graph().to_json())
    expected = (REPO_ROOT / "tests/golden/distroless_loop_topology.json").read_bytes()
    assert canonical == expected, (
        "Distroless loop topology drifted. Regenerate with:\n"
        "    pytest --update-golden tests/golden/test_distroless_loop_topology_golden.py"
    )
```

Run each; confirm all fail. Commit.

### Green — make it pass

Author `edges_distroless.py` first (1 small function); then `distroless_loop.py` (mirror `vuln_loop.py`); then run the topology test once with `--update-golden` to seed `tests/golden/distroless_loop_topology.json`.

### Refactor — clean up

- Add module docstring on `distroless_loop.py` citing arch §Component 7 and the divergence from `vuln_loop.py` (one extra node, one extra edge predicate, parallel factory per ADR-P7-001).
- Add canonical-JSON helper reuse from Phase 6's `tests/graph/_canonical.py`.
- Confirm no `random`, no `time` imports (fence-CI under `graph/`).
- Confirm the topology golden is canonical-sorted — Pydantic/JSON ordering must be stable across Python minor versions.
- Per arch §Edge cases #13: passing a non-`BaseCheckpointSaver` to `build_distroless_loop` must let `compile()` raise loud — do not wrap in a guard.
- The `route_after_resolve_target` `Literal["ok","catalog_miss"]` return type drifts the contract surface. This story's PR amends `tools/contract-surface.snapshot.json` if and only if `edges_distroless.py` introduces a new `Literal` to the snapshot's scope; check the snapshot regen rules in `phase-arch-design.md §Component 10` and confirm with the ADR audit.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/distroless_loop.py` | NEW — factory + topology wiring. |
| `src/codegenie/graph/edges_distroless.py` | NEW — `route_after_resolve_target` `@pure_edge`. |
| `src/codegenie/graph/__init__.py` | UPDATE — export `build_distroless_loop` and `route_after_resolve_target`. |
| `tests/graph/test_build_distroless_loop.py` | Factory tests — compile, interrupt_before, cache, distinct from vuln. |
| `tests/graph/test_distroless_edges.py` | Edge predicate tests. |
| `tests/golden/distroless_loop_topology.json` | NEW — committed canonical topology blob. |
| `tests/golden/test_distroless_loop_topology_golden.py` | Topology golden comparison test. |

## Out of scope

- **CLI surface (`run`/`resume`/`inspect`/`replay`/`render`)** — owned by S5-05.
- **Node bodies** — owned by S5-02 (gather) and S5-03 (execute).
- **`DistrolessLedger` model** — owned by S5-01.
- **The E2E test that invokes the factory end-to-end** — owned by S5-06.
- **`python -O` `@pure_edge` extension test** — owned by S8-02; this story ensures the new edge is decorated, S8-02 verifies the assertion-strip behavior.
- **Property test for `route_after_resolve_target` label invariance** — owned by S6-02 (over the full corpus); this story's unit tests are the seed.
- **Phase 8 supervisor unification** — out of scope by ADR-0011 + ADR-0022 Three Strikes.

## Notes for the implementer

- **Per `phase-arch-design.md §Development view` note: the `route_after_resolve_target` location decision is non-trivial.** Picking `graph/edges_distroless.py` (new file) avoids the ADR-0028 "additive function in existing file" amendment exposure and is the conservative pick. If you put it in `graph/edges.py`, you *must* (a) confirm ADR-P7-001..006 covers the additive-function case, (b) regenerate `tools/contract-surface.snapshot.json` in the same PR, and (c) link the ADR. The new-file path is simpler.
- **The lazy-singleton cache key uses `id(checkpointer)`, not equality.** `InMemorySaver()` from different test fixtures has different `id()` values → cache busts naturally. This is the Phase 6 ADR-0001 decision; reuse verbatim.
- **`interrupt_before=["await_human"]` is set at compile time, not invoke time.** Same as Phase 6 — LangGraph fires the interrupt *before* the node body executes; the CLI exits 12 (`paused_at_human`) via `aget_tuple` inspection.
- **The topology golden is canonicalized JSON.** Use `tests/graph/_canonical.py` from Phase 6 — recursive key sort + `separators=(",", ":")`. Any whitespace drift breaks the diff.
- **`build_distroless_loop` is the integration seam Phase 8's supervisor consumes** (per arch §Component 7 + ADR-P7-001). The signature `(checkpointer, max_attempts, force_rebuild) -> CompiledGraph` matches `build_vuln_loop` exactly — Phase 8 dispatches by `task_type` and calls one or the other. Do not rename arguments; do not reorder.
- **Per `CLAUDE.md` Rule 11: match existing conventions.** Mirror `vuln_loop.py` field-by-field where shapes coincide; do not "improve" the Phase 6 pattern. The deliberate divergence is the one extra node and edge predicate.
- **Per cross-cutting determinism**: no `random`, no `time` imports in `graph/`. Fence-CI is the canary.
- **The five-node `route_after_attempt` conditional edge is reused from Phase 6 verbatim.** Do not redefine it under `edges_distroless.py`; import it from `graph/edges.py` and wire by name. Per the verbatim-import discipline of S5-03.
