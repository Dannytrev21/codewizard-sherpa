# Phase 6 — SHERPA-style state machine for the vuln loop: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 6"

## Executive summary

Phase 6 lifts the Phase 3 → 4 → 5 linear vuln-remediation pipeline into a **LangGraph `StateGraph[VulnLedger]`** under SHERPA discipline: one typed Pydantic state ledger, four pure conditional edges, ten sync nodes, and one `interrupt()` site. The engineer ships a single new package `src/codegenie/graph/` and a parallel `src/codegenie/cli/loop.py` — **no edits to `cli/remediate.py`, `state.py`, or any vuln node from prior phases** (Phase 7 exit-criterion preservation). We sequence the work contracts-first: ship `VulnLedger` + `HumanRequest`/`HumanDecision` + the `@pure_edge` decorator + the after-node hook before any node implementation; then the `AuditedSqliteSaver` extending Phase 5's BLAKE3 audit chain; then the four conditional edges (with property tests pinning label-projection invariance); then the ten nodes (each thin wrapper over Phase 3/4/5 engines); then `build_vuln_loop()` itself plus the topology golden; finally the CLI, HITL replay test, Phase 5 parity test, and the perf canary that drives ADR-P6-006. Every step adds at least one CI gate (fence checks, mypy strict, golden topology, no-self-confidence-field introspection) so violations of ADR-0002 / ADR-0014 / ADR-0022 fail at PR time, not at runtime.

## Order of operations

**Contracts → checkpointer → edges → nodes → topology → CLI → HITL/replay → parity → perf/adversarial.** Rationale: `VulnLedger` is the single thing every later step depends on — its `extra="forbid"` shape, its `schema_version: Literal["v0.6.0"]` pin, and its mutable-field enumeration must be settled before any node returns one. The checkpointer comes next because Step 1's round-trip golden fixtures need a writer to validate against, and because the BLAKE3 chain extension into Phase 5's existing audit chain is the highest-risk interop seam in the phase. Edges precede nodes so that the conditional routing topology can be unit-tested with synthesized ledgers before real upstream engines are wired in. Nodes precede `build_vuln_loop()` because LangGraph validates node signatures at `_build()` time. The CLI is next because exit codes 0/11/12/13/1 must be observable before HITL and replay tests can SIGKILL the process and re-invoke. Parity with Phase 5's sync `GateRunner.run()` lands once the vertical slice runs end-to-end — it is the test that proves Phase 6 didn't silently change retry semantics. Adversarial and perf canaries close the phase because they verify properties of an already-working system.

## Step 1 — Scaffold `graph/` package, ship `VulnLedger` + HITL contracts + structural CI gates

**Goal:** The `graph/` package exists with the single state contract, the HITL contract pair, and every static CI gate that protects later steps — no node logic yet, but the lints that catch ADR-0002 violations are live.

**Features delivered:**
- `src/codegenie/graph/` package skeleton: `__init__.py`, `state.py`, `hitl.py`, `events.py`, `hooks.py`, `edges.py` (stub), `vuln_loop.py` (stub), `checkpointer.py` (stub), `nodes/__init__.py` (empty), `migrations/__init__.py` (empty).
- `state.py`: `VulnLedger` with `model_config = ConfigDict(extra="forbid", frozen=False)`, `schema_version: Literal["v0.6.0"]`, all fields per arch-design §Component 1, JSON-serializable end-to-end.
- `hitl.py`: `HumanRequest` and `HumanDecision`, both `extra="forbid", frozen=True`.
- `events.py`: `GraphEvent` + `emit_event()` constructor.
- `hooks.py`: `LedgerMutatedInPlace`, `CheckpointTampered`, `CheckpointerInsecure`, `SchemaDrift`, `AuditChainCorrupted`, `CheckpointSchemaMismatch`, `ImpureEdge` exception classes; `make_after_node_hook()` returning a callable that diffs `id()` of `_MUTABLE_FIELDS`.
- `__init__.py` exports: `build_vuln_loop`, `VulnLedger`, `HumanRequest`, `HumanDecision`.
- Fence-CI rules extended in `tools/fence_ci.yaml`: `graph/` forbidden from importing `anthropic | chromadb | sentence-transformers`; `graph/edges.py` forbidden from importing `random | time | os | datetime` (whitelist `datetime.fromisoformat`); `graph/nodes/*` forbidden from importing sibling nodes.
- CI gates: `tests/graph/test_state.py` (validation rules + `test_in_place_mutation_raises`), `tests/graph/test_no_self_confidence_in_loopstate.py` (Layer 0 introspection refuses `confidence|llm_says|self_reported` fields), `tests/graph/test_fence_graph_no_anthropic.py`, `tests/graph/test_pep_no_O_optimizations.py`, `tests/graph/test_schema_version_pin.py` (round-trip a v0.6.0 ledger fixture).

**Done criteria:**
- [ ] `pytest tests/graph/test_state.py tests/graph/test_no_self_confidence_in_loopstate.py tests/graph/test_fence_graph_no_anthropic.py` green.
- [ ] `mypy --strict src/codegenie/graph/` clean — no `Any`, no `cast`, no unjustified `# type: ignore`.
- [ ] `ruff check src/codegenie/graph/` clean.
- [ ] `VulnLedger.model_validate(<known-good json>)` round-trips byte-identical via `model_dump_json(by_alias=True, exclude_none=False)`.
- [ ] `VulnLedger.model_validate({"unknown_field": "x", ...})` raises `ValidationError` (extra=forbid enforced).
- [ ] After-node hook raises `LedgerMutatedInPlace` when a test deliberately mutates `state.events` in place; passes silently when `model_copy(update=...)` is used.
- [ ] Branch coverage on `state.py`, `hitl.py`, `events.py`, `hooks.py` ≥ 95%.
- [ ] Fence test refuses to import `anthropic` from any `graph/*.py` file.

**Depends on:** Phase 3 `AdvisoryRef`, `RecipeSelection`, `PatchRef`; Phase 4 `RagHit`; Phase 5 `AttemptSummary`, `GateOutcome`. All imported as types only — no behavior reached yet.

**Effort:** M — mechanical but volume is high; one Pydantic model with ~18 fields, four contracts, six exception classes, five fence/introspection tests, mypy-strict discipline from day one.

**Risks specific to this step:** Phase 3/4/5 types may not all be JSON-serializable with `mode="json"` round-trip; if `AttemptSummary` carries a non-JSON-native field (e.g., `Path`, `bytes`), a fixture-driven round-trip test catches it here, not in Step 2 where the checkpointer would surface it as a serialization failure under load.

## Step 2 — Implement `AuditedSqliteSaver` + per-workflow file + BLAKE3 chain extension into Phase 5's audit chain

**Goal:** A drop-in `BaseCheckpointSaver` subclass that writes per-workflow SQLite files at `0600`, fsyncs every checkpoint at the WAL boundary, extends Phase 5's existing BLAKE3 audit chain on every `put()`, and refuses to resume on tamper / schema drift / chain mismatch.

**Features delivered:**
- `graph/checkpointer.py`: `AuditedSqliteSaver(AsyncSqliteSaver)` with `put`, `aget_tuple`, `_enforce_file_mode_0600`, `_fsync_durable`, `_append_chain_event`, `_lookup_chain_event`, `_verify_chain`.
- `make_checkpointer(workflow_id, *, base: Path = Path(".codegenie/loop/checkpoints"), chain_lock: threading.Lock) -> AuditedSqliteSaver` factory — the single seam Phase 9 will replace with `AuditedPostgresSaver`.
- `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL` set on connect; `PRAGMA wal_checkpoint(PASSIVE)` after each commit.
- Shared-process `threading.Lock` for chain appends (one writer wins between Phase 5 `RetryLedger.record` and Phase 6 `put()`).
- Canonical-JSON serializer (`canonical_json(checkpoint)`) — recursive key-sort + `separators=(",", ":")`.
- Chain-event kinds: `checkpoint.write`, `checkpoint.tamper.detected`, `interrupt.raised`, `resume.applied`.

**Done criteria:**
- [ ] `tests/graph/test_checkpointer.py` round-trips a `VulnLedger` checkpoint write → read → `model_validate` byte-identical.
- [ ] `tests/adversarial/test_tampered_checkpoint.py` — open `<workflow_id>.sqlite3`, mutate a row, attempt `aget_tuple` → `CheckpointTampered` raised; chain receives `checkpoint.tamper.detected` event.
- [ ] `tests/adversarial/test_world_readable_checkpoint_refused.py` — `chmod 644 <db>`; constructor raises `CheckpointerInsecure`; remediation hint printed.
- [ ] `tests/adversarial/test_schema_drift_refused.py` — mutate `schema_version` literal in the persisted blob; resume raises `SchemaDrift`.
- [ ] `tests/integration/test_chain_seed_mismatch.py` — corrupted Phase 5 chain head causes `AuditChainCorrupted` at constructor time.
- [ ] `tests/integration/test_chain_single_writer.py` — concurrent `RetryLedger.record` + `AuditedSqliteSaver.put` under shared lock produce a chain whose events parse back in append order with no interleaving corruption.
- [ ] `mypy --strict` clean on the new file.
- [ ] Each `put()` durably persists before the next node runs — verified by `tests/integration/test_replay_byte_identical.py` (full canary in Step 8; smoke version here).

**Depends on:** Step 1 (`VulnLedger`, exception classes). Phase 5's `RetryLedger.head_from_phase5(run_id)` helper signature (read Phase 5's shipped `gates/retry_ledger.py` first).

**Effort:** M — small surface but high-stakes; the chain-write interop with Phase 5 is the single highest-risk interface in the phase. Misreading Phase 5's chain-event JSONL byte format produces silent chain corruption.

**Risks specific to this step:** Phase 5's `RetryLedger` may not expose a public `head_from_phase5()` — Gap 2 of the arch design flags this. Read `src/codegenie/gates/retry_ledger.py` before writing the checkpointer; if the helper does not exist, either (a) add a public read accessor to Phase 5's ledger (one-line addition, parity test catches drift) or (b) parse the chain JSONL directly from `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl` and surface a Phase-6 ADR documenting the choice.

## Step 3 — Ship `@pure_edge` decorator + the four conditional-edge predicates + property tests

**Goal:** All four routing decisions are pure functions of `VulnLedger` state, AST-verified for forbidden imports, property-tested for determinism and label-projection invariance.

**Features delivered:**
- `graph/edges.py`: `@pure_edge` decorator that AST-walks the function body at import time and raises `ImpureEdge` on `random | time | os | datetime` imports (whitelist `datetime.fromisoformat`).
- Four predicates: `route_after_select_recipe`, `route_after_rag`, `route_after_attempt`, `route_after_human`.
- `_same_signature(a: AttemptSummary, b: AttemptSummary) -> bool` helper for same-signature flake detection inside `route_after_attempt`.
- `route_after_attempt` returns `"passed" | "retry_phase4" | "retry_exhausted" | "non_retryable"`; `route_after_rag` consults `rag_hit.score >= 0.85` threshold (digest-pinned from `tools/policy/graph-thresholds.yaml`).

**Done criteria:**
- [ ] `tests/graph/test_edges.py` parametrizes the full state space for `route_after_attempt` — cartesian of `(passed ∈ {T,F}, retryable ∈ {T,F}, retry_count ∈ {0..max_attempts+1}, same_sig ∈ {T,F})` — 100% branch coverage.
- [ ] `tests/graph/test_edges_determinism.py` (Hypothesis, 10k examples) — `route_after_attempt(s) == route_after_attempt(s)` for every generated `VulnLedger`.
- [ ] `tests/graph/test_edge_label_depends_only_on_projection.py` (Hypothesis) — for each predicate, permute non-consumed fields (`events[].at`, `AttemptSummary.created_at`, `last_node`) and assert label is invariant. Closes critique security-attack-4.
- [ ] `tests/graph/test_pure_edge_rejects_forbidden_imports.py` — synthesizing a fake predicate that imports `time` raises `ImpureEdge` at decorator time.
- [ ] `tests/graph/test_edges.py::test_route_after_attempt_same_signature_flake` — two consecutive identical `failing_signals` route to `"non_retryable"` even with `retry_count < max_attempts`.
- [ ] No edge predicate body imports a banned module (fence-CI gate already exists from Step 1; this confirms compliance).

**Depends on:** Step 1 (`VulnLedger`, `AttemptSummary`).

**Effort:** S — small surface, but the property tests are the load-bearing correctness gate; Hypothesis strategies for `VulnLedger` must be hand-written.

**Risks specific to this step:** Hand-built Hypothesis strategies for nested Pydantic models drift; pin a strategy module (`tests/graph/strategies.py`) and golden-test a representative sample so a future Pydantic minor bump doesn't silently weaken coverage.

## Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines

**Goal:** Each of the ten nodes is a sync `def (state: VulnLedger) -> VulnLedger` that delegates to Phase 3/4/5, returns `state.model_copy(update={...})`, and emits at least one `GraphEvent`. Each has a dedicated unit test that mocks the upstream engine at the import boundary.

**Features delivered:**
- `graph/nodes/ingest_cve.py` — calls Phase 3 `AdvisoryLoader`; pins `advisory`.
- `graph/nodes/select_recipe.py` — calls Phase 3 `RecipeMatcher.match()`.
- `graph/nodes/apply_recipe.py` — calls Phase 3 `RecipeEngine.apply(ApplyContext(patch=..., prior_attempts=...))`.
- `graph/nodes/rag_lookup.py` — calls Phase 4 `RagTier.lookup()`.
- `graph/nodes/replan_with_phase4.py` — calls Phase 4 `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=state.prior_attempts)`; sets `last_engine="phase4_llm"`.
- `graph/nodes/validate_in_sandbox.py` — calls Phase 5 `GateRunner.run_one(transition, GateContext(...))` (the public alias per ADR-P6-001).
- `graph/nodes/record_attempt.py` — calls Phase 5 `RetryLedger.record(Attempt(...))`; resets `retry_count` to 1 on `current_gate_id` change.
- `graph/nodes/await_human.py` — the **only** file importing `langgraph.types.interrupt`; builds `HumanRequest`, fires `interrupt()`; on resume applies `HumanDecision`, resets `retry_count=0` when `action="continue"`.
- `graph/nodes/emit_artifact.py` — writes Phase 3 `RemediationReport`.
- `graph/nodes/escalate.py` — terminal node for `HumanDecision.action="abort"`; emits `kind="escalate"` event.
- `@audited_node` decorator that wraps each node return with the after-node `id()`-diff hook from Step 1.
- ADR-P6-001: rename Phase 5's `_run_one_attempt` → public `run_one` (one-line additive change in `gates/runner.py` if the seam is already factored; refactor otherwise — see Gap 2 of the arch design).

**Done criteria:**
- [ ] `tests/graph/test_nodes/test_<node>.py` exists for all ten nodes; each constructs an input `VulnLedger`, mocks the upstream engine, invokes the node, asserts the returned ledger's fields and the emitted `GraphEvent`.
- [ ] `tests/graph/test_record_attempt.py` — verifies `retry_count` reset semantics on `current_gate_id` change; cumulative within same `current_gate_id`.
- [ ] `tests/graph/test_await_human.py` — first entry fires `interrupt()`; resume entry with `human_decision.action="continue"` resets `retry_count=0`; `action="override"` and `"abort"` leave `retry_count` intact.
- [ ] `tests/graph/test_hitl_note_not_in_prompt.py` — instrument `replan_with_phase4` so any read of `state.human_decision.note` from inside it raises; integration verifies Phase 4 prompt builder is never fed `note`.
- [ ] No node-to-node imports (fence-CI gate from Step 1 catches violations).
- [ ] After-node `id()`-diff hook runs on every node return (verified by deliberately mutating `state.events` inside one node and seeing `LedgerMutatedInPlace`).
- [ ] ADR-P6-001 lands in `docs/phases/06-sherpa-state-machine/ADRs/` describing exactly what shipped to Phase 5's `gates/runner.py`.
- [ ] Branch coverage on each node module ≥ 90%.

**Depends on:** Steps 1–3. Phase 3 `RecipeEngine.apply` accepting `prior_attempts` kwarg (ADR-P5-002, already shipped). Phase 4 `FallbackTier.run` accepting `prior_attempts` kwarg. Phase 5 `GateRunner.run_one` public alias (ADR-P6-001 — verify or land in this step).

**Effort:** L — ten nodes, ten unit tests, plus the surgical Phase-5 touch. The single largest step by LOC.

**Risks specific to this step:** Phase 5's `_run_one_attempt` may not be a clean single-attempt seam (Gap 2). Read `src/codegenie/gates/runner.py` *first*; if a refactor is required, surface a follow-up ADR and accept the wider touch; do not silently inline the per-attempt logic into `validate_in_sandbox` because the Phase 5 parity test (Step 7) will fail by construction.

## Step 5 — Implement `build_vuln_loop()` lazy-singleton factory + topology golden + `interrupt_before` wiring

**Goal:** The compiled `StateGraph[VulnLedger]` exists, is reachable via `build_vuln_loop(checkpointer=..., max_attempts=3, force_rebuild=False)`, fires `interrupt_before=["await_human"]`, and its `get_graph().to_json()` form is a CI-gated golden file.

**Features delivered:**
- `graph/vuln_loop.py`: `_COMPILED` / `_COMPILED_KEY` module-level singleton; `_build(max_attempts) -> StateGraph[VulnLedger]` constructing the 10-node × 4-conditional-edge × 5-unconditional-edge topology per arch-design §Component 2.
- `compile(checkpointer=..., interrupt_before=["await_human"])` invocation.
- `tests/golden/vuln_loop_topology.json` — canonicalized `graph.get_graph().to_json()`.
- `tests/graph/test_topology_golden.py` — CI gate that diffs `canonical_json(g.to_json())` against the golden.
- `tests/graph/test_topology_reachability.py` — every node reachable from `ingest_cve`; both `END` paths reachable; no dead nodes.
- `tests/graph/test_compile_cache_uses_force_rebuild.py` — passing the same checkpointer + `max_attempts` returns the cached `_COMPILED`; `force_rebuild=True` recompiles; changing the checkpointer instance without `force_rebuild=True` raises a test-fixture warning.
- `tools/policy/graph-thresholds.yaml` shipped with `max_attempts: 3`, `rag_score_threshold: 0.85`, `same_signature_window: 2`; BLAKE3 digest pinned in `tools/digests.yaml`.

**Done criteria:**
- [ ] `build_vuln_loop(checkpointer=InMemorySaver()).compile()` succeeds with no LangGraph validation errors.
- [ ] `tests/graph/test_topology_golden.py` green; updating the golden requires a deliberate `pytest --update-golden` flag.
- [ ] `tests/graph/test_topology_reachability.py` green: every conditional-edge label has a downstream path to `END`.
- [ ] `tests/perf/test_compile_cold_start.py` — `build_vuln_loop(force_rebuild=True)` p50 < 200 ms (baseline target 80 ms; loose ceiling to absorb CI-runner noise).
- [ ] `_COMPILED` is reused across two consecutive calls with the same key; verified by `id()` equality.
- [ ] Interrupt fires correctly: with `interrupt_before=["await_human"]`, a path routing through `record_attempt → "retry_exhausted" → await_human` pauses at the `await_human` frame before the node body runs.

**Depends on:** Steps 1–4.

**Effort:** M — small new code (~60 LOC for the factory) but the topology golden file requires careful canonicalization to survive LangGraph minor bumps.

**Risks specific to this step:** LangGraph's `to_json()` output may include version-sensitive metadata (timestamps, version strings) — strip these in `canonical_json()` and document the stripped keys in `tests/golden/README.md` so a LangGraph bump doesn't tank CI.

## Step 6 — Ship `cli/loop.py` operator surface + workflow-id derivation + exit codes

**Goal:** Operators can run `codegenie loop run`, `resume`, `inspect`, `replay`, `migrate-checkpoint`, and `render`; exit codes 0 / 11 / 12 / 13 / 1 are observable; the CLI does not modify `cli/remediate.py`.

**Features delivered:**
- `src/codegenie/cli/loop.py` — Click command group `loop` with subcommands `run`, `resume`, `inspect`, `replay`, `migrate-checkpoint`, `render`.
- Workflow-id derivation: `workflow_id = blake3(f"{repo_root_blake3}|{advisory_canonical_id}".encode()).hexdigest()[:16]`.
- `run` constructs initial `VulnLedger` (seeds `chain_head` from Phase 5), builds `AuditedSqliteSaver(.codegenie/loop/checkpoints/<workflow_id>.sqlite3)`, calls `build_vuln_loop(...).ainvoke(initial, config={"configurable": {"thread_id": workflow_id}})`.
- `resume` parses `--decision continue|override|abort`, `--operator`, optional `--note`; constructs `HumanDecision`; calls `graph.aupdate_state(config, {"human_decision": ...}, as_node="await_human")` then `graph.ainvoke(None, config)`.
- `inspect` prints `graph.get_state_history(config)` as a human-readable table.
- `replay` replays from a chosen `--from <checkpoint_id>` frame and asserts byte-identical outputs.
- `render` invokes `langgraph-cli` to emit both `.json` (CI gate) and `.svg` (review-only); writes the SVG to `docs/phases/06-sherpa-state-machine/vuln_loop.svg`.
- `migrate-checkpoint` — scaffolding only; v0.6.0 ships no registered migrations; command exists to record the contract.
- Exit codes: `0` (emit_artifact), `11` (escalate), `12` (paused at await_human), `13` (CheckpointTampered / CheckpointerInsecure / SchemaDrift / AuditChainCorrupted), `1` (unexpected).
- `--json` flag toggles structured JSON output on stderr.

**Done criteria:**
- [ ] `tests/cli/test_loop_run_happy.py` — `codegenie loop run ./tests/fixtures/repos/cve-fixture/ --cve CVE-...` produces exit 0 + `report.json`.
- [ ] `tests/cli/test_loop_resume_no_pause_errors.py` — `resume` against a thread_id with no paused workflow exits 1 with a clear message.
- [ ] `tests/cli/test_loop_exit_codes.py` parametrizes each exit code path (0/11/12/13/1) and asserts both the int and the structured-JSON `reason` on stderr.
- [ ] `tests/cli/test_workflow_id_deterministic.py` — same advisory + same repo HEAD → same `workflow_id` (content-addressing property).
- [ ] `git diff origin/master -- src/codegenie/cli/remediate.py` is empty after this step lands (Phase 7 exit-criterion preserved).
- [ ] `codegenie loop render --out tests/golden/vuln_loop_topology.svg` produces both `.json` (compared against golden) and `.svg` (committed for review).
- [ ] CLI flags `--max-attempts`, `--checkpointer-db` are honored at parse time; `--max-attempts 0` rejected by Pydantic `Settings`.

**Depends on:** Steps 1–5.

**Effort:** M — CLI is mechanical but the exit-code matrix and the `aupdate_state(..., as_node="await_human")` resume dance need integration coverage.

**Risks specific to this step:** `langgraph-cli` is dev-only tooling; it may produce non-deterministic SVG output that drifts on minor version bumps. Mitigation: pin `langgraph-cli >= 0.x.y < 0.x+1` in `pyproject.toml`; gate CI on `.json` only (per ADR-P6-007); document SVG drift as an expected review concern in `tests/golden/README.md`.

## Step 7 — HITL replay + Phase 5 parity + retry-feedback-distinct-bytes tests (G3 + G4 + G5)

**Goal:** The three exit-criterion-bearing integration tests are green: HITL interrupt fires after consecutive failures and resumes; the LangGraph cycle produces byte-identical `attempts.jsonl` to Phase 5's sync `for`-loop; retry re-entry into Phase 4 produces distinct patch bytes.

**Features delivered:**
- `tests/integration/test_hitl_interrupt_and_resume.py` — drives the exit-criterion scenario (arch-design §Scenario 2). Parametrized at `max_attempts ∈ {1, 2, 3}` per Gap 5 of the arch design. With `max_attempts=2`, two consecutive failures trigger `interrupt()`; injected `HumanDecision(action="continue", ...)` via `aupdate_state(..., as_node="await_human")` continues the run; final state has `report.json` written.
- `tests/integration/test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py` — documents Gap 4 behavior loudly: after a same-signature flake, `continue` is silently re-routed to `non_retryable`; surfaces an operator warning.
- `tests/integration/test_retry_semantics_parity.py` — same fixture run through Phase 5 sync `GateRunner.run()` and Phase 6 LangGraph cycle; `attempts.jsonl` files byte-compared. Closes G4.
- `tests/integration/test_phase4_retry_feedback_distinct_bytes.py` — three-attempt retry through `replan_with_phase4` produces three distinct `patch-attempt-{1,2,3}.diff` files; attempt-2's Phase 4 prompt contains the fence-wrapped attempt-1 summary. Closes Phase 5 exit-criterion #19 (G5).
- `tests/integration/test_hitl_malformed_decision_raises.py` — submitting `HumanDecision(action="approve")` raises `ValidationError`.
- `tests/integration/test_resume_no_pause_errors.py` — resume against a non-existent paused frame errors clearly.
- VCR cassettes under `tests/fixtures/cassettes/cve_fixture_3retries/cassette-attempt-{1,2,3}.yaml`.
- `tests/integration/conftest.py` documents the `max_attempts=2` parametrization rationale (roadmap "twice in a row" wording vs ADR-0014 default).

**Done criteria:**
- [ ] `tests/integration/test_hitl_interrupt_and_resume.py[max_attempts=2]` green — `interrupt()` after two failures, resume completes with `report.json` written.
- [ ] Same test at `max_attempts=3` green — production-default path also exercised (Gap 5 closed).
- [ ] `tests/integration/test_retry_semantics_parity.py` — byte-diff of `attempts.jsonl` between Phase 5 sync and Phase 6 cycle is empty.
- [ ] `tests/integration/test_phase4_retry_feedback_distinct_bytes.py` — `blake3(patch-attempt-1) != blake3(patch-attempt-2) != blake3(patch-attempt-3)`.
- [ ] HITL contract exported to `docs/contracts/hitl-v0.6.0.json` via `python -m codegenie.graph.hitl --export`.
- [ ] CI gate diffs `docs/contracts/hitl-v0.6.0.json` against the committed file; PR must update deliberately on shape change.
- [ ] Layer-4 (HITL) and Layer-5 (parity) of the test pyramid pass within their CI budgets (~10 s + ~60 s).

**Depends on:** Steps 1–6. Phase 5's `RetryLedger` JSONL byte format must be stable.

**Effort:** L — three integration tests against a real fixture, VCR cassettes for three LLM attempts, and the contract export discipline.

**Risks specific to this step:** Phase 5's sync `GateRunner.run()` byte format may differ from Phase 6's cycle in event ordering (e.g., `at` timestamps); the parity test must normalize wall-clock fields before byte-diff. Document the normalization rules in `tests/integration/conftest.py`.

## Step 8 — Replay-after-kill canary (G2)

**Goal:** SIGKILL during `validate_in_sandbox`; restart fresh process; final state byte-identical to a non-killed reference run.

**Features delivered:**
- `tests/integration/test_replay_after_kill.py` — uses `multiprocessing` to spawn the child running `ainvoke`, kills it via `os.kill(child.pid, signal.SIGKILL)` during `validate_in_sandbox` (configurable delay), then a fresh subprocess re-invokes with the same `workflow_id`. Asserts byte-identical `report.json` + `attempts.jsonl`.
- `tests/integration/test_replay_byte_identical.py` — cleaner reference: runs to completion, then runs again with the same checkpoint, asserts identical outputs without a kill in between.
- `tests/integration/test_chain_seed_mismatch.py` from Step 2 lifted into this canary suite for the killed-then-corrupted-chain edge case.

**Done criteria:**
- [ ] `tests/integration/test_replay_after_kill.py` green — kill at configurable delay (parametrized over delays of 1s, 10s, 50s into `validate_in_sandbox`); each run produces byte-identical artifacts.
- [ ] `tests/integration/test_replay_byte_identical.py` green.
- [ ] WAL recovery verified: post-kill, the next process open of `<workflow_id>.sqlite3` finds the last fsync'd frame intact and rolls back any in-flight WAL frames.
- [ ] `aiosqlite` WAL+NORMAL durability is the only durability primitive — no application-level `os.fsync()` calls (verified by grep against `src/codegenie/graph/`).

**Depends on:** Steps 1–7.

**Effort:** M — the test scaffolding (multiprocessing + SIGKILL + content-address-driven re-invocation) is intricate but well-bounded.

**Risks specific to this step:** macOS and Linux differ in how `aiosqlite` interacts with WAL after SIGKILL; the test must run on both via the CI matrix or document the platform skip. The Phase 5 sandbox-boot wall-clock makes the test slow (~50 s); mark `@pytest.mark.slow` and run only on the merge queue.

## Step 9 — Performance canary (G6) + SQLite throughput watchdog (G9) + ADR-P6-006 escalation hook

**Goal:** Two perf gates land: per-node LangGraph overhead is measured against a committed baseline with a 25% regression tolerance; checkpoint throughput is measured serially and concurrently, with ADR-P6-006 firing if throughput falls below 100 writes/s.

**Features delivered:**
- `tests/perf/test_canary_overhead.py` — 100 no-op-node graph × 1,000 invocations; records p50/p95 to `tests/perf/baseline.json` on first CI run after merge; subsequent runs fail only on >25% regression.
- `tests/perf/test_checkpoint_throughput.py` (nightly) — 1,000 serial `AuditedSqliteSaver.put()` calls; asserts ≥ 100 writes/s on CI hardware.
- `tests/perf/test_checkpoint_concurrent_throughput.py` (per Gap 3 of the arch design) — N=10 `asyncio.Task`s each driving a separate per-workflow `AuditedSqliteSaver` through 100 serial checkpoints; aggregate throughput must scale to ≥ 10× the single-workflow baseline.
- `tests/perf/baseline.json` committed on first CI run after merge; bump procedure documented in `tests/perf/README.md`.
- `tests/perf/test_compile_cold_start.py` from Step 5 incorporated into the perf gate.
- ADR-P6-006 lands as a tripwire — text only at first; if throughput threshold fails on CI hardware post-merge, the ADR's "consequences" block triggers Phase 9 Postgres pull-forward.

**Done criteria:**
- [ ] `tests/perf/test_canary_overhead.py` writes baseline on first run; subsequent runs compare and fail only on > 25% regression.
- [ ] `tests/perf/test_checkpoint_throughput.py` asserts ≥ 100 writes/s; on failure, CI prints "ADR-P6-006 escalation: Postgres pull-forward triggered."
- [ ] `tests/perf/test_checkpoint_concurrent_throughput.py` asserts aggregate throughput ≥ 10× single-workflow throughput; failure escalates ADR-P6-006.
- [ ] All perf tests run nightly via the merge-queue cron; do not gate every PR.
- [ ] `tests/perf/README.md` documents how to update the baseline after a deliberate LangGraph / Pydantic bump.
- [ ] ADR-P6-006 exists with explicit numeric thresholds and a written escalation procedure.

**Depends on:** Steps 1–8.

**Effort:** S — small surface; the canary code is well-trodden Hypothesis-style perf-fixture work.

**Risks specific to this step:** CI-runner noise can produce false regressions on the 25% tolerance; the baseline-update PR procedure must be the documented escape valve, not a `// flaky-skip`. The concurrent-throughput test may surface event-loop overhead that's *not* a disk-fsync bottleneck — surface this as data, not a hard fail, and let ADR-P6-006 own the call.

## Step 10 — Adversarial hardening + Layer-8 E2E + final polish

**Goal:** The adversarial test suite is green; the slow Layer-8 E2E runs end-to-end through `codegenie loop run`; ADRs for Phase 6 are committed; the HITL contract is exported.

**Features delivered:**
- `tests/adversarial/test_forged_human_decision_rejected.py` — `HumanDecision(action="merge")` (not in Literal) rejected by `model_validate`.
- `tests/adversarial/test_out_of_order_transition_rejected.py` — `aupdate_state(as_node="emit_artifact")` from a state at `await_human` rejected.
- `tests/e2e/test_loop_run_vuln_remediation.py` — full `codegenie loop run ./tests/fixtures/repos/cve-fixture/ --cve CVE-2024-FAKE-NPM` ends in exit 0 + `report.json` written.
- ADRs committed under `docs/phases/06-sherpa-state-machine/ADRs/`:
  - ADR-P6-001 — promote `_run_one_attempt` to public `run_one` (renaming-only, or refactor if Gap 2 lands).
  - ADR-P6-002 — lazy-singleton compile of `build_vuln_loop()` with `force_rebuild=True`.
  - ADR-P6-003 — `interrupt()` is called from exactly one node (`await_human`).
  - ADR-P6-004 — HITL operator authentication deferred to Phase 11; single-host trust posture recorded.
  - ADR-P6-005 — `schema_version: Literal["v0.6.0"]` static (not dynamic blake3).
  - ADR-P6-006 — SQLite throughput watch tripwire.
  - ADR-P6-007 — JSON topology is the CI golden; SVG is review-only.
  - ADR-P6-008 (optional, per Gap 1) — roadmap exit-criterion wording vs ADR-0014 default; resolve to amend-roadmap or change-default.
- `docs/contracts/hitl-v0.6.0.json` regenerated; CI gate verifies match.

**Done criteria:**
- [ ] All adversarial tests green (Layer 6 of the pyramid).
- [ ] `tests/e2e/test_loop_run_vuln_remediation.py` green on the merge queue (`@pytest.mark.slow`).
- [ ] All seven (or eight, if ADR-P6-008 lands) ADRs committed in Nygard format.
- [ ] `docs/contracts/hitl-v0.6.0.json` is regenerated and CI-gated.
- [ ] `pre-commit` hook runs ruff + mypy strict on every changed file under `src/codegenie/graph/`.
- [ ] `mypy --strict src/codegenie/graph/` clean across the entire package (G20).
- [ ] Topology golden + JSON contract + ADRs are diff-clean against the committed files.
- [ ] The full Phase 5 regression suite still passes on top of Phase 6 changes (Phase 7 exit-criterion canary: no Phase 0–5 source touched except ADR-P6-001's surgical rename).

**Depends on:** Steps 1–9.

**Effort:** M — ADR drafting is the bulk; tests are mechanical.

## Exit-criteria mapping

| Exit criterion (roadmap Phase 6 §Exit criteria) | Step(s) |
|---|---|
| The vuln-remediation loop runs as a LangGraph state machine | Steps 1, 4, 5, 6, 10 |
| Mid-run kill + resume works without state loss | Steps 2, 8 |
| HITL interrupt fires when trust gates fail twice in a row, and a mocked human approval continues the run | Steps 3, 4 (await_human), 6 (resume CLI), 7 (HITL test parametrized at `max_attempts ∈ {1,2,3}`) |
| State-transition tests assert every conditional edge is exercised at least once | Step 3 (edge property tests, full state-space param), Step 5 (topology reachability) |
| Replay tests use the checkpointer to kill a mid-run workflow, resume it, and assert the same final state | Steps 2, 8 |
| HITL interrupt tests inject mocked human responses and verify the workflow continues correctly | Steps 6, 7 |

Every step appears in the table above except Step 9 (perf canary) and Step 10 (adversarial + E2E + ADRs); both produce CI gates rather than directly bearing a roadmap exit criterion, but Step 10's E2E test is the umbrella check that the first criterion still holds end-to-end after all hardening lands.

## Implementation-level risks

1. **Phase 5's `_run_one_attempt` is not actually a clean single-attempt seam** (Gap 2). *Signal:* reading `src/codegenie/gates/runner.py` reveals the per-attempt body is interleaved with retry-loop state. *Action:* surface a Phase-6 ADR amendment before writing `validate_in_sandbox`; either land a one-line public alias in Phase 5 (preferred, parity test catches drift) or accept a wider Phase-5 refactor and update Phase 5's contract-snapshot tests. **Do not** inline Phase 5's per-attempt logic into the Phase 6 node — the Phase 5 parity test (Step 7) will fail by construction.

2. **LangGraph `aupdate_state(..., as_node="await_human")` may not deterministically inject `human_decision`** such that the next `ainvoke(None, config)` resumes at the right edge. *Signal:* the HITL replay test (Step 7) fails intermittently; or works on `langgraph 0.2.x` but not `0.3.x`. *Action:* pin `langgraph >= 0.2.x, < 0.3.x` in `pyproject.toml`; ship `tests/graph/test_langgraph_version_pin.py` as a compatibility gate. If the test fails on a deliberate bump, surface the LangGraph API-shape change as a release-note item.

3. **The shared `threading.Lock` between Phase 5 `RetryLedger.record` and Phase 6 `AuditedSqliteSaver.put` may not be acquired symmetrically** — one writer may hold a different lock instance from the other. *Signal:* `tests/integration/test_chain_single_writer.py` produces interleaved JSONL events. *Action:* expose the chain lock as a process-global `codegenie.gates.retry_ledger.CHAIN_LOCK` and have both writers import the *same* lock object. Verify by `id()` equality in the test.

4. **The `max_attempts` mid-run override semantics are silently surprising** (Gap 1 + Risk #4 of the arch design). The CLI advertises `--max-attempts` but Phase 6 freezes it at graph-build time; an operator who passes `--max-attempts 5` on `resume` will be silently ignored. *Signal:* operator confusion at the first HITL run. *Action:* `cli/loop.py resume` rejects `--max-attempts` with a clear error; document the freeze in `--help` output and in the operator runbook stub.

5. **The 25% perf-regression tolerance produces flaky failures on noisy CI runners** (Step 9). *Signal:* CI green / red flapping on baseline-adjacent PRs. *Action:* document the baseline-update procedure in `tests/perf/README.md`; require a deliberate `git commit tests/perf/baseline.json` to bump it; never `// flaky-skip` the perf gate — surface the noise via Risk #5 escalation to ADR-P6-006 if needed.

6. **HITL `continue` after a same-signature flake silently routes to `non_retryable`** (Gap 4). *Signal:* operator approves `continue` on a flaked workflow; the very next gate evaluation routes back to `await_human`. *Action:* document the behavior loudly in `cli/loop.py resume` output (print a warning when resuming against a same-signature-flaked state); add `test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py` to the test pyramid; surface as a Phase-6 ADR (proposed P6-009) if a behavior change is preferred.

## What's next — handoff to Phase 7

After Phase 6 merges, the system is materially different along these axes:

- **`build_vuln_loop()` factory is import-stable.** Phase 7 ships `build_distroless_loop()` as a *sibling* under `src/codegenie/graph/` — no edits to `vuln_loop.py`, `state.py`, `edges.py`, or any vuln node. Phase 7's "no Phase 0–6 source modified" exit criterion is preserved by construction.
- **`VulnLedger` and `DistrolessLedger` are siblings, not subclasses.** ADR-0022 Three Strikes: vuln is strike one, distroless is strike two; abstraction waits for strike three (likely Phase 15 recipe-authoring).
- **`HumanRequest` / `HumanDecision` (`docs/contracts/hitl-v0.6.0.json`) are the task-class-agnostic HITL contract.** Phase 7 adds new `reason` literals (e.g., `"base_image_unavailable"`) via additive Literal extension; Phase 11 either consumes the existing shape or amends.
- **`AuditedSqliteSaver` + the extended BLAKE3 chain are the durability + tamper-evidence primitives.** Phase 7's distroless loop uses the same checkpointer at a sibling per-workflow path; the chain extends across both task classes.
- **`codegenie loop` CLI namespace is established.** Phase 7 ships either `codegenie loop run --task migration` or a parallel `codegenie distroless run` — Phase 6 leaves the choice open but the CLI-per-orchestration-layer pattern is set.
- **The full Phase 3–4–5 retry chain is now expressible as a topology** — `codegenie loop inspect` and `codegenie loop render` give operators a working introspection tool. Phase 8's planner will dispatch above this; Phase 9's Temporal wraps below.
- **ADR-P6-006 is the open tripwire.** If Phase 6's perf canary fires < 100 writes/s on CI hardware, Phase 7 carries the Postgres pull-forward decision into its own scope.
