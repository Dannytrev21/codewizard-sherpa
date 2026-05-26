# S3-01 — Plugin-local subgraph

**Status:** HARDENED
**Validated:** 2026-05-25 — see [`_validation/S3-01-plugin-local-subgraph.md`](_validation/S3-01-plugin-local-subgraph.md).
**Depends on:** [`S2-02-replay-verification.md`](S2-02-replay-verification.md) — entry-edge calls `hydrate_or_fail(store, workflow_id)` and dispatches on the returned `HydrationResult`; [`S2-01-semantic-checkpoints.md`](S2-01-semantic-checkpoints.md) — nodes emit `TransitionEvent`s at boundary kinds via the injected `CheckpointStore`; [`S1-02-ledger-state-union.md`](S1-02-ledger-state-union.md) — `TransitionEvent`, `_LEGAL_TRANSITIONS`, `_SEMANTIC_BOUNDARY_KINDS`; Phase-3 `SubgraphNode` Protocol + `Advance | ShortCircuit | Escalate` tagged union (`src/codegenie/plugins/subgraph.py`, `src/codegenie/transforms/outcomes.py`) — Phase-6 nodes are *implementers*, never *redefiners*; Phase-3 `Plugin` Protocol (`src/codegenie/plugins/protocols.py`) — the four-member kernel (`manifest`, `build_subgraph`, `adapters`, `transforms`) is frozen and the new plugin implements it.

**Goal:** Land the plugin-local LangGraph subgraph package at `plugins/vulnerability-remediation--node--npm/subgraph/` (the exact path final-design.md item 1 + ADR-0002 pin verbatim) that composes the existing Phase-3 `TransformRegistry` + Phase-4 `FallbackTier` + Phase-5 `GateRunner` + Phase-6 `CheckpointStore` + Phase-6 `ReplayVerifier` ports through **constructor-injected** dependencies; wires the canonical five-node sequence (`ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`) under one `SubgraphNode` Protocol implementation per file (Open/Closed at the file boundary); enforces "edges own control flow" (final-design.md item 4) through AST-walking fences that forbid direct node-to-node imports; routes failure through the four canonical paths (pass → `Completed`; retryable → `match_recipe` replan loop; repeated → `AwaitingHumanReview`; integrity → `FailedUnrecoverable`) via the existing `Advance | ShortCircuit | Escalate` tagged union with NO new arms; lands the **Phase-6 ADR-0004 path-scoped `langgraph` admission** (the closure-wide fence keeps stricter; only the new plugin subgraph package may import `langgraph` — mirrors the Phase-4 `anthropic_adapter.py` precedent); and exposes the resulting subgraph through the existing `Plugin.build_subgraph(registry) -> PluginSubgraph` Protocol member so the future `LangGraphSutAdapter` (S5-01) can `.compile(checkpointer=...)` it without ever importing the builder or naming a node.

This is the first half of `High-level-impl.md §"Step 3 — Plugin-local graph topology"`. The HITL typed-interrupt payload + resume validator (item 5 of final-design.md §"Decisions of record") is **deferred to S4-01**; this story emits a placeholder `Escalate(reason="awaiting_human_review")` at the relevant boundary so S4-01 can land the typed payload additively.

## References

- [final-design.md](../final-design.md) §"Decisions of record" item 1 ("Plugin-local graph topology" — pins the exact path), item 4 ("Edges own control flow. Nodes compute; conditional edges decide. No node directly calls another node." — drives AC-6 + AC-7 + the AST fence), item 5 ("Typed interruption. HITL is a discriminated-union outcome carrying reason, evidence, and resumption contract. 'Paused' is not a boolean side channel." — explicitly deferred to S4-01; this story emits the placeholder), item 6 ("No new trust bypass. Patch application, LLM invocation, and sandbox execution continue through Phase 3/4/5 ports and policies." — drives AC-5 + AC-12 subprocess fence); §"Main workflow" step 2 ("Build or resume `VulnLedger`" — entry-edge `hydrate_or_fail`); §"Main workflow" step 6 (four-routing matrix — AC-10); §"Relationship to Phase 6.5" ("may NOT depend on: the concrete graph builder; node names; checkpoint backend internals; plugin-local file layout" — drives AC-14 `__all__` unchanged).
- [phase-arch-design.md](../phase-arch-design.md) §"Logical view" (SUT → ADAPTER["LangGraphSutAdapter"] → GRAPH["plugin-local vuln subgraph"] → {Planner ports, Transform port, GateRunner, Ledger + checkpoint store} — the topology this story builds), §"Process view" (verify+hydrate → plan → validate → checkpoint sequence), §"Development view" (`plugins/vulnerability-remediation--node--npm/subgraph/` + `tests/unit/workflows/` + `tests/integration/workflows/` — Files-to-touch derives from these), §"Failure modes" rows 2 ("node attempts direct peer call | AST test | CI failure" — AC-6) and 5 ("planner/gate exception | node outcome wrapper | typed failed state, not traceback escape" — AC-11), §"Testing strategy" ("Static tests: graph nodes may import ports, not each other directly").
- [ADRs/0002-plugin-local-subgraph-topology.md](../ADRs/0002-plugin-local-subgraph-topology.md) — §Decision (the verbatim plugin path + reusable-types-in-`src/codegenie/` rule), §Consequences ("Subgraph topology is not inherited" — AC-15 plugin isolation fence).
- [ADRs/0003-checkpointed-ledger-replay-boundary.md](../ADRs/0003-checkpointed-ledger-replay-boundary.md) — entry-edge consumer; the `hydrate_or_fail` gate fires before any node runs.
- **ADRs/0004-langgraph-path-scoped-admission.md** (NEW — landed by this story) — Phase-6 fence amendment: `langgraph` admitted closure-wide BUT structurally restricted to the new plugin subgraph package via the new `tests/fence/test_pyproject_fence_phase6.py` (mirrors the Phase-4 `tests/fence/test_pyproject_fence_phase4.py` precedent that path-scoped `anthropic` to `anthropic_adapter.py`).
- [High-level-impl.md](../High-level-impl.md) §"Step 3 — Plugin-local graph topology" (the three bullets this story implements).
- [S2-02-replay-verification.md](S2-02-replay-verification.md) + [_validation/S2-02-replay-verification.md](_validation/S2-02-replay-verification.md) — the `hydrate_or_fail(store, workflow_id) -> HydrationResult` surface this story's entry-edge consumes; `HydrationResult` is `Hydrated | FailedUnrecoverable` discriminated union.
- [S2-01-semantic-checkpoints.md](S2-01-semantic-checkpoints.md) — `CheckpointStore` Protocol + `_SEMANTIC_BOUNDARY_KINDS` (the six-kind closed boundary set nodes select from); AC-4 boundary-only append policy (the `pydantic.ValidationError` the orchestrator catches on regression).
- [S1-02-ledger-state-union.md](S1-02-ledger-state-union.md) — `TransitionEvent`, `_LEGAL_TRANSITIONS` (the closed `(prior, next)` edges nodes select transitions from), `FailedUnrecoverable.reason: Literal["checkpoint_integrity", "subgraph_aborted", ...]` (the closed reason set this story's nodes populate via `subgraph_aborted` on uncaught exceptions and via `hydrate_or_fail` for `checkpoint_integrity`).
- [S1-01-sut-contract-types.md](S1-01-sut-contract-types.md) — `codegenie.workflows.__all__` allowlist sentinel (AC-14 byte-equal-unchanged).
- Phase-3 `SubgraphNode` Protocol + `SubgraphState` ([`src/codegenie/plugins/subgraph.py`](../../../../src/codegenie/plugins/subgraph.py)) — single-method `async def run(state: SubgraphState) -> NodeTransition`; runtime-checkable; AC-3 + AC-4 enforce conformance per node.
- Phase-3 tagged union ([`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py)) — `Advance | ShortCircuit | Escalate` (with `EscalationReason` 7-member enum per S6-03 Amendment 2026-05-19) — AC-9 confirms the four-routing matrix maps to existing arms with NO new variants needed.
- Phase-3 `Plugin` Protocol ([`src/codegenie/plugins/protocols.py`](../../../../src/codegenie/plugins/protocols.py)) — the four-member kernel `{manifest, build_subgraph, adapters, transforms}` is frozen by Phase-3 ADR-0004; the new plugin implements it without amendment.
- Phase-4 path-scoped fence precedent: [`tests/fence/test_pyproject_fence_phase4.py`](../../../../tests/fence/test_pyproject_fence_phase4.py) — the canonical "closure-wide deny + path-scoped admit" pattern AC-13's new Phase-6 fence mirrors.
- Phase-7 forward dep: roadmap commits to a sibling plugin (`plugins/migration--container--distroless/` or similar). The Phase-6 file layout is reused **by imitation**, not by inheritance — see AC-15 + Notes-for-implementer.

## Acceptance criteria

### Plugin directory + manifest (the byte-exact path final-design.md pins)

- [ ] **AC-1 — Plugin directory shape (byte-exact path).** The directory exists at `plugins/vulnerability-remediation--node--npm/subgraph/` (literal verbatim path from ADR-0002 + final-design.md item 1) and contains:
  - `__init__.py` (empty or with `__all__` re-exports of `build_subgraph` + `SubgraphDeps`)
  - `builder.py` — exposes `def build_subgraph(deps: SubgraphDeps) -> StateGraph` (uncompiled — see AC-2 + DP-5 rationale)
  - `state.py` — re-exports `SubgraphState` from `codegenie.plugins.subgraph` (NO redefinition — Phase-3 S6-03 owns the type)
  - `deps.py` — `SubgraphDeps` frozen Pydantic model carrying the six injected ports
  - `nodes/__init__.py` + one module per node (`nodes/ingest_cve.py`, `nodes/match_recipe.py`, `nodes/apply_recipe.py`, `nodes/stage6_validate.py`, `nodes/write_branch.py`) — Open/Closed at the file boundary
  - `routing.py` — the pure functions LangGraph's `add_conditional_edges` dispatches through (see AC-7)
  - `reducers.py` — pure `Annotated`-reducer functions if any accumulator field is multi-writer (see AC-8); the file MAY be empty today, but must exist so a sixth-accumulator amendment in Phase 7 lands additively
  - `plugin.yaml` — the plugin manifest (Phase-3 ADR-0004 four-member surface)

  Two tests: (i) directory-existence + file-existence parametrized; (ii) `from plugins.vulnerability_remediation__node__npm.subgraph.builder import build_subgraph` succeeds (the Python-importable name has `__` for hyphens — Python rules). **Mutation thinking:** dropping the `plugin.yaml` would leave the subgraph unreachable via `PluginRegistry.resolve()`; the AC-12 plugin-load test catches it from the other side, but the file-existence assertion catches it loud at this step.

- [ ] **AC-2 — `build_subgraph(deps)` is the single entry point; returns an uncompiled `StateGraph`.** The function signature is byte-equal:
  ```python
  def build_subgraph(deps: SubgraphDeps) -> StateGraph[SubgraphState]:
      """Wire the five vuln-remediation nodes through conditional edges.

      Returns the UNCOMPILED StateGraph. The LangGraphSutAdapter (S5-01)
      calls .compile(checkpointer=...) with the per-run checkpointer
      injection (SqliteCheckpointStore / MemorySaver / future Postgres).
      Compiling here would close the checkpointer-injection seam.
      """
  ```
  Tests at `tests/unit/workflows/test_subgraph_builder_shape.py`: (i) `inspect.signature(build_subgraph)` matches the exact `(deps: SubgraphDeps) -> StateGraph[SubgraphState]` signature; (ii) the returned object is `isinstance(g, StateGraph)`, NOT `CompiledStateGraph`; (iii) calling `.compile(checkpointer=MemorySaver())` on the returned graph succeeds. **Mutation thinking:** returning the compiled graph closes the checkpointer-injection seam (S5-01 would have to rebuild from scratch); the type test catches the regression immediately.

- [ ] **AC-3 — `SubgraphDeps` is a frozen Pydantic model with six typed port fields.** Declared in `deps.py`:
  ```python
  class SubgraphDeps(BaseModel):
      model_config = _FROZEN_FORBID
      planner: FallbackTier               # Phase-4 RAG-shaped LLM fallback pipeline
      transforms: TransformRegistry       # Phase-3 (S5-01b TransformRegistry)
      gates: GateRunner                   # Phase-5
      verifier: ReplayVerifier            # Phase-6 S2-02
      checkpoint_store: CheckpointStore   # Phase-6 S2-01 Protocol (not adapter)
      event_log: EventStreamSink          # Phase-3 S6-01 forensic two-stream log
  ```
  Three tests: (i) all six fields are present with the named Protocol types; (ii) `model_config = _FROZEN_FORBID` (single canonical import, not re-declared — AC-12 fence catches drift); (iii) constructing with a concrete adapter (e.g., `SqliteCheckpointStore`) succeeds because the Protocol is structurally satisfied. **Mutation thinking:** replacing `checkpoint_store: CheckpointStore` with `checkpoint_store: SqliteCheckpointStore` would couple the subgraph to a concrete substrate; the type assertion catches this and the Phase-9 Postgres swap (one constructor change) survives.

### Node implementations (one per module — Open/Closed at the file boundary)

- [ ] **AC-4 — Every node implements the existing `SubgraphNode` Protocol (no redefinition).** Each of the five node modules under `subgraph/nodes/` exposes exactly one class (`IngestCveNode`, `MatchRecipeNode`, `ApplyRecipeNode`, `Stage6ValidateNode`, `WriteBranchNode`); each class:
  - implements `async def run(self, state: SubgraphState) -> NodeTransition` byte-equal to the Phase-3 `SubgraphNode` Protocol signature (`src/codegenie/plugins/subgraph.py`)
  - accepts ports via `__init__` constructor injection (NOT module-level globals; NOT `registry.get(...)` inside `run()`)
  - declares `__slots__` enumerating only the injected port references

  A parametrized test at `tests/unit/workflows/test_subgraph_node_conformance.py`:
  ```python
  @pytest.mark.parametrize("node_cls", [IngestCveNode, MatchRecipeNode, ApplyRecipeNode, Stage6ValidateNode, WriteBranchNode])
  def test_node_satisfies_protocol(node_cls):
      instance = node_cls(**_minimal_port_fakes())
      assert isinstance(instance, SubgraphNode)
      assert inspect.iscoroutinefunction(instance.run)  # PEP 544 closes the runtime gap subgraph.py docstring names
      sig = inspect.signature(instance.run)
      assert list(sig.parameters) == ["state"]
      assert sig.return_annotation is NodeTransition
  ```
  **Mutation thinking:** a `def ingest_cve(state)` lambda or a `BaseModel` with no `run` method would satisfy "graph package lives under the plugin" but fail `isinstance(instance, SubgraphNode)` — caught here.

- [ ] **AC-5 — `apply_recipe` routes through `deps.transforms`; `match_recipe` routes through `deps.planner`; `stage6_validate` routes through `deps.gates`; `write_branch` routes through `deps.transforms` (no new trust bypass).** Per-node tests at `tests/unit/workflows/test_subgraph_node_port_routing.py`:
  - `test_apply_recipe_calls_transform_registry_with_named_kwargs` — `Mock(spec=TransformRegistry)`; assert `mock.apply.assert_called_once_with(plan=..., ctx=...)` with kwargs matching the canonical signature; assert the node's `NodeTransition` wraps the engine's `RecipeOutcome`.
  - `test_match_recipe_calls_fallback_planner` — same pattern with `Mock(spec=FallbackTier)`.
  - `test_stage6_validate_calls_gate_runner` — same pattern with `Mock(spec=GateRunner)`.
  - `test_write_branch_calls_transform_registry_for_commit` — same.

  **Mutation thinking:** a node that does its own `subprocess.run("npm install")` or its own `anthropic.messages.create(...)` would bypass Phase 3/4/5 trust gates — final-design.md item 6 explicitly forbids this. The AC-12 AST fence catches the import side; this AC catches the call side.

### Edges own control flow (final-design.md item 4 + arch §Failure-modes row 2)

- [ ] **AC-6 — AST fence: no direct node-to-node imports.** A new fence at `tests/fence/test_subgraph_no_peer_calls.py`:
  ```python
  _NODE_MODULES: Final[frozenset[str]] = frozenset({
      "ingest_cve", "match_recipe", "apply_recipe",
      "stage6_validate", "write_branch",
  })

  @pytest.mark.parametrize("node_module", sorted(_NODE_MODULES))
  def test_node_module_does_not_import_sibling(node_module: str) -> None:
      """Edges own control flow (final-design.md item 4). No node-to-node calls."""
      src = (NODES_DIR / f"{node_module}.py").read_text()
      tree = ast.parse(src)
      for stmt in ast.walk(tree):
          if isinstance(stmt, ast.ImportFrom):
              target = stmt.module or ""
              for sibling in _NODE_MODULES - {node_module}:
                  assert sibling not in target, (
                      f"{node_module}.py imports sibling node {sibling} — "
                      "edges own control flow (final-design.md item 4); "
                      "route via conditional edges in builder.py / routing.py."
                  )
  ```
  Plus a sibling test that walks each node module for `Call` AST nodes whose `func` resolves to another node's `run` method by name. **Mutation thinking:** an executor "helpfully" merges `apply_recipe → stage6_validate` into one combined node that calls `stage6_validate.run(state)` directly — the fence catches the import + the call.

- [ ] **AC-7 — Conditional edges are pure functions in `routing.py`.** Each `add_conditional_edges` call in `builder.py` takes a pure decision function from `routing.py` (e.g., `route_after_apply(state: SubgraphState) -> Literal["stage6_validate", "match_recipe", END]`). The functions are pure (no I/O, no clock, no ports — they take only `SubgraphState` and return a routing key). A test at `tests/unit/workflows/test_subgraph_routing_purity.py`:
  - asserts each routing function in `routing.py` returns the same key for the same input across two calls
  - parametrizes inputs covering the four routing paths and pins the expected key
  - asserts an AST fence: `routing.py` does NOT import `subprocess`, `time`, `random`, `uuid`, `os.environ`, `httpx`, `requests` (purity discipline mirroring `_chain.py`)

  **Mutation thinking:** an executor pushes the routing decision into a node (`return Advance(state, next_node="stage6_validate")`) — final-design.md item 4 explicitly forbids this; the AC-6 fence catches the node-side regression; this AC catches the routing-side regression.

- [ ] **AC-8 — `Annotated`-reducer hygiene for `SubgraphState` accumulators.** Any multi-writer accumulator field on `SubgraphState` (existing fields are predominantly single-writer per S6-03; this AC defends against future drift) uses `Annotated[T, reducer_fn]` with the reducer declared as a pure function in `subgraph/reducers.py`. A test asserts that every `Annotated` reducer in `SubgraphState` resolves to an importable pure function (no lambdas — lambdas defeat the AST purity fence). **Mutation thinking:** an `Annotated[list[str], lambda a, b: a + b]` inline would slip past the purity fence; the test catches the lambda. NOTE: today there may be ZERO accumulators requiring reducers; in that case, the test parametrizes over an empty list (trivially passes) AND the `reducers.py` file is empty — the file's existence is the Open/Closed substrate for future amendment.

### Routing matrix (final-design.md §"Main workflow" step 6)

- [ ] **AC-9 — Four-routing matrix maps to existing `NodeTransition` arms (no new variants).** A unit test at `tests/unit/workflows/test_subgraph_routing_matrix.py` parametrized over four cases:
  | At node | Returned `NodeTransition` | Expected terminus |
  |---|---|---|
  | gate-pass on `stage6_validate` | `Advance(state=..., next_node="write_branch")` | `Completed` after `write_branch` |
  | retryable failure on `stage6_validate` | `Advance(state=..., next_node="match_recipe")` (with `retry_count++`) | re-enters `match_recipe`; capped at `MAX_RETRIES=3` |
  | repeated failure (`retry_count >= 3`) on `stage6_validate` | `Escalate(reason="awaiting_human_review")` | `AwaitingHumanReview` boundary write + clean exit |
  | integrity failure from `hydrate_or_fail` | (entry edge short-circuits BEFORE `ingest_cve.run`) | `FailedUnrecoverable(reason="checkpoint_integrity")` |
  Each case asserts: (a) the terminal state via `await graph.ainvoke(...)`; (b) the recorded `TransitionEvent` sequence via the in-memory `CheckpointStore` spy; (c) the routing function from `routing.py` returned the expected key for the input state. **Mutation thinking:** a graph that always routes to `Completed` even on `Escalate` would pass single-node tests; the parametrized matrix forces all four arms to be exercised; the explicit `case 4` (integrity failure short-circuit) forces the entry-edge wiring to be correct.

- [ ] **AC-10 — Bounded retry loop (no infinite cycle).** A test at `tests/unit/workflows/test_subgraph_retry_bound.py` wires a node that always returns `Advance(next_node="match_recipe")` with no retry-count increment; asserts that `asyncio.wait_for(graph.ainvoke(state), timeout=2.0)` raises `TimeoutError` and the graph hasn't completed N more than `MAX_RETRIES` iterations (verified via the spy-`CheckpointStore` event count). A `MAX_RETRIES: Final[int]` constant declared in `routing.py`; the routing function `route_after_validate` checks `state.retry_count >= MAX_RETRIES` and emits `Escalate(reason="awaiting_human_review")`. **Mutation thinking:** removing the cap creates an infinite retry loop the test catches via the wall-clock bound + the event-count assertion.

### Entry-edge integration with S2-02 `hydrate_or_fail` (the load-bearing cross-story wiring)

- [ ] **AC-11 — Entry edge calls `hydrate_or_fail` exactly once before any node runs.** The graph's `entry_point` is wired to a special pseudo-node `_replay_gate` whose `run()` body is `return await _entry_gate(state, deps.verifier, deps.checkpoint_store)`. The pure helper `_entry_gate(state, verifier, store) -> NodeTransition` calls `verifier.hydrate_or_fail(store, state.workflow_id)` and:
  - On `Hydrated`: returns `Advance(state=state.with_hydrated_events(hydrated.events), next_node=_node_for_kind(hydrated.latest_state_kind))`
  - On `FailedUnrecoverable`: returns `ShortCircuit(terminal=hydrated)` carrying the `FailedUnrecoverable` instance into the graph's `END` arm

  Two tests at `tests/integration/workflows/test_subgraph_entry_hydration.py`:
  1. Tampered chain (pre-populated via raw-SQLite per S2-02 AC-9 setup) → `hydrate_or_fail` returns `FailedUnrecoverable(reason="checkpoint_integrity")` → graph short-circuits → `ingest_cve.run` is **never called** (spy via `Mock(spec=IngestCveNode)`); the final state is `FailedUnrecoverable`.
  2. Clean chain → `hydrate_or_fail` returns `Hydrated(events=(), latest_state_kind="needs_plan")` → graph dispatches to `ingest_cve`.

  **Mutation thinking:** skipping the entry edge would silently resume a tampered chain — the most catastrophic failure mode the entire phase-6 design defends against. The spy-`Mock(spec=IngestCveNode)` is the structural defense — it can ONLY be `assert_not_called()` if the entry edge correctly short-circuits.

### Node exception wrapping (arch §Failure-modes row 5)

- [ ] **AC-12 — Uncaught node exceptions are wrapped into `Escalate(reason="subgraph_aborted")`, never a traceback escape.** A decorator `_wrap_node_exceptions` (in `subgraph/_wrapping.py`) wraps each node's `run()` body in a typed try/except: any uncaught `Exception` (excluding `KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`) is converted to `Escalate(reason="subgraph_aborted", error=RemediationError(error_id="subgraph.<node_name>.uncaught_exception", message=str(exc)))`. A test at `tests/integration/workflows/test_subgraph_node_exception_wrapping.py` injects a `Mock(spec=TransformRegistry)` whose `apply.side_effect = RuntimeError("planner exploded")`; runs the graph; asserts the terminal state is `FailedUnrecoverable(reason="subgraph_aborted", error.error_id="subgraph.apply_recipe.uncaught_exception")` AND `graph.ainvoke()` does NOT raise.

  An AST fence at `tests/fence/test_subgraph_node_exception_wrapping.py` walks each node module and asserts `run()` is decorated with `@_wrap_node_exceptions` OR contains a `try/except` clause whose `except` clause converts to a typed `NodeTransition` (no bare `except:`, no `except Exception:` without re-raise or typed return). **Mutation thinking:** removing the wrapper lets a `KeyError` escape as an unhandled traceback — Phase-6.5 bench harness sees a non-typed exception and silently fails the run. The fence catches it.

### Trust-bypass closure (final-design.md item 6 + CLAUDE.md "Subprocess discipline")

- [ ] **AC-13 — AST fence: no `subprocess`, `os.system`, `os.popen`, `anthropic` SDK in the subgraph package.** A new fence at `tests/fence/test_subgraph_trust_closure.py` walks every module under `plugins/vulnerability-remediation--node--npm/subgraph/` and asserts no imports of:
  - `subprocess`, `os.system`, `os.popen`, `os.exec*`, `pty.*`
  - `anthropic`, `openai`, `langchain`, `transformers`, `sentence_transformers`, `torch` (the closure-wide deny set — `langgraph` is the SOLE exception per AC-14)
  - any module under `src/codegenie/exec/` other than via the injected `deps.gates` / `deps.planner` / `deps.transforms` ports
  - `re.compile`, `re.search`, `re.fullmatch` (the canonical-sanitizer-only discipline — see S2-01 AC-12 precedent)

  **Mutation thinking:** a node that "speeds up patch application" by calling `subprocess.run(["npm", "install"])` bypasses Phase-5 sandbox gates (final-design.md item 6 verbatim violation); the fence catches it at PR time.

### `langgraph` path-scoped admission (new Phase-6 ADR-0004)

- [ ] **AC-14 — Phase-6 ADR-0004 + new `tests/fence/test_pyproject_fence_phase6.py` admit `langgraph` ONLY in the new plugin subgraph package.** This story lands:
  1. A new ADR file `docs/phases/06-sherpa-vuln-loop/ADRs/0004-langgraph-path-scoped-admission.md` in Nygard format documenting the closure-wide-deny + path-scoped-admit decision (mirrors Phase-4 ADR-0003 / `anthropic_adapter.py` precedent).
  2. A new fence test `tests/fence/test_pyproject_fence_phase6.py` mirroring `tests/fence/test_pyproject_fence_phase4.py` (the canonical pattern): (a) asserts `langgraph` is importable; (b) AST-walks every `.py` under `src/codegenie/` and asserts NONE import `langgraph`; (c) AST-walks every `.py` under `plugins/` and asserts only files matching the glob `plugins/vulnerability-remediation--node--npm/subgraph/**/*.py` may import `langgraph`; (d) asserts `pyproject.toml` retains `langgraph` in the closure-wide `forbidden_modules` list (the closure-scope deny is STRICTER, not relaxed — only the path-scope admit is widened).
  3. The pyproject comment at the existing slot ("Phase 6's expected `langgraph` admission is anticipated to path-scope likewise — see ADR-0003 §Consequences") is rewritten to reference ADR-0004 instead (the prior reference was a forward-reference placeholder; ADR-0003 §Consequences does NOT contain the admission consequence — only the chain-head verification consequence).
  4. `pyproject.toml` declares `langgraph = "..."` in `[project.dependencies]` (path-scoped — fence test enforces the boundary).

  Tests: the fence's four sub-assertions PLUS a positive test that `from plugins.vulnerability_remediation__node__npm.subgraph.builder import build_subgraph` succeeds and triggers the `langgraph` import. **Mutation thinking:** widening the admission to all `plugins/**` would let a future Phase-7 plugin silently import LangGraph; the path-scoped glob catches it. Narrowing the closure-wide deny would let `src/codegenie/workflows/replay.py` import LangGraph and couple the substrate to the framework; the closure-deny assertion catches it.

### `__all__` discipline + cross-plugin isolation + closeout gates

- [ ] **AC-15 — `codegenie.workflows.__all__` is byte-equal-unchanged AND a cross-plugin isolation fence lands.** Two parts:
  1. The S1-01 / S1-02 / S2-01 / S2-02 14-name allowlist sentinel test (`tests/fence/test_workflows_public_surface.py`) continues to pass byte-equal — this story adds zero symbols to `codegenie.workflows.__all__` (the subgraph lives under `plugins/`, not `src/codegenie/workflows/`; Phase-6.5 may NOT depend on it per final-design.md §"Relationship to Phase 6.5").
  2. A new fence at `tests/fence/test_plugin_isolation.py` AST-walks every `.py` under `plugins/` and asserts no module under `plugins/vulnerability-remediation--node--npm/` imports from `plugins/<any-other-plugin>/`. (The fence is general — it walks all plugin pairs — so Phase-7's plugin inherits the protection additively.)

  **Mutation thinking:** an executor accidentally re-exports `SubgraphDeps` through `codegenie.workflows.__init__` for "convenience" — the byte-equality test catches it loud with the `final-design.md §"Relationship to Phase 6.5"` directive. A future Phase-7 plugin imports a Phase-6 node "for reuse" — the isolation fence catches it; ADR-0002 §Consequences "Existing plugin behavior remains isolated from future task classes" is enforced structurally.

- [ ] **AC-16 — `mypy --strict` clean + contract snapshot extension.** Two closeout gates:
  1. `make typecheck` passes over the new `plugins/vulnerability-remediation--node--npm/` directory (add the path to `[tool.mypy] files` if not already covered). No `Any`, no untyped `dict`, no `# type: ignore` without an upstream-issue comment.
  2. `tests/integration/test_phase6_sut_contract_snapshot.py` extended with: (a) `inspect.signature(build_subgraph)` byte-snapshot; (b) `SubgraphDeps` `model_json_schema(by_alias=True)`; (c) the sorted list of node class names (`["IngestCveNode", "MatchRecipeNode", "ApplyRecipeNode", "Stage6ValidateNode", "WriteBranchNode"]`); (d) the closed `_NODE_ERROR_IDS` frozenset values (per AC-12). The meta-test classifier (`_meta.py`) gets one additive synthetic delta (new node class) + one breaking synthetic delta (removed node class) so the classifier is exercised on subgraph-shaped deltas, not only ledger / verifier shapes.

  Regenerate the golden via `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` and commit.

## Files to touch

- `plugins/vulnerability-remediation--node--npm/subgraph/__init__.py` (new — empty or `__all__` re-exports)
- `plugins/vulnerability-remediation--node--npm/subgraph/builder.py` (new — `build_subgraph(deps) -> StateGraph`)
- `plugins/vulnerability-remediation--node--npm/subgraph/deps.py` (new — `SubgraphDeps` frozen Pydantic model)
- `plugins/vulnerability-remediation--node--npm/subgraph/state.py` (new — re-export of `codegenie.plugins.subgraph.SubgraphState`)
- `plugins/vulnerability-remediation--node--npm/subgraph/routing.py` (new — pure routing functions + `MAX_RETRIES: Final[int]`)
- `plugins/vulnerability-remediation--node--npm/subgraph/reducers.py` (new — empty placeholder file; Open/Closed substrate for future `Annotated` reducers per AC-8)
- `plugins/vulnerability-remediation--node--npm/subgraph/_wrapping.py` (new — `_wrap_node_exceptions` decorator per AC-12)
- `plugins/vulnerability-remediation--node--npm/subgraph/nodes/__init__.py` (new)
- `plugins/vulnerability-remediation--node--npm/subgraph/nodes/{ingest_cve,match_recipe,apply_recipe,stage6_validate,write_branch}.py` (new — one class per file)
- `plugins/vulnerability-remediation--node--npm/plugin.yaml` (new — plugin manifest per Phase-3 ADR-0004 four-member surface; declares scope + entry-point `subgraph.builder:build_subgraph`)
- `plugins/vulnerability-remediation--node--npm/__init__.py` (new — the `Plugin` Protocol implementation that exposes `manifest`, `build_subgraph`, `adapters`, `transforms`)
- `docs/phases/06-sherpa-vuln-loop/ADRs/0004-langgraph-path-scoped-admission.md` (new — Nygard format)
- `pyproject.toml` (modify — add `langgraph = "..."` to `[project.dependencies]`; update the existing slot comment to reference ADR-0004 instead of the placeholder ADR-0003 §Consequences anchor)
- `tests/fence/test_pyproject_fence_phase6.py` (new — mirrors `test_pyproject_fence_phase4.py`)
- `tests/fence/test_subgraph_no_peer_calls.py` (new — AC-6 AST fence)
- `tests/fence/test_subgraph_node_exception_wrapping.py` (new — AC-12 AST fence)
- `tests/fence/test_subgraph_trust_closure.py` (new — AC-13 AST fence)
- `tests/fence/test_plugin_isolation.py` (new — AC-15 cross-plugin import fence; walks all plugin pairs)
- `tests/unit/workflows/test_subgraph_builder_shape.py` (new — AC-2)
- `tests/unit/workflows/test_subgraph_deps_shape.py` (new — AC-3)
- `tests/unit/workflows/test_subgraph_node_conformance.py` (new — AC-4)
- `tests/unit/workflows/test_subgraph_node_port_routing.py` (new — AC-5)
- `tests/unit/workflows/test_subgraph_routing_purity.py` (new — AC-7)
- `tests/unit/workflows/test_subgraph_routing_matrix.py` (new — AC-9)
- `tests/unit/workflows/test_subgraph_retry_bound.py` (new — AC-10)
- `tests/integration/workflows/test_subgraph_entry_hydration.py` (new — AC-11 cross-story)
- `tests/integration/workflows/test_subgraph_node_exception_wrapping.py` (new — AC-12 integration)
- `tests/integration/test_phase6_sut_contract_snapshot.py` (modify — extend per AC-16)
- `tests/integration/test_phase6_sut_contract_snapshot_meta.py` (modify — add subgraph-shaped synthetic deltas)
- `tests/golden/phase6-contract/snapshot.json` (modify — regenerate)
- `pyproject.toml` `[tool.mypy] files` (modify — add `plugins/vulnerability-remediation--node--npm/` if not already covered)

## TDD plan

**Red.** Land in this order — every step writes a failing test first, then verifies the failure message is meaningful before writing production code:

1. AC-1 directory + file existence (fails: directory doesn't exist).
2. AC-14 Phase-6 ADR-0004 + new fence (fails: ADR doesn't exist, fence test doesn't exist; lands the `langgraph` admission BEFORE any module imports it — otherwise the existing closure-wide fence breaks CI).
3. AC-3 `SubgraphDeps` frozen-forbid shape (fails: module doesn't exist).
4. AC-2 `build_subgraph` signature + uncompiled-`StateGraph`-return test (fails: function doesn't exist; the type assertion drives the return-uncompiled discipline).
5. AC-4 per-node Protocol conformance test (fails: node classes don't exist).
6. AC-5 per-node port-routing tests (fails: nodes don't call their ports).
7. AC-12 node exception wrapping integration test + AST fence (fails: wrapper doesn't exist).
8. AC-6 AST no-peer-imports fence (fails initially trivially passing; starts biting once the executor adds nodes — keep the test active throughout).
9. AC-7 routing purity + per-key assertion test (fails: routing functions don't exist).
10. AC-9 four-routing matrix test (fails: routing doesn't dispatch correctly).
11. AC-10 bounded retry test (fails: no `MAX_RETRIES` cap).
12. AC-11 entry-hydration integration test (fails: entry edge doesn't call `hydrate_or_fail`).
13. AC-13 trust-closure AST fence (fails initially trivially passing; bites if a node imports `subprocess`).
14. AC-15 `__all__` byte-equality + cross-plugin isolation fence (fails: isolation fence doesn't exist).
15. AC-8 `Annotated`-reducer hygiene (trivially passes if no multi-writer fields today; the file's existence is the substrate).
16. AC-16 `mypy --strict` + contract snapshot extension (the final gates; regenerate golden under `PHASE6_CONTRACT_GOLDEN_REWRITE=1`).

**Green.** Implement the minimum that makes all red tests pass:

- Land ADR-0004 + the Phase-6 path-scoped fence FIRST (Red step 2) so the `langgraph` import in `builder.py` doesn't break the closure-wide fence.
- Add `SubgraphDeps` (`_FROZEN_FORBID` + the six Protocol-typed fields).
- Add the five node classes, each with `__slots__`, constructor-injected ports, and the `@_wrap_node_exceptions`-decorated `async def run(state)`.
- Add `routing.py` with the four pure decision functions + `MAX_RETRIES = 3`.
- Add `_wrap_node_exceptions` decorator in `_wrapping.py`.
- Add the `Plugin` Protocol implementation at `plugins/vulnerability-remediation--node--npm/__init__.py` exposing the four kernel members; `plugin.yaml` declares the scope + entry-point.
- Add `builder.py` wiring: entry edge → `_entry_gate(state, deps.verifier, deps.checkpoint_store)` → conditional dispatch to the right node OR short-circuit to `END` with the `FailedUnrecoverable` carried; node-to-node edges via `add_conditional_edges` using the pure routing functions.
- Regenerate the contract-snapshot golden.

**Refactor.** Cleanup only — no new behaviour:

- Confirm `_FROZEN_FORBID` is imported once at the top of `deps.py` (the existing AC-12 fence from S1-02 catches drift).
- Confirm `__slots__` enumerates every instance attribute on each node class.
- Confirm `MAX_RETRIES` and any other module-level constants are `Final`.
- Confirm `routing.py` has no I/O / clock imports (the AC-7 purity assertion enforces).

**Anti-refactor (Rule 2 + Open/Closed + composition-over-inheritance).** Do NOT introduce any of the following in this story:

1. **A `BaseNode` ABC or `NodeMixin`.** Five nodes share infrastructure (ports, logger) NOT behavior; rule-of-three for behavior-sharing is unmet. Phase-3 `SubgraphNode` Protocol IS the contract. Composition via constructor injection is the substrate.
2. **A `SubgraphBuilder` class.** One graph today; rule-of-two for builder variants unmet. The free function `build_subgraph(deps)` is the Plugin Protocol's existing factory boundary.
3. **A `SubgraphRegistry` or `@register_subgraph` decorator.** The `PluginRegistry` IS the registry; Phase-7's distroless plugin ships its own `build_subgraph` returning a different topology. Rule-of-two unmet for subgraph-level open dispatch.
4. **A `BaseEdge` / `EdgeStrategy` Strategy abstraction over routing functions.** Four routing functions today; each is a 3-line pure function; Rule 2 explicit ("three similar lines is better than premature abstraction"). LangGraph's `add_conditional_edges` IS the strategy substrate.
5. **A data-driven topology dict + translator.** LangGraph's imperative builder calls (`add_node`, `add_conditional_edges`) are idiomatic; a data-driven `topology = {...}` + translator would diverge from upstream and earn no testability gains over `inspect`-introspecting the built graph.
6. **A new `NodeTransition` arm for `FailedUnrecoverable`.** The existing `ShortCircuit(terminal=FailedUnrecoverable(...))` carries the terminal state through the `END` arm. Adding a fourth arm would require an additive amendment to `codegenie.transforms.outcomes` AND every existing match-exhaustiveness consumer — pay only if a Phase 7+ requirement materializes.
7. **A `Services` god-object dependency container.** `SubgraphDeps` is a frozen Pydantic model with exactly six explicit fields; nodes accept the SUBSET they need via their `__init__`. A `Services` god-object collapses the constructor-injection discipline back into service-locator (Phase-3 / 5 / 6 all reject this).
8. **An `EscalationReason` enum extension for "checkpoint_integrity_violation".** S2-02 owns the integrity-failure decision and maps it to `FailedUnrecoverable(reason="checkpoint_integrity")` at the `hydrate_or_fail` boundary — the subgraph's entry edge carries that result through `ShortCircuit`, never re-deriving the reason as an `EscalationReason` member.
9. **A `subgraph/nodes.py` single-file collection.** Per-node-file is the Open/Closed substrate (DP-2); adding a sixth node lands as one new sibling file plus one import in `builder.py`, zero edits to existing files.

## Out of scope

- The HITL typed-interrupt payload + resume validator — Phase-6 S4-01 owns this. This story emits the placeholder `Escalate(reason="awaiting_human_review")` at the relevant boundary; S4-01 lands the typed payload, the resume validator, and the stale-token rejection.
- The `LocalVulnRemediationSut` adapter that compiles the graph with a checkpointer + threads the `HydrationResult` — Phase-6 S5-01.
- The end-to-end `LocalVulnRemediationSut → graph → hydrate_or_fail → resume` integration golden — Phase-6 S5-01 + S6-01.
- The workflow-scope replay-determinism property (`tests/property/test_workflow_replay_determinism.py`) — Phase-6 S6-01 closeout owns this; it requires the fully-wired graph + adapter + checkpointer to fire. This story provides the substrate; S6-01 wires the property.
- The Postgres adapter for `CheckpointStore` — Phase-9 S5-01; the subgraph dispatches through the Protocol and inherits the adapter additively.
- A second concrete plugin (`plugins/migration--container--distroless/` or similar) — Phase-7 owns this. Phase-7 reuses the Phase-6 file layout by **imitation**, never by inheritance — see Notes-for-implementer.
- The richer TCCM `provides` namespace on the plugin manifest — minimal manifest lands here for `Plugin.build_subgraph` reachability; richer TCCM entries (per-CVE handler classes, per-ecosystem recipe lists) land in Phase-3 S7-01 (already shipped) and per-task-class amendments later.
- A `BaseNode` ABC / `SubgraphBuilder` class / `SubgraphRegistry` / `EdgeStrategy` / data-driven topology / `Services` god-object — see Anti-refactor #1–9.

## Notes for the implementer

- **Why ADR-0004 lands FIRST (Red step 2).** The closure-wide `langgraph` fence is already enforced; the moment `builder.py` imports `langgraph`, CI breaks. Landing the ADR + the new `tests/fence/test_pyproject_fence_phase6.py` before any production import means the path-scoped admission is the recorded decision, not a silent reaction to a broken build. The Phase-4 anthropic precedent is the canonical reference — `tests/fence/test_pyproject_fence_phase4.py` is the file to mirror.

- **Why `build_subgraph` returns the UNCOMPILED `StateGraph`.** LangGraph's `StateGraph.compile(checkpointer=...)` is the seam where the SUT adapter (S5-01) injects the per-run checkpointer (`SqliteCheckpointStore` today; `MemorySaver` for tests; Phase-9 Postgres saver additively). Compiling inside `build_subgraph` closes the seam — the adapter would have to rebuild from scratch. This is the same dependency-inversion discipline `SubgraphDeps` enforces for the other six ports.

- **Why per-node-file (Open/Closed at the file boundary).** Five nodes today, but the design substrate must accommodate a sixth without editing the existing five. Mirrors `vuln_*` file naming (S1-02 / S2-01 / S2-02 / new `vuln_replay.py`) and `transforms/engines/{npm_lockfile,openrewrite}.py` (Phase-3 day-1 two-implementations precedent). Adding `nodes/verify_sbom.py` later is one new file + one import in `builder.py`, zero edits to the existing five. A collapse to `subgraph/nodes.py` makes every node addition a kernel edit.

- **Why constructor-injection (rule-of-three from Phase-3 / 5 / 6).** `RecipeEngine(TransformRegistry)`, `GateRunner(SignalCollectorRegistry)`, `ReplayVerifier(CheckpointStore)` — three precedents, rule earned. Service-locator (`registry.get(...)` inside `run()`) defeats the substitutability the Protocol bought; a `Services` god-object reverses the DI direction by hiding which ports a node actually consumes. Each node's `__init__` declares the EXPLICIT subset of `SubgraphDeps` fields it needs.

- **Why `_wrap_node_exceptions` instead of try/except inside each `run()`.** Three reasons: (i) the wrapper is a single canonical-declaration site for the exception → `Escalate` mapping (the per-node `error_id` namespace `subgraph.<node_name>.uncaught_exception` is generated from the decorator's `__qualname__` introspection); (ii) the AST fence (AC-12) walks for the decorator presence rather than asserting against the body structure of every `run()` — simpler and more mutation-resistant; (iii) future amendments (e.g., emitting a typed event before re-raising) land in one file. Mirrors the Phase-3 `_wrap_recipe_outcome` precedent.

- **Why the entry edge is a pseudo-node `_replay_gate`, not an `add_edge(START, "ingest_cve")` directly.** Two reasons: (i) the `hydrate_or_fail` call is impure (it reads the substrate) and needs to live inside a node-like async context so LangGraph's checkpointer can record its `TransitionEvent` (the genesis transition); (ii) it lets the AC-11 spy-Mock assertion be structural ("`ingest_cve.run` was never called when `hydrate_or_fail` returned `FailedUnrecoverable`") rather than relying on the absence of a side-effect downstream. The pseudo-node has no business logic — only the gate call + the dispatch.

- **Why the four routing paths map to existing `NodeTransition` arms with NO amendments.** The S6-03 Amendment widened `EscalationReason` to seven members; `awaiting_human_review` is one of them. `FailedUnrecoverable` rides through `ShortCircuit(terminal=...)` because it's a terminal state, not an escalation. The three arms (`Advance | ShortCircuit | Escalate`) cover the four paths cleanly: pass = `Advance(next_node="write_branch")`; retry = `Advance(next_node="match_recipe")` with retry_count++; escalate = `Escalate(reason="awaiting_human_review")`; fail = `ShortCircuit(terminal=FailedUnrecoverable(...))`. If a future requirement needs a fourth arm, that's an additive amendment to `codegenie.transforms.outcomes` (already done once via S6-03 Amendment) — but not for this story.

- **Why a sole-site fence for `FailedUnrecoverable(reason="checkpoint_integrity")` lives in S2-02's verifier, NOT in this story.** S2-02 ships `hydrate_or_fail` as the SOLE construction site of that exact reason slug; this story's entry edge consumes the result. A second sole-site fence here would be redundant. The `subgraph_aborted` reason IS constructed in this story (by `_wrap_node_exceptions`) — and that IS unique to this story. The AC-15 isolation fence + the AC-16 contract-snapshot together ensure the namespace is preserved.

- **Why `tests/fence/test_plugin_isolation.py` walks ALL plugin pairs (not just Phase-6's).** Phase-7 will land its own plugin; the isolation fence must catch cross-imports between Phase-6 and Phase-7 plugins automatically (and Phase-15+ when the third plugin lands). Writing the fence as "Phase-6 plugin doesn't import Phase-X" would force a Phase-7 amendment. Walking all plugin-pairs makes it additive. This mirrors how `tests/fence/test_pyproject_fence_phase4.py` is single-purpose (Phase-4 anthropic admission) while `tests/fence/test_plugin_isolation.py` is general (covers all plugin pairs).

- **Phase-7 forward dep — reuse by imitation, not inheritance.** Phase-7's distroless-migration plugin (`plugins/migration--container--distroless/` or similar) ships its OWN graph topology, its OWN node modules, its OWN `SubgraphDeps` shape (likely with different ports: a `DockerfileParser`, an `ImageRegistryClient`, etc.). The shared substrate is: the `Plugin` Protocol (four-member kernel), the `SubgraphNode` Protocol, the `NodeTransition` tagged union, the `CheckpointStore` Protocol, the file-layout convention (`plugins/<slug>/subgraph/{builder,deps,state,routing,reducers,nodes/}.py`). Do NOT extract a `BaseSubgraph` or `SubgraphBuilderMixin` "for reuse" — the rule-of-three threshold for substrate abstraction isn't met until Phase-15+ (third task class). The Open/Closed substrate for plugin extension is the directory tree + the Plugin Protocol; both are already in place.

- **Phase-9 forward dep — the subgraph is checkpointer-agnostic.** The Phase-9 Postgres `CheckpointStore` adapter lands additively under the same Protocol; `build_subgraph(deps)` is unchanged because `deps.checkpoint_store: CheckpointStore` is structural. The `LangGraphSutAdapter` (S5-01) is the file that gets a one-line constructor change (`SqliteCheckpointStore(...)` → `PostgresCheckpointStore(...)`). This story freezes the substrate that makes Phase-9 a true one-line migration.

- **Why the workflow-replay-determinism property is deferred to S6-01.** The property fires only against the fully-wired graph PLUS the adapter PLUS the checkpointer; S3-01 only ships the graph builder. S6-01 closeout owns the property (it lands after S5-01 ships the adapter). This story provides the substrate the property exercises; the property itself depends on S5-01 to compile the graph with a real checkpointer.
