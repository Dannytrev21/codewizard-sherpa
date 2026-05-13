# Phase 6 — SHERPA-style state machine for the vuln loop: Security-first design

**Lens:** Security — auditability, tamper-evidence, least privilege, replay safety.
**Designed by:** Security-first design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 6 is the phase where **the loop becomes durable**. Until now the orchestrator was a Python process that crashed cleanly: anything not flushed to the BLAKE3 audit chain by `os._exit` was simply gone. Phase 6 swaps that for a Pydantic state ledger persisted to a SQLite checkpointer that **survives process death by design**. The same checkpointer also rehydrates state across an `interrupt()` that may pause the workflow for hours or days waiting on a human. The minute we make state durable, we make state attackable: persisted blobs sit on disk, can be edited offline, can be replayed, and can be smuggled across workflow boundaries by an attacker who got write access to `.codegenie/`. Worse, the LangGraph runtime turns *every* conditional-edge decision into a record on the wire — a tampered `retry_count` field is now a way to bypass [ADR-0014](../../production/adrs/0014-three-retry-default-per-gate.md)'s three-retry cap, and a forged `verdict: pass` is a way to bypass [ADR-0009](../../production/adrs/0009-humans-always-merge.md)'s human-merge invariant if Phase 11 ever reads it.

I optimized — in priority order — for: (1) **the state ledger and the checkpointer DB are tamper-evident** — every checkpoint extends the BLAKE3 audit chain from Phases 2–5 with a `checkpoint.write` event whose digest covers the serialized state blob, and the runtime refuses to resume from a checkpoint whose state digest does not match the chain's claim; (2) **conditional edges are deterministic and replay-equivalent** — given the same `LoopState` snapshot, the routing function returns the same edge label, and any non-determinism (wall-clock, env, `random`, untyped LLM output) inside an edge is a security bug that blocks merge; (3) **least privilege per node** — each LangGraph node receives a `LoopState` view limited to the fields it declares it reads and writes (a runtime-enforced field-level ACL on the Pydantic model, not a convention); (4) **replay-safe side effects** — every node that performs a non-idempotent external call (LLM, sandbox spawn, branch write, audit-chain append) is wrapped in a side-effect guard that records the call's deterministic key on first execution and short-circuits on resume; (5) **HITL trust boundary is real** — the `interrupt()` payload is signed by gate-control, the resume payload is countersigned by a human approver whose identity comes from a per-host operator credential (not a `dict[str, Any]` from the orchestrator's CLI), and the resumed run records the approver in the audit chain; (6) **bounded state schema** — `LoopState` is `BaseModel` with `extra="forbid", frozen=True`, no `dict[str, Any]`, no `Any` field anywhere, with a CI introspection test that fails the build if a future PR introduces one.

I deprioritized: graph-inspection ergonomics (the `langgraph-cli` UI is convenient but it must never speak directly to the production checkpointer — it talks to a read-only replica in dev, period), throughput (Phase 6 is single-workflow, sync, one checkpoint write per node — Phase 9's Temporal Postgres backend is the right place to scale), and operator convenience around the HITL resume flow (resuming is **deliberately a two-step explicit operator action**; there is no "auto-approve" mode in Phase 6, ever).

The structural choice that defines this lens: **the checkpointer is a security surface, not infrastructure.** A SQLite file sitting at `.codegenie/checkpointer/<workflow-id>.db` is treated with the same gravity as a private key — `0600` mode, owner-only, never world-readable, never copied across hosts without re-anchoring its chain, and **always** mirrored by the BLAKE3 audit chain so that an attacker who edits the DB without also forging the chain is detected at resume.

A note on roadmap fidelity. The roadmap's Phase 6 scope is small (`langgraph`, `pydantic`, `aiosqlite`, `langgraph-cli`); it does not say "encrypt the checkpointer." This design **does not** add encryption-at-rest as a Phase 6 requirement — that's Phase 16's multi-tenancy work. What it does add, and what I claim is Phase 6's responsibility, is the **tamper-evidence layer over an unencrypted DB**: chain-anchored checkpoint digests, signed `interrupt()` envelopes, schema-pinned serialization, and a startup verification pass. Encryption protects confidentiality; tamper-evidence protects integrity. The latter is the load-bearing property for a system that opens PRs to other people's repos.

---

## Goals (concrete, measurable)

- **Auditability target — what must be reconstructible from logs:**
  Given only `.codegenie/remediation/<run-id>/` on disk (the BLAKE3-chained `audit/<run-id>.jsonl`, the checkpointer DB, the `attempts.jsonl` from Phase 5, and the sandbox run dirs), an investigator must be able to reconstruct: (a) the exact sequence of LangGraph node executions, (b) the conditional-edge label chosen at every branching point and the `LoopState` snapshot that determined it, (c) every checkpoint write and the state digest at that point, (d) every `interrupt()` event including who resumed it and with what payload, (e) every retry counter transition, (f) every gate verdict and the `ObjectiveSignals` payload that produced it. **No event is implicit.** Wall-clock duration, node entry/exit timestamps, and the BLAKE3 chain head at each event are all on the line.

- **State-ledger invariants enforced (by code, not by convention):**
  1. `LoopState` is `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)`.
  2. No field on `LoopState` has type `Any`, `dict[str, Any]`, `object`, or untyped `Mapping`. A CI introspection test walks every reachable field and rejects these types.
  3. No field name contains `confidence`, `llm_says`, `self_reported`, `model_self_reported`, `model_says` — same lock as Phase 5 on `ObjectiveSignals`, lifted into `LoopState` so [ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md) is enforced at the ledger level.
  4. Every field has an explicit `read_acl` and `write_acl` (set of node names) declared via a Pydantic field annotation; a runtime check fails the node call if it reads or writes a field outside its ACL.
  5. State mutations are produced via **typed reducer functions** (`add_attempt`, `record_verdict`, `set_resume_marker`) — nodes return a reducer call, not a raw `LoopState`. Reducers are pure and unit-tested.

- **Replay-safety property:**
  Resuming any workflow from any persisted checkpoint produces **byte-identical** subsequent state if no new external input arrives. Specifically:
  - Re-running a node whose side effects already happened is a **no-op**, detected by a deterministic side-effect-key lookup against the audit chain.
  - The conditional-edge function `route_after_gate(state) -> Literal[...]` is pure: given the same `state`, returns the same edge label every call (property-tested across 10k randomly-shaped states).
  - A killed process's mid-node interrupt is re-entered from the last checkpoint, not from mid-execution: nodes that intend to perform side effects checkpoint *before* the call and verify *after*.

- **HITL authentication model:**
  An `interrupt()` event is **signed by gate-control** with the per-orchestrator HMAC key established at handshake (continued from Phase 5). The interrupt payload contains: workflow_id, node name, current chain head, current state digest, reason code, and an opaque per-interrupt nonce. Resume requires a **countersigned approval**: the operator runs `codegenie hitl approve <interrupt-id> --decision=advance|abort --notes=<text>`; the CLI reads a per-host operator key (file at `~/.config/codegenie/operator.key`, 0600, generated by `codegenie operator init`), signs the approval envelope, and the orchestrator on resume verifies both signatures. The approver's key fingerprint and the approval timestamp are written to the audit chain. **There is no in-process `--auto-approve` flag.** Tests inject mocked approvals by writing a test-fixture operator key into a tempdir — they never bypass the verification path; the test code holds the same signing key the production code would verify against.

- **Secrets-handling stance:**
  No secret is ever serialized into a checkpoint. `LoopState` may contain references to secret-bearing inputs (a `prompt_context_path`) but never the bytes. The Anthropic API key, the GitHub PAT (not yet introduced in Phase 6 but reserved), the audit-chain signing key, the operator HMAC key, and the gate-control HMAC key are all held by *processes*, not state. A CI test asserts that `LoopState`'s Pydantic JSON schema has no field whose name contains `key|token|secret|password|cred`. Serialization to the checkpointer uses a custom encoder that redacts any value tagged `SecretStr` (the Pydantic primitive); a property test feeds it adversarial states and asserts the on-disk bytes contain no allowlisted secret pattern.

---

## Threat model

### Assets

1. **The checkpointer SQLite database** at `.codegenie/checkpointer/<workflow-id>.db`. Holds every checkpoint's serialized state blob, the LangGraph thread metadata, and the resume markers. Compromise → an attacker can roll the workflow back to a state of their choosing, replay a verdict that previously failed, or inject a forged state with `retry_count=0` to skip the three-retry cap.
2. **The audit chain** `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl`. Phase 2/3/4/5 BLAKE3 chain — Phase 6 extends with `checkpoint.write`, `edge.taken`, `interrupt.raised`, `interrupt.approved`, `node.entered`, `node.exited`. The chain is the off-the-DB witness to checkpoint integrity. Compromise → silent rewrite of history.
3. **The `LoopState` Pydantic model definitions**. The schema is the contract; if the schema is altered between checkpoint and resume in incompatible ways, state corruption follows. The model definitions live in source — a malicious commit could change them.
4. **The HITL operator key** at `~/.config/codegenie/operator.key`. The single artifact that authorizes resume of a paused workflow. If stolen, an attacker can resume any paused workflow and forge any approval.
5. **The gate-control HMAC key** (continued from Phase 5). The signer of `interrupt()` events and of cross-boundary state-digest claims.
6. **The orchestrator process address space**. Holds the Anthropic key (Phase 4), the AF_UNIX socket to gate-control (Phase 5), and now the in-memory `LoopState` plus the SQLite connection. A compromise of orchestrator memory leaks any of these.
7. **The `langgraph-cli` inspection surface**. A debugging tool that reads checkpoints and renders state. If it ever speaks directly to a production DB or if its rendering deserializes attacker-controlled blobs, it is a pivot.

### Adversaries

- **Checkpoint-tampering adversary.** Has filesystem write on the orchestrator host. Goal: edit `<workflow-id>.db` to change `retry_count`, `verdict`, or to insert a forged `interrupt_approved` marker.
  Mitigations: every checkpoint write emits a `checkpoint.write` audit event carrying `blake3(state_blob || prev_chain_head)`; resume verifies the persisted state's digest matches the chain claim; mismatch raises `CheckpointTampered` and refuses to run. The SQLite DB is `0600`; the BLAKE3 chain is also `0600` and append-only by `O_APPEND`; the attacker must forge *both* — which requires the audit-chain signing key, which lives in a separate process.

- **Replay-attack adversary.** Has a copy of an old, validly-signed checkpoint (e.g., from a backup snapshot) and tries to re-anchor it as the current state.
  Mitigations: the chain is monotonic; resume re-anchors to the chain's *current head*, not the checkpoint's claimed-prior head. A checkpoint whose claimed prior-head is older than the chain's current head is rejected. The audit chain's append-only file is the source of truth for "what happened most recently."

- **State-injection adversary.** Influenced the LLM (Phase 4) such that the model output, when parsed, mutates a `LoopState` field it should not touch (e.g., LLM-emitted JSON that, when fed to a node's reducer, attempts to overwrite `verdict` or `interrupt_approved_by`).
  Mitigations: nodes do not consume raw LLM output as state mutations. The Phase 4 `OutputValidator` already produces a `RecipeApplication` Pydantic model — Phase 6 nodes consume only typed models. Reducers are explicit (`record_recipe_application`, `record_attempt`); a reducer cannot mutate a field outside its declared scope (enforced by per-reducer field ACLs).

- **Non-determinism-pivoted adversary.** Pushed a PR that uses `random.random()`, `time.time()`, `os.environ.get(...)`, or untyped `dict.get()` inside a conditional-edge function. Now the same checkpoint may route differently on resume, allowing a previously-failed branch to be skipped.
  Mitigations: conditional-edge functions live in `loop/edges.py` and are guarded by a `@pure_edge` decorator that snapshot-tests against 10k random `LoopState` inputs (Hypothesis); a fence-CI test asserts no module under `loop/edges/` imports `random`, `time`, `os`, or `datetime` (only `datetime.datetime.fromisoformat` for parsing string fields is whitelisted); edge functions return a `Literal[...]` not a string, so a typo in the return value is a type error not a routing bug.

- **HITL-bypass adversary.** Operator passes `--unsafe-mode-resume` or otherwise tries to resume an interrupted workflow without the operator key.
  Mitigations: there is no `--unsafe-mode-resume`. Resume requires `~/.config/codegenie/operator.key` and a `codegenie hitl approve` call whose signature is verified against the operator's registered public key in the workflow's run-dir. A test asserts CLI rejects resume without a valid signed approval; a static test asserts no codepath constructs a `ResumeEnvelope` without calling `OperatorKey.sign(...)`. The mock-human responses used in tests sign with a fixture key whose fingerprint is hard-coded into the test fixture's `expected_approvers.json` — the test code holds the same signing material the production verifier checks; tests cannot be a backdoor because the production verifier rejects unknown fingerprints.

- **Resume-payload-injection adversary.** Operator (compromised account) writes a valid approval but with a malicious `notes` field, a malicious `decision`, or a malicious supplementary payload that the resume reducer feeds back into `LoopState`.
  Mitigations: the resume envelope schema is locked: `decision: Literal["advance", "abort"]`, `notes: str` capped at 1 KB and fence-wrapped before reaching any LLM call, `supplementary_payload: None` (always — Phase 6 has no field for operator-supplied state; if a future phase needs one, an ADR amendment changes this).

- **Side-effect replay adversary.** Kills the orchestrator mid-LLM-call and restarts; tries to make the resume re-call the LLM, doubling cost or producing a different patch that bypasses the audit trail.
  Mitigations: every node that performs an external side effect (`call_llm`, `spawn_sandbox`, `apply_transform`, `write_branch`) emits a `sideeffect.started` audit event *before* the call, with a deterministic key derived from the state-at-call-time; on resume, if the chain shows a `sideeffect.started` with no matching `sideeffect.completed`, the node either: (a) checks for a recoverable artifact (the Phase 5 sandbox run dir, the Phase 4 LLM response cache), or (b) marks the node as failed with `recovery_required=true` and `interrupt()`s. The node never silently re-issues a side effect on resume.

- **Schema-drift adversary.** A future PR adds a field to `LoopState` and a workflow checkpointed under the old schema is resumed under the new code.
  Mitigations: every checkpoint blob carries a `schema_version` (BLAKE3 of the sorted Pydantic JSON schema of `LoopState`); resume compares persisted version against current version; mismatch raises `SchemaDrift` and *refuses* to resume — the operator must run `codegenie migrate-checkpoint --from <old> --to <new> --review` which produces a human-reviewable diff before any state mutation. There is no automatic upgrade path in Phase 6.

- **`langgraph-cli` pivot.** The inspection tool deserializes a malicious checkpoint and is exploited (Pickle-style, or via JSON deserialization in a vulnerable lib).
  Mitigations: serialization is **JSON only** (LangGraph's `MsgPackSerializer` is rejected for Phase 6 because MessagePack ext types are an attack surface for naive consumers); the `langgraph-cli` is run against a *copy* of the checkpointer file mounted read-only; in production (Phase 16+) the CLI is firewalled off from the prod DB entirely; for Phase 6, the dev rule is "the CLI never speaks to a path under `.codegenie/checkpointer/` of a live workflow."

- **Operator-misuse adversary.** Operator deletes a `.codegenie/checkpointer/<workflow-id>.db` file out of band (cleanup, disk pressure) and then re-runs the same `workflow-id`, expecting fresh state.
  Mitigations: `workflow-id` is content-addressed from the input bundle (`blake3(repo_path || cve_id || patch_attempt_input)`); attempting to start a workflow with a `workflow-id` whose chain contains a `workflow.completed` event raises `WorkflowAlreadyCompleted`; attempting to start with a chain that has `interrupt.raised` but no matching `interrupt.approved` raises `WorkflowPausedAwaitingResume`; the DB and chain are inseparable.

### Attack surfaces specific to Phase 6

1. **Checkpointer write path.** Every state mutation crosses an `aiosqlite` write. Surface: SQL injection (mitigated by parameterized queries through LangGraph's `AsyncSqliteSaver`), blob-size attacks (mitigated by a 64 KB hard cap per checkpoint blob; `LoopState` does not inline large artifacts — it references them by path), concurrent writers (Phase 6 ships **per-workflow SQLite files** so there is only ever one writer per file; concurrency is across files, not within).
2. **Checkpointer read/resume path.** Surface: deserialization of attacker-controlled JSON, schema-version race, chain-replay. Mitigations are listed under "Replay-attack adversary" and "Schema-drift adversary" above.
3. **`interrupt()` payload over Python channel.** LangGraph's `interrupt()` is in-process; the payload goes to the orchestrator's stdout/stderr or to a side channel. Surface: the payload is auto-serialized into the next checkpoint as a `__interrupt__` annotation; an attacker who can write the in-process value before checkpointing can poison the resume. Mitigation: the `interrupt()` call is wrapped in `raise_interrupt_for_human(reason, state)` which signs the payload with gate-control's HMAC; the resume verifier rejects unsigned `__interrupt__` annotations.
4. **Conditional-edge function source.** The set of routing functions in `loop/edges/` is the policy code that decides whether a workflow advances or escalates. A bug here is a security bug. Mitigation: every edge function is property-tested; the test fixture set contains adversarially-shaped `LoopState` instances (including ones with maximum legal values for all numeric fields, ones with empty optional fields, and ones with field-injection candidates); test coverage is reported per edge function with a 100% line / 95% branch floor.
5. **The reducer functions.** Every state mutation crosses a reducer. Surface: a reducer that mutates a field outside its declared ACL is a privilege escalation across nodes. Mitigation: each reducer carries `writes: frozenset[str]`; a runtime check after every reducer call asserts the diff matches `writes`; CI test enforces the same statically by AST inspection.
6. **The HITL `approve` CLI.** The CLI signs an envelope and submits it. Surface: phishing (operator approves the wrong workflow), key theft (operator key on disk), command-line injection. Mitigations: the CLI prints the *full* interrupt context to terminal before signing — workflow_id, repo path, CVE, current chain head, reason — and requires `--workflow-id <id>` to match; key permissions are `0600` and `codegenie operator init` warns if `umask` is too permissive; CLI arg parsing is `click` only, no shell-out.

### Trust boundaries

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │  HOST OPERATOR  (TRUSTED)                                            │
   │  - ~/.config/codegenie/operator.key (0600, generated by `init`)      │
   │  - never enters orchestrator process address space (signing only)    │
   └────────────────────────┬─────────────────────────────────────────────┘
                            │  `codegenie hitl approve <interrupt-id>`
                            │  signs envelope with operator.key
                            ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  HITL CLI PROCESS  (TRUSTED)                                         │
   │  - one-shot per approval; exits after writing signed envelope        │
   │  - prints interrupt context for the operator to read before sign     │
   └────────────────────────┬─────────────────────────────────────────────┘
                            │ writes signed envelope:
                            │ .codegenie/remediation/<run-id>/interrupts/
                            │   <interrupt-id>.approval.json
                            ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  ORCHESTRATOR  (SEMI-TRUSTED)  — Phase 6 owns:                       │
   │  - LangGraph runtime, `LoopState` in memory                          │
   │  - aiosqlite connection to <workflow-id>.db (0600)                   │
   │  - reads but does not hold operator.key                              │
   │  - reads gate-control HMAC key from per-process handshake (Phase 5)  │
   │  - extends BLAKE3 audit chain on every node entry/exit, every edge,  │
   │    every checkpoint, every interrupt, every resume                   │
   └──────────┬────────────────────────────────────────────┬──────────────┘
              │                                            │
              ▼                                            ▼
   ┌──────────────────────┐                ┌──────────────────────────────┐
   │ CHECKPOINTER          │               │ AUDIT CHAIN                  │
   │ <workflow-id>.db      │               │ audit/<run-id>.jsonl         │
   │ aiosqlite, 0600       │               │ append-only, 0600, O_APPEND  │
   │ JSON serializer only  │               │ BLAKE3-linked from Phase 2   │
   │ blobs ≤ 64 KB         │               │ extended by Phase 6 events:  │
   │ schema_version-tagged │               │   checkpoint.write           │
   │                       │               │   edge.taken                 │
   │ TRUST BOUNDARY:       │               │   node.entered / exited      │
   │  digest of every blob │ ─── mirrors ──▶│   interrupt.raised           │
   │  is recorded in the  │               │   interrupt.approved         │
   │  audit chain — the    │               │   sideeffect.started/done    │
   │  DB cannot lie alone  │               │   schema_drift.detected      │
   └───────────────────────┘               └──────────────────────────────┘
              ▲
              │ inspection only (read-only copy)
              │
   ┌──────────────────────────────────────────────────────────────────────┐
   │  langgraph-cli  (DEV-ONLY, NEVER PROD)                               │
   │  - operates on a *copy* of the checkpointer file                     │
   │  - never connects to a live workflow's DB                            │
   │  - JSON-only serializer (no msgpack ext deserialization)             │
   └──────────────────────────────────────────────────────────────────────┘
```

The boundary marked **TRUST BOUNDARY** is the load-bearing one for Phase 6: it asserts that the checkpointer file alone is not authoritative — the audit chain is the witness that says what the checkpointer *should* contain. An attacker who edits one without the other is detected at resume.

---

## Architecture

```
codegenie remediate <repo> --cve <id>
                │
                ▼ (Phase 3/4/5 unchanged; Phase 6 wraps Stage-3-through-5)
┌─────────────────────────────────────────────────────────────────────────┐
│  Phase 3 RemediationOrchestrator                                         │
│    Stages 1–2 unchanged.                                                 │
│    Stage 3 (Plan), Stage 4 (Apply), Stage 5 (Validate) lifted into a    │
│    LangGraph state machine. The orchestrator now does:                  │
│      graph = build_vuln_loop_graph(...)                                 │
│      checkpointer = SqliteSaver.from_path(                              │
│         f".codegenie/checkpointer/{workflow_id}.db")                    │
│      result = graph.invoke(initial_state, config=                       │
│         {"configurable": {"thread_id": workflow_id,                     │
│                            "operator_key_fingerprint": opfp}})          │
└────────────────────┬────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  src/codegenie/loop/  — Phase 6 new package                              │
│                                                                          │
│  graph.py                                                                │
│    build_vuln_loop_graph() -> CompiledStateGraph:                       │
│      nodes:                                                              │
│        plan_recipe          (reads RepoContext; writes recipe_choice)    │
│        plan_rag             (reads recipe_choice; writes rag_hits)       │
│        plan_llm             (reads rag_hits;  writes llm_plan;           │
│                              SIDE-EFFECT: invokes Phase 4 LLM)           │
│        apply_transform      (reads llm_plan; writes patch_blake3;        │
│                              SIDE-EFFECT: writes patch file)             │
│        validate_in_sandbox  (reads patch_blake3; writes signals;         │
│                              SIDE-EFFECT: spawns Phase 5 sandbox)        │
│        record_verdict       (reads signals; writes verdict, attempts[]) │
│        await_human_review   (writes resume_marker; INTERRUPT NODE)       │
│        commit_branch        (reads verdict; SIDE-EFFECT: git branch)     │
│        finalize_pass / finalize_escalate (terminal)                     │
│      edges: every transition is conditional; pure functions in          │
│              loop/edges.py; route_after_validate decides:               │
│                pass     → commit_branch                                  │
│                fail<3   → plan_llm  (re-plan with prior_attempts)        │
│                fail==3  → await_human_review                             │
│                unrecoverable → finalize_escalate                         │
│  state.py                                                                │
│    class LoopState(BaseModel, extra="forbid", frozen=True):              │
│      schema_version: str               # blake3 of sorted JSON schema    │
│      workflow_id: str                                                    │
│      chain_head_at_entry: bytes        # the BLAKE3 chain head           │
│      repo_path: Path                                                     │
│      cve_id: str                                                         │
│      recipe_choice: RecipeChoice | None                                  │
│      rag_hits: tuple[RagHit, ...] | None                                 │
│      llm_plan: LlmPlan | None                                            │
│      attempts: tuple[AttemptSummary, ...] = ()                           │
│      verdict: Literal["pass","fail","unrecoverable"] | None              │
│      pending_interrupt: InterruptEnvelope | None                         │
│      resume_marker: ResumeMarker | None                                  │
│      sideeffect_log: tuple[SideEffectRecord, ...] = ()                   │
│      # Every field carries Field(json_schema_extra={                     │
│      #   "read_acl": [...], "write_acl": [...] })                        │
│  edges.py                                                                │
│    @pure_edge                                                            │
│    def route_after_validate(s: LoopState) -> Literal["pass","retry",     │
│                                                        "escalate"]: ...  │
│    @pure_edge ...     (all 7 edge functions; no imports of               │
│                         random, time, os, datetime except                │
│                         datetime.datetime.fromisoformat)                 │
│  reducers.py                                                             │
│    @reducer(writes=frozenset({"attempts","sideeffect_log"}))             │
│    def add_attempt(s, summary): ...                                      │
│    @reducer(writes=frozenset({"verdict"})) ...                           │
│    @reducer(writes=frozenset({"pending_interrupt","resume_marker"}))     │
│    def raise_interrupt_for_human(s, reason, gate_signal): ...            │
│    Every reducer body emits a chain event before returning new state.    │
│  checkpointer.py                                                         │
│    class AuditedSqliteSaver(SqliteSaver):                                │
│      def put(self, config, checkpoint, metadata):                        │
│        blob = serialize_json(checkpoint)                                 │
│        digest = blake3(blob || prev_chain_head)                          │
│        audit_chain.append({"kind":"checkpoint.write", ...})              │
│        super().put(...)                                                  │
│      def get(self, config):                                              │
│        ckpt = super().get(...)                                           │
│        if blake3(serialize_json(ckpt)) != expected_digest_from_chain:    │
│           raise CheckpointTampered                                       │
│        if ckpt.schema_version != current_schema_version():               │
│           raise SchemaDrift                                              │
│        return ckpt                                                       │
│  sideeffects.py                                                          │
│    @side_effect("llm_call")                                              │
│    def call_llm_node(state: LoopState) -> ReducerCall: ...               │
│      key = deterministic_sideeffect_key(state, "llm_call")               │
│      if audit_chain.find_completed(key): return replay_from_chain(key)   │
│      audit_chain.append({"kind":"sideeffect.started","key":key,...})     │
│      result = phase4.fallback_tier.run(...)                              │
│      audit_chain.append({"kind":"sideeffect.completed","key":key,...})   │
│      return add_llm_plan(state, result)                                  │
│  interrupts.py                                                           │
│    def raise_interrupt(state, reason, signals) -> NoReturn:              │
│      env = InterruptEnvelope(workflow_id, node, chain_head, state_digest,│
│                              reason, nonce=os.urandom(16))               │
│      sig = gate_control_hmac.sign(env.canonical_bytes())                 │
│      audit_chain.append({"kind":"interrupt.raised", "env":env,           │
│                          "gate_sig":sig})                                │
│      write_envelope_to(f"<run>/interrupts/{env.id}.pending.json")        │
│      langgraph.interrupt(env.id)                                         │
│    def verify_resume(env_id) -> ResumeApproval:                          │
│      approval = read_json(f"<run>/interrupts/{env_id}.approval.json")    │
│      assert OperatorKeyVerifier.verify(approval)                          │
│      assert approval.fingerprint in expected_approvers                    │
│      assert approval.workflow_id == current_workflow_id                  │
│      assert approval.decision in {"advance","abort"}                     │
│      audit_chain.append({"kind":"interrupt.approved", "approval":...})   │
│      return approval                                                     │
│  cli_hitl.py                                                             │
│    codegenie hitl list      — list pending interrupts                    │
│    codegenie hitl show <id> — print full context (read interactively)    │
│    codegenie hitl approve <id> --decision={advance|abort} --notes=...    │
│                                                                          │
│  Cross-cutting (extensions to Phase 0–5 modules):                        │
│    audit/chain.py — extended with Phase 6 event types (additive)         │
│    cli/remediate.py — `--resume <workflow-id>` flag added                │
│    sandbox/, gates/, rag/, recipes/ — UNCHANGED (extension by addition)  │
└─────────────────────────────────────────────────────────────────────────┘

Package layout (new files only):
src/codegenie/loop/
  __init__.py
  graph.py                # build_vuln_loop_graph
  state.py                # LoopState + field ACLs + SecretStr discipline
  edges.py                # @pure_edge functions; one Literal-returning fn each
  reducers.py             # @reducer functions; field-ACL-checked
  checkpointer.py         # AuditedSqliteSaver wrapping AsyncSqliteSaver
  sideeffects.py          # @side_effect decorator + replay machinery
  interrupts.py           # InterruptEnvelope + signing + verification
  operator_key.py         # OperatorKeyStore + signature primitives
  schema_version.py       # blake3 of sorted Pydantic JSON schema
  cli_hitl.py             # codegenie hitl {list,show,approve}
  health/probe.py         # CheckpointerHealthProbe (ADR-0007 input)
  errors.py
tests/loop/...
tools/operator/
  README.md               # how to generate/rotate operator.key

Fence-CI extensions:
  loop/edges/            may NOT import random, time, os, datetime
                          (except datetime.datetime.fromisoformat)
  loop/                  may NOT import langgraph-cli's runtime
  loop/                  may NOT import anthropic|chromadb directly
                          (LLM access goes through phase4.fallback_tier)
```

---

## Components

### `LoopState` (the typed state ledger)

- **Purpose:** The one and only mutable artifact crossing nodes. Pydantic `BaseModel` with `extra="forbid", frozen=True`. Every field has an explicit type, a read ACL, and a write ACL.
- **Interface:** consumed by every node via `state` parameter; mutated only via `@reducer` calls that return `LoopState.model_copy(update={...})`. Nodes return `ReducerCall(reducer_name, *args)`, not raw `LoopState`.
- **Internal design (security reasoning):** The two CI introspection tests are the load-bearing controls. (1) `test_no_untyped_fields_in_loopstate.py` walks the Pydantic model field-by-field and rejects `Any`, `dict[str, Any]`, `object`, untyped `Mapping`. (2) `test_no_secret_named_fields_in_loopstate.py` rejects field names matching `key|token|secret|password|cred|api`. (3) `test_no_self_confidence_in_loopstate.py` lifts Phase 5's ADR-0008 lock — rejects `confidence|llm_says|self_reported|model_self_reported|model_says`. The `read_acl` / `write_acl` annotations are read at node-registration time and enforced at runtime by `enforce_field_acl(state_before, state_after, node_name)` after every node returns.
- **Tradeoffs accepted:** Adding a new field is an explicit code change with ACL declarations and an ADR-P6 amendment if the field carries security weight (verdict, interrupt, retry counter). The friction is the point. `frozen=True` means every mutation allocates a new model — small CPU/GC cost; the security gain (no in-place tampering via shared references) is worth it.

### `AuditedSqliteSaver` (the checkpointer wrapper)

- **Purpose:** The tamper-evidence layer over LangGraph's stock `SqliteSaver` (or `AsyncSqliteSaver` for the `aiosqlite` path the roadmap names). Wraps `put` / `get` / `list` so that every write extends the BLAKE3 audit chain and every read verifies the digest.
- **Interface:** Same as `BaseCheckpointSaver`; drop-in replacement. The wrapper enforces: JSON serializer only (`MsgPackSerializer` rejected); blob size ≤ 64 KB (raises `CheckpointTooLarge`); writes are wrapped in a `SAVEPOINT` so an audit-chain failure rolls back the DB write atomically.
- **Internal design (security reasoning):** The wrapper is the only code allowed to call `self._cursor.execute(...)` against the checkpointer DB; a fence-CI rule enforces this. On every `put`, it computes `blake3(json_bytes || prev_chain_head)`, appends a `checkpoint.write` event whose digest is the value, then writes the DB row in the same SAVEPOINT (if the audit append fails, the DB write rolls back — ordering is "chain first, then DB," not the reverse, so a partial failure leaves the DB consistent with the chain or empty). On every `get`, the wrapper recomputes the digest and matches against the chain's last `checkpoint.write` for the same `(thread_id, checkpoint_id)`; mismatch raises `CheckpointTampered`. The DB file mode is `0600` enforced at open time; if the file already exists with looser permissions, the wrapper refuses to use it.
- **Tradeoffs accepted:** Two writes per checkpoint (chain + DB) instead of one. Latency cost: ~1–2 ms per checkpoint. The SAVEPOINT means we cannot use SQLite's auto-commit mode — a write transaction is held for the duration of one node's checkpoint sequence. For Phase 6's per-workflow scope (one writer per file) this is fine; Phase 9's Postgres backend revisits.

### `@pure_edge` decorator + edge functions (`loop/edges.py`)

- **Purpose:** Conditional-edge functions are policy code. Make them pure, testable, and statically guaranteed not to leak time / env / randomness into routing decisions.
- **Interface:** Each function takes `LoopState` and returns a `Literal[...]` of edge labels. The decorator: (a) records the function name and `Literal` return type in a registry; (b) at import time, AST-inspects the function body and rejects any reference to a banned name (`random.*`, `time.*`, `os.environ`, `datetime.datetime.now`, `datetime.datetime.utcnow`); (c) registers the function with the Hypothesis property-test suite that runs at CI time.
- **Internal design (security reasoning):** Determinism is the security property. The Hypothesis test generates 10k `LoopState` instances (using Pydantic-derived strategies that cover every Literal value, every Optional present/absent combination, and the boundary values for every retry counter) and asserts the same input produces the same output. Coverage is reported per edge function with a 100% line / 95% branch floor — a missing branch in a routing function is a hidden default-route, which is a routing-bypass vulnerability.
- **Tradeoffs accepted:** Edge functions cannot consume "current time" for routing — fine, time-based routing is a security anti-pattern anyway. If a future phase needs time-of-day routing (it shouldn't), it must materialize the time into `LoopState` at workflow entry, not read it from `datetime.now()` inside the edge.

### `@reducer` decorator + reducers (`loop/reducers.py`)

- **Purpose:** The only legitimate way to mutate `LoopState`. Each reducer declares the fields it writes; runtime and CI both enforce that the diff matches.
- **Interface:** `@reducer(writes=frozenset({"attempts"}))` annotates a function `(state, *args) -> LoopState`. Nodes return `ReducerCall("add_attempt", summary)` rather than a raw state; LangGraph's reducer-merging is replaced by an explicit `apply_reducer(state, call)` dispatch in the graph's after-node hook.
- **Internal design (security reasoning):** Two layers. (1) Static: a CI AST scan walks every reducer body and asserts no field outside `writes` is assigned. (2) Runtime: after `apply_reducer` returns, `enforce_field_acl(before, after, reducer_name)` diffs the two `LoopState`s and asserts the diff fields are a subset of `writes`. A reducer that violates either layer raises `ReducerEscapedAcl` — a non-retryable, escalating error. The set of reducers is small (Phase 6 ships ~10) and each is unit-tested for the diff property with a fixture for every legal arg combination.
- **Tradeoffs accepted:** More code per state mutation than `state.attempts.append(x)`. The friction is exactly the principle of least privilege made concrete: a node can only do what its reducers let it do.

### `@side_effect` decorator + side-effect guard (`loop/sideeffects.py`)

- **Purpose:** Replay-safety. Any node that performs a non-idempotent external call wraps the call in a guard that records a deterministic key on first execution and short-circuits on resume.
- **Interface:** `@side_effect("llm_call")` annotates a function that performs the side effect. Inside, the function calls `guard.begin(key)` / `guard.complete(key, result)`. On entry, `guard.begin` checks the audit chain for a `sideeffect.completed` matching the key; if found, returns the recorded result and skips the call. If a `sideeffect.started` exists with no `completed`, the guard marks the node `recovery_required=true` and raises an `interrupt()` (the human decides: replay the call, or abort).
- **Internal design (security reasoning):** The deterministic key is `blake3(side_effect_name || canonical(state.relevant_subset))` where `relevant_subset` is the state fields the side effect actually consumes (declared at decoration time). The key derivation is itself property-tested for stability across Pydantic round-trips and across machine architectures.
  Three classes of side effect in Phase 6: `llm_call` (Phase 4 `FallbackTier.run`), `spawn_sandbox` (Phase 5 `GateRunner.run`), and `write_branch` (deterministic git ops, but file writes are non-idempotent if a concurrent operator edits the tree). Each has its own resumption strategy: LLM responses are reproducible from the prior cassette/cache if available, sandbox runs are looked up by `sandbox_run_id` in the Phase 5 ledger and not re-spawned (the verdict from the chain is replayed), branch writes are skipped if the branch already exists with the same head SHA.
- **Tradeoffs accepted:** The guard adds two audit-chain appends per side effect. For an LLM call (~seconds), the overhead is negligible. The guard introduces a "recovery_required" state class — the human has to decide what to do for partial side effects; Phase 6 makes this explicit rather than picking a wrong default.

### `InterruptEnvelope` + `OperatorKey` (HITL primitives)

- **Purpose:** Make `interrupt()` and resume cryptographically authenticated. No `--auto-approve`. No in-process resume of an unsigned approval. Tests use real signatures over a fixture key.
- **Interface:** `InterruptEnvelope` is a Pydantic frozen model with `workflow_id, node_name, chain_head_at_pause, state_digest, reason: Literal["retries_exhausted","unsafe_signal","unrecoverable"], requested_at, nonce: bytes`. `OperatorKey` is an Ed25519 keypair generated at `codegenie operator init`; the private half lives at `~/.config/codegenie/operator.key` (0600); the public half is registered with the orchestrator on first use and committed to `~/.config/codegenie/operators.json`.
- **Internal design (security reasoning):** Three signatures cover the resume path:
  1. **Gate-control signature** over the `InterruptEnvelope` at pause time (using the per-orchestrator HMAC key from Phase 5). This is the orchestrator's claim that "this interrupt was raised at this state."
  2. **Operator signature** over the approval payload (`envelope_id, decision, notes_blake3, approved_at`) at resume time. This is the human's authorization.
  3. **Resume-side verification**: the orchestrator re-derives the gate-control HMAC, verifies the envelope's own signature, fetches the approval, verifies the operator signature against the registered public key, asserts `approval.workflow_id == envelope.workflow_id`, asserts `approval.envelope_id == envelope.id` (no cross-interrupt approval reuse), asserts the chain has no prior `interrupt.approved` for the same envelope ID (no replay).
  Tests inject mocked approvals by generating a fixture Ed25519 keypair in a tempdir, registering its fingerprint in the test run's `expected_approvers.json`, and signing with the fixture private key. The verification path is identical to production; the test cannot bypass it. A static CI test asserts no codepath constructs a `ResumeApproval` without going through `OperatorKey.sign(...)`.
- **Tradeoffs accepted:** Resume is a two-step operator workflow: `codegenie hitl show <id>` to read context, then `codegenie hitl approve <id> ...` to sign. No "fast-path" auto-resume. The operator must have set up `operator.key` before they can resume any workflow; an integration test asserts a clean clone of the repo cannot resume a workflow without running `codegenie operator init` first.

### `CheckpointerHealthProbe` (Phase 5-style honest-confidence input)

- **Purpose:** Detect silent unavailability or corruption of the checkpointer surface. ADR-0007 honest-confidence input. Phase 5 lifts this pattern; Phase 6 reuses it.
- **Interface:** Standard `Probe`. `name="checkpointer_health"`. Checks: SQLite file mode is `0600` (fails otherwise — refuses to use a world-readable DB); the file's schema matches the current LangGraph schema; the file's last `checkpoint.write` digest matches the chain's last `checkpoint.write` event; operator.key exists with `0600` (if a paused workflow exists awaiting resume — otherwise this is a warning).
- **Internal design (security reasoning):** Fail-loud rather than fail-quiet. A misconfigured checkpointer file is a security-relevant condition (e.g., world-readable means another local user can read serialized state); the probe surfaces it as an error in `RepoContext.health.checkpointer`, the orchestrator refuses to start a workflow if the probe is in an error state without `--unsafe-checkpointer-mode`, and that flag does not exist in Phase 6.

---

## State ledger schema (security view)

Field-level access control. Every field carries `read_acl` and `write_acl` annotations. The table below is the canonical reference; CI generates it from the live model and compares against the committed file (drift fails the build).

| Field | Type | Read ACL (nodes) | Write ACL (nodes/reducers) | Redacted in audit-chain logs? | Notes |
|---|---|---|---|---|---|
| `schema_version` | `str` (blake3 hex) | all | (set once at workflow start, immutable thereafter) | no | tamper-evidence for schema drift |
| `workflow_id` | `str` | all | (set once) | no | content-addressed from input bundle |
| `chain_head_at_entry` | `bytes` | all | (set once) | hex-encoded, full | anchor for chain replay |
| `repo_path` | `Path` | all | (set once) | yes (basename only in logs) | reduces leakage of absolute paths |
| `cve_id` | `str` | all | (set once) | no | already public information |
| `recipe_choice` | `RecipeChoice \| None` | plan_recipe, plan_rag, plan_llm, apply_transform | plan_recipe | no | typed model from Phase 3 |
| `rag_hits` | `tuple[RagHit, ...] \| None` | plan_rag, plan_llm | plan_rag | no | digest-only, no inlined embeddings |
| `llm_plan` | `LlmPlan \| None` | plan_llm, apply_transform | plan_llm (via @side_effect) | yes (prompt and response logged as digests + paths, never inlined) | Phase 4 LLM output |
| `attempts` | `tuple[AttemptSummary, ...]` | record_verdict, plan_llm, await_human_review | record_verdict (via add_attempt) | summaries logged in full; raw logs referenced by path | each summary capped 4 KB (Phase 5 invariant) |
| `verdict` | `Literal["pass","fail","unrecoverable"] \| None` | record_verdict, route_after_validate, commit_branch, await_human_review, finalize_* | record_verdict | no | the field an attacker most wants to forge |
| `pending_interrupt` | `InterruptEnvelope \| None` | await_human_review, resume verifier | raise_interrupt reducer | envelope logged in full; nonce included | signed by gate-control |
| `resume_marker` | `ResumeMarker \| None` | resume verifier, route_after_resume | resume reducer (only on verified approval) | full | includes approver fingerprint, decision, signed digest |
| `sideeffect_log` | `tuple[SideEffectRecord, ...]` | side-effect guard, recovery node | @side_effect decorator only | full | replay-safety substrate |

**Invariant.** Audit-chain log lines never contain raw LLM bytes, raw test stdout, raw sandbox logs, or raw operator notes. They reference these by `path + blake3`. The chain is small, fast, and grep-friendly; the bulk artifacts are the workflow's run-dir.

**Invariant.** No `read_acl` is `["*"]` for `verdict`, `pending_interrupt`, `resume_marker`, or `sideeffect_log`. Each is read by a small, named set of nodes. A node that does not declare a need to read these cannot.

---

## Conditional edges (Trust-Aware gates)

The edge functions are how the state machine decides what runs next. Phase 5 produced the *verdict*; Phase 6 turns the verdict into a routing decision.

The edges are listed in `loop/edges.py` with `Literal[...]` return types so a typo in a label is a type error, not a routing bug.

| Edge function | From node | Reads state fields | Returns | Notes |
|---|---|---|---|---|
| `route_after_plan_recipe` | plan_recipe | `recipe_choice` | `Literal["apply","rag_fallback"]` | recipe miss → RAG |
| `route_after_plan_rag` | plan_rag | `recipe_choice, rag_hits` | `Literal["apply","llm_fallback"]` | RAG miss → LLM |
| `route_after_plan_llm` | plan_llm | `llm_plan` | `Literal["apply","escalate"]` | LLM-output-invalid → escalate |
| `route_after_apply` | apply_transform | `attempts (latest)` | `Literal["validate","escalate"]` | apply failure → escalate |
| `route_after_validate` | validate_in_sandbox | `verdict, attempts` | `Literal["pass","retry","escalate","unrecoverable"]` | the load-bearing gate edge |
| `route_after_human_review` | await_human_review | `resume_marker` | `Literal["advance","abort"]` | reads only the verified approval |
| `route_after_commit` | commit_branch | (no state, terminal) | `Literal["done"]` | sink |

**`route_after_validate` — the canonical Trust-Aware gate edge.** The behavior on the second consecutive failure ([ADR-0014](../../production/adrs/0014-three-retry-default-per-gate.md)'s three-retry default) is rendered as topology:

```python
@pure_edge
def route_after_validate(s: LoopState) -> Literal["pass","retry","escalate","unrecoverable"]:
    if s.verdict == "pass":
        return "pass"
    if s.verdict == "unrecoverable":
        return "unrecoverable"
    # verdict == "fail"
    attempts = len(s.attempts)
    if attempts >= 3:
        return "escalate"
    # detect identical-signature flake (carried from Phase 5)
    if attempts >= 2 and _same_signature(s.attempts[-1], s.attempts[-2]):
        return "unrecoverable"
    return "retry"
```

How a gate decision is **made**: the `validate_in_sandbox` node calls Phase 5's `GateRunner.run(...)`, gets a `GateOutcome`, builds an `AttemptSummary`, and returns a `ReducerCall("record_verdict", verdict, summary)`. The reducer is the only writer of `verdict` and `attempts`; the routing function reads them and chooses an edge.

How a gate decision is **recorded**: `record_verdict` reducer emits two audit-chain events — `node.exited{name=validate_in_sandbox,outcome=<verdict>}` and a state-snapshot digest. The routing function emits `edge.taken{from=validate_in_sandbox,to=<edge_label>,state_digest=<digest>}` *before* the next node runs; this is the witness that the chosen edge was a function of the recorded state, not of post-hoc mutation.

How a gate decision is **audited**: replay. Given `audit/<run-id>.jsonl`, an investigator finds every `record_verdict` event and the following `edge.taken` event; rebuilds the `LoopState` at that point from the chain's checkpoints; calls `route_after_validate(rebuilt_state)`; asserts the function returns the same edge label. The property-test suite proves this property over 10k synthetic states at CI time so the production replay path can rely on it.

**Second-consecutive failure** ([ADR-0014](../../production/adrs/0014-three-retry-default-per-gate.md)): the third attempt's failure increments `len(attempts)` to 3 (we counted the first attempt as 1); `route_after_validate` returns `"escalate"`; the await_human_review node runs and raises `interrupt()` via `raise_interrupt(state, reason="retries_exhausted", signals=...)`. The interrupt envelope is signed; the chain records `interrupt.raised`; the workflow pauses. There is **no** fourth attempt. There is **no** override flag in Phase 6 (Phase 5's `--max-attempts-override` survives — Phase 6 reads it as a config knob at workflow start, but the value is locked into `LoopState` at entry and cannot be changed mid-run; the audit chain records `gate.attempts_override` at start).

---

## Checkpointer security

The SQLite checkpointer at `.codegenie/checkpointer/<workflow-id>.db` is treated as a security-relevant artifact, not as routine state.

**File-mode.** `0600`, owner-only. Set at `open()` time via an explicit `os.chmod` after creation; verified on every reopen by `CheckpointerHealthProbe`. World-readable or group-readable DBs are refused — the orchestrator raises `CheckpointerInsecure` and refuses to run. Rationale: serialized state may transiently contain references to internal repo paths and may contain a `notes` field from an operator approval; another local user reading the file is an unintended disclosure.

**Encryption-at-rest stance.** Phase 6 does **not** add encryption-at-rest. The DB is plaintext JSON on disk under owner-only permissions. Rationale: this is a local POC; encryption-at-rest is Phase 16's multi-tenancy work, and adding it now would couple Phase 6 to a key-management story we do not yet have. The mitigation here is *integrity* (the chain), not *confidentiality*. The risk surface for confidentiality at this stage is: an attacker who already has shell on the orchestrator host. That attacker has Anthropic-key access; the DB is not the marginal leak.

**Schema versioning.** Every checkpoint blob is tagged with `schema_version = blake3(canonical_sorted_json(LoopState.model_json_schema()))`. On resume, the orchestrator computes the current schema version; if it does not match the persisted version, the orchestrator raises `SchemaDrift` and refuses to resume. The operator runs `codegenie migrate-checkpoint --from <old> --to <new>` which produces a diff (old fields removed, new fields added, type changes) and requires a human to confirm a deterministic mapping. There is no auto-migration. **The schema version is part of every audit-chain `checkpoint.write` event**, so a future fork of `LoopState` in source produces a different version that is detectable independently of the DB.

**Retention.** Successful workflows: the DB is kept for 30 days, then garbage-collected by `codegenie sandbox gc` (extended in Phase 6 to also handle `<workflow-id>.db` files). Failed and escalated workflows: the DB is kept until the operator explicitly closes the case (`codegenie hitl close <workflow-id>` — Phase 6 adds this CLI as part of `cli_hitl.py`). The audit chain is kept indefinitely (small; high investigative value).

**Concurrency.** Per-workflow SQLite files. One writer per file. LangGraph's `AsyncSqliteSaver` opens with `journal_mode=WAL`; the wrapper's SAVEPOINT semantics work cleanly under WAL. Cross-workflow concurrency is across files, so no cross-file locking issues.

**Backup and replication.** Out of scope for Phase 6. The DB lives on a single host. Phase 9's Postgres migration is the right place to land replication.

**Serializer.** JSON only. LangGraph supports MessagePack via `MsgPackSerializer`; that is rejected. Rationale: MessagePack ext types are an attack surface for naive consumers, and the `langgraph-cli` chain of trust must include the deserializer. JSON is human-auditable from `sqlite3` CLI, which is itself a security property (incident-response).

---

## HITL interrupt / resume protocol

This is the most security-sensitive flow Phase 6 introduces.

### Pause (interrupt) — orchestrator side

1. `route_after_validate` returns `"escalate"` (retries exhausted).
2. `await_human_review` node runs `raise_interrupt(state, reason="retries_exhausted", signals=state.attempts[-1].failing_signals)`.
3. `raise_interrupt`:
   - Constructs `InterruptEnvelope(workflow_id, node_name="await_human_review", chain_head_at_pause=<current head>, state_digest=blake3(canonical(state)), reason, requested_at, nonce=os.urandom(16), envelope_id=blake3(...))`.
   - Signs the envelope with the gate-control HMAC key: `gate_sig = HMAC-SHA256(gate_key, envelope.canonical_bytes())`.
   - Appends `audit_chain.append({"kind":"interrupt.raised", "envelope":..., "gate_sig":...})`.
   - Writes the envelope (with `gate_sig`) to `<run>/interrupts/<envelope_id>.pending.json`, `0644` (this is the file the operator reads).
   - Calls `langgraph.interrupt(envelope_id)` which serializes the envelope into the next checkpoint as a `__interrupt__` annotation, then halts the graph.
4. The orchestrator process exits cleanly with exit code `12` (interrupt-pending). Phase 6 adds this exit code to the conventions doc.

### Resume — operator side

1. Operator runs `codegenie hitl list` → sees the pending interrupt.
2. Operator runs `codegenie hitl show <envelope_id>`:
   - Reads the pending envelope, verifies `gate_sig` against the gate-control public material (the orchestrator publishes its HMAC public component to a per-host file at `~/.local/share/codegenie/gate-pubkey` — actually for HMAC we need a shared secret; for Phase 6 we use the same key the orchestrator holds, stored 0600. Phase 16 migrates to asymmetric signatures.).
   - Prints to the terminal: workflow_id, repo_path basename, cve_id, the failure summaries from the last three `AttemptSummary`s, the chain head at pause, and the envelope nonce.
   - The operator reads the context.
3. Operator runs `codegenie hitl approve <envelope_id> --decision=advance --notes="reviewed; upstream library author confirmed the fix; safe to retry"`:
   - The CLI re-reads the pending envelope.
   - Constructs `ResumeApproval(envelope_id, workflow_id, decision="advance", notes_blake3=blake3(notes), approved_at, approver_fingerprint=blake3(operator_pubkey))`.
   - Signs with `~/.config/codegenie/operator.key` (Ed25519) → `approval_sig`.
   - Writes `<run>/interrupts/<envelope_id>.approval.json`, `0600`.
   - Exits. The CLI does **not** itself resume the workflow.
4. Operator (or a separate cron) runs `codegenie remediate --resume <workflow-id>`:
   - The orchestrator loads the LangGraph state from the checkpointer.
   - Discovers the `__interrupt__` annotation in the current checkpoint.
   - Reads `<run>/interrupts/<envelope_id>.approval.json`.
   - `verify_resume(envelope_id)`:
     - Loads pending envelope. Verifies `gate_sig` (defense in depth — the envelope was signed at pause time).
     - Verifies `approval_sig` against `expected_approvers.json` (the public key registered by `codegenie operator init`).
     - Asserts `approval.workflow_id == envelope.workflow_id`. (No cross-workflow reuse.)
     - Asserts `approval.envelope_id == envelope.envelope_id`. (No cross-interrupt reuse.)
     - Asserts the audit chain has no prior `interrupt.approved` event with the same `envelope_id`. (No replay.)
     - Asserts `envelope.chain_head_at_pause == <chain head when the chain's interrupt.raised event was written>`. (No envelope substitution.)
     - Reads `approval.notes`, fence-wraps it (using Phase 4's `FenceWrapper`), truncates to 1 KB, pattern-checks for canary collisions.
   - Appends `audit_chain.append({"kind":"interrupt.approved", "envelope_id":..., "approval":..., "approver_fingerprint":...})`.
   - Constructs a `ResumeMarker` Pydantic model from the verified approval; passes it to the `resume` reducer, which writes `resume_marker` and clears `pending_interrupt`.
   - The graph resumes at the node *after* `await_human_review`. `route_after_human_review` reads `resume_marker.decision` and routes to `advance` or `abort`.

### Authentication summary

| Direction | Signer | Verifier | Mechanism |
|---|---|---|---|
| Orchestrator → operator (pause) | gate-control HMAC | operator's `codegenie hitl show` CLI | HMAC-SHA256 over canonical envelope bytes |
| Operator → orchestrator (resume) | operator Ed25519 private key | orchestrator's `verify_resume` | Ed25519 signature over canonical approval bytes |
| Orchestrator → audit chain | audit-chain signing key (Phase 2/3/4/5) | startup chain verification | BLAKE3-chained linked list |

### Replay protection

- `nonce: bytes` (16 random bytes) in every `InterruptEnvelope`. Two interrupts on the same workflow have different nonces, so an approval for envelope A cannot be replayed against envelope B.
- The audit chain rejects writing a second `interrupt.approved` for the same `envelope_id` (an integrity check before append).
- `envelope.chain_head_at_pause` is checked at resume against the chain's *actual* head when the `interrupt.raised` event was written; this prevents an envelope-substitution attack where an attacker swaps in a stale envelope.

### What a resumed payload is allowed to mutate

Exactly two fields. The `resume` reducer has `writes=frozenset({"resume_marker","pending_interrupt"})`. It writes `resume_marker` (the verified approval) and clears `pending_interrupt`. It does not touch `attempts`, `verdict`, `llm_plan`, `recipe_choice`. There is no field on `ResumeApproval` that maps to `LoopState.verdict` or any other state field. If a future phase needs the operator to supply state (e.g., "apply this hand-edited patch on resume"), that requires an ADR amendment and a new reducer with a new write-ACL.

### Mocked-human responses in tests cannot be a prod backdoor

The mock-human test fixtures generate a real Ed25519 keypair in a `tmp_path` directory; register the public key fingerprint in the test workflow's `expected_approvers.json`; sign with the private key; and invoke the production `verify_resume` path. The production verifier rejects any fingerprint not in `expected_approvers.json`; the test runs in isolation so the fixture key never appears in a real run's approver list. A static CI test (`test_no_test_keys_in_production_approvers.py`) walks `tools/` and `~/.config/codegenie/operators.json` candidates in the repo and asserts no test fixture's fingerprint ever appears.

---

## Failure modes & recovery

| Failure | Detected by | Recovery | Audit consequence |
|---|---|---|---|
| Checkpointer DB tampered (offline edit of `<workflow-id>.db`) | `AuditedSqliteSaver.get` digest verification | `CheckpointTampered` raised; orchestrator refuses to resume; operator must `codegenie audit verify` and triage | `checkpoint.tamper.detected` chain event; workflow flagged unrecoverable |
| Audit chain tampered (offline edit of `audit/<run-id>.jsonl`) | startup chain replay; `BLAKE3 mismatch` | refuse to start any workflow until the operator inspects | `chain.tamper.detected` (written to a separate `meta.jsonl` if the main chain can't be trusted) |
| Schema drift (LoopState definition changed since last checkpoint) | `schema_version` mismatch on resume | `SchemaDrift` raised; operator runs `codegenie migrate-checkpoint` with a diff review | `schema_drift.detected` event with old / new versions |
| `interrupt()` raised without signed envelope | a buggy or malicious code path calls raw `langgraph.interrupt(...)` outside `raise_interrupt(...)` | resume rejects an unsigned `__interrupt__` annotation; orchestrator raises `UnsignedInterrupt` | `unsigned_interrupt.detected` event; workflow refuses to resume |
| Resume approval signature invalid | `verify_resume` Ed25519 verify | refuse to resume; operator regenerates approval (or rotates key if compromised) | `approval.sig.invalid` event with offending fingerprint |
| Replay attack (operator submits approval for a different envelope) | `approval.envelope_id != envelope.envelope_id` check | reject | `approval.replay.detected` |
| Reducer writes a field outside its ACL | runtime `enforce_field_acl` diff check after `apply_reducer` | raise `ReducerEscapedAcl`; mark workflow `unrecoverable`; `interrupt()` for human review | `reducer.acl_violation` event with reducer name and offending field |
| Edge function returns a non-Literal value (typo) | type check at decoration time; runtime `assert label in EDGE_LABELS` | raise; treated as `unrecoverable` | `edge.label_invalid` event |
| Side-effect started but not completed (process killed mid-LLM-call) | resume finds `sideeffect.started` without `sideeffect.completed` | mark `recovery_required=true`; raise `interrupt()` so the human decides replay-or-abort | `sideeffect.partial.detected` event |
| Pydantic validation fails on a deserialized checkpoint blob | `AuditedSqliteSaver.get` triggers `LoopState.model_validate` | raise `CheckpointSchemaMismatch`; treat as unrecoverable | `checkpoint.schema_mismatch` event |
| Checkpointer DB file world-readable | `CheckpointerHealthProbe` startup check (file mode != `0600`) | refuse to start; print remediation hint (`chmod 600 <path>`) | `checkpointer.insecure_mode.detected` event |
| Operator key not present and operator tries to resume | `codegenie hitl approve` checks `~/.config/codegenie/operator.key` | CLI exits 2 with hint to run `codegenie operator init` | n/a (CLI failure, not chain) |
| Operator key compromised (operator notifies) | manual operator action: `codegenie operator rotate` | new keypair generated; old fingerprint removed from `expected_approvers.json`; pending approvals signed under the old key are rejected | `operator.key.rotated` event; affected pending workflows require re-approval |
| Mid-run kill (OS / power / `kill -9`) | next start sees a `node.entered` without a matching `node.exited` | resume from the most recent `checkpoint.write` (which is *before* the node that didn't complete); the side-effect guard handles in-flight side effects | normal `checkpoint.write` → `node.entered` → (no exit) → on resume, the node re-runs |
| `langgraph-cli` accidentally invoked against a live DB | the wrapper enforces — `langgraph-cli` is documented as dev-only; an integration test on macOS/Linux dev images runs the CLI against a snapshot path and asserts no writes to the live path | refuse if invoked against a path under `.codegenie/checkpointer/`; require `--from-snapshot <path>` | n/a (CLI guardrail, not chain) |
| `interrupt()` envelope written but operator never resumes | passive (workflow stays paused) | operator action; `codegenie hitl list --older-than 30d` surfaces stale interrupts | n/a until operator acts |

Every row writes (or refuses to write) one BLAKE3-chained event. Phase 13's cost ledger and Phase 16's compliance posture both read these event names.

---

## Test plan

Adversarial-first. Then property tests. Then unit and integration.

### Adversarial (the load-bearing tests)

- `tests/adversarial/test_tampered_checkpoint.py` — open the DB out of band, edit `LoopState.verdict` from `"fail"` to `"pass"`, attempt resume. Assert: `CheckpointTampered` raised; `checkpoint.tamper.detected` chain event written; resume refused.
- `tests/adversarial/test_tampered_audit_chain.py` — delete a `checkpoint.write` entry from the chain. Attempt to start any workflow. Assert: chain-replay verification fails at startup; orchestrator refuses to run.
- `tests/adversarial/test_forged_resume_approval.py` — generate an Ed25519 keypair *not* in `expected_approvers.json`. Sign a valid-looking approval with it. Attempt resume. Assert: `verify_resume` rejects; `approval.sig.invalid` event written.
- `tests/adversarial/test_replayed_resume_approval.py` — successfully approve and resume workflow W1. Re-submit the same approval envelope for W1. Assert: chain rejects (already has `interrupt.approved` for that envelope_id).
- `tests/adversarial/test_cross_workflow_approval_reuse.py` — approve workflow W1; copy the approval JSON to W2's interrupts dir with W2's envelope_id pasted in. Attempt resume on W2. Assert: `approval.workflow_id != envelope.workflow_id` check fires; rejected.
- `tests/adversarial/test_unsigned_interrupt.py` — a malicious node calls `langgraph.interrupt("foo")` directly without `raise_interrupt`. Persisted checkpoint contains an unsigned `__interrupt__` annotation. Resume rejects.
- `tests/adversarial/test_reducer_escapes_acl.py` — a fixture reducer declares `writes=frozenset({"attempts"})` but mutates `verdict`. Runtime `enforce_field_acl` raises `ReducerEscapedAcl`.
- `tests/adversarial/test_edge_function_nondeterminism.py` — a fixture edge function reads `time.time()`. Fence-CI fails; the test asserts the static guard catches it.
- `tests/adversarial/test_secret_leak_in_state.py` — attempt to construct `LoopState` with a field whose value contains a known canary string. The custom JSON encoder must redact it before serialization. The serialized bytes are scanned for the canary; absence is asserted.
- `tests/adversarial/test_schema_drift_refused.py` — checkpoint under schema version A; mutate `LoopState` to produce schema version B; attempt resume. Assert: `SchemaDrift` raised; no auto-migration; chain records `schema_drift.detected`.
- `tests/adversarial/test_world_readable_checkpoint_refused.py` — `chmod 644 <db>`; attempt to use. Assert: `CheckpointerInsecure` raised; orchestrator refuses to run.
- `tests/adversarial/test_oversize_checkpoint_refused.py` — construct a `LoopState` whose serialized JSON is > 64 KB; attempt write. Assert: `CheckpointTooLarge` raised; the SAVEPOINT rolls back.
- `tests/adversarial/test_sideeffect_replay_safety.py` — kill the process between `sideeffect.started` and `sideeffect.completed` for an LLM call. Resume. Assert: `recovery_required=true` marker set; `interrupt()` raised; mocked operator decision drives replay-or-abort.

### Property tests (Hypothesis)

- `tests/property/test_route_after_validate_deterministic.py` — for 10k random `LoopState` instances drawn from a Pydantic-derived strategy, `route_after_validate(s)` produces the same output every call.
- `tests/property/test_reducer_diff_matches_acl.py` — for every registered reducer and 1k random valid arg combinations, the diff between `before` and `after` `LoopState` is a subset of `writes`.
- `tests/property/test_schema_version_stable.py` — for 1k Pydantic JSON-schema constructions, `schema_version` is byte-stable.
- `tests/property/test_sideeffect_key_stable.py` — for 1k state-subset projections, the deterministic side-effect key is byte-stable across Python versions and OSes.
- `tests/property/test_loopstate_secret_redaction.py` — Hypothesis-generated `SecretStr` values never appear in the on-disk serialized bytes.

### Conditional-edge coverage

A dedicated CI gate asserts every edge function has 100% line / 95% branch coverage. The exit-criterion fixture set includes one workflow per edge label (every label is reached at least once across the test suite), matching the roadmap's "state-transition tests assert every conditional edge is exercised at least once" requirement.

### Replay tests (the exit-criterion case)

- `tests/integration/test_mid_run_kill_resume.py` — start a workflow with a fixture that takes ~5s in `validate_in_sandbox`. After the node enters, send `SIGKILL` to the orchestrator. Restart `codegenie remediate --resume <workflow-id>`. Assert: the workflow resumes from the most recent `checkpoint.write`; final state byte-identical to a clean run; audit chain shows `node.entered` × 2 (the first incomplete, the second complete) and a `sideeffect.partial.detected` if mid-LLM, or a clean resume if pre-side-effect.
- `tests/integration/test_replay_byte_identical.py` — run a workflow to completion; copy the audit chain and DB; restart the run from the same input bundle (same `workflow_id`); assert the produced state at every checkpoint matches.

### HITL interrupt tests

- `tests/integration/test_hitl_interrupt_fires_after_three_failures.py` — fixture: every `validate_in_sandbox` call fails (mocked Phase 5). Run the workflow. Assert: three `record_verdict{verdict=fail}` events, then `interrupt.raised{reason=retries_exhausted}` event, then orchestrator exits 12.
- `tests/integration/test_hitl_approve_resumes.py` — given the paused state from the prior test, generate a fixture operator key, register its fingerprint, sign an approval with `decision=advance`, run `codegenie remediate --resume`. Assert: `interrupt.approved` event; `resume_marker` set; the next node runs; the workflow proceeds (the fix succeeds when mocked Phase 5 flips to pass after the resume).
- `tests/integration/test_hitl_abort_terminates.py` — same setup; approval has `decision=abort`. Assert: `finalize_escalate` runs; workflow ends with exit 11; chain shows `interrupt.approved{decision=abort}` and `workflow.completed{outcome=aborted}`.
- `tests/integration/test_hitl_show_prints_full_context.py` — assert the operator-facing print contains workflow_id, repo basename, cve_id, last three failure summaries, and the chain head — and *not* the raw LLM bytes or secrets.

### Schema enforcement (CI gates)

- `tests/schema/test_no_untyped_fields_in_loopstate.py` — walks every field reachable from `LoopState`; rejects `Any`, `dict[str, Any]`, `object`, untyped `Mapping`.
- `tests/schema/test_no_secret_named_fields_in_loopstate.py` — rejects field names matching `key|token|secret|password|cred|api`.
- `tests/schema/test_no_self_confidence_in_loopstate.py` — rejects field names matching `confidence|llm_says|self_reported|model_self_reported|model_says`. ADR-0008 lock lifted to the state layer.
- `tests/schema/test_no_msgpack_serializer.py` — asserts `AuditedSqliteSaver` registers only `JsonSerializer`.
- `tests/schema/test_fence_loop_edges_no_random_time_os.py` — fence-CI gate: no module under `loop/edges/` imports `random`, `time`, `os.environ`, `datetime.datetime.now/utcnow`.
- `tests/schema/test_field_acl_declared.py` — every `LoopState` field has both `read_acl` and `write_acl` annotations.

---

## Risks (top 5)

1. **The HITL operator key is the single biggest attack target Phase 6 introduces.** If `~/.config/codegenie/operator.key` is stolen, an attacker can resume any paused workflow with `decision=advance`, and `route_after_human_review` advances the workflow. **Mitigations:** `0600` and clearly documented; `codegenie operator init` warns on permissive umask; `codegenie operator rotate` exists; an integration test on a fresh repo asserts the orchestrator refuses to resume without `operator init` first. **Residual risk:** real. Phase 16's hardware-token integration (YubiKey, secure enclave) is the right long-term answer. Phase 6 documents this in `operator_key.py`'s module docstring and in `risks.md`.

2. **The checkpointer is plaintext on disk.** An attacker with shell on the host reads the DB and sees serialized `LoopState` including repo paths and failure summaries. **Mitigations:** owner-only file mode; in-process redaction of `SecretStr` values; CI test asserting no secret-named fields. **Residual risk:** confidentiality of metadata (which CVE we're working on, which repo) on a shared host. Phase 16's encryption-at-rest closes this. For Phase 6's scope (local POC, single operator), the trust boundary is "you trust the local host." Documented.

3. **Schema drift between checkpoint and code is a real operational hazard.** A developer who changes `LoopState` and resumes an in-flight workflow without migration is invited to corrupt state. **Mitigations:** the `schema_version` field forces an explicit migration step; `codegenie migrate-checkpoint` requires human review; CI asserts a PR that changes `LoopState` also changes a migration registry. **Residual risk:** in active development, paused workflows older than a few days may never be migratable. Accept; document.

4. **Replay safety hinges on the side-effect guard catching every external call.** A future PR that adds a new external call (a new MCP server, a metric emitter that writes off-host) without decorating it with `@side_effect` is a silent replay-double-call bug. **Mitigations:** a fence-CI scan that flags imports of `httpx`, `requests`, `socket.create_connection`, `subprocess.*`, `anthropic.Anthropic.messages.create`, and the Phase 5 sandbox client outside of `@side_effect`-decorated callsites — anything that crosses an external boundary inside `loop/` must be wrapped. **Residual risk:** a clever future change that proxies through an indirection the scanner doesn't see. Code review is the remaining defense.

5. **The audit chain is the single source of truth and lives on one disk.** A disk failure or filesystem corruption that loses the chain mid-workflow is unrecoverable. **Mitigations:** `fsync` after every append; `O_APPEND` semantics; the audit chain is the smallest of the on-disk artifacts (KB-scale per workflow) so a cheap rsync-to-secondary in Phase 16 closes this. **Residual risk:** real in Phase 6; mitigated by the small chain size and the operator's `codegenie audit verify` habit. Phase 6 does not replicate.

---

## Acknowledged blind spots

- **Encryption-at-rest** — out of scope per the lens summary's roadmap-fidelity note. Phase 16 owns this.
- **Multi-host concurrent workflows** — out of scope. Phase 6 ships per-host; Phase 9's Temporal Postgres backend lifts.
- **Operator-key HSM / hardware-token integration** — Phase 16. Phase 6 ships file-on-disk.
- **`langgraph-cli` production hardening** — Phase 6 treats the CLI as dev-only and forbids it talking to a live DB. Phase 16's multi-tenant deployment introduces the read-only-replica model.
- **Cost of resume re-running side effects when the guard can't replay** — when the chain shows a `sideeffect.started` for an LLM call but the response cache has rotated out, we have no record of the result; the guard escalates to human, who decides "replay the call." The replay re-spends LLM tokens. Phase 4's `LlmInvocationGuard` records the spend honestly; the cost ledger surfaces it.
- **Sub-resource integrity for the Pydantic models in source** — if an attacker modifies `LoopState` definition in source, the schema_version changes and the workflow refuses to resume. But the attacker has *write access to source* — every other phase has the same issue. Phase 16's signed releases close this; Phase 6 documents.
- **Recovery from a paused workflow whose repo has moved on disk** — `LoopState.repo_path` is captured at workflow start; if the operator moves the directory, resume fails with `RepoPathMissing`. Phase 6 does not auto-discover. Document.
- **Concurrent operator approvals** — two operators racing to approve the same interrupt. The first signed approval written wins; the second fails the "no prior `interrupt.approved` for this envelope" check at resume time. Acceptable; documented.

---

## Open questions for the synthesizer

1. **Operator-key shape: HMAC vs Ed25519.** I picked Ed25519 for operator approvals and HMAC for the orchestrator → gate-control channel (the latter inherited from Phase 5). Performance and best-practices may prefer a single primitive across the board (HMAC everywhere; or Ed25519 everywhere). I argue Ed25519 is the right pick for any signature crossing process boundaries with different trust levels; HMAC is fine for the in-trust-boundary AF_UNIX channel. The synth should pick one principle and apply it consistently.

2. **Checkpoint location: per-workflow file vs single shared DB.** I picked per-workflow SQLite files for concurrency reasons; LangGraph's reference impls show a single shared DB. The per-workflow shape is more secure (file-level isolation per workflow), easier to clean up, and matches the "the DB and the chain are coupled per workflow" model. It does mean `langgraph-cli` has to be pointed at a specific file, not a directory. Synth should weigh ops ergonomics.

3. **Schema-drift migration path.** I refused auto-migration in Phase 6 and require human review via `codegenie migrate-checkpoint`. Best-practices may want auto-migration for additive changes (new optional field). I argue: no — the failure mode of an unintended migration (silent state corruption) is worse than the friction of a deliberate one. The synth should weigh dev-loop friction.

4. **HITL CLI shape.** I split `hitl show` and `hitl approve` into two commands so the operator reads context before signing. Performance may want a single `approve` command that prints context and prompts for confirmation. The two-command shape is more amenable to scripting (CI can run `show` in a pipeline before a human signs). Synth should pick.

5. **`schema_version` as part of `LoopState` vs as part of the audit-chain event.** I put it in `LoopState` (every checkpoint blob carries it) *and* in every `checkpoint.write` event. Redundancy is intentional; the duplicate detection is across both surfaces. Best-practices may prefer storing it only on the chain. I argue both — the cost is trivial and the verification surface doubles.

6. **Side-effect replay default: replay vs escalate.** When a `sideeffect.started` has no `sideeffect.completed`, I escalate to human. Performance may want "replay if the cached response exists, else escalate." I argue: starting that line is a slippery slope; making the human decide is the safe Phase 6 default. The synth should pick.

7. **Roadmap fidelity around encryption.** I deliberately do *not* add encryption-at-rest in Phase 6. If a roadmap-fidelity-first synth wants to add it (the roadmap doesn't say to, but doesn't say not to), it should land it behind an opt-in flag with a Phase 16 ADR-amendment-deferred default — and be ready for the key-management consequences in Phase 6's scope (which we don't have a story for).

8. **Whether `langgraph-cli` is shipped at all.** The roadmap names it. I treat it as a dev tool that never speaks to prod. An aggressive security stance would forbid it from the install entirely and provide a separate `codegenie checkpoint inspect` CLI. The synth should weigh "use the framework's tooling" against "minimize the deserialization surface."
