# S3-02 — Transition table tests

**Status:** HARDENED
**Validated:** 2026-05-26 — see [`_validation/S3-02-transition-table-tests.md`](_validation/S3-02-transition-table-tests.md).
**Depends on:** [`S3-01-plugin-local-subgraph.md`](S3-01-plugin-local-subgraph.md) — consumes the `subgraph/routing.py` pure routing functions, the `subgraph/nodes/` per-node modules, `MAX_RETRIES`, the five-node sequence, and the `_NODE_MODULES` frozenset; [`S1-02-ledger-state-union.md`](S1-02-ledger-state-union.md) — consumes `_LEGAL_TRANSITIONS`, `LedgerStateKind`, the seven-variant `VulnLedgerState` sum type, and the operationally-terminal partition `{completed, failed_unrecoverable}`; [`S2-01-semantic-checkpoints.md`](S2-01-semantic-checkpoints.md) — consumes `_SEMANTIC_BOUNDARY_KINDS`. **This story does NOT introduce a new ledger transition table or a new routing implementation.** S3-01 ships the routing layer; S1-02 ships the ledger transition table; this story is the *defensive coverage layer* that pins both to the design with mutation-resistant, exhaustive, declarative tests.

**Goal:** Land the **defensive coverage layer** for Phase-6 transition routing — three things, all *additive over S3-01 + S1-02*: (1) a **declarative routing-decision table** `_ROUTING_TABLE: Final[Mapping[SourceNode, frozenset[RoutingDecision]]]` at the head of `plugins/vulnerability-remediation--node--npm/subgraph/routing.py` enumerating every `(source_node, decision_predicate, dst_node)` triple the subgraph dispatches through (table-driven dispatch — data over branching code; Rule 2 explicit precedent from `_NODE_MODULES`, `_LEGAL_TRANSITIONS`, `_SEMANTIC_BOUNDARY_KINDS`), with the routing functions re-implemented as one-line lookups into the table; (2) an **exhaustive routing-table test suite** at `tests/unit/workflows/test_subgraph_routing_table.py` that parametrizes over every row in `_ROUTING_TABLE` (positive coverage) AND every `(source, decision) ∉ table` Hypothesis-drawn pair (negative coverage — rejection or unreachable), pins the `MAX_RETRIES = 3` cap, and proves the four canonical paths from S3-01 AC-9 are *projections* of the table (the table is the source of truth, the matrix is a view); (3) a **call-side AST fence** at `tests/fence/test_subgraph_no_peer_calls.py` (extending S3-01 AC-6's import-side fence) that walks every node module's AST for `Call` nodes whose `func` resolves by name to another node's `run` method (e.g., `IngestCveNode().run(state)`, `apply_recipe.run(state)`, `await write_branch_node.run(state)`) — final-design.md item 4 + arch §"Failure modes" row 2 verbatim. PLUS a fourth **cross-table consistency** invariant: every legal *ledger* transition in `_LEGAL_TRANSITIONS` that the subgraph is *responsible for* (operationally reachable inside the graph, not driven by HITL resume which S4-01 owns) is exercised by at least one row in `_ROUTING_TABLE`, and vice-versa (the routing table only emits transitions the ledger admits).

This story is the second half of `High-level-impl.md §"Step 3 — Plugin-local graph topology"` ("Add static tests forbidding direct node-to-node calls" — the AST fence; "Wire planner, transform, and gate ports through reducers and conditional edges" — the table-driven dispatch consolidation). S3-01 lands the *routing functions* (4 pure `route_after_<node>` functions + the four-path matrix test); this story lands the **table** the functions read from, the **exhaustive** coverage of that table, the **call-side** fence (S3-01 AC-6 is import-side only), and the **cross-table** invariant tying routing edges to ledger edges.

## References

- [final-design.md](../final-design.md) §"Decisions of record" item 4 ("Edges own control flow. Nodes compute; conditional edges decide. No node directly calls another node." — drives AC-3 + AC-7 verbatim; the AST fence's whole reason for being), §"Main workflow" step 6 (the four-routing matrix — AC-2 + AC-5 cross-projection invariant), §"State model" (the seven ledger variants — AC-6 cross-table consistency), §"Decisions of record" item 1 (plugin-local topology — drives the file path).
- [phase-arch-design.md](../phase-arch-design.md) §"Failure modes" row 2 ("node attempts direct peer call | AST test | CI failure" — drives AC-3 call-side AST fence; S3-01 AC-6 is import-side, this story is call-side), §"Testing strategy" ("Static tests: graph nodes may import ports, not each other directly" — extended here from "import" to "import OR call"), §"Testing strategy" ("Reducer unit tests: exhaustive transition matrix" — drives AC-1 exhaustive coverage), §"Logical view" (the `GRAPH` node — the routing table is the graph's dispatch substrate).
- [ADRs/0002-plugin-local-subgraph-topology.md](../ADRs/0002-plugin-local-subgraph-topology.md) §Decision (the verbatim plugin path; AC-3 fence is scoped to the plugin's `subgraph/nodes/` directory only — Phase-7 plugins inherit the protection via AC-8 generality).
- [ADRs/0003-checkpointed-ledger-replay-boundary.md](../ADRs/0003-checkpointed-ledger-replay-boundary.md) — consumed indirectly: the integrity short-circuit path (entry-edge `hydrate_or_fail` → `END`) is one of the four routing arms AC-2 enumerates; the table treats it as a *boundary* (entry-edge case) so the cross-table consistency invariant in AC-6 does not require an `_LEGAL_TRANSITIONS` row for it.
- [High-level-impl.md](../High-level-impl.md) §"Step 3 — Plugin-local graph topology" (third bullet "Add static tests forbidding direct node-to-node calls" — this story's AC-3 + AC-4; second bullet "Wire planner, transform, and gate ports through reducers and conditional edges" — the table-driven consolidation of the wiring).
- [S3-01-plugin-local-subgraph.md](S3-01-plugin-local-subgraph.md) — **primary upstream dependency.** This story extends S3-01's `routing.py` with `_ROUTING_TABLE` (additive — S3-01 ACs continue to hold byte-equal); S3-01 AC-6 (import-side fence) and AC-9 (four-path matrix) are *consumed* here, not replaced. S3-01 AC-7 (routing purity) is a *precondition* — the table-driven refactor must preserve purity.
- [S1-02-ledger-state-union.md](S1-02-ledger-state-union.md) + [_validation/S1-02-ledger-state-union.md](_validation/S1-02-ledger-state-union.md) — `_LEGAL_TRANSITIONS` (the ledger-edge inventory the cross-table invariant in AC-6 consumes), `LedgerStateKind`, the seven-variant universe; the precedent for **closed-set Final-mapping discipline** (Anti-refactor #2 — no registry, no decorator-extension) that this story mirrors for the routing table.
- [S2-01-semantic-checkpoints.md](S2-01-semantic-checkpoints.md) — `_SEMANTIC_BOUNDARY_KINDS` (consumed by AC-6: every destination state the routing table emits must be in this set when the destination is a semantic boundary; the test asserts the projection).
- [S1-01-sut-contract-types.md](S1-01-sut-contract-types.md) — the `codegenie.workflows.__all__` 14-name allowlist sentinel; AC-9 asserts the count and membership are **byte-equal-unchanged** after this story (the routing table lives under `plugins/`, not `src/codegenie/workflows/`; nothing new leaks to the public surface).
- [S4-01-hitl-interrupt-and-resume.md](S4-01-hitl-interrupt-and-resume.md) — downstream consumer; the HITL resume edges (`awaiting_human_review → plan_ready`, `awaiting_human_review → completed`) belong to S4-01's typed-resume validator, NOT to the subgraph's `_ROUTING_TABLE`. The cross-table invariant in AC-6 records this with an explicit `_HITL_LEDGER_EDGES: Final[frozenset[tuple[LedgerStateKind, LedgerStateKind]]]` exclusion set so the projection test does NOT fail when those edges are absent from the routing table.
- [S5-01-stable-sut-adapter.md](S5-01-stable-sut-adapter.md) — downstream consumer; the SUT adapter compiles the graph and dispatches the four canonical paths through it. AC-5 cross-projection ensures every adapter-visible path traces back to a routing table row.
- [S6-01-e2e-kill-resume-closeout.md](S6-01-e2e-kill-resume-closeout.md) — downstream consumer; the workflow-replay-determinism property exercises the routing table end-to-end. The table is the substrate; this story does not own the property itself.
- Precedent — closed-set `Final` mapping as table-driven dispatch substrate: `src/codegenie/workflows/vuln_ledger.py::_LEGAL_TRANSITIONS` (closed-set transition pairs), `src/codegenie/workflows/checkpoints.py::_SEMANTIC_BOUNDARY_KINDS` (closed-set boundary kinds), `src/codegenie/workflows/_chain.py` (pure-core helpers). Rule-of-three for the **closed-set-Final-mapping-with-AST-fence** pattern is met by these three precedents; this story adds the fourth concrete consumer — and **explicitly rejects** introducing a generalized `RoutingTableRegistry` or `@register_routing_row` decorator: the rule-of-three threshold for a *registry over routing tables* is unmet until Phase-7 ships a second plugin's routing table AND Phase-8+ ships a third (Anti-refactor #1).

## Acceptance criteria

### Declarative routing table + table-driven dispatch

- [ ] **AC-1 — `_ROUTING_TABLE` is a closed `Final[Mapping[SourceNode, frozenset[RoutingDecision]]]` at the head of `plugins/vulnerability-remediation--node--npm/subgraph/routing.py`.** The shape is **declarative data**, not branching code:
  ```python
  SourceNode = Literal["ingest_cve", "match_recipe", "apply_recipe", "stage6_validate", "write_branch"]
  DstNode    = Literal["match_recipe", "apply_recipe", "stage6_validate", "write_branch", "__end__"]
  # `RoutingDecision` is a frozen Pydantic model (mirrors the S1-02 sum-type
  # convention — no anaemic dicts for routing rows):
  class RoutingDecision(BaseModel):
      model_config = _FROZEN_FORBID
      predicate_name: Literal[
          "gate_passed",
          "gate_failed_retryable",
          "gate_failed_repeated",        # retry_count >= MAX_RETRIES
          "node_short_circuited",         # ShortCircuit(terminal=...) from any node
          "node_escalated",               # Escalate(reason="awaiting_human_review")
          "node_advanced_to_next",        # straight-line Advance(next_node=...)
      ]
      dst: DstNode
      ledger_edge: tuple[LedgerStateKind, LedgerStateKind] | None  # see AC-6
  _ROUTING_TABLE: Final[Mapping[SourceNode, frozenset[RoutingDecision]]] = MappingProxyType({
      "ingest_cve":       frozenset({...}),
      "match_recipe":     frozenset({...}),
      "apply_recipe":     frozenset({...}),
      "stage6_validate":  frozenset({...}),
      "write_branch":     frozenset({...}),
  })
  ```
  Three tests at `tests/unit/workflows/test_subgraph_routing_table_shape.py`:
  1. The mapping is **read-only** — `_ROUTING_TABLE` is `MappingProxyType` (or equivalent); mutating attempts raise `TypeError`. **Mutation thinking:** an executor swapping `MappingProxyType` for `dict` silently allows runtime drift; the read-only assertion catches it.
  2. Every `SourceNode` key matches the five-node sequence from S3-01 AC-1 (`{"ingest_cve", "match_recipe", "apply_recipe", "stage6_validate", "write_branch"}`); a missing key OR an extra key fails. **Mutation thinking:** dropping `"write_branch"` silently bypasses the post-patch commit step; the membership equality test catches the omission and the directive points at S3-01 AC-1.
  3. Every `RoutingDecision.dst` is either a `SourceNode` or the LangGraph sentinel `"__end__"`; no other destinations are admitted. **Mutation thinking:** a routing row pointing at `"completed"` (a *ledger* state, not a *node*) would conflate the two layers; the type-restricted membership assertion catches it.

- [ ] **AC-2 — Routing functions are one-line table lookups (table-driven dispatch).** Each of S3-01 AC-7's pure routing functions (`route_after_ingest_cve`, `route_after_match_recipe`, `route_after_apply_recipe`, `route_after_stage6_validate`, `route_after_write_branch`) is rewritten so its body computes a `predicate_name` from the input `SubgraphState` and the prior `NodeTransition`, looks up the matching `RoutingDecision` in `_ROUTING_TABLE[source_node]`, and returns the `dst` string LangGraph's `add_conditional_edges` consumes. The function body is the **lookup**; the decisions are the **data**. The predicate-computation step is itself a pure helper `_predicate_for(state: SubgraphState, last_transition: NodeTransition) -> PredicateName` at the same module-level — exhaustive `match` over the `NodeTransition` tagged union arms + the `retry_count >= MAX_RETRIES` cap, with `assert_never` on the default arm so a future `NodeTransition` amendment surfaces as a `mypy --strict` failure.

  Test at `tests/unit/workflows/test_subgraph_routing_table_dispatch.py`: for every `(source, RoutingDecision)` pair in `_ROUTING_TABLE`, constructing an input `(state, last_transition)` that satisfies `RoutingDecision.predicate_name` and calling `route_after_<source>(state)` returns `RoutingDecision.dst` byte-equal. The synthetic-input builder lives in `tests/unit/workflows/_routing_fixtures.py` and is itself a closed dispatch over `PredicateName` (so a new predicate added to `_ROUTING_TABLE` requires a fixture extension — fail-loud, mirror the S1-02 / S6-03 amendment discipline). **Mutation thinking:** a `route_after_stage6_validate` that returns `"write_branch"` regardless of gate state would pass the S3-01 AC-9 single-pass matrix but fail the exhaustive table dispatch test the moment the `gate_failed_retryable` row fires; the table coverage forces every branch.

- [ ] **AC-3 — Call-side AST fence: no direct node-to-node `Call` expressions.** A new fence at `tests/fence/test_subgraph_no_peer_calls.py` extends S3-01 AC-6 (which is import-side only) with a *call-side* walk. The fence walks every `.py` file under `plugins/vulnerability-remediation--node--npm/subgraph/nodes/` and rejects any `ast.Call` whose `func` resolves to another node's `run` method by name. Concretely:
  ```python
  _NODE_RUN_NAMES: Final[frozenset[str]] = frozenset({
      "IngestCveNode", "MatchRecipeNode", "ApplyRecipeNode",
      "Stage6ValidateNode", "WriteBranchNode",
  })

  def _is_peer_run_call(call: ast.Call, current_node_stem: str) -> bool:
      """Return True if `call` is `<PeerNode>(...).run(...)` or
      `peer_instance.run(...)` where `peer_instance` was constructed from a
      peer node class, OR `<peer_module>.run(...)` where the module name is
      one of the five sibling node modules."""
  ```
  The fence also walks for the simpler shape `await ingest_cve.run(state)` (a `Call` on a module-level `ImportFrom`-bound name matching `_NODE_MODULES - {current_module}`) and rejects it. A directive message names final-design.md item 4 verbatim and points the executor at the conditional-edge dispatch in `builder.py`. **Mutation thinking:** an executor who reads S3-01 AC-6 narrowly, removes the sibling `ImportFrom`, then calls the peer via a re-export *through `nodes/__init__.py`* (which IS legal as an import) — the AST `Call` walk catches the call shape even when the import path is laundered.

- [ ] **AC-4 — AST fence assertion catalog: every node module passes both the S3-01 AC-6 import-side fence AND this story's call-side fence.** A parametrized test over the five node modules asserts both fences agree on the verdict for each module (no module passes one fence but trips the other). This is the **conjunction guard**: the import and call fences are complementary — neither alone is sufficient. **Mutation thinking:** an executor disables one fence ("the other one covers it") via a `# noqa: ROUTING_FENCE` marker; the conjunction assertion still trips on the disabled side and the directive names the missing fence by ID.

- [ ] **AC-5 — Four-path matrix from S3-01 AC-9 is a *projection* of `_ROUTING_TABLE`.** A test at `tests/unit/workflows/test_subgraph_routing_matrix_projection.py` parametrizes over the four canonical paths (gate-pass → `Completed`; retryable → `match_recipe` replan; repeated → `AwaitingHumanReview`; integrity → `FailedUnrecoverable`) AND asserts that each canonical path traces through a *contiguous chain of `_ROUTING_TABLE` rows*. Concretely: each canonical path is a list `[(source₁, dst₁), (source₂, dst₂), ...]` where every `(srcᵢ, dstᵢ)` matches some `RoutingDecision` in `_ROUTING_TABLE[srcᵢ]`. The test asserts (i) every step in every canonical path is present in the table; (ii) every `RoutingDecision` in the table is reachable from `"ingest_cve"` via some sequence of decisions (no dead routing rows — a row no canonical path or replan loop reaches is a soft-lock bug). **Mutation thinking:** an executor adds a `RoutingDecision(predicate_name="node_advanced_to_next", dst="apply_recipe")` row to `stage6_validate` (skipping `write_branch`) — the reachability test asserts the `write_branch` row is still reachable from `"ingest_cve"`, and the canonical-path projection asserts the pass-path still traces through `stage6_validate → write_branch`; both catch the regression.

### Cross-table consistency (routing table ↔ ledger transition table)

- [ ] **AC-6 — Every `_ROUTING_TABLE` row with a non-`None` `ledger_edge` pins an edge in `_LEGAL_TRANSITIONS`, and every subgraph-owned legal ledger transition is covered by the routing table.** Concretely:
  1. **Forward consistency** (`_ROUTING_TABLE → _LEGAL_TRANSITIONS`): for every `RoutingDecision` in `_ROUTING_TABLE` with `ledger_edge=(prior_kind, next_kind)`, `(prior_kind, next_kind) ∈ _LEGAL_TRANSITIONS`. A routing decision emitting a transition the ledger forbids would be silently broken at the model_validator boundary; the cross-table test forces them to agree.
  2. **Backward consistency** (`_LEGAL_TRANSITIONS → _ROUTING_TABLE`): for every `(prior, next) ∈ _LEGAL_TRANSITIONS \ _HITL_LEDGER_EDGES \ _ENTRY_LEDGER_EDGES`, there exists at least one `RoutingDecision` in some `_ROUTING_TABLE[source]` with `ledger_edge == (prior, next)`. The two exclusion sets are declared at the head of `routing.py`:
     ```python
     _HITL_LEDGER_EDGES: Final[frozenset[tuple[LedgerStateKind, LedgerStateKind]]] = frozenset({
         ("awaiting_human_review", "plan_ready"),
         ("awaiting_human_review", "completed"),
         ("awaiting_human_review", "failed_unrecoverable"),
     })  # owned by S4-01 typed-resume validator, not by the subgraph router.
     _ENTRY_LEDGER_EDGES: Final[frozenset[tuple[LedgerStateKind, LedgerStateKind]]] = frozenset({
         # The integrity short-circuit at the entry edge is NOT a ledger
         # transition; it is the *pre-state* of the graph. The first ledger
         # row a clean run writes is `(needs_plan → plan_ready)` from
         # match_recipe; integrity failure short-circuits BEFORE any ledger
         # row is written. No edge exclusion needed for the integrity path —
         # `FailedUnrecoverable` from `hydrate_or_fail` is written by the
         # S2-02 verifier, not by a routing decision.
     })  # placeholder; declared for documentation symmetry, currently empty.
     ```
  3. **Semantic-boundary projection** (`_ROUTING_TABLE → _SEMANTIC_BOUNDARY_KINDS`): for every `RoutingDecision.ledger_edge=(_, next_kind)` where `next_kind ∈ _SEMANTIC_BOUNDARY_KINDS` (i.e., the destination is a boundary that triggers a checkpoint write), the routing destination must be a node that emits a `TransitionEvent` (per S2-01 boundary-only append discipline). The test asserts every such `next_kind` is reachable from a node whose `run()` body writes a `TransitionEvent` of kind `next_kind`.

  Three tests at `tests/integration/workflows/test_routing_ledger_consistency.py` — one per consistency direction. Each test prints a *directive* on failure naming both the offending row(s) and the precise amendment path (e.g., *"Forward consistency violated: `_ROUTING_TABLE[stage6_validate]` emits `ledger_edge=('patch_applied', 'cancelled')` but `cancelled` is not in `LedgerStateKind`. Adding a new ledger kind is an ADR-0001 + ADR-0003 amendment per S1-02 AC-15."*). **Mutation thinking:** a future story adds a new ledger transition (e.g., `gate_failed_retryable → patch_applied` re-apply shortcut) to `_LEGAL_TRANSITIONS` but forgets to expose it via the routing table — backward consistency fires loud. Conversely, a routing row emitting an edge missing from `_LEGAL_TRANSITIONS` — forward consistency fires loud before the model_validator does at runtime.

### Negative coverage + bounded-retry pin

- [ ] **AC-7 — Hypothesis property: every `(source, predicate)` pair NOT in `_ROUTING_TABLE` is unreachable from the production code.** A property test at `tests/unit/workflows/test_subgraph_routing_table_negatives.py`:
  ```python
  @given(st.sampled_from(get_args(SourceNode)),
         st.sampled_from(get_args(PredicateName)))
  def test_negative_pair_either_in_table_or_unreachable(
      source: SourceNode, predicate: PredicateName,
  ) -> None:
      """For any (source, predicate) drawn from the closed universe,
      EITHER the pair is in `_ROUTING_TABLE[source]` (matches some
      RoutingDecision.predicate_name) OR the test fixture builder
      `_routing_fixtures.build_state_for_predicate(source, predicate)`
      raises `UnreachableInProduction(reason=...)` with a directive."""
  ```
  The point is to prove the predicate enumeration is **closed and exhaustive**: a `(source, predicate)` pair not in the table is one of two things — (i) a state shape the graph CANNOT enter from `"ingest_cve"`, or (ii) a missing row. The fixture builder forces the implementer to declare which; a "silent gap" pair (neither in the table NOR explicitly unreachable) fails the property loud. **Mutation thinking:** the implementer adds a sixth predicate `"node_paused"` to `PredicateName` for a speculative HITL path but never adds a routing row OR an unreachable marker — Hypothesis draws the new predicate and the fixture builder raises an unexpected exception, surfacing the gap.

- [ ] **AC-8 — `MAX_RETRIES = 3` is pinned by name and by enforcement.** A test at `tests/unit/workflows/test_subgraph_max_retries_cap.py`:
  1. Asserts `routing.MAX_RETRIES == 3` (the constant is declared `Final[int]` per S3-01 AC-10 + the table-driven refactor preserves it).
  2. Parametrizes over `retry_count ∈ {0, 1, 2}` and asserts the `gate_failed_retryable` predicate routes to `"match_recipe"` (replan loop).
  3. For `retry_count == 3`, asserts the `gate_failed_repeated` predicate fires and the routing destination is `"__end__"` (with the `NodeTransition.Escalate(reason="awaiting_human_review")` carried).
  4. For `retry_count > 3` (off-by-one drift), asserts the `gate_failed_repeated` predicate still fires (the cap is a `>=`, not a `==`).

  **Mutation thinking:** changing `MAX_RETRIES = 3` to `MAX_RETRIES = 2` would silently shorten the loop and pass S3-01 AC-10 (which only asserts boundedness, not the specific cap); the exact-value pin here catches the regression. Changing `retry_count >= MAX_RETRIES` to `retry_count == MAX_RETRIES` breaks `retry_count > 3` (e.g., 4); the off-by-one parametrization catches it.

### Generality + closeout

- [ ] **AC-9 — `codegenie.workflows.__all__` is byte-equal-unchanged AND `_ROUTING_TABLE` does NOT leak through any public surface.** Two parts:
  1. The S1-01 / S1-02 / S2-01 / S2-02 14-name allowlist sentinel test continues to pass byte-equal — this story adds zero symbols to `codegenie.workflows.__all__`. The routing table lives under `plugins/vulnerability-remediation--node--npm/subgraph/routing.py`; Phase-6.5 may NOT depend on it (final-design.md §"Relationship to Phase 6.5": "may NOT depend on: the concrete graph builder; node names; checkpoint backend internals; plugin-local file layout").
  2. A new fence at `tests/fence/test_routing_table_isolation.py` AST-walks every `.py` under `src/codegenie/` and asserts NONE import `plugins.vulnerability_remediation__node__npm.subgraph.routing` (the routing table is private to the plugin; `src/codegenie/` MUST NOT consume it — the dependency direction is plugin → kernel, never kernel → plugin per ADR-0002).

  **Mutation thinking:** an executor re-exports `_ROUTING_TABLE` through `codegenie.workflows.__init__` "for the SUT adapter's convenience" — the byte-equality sentinel catches the leak; the directive names final-design.md §"Relationship to Phase 6.5" verbatim. A future kernel module imports `plugins.…subgraph.routing` to introspect — the isolation fence catches the upward dependency.

- [ ] **AC-10 — General `tests/fence/test_subgraph_no_peer_calls.py` walks ALL `plugins/*/subgraph/nodes/` directories, not just Phase-6's.** Per the S3-01 AC-15 isolation-fence precedent — the fence is general; Phase-7's plugin (`plugins/migration--container--distroless/` or similar) will land its own `subgraph/nodes/` directory and inherit the protection automatically. Concretely, the fence resolves the glob `plugins/*/subgraph/nodes/*.py` at test discovery time and parametrizes over every match; no Phase-6-specific path is hardcoded. **Mutation thinking:** writing the fence as `_PHASE6_NODES_DIR = Path("plugins/vulnerability-remediation--node--npm/subgraph/nodes/")` makes Phase-7 require a fence amendment; the glob-based discovery makes Phase-7 inherit the protection by addition.

- [ ] **AC-11 — Contract snapshot extension + `mypy --strict` clean.** Two closeout gates:
  1. `tests/integration/test_phase6_sut_contract_snapshot.py` extended with: (a) the sorted-tuple representation of `_ROUTING_TABLE` ((source, predicate_name, dst, ledger_edge) for every row, sorted lex); (b) the values of `_HITL_LEDGER_EDGES` and `_ENTRY_LEDGER_EDGES`; (c) `MAX_RETRIES`. The meta-test classifier (`_meta.py`) gets one additive synthetic delta (new routing row with a valid ledger edge → additive) and one breaking synthetic delta (removed routing row → breaking, requires ADR-0003 amendment) so the classifier is exercised on routing-shaped deltas, not only on ledger / verifier shapes.
  2. `make typecheck` passes over the new routing table + the test fixtures. No `Any`, no untyped `dict`, no `# type: ignore` without an upstream-issue comment. The `Mapping[SourceNode, frozenset[RoutingDecision]]` type is the load-bearing typecheck: a `dict[str, list[dict]]` slip would bypass the closed `SourceNode` Literal and re-admit anaemic dicts.

  Regenerate the golden via `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` and commit.

## Files to touch

- `plugins/vulnerability-remediation--node--npm/subgraph/routing.py` (modify — add `_ROUTING_TABLE`, `RoutingDecision`, `SourceNode`, `DstNode`, `PredicateName` Literals, `_HITL_LEDGER_EDGES`, `_ENTRY_LEDGER_EDGES`, `_predicate_for` pure helper; refactor the four `route_after_*` functions to be one-line table lookups; preserve `MAX_RETRIES` byte-equal)
- `tests/unit/workflows/test_subgraph_routing_table_shape.py` (new — AC-1)
- `tests/unit/workflows/test_subgraph_routing_table_dispatch.py` (new — AC-2)
- `tests/unit/workflows/_routing_fixtures.py` (new — closed-dispatch synthetic-input builder; the predicate-enumeration trampoline for AC-2 + AC-7 + AC-8 tests)
- `tests/fence/test_subgraph_no_peer_calls.py` (new — AC-3 call-side AST fence; **note:** this filename is reserved by S3-01 AC-6 for the *import-side* fence; this story's AC-3 fence MUST be a sibling file. Use `tests/fence/test_subgraph_no_peer_calls_callside.py` if the import-side fence already owns the original name — see Notes for the implementer)
- `tests/fence/test_subgraph_call_side_fence_conjunction.py` (new — AC-4 conjunction guard pairing the import-side + call-side fences)
- `tests/unit/workflows/test_subgraph_routing_matrix_projection.py` (new — AC-5)
- `tests/integration/workflows/test_routing_ledger_consistency.py` (new — AC-6 forward + backward + semantic-boundary projection)
- `tests/unit/workflows/test_subgraph_routing_table_negatives.py` (new — AC-7 Hypothesis negative)
- `tests/unit/workflows/test_subgraph_max_retries_cap.py` (new — AC-8 exact-value pin + off-by-one parametrization)
- `tests/fence/test_routing_table_isolation.py` (new — AC-9 plugin → kernel direction fence)
- `tests/integration/test_phase6_sut_contract_snapshot.py` (modify — extend per AC-11)
- `tests/integration/test_phase6_sut_contract_snapshot_meta.py` (modify — add routing-shaped synthetic deltas per AC-11)
- `tests/golden/phase6-contract/snapshot.json` (modify — regenerate under `PHASE6_CONTRACT_GOLDEN_REWRITE=1` after AC-11)

## TDD plan

**Red.** Land in this order — every step writes a failing test first, then verifies the failure mode is meaningful (the error message names a specific failure, not just an exception class) before writing production code:

1. AC-1 routing-table shape test (fails: `_ROUTING_TABLE` doesn't exist; the read-only assertion, the five-key membership equality, and the `dst ∈ SourceNode ∪ {"__end__"}` membership all fail).
2. AC-3 call-side AST fence (fails: file doesn't exist; once it does, the fence trivially passes against S3-01's current node modules — its purpose is to *bite* if a future mutation adds a peer call. Start the fence here so the catalog is in place.)
3. AC-4 conjunction guard (fails: file doesn't exist; the test imports both fences and asserts they agree on the verdict per-module).
4. AC-8 `MAX_RETRIES` exact-value + off-by-one tests (fail: `gate_failed_repeated` predicate may not yet exist if S3-01's `routing.py` has not been refactored; the test names what the cap MUST be).
5. AC-2 table-driven dispatch test (fails: the routing functions are not yet one-line lookups; the test parametrizes over every `_ROUTING_TABLE` row and asserts the per-predicate fixture builder produces inputs that dispatch correctly).
6. AC-7 Hypothesis negative property (fails: the fixture builder doesn't yet declare unreachability markers; the property surfaces every silent gap).
7. AC-5 four-path projection (fails: the canonical paths exist in S3-01 AC-9 but the projection assertion requires every step to match a `_ROUTING_TABLE` row).
8. AC-6 cross-table consistency (fails: forward consistency until every routing row's `ledger_edge` agrees with `_LEGAL_TRANSITIONS`; backward consistency until every non-HITL, non-entry-edge legal transition has a routing-table row; semantic-boundary projection until every checkpoint-writing destination is reached from a `TransitionEvent`-emitting node).
9. AC-9 part 1 — `codegenie.workflows.__all__` sentinel re-run (already passes; this AC asserts it CONTINUES to pass after the story lands).
10. AC-9 part 2 — kernel → plugin isolation fence (fails: file doesn't exist; once it does, walks `src/codegenie/` and asserts nobody imports `plugins.…subgraph.routing`).
11. AC-10 fence generality (fails initially trivially passing — only Phase-6 has a `plugins/*/subgraph/nodes/` directory today; the test exercises the glob-discovery shape so a Phase-7 plugin inherits protection automatically).
12. AC-11 contract snapshot extension (fails on first run with the directive; commit the regenerated golden in Green; meta-test asserts the additive + breaking classifier covers routing-shaped deltas).

**Green.** Implement the minimum that makes all red tests pass:

- Add `_ROUTING_TABLE`, `RoutingDecision`, the Literal aliases (`SourceNode`, `DstNode`, `PredicateName`), and the `_HITL_LEDGER_EDGES` / `_ENTRY_LEDGER_EDGES` exclusion sets at the head of `routing.py`. Use `MappingProxyType` for read-only.
- Add `_predicate_for(state, last_transition)` as a pure `match`-on-`NodeTransition` helper with `assert_never` on the default arm.
- Refactor the four `route_after_*` functions to one-line table lookups (`return _lookup(_ROUTING_TABLE[source], _predicate_for(state, last_transition)).dst`). The diff to `routing.py` is a *consolidation*, not an expansion — the existing per-function `if/elif` branches collapse into the table.
- Implement the call-side AST fence walking `ast.Call` nodes whose `func` resolves to a sibling node module's `run` method by name OR via re-export.
- Implement the cross-table consistency fixtures + assertions; the `ledger_edge: tuple | None` field on `RoutingDecision` is the bridge.
- Extend the contract snapshot test + regenerate the golden under `PHASE6_CONTRACT_GOLDEN_REWRITE=1`.

**Refactor.** Cleanup only — no new behaviour:

- Confirm `MAX_RETRIES` is `Final[int]` and module-level (not class-level on a routing class).
- Confirm `_ROUTING_TABLE` is the SOLE site enumerating routing decisions — no `if/elif` branches survive in `route_after_*` functions (the AC-2 test catches drift, but a manual scan is cheap).
- Confirm `_HITL_LEDGER_EDGES` and `_ENTRY_LEDGER_EDGES` are at module level (not inlined inside the consistency test).
- Confirm the per-node fence files reference final-design.md item 4 verbatim in their directive messages so a future executor reading the failure understands the load-bearing decision.

**Anti-refactor (Rule 2 + Open/Closed at the file boundary + composition-over-inheritance).** Do NOT introduce any of the following in this story:

1. **A `RoutingTableRegistry` or `@register_routing_row` decorator.** The five-source × six-predicate routing universe is closed; making it pluggable is a Rule-2 violation. The rule-of-three threshold for a *registry over routing tables* would be met only when Phase-7 ships a second plugin's routing table AND Phase-8+ ships a third — and even then, per-plugin tables live in per-plugin files (ADR-0002 plugin-local topology). The substrate the future registry would build on is the closed-Mapping pattern; this story ships that substrate.
2. **A `BaseRoutingDecision` ABC or `RoutingDecisionMixin`.** `RoutingDecision` is a single Pydantic model; no sibling variants justify an abstraction. Composition via the `predicate_name: Literal[...]` Literal IS the variant discriminator (mirrors the S1-02 sum-type discipline — Literal-discriminated, not subclass-discriminated).
3. **A data-driven graph topology in the routing table.** The routing table enumerates *decisions*, not *graph nodes* — the `add_node` / `add_edge` topology lives in `builder.py` (S3-01 territory). Mixing them would couple the routing layer to the LangGraph imperative builder, defeating the table's separability for testing.
4. **A `Specification`-pattern predicate composer (`AND(GatePassed, NotRetryExhausted)`).** Six predicate names today; each is a 1-3 line pure `match` arm; Rule 2 explicit ("three similar lines is better than premature abstraction"). The `PredicateName` Literal IS the specification language.
5. **A `RoutingResult` wrapper around the bare `dst: DstNode` string.** LangGraph's `add_conditional_edges` consumes the bare destination string. Wrapping it in a `RoutingResult` / `RouteOutcome` would force `route_after_*` callers to unwrap before passing to LangGraph — pure boilerplate.
6. **An exhaustive `_ROUTING_TABLE` exposed through `codegenie.workflows.__all__` "for the SUT adapter's convenience."** AC-9 forbids this. The SUT adapter (S5-01) compiles the graph through `Plugin.build_subgraph()`; it never reads `_ROUTING_TABLE` directly. Phase-6.5 must not depend on the routing topology per final-design.md §"Relationship to Phase 6.5".
7. **A consolidated single test file at `tests/unit/workflows/test_subgraph_routing.py` covering all four ACs in one parametrize.** Each AC has a distinct mutation-resistance role (shape, dispatch, projection, negative). Bundling them collapses the failure-mode resolution at CI time — when one fails, the executor has to read N parametrizations to identify which AC tripped. One file per AC is the load-bearing discoverability discipline (mirrors S1-02 split into per-AC test files).
8. **A `tests/fence/test_subgraph_no_peer_calls.py` that REPLACES S3-01 AC-6.** This story's AC-3 fence is the *call-side* complement to S3-01 AC-6's import-side fence. Both must remain green. The conjunction guard (AC-4) is the assertion that both are load-bearing. Replacing one with the other (e.g., "the call-side fence subsumes the import-side") would silently un-cover the import-shaped regression where a node imports a peer but never calls it — the import is the smell on its own (CLAUDE.md "no unused imports" / "fail loud"); the import-side fence catches it before the call ever lands.

## Out of scope

- The routing functions themselves (`route_after_<node>`) — S3-01 owns the *introduction* of these functions; this story owns their *refactor* into one-line table lookups + the *table* they read from. The 4-path matrix test (`tests/unit/workflows/test_subgraph_routing_matrix.py`) from S3-01 AC-9 continues to pass byte-equal; this story's AC-5 is the projection assertion on top.
- The HITL typed-resume validator and the `awaiting_human_review → plan_ready` / `→ completed` / `→ failed_unrecoverable` edges — Phase-6 S4-01 owns those. The cross-table invariant (AC-6) declares them in `_HITL_LEDGER_EDGES` as an explicit exclusion so the projection test does NOT fail when they are absent from `_ROUTING_TABLE`.
- The entry-edge `hydrate_or_fail` integrity short-circuit — Phase-6 S2-02 + S3-01 own this. The integrity short-circuit is NOT a ledger transition; it is the pre-state of the graph. `_ENTRY_LEDGER_EDGES` is declared as an empty frozenset for documentation symmetry; if a future story discovers an entry-edge transition, that's an additive amendment.
- The workflow-replay-determinism property — Phase-6 S6-01 closeout owns this. This story provides the routing-table substrate the property exercises; the property itself depends on the fully-wired graph (S3-01 + S5-01) + checkpointer (S2-01) + ledger (S1-02).
- A `RoutingTableRegistry` + `@register_routing_row` decorator + per-plugin routing-table substrate — Phase-7+ owns this if and only if the rule-of-three threshold is met. This story is the first concrete consumer of the closed-Mapping pattern for routing; the second is Phase-7's plugin; the third is Phase-8+ before any registry abstraction is justified.
- A `BaseRoutingDecision` ABC, `Specification`-pattern predicate composer, or `RoutingResult` wrapper — see Anti-refactor #2, #4, #5.

## Notes for the implementer

- **Why the table lives in `routing.py`, not in a sibling `routing_table.py`.** The table IS the routing layer's source of truth; separating them would force every routing-function consumer to import from two files and weaken the "data over branching code" coupling. The closed-Mapping at the head of `routing.py` mirrors the S1-02 `_LEGAL_TRANSITIONS` location at the head of `vuln_ledger.py` and `_SEMANTIC_BOUNDARY_KINDS` at the head of `checkpoints.py` — three precedents, rule-of-three earned for "closed-set Final mapping co-located with the dispatching module."

- **Why `MappingProxyType` and not a plain `dict`.** Pydantic + Python's runtime do not enforce `Final[Mapping[...]]` read-only-ness at attribute-access time; `_ROUTING_TABLE["ingest_cve"].add(...)` would silently mutate state if the frozenset were swapped for a regular set, or `_ROUTING_TABLE["ingest_cve"] = ...` would re-bind if the outer were a `dict`. `MappingProxyType` raises `TypeError` on assignment; frozenset raises `AttributeError` on `add`. The AC-1 read-only test asserts both layers.

- **Why `RoutingDecision` is a frozen Pydantic model, not a `NamedTuple`.** Two reasons: (i) Pydantic gives `model_config = _FROZEN_FORBID` (the same single-canonical config every other workflow type uses — AC-12 in S1-02's `_FROZEN_FORBID` AST fence walks `plugins/*/subgraph/*.py` if the path is added to its target list; doing so additively is a one-line change); (ii) the `ledger_edge: tuple[LedgerStateKind, LedgerStateKind] | None` field's `LedgerStateKind` Literal narrows the type at parse time, which a `NamedTuple` would force `mypy --strict` to widen to `tuple[str, str]`. Pydantic's discriminator + Literal machinery preserves the narrowing.

- **Why the call-side AST fence is a separate file from S3-01 AC-6's import-side fence.** The import side and the call side catch different mutations: an executor who removes the `from .ingest_cve import IngestCveNode` line but still references `IngestCveNode` via a re-export through `nodes/__init__.py` defeats the import fence; an executor who keeps the import but never calls the peer's `run()` (e.g., for a type annotation) trips the import fence falsely. Both fences are load-bearing; the conjunction guard (AC-4) asserts both must agree on the verdict. Bundling them would conflate the two failure modes.

- **Why the cross-table consistency invariant exists.** Two transition tables (`_LEGAL_TRANSITIONS` in the ledger, `_ROUTING_TABLE` in the subgraph) covering related-but-distinct universes is a classic *drift hazard*: someone adds a new ledger transition without exposing it through routing (the ledger admits it; the graph can never emit it — soft-lock); someone adds a new routing row without amending the ledger (the model_validator rejects the transition at runtime — loud failure but only at the first execution that hits the row). The forward + backward consistency tests at the integration boundary catch both at CI time. The two explicit exclusion sets (`_HITL_LEDGER_EDGES`, `_ENTRY_LEDGER_EDGES`) name the *responsibility boundary* between the subgraph routing and S4-01 HITL / S2-02 entry-edge layers — moving an edge across the boundary is a deliberate amendment to one of the exclusion sets, never a silent drift.

- **Why the negative Hypothesis property requires an `UnreachableInProduction` marker.** A `(source, predicate)` pair that is neither in the routing table NOR explicitly unreachable is a silent gap — the test fixture builder can't construct an input, and the production code may or may not handle the case. By forcing the implementer to mark the pair as unreachable (with a reason), the gap becomes loud: a future predicate added to `PredicateName` requires *either* a routing row *or* an `UnreachableInProduction` marker. This is the "make illegal states unrepresentable" discipline applied to test fixtures, not just production data shapes.

- **Why `MAX_RETRIES` pinning is exact-value + off-by-one + comparison-operator.** S3-01 AC-10 asserts boundedness (no infinite loop). This story's AC-8 asserts the *specific* cap (3) and the comparison operator (`>=`). Together they catch three mutation classes: (i) infinite loop (caught by S3-01 boundedness); (ii) wrong cap value (e.g., 2 or 5 — caught by AC-8 exact-value); (iii) wrong comparison (e.g., `==` instead of `>=` — caught by AC-8 off-by-one with `retry_count > 3`). All three are observable in the routing-table layer; the table makes them parametrizable.

- **Why the contract snapshot includes both `_ROUTING_TABLE` and `_HITL_LEDGER_EDGES`.** The exclusion sets are part of the *interface contract* between the subgraph and S4-01: moving an edge from "owned by subgraph" to "owned by HITL" changes which validator must handle it. The contract snapshot's additive-vs-breaking classifier (S1-02 AC-15) is exercised on routing-shaped deltas so a future S4-01 amendment that *also* changes the exclusion sets surfaces as a breaking delta that needs review, not as a silent ledger drift.

- **Why a Phase-7 plugin will inherit AC-10 fence protection automatically.** The fence resolves the glob `plugins/*/subgraph/nodes/*.py` at test discovery time and parametrizes over every match. When Phase-7 lands `plugins/migration--container--distroless/subgraph/nodes/`, the fence walks those files without amendment. The same generality discipline as S3-01 AC-15's cross-plugin isolation fence (which walks all plugin pairs). Writing the fence as `_PHASE6_NODES_DIR = Path("plugins/vulnerability-remediation--node--npm/subgraph/nodes/")` would force a Phase-7 amendment and miss the Open/Closed-at-the-file-boundary substrate.

- **Phase-9 forward dep — the routing table is checkpointer-agnostic.** The Phase-9 Postgres `CheckpointStore` adapter lands additively under the same Protocol; `_ROUTING_TABLE` is unchanged because routing decisions depend on `SubgraphState` shape + `NodeTransition` arms, not on the checkpoint substrate. This story freezes the routing substrate that makes Phase-9 a true zero-touch refactor at the routing layer.

- **Implementation-order suggestion.** The AC-1 table shape, AC-3 call-side fence, and AC-8 retry cap are independent — land them first to establish the substrate. AC-2 (table-driven dispatch refactor) is the consolidation that follows; it's *the* refactor of S3-01's `routing.py`. AC-5 (matrix projection) and AC-6 (cross-table consistency) are the *integration* assertions that fire once the substrate is in place. AC-7 (Hypothesis negative) and AC-10 (generality) are the *defensive* layers on top. AC-11 (contract snapshot) closes the loop. The TDD plan above interleaves them so the substrate exists before the integration tests run.
