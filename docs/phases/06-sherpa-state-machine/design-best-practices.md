# Phase 6 — SHERPA-style state machine for the vuln loop: Best-practices-first design

**Lens:** Best practices — maintainability, testability, idiomatic LangGraph + Python.
**Designed by:** Best-practices-first design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 6 is the **first time LangGraph touches the orchestrator** in this codebase. Every prior phase built a synchronous, sequential, testable foundation: Phase 3's `RemediationOrchestrator` is six function calls in a row; Phase 4's `FallbackTier` is a function; Phase 5's `GateRunner.run` is a plain `for` loop. Phase 6 lifts those into a LangGraph `StateGraph` **without changing what they do** — the nodes are thin wrappers over the existing engines, the conditional edges are thin wrappers over the gate verdicts already produced by Phase 5's `StrictAndGate`, and the SQLite checkpointer is configuration. The hard part is the **discipline** — Pydantic-typed state, nodes never call nodes, every conditional edge is a pure function over state, `interrupt()` at low-trust transitions only.

I optimized for: **one `graph/` package with a flat node module, a single Pydantic `VulnLedger` state model with explicit field ownership, conditional edges as pure functions of state, `langgraph-cli`-renderable topology from day one, a per-node unit test that constructs state and asserts the next-node target, replay tests that round-trip through the checkpointer, and a golden-graph snapshot test that fails on any topology drift.** The retry counter (ADR-0014) lives in state, not in node closures. `interrupt()` is one node, called from one place, with one canonical resume contract. The graph compiles at module import; module import is what tests use.

I deprioritized: shared subgraph abstractions (ADR-0022 says Three Strikes — vuln is strike one; Phase 7 distroless is strike two; strike three is when we extract), LLM-driven supervisor logic (ADR-0018 says pure routing — the Phase-6 supervisor is a switch over `intent.task_type` because the vuln workflow is the only task class in scope), Temporal envelope (Phase 9's territory — Phase 6 must not assume Temporal's idempotency, but must also not paint Phase 9 into a corner; we keep state JSON-serializable and node side-effects file-system-only, not network-IO), Postgres checkpointer (ADR-0016 defers — SQLite per the phase scope; the swap is one constructor call), parallel/concurrent node execution (Phase 9 with Temporal owns concurrency; Phase 6 is sequential).

---

## Conventions honored

- **No LLM in the gather or graph pipeline (ADR-0005).** The graph topology, edge predicates, supervisor routing, retry decisions, and HITL escalation are *all* deterministic. LLM appears at one node only (`llm_replan`), which delegates to Phase 4's `FallbackTier.run` — Phase 6 does not import `anthropic` directly. The fence CI policy extends to `graph/`: deny `anthropic`, `chromadb`, `sentence-transformers`.
- **Facts, not judgments (ADR-0008).** Every conditional-edge predicate reads booleans and counters from the state ledger that were written by Phase 5's signal collectors. No node infers "should we retry?" — the predicate is `retry_count < max_attempts and last_outcome.retryable`.
- **Extension by addition (commitment §2.5, ADR-0007).** Phase 6 adds **one** package (`src/codegenie/graph/`) and **one** ADR-amendable seam on Phase 5 (`GateRunner` is wrapped, not replaced — see Component 2). Phase 5's `GateRunner.run` body is what node functions call; the `for` loop is moved into LangGraph but the *unit of retry semantics* is unchanged. Phase 7 distroless adds a sibling subgraph (`graph/subgraphs/distroless.py`) under the same package, no edits to vuln nodes.
- **Determinism over probabilism (commitment §2.4).** The topology — node set, edge set, edge predicates — is fully declared at module import time. There is no runtime topology mutation, no LLM-decided routing, no agentic next-node choice. The agent has freedom *only inside leaf node implementations*, never at orchestration time.
- **Honest confidence (commitment §2.3).** Every state transition is recorded; every checkpoint is queryable by `workflow_id`. The state ledger carries `provenance` on every signal. `langgraph-cli` renders the graph from the same code paths CI uses; the rendered SVG is committed and diffed.
- **Humans always merge (ADR-0009).** Phase 6's `interrupt()` is **not** a merge gate (Phase 11 owns PR open + merge). Phase 6's `interrupt()` fires only on retry exhaustion or on a non-retryable signal that requires human triage. The resume contract carries a typed `HumanDecision` Pydantic model: `approve_continue`, `approve_override`, `abort`. No prose blobs.
- **Reversibility (Phase 9 envelope coming).** Every node function is `(state: VulnLedger) -> VulnLedger` — pure-ish (file-system side effects allowed; no network). This is exactly what a Temporal Activity wants. The SQLite checkpointer is one line of construction; swapping for `PostgresSaver` is a Phase-9 config change. State must be JSON-serializable (Pydantic's `model_dump_json` is the contract).
- **Progressive disclosure (commitment §2.7).** The `VulnLedger` indexes evidence; it does not inline logs. `evidence_paths: dict[str, Path]` on each gate attempt. The checkpointer stores the ledger; logs stay on disk under `.codegenie/`.
- **Idiomatic LangGraph.** `StateGraph[VulnLedger]`, `add_node`, `add_conditional_edges`, `interrupt()`, `aiosqlite`-backed `AsyncSqliteSaver`. The library, not against it.

---

## Goals (concrete, measurable)

Phase 6 ships **one** package (`graph/`) and amends **no** Phase 0–5 source. The Phase 5 `GateRunner.run` body becomes the node-internal call shape; the `for` loop is the graph.

| # | Goal | Target |
|---|---|---|
| 1 | **Per-node test coverage target** | ≥ 95% line / 90% branch on every node module. Conditional-edge predicates: 100% branch (every truthy/falsy combination asserted). |
| 2 | **Cyclomatic complexity ceiling per node** | McCabe ≤ 6 per node function; ruff `C901` enforced at threshold 7. The supervisor router is the function most at risk (still trivial in Phase 6 because the intent space is one task class). |
| 3 | **Strict-mypy + ruff lint clean** | yes. `mypy --strict` over `src/codegenie/graph/`; no `Any`, no `cast`, no `# type: ignore` without a one-line justification comment. |
| 4 | **New-developer onboarding target** (read README → run first state-transition test) | ≤ 30 minutes. The README has one quickstart: `pytest tests/graph/test_node_transitions.py::test_recipe_pass_short_circuits_to_handoff`. |
| 5 | **Coupling metric — nodes importing other nodes directly** | 0. Fence CI rule: `graph/nodes/*.py` may not `from codegenie.graph.nodes` (only `from codegenie.graph.state import …`). |
| 6 | **Public surface introduced** | 1 Pydantic state model (`VulnLedger`), 1 Protocol (`NodeFn = Callable[[VulnLedger], VulnLedger]` — really just a typing alias, not a class), 1 Pydantic family for HITL (`HumanRequest`, `HumanDecision`), 1 compiled graph (`build_vuln_graph()`), 1 CLI entry (`codegenie graph inspect`). No new ABCs in Phase 6 (ADR-0022 — premature abstraction). |
| 7 | **New top-level packages** | 1 — `src/codegenie/graph/`. Sibling to `transforms/`, `recipes/`, `rag/`, `llm/`, `sandbox/`, `gates/`. |
| 8 | **New Python files in `src/`** | ~14 modules, ~1200 LOC target, 1800 hard ceiling. The graph is **not** a place where new abstractions are minted; it composes existing ones. |
| 9 | **Test code ratio** | ≥ 1.8× source LOC (~2200–3300 LOC). Graph tests are cheap to write and high-value; we err on more. |
| 10 | **State-transition tests: every conditional edge fires at least once** | 100% conditional-edge coverage as a CI gate. The test is a parametrized `pytest` that walks a manually-curated table of `(state_fixture, expected_next_node)` pairs; the table is asserted complete by introspecting the compiled graph and listing edges it didn't cover. |
| 11 | **Replay tests (kill + resume) — same final state** | At least one replay test per major branch (recipe path, recipe-miss → RAG path, RAG-miss → LLM-fallback path, retry path, escalate path). Each test: build graph, run partially, kill, rehydrate from checkpoint, run to completion, assert ledger byte-equal to a non-killed run. |
| 12 | **HITL interrupt tests** | At least 3 — `approve_continue` resumes correctly, `approve_override` adjusts state and resumes, `abort` writes final state and exits. Mocked human responses are dict literals injected via `graph.update_state(...)`. |
| 13 | **Golden-graph snapshot test** | `tests/graph/test_topology_golden.py` exports the compiled graph as a deterministic JSON description (`graph.get_graph().to_json()`) and diffs against `tests/golden/vuln_graph.json`. Any node add/remove/rename or edge change fails the test unless the golden is updated in the same PR. |
| 14 | **Checkpointer backend (Phase 6)** | `AsyncSqliteSaver` with `aiosqlite` per the phase scope. Construction is one helper (`build_checkpointer(path: Path)`). Swapping for `PostgresSaver` in Phase 9 is one helper edit. `InMemorySaver` is used for unit tests; SQLite for replay and HITL tests. |
| 15 | **State model versioning** | `VulnLedger.schema_version: Literal["v0.6.0"]`. Migration policy in §State ledger. |
| 16 | **Tokens per run** | 0 inside Phase 6's package boundary. Phase 4 token cost (when `llm_replan` invokes `FallbackTier.run`) is the responsibility of Phase 4's `LlmInvocationGuard`. Phase 6 emits `cost.graph.run` cumulative ledger entries (wall-clock per node, checkpoint write count) for Phase 13. |
| 17 | **Exit-criterion coverage** | (a) Vuln loop runs as LangGraph state machine — covered by an E2E test that runs `build_vuln_graph().ainvoke(initial_state, config={"configurable": {"thread_id": ...}})` end-to-end on a fixture repo. (b) Mid-run kill + resume — covered by a replay test that uses `os.kill` on a subprocess running the graph at a checkpoint boundary. (c) HITL on two-consecutive-gate-failures + mocked approval — covered by an interrupt test that scripts the Phase 5 `GateRunner` to fail twice in a row then succeed after override. |
| 18 | **`langgraph-cli` graph inspection** | `codegenie graph render --out docs/phases/06-sherpa-state-machine/vuln-graph.svg` and a CI job that re-renders and diff-checks the committed SVG. The compiled graph is what humans read. |

---

## Architecture

```
                  codegenie remediate <repo> --cve <id>
                                  │
                                  ▼
              ┌──────────────────────────────────────────┐
              │  src/codegenie/cli/remediate.py           │   [P6 EDIT, ADR-P6-001]
              │   (was: call RemediationOrchestrator)     │
              │   (now: build_vuln_graph().ainvoke(...))  │
              └──────────────────┬───────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  src/codegenie/graph/builder.py — build_vuln_graph()          │
        │                                                              │
        │  StateGraph[VulnLedger]                                       │
        │      .add_node("ingest_cve",      ingest_cve)                 │
        │      .add_node("select_recipe",   select_recipe)              │
        │      .add_node("apply_recipe",    apply_recipe)               │
        │      .add_node("rag_lookup",      rag_lookup)                 │
        │      .add_node("llm_replan",      llm_replan)                 │
        │      .add_node("run_gate",        run_gate)                   │
        │      .add_node("record_attempt",  record_attempt)             │
        │      .add_node("await_human",     await_human)   # interrupt  │
        │      .add_node("emit_artifact",   emit_artifact)              │
        │      .add_node("escalate",        escalate)                   │
        │                                                              │
        │  Edges (every cond. edge is a pure fn of VulnLedger):         │
        │     START          → ingest_cve                               │
        │     ingest_cve     → select_recipe                            │
        │     select_recipe  → {matched: apply_recipe,                  │
        │                       miss:    rag_lookup}                    │
        │     apply_recipe   → run_gate                                 │
        │     rag_lookup     → {hit: apply_recipe,                      │
        │                       miss: llm_replan}                       │
        │     llm_replan     → run_gate                                 │
        │     run_gate       → record_attempt                           │
        │     record_attempt → {passed:           emit_artifact,        │
        │                       retryable_left:   <prior-engine>,       │
        │                       retry_exhausted:  await_human,          │
        │                       non_retryable:    await_human}          │
        │     await_human    → {continue:  <prior-engine>,              │
        │                       override:  emit_artifact,               │
        │                       abort:     escalate}                    │
        │     emit_artifact  → END                                      │
        │     escalate       → END                                      │
        │                                                              │
        │  Checkpointer: AsyncSqliteSaver(path)                         │
        │  Interrupt-before: ["await_human"]                            │
        └──────────────────┬───────────────────────────────────────────┘
                           │
                           ▼ (every node, no exceptions)
        ┌──────────────────────────────────────────────────────────────┐
        │  VulnLedger (Pydantic, frozen+extra=forbid, JSON-serializable)│
        │                                                              │
        │  ── identity ──                                              │
        │     workflow_id, thread_id, schema_version                   │
        │     repo_path, advisory: AdvisoryRef                         │
        │                                                              │
        │  ── routing ──                                               │
        │     last_engine: Literal["recipe","rag","llm",None]          │
        │     last_node:   str                                         │
        │                                                              │
        │  ── work-in-progress ──                                      │
        │     recipe_selection: RecipeSelection | None  # from Phase 3 │
        │     rag_hit:          RagHit | None           # from Phase 4 │
        │     patch:            PatchRef | None         # path + hash  │
        │     prior_attempts:   list[AttemptSummary]    # from Phase 5 │
        │                                                              │
        │  ── gate outcome ──                                          │
        │     last_outcome: GateOutcome | None  # Phase 5 model        │
        │     retry_count:  int                  # how many tries      │
        │                                                              │
        │  ── HITL ──                                                  │
        │     human_request:  HumanRequest | None                      │
        │     human_decision: HumanDecision | None                     │
        │                                                              │
        │  ── audit ──                                                 │
        │     chain_head: bytes                  # extends Phase 5     │
        │     events:     list[GraphEvent]       # node entry/exit     │
        └──────────────────────────────────────────────────────────────┘

  Package layout (one addition on top of Phase 5):
  src/codegenie/
    graph/                    ← NEW
      __init__.py
      builder.py              ← build_vuln_graph() — declarative topology
      state.py                ← VulnLedger, HumanRequest, HumanDecision,
                              ←   GraphEvent, AttemptSummary (re-export)
      events.py               ← GraphEvent + emit_event helper
      checkpointer.py         ← build_checkpointer(path) -> AsyncSqliteSaver
      edges.py                ← every conditional-edge predicate, pure fns
      nodes/
        __init__.py
        ingest_cve.py         ← thin wrapper over Phase 3 CVE feed reader
        select_recipe.py      ← thin wrapper over Phase 3 selector
        apply_recipe.py       ← thin wrapper over Phase 3 RecipeEngine
        rag_lookup.py         ← thin wrapper over Phase 4 RagTier
        llm_replan.py         ← thin wrapper over Phase 4 FallbackTier
        run_gate.py           ← thin wrapper over Phase 5 GateRunner.run-one
        record_attempt.py     ← writes Phase 5 RetryLedger entry
        await_human.py        ← interrupt() + typed resume contract
        emit_artifact.py      ← writes RemediationReport (Phase 3 shape)
        escalate.py           ← writes audit-event, sets exit code
    cli/
      graph.py                ← codegenie graph {render,inspect,replay}

  Fence policy CI updates:
    graph/                    may NOT import anthropic|chromadb|sentence-transformers
    graph/                    MAY  import langgraph, langgraph-cli
    graph/nodes/*.py          may NOT import codegenie.graph.nodes (sibling fence)
    graph/edges.py            may NOT import codegenie.graph.nodes
    cli/graph.py              may import codegenie.graph

  Phase 0–5 source code: unchanged. The cli/remediate.py edit is the
  only Phase-0–5 touch, and it is a one-line dispatcher swap captured by
  ADR-P6-001.
```

Import direction is strictly downward: `cli/` → `graph/` → (`graph/nodes/` || `graph/edges.py`) → (`graph/state.py` || existing Phase 3–5 modules). No node imports another node. No predicate imports a node. `state.py` imports only Pydantic + Phase 3–5 typed models.

---

## Module layout

The concrete file tree under the existing repo:

```
src/codegenie/graph/
├── __init__.py              # exports: build_vuln_graph, VulnLedger,
│                            #          HumanRequest, HumanDecision
├── builder.py               # ~150 LOC — declarative graph wiring;
│                            # no business logic, only StateGraph calls
├── state.py                 # ~200 LOC — VulnLedger + helper Pydantic models;
│                            # imports Phase 3 RecipeSelection, Phase 4 RagHit,
│                            # Phase 5 AttemptSummary, GateOutcome
├── events.py                # ~80  LOC — GraphEvent enum + emit helper
├── checkpointer.py          # ~50  LOC — build_checkpointer() factory
├── edges.py                 # ~120 LOC — every conditional predicate, each
│                            # ≤ 6 lines, each a pure (state) -> str
└── nodes/
    ├── __init__.py
    ├── ingest_cve.py        # ~60  LOC
    ├── select_recipe.py     # ~50  LOC
    ├── apply_recipe.py      # ~70  LOC
    ├── rag_lookup.py        # ~60  LOC
    ├── llm_replan.py        # ~80  LOC
    ├── run_gate.py          # ~80  LOC
    ├── record_attempt.py    # ~70  LOC
    ├── await_human.py       # ~60  LOC — the only file that calls interrupt()
    ├── emit_artifact.py     # ~70  LOC
    └── escalate.py          # ~60  LOC

src/codegenie/cli/
├── graph.py                 # ~120 LOC — render / inspect / replay subcommands

tests/graph/
├── __init__.py
├── conftest.py              # state fixture factories; in-memory + sqlite saver
├── test_state.py            # VulnLedger schema invariants, JSON round-trip
├── test_edges.py            # every predicate, parametrized
├── test_node_transitions.py # the workhorse — every conditional edge fires
├── test_nodes/
│   ├── test_ingest_cve.py
│   ├── test_select_recipe.py
│   ├── test_apply_recipe.py
│   ├── test_rag_lookup.py
│   ├── test_llm_replan.py   # uses Phase 4 VCR cassettes
│   ├── test_run_gate.py     # mocks Phase 5 SandboxClient
│   ├── test_record_attempt.py
│   ├── test_await_human.py
│   ├── test_emit_artifact.py
│   └── test_escalate.py
├── test_replay.py           # kill + resume; SQLite-backed
├── test_hitl.py             # interrupt + mocked decisions
├── test_topology_golden.py  # golden-graph diff
└── test_e2e_vuln_loop.py    # one full end-to-end; uses Phase 3 fixture repo

tests/golden/
└── vuln_graph.json          # the topology snapshot
```

---

## Components

### 1. `VulnLedger` — the state ledger

- **Provenance:** [B]
- **Purpose:** The single Pydantic-typed contract every node reads from and writes to. The checkpointer serializes this and only this. ADR-0002's "all state ledgers are typed Pydantic models — no `dict[str, Any]`" is enforced here.
- **Interface:**
  ```python
  class VulnLedger(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=False)
      # frozen=False intentional: LangGraph applies node-returned updates by
      # constructing a new instance; the model_copy + validate path is what
      # makes "every transition produces a fresh, validated state" cheap.
      # Mutation is forbidden by code review + a CI test that asserts no
      # node module performs in-place attribute assignment on a VulnLedger.

      schema_version: Literal["v0.6.0"]

      # identity
      workflow_id: str           # uuid7
      thread_id: str             # LangGraph thread id, same as workflow_id
      repo_path: Path
      advisory: AdvisoryRef      # Phase 3 type

      # routing
      last_engine: Literal["recipe", "rag", "llm"] | None = None
      last_node: str = "START"

      # work in progress
      recipe_selection: RecipeSelection | None = None  # Phase 3 type
      rag_hit: RagHit | None = None                    # Phase 4 type
      patch: PatchRef | None = None
      prior_attempts: list[AttemptSummary] = Field(default_factory=list)
                                                       # Phase 5 type

      # gate outcome
      last_outcome: GateOutcome | None = None          # Phase 5 type
      retry_count: int = 0
      max_attempts: int = 3                            # ADR-0014 default

      # HITL
      human_request: HumanRequest | None = None
      human_decision: HumanDecision | None = None

      # audit
      chain_head: bytes                                # extends Phase 5 chain
      events: list[GraphEvent] = Field(default_factory=list)
  ```
- **Internal design:**
  - `extra="forbid"` — typos in node updates fail loudly, not silently.
  - All sub-models are reused from Phase 3/4/5 (`RecipeSelection`, `RagHit`, `AttemptSummary`, `GateOutcome`, `AdvisoryRef`). Phase 6 mints **no** new domain types beyond the HITL pair, the event enum, and the ledger itself.
  - `chain_head: bytes` is initialized from Phase 5's `RetryLedger.head()` at graph entry. Every checkpoint write extends the chain (Phase 5's `RetryLedger.record` is the chokepoint).
  - JSON-serializable end-to-end (`Path → str`, `bytes → base64`, `datetime → ISO 8601`). Validated by a property-based test that round-trips arbitrary `VulnLedger` instances through `model_dump_json` → `model_validate_json` and asserts equality.
- **Tradeoffs accepted:**
  - One large Pydantic model rather than a hierarchy. Justified because every node already needs to *read* fields owned by other nodes (the retry counter is read by `edges.py`; the recipe selection is read by `apply_recipe`). A nested namespace adds boilerplate without buying isolation; ADR-0022 says do not abstract prematurely.
  - `frozen=False` so LangGraph's update merging works idiomatically. The "no in-place mutation" rule is enforced by AST lint, not by Pydantic.

### 2. The node function contract

- **Provenance:** [B]
- **Purpose:** Single canonical shape for every node so testing, registration, and topology declaration are uniform.
- **Interface:**
  ```python
  NodeFn = Callable[[VulnLedger], VulnLedger]

  # Convention (enforced by ruff + a CI introspection test):
  # 1. Module name == node name (e.g., `apply_recipe` lives in apply_recipe.py).
  # 2. The module exports exactly one public callable, also named `apply_recipe`.
  # 3. The callable signature is `(state: VulnLedger) -> VulnLedger`.
  # 4. The function body MUST end with `return state.model_copy(update={...})`.
  #    (CI lint asserts every node function returns via model_copy.)
  # 5. The function MUST NOT import any other `graph.nodes.*` module.
  ```
- **Internal design:**
  - Async LangGraph nodes are allowed (`async def apply_recipe(...) -> VulnLedger`), but every node in Phase 6 is sync — the underlying Phase 3/4/5 engines are sync, and Phase 9's Temporal envelope will wrap them. Mixing sync and async nodes in the same graph is supported by LangGraph but creates a stack-jumping debugging trap; we keep everything sync in Phase 6.
  - Each node module is unit-testable in isolation: construct a `VulnLedger` fixture, call the function, assert the returned ledger's fields. No graph required; no checkpointer required.
  - Side effects allowed: file-system writes under `.codegenie/` (logs, signal JSON, ledger snapshots) and stdout (via the structured logger). **Not allowed:** network I/O directly from a node (must go through a Phase 5 SandboxClient or Phase 4 LLM client), in-place mutation of input state, mutation of another node's output state, calling another node function.
- **Why this choice over the alternatives:**
  - **Class-per-node (ABC + concrete subclasses):** rejected. ADR-0022 (Three Strikes) says no shared structure until the third concrete subgraph. Adds inheritance hierarchy for zero current benefit; testing a class wrapping a single function is a worse experience than testing the function.
  - **Dict-state with TypedDict:** rejected. ADR-0002 explicitly forbids `dict[str, Any]` style. Pydantic is the contract.
  - **Decorator-based registration (`@register_node`):** rejected for Phase 6. The topology is declared in *one* file (`builder.py`) — central, readable, diff-friendly. A registry decorator hides the topology from the reader; for a Phase-6-sized graph (10 nodes) that's a strict loss. Re-evaluate at strike-three (Phase 15).
- **Tradeoffs accepted:**
  - The "no node imports another node" rule must be enforced by lint, not by Python. We accept the cost of one AST-based ruff check (or a tiny custom flake8 plugin) that walks `graph/nodes/*.py` import statements.

### 3. The conditional-edge predicate contract

- **Provenance:** [B]
- **Purpose:** Make routing decisions inspectable, testable, and obviously correct.
- **Interface:** All predicates live in `graph/edges.py`:
  ```python
  def route_select_recipe(state: VulnLedger) -> Literal["matched", "miss"]:
      assert state.recipe_selection is not None  # Phase 3 invariant
      return "matched" if state.recipe_selection.recipe is not None else "miss"

  def route_rag_lookup(state: VulnLedger) -> Literal["hit", "miss"]:
      return "hit" if state.rag_hit is not None and state.rag_hit.score >= 0.85 else "miss"

  def route_after_attempt(state: VulnLedger) -> Literal[
      "passed", "retryable_recipe", "retryable_rag", "retryable_llm",
      "retry_exhausted", "non_retryable"
  ]:
      assert state.last_outcome is not None
      if state.last_outcome.passed:
          return "passed"
      if not state.last_outcome.retryable:
          return "non_retryable"
      if state.retry_count >= state.max_attempts:
          return "retry_exhausted"
      # route back to the same engine that produced this attempt
      return f"retryable_{state.last_engine}"  # type: ignore[return-value]

  def route_human_decision(state: VulnLedger) -> Literal["continue", "override", "abort"]:
      assert state.human_decision is not None
      return state.human_decision.action
  ```
- **Internal design:**
  - Every predicate is `(VulnLedger) -> str-literal`. Pure. No side effects. ≤ 6 lines. McCabe ≤ 3.
  - The router that loops back to the prior engine reads `state.last_engine`; this is what makes the three-retry loop expressible without a `for` loop in node code (the *graph cycle* is the loop).
  - The `retry_count` increment lives in `record_attempt.py` — exactly one place. Predicates *read* it, they do not write it.
  - The threshold for RAG hit (`>= 0.85`) is read from a YAML config (`tools/policy/graph-thresholds.yaml`) at graph build time and bound into a default arg — not Phase 6's calibration to set, but Phase 6's responsibility to surface as data not magic.
- **Why this choice over the alternatives:**
  - **Predicate-as-method-on-state (`state.next_after_attempt()`):** rejected. Couples routing logic to the state model. Hard to mock; hard to vary across subgraphs. Pure functions over state are the SHERPA-disciplined shape.
  - **Conditional logic inside nodes (node returns a tuple `(state, next_node_name)`):** rejected. LangGraph's `add_conditional_edges` is *the* idiomatic primitive for this; sidestepping it forfeits the graph visualization, the checkpointer's edge tracking, and `langgraph-cli` inspection.
- **Tradeoffs accepted:** Adding a new branch is two diffs (predicate + `add_conditional_edges` call in `builder.py`). The golden-graph test forces both changes in one PR — which is good.

### 4. `build_vuln_graph()` — declarative topology

- **Provenance:** [B]
- **Purpose:** The single source of truth for what the vuln state machine *is*. Builder.py exports one function; everything else in the package is imported by it.
- **Interface:**
  ```python
  def build_vuln_graph(
      *,
      checkpointer: BaseCheckpointSaver | None = None,
      max_attempts: int = 3,
  ) -> CompiledGraph:
      g = StateGraph(VulnLedger)
      g.add_node("ingest_cve",      ingest_cve)
      g.add_node("select_recipe",   select_recipe)
      # ... (all 10 nodes)
      g.set_entry_point("ingest_cve")
      g.add_edge("ingest_cve",   "select_recipe")
      g.add_conditional_edges("select_recipe", route_select_recipe, {
          "matched": "apply_recipe",
          "miss":    "rag_lookup",
      })
      # ... (every edge declared explicitly)
      g.add_conditional_edges("record_attempt", route_after_attempt, {
          "passed":             "emit_artifact",
          "retryable_recipe":   "apply_recipe",
          "retryable_rag":      "rag_lookup",
          "retryable_llm":      "llm_replan",
          "retry_exhausted":    "await_human",
          "non_retryable":      "await_human",
      })
      g.add_edge("emit_artifact", END)
      g.add_edge("escalate",      END)
      return g.compile(
          checkpointer=checkpointer or InMemorySaver(),
          interrupt_before=["await_human"],
      )
  ```
- **Internal design:** No dynamic node injection; no conditional `add_node` based on flags. The topology is *the same* across dev, test, and prod. The only varying input is the checkpointer.
- **Why this choice over the alternatives:**
  - **Topology as YAML data + a loader:** rejected for Phase 6. The topology is small enough that prose-readable Python is clearer than YAML-then-loader. Reconsider when there are 30+ nodes (Phase 12+).
  - **Topology as decorator-registered fragments:** rejected for the same reason as decorator-registered nodes. Centralize.
- **Tradeoffs accepted:** Adding a node is a two-diff PR (node module + builder edit). The golden-graph test enforces consistency between the two.

### 5. `await_human` — the only `interrupt()` site

- **Provenance:** [B]
- **Purpose:** Implement HITL with one canonical resume contract. `interrupt()` is called from *one* place; the contract is *one* Pydantic model.
- **Interface:**
  ```python
  class HumanRequest(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      reason: Literal["retry_exhausted", "non_retryable_signal"]
      summary: str               # ≤ 4 KB sanitized
      evidence_paths: dict[str, Path]
      failing_signals: list[str]

  class HumanDecision(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      action: Literal["continue", "override", "abort"]
      operator: str
      decided_at: datetime
      note: str = ""             # ≤ 1 KB free-text justification
      # "continue" → retry from the same engine, retry_count reset to 0
      # "override" → mark patch as accepted, skip remaining gates, go to handoff
      # "abort"    → write final state, escalate

  async def await_human(state: VulnLedger) -> VulnLedger:
      request = build_request(state)  # pure
      state = state.model_copy(update={"human_request": request})
      decision = interrupt(request.model_dump())   # LangGraph primitive
      validated = HumanDecision.model_validate(decision)
      return apply_decision(state, validated)      # pure
  ```
- **Internal design:**
  - `interrupt()` is called exactly once in this codebase. Every other "wait for human" need routes here.
  - The compiled graph uses `interrupt_before=["await_human"]` so LangGraph pauses *before* entering the node — checkpointer write happens, the workflow can be killed, and resume re-enters this node with the injected decision visible via `Command(resume=...)` or `graph.update_state(...)`.
  - On resume, `HumanDecision.model_validate(decision)` rejects malformed payloads loudly. The fuzz-test ensures malformed dicts produce `ValidationError`, not silent behavior.
  - `apply_decision` is a pure function: it does not call `interrupt()`, does not re-enter the graph, does not mutate disk. The next conditional edge (`route_human_decision`) handles routing.
- **Why this choice over the alternatives:**
  - **Multiple interrupt sites:** rejected. Each new interrupt site is a new resume contract for tests and operators to learn. One site + one Pydantic model is the lowest-cost discipline.
  - **Use LangGraph's `breakpoints` instead of `interrupt()`:** rejected. Breakpoints are for debugging; `interrupt()` is the durable HITL primitive. Phase 9's Temporal envelope will signal-on-resume; the `interrupt()` shape is what survives.

### 6. Checkpointer wrapper

- **Provenance:** [B]
- **Purpose:** Make the SQLite-vs-Postgres choice (ADR-0016) a one-line swap.
- **Interface:**
  ```python
  async def build_checkpointer(
      kind: Literal["memory", "sqlite"] = "sqlite",
      *,
      path: Path | None = None,
  ) -> BaseCheckpointSaver:
      if kind == "memory":
          return InMemorySaver()
      if path is None:
          path = Path(".codegenie/graph/checkpoints.sqlite3")
      path.parent.mkdir(parents=True, exist_ok=True)
      conn = await aiosqlite.connect(str(path))
      return AsyncSqliteSaver(conn)
  ```
- **Internal design:** Tests construct `kind="memory"`. Production constructs `kind="sqlite"`. Phase 9 adds `kind="postgres"` here and edits exactly one file. ADR-P6-002 captures this.
- **Tradeoffs accepted:** SQLite is single-writer; concurrent vuln workflows on the same dev box serialize on the checkpointer file. Acceptable for Phase 6 (developer-laptop scale); Phase 9 fixes with Postgres.

### 7. Graph CLI surface — `codegenie graph`

- **Provenance:** [B]
- **Purpose:** Make the graph inspectable from a terminal without a notebook.
- **Public interface:**
  - `codegenie graph render --out path.svg` — wraps `langgraph-cli`'s renderer; commits an SVG so reviewers can see the topology in a PR diff.
  - `codegenie graph inspect <thread-id>` — pretty-prints the checkpoint history for a thread (uses `graph.get_state_history(config)`).
  - `codegenie graph replay <thread-id> --from <checkpoint-id>` — re-runs the graph from a chosen checkpoint, useful for debugging.
- **Internal design:** `click` subcommand group. No new dependencies beyond `langgraph-cli`.

---

## State ledger

**Pydantic schema sketch.** See Component 1 for the field-by-field model. Key invariants:

- `extra="forbid"` — unknown fields raise. Typos in node updates die at validation time, not at debug time three nodes later.
- All field types are concrete (Phase 3/4/5 Pydantic models or stdlib types). No `Any`. No `dict[str, str | int]` "details bag" — the existing typed sub-models (`RecipeSelection`, `RagHit`, `AttemptSummary`, `GateOutcome`) carry that detail.
- JSON-serializable end-to-end. Tested by a property-based round-trip test.
- `chain_head: bytes` is the extension point onto Phase 2/3/4/5's BLAKE3 audit chain. The chain head at graph entry equals Phase 5's `RetryLedger.head()`; every node's `events` append extends the chain (`hash_extend(prev, event_bytes)`).

**Versioning policy.**

- `schema_version: Literal["v0.6.0"]`. Bumped on any field add/remove/rename or type change.
- New fields land as `Optional` with a default. The Pydantic model accepts old checkpoints (no field for `field_x`) without migration code as long as the default is sensible.
- Field removal or type change → a **migration script** under `src/codegenie/graph/migrations/v0_6_0_to_v0_7_0.py` plus an entry in `MIGRATIONS_REGISTRY` keyed by source version. Migrations run lazily on checkpoint load: if `state.schema_version != CURRENT`, walk the chain of migrations.
- A CI test asserts every committed `tests/fixtures/checkpoints/*.json` (one per shipped schema version) loads cleanly under the current model — catches accidental breakages.

**Migration policy.**

- Phase 6 ships v0.6.0. Phase 7 (distroless extension) is expected to add an optional `distroless_subgraph_state` field on a future shared ledger — but per ADR-0022 (Three Strikes), Phase 7 ships its *own* `DistrolessLedger` rather than widening `VulnLedger`. Phase 6's contract is for the vuln workflow only.
- Migrations are one-way. No downgrade. Backups are the operator's responsibility (the SQLite file is one path).

---

## Node contract

The canonical signature every node implements (also stated in Component 2):

```python
def <node_name>(state: VulnLedger) -> VulnLedger:
    # 1. Read fields owned by upstream nodes (typed; mypy-checked).
    # 2. Invoke the underlying Phase 3/4/5 engine, passing only what's needed.
    # 3. Return `state.model_copy(update={"<owned_field>": <value>, ...})`.
```

**How a node declares the fields it reads vs writes.**

A module-level docstring at the top of every node file enumerates `Reads:` and `Writes:` field names. A CI test parses these docstrings, runs an AST visit over the function body, and asserts:

- Every name in `Reads:` actually appears as a `state.<name>` access in the body.
- Every name in `Writes:` actually appears as a key in the `model_copy(update={...})` literal.
- No `state.<name>` access appears that is not declared in `Reads:`.
- No `update={"<name>": ...}` key appears that is not declared in `Writes:`.

This is the test that closes the "nodes drift in what they actually do vs. what we think they do" loophole. The check is ~80 LOC of `ast` walking; it lives in `tests/graph/test_node_field_contracts.py`.

Example:

```python
"""
apply_recipe — invoke the Phase 3 RecipeEngine on the selected recipe.

Reads: recipe_selection, repo_path, advisory, retry_count, prior_attempts
Writes: patch, last_engine, last_node, events, chain_head
"""

def apply_recipe(state: VulnLedger) -> VulnLedger:
    assert state.recipe_selection is not None
    engine = current_recipe_engine()
    application = engine.apply(
        recipe=state.recipe_selection.recipe,
        repo=state.repo_path,
        prior_attempts=state.prior_attempts,
    )
    return state.model_copy(update={
        "patch": PatchRef(path=application.patch_path, blake3=application.patch_blake3),
        "last_engine": "recipe",
        "last_node": "apply_recipe",
        "events": [*state.events, GraphEvent.node_exit("apply_recipe", at=utcnow())],
        "chain_head": extend_chain(state.chain_head, "apply_recipe", application),
    })
```

**How nodes are registered.**

Centrally, in `builder.py`. No decorator registry. The list of `add_node` calls is the registry. Adding a node is one diff in `builder.py` + one new module under `nodes/`. The golden-graph test asserts the registered set is what the topology snapshot says.

---

## Conditional edges (gates)

**How a gate is expressed in code.** Every Trust-Aware gate in Phase 6 is a *conditional edge* whose predicate reads `state.last_outcome` (the `GateOutcome` Pydantic model produced by Phase 5's `StrictAndGate` — Phase 6 does **not** re-implement gate evaluation; it routes on the verdict that Phase 5 produced).

```python
# graph/edges.py

def route_after_attempt(state: VulnLedger) -> Literal[
    "passed", "retryable_recipe", "retryable_rag", "retryable_llm",
    "retry_exhausted", "non_retryable"
]:
    assert state.last_outcome is not None
    if state.last_outcome.passed:
        return "passed"
    if not state.last_outcome.retryable:
        return "non_retryable"
    if state.retry_count >= state.max_attempts:
        return "retry_exhausted"
    assert state.last_engine is not None
    return f"retryable_{state.last_engine}"  # type: ignore[return-value]
```

**Where the threshold lives.**

- ADR-0015 (trust-score threshold calibration) is **deferred** — Phase 6 is not the right phase to set numerical thresholds. The `StrictAndGate` in Phase 5 already encodes the strict-AND of objective signals (every required signal must pass). Phase 6 reads `last_outcome.passed: bool`. No threshold lives in `graph/`.
- The RAG hit threshold (`score >= 0.85`) is Phase 4's territory; in Phase 6's edges, the threshold is a default arg bound at graph-build time from `tools/policy/graph-thresholds.yaml`. Phase 6 surfaces it as data; Phase 13 collects evidence to calibrate it.

**Where the three-retry counter lives (ADR-0014).**

- `VulnLedger.retry_count: int = 0` — owned in state, single source of truth.
- Incremented in exactly one node: `record_attempt.py`, on every non-passed attempt:
  ```python
  return state.model_copy(update={
      "retry_count": state.retry_count + 1 if not outcome.passed else state.retry_count,
      ...
  })
  ```
- On a "passed" outcome, the counter is **not** reset (it represents lifetime attempts on this workflow, useful for analytics). On HITL "continue" (a human-blessed retry), the counter *is* reset to 0 — but that reset happens in `await_human.apply_decision`, not in `record_attempt`. Two writers total; both unit-tested.
- `route_after_attempt` reads `state.retry_count` and `state.max_attempts`. `max_attempts` defaults to 3 (ADR-0014); per-gate override via the YAML catalog already exists in Phase 5 — Phase 6 plumbs it into `VulnLedger.max_attempts` at graph entry, not at every transition.

---

## HITL interrupt / resume

**The contract.** See Component 5 — one `await_human` node, two Pydantic models (`HumanRequest`, `HumanDecision`).

**How a developer writes an interrupt point.** They don't. If a new node thinks it needs human input, the answer is: route to `await_human` via a conditional edge, and add a new `reason` enum value to `HumanRequest.reason: Literal[...]`. Centralization is the discipline. ADR-P6-003 captures this.

**The flow.**

1. Some node (`record_attempt`) detects a state that requires human review (retry exhausted, non-retryable signal). It does **not** call `interrupt()` itself — it just sets the relevant fields and returns. The conditional edge `route_after_attempt` then routes to `await_human`.
2. LangGraph (configured with `interrupt_before=["await_human"]`) pauses *before* executing `await_human`. The checkpointer persists `VulnLedger` to disk.
3. The CLI exits with a documented code (`exit 12 = graph_awaits_human`) and prints the thread ID + the resume command (`codegenie graph resume <thread-id>`).
4. The operator (in a future Phase 11 UI; in Phase 6, via CLI) inspects the state, decides, and calls `codegenie graph resume <thread-id> --decision '{"action": "continue", "operator": "alice", ...}'`.
5. The resume injects the decision into the next graph step: `graph.ainvoke(None, config, ..., resume_value=decision)`. `await_human` reads it via `interrupt(request.model_dump())`'s return value, validates it as `HumanDecision`, sets `state.human_decision`, and returns.
6. `route_human_decision` routes based on `decision.action`.

**How tests inject a mocked response.**

```python
async def test_hitl_continue_resumes_into_llm_replan(
    sqlite_checkpointer, vuln_fixture, monkeypatch
):
    graph = build_vuln_graph(checkpointer=sqlite_checkpointer)
    config = {"configurable": {"thread_id": "t-1"}}

    # Force gate to fail twice in a row.
    monkeypatch.setattr(run_gate_module, "GATE_OUTCOMES",
                        deque([failing_outcome, failing_outcome]))

    # First invocation runs until interrupt_before=["await_human"].
    await graph.ainvoke(initial_state(vuln_fixture), config=config)

    # Inject a mocked human decision.
    decision = HumanDecision(action="continue", operator="test",
                             decided_at=utcnow(), note="please retry")
    await graph.aupdate_state(
        config, {"human_decision": decision}, as_node="await_human"
    )

    # Resume; assert it routes back to llm_replan and ultimately succeeds.
    monkeypatch.setattr(run_gate_module, "GATE_OUTCOMES",
                        deque([passing_outcome]))
    final = await graph.ainvoke(None, config=config)
    assert final["last_outcome"].passed
    assert "llm_replan" in [e.node for e in final["events"]]
```

The injection path uses LangGraph's idiomatic `update_state(..., as_node="await_human")` — no monkey-patching of `interrupt()` itself. This is what the LangGraph docs intend.

---

## Test plan

A wide-base pyramid: many fast unit tests, fewer integration tests, very few E2E.

### Layer 0 — Static checks (CI gate, ~5 s)

- `mypy --strict src/codegenie/graph/` — zero errors.
- `ruff check src/codegenie/graph/ tests/graph/` — clean.
- `tests/graph/test_node_field_contracts.py` — AST walk asserting docstring `Reads:`/`Writes:` match function bodies for every node.
- `tests/graph/test_no_cross_node_imports.py` — AST walk asserting `graph/nodes/*.py` does not import from `graph.nodes`.
- `tests/graph/test_topology_golden.py` — `graph.get_graph().to_json()` matches `tests/golden/vuln_graph.json` byte-for-byte after deterministic key sort.

### Layer 1 — Unit tests, no graph (~60% of test LOC, ~3 s)

- `tests/graph/test_state.py` — `VulnLedger` schema invariants, `extra="forbid"` rejection, JSON round-trip property test (Hypothesis), `model_copy` immutability check.
- `tests/graph/test_edges.py` — every predicate, parametrized over a table of `(VulnLedger fixture, expected literal)`. Achieves 100% branch coverage on `edges.py`. The table is asserted complete by introspecting each `Literal[...]` return type and confirming every literal value appears in the expected column.
- `tests/graph/test_nodes/test_<node>.py` — one file per node. Each constructs an input `VulnLedger`, invokes the node function, asserts the returned ledger's fields. Phase 3/4/5 engines are mocked at the import boundary (e.g., `test_apply_recipe.py` mocks `current_recipe_engine()`).

### Layer 2 — State-transition tests, in-memory checkpointer (~20% of test LOC, ~8 s)

- `tests/graph/test_node_transitions.py` — **the goal-11 workhorse.** Parametrized over a curated table of `(start-state-fixture, scripted-engine-outcomes, expected-node-sequence)`. Every conditional edge appears in at least one row. The introspection assertion: the test fixtures' union of fired edges == the set of edges in the compiled graph.
  - Sample rows: recipe-pass-short-circuit (`ingest_cve → select_recipe[matched] → apply_recipe → run_gate → record_attempt[passed] → emit_artifact → END`); recipe-miss-then-rag-hit-then-pass; recipe-miss-then-rag-miss-then-llm-then-fail-then-llm-then-pass; recipe-pass-then-non-retryable-signal-then-human-abort; retry-exhausted-then-human-continue-then-pass; retry-exhausted-then-human-override-then-handoff.

### Layer 3 — Replay tests, SQLite checkpointer (~5% of test LOC, ~30 s)

- `tests/graph/test_replay.py` — for each major branch (recipe path, RAG path, LLM path, retry path, HITL path): build graph with `AsyncSqliteSaver`, run partway (cancel via `asyncio.wait_for` timeout at a known checkpoint boundary), reconstruct the graph from the same SQLite path, run to completion, assert the final `VulnLedger` is **byte-equal** to a non-killed reference run (`reference.model_dump_json() == replayed.model_dump_json()`).
- One test uses `multiprocessing` to kill a subprocess running the graph at a known node boundary, then rehydrates in the parent process — exercises the actual durability story, not just an in-process cancel.

### Layer 4 — HITL tests, SQLite checkpointer (~5% of test LOC, ~10 s)

- `tests/graph/test_hitl.py`:
  - `test_hitl_continue_resumes_correctly` — gate fails twice, human approves continue, third gate passes, final state shows successful artifact.
  - `test_hitl_override_jumps_to_handoff` — gate fails twice, human approves override, graph emits artifact without further gate attempts.
  - `test_hitl_abort_writes_final_escalate_state` — gate fails twice, human aborts, `escalate` node runs, exit code is the documented escalate code.
  - `test_hitl_malformed_decision_raises` — `update_state` with a malformed decision dict, assert `ValidationError` at `HumanDecision.model_validate`.
  - `test_hitl_interrupt_persists_across_process_restart` — combines HITL with replay; runs in subprocess, kills it at `interrupt_before` checkpoint, resumes in a new process.

### Layer 5 — End-to-end (~1 test, ~60 s)

- `tests/graph/test_e2e_vuln_loop.py` — uses a Phase 3 fixture Node.js repo with a known CVE, real Phase 3 selector + recipe engine, real Phase 4 RAG (mocked LLM via VCR), real Phase 5 `GateRunner` (in-process; `SandboxClient` mocked to a fake that runs `npm ci` directly). Asserts the workflow reaches `emit_artifact` and the produced `RemediationReport` matches Phase 3's expected shape. Marked `@pytest.mark.slow`; CI runs it on PR + nightly.

### Layer 6 — Golden graph (CI gate, ~1 s)

- `tests/graph/test_topology_golden.py` — already mentioned, lives at Layer 0 because of speed. Also worth listing here as a *visual* test: `codegenie graph render --out tests/golden/vuln_graph.svg` is run in CI and the SVG bytes are diffed. SVG drift fails the build; updating the golden is a deliberate PR step.

---

## Risks (top 3–5)

1. **State-model bloat across phases.** Phase 6 lands `VulnLedger`; Phase 7 will be tempted to widen it for distroless; Phase 8 will be tempted to add planner fields. The "extension by addition" commitment says no — each task class gets its own ledger. Mitigation: ADR-P6-004 ("VulnLedger is task-class-scoped; new task classes ship new ledgers") + Phase 7's design review asserts no widening of `VulnLedger`. **Severity: medium.** **Reversal cost: high** if we let it bloat — the migration story becomes painful.
2. **LangGraph idiom drift.** The library is moving fast; APIs we use today (`interrupt()`, `add_conditional_edges`, `aupdate_state(..., as_node=...)`) may evolve. Phase 6's design pins `langgraph` to a known-good minor version and treats version bumps as ADR-amendable. The golden-graph test catches behavioral surprises; the contract tests on `interrupt()` resume catch protocol drift. Mitigation: a single internal `_compat.py` module under `graph/` is allowed to wrap the few `langgraph` APIs we depend on so a future major-version bump is one file's diff. **Severity: medium.**
3. **The "nodes never call nodes" rule is enforced by lint, not by the runtime.** A determined or unaware contributor could violate it; the lint catches it at PR time. Mitigation: the lint is on the pre-commit hook + CI; the rule is in the README + every node module's docstring template; PR reviewers are trained on it (Phase 0 README addition). **Severity: low** with mitigations in place.
4. **SQLite single-writer concurrency.** Two `codegenie remediate` invocations on the same dev box hitting the same checkpoint file will serialize, and under high contention may yield `database is locked` errors. Phase 6 documents this as a known limitation; Phase 9 (Postgres) is the structural fix. Mitigation: per-workflow checkpoint files in dev (`.codegenie/graph/checkpoints/<workflow_id>.sqlite3`) so concurrent workflows don't contend; the single-file path is for production-shape testing only. **Severity: low** for Phase 6's scope.
5. **The `interrupt()` contract is the dominant Phase-9 compatibility surface.** Temporal's signal-on-resume primitive in Phase 9 must round-trip the same `HumanRequest`/`HumanDecision` Pydantic models. If those models drift between Phase 6 and Phase 9, Phase-9 testing exposes the drift expensively. Mitigation: the Pydantic models are frozen + JSON-schema-exported under `docs/contracts/hitl-v0.6.0.json` and a Phase 9 design-review checklist item is "does the Temporal signal payload validate against this schema?" **Severity: medium**, but cheap to mitigate now.

---

## Acknowledged blind spots

- **Concurrent multi-thread (`thread_id`) execution.** Phase 6 ships single-process, single-workflow at a time. LangGraph supports multiple concurrent threads via the checkpointer's `thread_id` namespacing, and Phase 9 will exercise this with Temporal. Phase 6's tests are single-thread; we trust LangGraph's docs that `thread_id` isolation works, but we don't independently verify it. This is fine — verifying it is Phase 9's job.
- **Subgraph composition.** Phase 6 does not ship subgraphs (ADR-0022, Three Strikes). Phase 7 (distroless) adds a sibling top-level subgraph; Phase 8 (planner) will compose them. Phase 6's `builder.py` is one flat graph. If subgraph composition turns out to need a richer Pydantic-state-handoff protocol than `model_copy(update={...})`, Phase 7 will surface that.
- **Streaming intermediate state to observers.** LangGraph's `astream_events` API would let a UI watch the graph progress in real time. Phase 6 ships none of that — the CLI prints structured logs and that's it. Phase 8's planner UI is the right home.
- **Mid-node failure semantics with the checkpointer.** What happens if `apply_recipe` raises mid-function — is the state at the *start* of `apply_recipe` what survives, or some partial mutation? LangGraph's checkpointer writes at node boundaries (entry + exit), so the answer is: the state at node entry survives, the node re-runs on resume. We trust this; we test it indirectly via the replay tests but not exhaustively per-node. The `multiprocessing` kill test in the replay layer is the strongest evidence; if it passes for one node, the LangGraph contract says it passes for all.
- **The exact wire format of `interrupt()` resume payloads across LangGraph versions.** Phase 6's `await_human` uses `interrupt(dict_payload)` and assumes the resume value is the dict-like payload injected via `aupdate_state` or `Command(resume=...)`. If LangGraph changes how resume values are carried, the `_compat.py` shim above is the fix; the contract tests on HITL would catch the breakage at version-bump time.

---

## Open questions for the synthesizer

1. **Should the supervisor (intent → subgraph routing) ship in Phase 6 or wait for Phase 8?** ADR-0018 (pure routing vs. LLM) is deferred and the Phase 8 design owns it. Phase 6 has only one task class (vuln), so a supervisor is trivially `lambda intent: vuln_subgraph`. My recommendation: **do not ship a supervisor in Phase 6**. The cli/remediate.py edit calls `build_vuln_graph()` directly. Phase 7 (distroless) adds a sibling builder; Phase 8 mints the supervisor that picks between them. Surfacing for synthesizer review because the performance lens may argue for shipping the supervisor seam now to avoid a refactor.
2. **Should `record_attempt` and `run_gate` be one node or two?** The Phase 5 `GateRunner.run(...)` body conceptually wraps both (execute sandbox + record attempt). Splitting them in the graph gives a clearer topology and a dedicated checkpoint between sandbox execution and ledger write — useful for replay. Cost: one extra node. My choice: **two nodes**. Surface for review.
3. **Should `apply_recipe`, `rag_lookup`, `llm_replan` each call into Phase 5's `GateRunner` themselves, or should `run_gate` be a single shared node downstream?** I chose a single shared `run_gate` node downstream of all three engines (clearer topology, single gate-execution path). The alternative — gate-per-engine-node — couples gating into each engine node and balloons the topology. Surface for review in case the security or performance lens has objections about per-engine gate config differences.
4. **What is the documented exit code namespace?** Phase 5 documented `exit 11 = gate_escalate_human`. Phase 6 adds `exit 12 = graph_awaits_human` (pause) and reuses `exit 11` after `escalate` runs (abort). Surfacing for synthesizer to confirm the namespace is consistent across phases (a project-wide `docs/exit-codes.md` would help; not in scope for Phase 6 to create).
5. **The golden-graph test as a CI gate is opinionated.** If the synthesizer prefers a "review-only" graph artifact (commit the SVG, don't fail CI on drift), the topology becomes mutable without a deliberate PR step. My recommendation: **fail CI on drift**. Updating the golden is one extra command (`pytest --update-golden`). Surface for review.
