# Phase 6 — SHERPA-style state machine for the vuln loop: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** design-performance.md · design-security.md · design-best-practices.md · critique.md

## Lens summary

Best-practices dominates the **shape** of this phase: one `graph/` package, one Pydantic `VulnLedger`, one `interrupt()` site, declarative `build_vuln_graph()`, idiomatic LangGraph (`add_conditional_edges`, `interrupt_before`, `aupdate_state`), and a golden-graph topology snapshot. Performance dominates the **runtime budget**: module-level compile, per-node overhead canary, the SQLite checkpointer is real (not deferred), and we measure the assumptions instead of asserting them. Security dominates the **integrity layer** but is sharply scoped down: BLAKE3 chain extension is kept (it continues the Phase 2–5 chain that already exists); `extra="forbid"`, fence-CI rules, the `@pure_edge` AST check, and JSON-only serialization are kept; **all ~600 LOC of Ed25519/HMAC operator-key infrastructure is deferred to Phase 11 / Phase 16**, replaced by a typed `HumanDecision` Pydantic model and a single-host `0600` filesystem posture. Where the critic exposed a hard fork — `frozen`, retry-counter scope, Phase 4 re-entry on retry, single shared DB vs per-workflow DB, entry-point naming, `cli/remediate.py` editing — the synthesizer picked one per global-rule §7 ("surface conflicts, don't average them") and documented why, the loudest being: **per-gate retry counter (P,S over B) + Phase 4 `FallbackTier.run` re-entry on retry (S over P, honoring Phase 5 exit-criterion #19)**. The `cli/remediate.py` edit is replaced by a thin dispatch in `cli/loop.py` that **does not modify Phase 0–6 source** and that Phase 7's supervisor will swap behind, so Phase 7's "no Phase 0–6 source touched" exit criterion stays clean.

## Goals (concrete, measurable)

| # | Goal | Target | Provenance |
|---|---|---|---|
| 1 | Vuln loop runs as a LangGraph `StateGraph` end-to-end | `build_vuln_loop().ainvoke(initial, config={thread_id})` reaches `emit_artifact` on Phase 3's `cve-fixture` repo | `[B]` |
| 2 | Mid-run kill + resume produces byte-identical final state | `tests/integration/test_replay_after_kill.py` runs the workflow in a subprocess, SIGKILLs during `validate_in_sandbox`, restarts a fresh process, asserts the produced `RemediationReport` and `attempts.jsonl` are byte-identical to a non-killed reference run | `[B]+[P]` |
| 3 | HITL `interrupt()` fires on **two consecutive gate failures at the same gate transition** and a mocked human approval continues the run | `tests/integration/test_hitl_interrupt_and_resume.py` scripts Phase 5's gate runner to fail twice in a row, asserts `interrupt.raised`, injects `HumanDecision(action="continue", ...)` via `aupdate_state(..., as_node="await_human")`, asserts the workflow proceeds and (when scripted) succeeds | `[B]+[P]` |
| 4 | Per-gate retry counter honors ADR-0014 — three retries **per gate transition**, not per workflow lifetime | `VulnLedger.retry_count` is reset to 0 on every entry to `validate_in_sandbox` for a *new* gate transition; existing gate-transition retries increment it; the same retry edge that ships in Phase 5's `GateRunner.run` is re-expressed as a graph cycle whose `RetryLedger` output is **byte-identical** to Phase 5's sync `for`-loop ledger (parity test) | `[synth — resolves critic best-practices.1]` |
| 5 | Retry feedback semantics honor Phase 5 exit-criterion #19 — retry-1 re-enters Phase 4 with `prior_attempts` and produces a **different** `RecipeApplication` (distinct patch bytes) | `tests/integration/test_retry_reenters_phase4.py` asserts `attempts.jsonl` has 2 entries with distinct `attempt_id`, distinct `prior_failure_summary`, distinct `sandbox_run_id`, **distinct patch bytes**; Phase 4's prompt on attempt 2 contains the fence-wrapped summary | `[synth — resolves critic performance.1, security view via Phase 4 re-entry]` |
| 6 | Per-node LangGraph overhead is **measured**, not assumed | `tests/perf/test_canary_overhead.py` runs a 100-no-op-node graph 1,000× and **records** p50/p95 in `tests/perf/baseline.json`; the test fails only on **regression >25%** vs the baseline; baseline is committed once the test first runs in CI | `[synth — closes critic performance.3]` |
| 7 | Time-to-PR p95 envelope contribution (RAG hot path) | ≤ 5 s LangGraph overhead beyond Phase 4/5's existing budget (~95 s) — verified by the canary + an E2E timing assertion | `[P]` |
| 8 | Checkpoint durability under kill | Every node-boundary checkpoint is **fsync'd before LangGraph moves to the next node**. No background-queue trick. Throughput is whatever WAL + NORMAL fsync delivers (measured by the throughput test); we do not promise 800 writes/s | `[synth — resolves critic performance.2 — "without state loss" is non-negotiable per exit criterion]` |
| 9 | SQLite throughput is **measured** before deferring to Phase 9 Postgres | `tests/perf/test_checkpoint_throughput.py` issues 1,000 checkpoints serially through `AsyncSqliteSaver(WAL=on, synchronous=NORMAL)` and records achieved throughput in `tests/perf/baseline.json`. If achieved throughput is < 100 writes/s on CI hardware, an ADR-amendment story fires (`ADR-P6-006: SQLite throughput insufficient — escalate Postgres earlier`) | `[synth — closes shared blind spot "all three defer Postgres without measuring SQLite"]` |
| 10 | Per-workflow checkpointer concurrency model | **Per-workflow SQLite file** at `.codegenie/loop/checkpoints/<workflow_id>.sqlite3` (security's pick); concurrent workflows do not contend on one file; `langgraph-cli` is documented as point-at-a-specific-file | `[S]+[synth — resolves shared blind spot "all three defer Postgres", best-practices' SQLite-lock-contention risk]` |
| 11 | `VulnLedger` schema-version pin + drift detection | `schema_version: Literal["v0.6.0"]` is a static string (not blake3 of `model_json_schema()` — that fails on Pydantic minor bumps per critic security-hidden-assumption.2). A persisted blob with a mismatched version raises `SchemaDrift` and refuses to resume; an explicit `codegenie loop migrate-checkpoint` operator command is the only path forward. **No auto-migration in Phase 6.** | `[B]+[synth — departs from S's dynamic blake3]` |
| 12 | `VulnLedger` is `extra="forbid", frozen=False` | Frozen=False lets LangGraph's idiomatic reducer-merging work; the "no in-place mutation of mutable field values" rule is enforced by a **runtime assertion at node-exit** (the after-node hook diffs `id()` of every list/dict field; in-place mutation raises) plus a Pydantic-side `model_copy` discipline check | `[B]+[synth — resolves critic best-practices.4 and the frozen-fork from critic cross-design.frozen]` |
| 13 | One entry-point name across all phases | The compiled graph is named **`vuln_loop`** and is built by **`build_vuln_loop()`** in `src/codegenie/graph/vuln_loop.py`. The CLI command is **`codegenie loop run <repo> --cve <id>`** (a new subcommand, not an edit of `codegenie remediate`). Phase 7's supervisor will dispatch on `task_type` and call `build_vuln_loop()` or `build_distroless_loop()`; Phase 8's `Supervisor` does the same. | `[synth — resolves critic cross-design "three different entry-point names; Phase 8 supervisor will collide"]` |
| 14 | `cli/remediate.py` is **not modified** | A new `cli/loop.py` (Phase 6 owns) provides `codegenie loop {run, resume, inspect, replay, migrate-checkpoint, render}`. `codegenie remediate` continues to call Phase 3's `RemediationOrchestrator` directly — Phase 6 ships in parallel, not in-place. Phase 7's supervisor dispatch lives in a future `cli/sherpa.py` and likewise does not edit Phase 6's `cli/loop.py`. | `[synth — resolves critic best-practices.5 ("cli/remediate.py edit") + Phase-7 exit criterion]` |
| 15 | Token budget contributed by Phase 6 | 0. The state machine never invokes an LLM; Phase 4's `FallbackTier` is invoked from a single node (`replan_with_phase4`) and Phase 4 owns its own LLM cost budget. | `[P]+[B]` |
| 16 | Public surface introduced by Phase 6 | One package (`src/codegenie/graph/`), one Pydantic state model (`VulnLedger`), one HITL contract pair (`HumanRequest`, `HumanDecision`), one compiled-graph factory (`build_vuln_loop()`), one CLI subcommand (`codegenie loop`). No new ABCs (ADR-0022 Three Strikes — strike one). | `[B]` |
| 17 | `langgraph-cli` posture | Treated as a **dev-only** topology renderer. `codegenie loop render --out tests/golden/vuln_loop_topology.svg` runs it; the CI golden gate diffs the **JSON form** of the topology (`graph.get_graph().to_json()` round-tripped through a canonical key sort), **not** the SVG (SVG layout depends on `langgraph-cli`'s version and is not a stable contract per critic best-practices.hidden-assumption.1). The SVG is committed for human review but **does not fail CI on drift**. | `[B]+[synth — closes critic best-practices.hidden-1 and shared blind spot 3]` |
| 18 | `HumanDecision` is the explicit Phase 6 / Phase 11 contract | Defined in `src/codegenie/graph/hitl.py`. Exported under `docs/contracts/hitl-v0.6.0.json`. The Phase 11 design review (when it happens) is **required** to either consume this shape or amend it via ADR. | `[B]+[synth — closes shared blind spot 2 by *recording* the deferral instead of papering over it]` |
| 19 | Tests verify **intent**, not syntax | The Pydantic field-ACL idea from security and the docstring-`Reads:`/`Writes:` idea from best-practices are both **deferred** (per critic best-practices.2 and security.3): they verify appearance, not behavior. Phase 6 ships per-node unit tests that mock upstream engines and assert *what each node actually produces from a known input*; the AST machinery is dropped. | `[synth — departs from S and B; aligns with global rule §9]` |
| 20 | Strict static checks | `mypy --strict src/codegenie/graph/` clean; `ruff check src/codegenie/graph/` clean; no `Any`, no `cast`, no `# type: ignore` without a justification comment. | `[B]` |

## Architecture

```
              codegenie loop run <repo> --cve <id>                   [synth — new CLI; cli/remediate.py NOT edited]
                              │
                              ▼
              ┌────────────────────────────────────────────────────────┐
              │  src/codegenie/cli/loop.py — codegenie loop {run,...}   │  [synth]
              │    builds checkpointer + VulnLedger; invokes ainvoke    │
              └──────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  src/codegenie/graph/vuln_loop.py — build_vuln_loop()         │  [B]+[synth name]
        │                                                              │
        │  Module-level compile (P) inside lazy singleton (synth):      │  [P+synth]
        │    _COMPILED: CompiledGraph | None = None                     │
        │    def build_vuln_loop(*, checkpointer, max_attempts=3,       │
        │                        force_rebuild=False) -> CompiledGraph: │
        │      global _COMPILED                                         │
        │      if _COMPILED is None or force_rebuild:                   │
        │        _COMPILED = _build(max_attempts).compile(              │
        │          checkpointer=checkpointer,                           │
        │          interrupt_before=["await_human"])                    │
        │      return _COMPILED                                         │
        │                                                              │
        │  Tests/CLI pass `force_rebuild=True` when a new checkpointer  │
        │  path is required, eliminating critic performance.4's flaw.   │
        │                                                              │
        │  StateGraph[VulnLedger]:                                      │
        │    nodes: ingest_cve, select_recipe, apply_recipe,            │
        │           rag_lookup, replan_with_phase4, validate_in_sandbox,│
        │           record_attempt, await_human, emit_artifact,         │
        │           escalate                                            │
        │                                                              │
        │  Edges (every conditional edge is a pure (state) -> Literal):│
        │    START          → ingest_cve                                │
        │    ingest_cve     → select_recipe                             │
        │    select_recipe  → {matched: apply_recipe, miss: rag_lookup} │
        │    apply_recipe   → validate_in_sandbox                       │
        │    rag_lookup     → {hit: apply_recipe, miss:                 │
        │                       replan_with_phase4}                     │
        │    replan_with_phase4 → apply_recipe                          │
        │    validate_in_sandbox → record_attempt                       │
        │    record_attempt → {passed:           emit_artifact,         │
        │                      retry_phase4:     replan_with_phase4,    │  ← retry re-enters Phase 4 (synth — exit-#19)
        │                      retry_exhausted:  await_human,           │
        │                      non_retryable:    await_human}           │
        │    await_human    → {continue:   replan_with_phase4,          │
        │                      override:   emit_artifact,               │
        │                      abort:      escalate}                    │
        │    emit_artifact  → END                                       │
        │    escalate       → END                                       │
        │                                                              │
        │  Checkpointer: per-workflow AsyncSqliteSaver                  │  [S+synth]
        │    path: .codegenie/loop/checkpoints/<workflow_id>.sqlite3    │
        │    aiosqlite, WAL=on, synchronous=NORMAL,                     │
        │    fsync at every node-boundary (no background queue)         │  [synth — closes critic perf.2]
        │    file mode 0600                                             │  [S]
        │                                                              │
        │  interrupt_before=["await_human"] — single interrupt site     │  [B]
        └──────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  VulnLedger (Pydantic; extra="forbid", frozen=False;          │  [B+synth]
        │                JSON-serializable end-to-end)                  │
        │                                                              │
        │  ── identity ──                                              │
        │     schema_version: Literal["v0.6.0"]                         │  [B+synth — static, not dynamic blake3]
        │     workflow_id: str            thread_id: str                │
        │     repo_path: Path             advisory: AdvisoryRef         │
        │                                                              │
        │  ── routing ──                                               │
        │     last_engine: Literal["recipe","rag","phase4_llm"] | None  │
        │     last_node:   str                                         │
        │                                                              │
        │  ── work-in-progress (paths, not bodies — commitment §2.7) ──│
        │     recipe_selection: RecipeSelection | None     # Phase 3   │
        │     rag_hit:          RagHit | None              # Phase 4   │
        │     patch:            PatchRef | None  # path + blake3       │
        │     prior_attempts:   list[AttemptSummary]       # Phase 5   │
        │                                                              │
        │  ── gate outcome (per gate transition) ──                    │
        │     current_gate_id: str | None                              │
        │     retry_count:     int = 0   # reset on new gate transition│  [synth — ADR-0014 per-gate]
        │     max_attempts:    int = 3                                 │
        │     last_outcome:    GateOutcome | None    # Phase 5         │
        │                                                              │
        │  ── HITL ──                                                  │
        │     human_request:  HumanRequest | None                      │
        │     human_decision: HumanDecision | None                     │
        │                                                              │
        │  ── audit ──                                                 │
        │     chain_head: bytes         # extends Phase 5 chain        │
        │     events:     list[GraphEvent]                             │
        └──────────────────────────────────────────────────────────────┘

  Package layout (Phase 6 additions; zero edits to Phase 0–5 source):
  src/codegenie/
    graph/                            ← NEW
      __init__.py                     ← exports: build_vuln_loop, VulnLedger,
                                                 HumanRequest, HumanDecision
      vuln_loop.py                    ← build_vuln_loop() — declarative topology
      state.py                        ← VulnLedger + helper Pydantic models
      hitl.py                         ← HumanRequest, HumanDecision Pydantic
      edges.py                        ← every conditional-edge predicate
      events.py                       ← GraphEvent + emit_event helper
      checkpointer.py                 ← AuditedSqliteSaver wrapping AsyncSqliteSaver
      nodes/
        __init__.py
        ingest_cve.py
        select_recipe.py
        apply_recipe.py
        rag_lookup.py
        replan_with_phase4.py       ← invokes Phase 4 FallbackTier.run(... prior_attempts=...)
        validate_in_sandbox.py      ← invokes Phase 5 GateRunner.run_one(...)
        record_attempt.py           ← writes Phase 5 RetryLedger entry
        await_human.py              ← the only file that calls interrupt()
        emit_artifact.py
        escalate.py
    cli/
      loop.py                         ← codegenie loop {run, resume, inspect, replay,
                                                          migrate-checkpoint, render}

  Fence-CI updates (extend Phase 0's policy):
    graph/         may NOT import anthropic | chromadb | sentence-transformers
    graph/edges.py may NOT import random | time | os | datetime
                    (datetime.fromisoformat for parsing is whitelisted)
    graph/nodes/*  may NOT import codegenie.graph.nodes (cross-node fence)
    graph/         may import langgraph, aiosqlite, pydantic, click

  Phase 0–5 source: untouched.
  ADR-P5-002's `prior_attempts: list[AttemptSummary] = []` kwarg on
  Phase 4's FallbackTier.run is the seam Phase 6 uses; it already exists.
  Phase 5's GateRunner.run_one(...) is what Phase 6 calls per gate attempt;
  the body of Phase 5's for-loop becomes the LangGraph cycle.
```

## Components

### 1. `VulnLedger` — the state ledger

- **Provenance:** [B]+[synth]
- **Purpose:** The single Pydantic-typed contract every node reads from and writes to. The checkpointer serializes this and only this. ADR-0002's "all state ledgers are typed Pydantic models — no `dict[str, Any]`" is the contract here.
- **Interface:** `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=False)`. All field types are concrete Phase 3/4/5 Pydantic models or stdlib types. No `Any`. JSON-serializable end-to-end (`Path → str`, `bytes → base64`, `datetime → ISO 8601`).
- **Internal design:**
  - `schema_version: Literal["v0.6.0"]` — a static literal, not `blake3(model_json_schema())`. The critic landed: Pydantic minor bumps reshuffle `model_json_schema()` output, so the dynamic version flips constantly. The static literal is bumped manually by the engineer making the change; CI's golden checkpoint fixtures (under `tests/fixtures/checkpoints/v0.6.0/`) guard against accidental field changes.
  - `frozen=False` — picked because LangGraph's `model_copy(update=...)` idiom is what we want at the node-return boundary. The "no in-place mutation of mutable field values" rule (e.g., `state.prior_attempts.append(...)`) is enforced by a **runtime after-node hook** that diffs `id()` of every list/dict field; an `id()` match with a content mismatch raises `LedgerMutatedInPlace`. This is the runtime version of the AST lint best-practices proposed; it cannot be evaded.
  - `retry_count` is **scoped per gate transition** (ADR-0014). `record_attempt` resets `retry_count = 0` whenever `current_gate_id` changes; otherwise increments. `await_human.apply_decision` resets to 0 when `action="continue"`.
  - `chain_head: bytes` extends Phase 5's `RetryLedger.head()` (read at graph entry); every `record_attempt` write extends the chain via Phase 5's `RetryLedger.record(...)`. There is **one** BLAKE3 chain across Phases 2–6; Phase 6 does not mint a second.
- **Why this choice over the alternatives:** The critic's `frozen` fork was real: security's `frozen=True` requires replacing LangGraph reducer-merging with a custom `@reducer` dispatcher, which fights ADR-0002 ("use LangGraph's mature tooling for free"). Best-practices' `frozen=False` matches the idiom but admits the AST lint claim is hand-waved. The synthesizer chose `frozen=False` (best-practices) but replaced the AST lint with a **runtime id() diff** that actually catches in-place mutation — closing the lint gap the critic exposed.
- **Tradeoffs accepted:**
  - One large flat Pydantic model rather than a hierarchy (no nested namespaces). ADR-0022 (Three Strikes) — vuln is strike one; defer the hierarchy.
  - Reducer-merging is LangGraph's, not custom; the runtime-id-diff hook is the single piece of custom dispatch we ship.

### 2. `build_vuln_loop()` — the lazy-singleton compiled graph

- **Provenance:** [P]+[B]+[synth]
- **Purpose:** Express the Phase 3/4/5 pipeline as a deterministic LangGraph; pay the ~80 ms compile cost once per worker (P's optimization) without making the checkpointer a module-level constant (critic performance.4's contradiction).
- **Interface:** `build_vuln_loop(*, checkpointer, max_attempts=3, force_rebuild=False) -> CompiledGraph`.
- **Internal design:**
  - The compiled graph is cached in a module-level `_COMPILED` after first call. Tests pass `force_rebuild=True` to swap checkpointers without breaking isolation. Production passes the same checkpointer for the worker's lifetime, so the cache hits.
  - Nodes are plain **sync** functions returning `state.model_copy(update={...})`. LangGraph supports sync nodes inside an `ainvoke` driven by an async checkpointer — best-practices' "sync nodes in async graphs creates a stack-jumping debugging trap" warning is acknowledged; we accept the trap in exchange for keeping every node's body shape obvious (every node is a `def`, no `async`). The single async surface is the checkpointer; LangGraph bridges sync nodes to it via its standard thread-pool. The critic's worry (best-practices.hidden-assumption.3) is real but the mitigation is "test it" — the replay test (`test_replay_after_kill.py`) drives a sync-node async-checkpointer graph end-to-end and that is the canary.
  - The compile is locked at module import time after the first `build_vuln_loop()` call. Hot-reloading a node body requires the test fixtures or the operator to pass `force_rebuild=True`. Acceptable; Phase 9 (Temporal) restarts workers on deploy anyway.
- **Why this choice over the alternatives:** Module-level `VULN_LOOP: CompiledGraph = ...` (performance's original) is dead-on-arrival per critic performance.4 — the `--checkpointer-db` flag and tests cannot work. Per-invocation compile (best-practices' default) pays the 80 ms on every CLI run. The lazy-singleton with `force_rebuild` keeps both — the common case hits the cache; the test/CLI-override case explicitly busts it.
- **Tradeoffs accepted:**
  - Tests must remember to pass `force_rebuild=True` when they swap checkpointers — documented in `tests/graph/conftest.py`'s docstring.

### 3. `AuditedSqliteSaver` — durable, per-workflow, integrity-verified checkpointer

- **Provenance:** [S]+[B]+[synth]
- **Purpose:** Persist `VulnLedger` between nodes, survive process kill, extend the BLAKE3 audit chain, and refuse to read a tampered checkpoint.
- **Interface:** Subclasses LangGraph's `AsyncSqliteSaver`. Drop-in replacement; same `BaseCheckpointSaver` protocol.
- **Internal design:**
  - **Per-workflow SQLite file** at `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`. One writer per file. Concurrency across files. File mode `0600` enforced at open time; if the file exists with looser permissions, the saver raises `CheckpointerInsecure` and refuses to use it (security's posture, kept).
  - `WAL=on, synchronous=NORMAL`, **fsync at every node-boundary write** (no background queue). Performance's "checkpoint returns when queued" trick is dropped — critic performance.2 landed: a 50 ms durability gap is state loss, and the exit criterion forbids state loss. We trade some throughput for correctness; the throughput test (Goal 9) measures what we get.
  - **JSON serializer only.** No MessagePack. Critic security.5 said this defense is unmotivated *in security's threat model*, but the synthesizer keeps JSON because: (a) `sqlite3` CLI can read JSON checkpoints (incident response), (b) deserialization surface is smaller, (c) `langgraph-cli` dev tooling reads JSON cleanly. The 64 KB hard cap on blobs is **dropped** — it would fail on legitimate `prior_attempts` payloads (critic security.5's second point). Blobs grow with `prior_attempts`; if they ever exceed 32 KB we surface it via a metric, not a hard fail.
  - **BLAKE3 chain extension on every checkpoint write.** Computed `blake3(json_bytes || prev_chain_head)`; the digest is appended as a `checkpoint.write` event to the **existing Phase 5 `RetryLedger` chain file** (`.codegenie/remediation/<run-id>/audit/<run-id>.jsonl`) — there is one chain, not two. The critic's hidden-assumption.1 (whether Phase 5's chain and Phase 6's chain are the same file) is resolved by this synthesis: **same file**, extended by `record_attempt` for attempts and by `AuditedSqliteSaver.put` for checkpoint frames. On `get`, the saver recomputes the digest and matches against the chain's most recent `checkpoint.write` for the same `(thread_id, checkpoint_id)`; mismatch raises `CheckpointTampered`. This catches offline DB-only edits.
  - **Schema-version check on resume.** The persisted blob's `schema_version` literal is compared to the current code's `Literal["v0.6.0"]`. Mismatch → `SchemaDrift`, refuse to resume; operator runs `codegenie loop migrate-checkpoint --from <old> --to <new>` (Phase 6 ships the command but only `v0.6.0` exists for now; later phases add migrations under `graph/migrations/`).
- **Tradeoffs accepted:**
  - Fsync-per-node-boundary is slower than performance's queued path. Goal 9's throughput test calibrates the cost; if SQLite can't hit ~100 writes/s with this configuration on the CI runner, ADR-P6-006 fires and Phase 9's Postgres migration is pulled forward.
  - The chain is appended in two places (Phase 5's `RetryLedger.record` for attempts, Phase 6's `AuditedSqliteSaver.put` for checkpoints). Both write the same file under `O_APPEND`; both come from the same single-orchestrator process, so there is no cross-process race. CI test (`test_chain_single_writer.py`) asserts both writers acquire a single `RetryLedger`-owned `threading.Lock` before appending.

### 4. `@pure_edge`-marked conditional-edge predicates

- **Provenance:** [B]+[S]
- **Purpose:** Routing decisions are deterministic, pure, and statically auditable.
- **Interface:** Each predicate lives in `graph/edges.py`, takes `VulnLedger`, returns a `Literal[...]`. Decorated with `@pure_edge`, which: (a) registers the function for property-tests; (b) at import time, AST-inspects the body and rejects imports of `random`, `time`, `os`, `datetime` (with `datetime.fromisoformat` whitelisted for parsing).
- **Internal design:**
  ```python
  @pure_edge
  def route_after_attempt(state: VulnLedger) -> Literal[
      "passed", "retry_phase4", "retry_exhausted", "non_retryable"
  ]:
      assert state.last_outcome is not None
      if state.last_outcome.passed:
          return "passed"
      if not state.last_outcome.retryable:
          return "non_retryable"
      if state.retry_count >= state.max_attempts:
          return "retry_exhausted"
      return "retry_phase4"   # ADR-0014 + Phase 5 exit-#19
  ```
  - **Single retry edge: `retry_phase4`.** Not three (best-practices' `retryable_{engine}` f-string). On retry, Phase 4's `FallbackTier.run(..., prior_attempts=[AttemptSummary(...)])` is invoked. Phase 4 internally decides recipe / RAG / LLM — Phase 6 does not. This honors Phase 5 exit-criterion #19 (Phase 4 re-entry produces a *different* `RecipeApplication`) and rejects performance's "same recipe re-applied" cheap path.
  - The same-signature flake-detection branch (security's design) is **kept** as a refinement of `non_retryable`: if `len(prior_attempts) >= 2 and same_signature(prior_attempts[-1], prior_attempts[-2])`, the edge returns `non_retryable` instead of `retry_phase4`. This prevents burning the retry budget on a deterministic recurring failure.
  - **Hypothesis property tests** at CI time: 10k generated `VulnLedger` instances assert determinism (`route_after_attempt(s) == route_after_attempt(s)`). Critic security.4 caught that the property test runs on *synthetic* states while production states carry timestamps from upstream `AttemptSummary`s; the synthesizer's response: predicates may **read** timestamp-bearing fields, but every predicate must return a label that depends *only* on the boolean / counter / Literal projections of state. We ship a stricter unit test (`test_edge_label_depends_only_on_projection.py`) that pins each predicate's label to the subset of state it actually consumes; mutating timestamps in fixtures must not change the label.
- **Tradeoffs accepted:** Adding a new branch is two diffs (predicate + `add_conditional_edges` mapping in `vuln_loop.py`). The golden-graph topology test (Component 8) fails on the second diff if either is missing.

### 5. `validate_in_sandbox` + `record_attempt` — Phase 5 gate, lifted (not re-implemented)

- **Provenance:** [B]+[synth]
- **Purpose:** Express Phase 5's three-retry gate as a graph cycle whose `RetryLedger` output is byte-identical to Phase 5's sync `for`-loop ledger.
- **Interface:**
  - `validate_in_sandbox(state) -> state'` — calls Phase 5's `GateRunner.run_one(transition, ctx)` (single attempt; not the looped `run`). `ctx.prior_attempts` is filled from `state.prior_attempts`. Returns state with `last_outcome` updated.
  - `record_attempt(state) -> state'` — writes Phase 5's `RetryLedger.record(...)`, increments `retry_count` per-gate (resets if `current_gate_id` changed), appends `AttemptSummary` to `state.prior_attempts`.
- **Internal design:**
  - Phase 5 ships **`GateRunner.run` (the looped version)** as its current API. The Phase 5 `for attempt in range(1, max_attempts+1)` body is what Phase 6 lifts. We do **not** ask Phase 5 to expose a new `run_one` method (critic best-practices.cross-design.3 called out that this would be a Phase 5 source touch, which violates Phase 6's "no Phase 0–5 edit" budget). Instead:
    - Phase 5's `GateRunner` already factors its single-attempt body into a private helper (`_run_one_attempt`); this helper is **already** module-public via being a top-level function in `gates/runner.py` (per Phase 5 final-design's package layout). Phase 6 calls it. If that helper is in fact private in the shipped Phase 5 code, this design ships **ADR-P6-001: Phase 5 `GateRunner._run_one_attempt` is promoted to `run_one` — a renaming-only additive change** (the original `GateRunner.run` is unchanged; a new public name is added). This is the *one* and *only* Phase-5 source touch Phase 6 makes; it is documented and surgical (per CLAUDE.md Rule 3). Best-practices' design had a similar but undocumented assumption (its node calls `GateRunner.run-one`); we make it explicit.
  - The parity test (`tests/integration/test_retry_semantics_parity.py`) runs the same fixture through Phase 5's sync `GateRunner.run` and through Phase 6's cycle; asserts byte-identical `attempts.jsonl`. This is the single canary that the two paths have not drifted.

### 6. `replan_with_phase4` — the one node that invokes Phase 4 on retry

- **Provenance:** [synth — resolves critic performance.1 + Phase 5 exit-#19]
- **Purpose:** When `route_after_attempt → "retry_phase4"` fires, this node invokes Phase 4's `FallbackTier.run(..., prior_attempts=state.prior_attempts)` and produces a new `patch` (distinct bytes from the prior attempt). It is **also** the destination of `route_after_human(continue)` so HITL "continue" routes through Phase 4 re-planning, not into a stale recipe.
- **Interface:** `replan_with_phase4(state) -> state'`. Reads `advisory`, `recipe_selection`, `prior_attempts`. Writes `patch`, `last_engine="phase4_llm"` (or whatever Phase 4 reports back as the `engine_used` discriminator).
- **Internal design:** Delegates entirely to Phase 4. The fence-wrapping, canary checks, and cost-cap enforcement are Phase 4's. Phase 6 imports `from codegenie.planner.fallback_tier import FallbackTier`. This is the *only* Phase 6 node that imports anything LLM-adjacent; the `graph/` fence policy allows it because `planner.fallback_tier` is the Phase 4 boundary (not `anthropic`).

### 7. `await_human` + `HumanRequest` / `HumanDecision` — the only `interrupt()` site

- **Provenance:** [B]+[synth — security's Ed25519 stack deferred]
- **Purpose:** One `interrupt()` call in the codebase, one resume contract.
- **Interface:**
  ```python
  class HumanRequest(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      reason: Literal["retry_exhausted", "non_retryable_signal"]
      summary: str            # ≤ 4 KB, sanitized
      evidence_paths: dict[str, Path]
      failing_signals: list[str]
      chain_head_at_pause: bytes
      requested_at: datetime

  class HumanDecision(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      action: Literal["continue", "override", "abort"]
      operator: str           # display name; not authenticated in Phase 6
      decided_at: datetime
      note: str = ""          # ≤ 1 KB free-text
      # action semantics:
      #   continue → route to replan_with_phase4; retry_count reset to 0
      #   override → mark patch accepted, skip remaining gates, go to emit_artifact
      #   abort    → escalate, terminal
  ```
- **Internal design:**
  - `interrupt_before=["await_human"]` — LangGraph pauses *before* entering the node; the checkpointer persists state; the CLI exits with code `12` (graph_awaits_human).
  - On resume, `await_human` runs; `HumanDecision.model_validate(...)` rejects malformed payloads loudly; `route_after_human` routes on `decision.action`.
  - **No Ed25519, no operator-key file, no two-step CLI signing.** Security's full stack is deferred to Phase 11 (where real GitHub PR comments become the HITL signal source) and Phase 16 (where multi-tenant SSO/RBAC lands). The justification is critic security.1: ~600 LOC of crypto plumbing in a phase the roadmap scopes to "LangGraph + Pydantic + SQLite + langgraph-cli" is scope creep that the load-bearing-commitment §2.5 ("Extension by addition") explicitly forbids.
  - **Single-host trust posture.** The `0600` file-mode posture on the checkpointer (security) is kept. The local POC's trust boundary is "you trust the local host"; tamper-evidence (the BLAKE3 chain integrity check on resume) protects against accidental or remote-write tampering of the on-disk state. The full operator-authentication stack waits for the phase where it has a real consumer.
  - **`HumanDecision.note` does not flow into any LLM prompt.** Critic flagged that security's `notes_blake3` + fence-wrap suggests Phase 6 participates in LLM prompt construction. We explicitly forbid it: `note` is logged to the audit chain and is for human-to-human reading only. Phase 4's prompt builder consumes `prior_attempts.prior_failure_summary` (the structured Phase 5 field) — not `HumanDecision.note`.
- **Why this choice over the alternatives:** Security's full operator-key stack is overscope; best-practices' `aupdate_state(..., {"human_decision": dict})` is under-scoped (no typing). The synthesizer keeps best-practices' shape with security's typed-resume-only invariant (`HumanDecision.model_validate` rejects malformed inputs) and **defers** the cryptographic resume-authentication layer to Phase 11. Goal 18 commits the contract shape to disk so Phase 11 either consumes it or amends it deliberately.
- **Tradeoffs accepted:**
  - Local resume is not cryptographically authenticated. On a single-operator dev box this matches the threat model. The risk is recorded under §Risks and is the explicit subject of ADR-P6-004.

### 8. Golden-graph topology snapshot (JSON, not SVG)

- **Provenance:** [B]+[synth]
- **Purpose:** Catch unintended topology changes at CI time.
- **Interface:** `tests/graph/test_topology_golden.py` exports `build_vuln_loop().get_graph().to_json()`, canonical-key-sorts the dict, diffs against `tests/golden/vuln_loop_topology.json`.
- **Internal design:** The JSON form is the contract (stable across `langgraph-cli` versions; the SVG is not — critic best-practices.hidden-1). The SVG is also rendered and committed (`docs/phases/06-sherpa-state-machine/vuln_loop.svg`) for human review at PR time, but **does not fail CI on drift**. Updating either golden is a deliberate `pytest --update-golden` invocation.

### 9. CLI surface — `codegenie loop`

- **Provenance:** [synth — replaces all three lenses' overlapping CLI plans]
- **Purpose:** Operator and test harness for the state machine. **Does not edit `cli/remediate.py`.**
- **Interface:**
  - `codegenie loop run <repo> --cve <id>` — entry; builds checkpointer, builds initial `VulnLedger`, invokes `build_vuln_loop().ainvoke(initial, config={thread_id})`.
  - `codegenie loop resume <thread_id> --decision continue|override|abort [--note "..."] [--operator <name>]` — typed HITL resume; constructs `HumanDecision`, calls `graph.aupdate_state(..., as_node="await_human")`, then `graph.ainvoke(None, config)`.
  - `codegenie loop inspect <thread_id>` — pretty-prints `graph.get_state_history(config)`.
  - `codegenie loop replay <thread_id> --from <checkpoint_id>` — deterministic replay harness.
  - `codegenie loop migrate-checkpoint --from <old> --to <new>` — schema-drift migration (no migrations registered in v0.6.0; the command exists to record the path).
  - `codegenie loop render --out <path>` — `langgraph-cli` topology renderer wrapper; writes both `.json` (for the CI golden) and `.svg` (for human review).
- **Why this choice over the alternatives:** Performance's `codegenie loop run` and best-practices' edit of `cli/remediate.py` collide; performance's name wins (it makes the Phase-6/Phase-3 entry-point split explicit) and the `cli/remediate.py` edit is dropped (closes critic best-practices.5 and protects Phase 7's "no Phase 0–6 source touched" exit criterion).

### 10. Cost-ledger seam (forward-compat for Phase 13)

- **Provenance:** [synth — closes critic best-practices.things-missed.1]
- **Purpose:** Phase 6 emits *enough* cost-relevant telemetry that Phase 13's ledger can compute it without retroactively editing Phase 6.
- **Interface:** Every node emits one `GraphEvent` per entry/exit with `(node_name, started_at, ended_at, wall_clock_ms)`. The `RetryLedger.record` Phase 5 entry already carries `cost_tokens` for the Phase 4 path; `validate_in_sandbox` emits `sandbox_wall_clock_ms` per attempt. Phase 13 consumes both streams; Phase 6 does not compute ROI itself.
- **Internal design:** A single `events.emit(state, node_name, kind, fields)` helper writes to `state.events` (in-state, for replay debugging) and emits an OpenTelemetry span (when the OTel exporter is configured by Phase 13). Phase 6 does not require OTel to be present.

## Data flow

End-to-end walk for the **Phase 5 exit-criterion case** (vuln remediation; recipe miss → RAG miss → Phase 4 LLM produces patch-attempt-1 that breaks a test → retry-1 re-enters Phase 4 with `prior_attempts` → distinct patch-attempt-2 passes the gate):

1. **t=0 (cold start, paid once per worker):** Worker imports `codegenie.graph.vuln_loop`. First call to `build_vuln_loop(checkpointer=AuditedSqliteSaver(...))` runs the `_build()` once (~80 ms) and caches `_COMPILED`. Subsequent workflows on the same worker reuse the compiled graph. *(P's optimization, S/B-safe via the lazy-singleton.)*
2. **t=0+ε:** `codegenie loop run` builds the initial `VulnLedger(schema_version="v0.6.0", workflow_id=..., thread_id=workflow_id, repo_path=..., advisory=..., chain_head=RetryLedger.head_from_phase5(...))` and calls `await VULN_LOOP.ainvoke(initial, config={"configurable": {"thread_id": workflow_id}})`.
3. **t≈10 ms:** Entry checkpoint fsync'd to `<workflow_id>.sqlite3`; chain extended with `checkpoint.write` event. `ingest_cve` runs; reads pinned CVE snapshot; ≤ 30 ms. **t≈30 ms:** `select_recipe` runs; recipe catalog miss; edge `miss` → `rag_lookup`.
4. **t≈60 ms:** `rag_lookup` runs; Phase 4's `RagTier` returns score < 0.85; edge `miss` → `replan_with_phase4`.
5. **t≈100 ms:** `replan_with_phase4` runs; `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=[])`. LLM produces a structured plan; patch lands at `.codegenie/remediation/<run-id>/patch-attempt-1.diff`. Wall-clock p50 ≤ 5 s (Phase 4's existing RAG-miss budget).
6. **t≈5 s:** `apply_recipe` applies the patch to the working tree (delegates to Phase 3's `RecipeEngine.apply` with the Phase 4-produced plan as input).
7. **t≈6 s:** `validate_in_sandbox` calls `GateRunner.run_one(transition=stage6_validate, ctx=GateContext(worktree, advisory, recipe_selection, prior_attempts=[]))`. Phase 5 boots the sandbox; runs build+install+test; returns `GateOutcome(passed=False, retryable=True, failing_signals=["tests"], evidence_paths=...)`.
8. **t≈90 s:** `record_attempt` runs; Phase 5's `RetryLedger.record(Attempt(attempt_id=1, sandbox_run_id=..., signals=os, outcome=..., prior_failure_summary=...))`. `state.prior_attempts += [AttemptSummary(...)]`. `retry_count += 1` (now 1; same `current_gate_id`). `chain_head` advances. Checkpoint fsync'd.
9. **t≈90.1 s:** `route_after_attempt(state)` reads `retry_count=1, max_attempts=3, last_outcome.passed=False, last_outcome.retryable=True` → returns `"retry_phase4"`. Edge fires; control returns to `replan_with_phase4`.
10. **t≈90.2 s:** `replan_with_phase4` re-enters Phase 4 with `prior_attempts=[AttemptSummary(failing_signals=["tests"], prior_failure_summary="1 test failed; first: auth/jwt.test.ts: should reject expired tokens", evidence_paths=...)]`. Phase 4's prompt builder fence-wraps `prior_failure_summary` (truncated 8 KB, canary-checked — Phase 4's existing defense), runs the LLM with the second cassette `cassette-attempt-2.yaml`, produces a **different** `RecipeApplication` (distinct `patch_blake3`). Patch lands at `.codegenie/remediation/<run-id>/patch-attempt-2.diff`.
11. **t≈95 s:** `apply_recipe` reapplies the new patch; `validate_in_sandbox` runs the gate again; this time `GateOutcome(passed=True, ...)`.
12. **t≈140 s:** `record_attempt` writes the second `Attempt(attempt_id=2, ...)` to `attempts.jsonl`. Two entries with distinct `attempt_id`, distinct `prior_failure_summary`, distinct `sandbox_run_id`, **distinct patch bytes**. (Phase 5 exit-criterion #19 satisfied; closed by `test_retry_reenters_phase4.py`.)
13. **t≈140.1 s:** `route_after_attempt` returns `"passed"`. Edge fires; `emit_artifact` runs; writes `RemediationReport` to disk. Workflow ends.

**Total wall-clock:** ~140 s, dominated by two sandbox boots (Phase 5 cost). LangGraph envelope contribution: ~50 ms total across ~10 node transitions + ~12 checkpoint fsyncs. The canary regression test (Goal 6) is what holds this honest in CI.

**HITL variant:** if the gate fails three times consecutively at the same transition, `route_after_attempt` returns `"retry_exhausted"`; `await_human` is the next node; LangGraph (configured with `interrupt_before=["await_human"]`) pauses *before* entering, fsync'd the checkpoint, CLI exits 12. Operator runs `codegenie loop resume <thread_id> --decision continue`. LangGraph rehydrates from the interrupt frame; `aupdate_state` injects the `HumanDecision`; `await_human` runs; `route_after_human` returns `"continue"`; control routes to `replan_with_phase4`; `retry_count` is reset to 0 (HITL `continue` semantics). Workflow proceeds.

**Kill-and-resume variant:** at any node boundary, SIGKILLing the orchestrator process leaves the SQLite file with the last fsync'd checkpoint. A new orchestrator process invocation of `codegenie loop run <repo> --cve <id>` (same workflow content-address → same `workflow_id` → same `thread_id`) calls `build_vuln_loop()` with the same checkpointer path; LangGraph rehydrates from the persisted state; the killed node re-runs from its entry. Replay produces a byte-identical final `RemediationReport`.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Worker killed mid-node | LangGraph on next `ainvoke(config={thread_id})` | None — the in-flight node re-runs from its entry checkpoint | Resume produces byte-identical final state (canonical exit criterion) | [P]+[B]+[synth] |
| Worker killed mid-checkpoint-write | aiosqlite WAL recovery on next open | In-flight WAL frame rolled back | Resume from previous fsync'd frame; node re-runs | [P]+[synth] |
| `<workflow_id>.sqlite3` tampered offline | `AuditedSqliteSaver.get` BLAKE3 digest mismatch against the chain's last `checkpoint.write` event | Refuse to resume; raise `CheckpointTampered`; chain records `checkpoint.tamper.detected` | Operator runs `codegenie loop inspect <thread_id>` + `codegenie audit verify` | [S]+[synth] |
| Phase 5 chain head mismatch on Phase 6 startup | `RetryLedger.head_from_phase5()` returns a value that does not match the first `checkpoint.write`'s `prev` | Raise `AuditChainCorrupted`; refuse to run any workflow | Operator triage; closes critic security-hidden-assumption.1 | [synth] |
| Schema drift between persisted blob and current code | `schema_version` Literal mismatch on resume | Raise `SchemaDrift`; refuse to resume | `codegenie loop migrate-checkpoint --from <old> --to <new>` (no migrations registered in v0.6.0) | [B]+[synth] |
| Gate retry exhaustion (3 fails at same transition) | `route_after_attempt` returns `"retry_exhausted"` | `await_human` runs; LangGraph pauses on `interrupt_before` | `codegenie loop resume` with `continue`, `override`, or `abort` | [B]+[P]+[synth] |
| Non-retryable signal from Phase 5 (`outcome.retryable=False`) | `route_after_attempt` returns `"non_retryable"` | `await_human` runs; LangGraph pauses | Same as above | [B]+[S] |
| Same-signature flake (≥2 consecutive identical failure signatures) | `route_after_attempt` detects via `same_signature(prior_attempts[-1], prior_attempts[-2])` | Routes to `non_retryable` early; does not burn retry budget | HITL via `await_human` | [S]+[synth] |
| In-place mutation of a `VulnLedger` mutable field | Runtime after-node hook: `id()` of list/dict field unchanged but content changed | Raise `LedgerMutatedInPlace`; node fails | Author fix; lint catches in PR review | [synth — replaces B's AST lint with runtime id() check] |
| Pydantic validation fails on a deserialized checkpoint | `AuditedSqliteSaver.get` triggers `VulnLedger.model_validate` | Raise `CheckpointSchemaMismatch` | Operator triage; deliberate migration via `codegenie loop migrate-checkpoint` | [S]+[B] |
| `HumanDecision` malformed on resume | `HumanDecision.model_validate(decision)` in `await_human` | Raise `ValidationError` from LangGraph; workflow halts, state preserved | Operator re-submits with corrected JSON | [B]+[synth] |
| World-readable `<workflow_id>.sqlite3` | `AuditedSqliteSaver` startup check (file mode != `0600`) | Raise `CheckpointerInsecure`; refuse to run | `chmod 600 <path>` per the printed hint | [S] |
| SQLite throughput insufficient for Phase 6's measured workload | Goal 9 test reports < 100 writes/s | Block merge of any work that depends on Phase 6 ops at scale; trigger ADR-P6-006 | Pull Phase 9 Postgres migration earlier | [synth — closes shared blind spot] |
| Phase 5 `_run_one_attempt` not promoted to public `run_one` | CI lint asserts `codegenie.gates.runner.run_one` is importable from `graph/nodes/validate_in_sandbox.py` | Build fails | ADR-P6-001 promotion lands | [synth] |
| `codegenie loop render` `langgraph-cli` version drift | SVG diff *not* in CI; JSON golden diff fails | JSON golden update is the only blocker | Update `tests/golden/vuln_loop_topology.json` via `pytest --update-golden`; verify topology change is intentional | [B]+[synth] |

## Resource & cost profile

| Resource | Phase 6 envelope contribution | Total per run (with Phase 3/4/5) | Source-of-numbers |
|---|---|---|---|
| Tokens per run (Phase 6 only) | 0 | RAG hot: 0; LLM cold: Phase 4's budget unchanged | [P] |
| Wall-clock p50 (RAG hot path) | +5 s envelope | ~95 s | [P]; envelope budget asserted by canary, not measured at design time |
| Wall-clock p50 (LLM cold + 1 retry) | +8 s envelope | ~140 s (one extra Phase 4 invocation + one extra sandbox boot) | [P]+[synth] |
| Per-node LangGraph overhead | **measured by canary in CI**; baseline committed on first run | — | [synth — closes critic performance.3] |
| Memory per worker (loop only) | ≤ 300 MB (langgraph + aiosqlite + Pydantic + GC headroom) | ≤ 2.0 GB total (Phase 4 owns 1.7 GB) | [P] |
| Checkpoint write throughput | **measured** (Goal 9). Performance target: ≥ 100 writes/s sustained on CI runner. If short, ADR-P6-006 fires | — | [synth — replaces performance's unmeasured 800 writes/s claim] |
| Per-workflow checkpoint storage (final) | ~16–48 KB (grows with `prior_attempts`; 64 KB hard cap dropped — critic security.5) | + Phase 5 ledger (~50 KB) + Phase 4 RAG entry (~10 KB) | [synth] |
| Concurrent workflows per host (Phase 6) | unbounded (per-workflow files); Phase 9 Temporal owns horizontal scaling | — | [S]+[synth] |
| CPU per workflow envelope | ≤ 1.5 vCPU avg, ≤ 4 vCPU peak during sandbox spawn (Phase 5 cost) | — | [P] |

Where P's numbers trade against S/B controls: P's "queued, not persisted" checkpointer would push throughput higher but at the cost of state loss on kill — incompatible with exit-criterion 2 ("without state loss"). The synthesis prioritizes correctness; the measured throughput tells us whether SQLite is enough or whether Postgres migration pulls forward. S's 64 KB blob cap would hard-fail on legitimate `prior_attempts` payloads — critic security.5 landed; we drop the cap.

## Test plan

A pyramid: many fast unit tests at the base, fewer integration, very few E2E. **Tests verify intent.** No docstring-AST or field-ACL theater (critic best-practices.2, security.3) — those tests verify appearance, not behavior.

### Layer 0 — Static (~5 s CI)

- `mypy --strict src/codegenie/graph/` clean.
- `ruff check src/codegenie/graph/` clean.
- `tests/graph/test_topology_golden.py` — `graph.get_graph().to_json()` matches `tests/golden/vuln_loop_topology.json` byte-for-byte after deterministic key sort.
- `tests/graph/test_no_cross_node_imports.py` — AST walk; no `graph/nodes/*.py` imports any sibling node.
- `tests/graph/test_fence_loop_edges.py` — no module under `graph/edges.py` imports `random | time | os | datetime` (whitelist: `datetime.fromisoformat`).
- `tests/graph/test_no_anthropic_in_graph.py` — `graph/` does not import `anthropic | chromadb | sentence-transformers` (extends Phase 0's fence).
- `tests/graph/test_pydantic_no_any.py` — `VulnLedger` and `HumanRequest`/`HumanDecision` reachable fields contain no `Any`, `dict[str, Any]`, `object`, untyped `Mapping`.

### Layer 1 — Unit, no graph (~60% of test LOC; ~3 s CI)

- `tests/graph/test_state.py` — `VulnLedger` `extra="forbid"` rejection; JSON round-trip property (Hypothesis); the **runtime in-place-mutation hook** raises `LedgerMutatedInPlace` when a node returns a state with a mutated list-field-by-`id()`.
- `tests/graph/test_edges.py` — every predicate, parametrized over a curated table of `(VulnLedger fixture, expected literal)`; 100% branch coverage on `edges.py`; the table is asserted complete by introspecting each `Literal[...]` return type.
- `tests/graph/test_edges_determinism.py` — Hypothesis property test: 10k generated `VulnLedger` instances; `route_after_attempt(s)` is referentially transparent.
- `tests/graph/test_edge_label_depends_only_on_projection.py` — for every predicate, the label is asserted invariant under permutations of fields the predicate does **not** consume (includes mutating timestamps on `AttemptSummary` — closes critic security.4).
- `tests/graph/test_nodes/test_<node>.py` — one file per node; constructs an input `VulnLedger`, mocks the upstream Phase 3/4/5 engine at the import boundary, invokes the node, asserts the returned ledger's fields.

### Layer 2 — State-transition coverage (~20% of test LOC; ~8 s CI)

- `tests/graph/test_node_transitions.py` — parametrized over `(start-state-fixture, scripted-engine-outcomes, expected-node-sequence)`. Every conditional edge appears in at least one row. The introspection assertion: fixture-fired-edges == the set of edges in the compiled graph. This is the exit-criterion's "every conditional edge exercised" gate.

### Layer 3 — Replay (~5% of test LOC; ~30 s CI)

- `tests/integration/test_replay_after_kill.py` — runs the graph in a subprocess via `multiprocessing`; SIGKILLs during `validate_in_sandbox` (the longest node); restarts; asserts the produced `RemediationReport` and `attempts.jsonl` are byte-identical to a non-killed reference run.
- `tests/integration/test_replay_byte_identical.py` — runs a full workflow; copies the audit chain + the SQLite file; restarts from the same input bundle (same workflow content-address → same `workflow_id`); asserts state at every checkpoint matches.

### Layer 4 — HITL (~5% of test LOC; ~10 s CI)

- `tests/integration/test_hitl_interrupt_and_resume.py` — **the exit-criterion test.** Scripts Phase 5's gate runner to fail twice consecutively at the same transition; asserts `await_human` is reached and `interrupt.raised` is in the audit chain; injects `HumanDecision(action="continue", ...)` via `aupdate_state(..., as_node="await_human")`; asserts the workflow proceeds; scripts the third gate to pass; asserts the workflow reaches `emit_artifact`.
- `tests/integration/test_hitl_override_jumps_to_emit_artifact.py` — same setup; `action="override"`; asserts no further gate attempts; final state is `emit_artifact` with `patch` preserved.
- `tests/integration/test_hitl_abort_terminates.py` — same setup; `action="abort"`; asserts `escalate` runs; exit code 11 (Phase 5's reserved "escalate human" code).
- `tests/integration/test_hitl_malformed_decision_raises.py` — `aupdate_state` with a malformed dict; asserts `ValidationError` at `HumanDecision.model_validate`.
- `tests/integration/test_hitl_persists_across_process_restart.py` — combines HITL + replay; runs in subprocess, kills it at `interrupt_before` checkpoint, resumes in a new process.

### Layer 5 — Parity with Phase 5

- `tests/integration/test_retry_semantics_parity.py` — runs the same fixture scenario through Phase 5's sync `GateRunner.run` *and* Phase 6's cycle; asserts byte-identical `attempts.jsonl`. The day this drifts, one of the two implementations is wrong.
- `tests/integration/test_retry_reenters_phase4.py` — **the exit-criterion #19 test, lifted from Phase 5 into Phase 6.** Asserts `attempts.jsonl` has 2 entries with distinct `attempt_id`, distinct `prior_failure_summary`, distinct `sandbox_run_id`, **distinct patch bytes**; Phase 4's prompt on attempt 2 contains the fence-wrapped summary. (The Phase 5 test uses the synchronous orchestrator; the Phase 6 test uses the graph. Both must pass.)

### Layer 6 — Adversarial (sharply scoped to Phase 6's threat model)

- `tests/adversarial/test_tampered_checkpoint.py` — open `<workflow_id>.sqlite3` out of band, edit `last_outcome.passed` from `False` to `True`, attempt resume. Assert `CheckpointTampered` raised; `checkpoint.tamper.detected` chain event written.
- `tests/adversarial/test_world_readable_checkpoint_refused.py` — `chmod 644 <db>`; attempt resume. Assert `CheckpointerInsecure` raised.
- `tests/adversarial/test_schema_drift_refused.py` — checkpoint under `v0.6.0`; mutate `LoopState.schema_version` literal to `v0.7.0` in source; attempt resume. Assert `SchemaDrift` raised; no auto-migration.

**Deliberately not in scope:** Ed25519/HMAC adversarial tests (deferred to Phase 11/16 with the operator-key infrastructure they belong to). The security design's full adversarial suite is preserved in critique form for those phases.

### Layer 7 — Performance regression (CI gate)

- `tests/perf/test_canary_overhead.py` — 100-no-op-node graph × 1,000 invocations; records p50/p95 to `tests/perf/baseline.json` on first run; subsequent runs assert no >25% regression (closes critic performance.3 — we **measure** instead of **assume**).
- `tests/perf/test_checkpoint_throughput.py` (nightly) — 1,000 serial checkpoints; asserts achieved throughput ≥ 100 writes/s; failure triggers ADR-P6-006.

### Layer 8 — E2E (~1 test; ~120 s CI; `@pytest.mark.slow`)

- `tests/e2e/test_loop_run_vuln_remediation.py` — runs `codegenie loop run ./tests/fixtures/repos/cve-fixture/ --cve CVE-2024-FAKE-NPM`; asserts exit 0, remediation branch exists, `attempts.jsonl` has exactly 1 attempt, `RemediationReport` shape matches Phase 3's contract.

## Risks (top 5)

1. **Phase 5's `_run_one_attempt` may not be public.** Phase 6 needs to call Phase 5's per-attempt entry point. If Phase 5 only ships the looped `run`, Phase 6's ADR-P6-001 promotes a private helper to public — a renaming-only surgical change. If Phase 5's code shape doesn't even factor it that way, Phase 6's compile fails and the synthesizer's "no Phase 0–5 source touch" budget is violated. **Mitigation:** the parity test (`test_retry_semantics_parity.py`) is the canary; the ADR-P6-001 amendment is the recorded edit; the alternative would be to re-implement Phase 5's per-attempt logic in Phase 6 (rejected — drift between two implementations is exactly the wrong outcome).
2. **The `HumanDecision` contract is being defined without Phase 11 input.** All three lenses ship a HITL resume contract; none have asked Phase 11 what the actual signal source will be (GitHub webhook? Slack interactive button? MCP poll?). The shape we ship in `docs/contracts/hitl-v0.6.0.json` may be wrong. **Mitigation:** `HumanDecision` is intentionally minimal — three Literal actions, an `operator: str`, a `note: str`, a `decided_at: datetime`. The Phase 11 design review is gated to either consume or amend this shape via ADR; we ship the contract on disk so it cannot drift silently.
3. **SQLite throughput under realistic load is untested at design time.** All three designs deferred Postgres without measuring SQLite. Goal 9's throughput test is what closes this. If SQLite is genuinely not enough, ADR-P6-006 forces an early Postgres migration — a Phase 9 commitment pulled into Phase 7-or-8. **Mitigation:** measure on CI hardware on first merge; if < 100 writes/s, escalate immediately.
4. **The single-host trust posture is intentionally permissive.** No operator authentication on `codegenie loop resume`. A local user with write access to the home directory can resume any paused workflow with any `HumanDecision`. **Mitigation:** documented in ADR-P6-004; the BLAKE3 chain integrity check still catches *tampering* (offline DB edits); the missing piece is *authentication* of the operator at resume time, which is Phase 11's job (real PR comments tied to real GitHub identities) and Phase 16's job (SSO/RBAC). This is the deliberate scope cut against security's full operator-key stack.
5. **Sync nodes in an async checkpointer graph.** LangGraph supports it; the contract is not perfectly documented. The replay test is the canary. If LangGraph's sync-to-async bridging produces non-deterministic ordering at high concurrency, the parity test against Phase 5's sync loop is the first place that breaks. **Mitigation:** Phase 6 ships single-workflow at a time per worker; concurrency is Phase 9's territory. Until then we exercise the sync-node-async-checkpointer path on every replay test.

## Synthesis ledger

### Vertex count

- Performance: ~58 (12 components + 7 nodes + 15 goals + 9 failure modes + 10 tests + 5 risks)
- Security: ~74 (16 components + 13 attack surfaces + 8 goals + 13 failure modes + 13 adversarial tests + 5 risks + 6 trust-boundary items)
- Best-practices: ~52 (7 components + 10 nodes + 18 goals + 6 layers × ~3 tests + 5 risks)
- **Total decomposed vertices: ~184**, of which the synthesizer scored ~30 as load-bearing conflicts.

### Edges

- AGREE: 21 (e.g., all three pick LangGraph runtime; all three defer Postgres; all three put retry-counter in state; all three commit to a single `interrupt()` site for HITL; all three pick `extra="forbid"`; all three commit to JSON-serializable state; all three pick file-system-only node side effects)
- CONFLICT: 14 (`frozen` on state ledger; retry-counter scope; Phase 4 re-entry on retry; checkpointer concurrency model; HITL resume authentication; entry-point naming; `cli/remediate.py` edit; queued-vs-fsync checkpoint writes; serializer choice; field-ACL machinery; module-level vs lazy-singleton compile; SVG vs JSON golden; same-signature flake detection; sensitivity classifier)
- COMPLEMENT: 18 (P's canary + B's golden topology; S's BLAKE3 chain extension + P's lazy compile; S's `0600` posture + B's per-workflow file; P's `dump-topology` + B's golden test; S's `@pure_edge` + B's predicate table; P's compile-once + B's typed CLI; B's HITL Pydantic + S's reason enum; P's path-references-only + S's progressive disclosure invariant; etc.)
- SUBSUME: 9 (B's docstring `Reads:/Writes:` AST → subsumed by Layer 1 per-node unit tests; S's `@reducer` dispatcher → subsumed by frozen=False + runtime id-diff; S's full Ed25519/HMAC stack → subsumed (deferred) by typed `HumanDecision`; P's sensitivity classifier → subsumed by Phase 5's existing `escalate` semantics; S's 64 KB blob cap → dropped; S's MsgPack reject → kept (JSON-only); S's `@side_effect` decorator → subsumed (deferred) by Phase 9 Temporal; B's `cli/remediate.py` edit → replaced by `cli/loop.py`; P's queued checkpoint writes → replaced by fsync-per-boundary)

### Conflict-resolution table

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|
| `frozen` on state ledger | unspecified (frozen=False implied) | `frozen=True` + custom `@reducer` dispatcher | `frozen=False` + AST lint for in-place mutation | **`frozen=False` + runtime id() diff hook** `[B+synth]` (LangGraph idiom preserved; lint gap closed) | 3 | 3 | 3 | 3 | **12** |
| Retry-counter scope | per-gate | per-workflow with same-signature flake detection | per-workflow lifetime (monotonic) | **per-gate, with B's same-signature flake refinement** `[P+S+synth]` (ADR-0014 title is per-gate; Phase 5 parity test demands this) | 3 | 3 | 3 | 3 | **12** |
| Retry path: re-apply same `RecipeApplication` vs re-enter Phase 4 | re-apply same recipe (open-Q1) | re-enter Phase 4 `plan_llm` on retry | engine-of-record via `retryable_{engine}` | **re-enter Phase 4 `FallbackTier.run(..., prior_attempts=...)`; single `retry_phase4` edge** `[S+synth]` (Phase 5 exit-criterion #19 demands distinct patch bytes) | 3 | 3 | 3 | 3 | **12** |
| Checkpoint durability | queued; fsync at next gate boundary | fsync immediate | aiosqlite default | **fsync at every node-boundary write, no background queue** `[S+B+synth]` (exit criterion forbids state loss) | 3 | 2 | 3 | 3 | **11** |
| Checkpointer concurrency | single shared DB file | per-workflow SQLite file | single shared DB ("per-workflow only for dev") | **per-workflow SQLite file** `[S]` (no contention; cleaner ops; matches BLAKE3-chain-per-workflow shape) | 3 | 3 | 3 | 3 | **12** |
| HITL resume authentication | untyped `Command(resume=ApprovalDecision(...))` | Ed25519 + HMAC + 2-step CLI signing | untyped `aupdate_state(..., {"human_decision": dict})` | **typed `HumanDecision.model_validate` only; full crypto stack deferred to Phase 11/16** `[B+synth]` (security scope creep — critic security.1 landed; ~600 LOC saved; ADR-P6-004 records the deferral) | 3 | 3 | 3 | 3 | **12** |
| Module-level compile vs per-invocation | module-level singleton (~80 ms saved) | per-invocation | per-invocation | **lazy-singleton with `force_rebuild=True` for tests** `[synth]` (closes critic performance.4 — `--checkpointer-db` flag works *and* compile cost paid once) | 3 | 3 | 3 | 3 | **12** |
| Entry-point name | `VulnLoop` / `codegenie loop run` | `build_vuln_loop_graph` | `build_vuln_graph` / `cli/remediate.py` edit | **`build_vuln_loop()` + `codegenie loop run`** `[synth]` (avoids Phase 8 supervisor collision; explicit Phase-6-vs-Phase-3 split; performance's CLI name wins on clarity) | 3 | 3 | 3 | 3 | **12** |
| `cli/remediate.py` edit | not specified | not specified | edit (ADR-P6-001 in B) | **do not edit; ship `cli/loop.py` in parallel** `[synth]` (Phase 7 exit criterion: "no Phase 0–6 source modified") | 3 | 3 | 3 | 3 | **12** |
| `schema_version` encoding | not specified | `blake3(model_json_schema())` (dynamic) | `Literal["v0.6.0"]` (static) | **`Literal["v0.6.0"]` static** `[B+synth]` (critic security-hidden-2 — dynamic blake3 flips on every Pydantic minor bump) | 3 | 3 | 3 | 3 | **12** |
| Golden topology test | per-run JSON dump | none | both SVG and JSON | **JSON-only as CI gate; SVG committed for review** `[B+synth]` (critic best-practices-hidden-1 — SVG isn't stable contract) | 3 | 3 | 3 | 3 | **12** |
| Serializer | aiosqlite default | JSON only + 64 KB cap | aiosqlite default | **JSON only, no 64 KB cap** `[synth]` (S's serializer choice + critic-driven cap removal — `prior_attempts` legitimately exceeds 64 KB) | 3 | 3 | 3 | 3 | **12** |
| Field-ACL machinery (read/write per field) | none | runtime + AST | docstring `Reads:`/`Writes:` + AST | **none — replace with per-node unit tests** `[synth]` (critic best-practices.2 + security.3 both landed: these tests verify appearance, not behavior; global rule §9) | 3 | 3 | 3 | 3 | **12** |
| `@side_effect` decorator | none | full guard with chain-event lookup | none | **defer to Phase 9 Temporal** `[synth]` (critic security.2 — Phase 9 owns side-effect idempotency; saving Phase 6 the LOC) | 3 | 3 | 3 | 3 | **12** |

All 14 conflicts above scored 11 or 12 — the synthesizer was decisive on each. No tie-break needed.

### Shared blind spots considered

The critic flagged three quiet agreements among all three designs. The synthesizer's posture on each:

1. **"All three defer Postgres without measuring SQLite throughput."** **Departed from all three.** Goal 9 ships a measured throughput test; on a failure, ADR-P6-006 forces an earlier Postgres migration. The synthesizer refuses to defer a load-bearing operational property to a future phase without recording a measurement.
2. **"All three define `HumanDecision` without Phase 11 input."** **Carried forward, but recorded explicitly.** Goal 18 commits the contract to `docs/contracts/hitl-v0.6.0.json` and gates Phase 11's design review on consumption-or-amendment. The synthesizer accepts that the shape may need to change; the discipline is *not papering over the deferral*. Risk #2 above is the audit trail.
3. **"All three treat `langgraph-cli` as debug-only and budget zero for its operational role."** **Carried forward.** The roadmap names `langgraph-cli` in Phase 6's tooling list; the synthesizer treats it as a topology renderer + dev inspector. Phase 9's Temporal-Postgres migration will need its own operator-inspection story (`temporal-ui` is named in the roadmap; LangGraph's CLI may not survive the move). Phase 6 does not pre-design Phase 9's inspector.

### Departures from all three inputs

- **Goal 6 (canary as regression gate, not absolute budget).** Performance asserted "p50 ≤ 2 ms / p95 ≤ 8 ms" with no measured baseline; security and best-practices did not have a canary at all. The synthesizer ships the canary but anchors it to a *committed baseline from first CI run* and a >25% regression gate. This is the global-rule-§12 ("Fail loud") response to critic performance.3 — measure, don't assume.
- **Goal 9 (SQLite throughput as a phase-gate).** No input design measured. The synthesizer treats this as a phase-blocker for the Postgres-deferral assumption.
- **`cli/remediate.py` is not edited.** Performance left this unspecified; security left this unspecified; best-practices edited it via ADR-P6-001. The synthesizer ships a new `cli/loop.py` and leaves `cli/remediate.py` alone — closes the Phase-7 "no Phase 0–6 source modified" exit criterion (critic best-practices.5).
- **Runtime in-place-mutation hook via `id()` diff.** Best-practices' AST lint was hand-waved (critic best-practices.4); security's `frozen=True` requires a custom dispatcher. The synthesizer ships a runtime hook that diffs `id()` of every list/dict field after every node returns — this catches `state.events.append(...)` directly, no AST analysis required.
- **Same-signature flake detection moved into `route_after_attempt`.** Security's idea; best-practices does not have it. Synthesizer keeps it because it protects the retry budget against deterministic recurring failures and is one line of code.
- **`HumanDecision.note` is **not** flowed into any LLM prompt.** Security's design was ambiguous about this. The synthesizer is explicit: notes are for human reading only; they never reach Phase 4's prompt builder. Closes the global-rule-§2.1 ("no LLM in routing/gather") corner case the critic flagged.
- **`langgraph-cli` SVG is committed for review but not a CI gate.** Best-practices' design had SVG as a gate; critic best-practices-hidden-1 said the SVG isn't a stable contract. JSON-only as the gate.

## Exit-criteria checklist

- [x] **"The vuln-remediation loop runs as a LangGraph state machine."** Component 2 (`build_vuln_loop()`); Component 6 (`replan_with_phase4`); Layer 8 E2E test (`test_loop_run_vuln_remediation.py`) runs the full graph against Phase 3's `cve-fixture` repo end-to-end.
- [x] **"Mid-run kill + resume works without state loss."** Goal 8 (fsync-per-boundary); Component 3 (`AuditedSqliteSaver`); `tests/integration/test_replay_after_kill.py` SIGKILLs during `validate_in_sandbox` and asserts byte-identical final state; `tests/integration/test_replay_byte_identical.py` is the cleaner reference.
- [x] **"HITL interrupt fires when trust gates fail twice in a row, and a mocked human approval continues the run."** Component 7 (`await_human` + `HumanDecision`); Goal 3; Goal 4 (per-gate retry counter); `tests/integration/test_hitl_interrupt_and_resume.py` is the exit-criterion test. The "twice in a row" is interpreted as "two consecutive failures at the same gate transition" — strictly following ADR-0014's "per gate transition" wording; the third attempt fires only if HITL approves continue.

## Load-bearing commitments check

For each commitment in `production/design.md §2` that applies to Phase 6:

- **§2.1 "No LLM in the gather pipeline."** Phase 6's `graph/` package is fence-CI-denied from importing `anthropic | chromadb | sentence-transformers`. Phase 4's `FallbackTier` is the *only* path that can reach an LLM, and it is invoked from exactly one node (`replan_with_phase4`). Conditional-edge predicates are pure-functional; no routing decision touches an LLM. `HumanDecision.note` is never flowed into any prompt.
- **§2.2 "Facts, not judgments."** Every conditional edge reads booleans and counters written by Phase 5's signal collectors. No node infers "should we retry?"; the predicate computes it from `retry_count`, `max_attempts`, `last_outcome.passed`, `last_outcome.retryable`, and the same-signature flake check.
- **§2.3 "Honest confidence."** Every state transition is recorded in `state.events` and the BLAKE3 audit chain. `RetryLedger.record` carries Phase 5's signal provenance forward; Phase 6 does not add `confidence` fields to `VulnLedger` (`schema_version` Literal pins the shape; `test_no_self_confidence_in_loopstate.py` is borrowed from security to assert no `confidence|llm_says|self_reported` field names exist).
- **§2.4 "Determinism over probabilism for structural changes."** The graph topology (node set, edge set, predicates) is fully declared at module import time. No runtime topology mutation. No LLM-decided routing. The agent (Phase 4) has freedom only inside `replan_with_phase4`; everything else is deterministic.
- **§2.5 "Extension by addition."** **The most-attacked commitment in the critique.** The synthesis: Phase 6 adds **one** package (`graph/`) and **one** Phase-5 ADR-amended seam (`run_one` promoted from `_run_one_attempt` per ADR-P6-001). Phase 7's distroless task class adds a sibling builder (`build_distroless_loop()`) under `graph/`; no edits to vuln nodes; the supervisor (Phase 8) dispatches on `task_type`. **`cli/remediate.py` is not edited** (critic best-practices.5 closed). Phase 4's `FallbackTier.run` has the `prior_attempts` kwarg already (ADR-P5-002, additive); Phase 6 just uses it.
- **§2.6 "Organizational uniqueness as data, not prompts."** Phase 6 ships no prompts. Trust-Aware gate thresholds live in YAML (Phase 5's territory); Phase 6's `max_attempts` default (3) is bound at graph-build time from `tools/policy/graph-thresholds.yaml`.
- **§2.7 "Progressive disclosure."** `VulnLedger` indexes evidence by `Path` references and `blake3` digests; raw patch bytes, raw test stdout, raw sandbox logs all live on disk under `.codegenie/`; the audit chain references them by path. Critic-flagged: this is what makes the checkpoint blob small enough that we can drop security's 64 KB hard cap and still keep it usually < 32 KB.
- **§2.8 "Humans always merge."** Phase 6's `interrupt()` is **not** a merge gate. It is a triage gate (retry exhausted or non-retryable signal). The merge step is Phase 11 territory; the agent opens the PR, the human merges. Phase 6 honors §2.8 by ensuring `interrupt()` is the only way to escalate human-relevant work.
- **§2.9 "Cost is observable end-to-end and bounded per workflow."** Phase 6 emits per-node wall-clock spans (Component 10) for Phase 13's cost ledger; the Phase 4 `LlmInvocationGuard` is unchanged; the Phase 5 sandbox-cost telemetry is unchanged. Phase 6 itself contributes zero LLM tokens.

## Roadmap coherence check

### What prior phases established that this design depends on

- **Phase 3:** `RemediationOrchestrator` (the linear sync orchestrator Phase 6 wraps without modifying); `RecipeEngine.apply`, `RecipeSelection`, `RecipeApplication`, `ApplyContext` (Phase 6 imports these as typed Pydantic models); `RemediationReport` schema (Phase 6's terminal `emit_artifact` node writes this); BLAKE3 audit-chain primitive.
- **Phase 4:** `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=[])` (ADR-P5-002 amended additively in Phase 5); `RagTier` for recipe-miss path; the fence-wrap + canary-check defenses on prompt construction; `engine_used` discriminator (`recipe | rag | rag_llm`); Phase 4 chain-head predecessor of Phase 5's first chain entry.
- **Phase 5:** `GateRunner` (Phase 6 calls per-attempt entry via ADR-P6-001 promotion); `GateContext`, `GateOutcome`, `AttemptSummary` (Phase 6 imports as typed Pydantic models); `RetryLedger.record` (Phase 6's `record_attempt` node delegates); the `attempts.jsonl` BLAKE3-chained ledger that Phase 6's `AuditedSqliteSaver` extends; the `gate_isolation_class` annotation Phase 11 will read; the existing `prior_attempts` retry-feedback transport.

### What this design establishes that later phases will need

- **`VulnLedger` schema** — Phase 7 ships its own `DistrolessLedger` (ADR-0022 Three Strikes — strike one is vuln). Phase 8's supervisor dispatches on `task_type` to `build_vuln_loop()` or `build_distroless_loop()`.
- **`build_vuln_loop()` factory** — the canonical entry point name; the supervisor in Phase 8 imports it. Phase 7's distroless adds a sibling `build_distroless_loop()` under the same package.
- **`HumanRequest` / `HumanDecision` contract** (`docs/contracts/hitl-v0.6.0.json`) — Phase 11 either consumes or amends.
- **`AuditedSqliteSaver` + BLAKE3 chain extension semantics** — Phase 9's Postgres migration must preserve the chain extension on every checkpoint write.
- **`@pure_edge` discipline + JSON golden topology** — every future state machine (distroless, planner subgraphs, recipe-authoring subgraphs in Phase 15) inherits this discipline.
- **`codegenie loop` CLI namespace** — Phase 8's supervisor adds `codegenie sherpa` as a parallel namespace; Phase 9's Temporal worker is `codegenie temporal-worker` (also parallel). The CLI namespace pattern is "one verb per orchestration layer."
- **Per-node wall-clock event stream** — Phase 13's cost ledger consumes it.

### Any new ADRs implied by this design that should be drafted

- **ADR-P6-001:** Promote Phase 5's `_run_one_attempt` to public `run_one` (renaming-only additive change).
- **ADR-P6-002:** Lazy-singleton compile of `build_vuln_loop()` with `force_rebuild=True` for tests.
- **ADR-P6-003:** `interrupt()` is called from exactly one node (`await_human`); future HITL needs route to it.
- **ADR-P6-004:** HITL operator authentication is deferred to Phase 11; Phase 6 ships typed `HumanDecision` only. The single-host trust posture is the explicit recorded scope cut.
- **ADR-P6-005:** `schema_version: Literal["v0.6.0"]` (static literal, not dynamic `blake3(model_json_schema())`); migration registry lives under `graph/migrations/`.
- **ADR-P6-006:** SQLite throughput watch — if Goal 9's test reports < 100 writes/s on CI hardware, Phase 9's Postgres migration is pulled forward.
- **ADR-P6-007:** Topology change discipline — the JSON form of `graph.get_graph().to_json()` is the CI golden; the SVG is committed for human review but does not gate CI.

## Open questions deferred to implementation

1. **Does Phase 5's `_run_one_attempt` factor cleanly as a top-level function, or does ADR-P6-001 require a refactor of `GateRunner` internals?** The parity test will surface this; if a refactor is required, the implementer must surgical-touch Phase 5's `gates/runner.py` and update Phase 5's contract-snapshot tests.
2. **What is the canonical path for the audit chain file?** Phase 5 ships `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl`; Phase 6 extends the same file. Confirm at implementation time that the path is `run-id`-keyed (not `workflow-id`-keyed) and that the `chain_head_from_phase5(...)` helper finds it.
3. **Does LangGraph's `aupdate_state(..., as_node="await_human")` reliably inject `HumanDecision` such that the next `ainvoke(None, config)` resumes deterministically?** The HITL replay test is the canary; the LangGraph version is pinned (`>= 0.2.x`); ADR-P6-002's `_compat.py` shim is the upgrade fence.
4. **Is the `RetryLedger.record` write path truly single-threaded?** Phase 5's design says yes (one orchestrator process). Phase 6 adds the `AuditedSqliteSaver.put` write to the same chain file. Implementation must ensure both writers acquire the same `threading.Lock` before `O_APPEND` — verified by `test_chain_single_writer.py`.
5. **What is the migration story for the FIRST schema bump (v0.6.0 → v0.7.0)?** Phase 6 ships no migrations; the first phase that adds a `VulnLedger` field (likely Phase 8 with planner-routing fields) writes the first migration. The shape of `graph/migrations/v0_6_0_to_v0_7_0.py` is unspecified in Phase 6 by design.
6. **Does the `canary baseline` survive `langgraph` or `pydantic` minor bumps?** The 25% regression tolerance is the policy; Renovate PRs that bump these libraries are expected to update the baseline as a deliberate step.
