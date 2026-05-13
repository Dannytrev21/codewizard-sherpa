# Phase 6 — SHERPA-style state machine for the vuln loop: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

I optimized for **workflows-per-hour at portfolio scale** and **time-to-PR p95**. The Phase 5 stack already does the expensive work (sandbox boots, npm install, npm test) — Phase 6 is glue that decides what runs next. The dominant performance levers here are (1) keeping the LangGraph overhead per node under 5ms so the state machine is invisible compared to a 90s npm install, (2) making the SQLite checkpointer never block the hot path, (3) keeping the Pydantic state ledger small and incrementally serialized so checkpoint cost grows with the *delta*, not the *whole state*, and (4) collapsing the Phase 5 `GateRunner` `for`-loop into a self-loop subgraph so we do not pay both an outer Phase-5 retry loop *and* an inner Phase-6 retry loop on the same gate.

I explicitly deprioritized: ergonomics of `langgraph-cli` visualization (we ship the wire format that it consumes, not a pretty topology); SHERPA-purist "nodes never call nodes" enforced at runtime (we enforce it at lint time only — runtime checks would cost cycles in the hot path); Postgres-readiness (ADR-0016 is deferred — SQLite is fine until Phase 9). I also push back on one ADR-0014 corollary in §Risks: the three-retry feedback path as currently written re-enters Phase 4 from cold each time, which is the largest single waste in the loop.

## Goals (concrete, measurable)

| # | Goal | Target | Why |
|---|---|---|---|
| 1 | **Workflows/hour per worker** (Phase-6 envelope only, hot RAG path) | **≥ 40 wf/hr/worker** | 90s sandbox-bound work + ≤ 5s state-machine overhead ⇒ ~95s/wf |
| 2 | **Time-to-PR p95, RAG hot path** | **≤ 100 s** (Phase 4 was 95 s; Phase 6 adds ≤ 5 s envelope) | LangGraph overhead must be invisible |
| 3 | **Time-to-PR p95, LLM cold path with 1 successful retry** | **≤ 240 s** | retry-1 ≤ 1.6× retry-0 (Phase 5 ledger budget) |
| 4 | **Per-node LangGraph overhead** (no work in node body) | **p50 ≤ 2 ms / p95 ≤ 8 ms** | Excludes Pydantic validate; measured by canary node |
| 5 | **Checkpoint write latency** (SQLite, single-row diff, ≤ 8 KB state delta) | **p50 ≤ 4 ms / p95 ≤ 15 ms** | aiosqlite WAL mode; off the hot critical path via background flush |
| 6 | **Checkpoint write throughput** (sustained) | **≥ 800 writes/s/worker** | 40 wf × 20 checkpoints/wf = 800/s ceiling under one worker |
| 7 | **Resume-from-kill p95** (warm SQLite, state ≤ 64 KB) | **≤ 250 ms** end-to-end before next node fires | Replay tests use this as the canary |
| 8 | **Per-workflow state ledger ceiling (in-memory)** | **≤ 256 KB** working set, **≤ 64 KB** serialized after pruning | progressive disclosure — paths, not bodies |
| 9 | **Per-workflow checkpoint storage** (final, after retention prune) | **≤ 32 KB** | Last-write-wins of all but the head + interrupt frames |
| 10 | **Tokens/PR — Phase 6 envelope contribution** | **0** (no new LLM calls; Supervisor stays pure-routing per ADR-0018 default) | The state machine never tokenizes anything |
| 11 | **Cache hit rate — replay/idempotency** | **≥ 95%** on cassette re-runs | Same `(workflow_id, thread_id)` short-circuits at the entry node |
| 12 | **Per-worker steady-state memory ceiling** | **≤ 2.0 GB** including Phase 4's 1.7 GB | LangGraph + aiosqlite footprint ≤ 300 MB |
| 13 | **Per-worker CPU ceiling at 40 wf/hr** | **≤ 1.5 vCPU** average | Most time waits on subprocess; state machine is cheap |
| 14 | **Conditional-edge evaluation cost** | **p99 ≤ 200 µs** | Pure-function gate readers; zero IO |
| 15 | **HITL interrupt round-trip — fire + checkpoint + ready-for-resume signal** | **p95 ≤ 80 ms** | Phase 11 picks this up; we ship the latency budget here |

## Architecture

```
                 codegenie remediate <repo> --cve <id>     (entry unchanged)
                                  │
                                  ▼
                ┌──────────────────────────────────────────┐
                │  Phase 3/4/5 orchestrator entry           │
                │  Now invoked as a LangGraph CompiledGraph │   [P6]
                │  via VulnLoop.ainvoke(initial_state,      │
                │                       config={thread_id}) │
                └──────────────────┬───────────────────────┘
                                   │
                                   ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  src/codegenie/loop/vuln_loop.py — VulnLoop = StateGraph.compile(...)     │
   │                                                                            │
   │  StateGraph(VulnState)                                                    │
   │   ├─ entry: load_context        (Phase 3 Stage 1, wrapped)                │
   │   ├─ node: resolve_advisory      (Phase 3 Stage 2)                        │
   │   ├─ node: select_recipe         (Phase 3 Stage 3 + Phase 4 RagLlmEngine) │
   │   ├─ node: apply_transform       (Phase 3 Stage 5)                        │
   │   ├─ subgraph: gate_loop         (Phase 5 GateRunner *as* a subgraph)     │
   │   │    nodes:  build_spec → execute_sandbox → collect_signals             │
   │   │            → evaluate_gate → branch                                    │
   │   │    conditional_edge: passed | retryable | unrecoverable | escalate    │
   │   │    self-loop on retryable (≤ 3, ADR-0014); writes prior_attempts      │
   │   │    interrupt() on unrecoverable when sensitivity == high              │
   │   └─ node: emit_report           (Phase 3 RemediationReport)              │
   │                                                                            │
   │  Compiled once at import time; CompiledGraph reused across workflows      │
   │  (no per-workflow .compile() — saves ~80 ms/wf cold start)                │
   │                                                                            │
   │  Checkpointer: AsyncSqliteSaver(.codegenie/loop/checkpoints.sqlite)       │
   │                WAL=on, synchronous=NORMAL, mmap_size=256MB                │
   └──────────────────┬────────────────────────────────────────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  src/codegenie/loop/state.py — VulnState (Pydantic BaseModel)             │
   │                                                                            │
   │  model_config = ConfigDict(extra="forbid", frozen=False)                  │
   │                                                                            │
   │  Hot fields (every checkpoint):                                           │
   │    run_id: str          thread_id: str          stage: StageEnum          │
   │    cursor: NodeId       attempt: int            last_gate_id: str | None  │
   │    cost_running_usd: Decimal   budget_usd: Decimal                        │
   │                                                                            │
   │  Cold fields (paths only — progressive disclosure):                        │
   │    repo_context_path: Path       advisory_ref: AdvisoryRef                │
   │    recipe_application_path: Path   prior_attempts: list[AttemptRef]       │
   │    ledger_head: bytes           audit_chain_head: bytes                   │
   │                                                                            │
   │  Reducers (LangGraph Annotated[..., reducer]):                            │
   │    prior_attempts: append-only list (delta-encoded in checkpoint)         │
   │    cost_running_usd: monotonic-add reducer (atomic increment)             │
   │    All other fields: last-write-wins                                       │
   └──────────────────┬────────────────────────────────────────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  AsyncSqliteSaver — write-batched, single-writer SQLite                   │
   │                                                                            │
   │   - aiosqlite, WAL mode, NORMAL fsync, mmap'd                              │
   │   - Single writer task drains an asyncio.Queue (capacity 256)             │
   │   - Workflow nodes call checkpointer.aput(...) → returns when queued,     │
   │     not when persisted; durability bound = next gate boundary (~50 ms)    │
   │   - PRAGMA journal_size_limit = 32 MB; auto_vacuum=INCREMENTAL            │
   │   - Retention: keep last 4 checkpoints + every interrupt frame;           │
   │     async vacuum runs nightly                                              │
   │                                                                            │
   │  Why not InMemorySaver: replay tests demand survive-process-restart.      │
   │  Why not Postgres: Phase 9 territory; SQLite WAL hits the throughput      │
   │  target with zero ops surface.                                             │
   └──────────────────┬────────────────────────────────────────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  HITL interrupt() integration                                             │
   │                                                                            │
   │   Trigger: gate_loop.evaluate_gate → branch returns "interrupt"           │
   │            when attempt == max && sensitivity_class ∈ {high, critical}   │
   │   Wire: NodeInterrupt(value=PauseEnvelope(...)) → CompiledGraph emits     │
   │            on the stream; checkpoint persists at the interrupt frame      │
   │   Resume: VulnLoop.ainvoke(Command(resume=ApprovalDecision(...)),         │
   │            config={thread_id}) — replays from checkpoint, single node    │
   │            fires next                                                     │
   │   Latency budget: ≤ 80 ms from interrupt call to "ready_for_resume"      │
   │            event on the stream (measured in tests)                       │
   └──────────────────────────────────────────────────────────────────────────┘

  Package layout (additions on top of Phase 5):
  src/codegenie/
    loop/                       ← NEW
      __init__.py
      vuln_loop.py              ← VulnLoop CompiledGraph factory + module-level compile
      state.py                  ← VulnState + reducers + sensitivity classifier
      checkpointer.py           ← AsyncSqliteSaver wrapper + retention policy
      nodes/                    ← One file per node; each is a plain async function
        load_context.py
        resolve_advisory.py
        select_recipe.py
        apply_transform.py
        emit_report.py
      gate_subgraph/            ← Phase 5 GateRunner translated to LangGraph
        __init__.py
        build_spec.py
        execute_sandbox.py
        collect_signals.py
        evaluate_gate.py
        branch.py               ← conditional_edge logic (pure function)
      interrupts.py             ← PauseEnvelope, sensitivity rules, NodeInterrupt wrapper
      bench/
        canary_node.py          ← no-op node for per-node overhead regression test
    cli/
      loop.py                   ← codegenie loop {run, resume, inspect, replay}

  Phase 0 fence policy:
    loop/                       may import: phases 0–5 packages, langgraph, aiosqlite
    loop/                       may NOT import: anthropic, chromadb (Phase 4 holds those)
    loop/state.py               may NOT import any subprocess/network module
    loop/checkpointer.py        is the sole importer of aiosqlite
```

## Components

### 1. `VulnLoop` — the compiled `StateGraph`

- **Purpose:** Express the Phase 3/4/5 pipeline as a deterministic LangGraph with conditional edges as Trust-Aware gates, compiled exactly once per process.
- **Interface:**
  - Inputs: `initial_state: VulnState`, `config: RunnableConfig` (carries `thread_id`, `checkpoint_ns`).
  - Outputs: `VulnState` (final), interrupt events on the async stream.
  - Errors: `LoopAborted`, `BudgetExhausted` (re-raised from inside nodes), `AuditChainCorrupted` (from Phase 5 ledger init).
- **Internal design:**
  - **Compiled once at import time.** `VULN_LOOP: CompiledGraph = _build().compile(checkpointer=...)`. The `_build()` cost (~80 ms) is paid once per worker, not per workflow. This is the single biggest cold-start win available.
  - Nodes are **plain async functions**. Each function signature is `async def fn(state: VulnState) -> VulnState | dict`. Returning a dict (with only the fields that changed) is preferred — LangGraph applies it as a delta, which keeps the checkpoint payload small.
  - The Phase 5 `GateRunner` becomes the `gate_subgraph` rather than running its own `for`-loop. Same `RetryLedger` writes; loop control lives in LangGraph's conditional edge. **One retry loop, not two.**
  - The Phase 3 orchestrator is *invoked through* `VulnLoop.ainvoke`, not in parallel with it. The orchestrator's existing six-function-call body becomes the node bodies, one node per function. No code is duplicated.
- **Tradeoffs accepted:**
  - Module-level compile means the graph topology is locked at process start. Hot-swapping nodes requires a worker restart. Acceptable — Phase 9 (Temporal) restarts workers on deploy anyway.
  - Returning dicts (not full state) is a SHERPA-correctness footgun if a node forgets a field. Mitigation: a pytest plugin asserts that every node's return type is `dict | VulnState` and that the dict keys are a subset of `VulnState`'s field names — runs at import time in CI, free at runtime.

### 2. `VulnState` — the typed state ledger with reducers

- **Purpose:** Single source of mutable truth between nodes. Tight enough to checkpoint quickly; rich enough to drive every conditional edge without rehydrating cold artifacts.
- **Interface:** Pydantic `BaseModel`. `model_config = ConfigDict(extra="forbid", frozen=False)`. Fields split into "hot" (every checkpoint) and "cold" (paths only).
- **Internal design:**
  - **Hot fields are flat scalars.** `run_id`, `thread_id`, `stage`, `cursor`, `attempt`, `last_gate_id`, `cost_running_usd`, `budget_usd`. Total < 256 bytes serialized. The conditional-edge functions only need these — no cold-field IO on the hot path.
  - **Cold fields are `Path` references.** `repo_context_path`, `recipe_application_path`, `prior_attempts: list[AttemptRef]`. The actual `RepoContext`, the actual `RecipeApplication`, the actual `AttemptSummary` bytes live on disk under `.codegenie/`. Nodes that need the body call a tiny `Lazy[T]` helper (`load_repo_context(path) -> RepoContext`) which mmaps and caches per-process.
  - **Reducers reduce checkpoint payload.** `prior_attempts` is `Annotated[list[AttemptRef], append_only]`; the checkpointer persists *only the appended entries* per step, not the whole list. `cost_running_usd` is `Annotated[Decimal, monotonic_add]` — the same node failing 3× still only writes 3 deltas, not 3 full-state snapshots.
  - **Sensitivity classifier is pure.** `sensitivity_class(state) -> Literal["low","medium","high","critical"]` is a 20-LOC function over hot fields (CVE severity from `advisory_ref`, repo-criticality flag from `repo_context_path` *manifest* — not body — read at `load_context` time and cached on the state). No IO at edge-evaluation time.
- **Tradeoffs accepted:**
  - The "paths not bodies" rule means a node that re-reads `RepoContext` on every visit pays mmap cost (cheap, ~1 ms warm) instead of getting it free from state. Acceptable: nodes that re-read are rare (only `apply_transform` and `select_recipe`).
  - Reducers mean reasoning about state mutation requires reading the `Annotated[...]` declaration. A lint rule in CI asserts every list/Decimal/set field has an explicit reducer or an explicit `last_write_wins` marker; no implicit semantics.

### 3. `AsyncSqliteSaver` wrapper — never block the hot path

- **Purpose:** Persistent state with sub-15ms p95 write latency under sustained 800 writes/s/worker load.
- **Interface:** Conforms to LangGraph's `BaseCheckpointSaver` async protocol; adds `aput_async_queued(...)` that returns once enqueued (not persisted).
- **Internal design:**
  - **WAL mode + NORMAL fsync.** WAL gives concurrent reads while a write is in flight; NORMAL fsync is the right durability/throughput trade for a single-host POC (the worst case on crash is losing the last unflushed checkpoint, and Phase 9's Temporal envelope is the higher-durability layer).
  - **Single writer task drains an `asyncio.Queue(maxsize=256)`.** Node bodies `await queue.put((thread_id, checkpoint))` and continue immediately. A dedicated writer task batches up to 16 checkpoints per transaction. **The node returns before fsync** — durability is guaranteed by the next gate boundary, where we explicitly `await drain()` before LangGraph emits an interrupt.
  - **`mmap_size=256MB` + `cache_size=-65536` (64 MB).** Reads (resume, replay tests) hit memory, not disk.
  - **Retention.** Keep only `(head, last_interrupt_frame, last 3 successful gate frames)` per `thread_id`. Older frames are garbage-collected nightly. Bounds storage at ~32 KB/wf final.
  - **Schema migration is a no-op for Phase 6.** We use LangGraph's stock SQLite schema. Phase 9 owns the Postgres migration (ADR-0016 deferred).
- **Tradeoffs accepted:**
  - **Non-fsync'd checkpoint may be lost on hard crash between nodes.** Acceptable because the *next* node either (a) re-derives state from disk artifacts (Phase 5 ledger is the source of truth for gate attempts) or (b) the workflow restarts from the last fsync'd frame. We never lose more than one node's worth of work.
  - Single-writer queue is a Phase 6 bottleneck at very high concurrency (theoretical ceiling ~5,000 writes/s on a fast NVMe). We're targeting 800 writes/s/worker, which leaves 6× headroom. Phase 9's per-worker Postgres connection pool removes the constraint.

### 4. `gate_subgraph` — Phase 5's `GateRunner` translated to LangGraph

- **Purpose:** Implement ADR-0014 retry loop as graph topology, not as a Python `for`-loop.
- **Interface:** Same `GateContext` in, same `GateOutcome` out. The Phase 5 `RetryLedger` writes are unchanged — same files, same BLAKE3 chain, same audit chain root.
- **Internal design:**
  - **Five nodes:** `build_spec` → `execute_sandbox` → `collect_signals` → `evaluate_gate` → `branch`. Each node body is the corresponding section of Phase 5's `GateRunner.run`, lifted verbatim.
  - **`branch` is a pure conditional edge** that returns one of: `"pass"` → exit subgraph with `passed=True`; `"retry"` → back-edge to `build_spec` (LangGraph supports cycles; this is exactly the right primitive); `"unrecoverable"` → exit subgraph with `passed=False, escalate=False`; `"interrupt"` → emit `NodeInterrupt` for HITL.
  - **`prior_attempts` updates flow through state.** The Phase 5 `with_prior_attempt` semantics map to LangGraph's append-only reducer — no manual mutation.
  - **One retry loop, not two.** The Phase 5 `for attempt in range(1, max_attempts + 1)` body is *deleted* on the Phase 6 path; Phase 6 re-instantiates the gate via the cycle edge. The Phase 5 `GateRunner.run` function remains for sync-only callers (CLI smoke tests, Phase 5 regression tests) but is bypassed by Phase 6.
- **Tradeoffs accepted:**
  - Two retry implementations exist in the codebase (Phase 5 sync, Phase 6 graph). They must stay semantically identical. Mitigation: a single parametric test fixture (`test_retry_semantics_parity.py`) runs the same scenario through both and asserts identical `RetryLedger` outputs byte-for-byte. The day they drift is the day Phase 5's sync loop gets deleted.
  - Cycle edges in LangGraph are slightly more expensive than straight-line nodes (~1 ms extra per cycle). At max 3 cycles per gate × ~5 gates per workflow, that's 15 ms — well inside the 5s envelope budget.

### 5. `interrupts.py` — HITL with sub-100 ms round trip

- **Purpose:** Translate Phase 5's "escalate" branch into a LangGraph `interrupt()` that pauses the workflow durably and resumes deterministically on human approval.
- **Interface:**
  - `pause(state, reason: EscalationReason) -> NoReturn` — raises `NodeInterrupt(PauseEnvelope(...))`.
  - `resume(thread_id, decision: ApprovalDecision) -> AsyncIterator[StreamEvent]` — wraps `VulnLoop.ainvoke(Command(resume=decision), config={thread_id})`.
- **Internal design:**
  - **Fire path:** `evaluate_gate` node, on the `interrupt` branch, calls `pause(state, reason)`. `PauseEnvelope` is a Pydantic frozen model with `gate_id`, `attempt`, `failing_signals`, `ledger_head`, `evidence_paths` — all hot fields plus a few cold paths. ≤ 4 KB serialized. The interrupt is the trigger for an immediate `await checkpointer.drain()` (the only place we synchronously fsync; we *want* this checkpoint durable).
  - **Sensitivity → interrupt mapping.** ADR-0014 says "interrupt on retry exhaustion." We refine: `attempt == max_attempts AND sensitivity_class in {high, critical}` → interrupt. `attempt == max_attempts AND sensitivity_class in {low, medium}` → `failed_unrecoverable` exit (Phase 5's semantics). Default `sensitivity_class` for vuln remediation in Phase 6 = `high` (everything in the vuln loop hits human eyes). Phase 7+ can ratchet `low`/`medium` cases to auto-fail for throughput.
  - **Resume path:** `VulnLoop.ainvoke(Command(resume=decision), ...)` rehydrates from the interrupt frame. The next node executed reads `decision.action ∈ {"approve_and_retry", "approve_and_fail", "reject"}` and routes accordingly via a new edge from the interrupt resume point.
  - **The 80 ms budget is the time between `pause()` returning and the *resume-ready* event on the stream.** Most of that is `checkpointer.drain()` (≤ 30 ms WAL fsync) + `NodeInterrupt` propagation (≤ 5 ms) + stream emit (≤ 5 ms). The remaining 40 ms is slack.
- **Tradeoffs accepted:**
  - Forcing fsync on interrupt makes interrupt the slowest checkpoint in the workflow. Acceptable — interrupts are by definition rare (≤ 1 per workflow on the bad path; 0 on the hot path).
  - Phase 11 owns the *human* side of resume (PR comment dispatch, approval ingestion). Phase 6 only ships the in-process `resume()` function and a mocked CLI command (`codegenie loop resume <thread_id> --decision approve_and_retry`) so the exit-criterion HITL test can run end-to-end without GitHub plumbing.

### 6. Per-node overhead canary

- **Purpose:** Performance regression gate. If LangGraph or Pydantic ever drift the per-node overhead above budget, CI catches it.
- **Interface:** Pytest benchmark fixture; `pytest tests/perf/test_canary_overhead.py --benchmark-only`.
- **Internal design:** A graph of 100 no-op nodes (each returns `{}`) is invoked 1,000 times. Total wall-clock divided by 100,000 invocations = mean per-node overhead. Asserted < 2 ms p50, < 8 ms p95. Runs on every PR that touches `loop/` or upgrades `langgraph`/`pydantic` versions.
- **Tradeoffs accepted:** Adds ~5 s to CI on PRs that touch the loop. Worth it — drift here is silent and catastrophic.

### 7. CLI surface — `codegenie loop`

- **Purpose:** Operator and test harness for the state machine.
- **Public interface:**
  - `codegenie loop run <repo> --cve <id>` — the new top-level entry; wraps `codegenie remediate` and routes through `VulnLoop`. The old `codegenie remediate` becomes an alias.
  - `codegenie loop resume <thread_id> --decision {approve_and_retry, approve_and_fail, reject}` — HITL resume.
  - `codegenie loop inspect <thread_id>` — pretty-prints the checkpoint chain.
  - `codegenie loop replay <thread_id> --from <checkpoint_id>` — re-executes the graph from a chosen checkpoint frame (deterministic-replay test harness).
- **Internal design:** `click`. Reuses Phase 5's `--max-attempts-override`. All commands accept `--checkpointer-db <path>` for test isolation.

## Data flow

End-to-end walk for one representative workflow (Node service, hot RAG path, 1 gate retry, no HITL):

1. **t=0 (cold-start budget paid at import):** Worker process imports `codegenie.loop.vuln_loop`; `VULN_LOOP: CompiledGraph` is built and stored at module scope. ~80 ms one-shot cost.
2. **t=0+ε:** `codegenie loop run` enters. Builds an initial `VulnState(run_id=..., thread_id=..., stage=ENTRY, cursor="load_context", attempt=0, cost_running_usd=0, budget_usd=5.0)`. Calls `await VULN_LOOP.ainvoke(state, config={"configurable": {"thread_id": thread_id}})`.
3. **t≈10 ms:** Entry checkpoint written (async, queued). `load_context` node runs: reads `.codegenie/context/repo-context.yaml`, validates schema, returns `{repo_context_path: ..., sensitivity_class: "high"}`. Wall-clock ≤ 200 ms (cached `RepoContext`).
4. **t≈220 ms:** `resolve_advisory` node: reads pinned CVE snapshot. ≤ 30 ms. Returns `{advisory_ref: ...}`.
5. **t≈250 ms:** `select_recipe` node enters; delegates to Phase 4 `RagLlmEngine`. Tier 0 query-key cache miss → Tier 1 embed + RAG hit (cosine ≥ τ_hit). 0 LLM tokens. Returns `{recipe_application_path: ...}`. Wall-clock p50 ≤ 5 s (Phase 4's existing RAG path budget).
6. **t≈5 s:** `apply_transform` node: writes patch to working tree. ≤ 1 s.
7. **t≈6 s:** Enters `gate_subgraph`. `build_spec` (≤ 5 ms) → `execute_sandbox` (Phase 5 DiD; build+install+test; p50 60–90 s) → `collect_signals` (≤ 10 ms) → `evaluate_gate` (≤ 1 ms): retryable failure on `tests.failed`. Branch → `"retry"`. Append `AttemptRef` to state via reducer; back-edge to `build_spec`. Checkpoint queued.
8. **t≈70 s:** Second pass through gate_subgraph. This time `select_recipe` is *not* re-entered (the Phase 4 re-plan path requires explicit orchestrator decision); instead the same recipe is re-applied with `prior_attempts` carried in `ApplyContext`. Phase 4's `FallbackTier.run` *would* re-engage only on `unrecoverable` exits. *See §Risks risk-1 — this is the largest deviation from Phase 4/5's stated design and the open question for the synthesizer.*
9. **t≈140 s:** Gate passes on retry-1. `emit_report` node: writes `RemediationReport`. ≤ 100 ms.
10. **t≈140.5 s:** Final checkpoint written; `VulnLoop.ainvoke` returns. CLI prints success.

**Total wall-clock**: ~141 s, dominated by two sandbox boots (Phase 5 cost). LangGraph envelope contribution: ~50 ms total across ~10 nodes. Within budget.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Worker process killed mid-node | LangGraph on next `ainvoke(config={thread_id})` | Resumes from last fsync'd checkpoint; at most one in-flight node re-runs. Replay test asserts identical final state. |
| Worker process killed mid-checkpoint-write | SQLite WAL recovery on next open | The in-flight WAL frame is rolled back; we resume from the previous committed frame. ≤ 1 node's work re-done. |
| Checkpoint queue overflows (back-pressure) | `queue.put_nowait` raises `QueueFull` in the wrapper | Node `await`s the put; degrades latency by a few ms. Never drops a checkpoint. Metric `loop.checkpoint.backpressure_events` alerts above 1/min. |
| SQLite file corruption | `sqlite3.DatabaseError` on open | Fail loud: `LoopAborted("checkpoint db corrupt; run codegenie loop salvage <thread_id>")`. Salvage tool reads Phase 5 `RetryLedger` (the audit ground truth) and reconstructs minimal state to resume. |
| Gate retry exhaustion, `sensitivity ∈ {low, medium}` | `evaluate_gate` branch returns `unrecoverable` | Exits subgraph with `passed=False`; `emit_report` records failure; workflow returns non-zero. No HITL. |
| Gate retry exhaustion, `sensitivity ∈ {high, critical}` | Same branch returns `interrupt` | `NodeInterrupt` raised; checkpoint drained synchronously; stream emits `interrupt_ready` event. Workflow paused indefinitely. `codegenie loop resume` continues. |
| `VulnState` schema mismatch on resume (Phase 6 upgraded, old checkpoints exist) | Pydantic validation in `AsyncSqliteSaver.aget` | Fail loud with `CheckpointSchemaIncompatible(checkpoint_version=N, current_version=M)`. Migration ADR required (none in Phase 6 — schema is v1). |
| Node body raises an unhandled exception | LangGraph wraps and surfaces on the stream | Workflow terminates; last checkpoint is the one *before* the failing node. Re-running `ainvoke` from `thread_id` retries that node deterministically. No retry-storm; LangGraph emits the exception to the caller. |
| `cost_running_usd >= budget_usd` | Edge-evaluation guard in `branch` | Routes to `emit_report` with `BudgetExhausted` reason. Phase 5 cost ledger already captured the spend. |
| Module-level `_build()` compile fails on import | Python import error | Worker process dies at startup. Loud, fast. Operations replace via deploy. |

## Resource & cost profile

| Resource | Phase 6 envelope contribution | Total per run (with Phase 3/4/5) |
|---|---|---|
| **Tokens per run (Phase 6 only)** | 0 | RAG hot: 0; LLM cold: ≤ 48k input + 8k output |
| **Wall-clock p50 (RAG hot path)** | +5 s overhead | ~95 s |
| **Wall-clock p95 (RAG hot path)** | +8 s overhead | ~100 s |
| **Wall-clock p95 (LLM path + 1 retry)** | +12 s overhead | ~240 s |
| **Per-node overhead (no work)** | p50 2 ms / p95 8 ms | — |
| **Memory per worker (loop only)** | ≤ 300 MB (langgraph ~80 MB, aiosqlite + 64 MB cache + 256 MB mmap virtual, Pydantic models + GC headroom) | ≤ 2.0 GB total |
| **Storage growth per workflow (final, post-retention)** | ≤ 32 KB checkpoint | + Phase 5 ledger (~50 KB) + Phase 4 RAG entry (~10 KB) |
| **Storage growth per workflow (peak, during run)** | ≤ 256 KB | — |
| **Hot vs cold ratio (Phase 6 envelope)** | RAG hot 0 tokens; LLM cold same as Phase 4 — Phase 6 adds no LLM | — |
| **Throughput ceiling per worker** | ≥ 40 wf/hr (RAG hot path; limited by sandbox, not loop) | — |
| **CPU at 40 wf/hr/worker** | ≤ 1.5 vCPU avg, ≤ 4 vCPU peak (during sandbox spawn) | — |

## Test plan

**Definition of "passes its tests":**

1. **State-transition coverage (exit-criterion AC).** A test `test_every_conditional_edge_exercised.py` runs scenarios that collectively visit every conditional edge at least once. Coverage is measured via a custom LangGraph callback that records `(from_node, to_node)` tuples; the test asserts the set equals the registered edge set. CI fails on missing edges. Concretely:
   - `pass` edge from `evaluate_gate`: hot path scenario.
   - `retry` edge: gate-fail-then-pass scenario.
   - `unrecoverable` edge (low sensitivity): 3-fails-low-sensitivity scenario.
   - `interrupt` edge (high sensitivity): 3-fails-high-sensitivity scenario.
   - Budget-exhausted edge from `branch`: synthetic high-budget-consumption scenario.

2. **Replay test (exit-criterion AC).** `test_replay_after_kill.py` starts a workflow, kills the process during the second `execute_sandbox` node (using `os.kill(os.getpid(), SIGTERM)` from a sandbox-mock hook), restarts a fresh worker, and asserts the resumed workflow produces a `RemediationReport` byte-identical to a baseline non-killed run. Uses `pytest-recording` cassettes for any Phase 4 LLM calls so the test is fully deterministic.

3. **HITL interrupt test (exit-criterion AC).** `test_hitl_interrupt_and_resume.py` runs a scenario where the gate fails twice with `sensitivity_class="high"`; asserts a `NodeInterrupt` is emitted; invokes `resume(thread_id, ApprovalDecision(action="approve_and_retry"))`; asserts the third gate attempt fires; if scripted to pass, asserts final state is success. Verifies the 80 ms interrupt-round-trip budget with `time.monotonic()` assertions.

4. **Retry parity test.** `test_retry_semantics_parity.py` runs the same fixture scenario through (a) Phase 5's `GateRunner.run` sync loop and (b) Phase 6's `gate_subgraph` cycle; asserts the resulting `RetryLedger` files are byte-identical. The day this fails, one of the two implementations has drifted.

5. **Performance regression canary (mandatory).** `test_canary_overhead.py` is a pytest-benchmark test running 100,000 no-op-node invocations. **Asserts p50 < 2 ms, p95 < 8 ms.** Runs in CI on every PR touching `loop/`, `langgraph` version, or `pydantic` version. Asserts the benchmark's `stddev / mean < 0.15` to catch regression caused by GC pressure or background-task contention.

6. **Checkpoint throughput test.** `test_checkpoint_throughput.py` issues 10,000 checkpoints through `AsyncSqliteSaver` at maximum concurrency; asserts sustained throughput ≥ 800 writes/s and p99 enqueue latency < 5 ms. Run nightly (slow).

7. **Workflow throughput integration test.** `test_throughput_e2e.py` runs 40 mock workflows (sandbox stubbed to ~30 s each) concurrently through one worker; asserts wall-clock ≤ 30 min (i.e., the state machine is not the bottleneck). Nightly.

8. **State-payload size test.** `test_state_size_budget.py` asserts the final checkpoint for each fixture scenario is ≤ 32 KB serialized; asserts peak in-memory `VulnState.model_dump()` is ≤ 256 KB.

9. **Phase-5 regression suite re-runs unchanged.** Phase 5's gate tests run with the *sync* `GateRunner.run` path active, proving the dual-implementation does not break Phase 5's contracts.

10. **Cassette-replay determinism test.** Re-running the LLM-cold-path test 10× must produce 10 byte-identical `RemediationReport` files and 10 byte-identical checkpoint chains.

## Risks (top 5)

1. **Retry-2 cost is much larger than ADR-0014 implies.** ADR-0014 says retry sends the gate back with prior-attempt context. *Where the prior context goes* is unclear: (a) re-apply the same `RecipeApplication` and just re-run the gate (cheap; what Phase 5's `RetryLedger` actually captures); (b) re-enter Phase 4's `FallbackTier.run` with `prior_attempts` and let it re-plan (expensive — full RAG + possibly LLM). Performance-favored interpretation is (a), but the Phase 4 final design's "feedback path semantics actually exercised" requirement (exit-criterion #19 in Phase 5 final-design) implies (b). **If (b) is the intended semantics, the workflow-per-hour target needs to drop by ~30% or the prior-attempt context needs to be carried into Phase 4's prompt-cache key so subsequent invocations stay cache-warm.** Surfaced for synthesizer resolution.

2. **`langgraph-cli` graph inspection (called out in Phase 6 scope) is not free.** Visualization requires emitting graph topology + state schema as JSON; doing this at every run adds ~30 ms cold-start. We ship a static `codegenie loop dump-topology` command that writes a one-time JSON, *not* per-run inspection. If the synthesizer wants live inspection, it costs a constant ~30 ms per workflow startup.

3. **AsyncSqliteSaver under heavy concurrency.** The single-writer queue is a Phase 6 bottleneck. Targets are met for one worker at 40 wf/hr. If Phase 7+ stacks two workflows per worker, the queue saturates at ~5,000 writes/s. The shim is forward-compatible: Phase 9 swaps to Postgres with no `VulnState` schema change. Risk is operational misuse — running Phase 6 with 4 workers per host without re-benching.

4. **Pydantic v2 dump cost on every checkpoint.** `model_dump_json()` on a 64 KB `VulnState` is ~1.5 ms. Cumulative over ~20 checkpoints per workflow = 30 ms. Mitigation: the dict-return discipline (nodes return `{changed_field: value}`, never the whole model) reduces dump scope to the delta. If Pydantic v3 lands during the phase and changes serialization perf, the canary catches it.

5. **`module-level compile + thread_id-keyed checkpointer` couples worker lifetime to graph version.** Hot-reloading a node body means restarting the worker. This is fine in Phase 9 (Temporal handles worker rotation), but in Phase 6 dev/test it means every code change requires a CLI restart. Friction, not correctness.

## Acknowledged blind spots

- **No actual portfolio-scale benchmarks.** All numbers above are derived from Phase 4/5 measured latencies plus LangGraph's published per-node overhead. The 40 wf/hr/worker target presumes a single-worker single-host setup; Phase 9 will produce the real number against Postgres.
- **No measurement of `interrupt()` resumed-graph cold cache.** The 250 ms resume budget assumes WAL is warm. After a long pause (days, per ADR-0009), the SQLite mmap may be cold; first read on resume could be 50–100 ms slower. Acceptable for a HITL flow but not measured.
- **macOS-specific perf is not separately budgeted.** All targets assume Linux/CI. Phase 5's `gate_isolation_class` decision means macOS dev runs DiD; the state-machine envelope is OS-independent in theory but I have not benchmarked aiosqlite on Darwin.
- **The performance argument against full `prior_attempts → Phase 4 re-plan`** (risk-1) directly contradicts the spirit of Phase 5 final-design exit-criterion #19. I am surfacing the conflict rather than averaging it (per global rule §7).
- **Token estimate for retry-with-feedback assumes prompt-cache hit on the immutable system block.** If the prior-attempt context invalidates the cache key, retry-1 LLM cost balloons 5×. Phase 4's `cache_breakpoints` discipline must explicitly *not* include the `prior_attempts` block above the cache fence.
- **I have not designed the SHERPA-discipline runtime lint.** ADR-0002 mentions "AST-based lints can enforce nodes never call nodes." I deprioritized this — it is implementable with a pre-commit hook walking node files for cross-node import statements. Surfaced for whoever writes that hook.

## Open questions for the synthesizer

1. **Retry feedback semantics (risk-1):** On gate retry, does the workflow re-enter Phase 4's `FallbackTier.run` with `prior_attempts`, or does it re-apply the same `RecipeApplication` and let the gate re-evaluate? My performance-favored read is the latter (cheap, correct for "flake" cases). Phase 5 final-design #19 reads the former. The cost difference is ~3× on the unhappy path.
2. **Sensitivity classifier defaults:** I propose `vuln remediation → high` (everything escalates), but if Phase 7's distroless workload is added with `sensitivity=medium` by default, the auto-fail path gets exercised. Is `sensitivity` a per-task-class config or a per-CVE-severity computed value? My design treats it as a pure function over hot state, but the inputs need ADR-level definition.
3. **Should `select_recipe` be re-entered on retry?** If the Phase 5 gate fails because the recipe was wrong (peer-dep conflict surfaced post-install, not pre-install), the right response is to **change recipes**, not to re-apply. Phase 6 has no node for "go back to recipe selection." I propose adding a conditional edge from `branch` → `select_recipe` for one specific failure signature (`install.failed` with peer-dep error in logs) — but this is a Phase-6 *scope expansion* that I have not budgeted. Synthesizer call.
4. **`thread_id` semantics:** I treat `thread_id == workflow_id`. LangGraph supports thread *namespaces* for sub-graph isolation. Do we want per-stage namespaces (lets us inspect stages independently) or one namespace per workflow (simpler)? I picked simpler.
5. **`Postgres deferral` from ADR-0016 — is "single-host POC" still the operative framing for Phase 6?** If the answer is "Phase 6 will run on multiple hosts before Phase 9 ships," SQLite is wrong from day one. I assumed single-host; if that assumption is wrong, the design needs Postgres now (and an aiopg checkpointer).
6. **The roadmap lists `langgraph-cli` as a tool. What is its actual role?** I treat it as a debug visualization tool (one-shot `dump-topology`); if the synthesizer wants it embedded in normal operations (live inspection of running workflows), the per-workflow overhead is real and needs budgeting.
