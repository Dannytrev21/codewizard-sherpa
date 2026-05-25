# S2-01 — Semantic checkpoints

**Status:** GREEN
**Validated:** 2026-05-25 — see [`_validation/S2-01-semantic-checkpoints.md`](_validation/S2-01-semantic-checkpoints.md).
**Shipped:** 2026-05-25 — see [`_attempts/S2-01-semantic-checkpoints.md`](_attempts/S2-01-semantic-checkpoints.md). 17/17 ACs satisfied with runtime evidence; 56 new tests + 7 amended tests; mypy --strict + ruff + import-linter clean.
**Depends on:** [`S1-02-ledger-state-union.md`](S1-02-ledger-state-union.md) — imports `TransitionEvent`, `LedgerStateKind`, `_TERMINAL_LEDGER_KINDS`, `_LEGAL_TRANSITIONS`, and the `_compute_chain_head` pure helper from `codegenie.workflows`. AC-9 cross-story consistency test asserts the semantic-boundary catalog is a subset of `LedgerStateKind`. Also depends on [`S1-01-sut-contract-types.md`](S1-01-sut-contract-types.md) for `WorkflowId`, `_FROZEN_FORBID`, the `codegenie.workflows.__all__` allowlist sentinel, and the contract-snapshot meta-test the AC-15 extension inherits.

**Goal:** Land the replay-safe **`CheckpointStore` port** (with at least the production `SqliteCheckpointStore` adapter and the test-only `InMemoryCheckpointStore` adapter), the closed `_SEMANTIC_BOUNDARY_KINDS: Final[frozenset[LedgerStateKind]]` catalog that ADR-0003's "persist only at semantic boundaries" rule enumerates, the bounded-payload guard (canonical-JSON byte cap) that AC-3-original gestured at, and the BLAKE3 chain-forward extension wiring that consumes S1-02's `_compute_chain_head` helper — and *only* those — so the replay verifier (S2-02), the subgraph nodes (S3-01), the HITL resume validator (S4-01), and the SUT adapter (S5-01) can target a frozen append/read contract that the Phase-6.5 bench harness and the Phase-9 Postgres-adapter swap (S5-01 in Phase 9) will later assert byte-identical across substrates.

This is the first half of High-level-impl.md §"Step 2 — Replay-safe checkpoint store" ("Implement semantic checkpoint append/read"). S1-02 shipped the *event* + the closed transition table + the *pure* chain-head helper; this story ships the *persistent store* every node and the replay verifier (S2-02) will dispatch through. The "verify prior chain head before hydrate" half lives in S2-02 (this story's `tail_chain_head` is the substrate S2-02 calls; this story does **not** own the integrity-failure → `FailedUnrecoverable(reason="checkpoint_integrity")` decision — only the *detection* primitive S2-02 invokes).

## References

- [final-design.md](../final-design.md) §"Main workflow" steps 1–7 (where the boundary writes happen), §"Decisions of record" item 3 (checkpoint at plan / patch / gate / escalation / terminal — the exact five semantic boundaries the catalog enumerates), §"State model" (the closed seven-variant universe from which the boundary subset is drawn).
- [phase-arch-design.md](../phase-arch-design.md) §"Logical view" (the `LEDGER["VulnLedger + checkpoint store"]` node — this story builds the *checkpoint store* half), §"Process view" sequence "G->>L: checkpoint PlanReady" and "G->>L: checkpoint terminal / retry / interrupt" (the orchestrator-side call shape AC-2 freezes), §"Deployment view" (`.codegenie/remediation/<run-id>/` SQLite file is the local substrate this story implements), §"Failure modes" (checkpoint chain mismatch → `FailedUnrecoverable` belongs to S2-02; this story owns the *detection*-substrate `tail_chain_head` API).
- [ADRs/0003-checkpointed-ledger-replay-boundary.md](../ADRs/0003-checkpointed-ledger-replay-boundary.md) §Decision (persist only at semantic boundaries — drives AC-3 catalog + AC-4 boundary-write-only policy) + §Tradeoffs ("A crash between semantic checkpoints replays a little work" — drives AC-13 between-boundary-no-write property) + §Consequences ("Kill/resume tests pin checkpoint ordering" — drives AC-6 golden ordering test) + ("Failed verification transitions to `FailedUnrecoverable`" — explicitly **owned by S2-02**, not this story).
- [High-level-impl.md](../High-level-impl.md) §"Step 2 — Replay-safe checkpoint store" (this story is the first bullet — "Implement semantic checkpoint append/read"; S2-02 is the second bullet — "Verify prior chain head before hydrate"; S2-06 the kill/resume golden is here too, but the golden ordering test for the store layer is owned by THIS story per ADR-0003 Consequences).
- [S1-02-ledger-state-union.md](S1-02-ledger-state-union.md) + [_validation/S1-02-ledger-state-union.md](_validation/S1-02-ledger-state-union.md) — `TransitionEvent` (seven-field shape), `_LEGAL_TRANSITIONS` (closed edges), `_TERMINAL_LEDGER_KINDS` (terminal partition), `_compute_chain_head` (pure helper in `_chain.py`), `_FROZEN_FORBID` (canonical config), the AST no-side-effects fence over `_chain.py` that this story inherits (the store layer is the imperative shell that *consumes* the pure core — must NOT add `time` / `uuid` / `os.environ` imports to `_chain.py` while wiring the store).
- [S1-01-sut-contract-types.md](S1-01-sut-contract-types.md) — `WorkflowId` newtype, `codegenie.workflows.__all__` allowlist sentinel (AC-12) this story does **not** mutate (the store types stay package-private — see AC-2), the contract-snapshot meta-test (AC-15 in this story extends it additively with `CheckpointStore`-shaped synthetic deltas).
- [S2-02-replay-verification.md](S2-02-replay-verification.md) — downstream consumer; AC-9 of this story documents the substrate contract S2-02 verifies (read-all-for-workflow returns events in append-order; `tail_chain_head` returns the head S2-02 recomputes against).
- Phase-3 S6-01 precedent: [`src/codegenie/plugins/events.py`](../../../../src/codegenie/plugins/events.py) — the canonical `EventStreamSink` Protocol + `ZstdAppendingFileSink` + `InMemorySink` two-adapter pattern; `GENESIS_CHAIN_HEAD: Final[BlobDigest] = BlobDigest("0" * 64)` chain-genesis constant convention; `fcntl.flock`-protected append discipline. This story applies the same port-plus-two-adapters pattern to a SQLite substrate. **Disambiguation note (load-bearing):** the Phase-3 `EventLog` is the *forensic two-stream log* (`emit_internal` / `emit_spanning`) — it is NOT this story's `CheckpointStore`. The forensic log records "what happened" across the whole workflow + cross-workflow span (provenance gates, capabilities minted, RAG harvest); the checkpoint store records "what state transitions were durably observed" for the specific purpose of replay-safe resume. Conflating the two would couple the replay-verification path (S2-02) to the forensic-log path (S6-01) — see S1-02 validation §Notes-for-implementer "EventId vs TransitionId" for the parallel newtype disambiguation.
- Phase-3 S6-04 precedent: [`docs/phases/03-vuln-deterministic-recipe/stories/S6-04-remediation-orchestrator.md`](../../03-vuln-deterministic-recipe/stories/S6-04-remediation-orchestrator.md) — the orchestrator that emits transitions; AC-4 names the orchestrator-side call shape this store's `append()` accepts.
- Phase-4 forward reuse: [`src/codegenie/output/sanitizer.py`](../../../../src/codegenie/output/sanitizer.py) — the canonical regex set + `RedactedSlice` smart constructor; AC-12 requires the bounded-payload guard call the existing sanitizer before write, not fork it.
- Phase-9 forward dep: [`docs/phases/09-temporal-durable-workflow/stories/S5-01-postgres-checkpointer-adapter.md`](../../09-temporal-durable-workflow/stories/S5-01-postgres-checkpointer-adapter.md) — the third concrete `CheckpointStore` adapter (Postgres). The file naming + the Protocol shape this story freezes (`CheckpointStore`, not `SqliteCheckpointStore`-as-Protocol) is the Open/Closed substrate that lets Phase 9's adapter land *additively*. AC-2 forbids any consumer importing `SqliteCheckpointStore` directly — they import the Protocol — so the Postgres swap is a constructor injection, not a kernel edit.
- Phase-9 forward dep: [`docs/phases/09-temporal-durable-workflow/stories/S3-01-event-log-append-chain.md`](../../09-temporal-durable-workflow/stories/S3-01-event-log-append-chain.md) — Phase-9's BLAKE3 chain-append discipline; AC-7 of this story (chain-forward extension property over `append() → tail_chain_head()`) is the substrate Phase-9 will assert byte-identical across SQLite and Postgres backends.

## Acceptance criteria

### `CheckpointStore` port (the Open/Closed substrate)

- [ ] **AC-1 — Canonical module + Protocol shape.** `src/codegenie/workflows/checkpoints.py` declares a `runtime_checkable` Protocol with exactly five methods:
  ```python
  @runtime_checkable
  class CheckpointStore(Protocol):
      def append(self, event: TransitionEvent) -> ChainHead:
          """Append `event` under the workflow's append-lock; return the new chain head."""

      def read_all_for_workflow(self, workflow_id: WorkflowId) -> Iterator[TransitionEvent]:
          """Yield every TransitionEvent for `workflow_id` in monotonic append order."""

      def tail_chain_head(self, workflow_id: WorkflowId) -> ChainHead:
          """Return the latest chain head for `workflow_id`, or `_GENESIS_CHAIN_HEAD` if none."""

      def lock(self, workflow_id: WorkflowId) -> AbstractContextManager[None]:
          """Acquire the exclusive append lock for `workflow_id`."""

      def close(self) -> None:
          """Release substrate resources (connection pools, file handles)."""
  ```
  A static test asserts: (i) exactly five abstract methods on the Protocol; (ii) parameter and return annotations match the strings above byte-for-byte (`typing.get_type_hints`); (iii) `runtime_checkable` decorator present; (iv) Phase-3 `EventStreamSink` Protocol is NOT imported here (the two ports are deliberately distinct — see References §"Disambiguation note"). **Mutation thinking:** silently merging `append` and `lock` into a single method would let an executor ship a store that locks per-append (correct) or never locks (broken); keeping them distinct + tested separately makes the lock policy observable.
  - **Rule-of-three note (DP-A — Open/Closed at file boundary):** the file is named `checkpoints.py`, *not* `sqlite_store.py`, so Phase 9's Postgres adapter (`src/codegenie/workflows/postgres_checkpoints.py`) and any future in-memory replay-fuzzer adapter can land beside this story's `sqlite_checkpoints.py` without editing this file. The Protocol stays the kernel; adapters are the additions. Mirrors Phase-3 `EventStreamSink` (port) + `ZstdAppendingFileSink` (adapter A) + `InMemorySink` (adapter B); the third adapter (Postgres) lands additively in Phase 9.

- [ ] **AC-2 — Package-private store types (do NOT mutate `codegenie.workflows.__all__`).** This story adds three new symbols inside `codegenie.workflows`:
  - `CheckpointStore` (the Protocol, AC-1)
  - `SqliteCheckpointStore` (the production adapter, AC-5)
  - `InMemoryCheckpointStore` (the test adapter, AC-6)

  None of the three are added to `codegenie.workflows.__all__`. The Phase-6.5 bench harness consumes ONLY the four S1-01 names (`VulnRemediationCase`, `VulnRemediationResult`, `SutDigest`, `VulnRemediationSut`) plus the ten S1-02 names (the variants + `VulnLedgerState` + `LedgerStateKind` + `TransitionEvent` + `TransitionId`) — 14 names total. A test asserts `codegenie.workflows.__all__` is byte-equal to that 14-name set *after* this story lands (the S1-01 AC-12 allowlist sentinel test continues to pass unchanged; this story does not amend it). Store types are deliberately internal — Phase-6.5 must not depend on store internals (mirrors final-design.md §"Relationship to Phase 6.5" `may not depend on: checkpoint backend internals`).

  **Mutation thinking:** an executor under deadline pressure adds `CheckpointStore` to `__all__` for "API convenience"; the byte-equality test fails loud with a directive pointing at the final-design.md "may not depend on" constraint.

### Semantic-boundary catalog (the closed five-state set ADR-0003 names)

- [ ] **AC-3 — Closed `_SEMANTIC_BOUNDARY_KINDS` set + drift test.** A module-level `_SEMANTIC_BOUNDARY_KINDS: Final[frozenset[LedgerStateKind]]` declares the closed set of kinds at which a checkpoint MUST be appended:
  ```python
  _SEMANTIC_BOUNDARY_KINDS: Final[frozenset[LedgerStateKind]] = frozenset({
      "plan_ready",                # plan acceptance — final-design.md item 3 "plan acceptance"
      "patch_applied",             # patch application — item 3 "patch application"
      "gate_failed_retryable",     # gate result (retryable arm) — item 3 "gate result"
      "awaiting_human_review",     # escalation — item 3 "escalation"
      "completed",                 # terminal — item 3 "terminal completion"
      "failed_unrecoverable",      # terminal — item 3 "terminal completion"
  })
  ```
  Three tests:
  1. **Membership-byte-equality** against final-design.md §"Decisions of record" item 3: the set must be byte-equal to the six kinds listed above; adding a seventh is an ADR-0003 amendment.
  2. **Subset of `LedgerStateKind`** (S1-02 cross-story consistency): `_SEMANTIC_BOUNDARY_KINDS <= set(get_args(LedgerStateKind))` — if S1-02 ever renames a variant kind without updating this set, CI fails loud with a directive naming both files.
  3. **Boundary-includes-every-terminal** (cross-consistency with S1-02 `_TERMINAL_LEDGER_KINDS`): `_TERMINAL_LEDGER_KINDS <= _SEMANTIC_BOUNDARY_KINDS` — terminal states are always boundaries (a workflow that ends MUST have a final durable checkpoint). The complement test asserts the one non-boundary kind (`needs_plan`) is NOT in `_SEMANTIC_BOUNDARY_KINDS` (a write at `needs_plan` would be a redundant snapshot of the initial state).

  **Mutation thinking:** dropping `failed_unrecoverable` from the boundary set would let a workflow crash silently with no terminal checkpoint; test (3) catches this immediately. Adding `needs_plan` would burn writes on the initial state; the complement assertion catches that.

- [ ] **AC-4 — Boundary-only append policy (the orchestrator-side contract).** The store's `append()` accepts ONLY `TransitionEvent`s whose `next_state_id ∈ _SEMANTIC_BOUNDARY_KINDS`. A `model_validator(mode="after")` on a thin `CheckpointAppendRequest` wrapper (or `append()`'s first line, if the wrapper is rejected as premature abstraction per AC-15 Anti-refactor) raises `pydantic.ValidationError` with a directive: *"Phase-6 checkpoint policy violation. Semantic boundaries are {plan_ready, patch_applied, gate_failed_retryable, awaiting_human_review, completed, failed_unrecoverable} (ADR-0003). The orchestrator attempted to checkpoint at {next_state_id}. If this is a new boundary, amend ADR-0003 §Decision + `_SEMANTIC_BOUNDARY_KINDS`. If this is a non-boundary transition, the orchestrator should log the transition via the forensic EventLog (Phase-3 S6-01) without persisting a checkpoint row."* Test parametrizes over `LedgerStateKind \ _SEMANTIC_BOUNDARY_KINDS` (one element today: `needs_plan`) and asserts every non-boundary append is rejected with the directive substring. **Mutation thinking:** dropping the `model_validator` check lets non-boundary writes through; AC-13's between-boundary-no-write property catches the same regression from the other side.

### Production substrate (SQLite WAL adapter)

- [ ] **AC-5 — `SqliteCheckpointStore` shape + WAL + per-workflow lock.** `src/codegenie/workflows/sqlite_checkpoints.py` defines `SqliteCheckpointStore` constructed from a single directory path: `SqliteCheckpointStore(root: Path)`. On first use it creates `root / "<workflow_id>" / "checkpoints.sqlite"` per-workflow (NOT one shared file — concurrent workflows must not block each other; mirrors the per-`run-id` directory shape phase-arch-design.md §"Deployment view" names). Schema:
  ```sql
  CREATE TABLE IF NOT EXISTS checkpoint_chain (
      sequence       INTEGER PRIMARY KEY AUTOINCREMENT,
      transition_id  TEXT    NOT NULL UNIQUE,         -- ULID, AC-7 newtype from S1-02
      prior_head     TEXT    NOT NULL,                -- ChainHead "blake3:<64hex>"
      next_head      TEXT    NOT NULL,                -- ChainHead, _compute_chain_head output
      event_bytes    BLOB    NOT NULL,                -- canonical JSON, AC-12 bounded
      written_at     TEXT    NOT NULL                 -- ISO-8601 UTC, audit-only; NOT in chain
  );
  CREATE UNIQUE INDEX IF NOT EXISTS ix_chain_next_head ON checkpoint_chain(next_head);
  ```
  Connection opens with `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;`. A static test (i) asserts the schema string above is byte-equal to a golden in `tests/golden/phase6-checkpoint/sqlite_schema.sql`; (ii) asserts `journal_mode == "wal"` and `synchronous == 2` (FULL) on a constructed store; (iii) asserts `busy_timeout >= 5000`. **Mutation thinking:** `synchronous=NORMAL` would let a power-loss between commit and fsync leave a torn write — AC-11's partial-write-detection property catches the data side; this AC catches the configuration side.

  The append flow is:
  ```
  with self.lock(workflow_id):
      prior = self.tail_chain_head(workflow_id)
      next_ = _compute_chain_head(prior, event)
      conn.execute("INSERT INTO checkpoint_chain ...", (event.transition_id, prior, next_, event.model_dump_json(sort_keys=True).encode(), iso_now))
      conn.commit()
      return next_
  ```
  The clock-touching `iso_now` is the SOLE clock site in the store; it is captured into the imperative-shell store, NEVER inside `_compute_chain_head` (whose purity is enforced by S1-02 AC-8's AST fence). A separate AST test at `tests/fence/test_chain_head_purity.py` (the S1-02 fence) continues to pass after this story lands.

- [ ] **AC-6 — `InMemoryCheckpointStore` parity adapter.** `src/codegenie/workflows/in_memory_checkpoints.py` defines an in-memory adapter satisfying the `CheckpointStore` Protocol — internally a `dict[WorkflowId, list[tuple[TransitionId, ChainHead, ChainHead, bytes]]]`. A **parity contract test** at `tests/integration/test_checkpoint_store_parity.py` exercises BOTH adapters against the same property suite (AC-7, AC-8, AC-13) parametrized via `pytest.fixture(params=[InMemoryCheckpointStore, SqliteCheckpointStore])` — same inputs ⇒ same `tail_chain_head` output, same `read_all_for_workflow` byte-equal sequences, same `append()` chain-head output. The parity test is the canonical assertion that the Protocol is the contract (not the adapter); when Phase-9 adds the third (Postgres) adapter, it joins the same parametrize without editing this story's tests.

  **Mutation thinking:** an executor implements `InMemoryCheckpointStore` with a different chain-head computation (e.g., uses Python's `hash()`); the parity test fails byte-loud on the first `tail_chain_head` comparison.

### Chain-forward extension + read-all ordering (the substrate S2-02 verifies)

- [ ] **AC-7 — Chain-forward extension property (Hypothesis, Open/Closed via parametrize-over-adapters).** A Hypothesis property at `tests/property/test_checkpoint_chain_forward.py`:
  ```python
  @given(st.lists(transition_event_strategy(), min_size=1, max_size=20))
  @pytest.mark.parametrize("store_factory", [InMemoryCheckpointStore, SqliteCheckpointStore])
  def test_chain_head_after_appends_matches_recomputation(store_factory, tmp_path, events):
      store = store_factory(tmp_path)
      workflow_id = WorkflowId("wf-test")
      head = _GENESIS_CHAIN_HEAD
      for e in events:
          head = _compute_chain_head(head, e)
          store.append(e)
      assert store.tail_chain_head(workflow_id) == head
  ```
  Three sub-properties: (a) stability (`tail_chain_head` returns byte-equal output across two calls); (b) chain-forward extension (the property above); (c) cross-workflow isolation (appends to `workflow_id_A` do not change `tail_chain_head(workflow_id_B)` — drawn pairs `(workflow_id_A, workflow_id_B)` with `assume(A != B)`). **Mutation thinking:** a buggy store that swallows the `prior_head` argument and uses `_GENESIS_CHAIN_HEAD` for every append fails property (b) on the first sequence with `min_size=2`; a buggy store that shares chain heads across workflows fails property (c) immediately.

- [ ] **AC-8 — `read_all_for_workflow` returns events in monotonic append order (Hypothesis).** Property at `tests/property/test_checkpoint_read_ordering.py`:
  ```python
  @given(st.lists(transition_event_strategy(), min_size=0, max_size=20))
  @pytest.mark.parametrize("store_factory", [InMemoryCheckpointStore, SqliteCheckpointStore])
  def test_read_yields_append_order(store_factory, tmp_path, events):
      store = store_factory(tmp_path)
      for e in events:
          store.append(e)
      assert list(store.read_all_for_workflow(WorkflowId("wf-test"))) == events
  ```
  And the cross-workflow filter property: appending events for `workflow_A` and `workflow_B` interleaved, `read_all_for_workflow(workflow_A)` yields ONLY the A events in their A-append-order, never the B events. **Mutation thinking:** an executor that sorts by `transition_id` (ULID is monotonic, so it looks correct) but does NOT filter by workflow fails the cross-workflow property; an executor that reads from the `next_head` index (which is unique but not append-ordered) returns events in chain-head-string-sort order — the property catches it.

- [ ] **AC-9 — Golden ordering test (ADR-0003 §Consequences "Kill/resume tests pin checkpoint ordering").** A test at `tests/integration/test_checkpoint_golden_ordering.py` runs a fixed scripted sequence representing Phase-arch-design §Scenarios #1 (clean completion: `needs_plan → plan_ready → patch_applied → completed`) and asserts `read_all_for_workflow(workflow_id)` yields the four-event sequence in *that exact order* with chain heads recomputed against a golden at `tests/golden/phase6-checkpoint/clean_completion_chain.json`. The golden encodes the full `(transition_id, prior_head, next_head)` triple for each row; regeneration requires `PHASE6_CHECKPOINT_GOLDEN_REWRITE=1`. The test directive on failure: *"Phase-6 checkpoint ordering drift. If additive (new field on `TransitionEvent` with a default, new serialization-affecting Pydantic config), regenerate the golden under `PHASE6_CHECKPOINT_GOLDEN_REWRITE=1 pytest tests/integration/test_checkpoint_golden_ordering.py`. If breaking (re-orderable events, changed canonical-JSON shape, broken `_compute_chain_head` byte-stability), this is an ADR-0003 amendment + Phase-9 review (S5-01 Postgres adapter G5 byte-equality forward dep)."* A second scenario in the same file covers Scenario #2 (retry-then-recovery: `... → gate_failed_retryable → needs_plan → plan_ready → patch_applied → completed` — note `needs_plan` mid-sequence is a *transition target*, not a checkpoint write; the test asserts the store sees only the FIVE boundary events from this 6-transition path).

### Bounded payload + partial-write detection (the original AC-3 + the missing partial-write story)

- [ ] **AC-10 — Per-event canonical-JSON byte cap (`_MAX_EVENT_BYTES: Final[int] = 65_536`).** The store rejects any `TransitionEvent` whose `event.model_dump_json(sort_keys=True).encode()` exceeds `_MAX_EVENT_BYTES` bytes, raising `CheckpointPayloadTooLargeError` (a new typed exception in `codegenie.workflows.errors`; error_id `workflows.checkpoint_payload_too_large` per Phase-1 ADR-0007 dotted-snake-case format). Test: a hand-constructed `TransitionEvent` whose `triggering_outcome` evidence inflates to >64 KiB is rejected at `append()` with the directive: *"Phase-6 checkpoint payload exceeds the 64 KiB per-event cap (ADR-0003 §Tradeoffs `Ledger code is slightly more involved than naïve snapshots` — large evidence is referenced via blob digest, never inlined). The orchestrator should write large evidence to the blob-ref store (Phase-9 S3-05) and reference it by `BlobDigest` in the transition."* The test also asserts the cap is enforced at the store layer, not the model layer (S1-02 deliberately does NOT cap `TransitionEvent` size at the model — non-checkpointed transitions can be larger; the store is the bound).

  **Mutation thinking:** capping at the model layer would prevent the forensic EventLog (S6-01) from carrying full evidence; capping at the store layer keeps the checkpoint chain bounded without restricting the forensic log. A swap that moves the cap to S1-02 would silently break the forensic log's full-evidence capture.

- [ ] **AC-11 — Partial-write detection.** The SQLite adapter relies on `journal_mode=WAL + synchronous=FULL + COMMIT` for crash-atomicity: a row is either fully committed (visible to `read_all_for_workflow`) or not present at all. A property test at `tests/property/test_checkpoint_partial_write.py` simulates the partial-write failure mode by:
  1. Appending three events, fsync'ing, then writing a fourth raw row whose `next_head` field is set to a wrong value (chain-head tamper).
  2. Calling `tail_chain_head(workflow_id)` and asserting the returned head is the wrong (tampered) value — this is **detection-substrate-only**; the *integrity decision* belongs to S2-02. The AC's contract: `tail_chain_head` returns whatever the substrate persisted; it does NOT recompute the chain. (Recomputing is `S2-02 ReplayVerifier.verify(workflow_id) -> Literal["ok", "chain_mismatch", "torn_write"]`.)
  3. Calling `read_all_for_workflow(workflow_id)` and asserting it yields the same four rows including the tampered one (faithful read; integrity policing is S2-02). **Mutation thinking:** an executor "helpfully" adds chain recomputation inside `tail_chain_head`; the partial-write detection test catches it because the recomputed value would differ from the persisted (tampered) value. Recomputation belongs *only* in S2-02's verifier — this is the load-bearing separation between detection-substrate (this story) and integrity-policy (S2-02).

  An accompanying test asserts that a SQLite `INSERT INTO checkpoint_chain ... VALUES (..., NULL)` (NOT NULL constraint violation) raises a SQLite integrity error inside `append()`, NOT a silent skip — the orchestrator must surface the failure, never silently drop the write.

### Sanitization + clock-injection + AST fences (the structural defenses)

- [ ] **AC-12 — Canonical sanitizer is invoked, not forked.** The store's serialization path (`event.model_dump_json(sort_keys=True).encode()` → store row) MUST pass through `codegenie.output.sanitizer.sanitize_for_persistence` (a new thin wrapper around the existing canonical regex set + `RedactedSlice` smart constructor) before write. An AST test at `tests/fence/test_checkpoint_sanitizer_imports.py` walks `src/codegenie/workflows/sqlite_checkpoints.py` + `src/codegenie/workflows/in_memory_checkpoints.py` and asserts (i) `codegenie.output.sanitizer` is imported; (ii) no `re.compile`, `re.fullmatch`, `re.search`, `regex.` call appears in either file (the regex set is canonical-import-only — forking is the Phase-9 critique-report failure mode S1-01 Notes-for-implementer cited).
  An accompanying property test draws an `evidence_digest` value matching one of the canonical secret-shape patterns from `sanitizer.py` (`^(?i)(.*_)?(KEY|TOKEN|SECRET|PASSWORD|PAT|JWT|CRED)(_.*)?$`) and asserts the appended row's `event_bytes` contains the redaction sentinel, not the raw secret. **Mutation thinking:** an executor calls `event.model_dump_json()` *bypassing* the sanitizer; the secret-shape property test catches it on the first generated example.

- [ ] **AC-13 — Between-boundary no-write property + clock injection.** Two structural defenses:
  1. **Clock injection.** `SqliteCheckpointStore.__init__` accepts a `clock: Callable[[], datetime] | None = None` keyword (defaults to `lambda: datetime.now(UTC)`); the `written_at` column is captured via this clock. Tests inject `lambda: datetime(2026, 1, 1, tzinfo=UTC)` and assert deterministic `written_at` values. **Mutation thinking:** a store that calls `datetime.now()` directly cannot be deterministically tested; the golden ordering test (AC-9) would be inherently flaky.
  2. **Between-boundary no-write property.** A scripted scenario where the orchestrator emits a `needs_plan → plan_ready` transition (boundary, persisted) and then a `plan_ready → patch_applied` transition (boundary, persisted): the test asserts NO row exists for any intermediate non-boundary state and the chain has EXACTLY two rows. (Today there is no intermediate non-boundary state along this path — `needs_plan` is the only non-boundary kind — but the test pins the structural invariant so a future S1-02 amendment that adds a non-boundary kind still asserts the policy holds.)

- [ ] **AC-14 — AST `__slots__` + frozen-store fence over the adapters.** Both adapters MUST set `__slots__ = (...)` on their classes (mutable internals are explicitly enumerated; arbitrary attribute creation is a typo waiting to happen). A test at `tests/fence/test_checkpoint_adapter_slots.py` AST-walks the adapter modules and asserts every adapter class declares `__slots__`. **Mutation thinking:** without `__slots__`, an executor accidentally assigns `self._connetcion = ...` (typo); the runtime creates a new attribute and the actual `self._connection` is None on the next access — a silent NoneError much later. `__slots__` makes the typo a class-construction failure.

### Contract snapshot + typecheck (the closeout gates)

- [ ] **AC-15 — Contract snapshot extension (CI-gating).** Extend `tests/integration/test_phase6_sut_contract_snapshot.py` (the meta-test landed in S1-01 + extended in S1-02) with the `CheckpointStore` Protocol's `model_json_schema`-equivalent signature snapshot: `inspect.signature(method)` for each of the five Protocol methods + the `_SEMANTIC_BOUNDARY_KINDS` sorted membership list + `_MAX_EVENT_BYTES` value + the SQLite schema string. On failure, the directive prints: *"Phase-6 checkpoint contract drift. If additive (new optional adapter method with default behavior, new substrate adapter, new semantic boundary kind with corresponding ADR-0003 amendment), regenerate the golden under `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` AND amend ADR-0003 §Decision. If breaking (rename of a Protocol method, change of `append()` return type, removal of a semantic boundary kind, narrowing of `_MAX_EVENT_BYTES` downward, schema column rename), this is an ADR-0003 amendment + Phase-9 S5-01 (Postgres adapter) review per ADR-0003 §Consequences."* The meta-test inherits S1-01's + S1-02's additive-vs-breaking classifier; this AC adds two synthetic `CheckpointStore`-shaped deltas (one additive — new adapter method with `Protocol` `...` body; one breaking — removed semantic boundary kind) to the meta-test's case set so the classifier is exercised on store-shaped deltas, not only on SUT-result-shaped or ledger-shaped ones.

- [ ] **AC-16 — `mypy --strict` clean.** All new modules pass `make typecheck` with no `Any`, no untyped `dict`, no `# type: ignore` without a comment naming the upstream issue. The `runtime_checkable` Protocol is the load-bearing strictness check — an adapter that omits a method becomes a typecheck failure when the adapter is constructed into a `CheckpointStore`-typed slot.

- [ ] **AC-17 — Adapter parity meta-test (mutation guard for AC-6).** A meta-test at `tests/integration/test_checkpoint_store_parity_meta.py` constructs a deliberately-broken in-memory adapter that fails one of the parity invariants (e.g., returns events out-of-order from `read_all_for_workflow`), feeds it into the parity-contract test from AC-6, and asserts the parity test FAILS with a descriptive message naming the violated invariant. **Mutation thinking:** the parity test is itself susceptible to mutation (a `==` swap, a missing `.read_all_for_workflow()` call); the meta-test makes the parity test mutation-resistant. This closes the exact gap S6-06 (Phase-3) flagged as "false-positive additive is the scariest failure mode," applied here to contract conformance.

## Files to touch

- `src/codegenie/workflows/checkpoints.py` (new) — `CheckpointStore` Protocol + `_SEMANTIC_BOUNDARY_KINDS` + `_MAX_EVENT_BYTES` + `_GENESIS_CHAIN_HEAD` re-export.
- `src/codegenie/workflows/sqlite_checkpoints.py` (new) — `SqliteCheckpointStore` adapter (production).
- `src/codegenie/workflows/in_memory_checkpoints.py` (new) — `InMemoryCheckpointStore` adapter (tests).
- `src/codegenie/workflows/errors.py` (new or extend if S1-01 / S1-02 landed it) — `CheckpointPayloadTooLargeError` + `error_id = "workflows.checkpoint_payload_too_large"`.
- `src/codegenie/output/sanitizer.py` (modify — add `sanitize_for_persistence(payload: bytes) -> bytes` thin wrapper if not already present; do NOT fork the regex set).
- `tests/unit/workflows/test_checkpoint_store_protocol.py` (new) — AC-1 five-method shape + `runtime_checkable` + annotation byte-equality.
- `tests/unit/workflows/test_semantic_boundary_set.py` (new) — AC-3 membership + AC-4 boundary-only append rejection.
- `tests/unit/workflows/test_checkpoint_sqlite_schema.py` (new) — AC-5 schema golden + WAL/sync pragmas.
- `tests/property/test_checkpoint_chain_forward.py` (new) — AC-7 stability + chain-forward + cross-workflow isolation (parametrized over both adapters).
- `tests/property/test_checkpoint_read_ordering.py` (new) — AC-8 append-order + cross-workflow filter (parametrized).
- `tests/property/test_checkpoint_partial_write.py` (new) — AC-11 detection-substrate-only contract.
- `tests/integration/test_checkpoint_golden_ordering.py` (new) — AC-9 clean-completion + retry-recovery scenarios + golden chain.
- `tests/integration/test_checkpoint_store_parity.py` (new) — AC-6 parametrize over both adapters.
- `tests/integration/test_checkpoint_store_parity_meta.py` (new) — AC-17 meta-test (broken adapter → parity test fails).
- `tests/fence/test_checkpoint_sanitizer_imports.py` (new) — AC-12 sanitizer-import + no-regex-locally fence.
- `tests/fence/test_checkpoint_adapter_slots.py` (new) — AC-14 `__slots__` AST fence.
- `tests/integration/test_phase6_sut_contract_snapshot.py` (modify — extend per AC-15) + `..._meta.py` (modify — add two synthetic checkpoint-shaped deltas).
- `tests/golden/phase6-checkpoint/sqlite_schema.sql` (new) — AC-5 schema byte-golden.
- `tests/golden/phase6-checkpoint/clean_completion_chain.json` (new) — AC-9 chain-head golden.
- `tests/golden/phase6-contract/snapshot.json` (modify — regenerate under `PHASE6_CONTRACT_GOLDEN_REWRITE=1` after AC-15 implementation).
- `tests/unit/types/test_identifiers_phase3.py` (or Phase-6 sibling) — no new newtype to register (the store reuses `WorkflowId`, `TransitionId` from S1-02, `ChainHead` from Phase-4, `BlobDigest` from Phase-2); no drift-test edit required.

## TDD plan

**Red.** Land in this order — every step writes a failing test first, then asserts the failure mode is meaningful (the error message + the directive substring, not just the exception class) before writing any production code:

1. AC-1 five-method Protocol shape test (fails: module doesn't exist; asserts `runtime_checkable` + annotation byte-equality).
2. AC-3 `_SEMANTIC_BOUNDARY_KINDS` membership + subset + boundary-includes-terminals tests (fails: constant doesn't exist; verifies the byte-equal six-element set).
3. AC-4 boundary-only append rejection test (fails: rejection logic absent; verifies the directive substring).
4. AC-10 payload-too-large rejection test (fails: typed exception + cap absent; verifies the directive substring + the 64 KiB threshold).
5. AC-5 schema golden + WAL/sync pragma test (fails: SQLite store doesn't exist; the schema byte-equality drives the schema string).
6. AC-6 + AC-8 read-order + cross-workflow filter property tests, parametrized over both adapters (fails: adapters don't exist).
7. AC-7 chain-forward extension property + stability + cross-workflow isolation, parametrized (fails: chain logic absent; the cross-workflow isolation sub-property is the load-bearing mutation guard).
8. AC-9 golden ordering test for Scenario #1 (clean completion) + Scenario #2 (retry-recovery) (fails: golden absent; first-run regeneration via `PHASE6_CHECKPOINT_GOLDEN_REWRITE=1`).
9. AC-11 partial-write detection-substrate test (fails: detection contract absent; the load-bearing assertion is "tail_chain_head does NOT recompute; recomputation belongs to S2-02").
10. AC-12 sanitizer-import AST fence + secret-shape property test (fails: sanitizer call absent).
11. AC-13 clock-injection determinism + between-boundary no-write tests (fails: clock injection absent).
12. AC-14 `__slots__` AST fence (fails: adapters declare no `__slots__`).
13. AC-17 parity-meta test (broken adapter → parity test fails) (fails: parity-meta-test absent; this AC is the mutation guard for AC-6).
14. AC-15 contract snapshot extension test + meta-test additive/breaking case set (fails: extension absent; first-run regeneration via `PHASE6_CONTRACT_GOLDEN_REWRITE=1`).
15. AC-16 `make typecheck` (the final gate).
16. AC-2 `__all__` byte-equality test (fails LOUD if the executor adds any store type to `__all__` — asserts the 14-name set is unchanged from S1-01 + S1-02).

**Green.** Implement the minimum that makes all red tests pass:

- Add `CheckpointPayloadTooLargeError` in `codegenie.workflows.errors` (a single-line class + the `error_id` Final constant).
- Implement `checkpoints.py`: the `CheckpointStore` Protocol (Protocol body is `...` — five method stubs), the `_SEMANTIC_BOUNDARY_KINDS` frozenset, the `_MAX_EVENT_BYTES` constant, the `_GENESIS_CHAIN_HEAD` re-export, the boundary-policy check helper that AC-4 invokes (`_assert_boundary(event: TransitionEvent) -> None`).
- Implement `sqlite_checkpoints.py`: the schema (must byte-match the golden — paste once); `__init__(root, *, clock=None)`; `_connection_for(workflow_id)` helper; `lock(workflow_id)` via `fcntl.flock` over the per-workflow `.lock` file beside the SQLite (cross-process safety); `append(event)` body following the AC-5 flow; `read_all_for_workflow(workflow_id)` body via `SELECT event_bytes FROM checkpoint_chain WHERE ... ORDER BY sequence ASC` + `TransitionEvent.model_validate_json(row)`; `tail_chain_head(workflow_id)` via `SELECT next_head FROM checkpoint_chain WHERE ... ORDER BY sequence DESC LIMIT 1`; `close()`.
- Implement `in_memory_checkpoints.py`: same shape over a `dict[WorkflowId, list[...]]` substrate; `lock()` is a no-op context manager (single-process test substrate — cross-process safety is exercised against the SQLite store; mirrors `InMemorySink`'s `lock()` pattern from Phase-3 events.py).
- Add `sanitize_for_persistence(payload: bytes) -> bytes` to `codegenie.output.sanitizer` as a single-line wrapper over the existing regex set (one canonical declaration; AC-12 enforces the import).
- Generate goldens via `PHASE6_CHECKPOINT_GOLDEN_REWRITE=1 PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_checkpoint_golden_ordering.py tests/integration/test_phase6_sut_contract_snapshot.py` and commit them.

**Refactor.** Cleanup only — no new behaviour. Specifically:

- Confirm `_GENESIS_CHAIN_HEAD` is the literal `ChainHead("blake3:" + "0" * 64)` (or re-exported from Phase-3 events.py if a single canonical declaration already exists; the AC-12 sanitizer fence's "no fork" principle applies here too — pick one site, document the choice in a one-line comment).
- Confirm `_SEMANTIC_BOUNDARY_KINDS` and `_MAX_EVENT_BYTES` are `Final` and at module level (constants, not class-level attributes — mirrors the `_TERMINAL_LEDGER_KINDS` and `_LEGAL_TRANSITIONS` pattern from S1-02).
- Confirm the SQLite schema string and the `tests/golden/phase6-checkpoint/sqlite_schema.sql` file are textually identical (the AC-5 golden test enforces; cleanup confirms no trailing-whitespace drift).
- Confirm `__slots__` enumerates every instance attribute on both adapters (the AC-14 fence enforces; cleanup confirms no `_initialised` flag was left out).

**Anti-refactor (Rule 2 + Open/Closed + composition-over-inheritance).** Do NOT introduce any of the following in this story:

1. **A `BaseCheckpointStore` ABC or `CheckpointStoreMixin`.** The original story's Refactor step ("share canonical serialization helpers") is a *premature DRY* anti-pattern AND an inheritance violation. The Phase-3 precedent (`EventStreamSink` + two adapters) deliberately rejects this: the two adapters share NOTHING via inheritance; they share the *Protocol* (port). If `SqliteCheckpointStore` and `InMemoryCheckpointStore` end up duplicating the canonical-JSON-bytes computation, the right move is to extract a *free function* `_canonical_event_bytes(event: TransitionEvent) -> bytes` in `checkpoints.py` and call it from both adapters — composition via function call, not inheritance.
2. **A `CheckpointStoreRegistry` or `@register_checkpoint_store(SubstrateKind)` decorator.** Today there are two adapters (SQLite + InMemory); Phase-9 adds a third (Postgres). The rule-of-three threshold for a registry is reached at *that* point, not this one — and the registry would be earned by a *dispatch* requirement that does not exist today (the orchestrator injects a `CheckpointStore`-typed parameter; selecting by string-key is not required). Surfacing the opportunity is a Notes-for-implementer concern.
3. **A `CheckpointTransaction` context manager that wraps both the boundary check + the chain extension + the row insert.** This would be a Command-pattern over-design when the body is six lines of imperative-shell SQL. Three similar lines is better than premature abstraction.
4. **A `SemanticBoundaryStrategy` Strategy-pattern abstraction.** The boundary catalog is a closed `frozenset`; Strategy is for *open* dispatch over varying behaviors. Phase-7 (migration task class) will have its OWN ledger sum type and its OWN boundary catalog — but those are different *constants* in a different *file* (`migration_checkpoints.py` beside `sqlite_checkpoints.py`), not a runtime-dispatched strategy.
5. **A `CheckpointAppendRequest` wrapper Pydantic model around `TransitionEvent`.** Tempting because AC-4's boundary check has a natural validator-shape, but introducing a wrapper for one extra field of metadata is the primitive-obsession-in-reverse anti-pattern; put the boundary check inside `append()`'s first line and emit the directive from there.
6. **A `clock` Protocol with `now() -> datetime`.** AC-13 names a `Callable[[], datetime]` — that IS the clock Protocol's runtime shape, expressed without ceremony. A separate Protocol earns its keep when there are 3+ clock implementations with side-effecting initialization; today there are two (real + test-injected).
7. **An async `append()` / `read_all_for_workflow()` on the Protocol.** The orchestrator wraps SQLite calls in `asyncio.to_thread` (mirrors the Phase-3 `EventLog.emit_spanning` pattern). Async-by-default in the store leaks the substrate choice (SQLite is sync; Postgres async drivers exist but the orchestrator is the seam, not the store).

## Out of scope

- The replay verifier (Phase-6 S2-02) — consumes `tail_chain_head` + `read_all_for_workflow` to assert chain integrity, decides `FailedUnrecoverable(reason="checkpoint_integrity")`, and rejects partial-final-write hydrates. This story ships ONLY the detection-substrate primitives S2-02 calls; the integrity policy itself is owned by S2-02.
- The LangGraph subgraph nodes that EMIT `TransitionEvent`s through the conditional edges (Phase-6 S3-01) — consumers of `append()`, not its definers.
- The HITL resume validator (Phase-6 S4-01) — reads the chain head + the latest `awaiting_human_review` row from this store; does NOT modify it.
- The SUT adapter `LocalVulnRemediationSut` (Phase-6 S5-01) — constructs a `SqliteCheckpointStore` injection and threads it to the subgraph.
- The Postgres adapter (Phase-9 S5-01) — third adapter behind the same Protocol; lands additively per the AC-1 rule-of-three note.
- The forensic two-stream `EventLog` (Phase-3 S6-01) — orthogonal substrate; AC-1 (iv) forbids importing `EventStreamSink` from this module.
- A `BaseCheckpointStore` / `CheckpointStoreMixin` ABC — see Anti-refactor #1.
- A `CheckpointStoreRegistry` — see Anti-refactor #2.
- A second concrete production substrate (e.g., a JSONL-on-disk store) — Phase-9 Postgres is the canonical "second production substrate"; introducing a third in Phase-6 violates Rule 2.

## Notes for the implementer

- **Why the five-method Protocol shape matters.** ADR-0001 + ADR-0003 + final-design.md commit Phases 6 / 6.5 / 9 to a store-substrate that is *injectable* (constructor dependency, not module-level singleton). Phase 9's Postgres adapter swap is a single-line constructor change in the orchestrator — not a kernel edit, not an `if backend == "sqlite"` branch. The Protocol is the kernel; adapters are additions. **If you find yourself wanting to add a sixth Protocol method to `CheckpointStore`, stop and ask: would the Postgres adapter implement it the same way the SQLite adapter does?** If yes, it's likely a free function on `checkpoints.py`. If no, it's a sign the Protocol should split (e.g., a `ReadOnlyCheckpointStore` Protocol for the verifier S2-02).

- **Why the `EventLog` and `CheckpointStore` are deliberately separate.** S1-02's validation cited the `EventId` vs `TransitionId` disambiguation; this story extends the same discipline to the *storage* layer. The forensic `EventLog` records "what happened" (workflow lifecycle, capability mints, provenance gates) for offline forensics and cross-workflow audit; the `CheckpointStore` records "what state transitions were durably observed" for the specific purpose of replay-safe resume. They have different durability requirements (`EventLog` is append-mostly with FSync-on-flush; `CheckpointStore` is append-and-fsync-per-row), different read patterns (`EventLog` is whole-stream replay for forensics; `CheckpointStore` is per-workflow tail-walk for resume), and different consumers (`EventLog` is read by audit tools; `CheckpointStore` is read by S2-02's verifier + S5-01's adapter). Conflating them would couple the replay path to the forensic path and force the Phase-9 Postgres migration to dual-implement. Two ports, two adapter pairs, no shared base.

- **Why payload-cap lives at the store layer, not the model layer.** The forensic EventLog captures full evidence (a large RAG-retrieved cassette dump might exceed 100 KiB); the checkpoint chain captures only what's needed for replay (a `BlobDigest` referencing the full evidence). Capping `TransitionEvent` at the model layer would break the forensic log; capping at the store layer keeps the chain compact without restricting forensic capture. The 64 KiB number is conservative — typical events are <2 KiB (six string fields plus a few digests); 64 KiB is "something is wrong" not "tight bound." The cap exists to surface accidental evidence inlining (e.g., a node that stores a full RAG-retrieved cassette as the `triggering_outcome` rather than a `BlobDigest` reference).

- **Why per-workflow SQLite files (not one shared file).** Three reasons: (i) concurrent workflows must not block each other on the WAL write lock (one shared file would serialize unrelated workflows); (ii) per-workflow files match the `.codegenie/remediation/<run-id>/` directory shape phase-arch-design.md §"Deployment view" already names; (iii) cleanup is trivial — removing one workflow's data is `rm -rf .codegenie/remediation/<run-id>/`, not a transactional DELETE that the WAL must replay. The trade-off is a per-workflow connection cost; a `LRU(max=64)` connection cache lives in `_connection_for(workflow_id)` to amortize.

- **Why detection-substrate-only (AC-11) is load-bearing.** ADR-0003's "verify the previous chain head before hydration on resume" is the *integrity policy*; this story's `tail_chain_head` is the *primitive* the policy reads. If `tail_chain_head` silently recomputes the chain, two failure modes become indistinguishable: (a) "the persisted chain head matches what we recomputed" (replay-safe) vs (b) "the persisted chain head is wrong but `tail_chain_head` reported what the chain should have been, so the verifier thinks it's fine." Keeping detection and policy separate makes the verifier (S2-02) the SOLE site of integrity decision; this story is the SOLE site of substrate fidelity. The AC-11 test is the structural defense that catches the "helpful recomputation" mutation.

- **Why the parity contract test (AC-6) parametrizes over the adapter factory, not the adapter instance.** Substrates have different setup costs (SQLite needs a `tmp_path`-rooted directory; in-memory needs nothing). A `pytest.fixture(params=[factory_a, factory_b])` lets each property invocation construct a fresh adapter without leaking state across properties. When Phase 9 adds the Postgres adapter, it joins the same `params` list — one line of test diff, no copy-paste of every property test. This is the rule-of-three precedent that EARNS the `CheckpointStoreRegistry` Phase 9 will land (the *third* concrete user is what justifies the registry; the test infrastructure is the proof-by-example that the Protocol is the kernel).

- **Why `__slots__` (AC-14) on the adapters.** Two reasons: (i) typo defense (a typo'd attribute assignment creates a silent shadow attribute on a default class; on a `__slots__` class it's an `AttributeError` at construction time); (ii) memory discipline (the `_connection_cache` LRU on `SqliteCheckpointStore` is the only mutable attribute; an executor that adds `self._stats: dict = {}` for "ad-hoc telemetry" needs to amend `__slots__`, which forces them to surface the addition in a PR review).

- **Why the contract snapshot extension (AC-15) is non-negotiable.** S1-01 + S1-02 established the contract-snapshot meta-test as the canonical structural-drift defense; this story extends it to the *store* layer. A future executor of S2-02 / S5-01 might "helpfully" widen `append()` to accept a `dict` (for "convenience"); the contract snapshot fails byte-loud with the additive-vs-breaking directive. The meta-test extension (two synthetic store-shaped deltas) closes the exact mutation gap S6-06 (Phase-3) singled out: "a `==` swapped for `!=` in the classifier silently lets breaking changes through." Land the meta-test extension in Red, not Refactor.

- **Phase-7 migration checkpoints — file naming is the Open/Closed substrate.** Today there is one ledger (`vuln_ledger.py`) and one store family (`{sqlite,in_memory}_checkpoints.py`). Phase 7 will add `migration_ledger.py` for the distroless-migration task class AND `migration_checkpoints.py` for its store; the two task classes will share `CheckpointStore` (the Protocol) but NOT the boundary catalog (different state machines have different semantic boundaries). Open/Closed at the file boundary: this story freezes the Protocol; Phase 7 lands a sibling `_SEMANTIC_BOUNDARY_KINDS_MIGRATION` constant without editing this file. The day Phase 8+ adds the THIRD task class, the rule-of-three threshold is reached and a `BoundaryKindsCatalog` registry is the additive next step.

- **Phase-9 Postgres swap — what stays the same.** The Phase-9 Postgres adapter implements `CheckpointStore` (this story's Protocol) byte-equivalently: same `append() -> ChainHead` return type, same `read_all_for_workflow()` iteration order, same `tail_chain_head()` raw-persisted return (NOT recomputed). The adapter swap is a *constructor injection* in the orchestrator — `LocalVulnRemediationSut(checkpoint_store=PostgresCheckpointStore(...))` vs the current `SqliteCheckpointStore(...)`. The parity contract test (AC-6) gains a third adapter in its `params` list; nothing else changes. This is the proof that the Open/Closed substrate this story freezes is real: a 100-line Postgres adapter + one parametrize-row addition is the entire migration.
