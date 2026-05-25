# Attempt log — S2-01 (Semantic checkpoints)

## Attempt 1 — 2026-05-25 — GREEN

**Executor:** phase-story-executor (Claude Opus 4.7)
**Outcome:** All 17 acceptance criteria satisfied; full Phase-6 + checkpoint test suite green (268 new + amended tests pass).
**Total new tests landed:** 56 unit + property + integration + fence tests across 10 new files + 3 amended files.

### Files landed

**Source (new):**
- `src/codegenie/workflows/checkpoints.py` — `CheckpointStore` Protocol (runtime_checkable, 5 methods), `_SEMANTIC_BOUNDARY_KINDS` (closed frozenset of 6), `_MAX_EVENT_BYTES = 65_536`, `_GENESIS_CHAIN_HEAD`, `_assert_boundary` helper, `_canonical_event_bytes` helper.
- `src/codegenie/workflows/sqlite_checkpoints.py` — production WAL adapter, per-workflow SQLite file under `root/<workflow_id>/checkpoints.sqlite`, per-workflow `fcntl.flock` lock file, clock injection, `__slots__`, sanitizer wired.
- `src/codegenie/workflows/in_memory_checkpoints.py` — test adapter mirroring the same Protocol; same sanitizer/cap/boundary discipline so AC-6 byte-equality holds.
- `src/codegenie/workflows/errors.py` — `CheckpointPayloadTooLargeError` with `error_id = "workflows.checkpoint_payload_too_large"`.

**Source (amended):**
- `src/codegenie/output/sanitizer.py` — added `sanitize_for_persistence(bytes) -> bytes`, a thin wrapper over `redact_raw_artifact_bytes` so the canonical regex set has a single declaration site.

**Tests (new):**
- `tests/unit/workflows/test_checkpoint_store_protocol.py` — AC-1 (4 tests).
- `tests/unit/workflows/test_semantic_boundary_set.py` — AC-3 + AC-4 (12 tests).
- `tests/unit/workflows/test_checkpoint_sqlite_schema.py` — AC-5 (2 tests).
- `tests/unit/workflows/test_checkpoint_payload_cap.py` — AC-10 (4 tests).
- `tests/unit/workflows/test_checkpoint_clock_and_between_boundary.py` — AC-13 (3 tests).
- `tests/unit/workflows/test_all_unchanged_after_s2_01.py` — AC-2 (2 tests).
- `tests/property/_phase6_event_strategies.py` — shared Hypothesis strategy + factory parametrize lists.
- `tests/property/test_checkpoint_chain_forward.py` — AC-7 (6 tests, parametrized over both adapters).
- `tests/property/test_checkpoint_read_ordering.py` — AC-8 (4 tests, parametrized).
- `tests/property/test_checkpoint_partial_write.py` — AC-11 (2 tests).
- `tests/integration/test_checkpoint_store_parity.py` — AC-6 (3 tests).
- `tests/integration/test_checkpoint_store_parity_meta.py` — AC-17 (1 test).
- `tests/integration/test_checkpoint_golden_ordering.py` — AC-9 (2 tests).
- `tests/fence/test_checkpoint_sanitizer_imports.py` — AC-12 (3 tests, AST + runtime).
- `tests/fence/test_checkpoint_adapter_slots.py` — AC-14 (3 tests, AST + runtime).

**Tests (amended):**
- `tests/integration/test_phase6_sut_contract_snapshot.py` — AC-15 extension: added `checkpoint_store_protocol`, `checkpoint_store_is_runtime_protocol`, `semantic_boundary_kinds`, `max_event_bytes`, `checkpoint_sqlite_schema` to the snapshot; extended classifier with checkpoint-substrate diff rules.
- `tests/integration/test_phase6_sut_contract_snapshot_meta.py` — AC-15 meta: 6 new synthetic deltas (additive new Protocol method, breaking removed boundary kind, breaking narrowed `_MAX_EVENT_BYTES`, additive widened cap, breaking runtime_checkable removed, breaking signature changed).

**Goldens:**
- `tests/golden/phase6-checkpoint/sqlite_schema.sql` — AC-5 byte-equal sidecar.
- `tests/golden/phase6-checkpoint/clean_completion_chain.json` — AC-9 chain golden.
- `tests/golden/phase6-contract/snapshot.json` — regenerated under `PHASE6_CONTRACT_GOLDEN_REWRITE=1` after AC-15 extension.

### Mutation-resistance checks performed

- **AC-1 method-set:** dropping any of the five methods fails `test_checkpoint_store_exposes_exactly_five_methods` byte-loud.
- **AC-3 boundary set:** dropping `failed_unrecoverable` fails `test_ac3_terminal_kinds_are_boundary_kinds` (terminal partition discipline); adding `needs_plan` fails `test_ac3_needs_plan_is_not_a_boundary`.
- **AC-4 directive substring:** the parametrized non-boundary test checks for "Phase-6 checkpoint policy violation" + "ADR-0003" + the literal `next_state_id`.
- **AC-5 schema golden:** any whitespace drift between `_CHECKPOINT_SCHEMA_SQL` and the `.sql` sidecar fails byte-loud.
- **AC-6 parity:** a buggy adapter using `hash()` or `_GENESIS_CHAIN_HEAD` for every append fails the byte-equality assertion across both stores.
- **AC-7 chain-forward:** a store that swallows `prior_head` fails on `min_size=2` Hypothesis examples; a store that shares heads across workflows fails the cross-workflow-isolation sub-property.
- **AC-8 ordering:** a store that sorts by `transition_id` or `next_head` fails the append-order property; one that omits the workflow filter fails cross-workflow.
- **AC-9 golden:** any change to `_compute_chain_head` byte-stability or `TransitionEvent` schema fails the byte-equal assertion with a clear additive-vs-breaking directive.
- **AC-10 cap:** a swap to cap at the model layer would break the forensic EventLog; `test_ac10_cap_lives_at_store_layer_not_model_layer` constructs an oversized event the model accepts but the store rejects.
- **AC-11 detection-only:** an executor "helpfully" recomputing inside `tail_chain_head` would return a recomputed-different-from-persisted value; my test tampers the row and asserts the *tampered* value is returned.
- **AC-12 sanitizer:** any local `re.compile` in either adapter trips the AST fence; the secret-shape property test injects an `AKIA...` token and asserts redaction in persisted bytes.
- **AC-13 clock determinism:** any executor that calls `datetime.now()` directly cannot inject a frozen clock, breaking the golden ordering test.
- **AC-14 `__slots__`:** a typo'd `self._connetcion = ...` assignment raises `AttributeError` at runtime (third test asserts this directly).
- **AC-15 contract snapshot:** any `==`→`!=` mutation in the additive/breaking classifier is caught by the 6 new meta-tests exercising checkpoint-shaped deltas.
- **AC-17 parity meta:** a reversed-reader adapter passing the parity test would be a tautology; the meta-test asserts the parity invariant fires.

### Decisions of record

- **`_GENESIS_CHAIN_HEAD` declared locally (not re-exported from Phase-3 events.py).** The Phase-3 `GENESIS_CHAIN_HEAD` is a `BlobDigest`, not a `ChainHead`; the two are different newtypes. Phase-3 declared its own; Phase-6 declares its own. Both are bare 64-hex zeros — convention preserved.
- **Sanitization is write-time only; chain head is computed over the live event.** AC-12 says "the store's serialization path ... MUST pass through sanitize_for_persistence" — that's the bytes written to the row. The chain head input is the live `event` (which retains the cleartext) so byte-equality between adapters holds even when the on-disk bytes are redacted. The S2-02 verifier will recompute against the persisted bytes; if a redaction triggers, that's a deliberate divergence the verifier policy can flag — but detection-substrate-only is preserved here.
- **Per-example tmp subdir for Hypothesis tests.** Without a fresh sub-directory per example, the SQLite file accumulates state across `@given` examples within one test invocation. The `_EXAMPLE_COUNTER` module-level dict + `_fresh_subdir(tmp_path)` helper isolates each example.
- **Unique `transition_id` within Hypothesis lists.** Used `unique_by=lambda e: e.transition_id` on the `st.lists` strategy so the SQLite UNIQUE constraint never trips within a single example draw.
- **`InMemoryCheckpointStore` accepts (and ignores) a `root` argument.** Required by the parity contract fixture which constructs `factory(tmp_path)` for both adapters. Mirrors the Phase-3 `InMemorySink()` convenience (no-arg) but extended for parity-test ergonomics.
- **In-memory adapter stores sanitized bytes + parses on read.** Mirrors the SQLite adapter exactly so the parity contract test (AC-6) compares byte-for-byte across adapters. An alternative — storing the live event in-memory and skipping the round-trip — would have been faster but would have broken byte-parity when sanitization triggers.
- **Scenario #2 path corrected to 6 transitions / 5 boundary writes.** Initial sequence had no non-boundary transition target so `len(boundary_writes) == 6`; corrected to include the `gate_failed_retryable → needs_plan` retry-branch (the one non-boundary edge today) so the test asserts the structural invariant per the story prose.

### Refactor decisions

- **Composition over inheritance for adapter sharing.** Both `SqliteCheckpointStore` and `InMemoryCheckpointStore` call free functions `_assert_boundary`, `_canonical_event_bytes` in `checkpoints.py` — no `BaseCheckpointStore` ABC, no mixin. Anti-refactor #1 honored.
- **No `CheckpointStoreRegistry`.** Two adapters today; rule-of-three threshold reached when Phase-9 lands `PostgresCheckpointStore`. Anti-refactor #2 honored.
- **No `CheckpointTransaction` context manager.** The `append()` body is six lines of imperative-shell SQL; wrapping it in a Command-pattern abstraction is over-design for one call site. Anti-refactor #3 honored.
- **`Callable[[], datetime]` as the clock type, not a `Clock` Protocol.** AC-13 names the callable shape directly; no ceremony. Anti-refactor #6 honored.

### Test counts touched

- Suite-level: **7321 passed, 44 skipped, 9 xfailed, 4 pre-existing flakes** (lint-imports/pre-commit/mkdocs PATH issues; tsconfig perf flake) — all four flakes pass when re-run with the venv on PATH (env-related, not introduced by this story).
- Phase-6 checkpoint suite: 49 tests across 9 new files + 7 new tests on amended files (`test_phase6_sut_contract_snapshot.py` AC-15 row, meta-test 6 new cases).
- Mypy: 243 source files clean under `--strict`.
- Ruff: all checks passed; ruff format clean.
- Import-linter: 12 contracts kept, 0 broken.

### Notes for downstream stories

- **S2-02 (replay verifier)** dispatches on `store.tail_chain_head(wf)` + `store.read_all_for_workflow(wf)`; recomputes the chain via `_compute_chain_head` and rejects any divergence with `FailedUnrecoverable(reason="checkpoint_integrity")`. The AC-11 partial-write tamper test is exactly the failure mode S2-02 must surface.
- **S3-01 (plugin-local subgraph)** constructs a `SqliteCheckpointStore` (via constructor injection from the SUT adapter S5-01) and emits `TransitionEvent`s through the conditional edges. The boundary policy is enforced by `append()` — the subgraph cannot accidentally checkpoint at `needs_plan`.
- **S4-01 (HITL)** reads the chain head + the latest `awaiting_human_review` row via `store.read_all_for_workflow(wf)` filtered by `next_state_id`; legal `awaiting_human_review → plan_ready` transition is already in S1-02's `_LEGAL_TRANSITIONS`.
- **S5-01 (LocalVulnRemediationSut)** constructs the store via `SqliteCheckpointStore(root, clock=...)` and passes it through the subgraph. The Postgres adapter swap (Phase-9 S5-01) is a one-line constructor change.
- **Phase-9 G5 byte-equality.** The Protocol + parity-contract test is the substrate Phase 9 will assert byte-identical across SQLite and Postgres backends. Adding the Postgres adapter is one line in `ADAPTER_FACTORIES` + one new file `postgres_checkpoints.py`.

### Sanitization design point — surfaced for downstream review

The chain head is computed over the *live* event (which can contain cleartext), while the on-disk row is the *sanitized* bytes. On replay, S2-02 will recompute the chain over the persisted (sanitized) bytes, which would NOT match the persisted chain head if sanitization triggered. This is intentional:

- The detection (S2-01's `tail_chain_head` reads what was persisted; never recomputes).
- The policy (S2-02's verifier folds the persisted bytes and compares; if they differ, the workflow transitions to `FailedUnrecoverable(reason="checkpoint_integrity")`).

If S2-02 wants to surface secret-redaction as a benign divergence vs. a tamper, it will need to know how to distinguish them. Two approaches: (i) S2-02 also runs `sanitize_for_persistence` on the live event before recomputing (mirrors the write path); (ii) we add a "redaction occurred" sentinel column to the SQLite schema. Both are S2-02 design decisions, deferred to that story. **Surfaced for the S2-02 executor.**

### Follow-ups surfaced this attempt

- **S2-02 sanitization-aware replay.** Per the design point above, S2-02 must decide how to handle the live-event-vs-persisted-bytes divergence when sanitization triggered. Recommend mirroring the write path: S2-02's recomputation pipeline calls `sanitize_for_persistence` on the live event before folding. (Minor; S2-02 design decision.)
- **`PostgresCheckpointStore` (Phase-9 S5-01).** The Protocol + parity-contract test is the substrate. One line addition to `tests/property/_phase6_event_strategies.py` `ADAPTER_FACTORIES` + a new `postgres_checkpoints.py` adapter. (Out of scope; just the precedent.)
