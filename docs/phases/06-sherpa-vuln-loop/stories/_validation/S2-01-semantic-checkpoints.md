# Validation report — S2-01 (Semantic checkpoints)

**Date:** 2026-05-25
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief; the story is small enough and the lenses converge sharply enough that spawning four parallel critic agents would have burned tokens without changing the verdict, mirroring the precedent set by the S1-01 and S1-02 validations in this same phase).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S2-01-semantic-checkpoints.md`](../S2-01-semantic-checkpoints.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* is correct: it owns the replay-safe checkpoint append/read substrate, and High-level-impl.md §"Step 2" explicitly opens with "Implement semantic checkpoint append/read" as its first bullet. But every AC was a vague qualitative statement and the Refactor step contradicted the Phase-3 precedent. Specifically:

1. **AC-1 was un-verifiable.** "Checkpoints append at plan, patch, gate, interrupt, and terminal boundaries." — append *what*, *where*, with what *port shape*? An executor could ship a single 50-line function with five `if` branches and pass. No Protocol, no adapter pattern, no `CheckpointStore` port.
2. **AC-2 was hollow.** "Golden ordering test is deterministic." — the original AC neither named the scenario, the golden location, the failure-mode directive, nor pinned which scenarios from phase-arch-design.md §"Scenarios" the golden covers. Three executor attempts would write three different shapes.
3. **AC-3 was vague.** "Payload size remains bounded." — bounded to *what*? at the *model* layer (would break the forensic EventLog) or the *store* layer (correct)? With what exception type? With what error_id? Without a numeric cap and a typed exception, the executor cannot binary-pass-fail.
4. **The `CheckpointStore` port was entirely missing.** Phase-3 S6-01 already shipped `EventStreamSink` (port) + `ZstdAppendingFileSink` (production adapter) + `InMemorySink` (test adapter) as the canonical "port + two adapters" pattern. This story is the *direct* application of that pattern to the SQLite checkpoint substrate — without naming the Protocol, an executor would likely ship a single concrete class with no test substrate, breaking the parity contract Phase-9's Postgres adapter swap relies on.
5. **SQLite WAL + per-workflow file + locking discipline was unstated.** phase-arch-design.md §"Deployment view" pins `.codegenie/remediation/<run-id>/` as the substrate location, but the story didn't name SQLite, didn't pin `journal_mode=WAL`, didn't pin `synchronous=FULL`, and didn't name the cross-process `fcntl.flock` discipline. An executor with budget pressure ships a single shared SQLite file with `journal_mode=DELETE` and concurrent workflows silently serialize.
6. **Closed `_SEMANTIC_BOUNDARY_KINDS` catalog was unencoded.** The five boundary kinds named by final-design.md §"Decisions of record" item 3 (plan acceptance / patch application / gate result / escalation / terminal completion) MUST be a closed `frozenset[LedgerStateKind]` that the boundary-only append policy reads. Without the constant, the executor inlines the five string literals across the codebase and a future drift adds a sixth boundary in one place but not the other.
7. **Cross-story consistency with S1-02's `_TERMINAL_LEDGER_KINDS` was unencoded.** Terminal kinds MUST be boundary kinds (a workflow that ends must have a final durable checkpoint). The original story had no AC that enforced this cross-story membership; a future drift could remove `failed_unrecoverable` from boundaries and silently lose terminal checkpoints.
8. **Chain-forward extension property was absent.** S1-02 shipped `_compute_chain_head` (pure helper) with stability + sensitivity properties; the *store* is the imperative shell that consumes it. The chain-forward extension property (`store.tail_chain_head` after N appends == iterative `_compute_chain_head` over the same sequence) is the load-bearing replay-determinism floor — without it, a buggy store that swallows `prior_head` would pass every other test.
9. **Cross-workflow isolation property was absent.** A store that appends to `workflow_id_A` and pollutes `tail_chain_head(workflow_id_B)` would be catastrophic for the multi-workflow harness; the property test is the structural defense.
10. **Detection-substrate-only contract for `tail_chain_head` was unencoded.** The most insidious failure mode for the checkpoint substrate is an executor "helpfully" adding chain recomputation inside `tail_chain_head` — this collapses the detection/policy separation that ADR-0003's "verify the previous chain head before hydration" depends on (S2-02 is the SOLE policy site). Without the AC-11 explicit "tail_chain_head does NOT recompute" assertion, the executor cannot know this constraint exists.
11. **Sanitizer-import discipline was absent.** Phase-9 critique report flagged regex-set forking as a canonical failure mode; the SUT result sanitization path (`codegenie/output/sanitizer.py`) is the single canonical home. Without an AST fence over the store modules forbidding local `re.compile` and requiring the canonical sanitizer import, an executor under deadline pressure forks the regex set.
12. **Clock injection was unstated.** Without a `clock: Callable[[], datetime] | None` constructor parameter, the SQLite store's `written_at` column captures wall-clock `datetime.now()` directly, making the golden ordering test (the original AC-2) inherently flaky. Clock injection is the *substrate* that makes the golden test deterministic.
13. **`__all__` boundary discipline was unstated.** S1-01 + S1-02 established the `codegenie.workflows.__all__` allowlist sentinel as load-bearing (extension by addition, no silent edits). This story adds three new types (`CheckpointStore`, `SqliteCheckpointStore`, `InMemoryCheckpointStore`) but none of them belong in `__all__` (final-design.md §"Relationship to Phase 6.5" `may not depend on: checkpoint backend internals`). Without an explicit AC asserting the 14-name set is byte-equal-unchanged after this story, an executor would enthusiastically add `CheckpointStore` for "API convenience" and break Phase-6.5's contract boundary.
14. **Refactor step inverted the Phase-3 precedent.** "Share canonical serialization helpers" via what mechanism? a `BaseCheckpointStore`? a mixin? The Phase-3 precedent (`EventStreamSink` + two adapters share NOTHING via inheritance; only the Protocol) is the canonical anti-shared-base shape. Without the Anti-refactor block forbidding `BaseCheckpointStore`, the executor's Refactor pass would land a mixin and silently couple the SQLite + InMemory adapters together.
15. **Mutation-resistance pass was absent.** Every AC was checked: a mutant `append()` that ignores `prior_head` passes "checkpoints append at boundaries"; a mutant `read_all_for_workflow` that returns chain-head-sorted results passes "golden ordering test"; a mutant payload validator that caps at 1 KiB instead of 64 KiB silently rejects valid events. The new ACs encode the specific failure modes so mutants die.
16. **No AC for AC-15 contract snapshot extension.** S1-01 + S1-02 established the contract snapshot meta-test pattern; this story must extend it with the `CheckpointStore` Protocol shape + the `_SEMANTIC_BOUNDARY_KINDS` membership + the `_MAX_EVENT_BYTES` value + the SQLite schema. Without the AC, contract drift across S2-02 / S3-01 / S5-01 / Phase-9 S5-01 goes undetected until a downstream test breaks 800 commits later.
17. **No parity-meta-test (AC-17) closing the mutation gap on the parity test itself.** The parity contract test (AC-6) is itself susceptible to mutation; the meta-test (broken adapter → parity test fails) closes the exact gap S6-06 flagged.

All in-place fixable, none requires re-running `phase-story-writer`. The story's structure (one-paragraph goal, three-section TDD plan) survives — the three ACs grew to seventeen, the TDD plan was reordered with the anti-refactor block, and References / Files-to-touch / Out-of-scope / Notes-for-implementer were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship `src/codegenie/workflows/{checkpoints,sqlite_checkpoints,in_memory_checkpoints,errors}.py` with the `CheckpointStore` Protocol (port), the SQLite production adapter (WAL + per-workflow file + flock-protected append), the in-memory test adapter, the closed `_SEMANTIC_BOUNDARY_KINDS` frozenset, the `_MAX_EVENT_BYTES = 65_536` payload cap with typed `CheckpointPayloadTooLargeError`, the boundary-only append policy with `pydantic.ValidationError` rejection + directive, the chain-forward extension wiring (consumes S1-02's `_compute_chain_head` without modifying it), the cross-workflow isolation property, the detection-substrate-only `tail_chain_head` contract (no recomputation — S2-02 owns policy), the canonical sanitizer-import AST fence, the `__slots__` AST fence on both adapters, the clock-injection determinism, the golden ordering test for two scenarios, the parity contract test parametrized over both adapters, the parity-meta-test, and the contract-snapshot extension with two synthetic checkpoint-shaped deltas.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### What final-design.md §"Decisions of record" item 3 pins

> The ledger persists after plan acceptance, patch application, gate result, escalation, and terminal completion.

Five semantic boundary events. Mapped to `LedgerStateKind`: `plan_ready` (plan acceptance), `patch_applied` (patch application), `gate_failed_retryable` (gate result, retryable arm), `awaiting_human_review` (escalation), `completed` + `failed_unrecoverable` (terminal completion — two terminal kinds, one boundary category). Six boundary kinds total in the catalog. The one non-boundary kind is `needs_plan` (initial state — no value in persisting the snapshot of "nothing has happened yet").

### What ADR-0003 pins

> Persist checkpoints only at semantic boundaries and verify the previous chain head before hydration on resume.

Two halves:
- **First half (this story):** "persist only at semantic boundaries" — the boundary catalog + append policy + the BLAKE3-chained substrate.
- **Second half (S2-02):** "verify the previous chain head before hydration on resume" — the integrity policy.

The AC-11 detection-substrate-only contract is the load-bearing separation between the two halves.

### What phase-arch-design.md §"Deployment view" pins

> Phase 6 stays local: Python process + SQLite checkpoint file under `.codegenie/remediation/<run-id>/`.

The substrate is SQLite, the location is per-workflow under `.codegenie/remediation/<run-id>/`, the architecture "intentionally mirrors the later Temporal shape but does not pull Temporal into the local phase." This drives the per-workflow file choice (AC-5) over a single shared SQLite file.

### What S1-02 forward-depends on

S1-02 shipped `TransitionEvent` (the seven-field event the store appends), `_LEGAL_TRANSITIONS` (the closed edges the orchestrator chooses among), `_TERMINAL_LEDGER_KINDS` (`{"completed", "awaiting_human_review", "failed_unrecoverable"}`), `_compute_chain_head` (the pure helper in `_chain.py` with the AST no-side-effects fence), and `_FROZEN_FORBID` (the canonical config). This story consumes all five; it adds NO new newtypes (`WorkflowId`, `TransitionId`, `ChainHead`, `BlobDigest` all already exist).

### What S1-01 forward-depends on

S1-01's AC-12 `codegenie.workflows.__all__` allowlist sentinel must continue to pass *unchanged* after this story lands. The three new types (`CheckpointStore`, `SqliteCheckpointStore`, `InMemoryCheckpointStore`) are package-private; the Phase-6.5 bench harness consumes only the 14 S1-01 + S1-02 names. AC-2 of this story enforces the byte-equality of the unchanged `__all__`.

### What CLAUDE.md load-bearing commitments force

- **Match the existing convention.** The Phase-3 `EventStreamSink` + two adapters pattern is the canonical "port + two adapters" shape for chained event persistence. Drives AC-1 + AC-5 + AC-6.
- **Composition over inheritance.** Drives the anti-refactor block (no `BaseCheckpointStore`; shared serialization via free function `_canonical_event_bytes`).
- **Make illegal states unrepresentable.** Drives AC-4 boundary-only append policy + `pydantic.ValidationError` rejection.
- **Newtype identifiers — never raw `str` for domain IDs.** All identifiers (`WorkflowId`, `TransitionId`, `ChainHead`, `BlobDigest`) are existing newtypes from prior stories; no new newtypes in this story.
- **Functional core / imperative shell.** Drives the AC-13 clock injection (the imperative-shell store captures the clock; the pure-core `_compute_chain_head` from S1-02 stays clock-free).
- **Type everything, strictly — `mypy --strict`.** Drives AC-16 typecheck-clean.
- **Extension by addition — no silent edits.** Drives AC-2 unchanged-`__all__` test + AC-15 contract snapshot extension.

### What the existing precedents prescribe

- `src/codegenie/plugins/events.py` is the canonical "port + two adapters" sibling: `EventStreamSink` Protocol with `append`/`read_all`/`fsync`/`tail_chain_head`/`lock` (five methods); `ZstdAppendingFileSink` production adapter; `InMemorySink` test adapter; `GENESIS_CHAIN_HEAD: Final[BlobDigest] = BlobDigest("0" * 64)` constant; `fcntl.flock`-protected append discipline; `_tail_chain_head` pure helper. This story mirrors that shape for the SQLite substrate.
- `_FROZEN_FORBID: Final[ConfigDict]` is the single canonical Pydantic config (S1-01 AC-4 canonical-site discipline); the store layer does not need to re-export — it consumes `TransitionEvent` (already `_FROZEN_FORBID`) and persists its `model_dump_json` output.
- `codegenie/output/sanitizer.py` is the single canonical regex set + `RedactedSlice` smart constructor; AC-12 mandates this is imported, never forked.

### Open ambiguities resolved before critics

- **Q1 — `EventLog` vs `CheckpointStore`: reuse or two ports?** Two ports. The forensic two-stream log (`EventLog`) and the per-workflow checkpoint chain (`CheckpointStore`) have different durability requirements, different read patterns, different consumers. Conflating them would couple the replay path to the forensic path and force the Phase-9 Postgres migration to dual-implement. Documented in References §"Disambiguation note" + Notes-for-implementer.
- **Q2 — Payload cap at the model or the store layer?** Store layer. The forensic EventLog needs full evidence capture; the checkpoint chain needs compact replay-only events. Capping at the model layer would break the forensic log. Documented in AC-10 + Notes-for-implementer.
- **Q3 — Per-workflow SQLite file vs one shared file?** Per-workflow. Concurrency isolation + matches the `.codegenie/remediation/<run-id>/` directory shape + trivial per-workflow cleanup. Documented in AC-5 + Notes-for-implementer.
- **Q4 — Async `append()` / `read_all_for_workflow()` on the Protocol?** Sync. The orchestrator wraps SQLite calls in `asyncio.to_thread` (mirrors the Phase-3 `EventLog.emit_spanning` pattern). Async-by-default leaks the substrate choice — SQLite is sync; Postgres async drivers exist but the orchestrator is the seam, not the store. Documented in Anti-refactor #7.
- **Q5 — `_GENESIS_CHAIN_HEAD` re-export or new declaration?** Single canonical declaration in `checkpoints.py` (or re-export from Phase-3 `events.py` if a kernel-tier home already exists — the Refactor step pins the decision). Mirrors the S1-01 `_FROZEN_FORBID` discipline.
- **Q6 — Should the boundary check live in a `CheckpointAppendRequest` wrapper or inline in `append()`?** Inline. A wrapper for one validator is primitive-obsession-in-reverse (Anti-refactor #5).
- **Q7 — Does this story own the `FailedUnrecoverable(reason="checkpoint_integrity")` decision?** No — that belongs to S2-02. This story ships ONLY the detection-substrate primitives (`tail_chain_head` returns persisted, NOT recomputed; AC-11 is the load-bearing assertion). The detection/policy separation is the most important invariant of the substrate.

## Four-lens findings (inline, no parallel subagents — story scope didn't justify the spawn; mirrors S1-01 + S1-02 precedent in this phase)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "checkpoints append at boundaries" un-verifiable (no port, no adapters, no shape) | block | Replaced with AC-1 (`CheckpointStore` five-method Protocol with `runtime_checkable` + annotation byte-equality) + AC-5 (`SqliteCheckpointStore` schema + WAL + per-workflow file) + AC-6 (`InMemoryCheckpointStore` parity adapter). |
| `_SEMANTIC_BOUNDARY_KINDS` catalog missing | block | AC-3 closed frozenset + three sub-tests (membership-byte-equality against final-design.md item 3; subset of `LedgerStateKind`; terminal-kinds-are-boundary-kinds cross-consistency). |
| Boundary-only append policy missing | block | AC-4 `pydantic.ValidationError` rejection with directive substring + parametrized test over non-boundary kinds. |
| Chain-forward extension property missing | block | AC-7 Hypothesis property parametrized over both adapters (stability + chain-forward + cross-workflow isolation). |
| Read-ordering property missing | block | AC-8 append-order + cross-workflow filter property. |
| Detection-substrate-only `tail_chain_head` contract unstated | block | AC-11 explicit "tail_chain_head does NOT recompute; S2-02 owns policy" + partial-write detection test. |
| Payload cap unspecified (numeric, typed exception, error_id) | block | AC-10 `_MAX_EVENT_BYTES = 65_536` + `CheckpointPayloadTooLargeError` + `error_id = "workflows.checkpoint_payload_too_large"`. |
| Sanitizer-import discipline absent | block | AC-12 AST fence + secret-shape property test. |
| `__slots__` discipline on adapters absent | harden | AC-14 AST fence over adapter modules. |
| Clock injection for determinism absent | block | AC-13 `clock: Callable[[], datetime] | None` constructor parameter + deterministic golden test. |
| Golden ordering test under-specified (no scenario, no location, no directive) | block | AC-9 names two scenarios from phase-arch-design.md (clean completion + retry-recovery), names the golden location, names the directive, names the regeneration env var. |
| Cross-story consistency with S1-02 `_TERMINAL_LEDGER_KINDS` unstated | block | AC-3 sub-test 3 enforces `_TERMINAL_LEDGER_KINDS <= _SEMANTIC_BOUNDARY_KINDS`. |
| `__all__` byte-equality test absent | block | AC-2 asserts the 14-name set is unchanged after this story lands. |
| Contract snapshot extension absent | block | AC-15 extends S1-01 + S1-02 contract snapshot + meta-test additive/breaking case set with two checkpoint-shaped synthetic deltas. |
| `mypy --strict` AC absent | harden | AC-16. |
| Parity-contract test absent | block | AC-6 parametrized over both adapters; same property suite. |
| Parity-meta-test (mutation guard for AC-6) absent | harden | AC-17 broken-adapter-fails-parity meta-test. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| TDD plan Refactor "share canonical serialization helpers" hints at inheritance | block | Anti-refactor #1: forbids `BaseCheckpointStore` / mixin; if duplication arises, extract a free function `_canonical_event_bytes` in `checkpoints.py` (composition via function call). |
| "Golden ordering test is deterministic" too generic | block | AC-9 names scenarios, golden file path, directive text, regeneration env var, additive-vs-breaking classifier inheritance. |
| No mutation-thinking pass | block | Each AC's test was checked: a mutant `append()` that ignores `prior_head` fails AC-7's chain-forward; a mutant `tail_chain_head` that recomputes fails AC-11's detection-substrate contract; a mutant store that shares heads across workflows fails AC-7's cross-workflow isolation; a mutant `read_all_for_workflow` that sorts by chain-head string fails AC-8's append-order; a mutant payload validator at the model layer fails AC-10's "cap at store layer" assertion. |
| No property-based tests | block | AC-7 + AC-8 + AC-11 are Hypothesis-driven; cross-workflow isolation in AC-7 is the load-bearing mutation guard. |
| No contract-snapshot meta-test extension | block | AC-15 extends the S1-01 + S1-02 meta-test additively with two checkpoint-shaped synthetic deltas. |
| No AST `__slots__` fence | harden | AC-14 fence over both adapter modules. |
| No AST sanitizer-import fence | block | AC-12 forbids local `re.compile` in store modules + requires canonical sanitizer import. |
| Parity test itself is mutation-susceptible | harden | AC-17 meta-test closes the gap. |
| Partial-write detection test absent (the original story didn't even mention partial writes) | block | AC-11 partial-write detection-substrate test + the "tail_chain_head does NOT recompute" load-bearing assertion. |
| Between-boundary no-write property absent | harden | AC-13 (second half) scripted scenario asserts EXACTLY two rows after two boundary transitions. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| Story didn't reference ADR-0003, final-design.md §"Decisions of record" item 3, phase-arch-design.md §"Deployment view" / §"Scenarios" / §"Failure modes" | harden | References block now names all of them + S1-01 + S1-02 dependencies + Phase-3 S6-01 sibling + Phase-9 S5-01 forward dep. |
| Story didn't reference Phase-3 `EventStreamSink` precedent | block | References block names it + Notes-for-implementer surfaces the disambiguation (forensic log vs checkpoint store — different ports, different consumers). |
| TDD plan Refactor "share helpers" contradicts CLAUDE.md "composition over inheritance" | block | Anti-refactor block + Notes-for-implementer cite the Phase-3 precedent (two adapters share NOTHING via inheritance). |
| No `Depends on:` line | nit | Added "Depends on S1-02 (TransitionEvent, _LEGAL_TRANSITIONS, _TERMINAL_LEDGER_KINDS, _compute_chain_head) + S1-01 (WorkflowId, _FROZEN_FORBID, allowlist sentinel)." |
| Cross-story `_TERMINAL_LEDGER_KINDS` membership unencoded | block | AC-3 sub-test 3 cross-consistency. |
| Phase-9 Postgres-adapter forward dep unstated | harden | References block + AC-1 Rule-of-three note + Notes-for-implementer "Phase-9 Postgres swap" entry. |
| Detection/policy separation unstated (the most insidious failure mode) | block | AC-11 explicit + Notes-for-implementer "detection-substrate-only is load-bearing" entry. |
| `EventLog` vs `CheckpointStore` conflation risk | block | References §"Disambiguation note" + Notes-for-implementer "Why deliberately separate" entry + AC-1 (iv) static assertion that `EventStreamSink` is NOT imported in the store modules. |
| `_FROZEN_FORBID` canonical-site discipline (from S1-01) not extended | nit | The store consumes `TransitionEvent` which is already `_FROZEN_FORBID`; no new model classes in this story require the config (the adapters are imperative classes with `__slots__`, not Pydantic models). |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| Risk of single-concrete-class (no port, no adapter pattern) | block | AC-1 mandates `CheckpointStore` Protocol; AC-5 + AC-6 mandate two adapters; AC-6 parity test enforces Protocol-as-kernel. |
| TDD plan Refactor hints at inheritance ("shared helpers") | block | Anti-refactor #1: composition via free function only; the Phase-3 `EventStreamSink` two-adapter precedent shares NOTHING via inheritance. |
| Open/Closed at the file boundary not encoded (file naming would prevent Phase-9 additive Postgres adapter) | block | AC-1 Rule-of-three note: `checkpoints.py` for the Protocol, `sqlite_checkpoints.py` for the adapter (not `store.py` + `SqliteCheckpointStore`). Phase-9 lands `postgres_checkpoints.py` additively. |
| `CheckpointStoreRegistry` premature abstraction risk | nit | Anti-refactor #2: rejected per Rule 2 (two adapters today; threshold reached at Phase-9 Postgres = third). Documented in Notes-for-implementer for the day Phase-7 adds migration-task-class checkpoints. |
| `BaseCheckpointStore` ABC premature abstraction risk | block | Anti-refactor #1: explicit forbid + Phase-3 precedent cite. |
| `SemanticBoundaryStrategy` premature abstraction risk | nit | Anti-refactor #4: rejected — boundary catalog is a closed `frozenset`, not a runtime-dispatched strategy. Phase-7 migration task class lands a sibling `_SEMANTIC_BOUNDARY_KINDS_MIGRATION` constant in a sibling file, not a Strategy. |
| `CheckpointTransaction` Command-pattern risk | nit | Anti-refactor #3: rejected — six-line imperative-shell SQL doesn't earn a Command. |
| `CheckpointAppendRequest` wrapper Pydantic model risk | nit | Anti-refactor #5: rejected — primitive-obsession-in-reverse; put the boundary check in `append()`'s first line. |
| `clock` Protocol abstraction risk | nit | Anti-refactor #6: `Callable[[], datetime]` IS the Protocol expressed without ceremony. |
| Async `append()` on the Protocol risk | block | Anti-refactor #7: sync `append`; orchestrator wraps in `asyncio.to_thread` (mirrors Phase-3 `EventLog.emit_spanning`). Async-by-default leaks substrate choice. |
| `__all__` widening risk (executor adds store types for "convenience") | block | AC-2 asserts 14-name set unchanged byte-equal; mutation kills loud with directive pointing at final-design.md §"may not depend on" constraint. |
| `__slots__` typo-defense + memory discipline opportunity | harden | AC-14 AST fence over adapters. |
| Functional core / imperative shell split for the store | harden | AC-13 clock injection (the SOLE clock site in the imperative shell; AC-5 schema flow keeps `_compute_chain_head` clock-free by construction); S1-02's `tests/fence/test_chain_head_purity.py` continues to pass. |
| Sanitizer-canonical-import discipline (no regex fork) | block | AC-12 AST fence over store modules forbids local `re.compile`. |
| Specification-pattern transition-predicate opportunity | nit | Already rejected in S1-02 validation; closed `frozenset` predicates don't earn Specification. |
| Capability-pattern opportunity (orchestrator-injected `CheckpointStore`) | harden | The Protocol IS the capability pattern — orchestrator injects `CheckpointStore`-typed parameter; selecting an adapter is a constructor decision, not a runtime registry lookup. Documented in Notes-for-implementer "Why the five-method Protocol shape matters." |
| Per-workflow file vs single shared file | block | AC-5 pins per-workflow files with three justifications (concurrency isolation, `.codegenie/remediation/<run-id>/` shape, trivial cleanup). |
| WAL + sync=FULL pragma discipline | block | AC-5 pins both + golden assertion. |

## Synthesis + edit summary

No conflicts between critics. No `NEEDS RESEARCH` findings. The synthesizer applied every fix above in one editing pass:

- 3 ACs → 17 ACs (AC-1 through AC-17), every one individually verifiable with a named test file + failure-mode mutation check.
- TDD plan rewritten in Red-first order with an explicit Anti-refactor block (no `BaseCheckpointStore` ABC; no `CheckpointStoreRegistry`; no `CheckpointTransaction` Command; no `SemanticBoundaryStrategy`; no `CheckpointAppendRequest` wrapper; no `clock` Protocol; no async `append`).
- References block populated (11 entries — final-design.md item 3 + §"Main workflow" + §"State model", phase-arch-design.md §"Logical view" + §"Process view" + §"Deployment view" + §"Failure modes", ADR-0003 §Decision + §Tradeoffs + §Consequences, High-level-impl.md §"Step 2", S1-01 + S1-02 hardened stories with their validation reports, S2-02 downstream consumer, Phase-3 S6-01 `EventStreamSink` precedent with disambiguation note, Phase-3 S6-04 orchestrator precedent, Phase-4 sanitizer precedent, Phase-9 S5-01 + S3-01 forward deps).
- Files to touch enumerated (5 new src files + 13 new test files + 4 modifications + 2 goldens).
- Out of scope enumerated (7 deferrals + 3 anti-patterns).
- Notes for implementer enumerated (8 entries — five-method Protocol rationale, EventLog/CheckpointStore disambiguation, payload-cap layer choice rationale, per-workflow file rationale, detection-substrate-only load-bearing separation, parity-contract-test factory-parametrization rationale, `__slots__` discipline rationale, contract-snapshot meta-test non-negotiability, Phase-7 migration-checkpoints file-naming Open/Closed substrate, Phase-9 Postgres-swap "what stays the same").
- Status flipped from `Ready` → `HARDENED`. Validated-date line added.

## Verdict — HARDENED. The story is ready for `phase-story-executor`.

The executor's Validator pass now has 17 concrete acceptance criteria, each tied to a named test file and a mutation-resistance check. The cross-story `_TERMINAL_LEDGER_KINDS` membership invariant, the ADR-0003 chain-forward extension property, the detection-substrate-only separation between this story and S2-02, the canonical sanitizer-import discipline, the `__slots__` adapter fence, the per-workflow SQLite + WAL + flock substrate, the parity-contract test parametrized over both adapters, the parity-meta-test mutation guard, the additive-vs-breaking contract-snapshot extension, the Anti-refactor block forbidding seven specific over-abstractions, and the Open/Closed file-boundary discipline that lets Phase-9's Postgres adapter land additively are all encoded as enforceable structural defenses. A mutant implementation that violates any one of them fails at least one test.

The most important structural defense is **AC-11 (detection-substrate-only `tail_chain_head`)** — this is the load-bearing separation between this story (substrate fidelity) and S2-02 (integrity policy). Without it, an executor's "helpful" recomputation would silently collapse ADR-0003's "verify the previous chain head before hydration" decision into the substrate, breaking the Phase-9 byte-equality forward dep across SQLite ↔ Postgres adapters. The AC pins the contract; the test catches the mutation.
