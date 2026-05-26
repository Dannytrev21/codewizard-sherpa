# S2-02 — Replay verification

**Status:** GREEN
**Validated:** 2026-05-25 — see [`_validation/S2-02-replay-verification.md`](_validation/S2-02-replay-verification.md).
**Shipped:** 2026-05-25 — see [`_attempts/S2-02-replay-verification.md`](_attempts/S2-02-replay-verification.md). 15/15 ACs satisfied with runtime evidence; 50 new tests + 1 amended S2-01 protocol-shape test (sixth additive Protocol method `iter_persisted_chain`); mypy --strict + ruff + import-linter clean. Required a small S2-01 substrate change (chain head folded over sanitized-reconstructed event, not live event) so the verifier can reproduce the rolling head from persisted bytes — addresses the exact "sanitization design point surfaced for downstream review" in the S2-01 attempt log.
**Depends on:** [`S2-01-semantic-checkpoints.md`](S2-01-semantic-checkpoints.md) — consumes the `CheckpointStore` Protocol, `_GENESIS_CHAIN_HEAD`, `_canonical_event_bytes`, and `sanitize_for_persistence`; [`S1-02-ledger-state-union.md`](S1-02-ledger-state-union.md) — consumes the `_compute_chain_head` pure helper, `TransitionEvent`, `LedgerStateKind`, `FailedUnrecoverable`, `FailedUnrecoverableReason` (the closed reason set already pins `"checkpoint_integrity"`), and `_LEGAL_TRANSITIONS`; [`S1-01-sut-contract-types.md`](S1-01-sut-contract-types.md) — the `codegenie.workflows.__all__` allowlist sentinel (AC-2 keeps it unchanged).

**Goal:** Land the **`ReplayVerifier`** substrate — a pure-core fold + a thin imperative-shell entry point — that consumes the `CheckpointStore` substrate (S2-01), recomputes the BLAKE3 chain over the persisted sequence using the canonical write-path discipline (sanitize-then-fold), classifies the verdict as a closed-set tagged union (`Verified | ChainMismatch | TornWrite | EmptyWorkflow`), and a higher-level **`hydrate_or_fail`** gate that maps every non-`Verified` verdict to `FailedUnrecoverable(reason="checkpoint_integrity")` and refuses to hydrate any in-memory ledger state until verification passes — so the subgraph nodes (S3-01), the HITL resume validator (S4-01), and the SUT adapter (S5-01) can dispatch on a frozen "is the chain safe to replay?" decision without each re-deriving the policy.

This is the **second half** of `High-level-impl.md §"Step 2 — Replay-safe checkpoint store"` ("Verify prior chain head before hydrate"). S2-01 shipped the *detection substrate* (`tail_chain_head` returns whatever the store persisted, never recomputed); this story ships the *integrity policy* (the verifier recomputes the chain and rejects mismatches) and the *fail-closed hydration gate* that wires the policy to ADR-0003's `FailedUnrecoverable(reason="checkpoint_integrity")` decision. The detection/policy separation pinned by S2-01 AC-11 is the load-bearing invariant this story consumes — the verifier MUST recompute (because the store does not), and the store MUST NOT recompute (because the verifier does).

## References

- [final-design.md](../final-design.md) §"Main workflow" step 2 ("Build or resume `VulnLedger`" — the entry point this story owns the resume half of), §"Decisions of record" item 3 ("Resume verifies the prior chain head before replay" — the exact ADR-0003 second half this story implements).
- [phase-arch-design.md](../phase-arch-design.md) §"Logical view" (the `LEDGER["VulnLedger + checkpoint store"]` node — this story builds the *replay-verify-before-hydrate* glue), §"Process view" sequence "G->>L: verify + hydrate" (the orchestrator-side call shape `hydrate_or_fail` accepts), §"Scenarios" #4 (tampered checkpoint — the canonical AC-9 golden scenario; "graph returns `FailedUnrecoverable(reason='checkpoint_integrity')`, no patch work resumes"), §"Failure modes" row 1 ("checkpoint chain mismatch | replay verification | fail closed before work resumes" — the verbatim integrity-policy contract this story implements).
- [ADRs/0003-checkpointed-ledger-replay-boundary.md](../ADRs/0003-checkpointed-ledger-replay-boundary.md) §Decision ("verify the previous chain head before hydration on resume" — verbatim) + §Tradeoffs ("Tamper or partial writes fail closed before new work starts" — the AC-8 + AC-9 contract) + §Consequences ("Failed verification transitions to `FailedUnrecoverable`" — owned by this story via `hydrate_or_fail`; "Kill/resume tests pin checkpoint ordering" — S2-01 owns the substrate ordering, this story owns the resume-side verification of that ordering).
- [High-level-impl.md](../High-level-impl.md) §"Step 2 — Replay-safe checkpoint store" (this story is the second bullet — "Verify prior chain head before hydrate" + the third bullet — "Add tamper and resume golden tests"). Step 6 ("Kill/resume fixture", "Clean completion fixture", "Retry-then-recover fixture") consumes `hydrate_or_fail` but is owned by S6-01.
- [S2-01-semantic-checkpoints.md](S2-01-semantic-checkpoints.md) + [_validation/S2-01-semantic-checkpoints.md](_validation/S2-01-semantic-checkpoints.md) + [_attempts/S2-01-semantic-checkpoints.md](_attempts/S2-01-semantic-checkpoints.md) — `CheckpointStore` Protocol (the five-method substrate), `_GENESIS_CHAIN_HEAD` (the seed for the empty-workflow verdict), `_canonical_event_bytes` + `sanitize_for_persistence` (the write-path discipline this story's fold mirrors), the AC-11 detection-substrate-only contract (load-bearing — this story is the SOLE site that recomputes), the AC-15 contract-snapshot meta-test (this story extends it with the verifier's tagged-union shape), and the S2-01 attempt log's "Sanitization design point — surfaced for downstream review" entry (the verifier MUST mirror the write path: sanitize-then-fold; recommended approach `(i)`).
- [S1-02-ledger-state-union.md](S1-02-ledger-state-union.md) — `_compute_chain_head` (the pure helper this story's fold dispatches through), `TransitionEvent` (the event the verifier round-trips through `model_validate_json` after reading the persisted bytes), `FailedUnrecoverable` + `FailedUnrecoverableReason` (the typed return — `"checkpoint_integrity"` is already in the closed set, no new reason needed), the AST no-side-effects fence on `_chain.py` (this story's pure-core fold helper inherits the fence — no `time`, `os.environ`, `datetime.now`, `random` in `_replay.py`).
- [S1-01-sut-contract-types.md](S1-01-sut-contract-types.md) — the `codegenie.workflows.__all__` allowlist sentinel; AC-2 of this story asserts the 14-name set is **byte-equal-unchanged** after this story lands (the verifier types are package-private).
- [S3-01-plugin-local-subgraph.md](S3-01-plugin-local-subgraph.md) — downstream consumer; the subgraph's "verify + hydrate" entry edge calls `hydrate_or_fail(store, workflow_id)`. The verifier API shape is constrained by that call site.
- [S4-01-hitl-interrupt-and-resume.md](S4-01-hitl-interrupt-and-resume.md) — downstream consumer; the HITL resume validator reads the verifier's `Verified.events` to find the latest `awaiting_human_review` row.
- [S5-01-stable-sut-adapter.md](S5-01-stable-sut-adapter.md) — downstream consumer; `LocalVulnRemediationSut.run_case` constructs the `SqliteCheckpointStore` and dispatches the resume path through `hydrate_or_fail`.
- Phase-3 forward reuse: [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) — `RemediationError` (consumed by `FailedUnrecoverable.error`; this story constructs one with a typed `error_id` per Phase-1 ADR-0007 dotted-snake-case format).

## Acceptance criteria

### Replay verdict (the closed tagged union)

- [ ] **AC-1 — `ReplayVerdict` is a closed four-variant discriminated union** with the same `Annotated[..., Field(discriminator="kind")]` shape S1-02 uses for `VulnLedgerState` (mirror the canonical project precedent — `codegenie/transforms/outcomes.py`, `indices/freshness.py`, `fallback/plan_outcome.py`):
  ```python
  class Verified(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["verified"] = "verified"
      tail_chain_head: ChainHead              # the recomputed head (== persisted)
      events: tuple[TransitionEvent, ...]     # frozen sequence, append order

  class ChainMismatch(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["chain_mismatch"] = "chain_mismatch"
      persisted_tail: ChainHead               # what tail_chain_head returned
      recomputed_tail: ChainHead              # what the verifier folded
      divergence_index: int                   # 0-based first row where folded != persisted
      offending_transition_id: TransitionId   # the row at divergence_index

  class TornWrite(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["torn_write"] = "torn_write"
      reason: Literal["unparseable_event", "null_event_bytes", "duplicate_chain_link"]
      offending_sequence: int                 # SQLite sequence column value

  class EmptyWorkflow(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["empty_workflow"] = "empty_workflow"
      genesis_chain_head: ChainHead           # always == _GENESIS_CHAIN_HEAD

  ReplayVerdict = Annotated[
      Verified | ChainMismatch | TornWrite | EmptyWorkflow,
      Field(discriminator="kind"),
  ]
  ```
  A static test asserts: (i) all four variants are `_FROZEN_FORBID` (the canonical config — never inlined); (ii) the `kind` literal of each variant is byte-equal to the four slugs above; (iii) the union has exactly four members via `typing.get_args` (no silent fifth variant); (iv) `ChainMismatch.divergence_index` is `>= 0` validated by a Pydantic `Field(ge=0)`; (v) `TornWrite.reason` is exactly the three-element closed Literal above. **Mutation thinking:** removing the `divergence_index` field would let a buggy verifier "report mismatch" without locating which row — downstream tests would not be able to assert the offending transition is the one we tampered with. Removing `tornwrite.reason` would let a verifier conflate "the bytes were null" with "the JSON was malformed" — different recovery stories. Both regressions die on AC-9 + AC-10.

  - **Rule-of-three note (DP-A — Open/Closed at the variant boundary):** four variants today; if Phase 9 (Postgres) needs a fifth verdict (e.g., `BackendUnavailable` — the connection failed before fold), that lands additively in this file with a corresponding `_LEGAL_VERDICT_TO_INTEGRITY` row in `_replay.py`'s sum-type-exhaustiveness gate (AC-7). Adding a fifth variant is an ADR-0003 amendment.

### The pure verifier core (functional core / imperative shell)

- [ ] **AC-2 — `codegenie.workflows.__all__` is byte-equal-unchanged after this story lands.** This story adds three or four new symbols inside `codegenie.workflows` (`ReplayVerdict`, `Verified`, `ChainMismatch`, `TornWrite`, `EmptyWorkflow`, plus the `ReplayVerifier` class and the `hydrate_or_fail` function) — **none of them** are added to `codegenie.workflows.__all__`. The Phase-6.5 bench harness consumes ONLY the 14 S1-01 + S1-02 names; verifier types are package-private. A test asserts the `__all__` allowlist sentinel (`tests/fence/test_workflows_public_surface.py`) is unchanged byte-equal after this story. **Mutation thinking:** an executor adds `ReplayVerifier` to `__all__` for "API convenience"; the byte-equality test fails LOUD with a directive pointing at final-design.md §"Relationship to Phase 6.5" `may not depend on: checkpoint backend internals`. The verifier is a *backend internal* — consumers depend on the `VulnRemediationSut` contract, not on the verifier directly.

- [ ] **AC-3 — Pure-core fold helper `_replay_fold` lives in `src/codegenie/workflows/_replay.py` and has zero side effects.** Signature:
  ```python
  def _replay_fold(
      events: Iterable[TransitionEvent],
      *,
      genesis: ChainHead = _GENESIS_CHAIN_HEAD,
  ) -> ChainHead:
      """Pure functional core: fold _compute_chain_head over `events`.

      The fold mirrors the WRITE PATH exactly: sanitize the canonical
      event bytes (sanitize_for_persistence) BEFORE computing the chain
      head — except the chain head itself is computed against the LIVE
      event, just like _compute_chain_head's contract. The verifier's
      fold therefore reproduces the write-path bytes byte-for-byte, so
      a sanitization that triggered on write is a benign no-op on
      verify, NOT a chain mismatch.
      """
  ```
  The AST no-side-effects fence at `tests/fence/test_chain_head_purity.py` extends to walk `_replay.py` and refuse names like `open`, `socket`, `time.time`, `datetime.now`, `random`, `uuid`, `os.environ`, `Path(...).read_*`, `sqlite3`, `fcntl` — the moment any later story tries to widen the verifier-core with impurity, CI fails loud. (Reuse the existing fence — add `_replay.py` to its module-list constant, do NOT fork a new fence test file.) **Mutation thinking:** a `time.time()` call inside the fold would make the verifier flaky on slow CI; a `sqlite3` import would re-couple the pure core to the SQLite-specific substrate, breaking the Phase-9 Postgres parity. The fence is the structural defense.

  - **Sanitization-aware fold (the load-bearing invariant the S2-01 attempt log surfaced).** The S2-01 attempt log explicitly noted: "The chain head is computed over the *live* event (which can contain cleartext), while the on-disk row is the *sanitized* bytes. On replay, S2-02 will recompute the chain over the persisted (sanitized) bytes, which would NOT match the persisted chain head if sanitization triggered." The recommended fix is `(i)`: mirror the write path. The fold therefore: (a) reads the persisted byte row; (b) round-trips through `TransitionEvent.model_validate_json(row)` to reconstruct the LIVE event shape (Pydantic field validators run; cleartext that was redacted on the wire is still redacted in memory — the redaction is in the bytes, not in the type); (c) calls `_compute_chain_head(prior_head, event)` using the *reconstructed* event; (d) returns the rolling head. The chain-head bytes will be byte-equal to the write-path bytes IFF the sanitization is idempotent (which it is — a redaction sentinel cannot match a secret pattern). A test at `tests/unit/workflows/test_replay_sanitization_aware.py` constructs a `TransitionEvent` whose `triggering_outcome` contains a secret-shaped string (e.g., `"sk-ant-" + "x" * 50`), appends it via the store, calls `verify()`, and asserts the verdict is `Verified` — NOT `ChainMismatch`. **Mutation thinking:** a verifier that re-parses the bytes WITHOUT re-canonicalizing (e.g., uses `json.loads` + Python's `repr`) would compute a different rolling head — the test catches this.

### The `ReplayVerifier` class (the imperative shell)

- [ ] **AC-4 — `ReplayVerifier` is a single thin class in `src/codegenie/workflows/replay.py`** with `__slots__` and constructor injection of the `CheckpointStore`:
  ```python
  class ReplayVerifier:
      __slots__ = ("_store",)

      def __init__(self, store: CheckpointStore) -> None:
          self._store = store

      def verify(self, workflow_id: WorkflowId) -> ReplayVerdict:
          """Recompute the chain over the persisted sequence; classify the verdict."""
  ```
  A test at `tests/fence/test_checkpoint_adapter_slots.py` (extend the existing S2-01 fence — do NOT fork) asserts `ReplayVerifier` declares `__slots__` containing exactly `("_store",)`. **Mutation thinking:** without `__slots__`, an executor adds `self._cache: dict = {}` for ad-hoc memoization — but caching verification results across `verify()` calls is dangerous (the underlying chain can be re-tampered between calls). `__slots__` makes that addition surface in PR review.
  - **Anti-refactor #1:** no `BaseReplayVerifier` ABC, no `VerifierMixin`. Single class today; rule-of-three threshold reached if and only if Phase-9 (Postgres) lands a second concrete verifier that materially differs (it should not — the verifier is substrate-agnostic; it dispatches through the Protocol).
  - **Anti-refactor #2:** no `VerifierStrategy` Strategy abstraction over different chain-folding policies. The fold is the *one* canonical policy (sanitize-then-fold); a "loose" fold for tests would silently mask the load-bearing AC-3 invariant.
  - **Anti-refactor #3:** no `verify` returning a bare `bool` or a 2-tuple `(verdict_kind, payload)`. The tagged union IS the return type; primitive-obsession-in-reverse (Anti-refactor #5 from S2-01) applies.

- [ ] **AC-5 — `verify()` classification matrix is exhaustive over the verdict union.** A unit test at `tests/unit/workflows/test_replay_verify_classifications.py` constructs five scenarios and asserts the verdict for each:
  1. **Empty workflow** (zero appended rows) → `EmptyWorkflow(genesis_chain_head=_GENESIS_CHAIN_HEAD)`.
  2. **Legitimate sequence** (three boundary appends, no tamper) → `Verified(tail_chain_head=fold(events), events=tuple(events))`.
  3. **Tampered tail `next_head`** (the AC-11 S2-01 raw-SQLite tamper on the LAST row) → `ChainMismatch(persisted_tail=tampered, recomputed_tail=fold(events), divergence_index=2, offending_transition_id=events[2].transition_id)`.
  4. **Tampered middle `next_head`** (raw-SQLite tamper on row index 1 of 3) → `ChainMismatch(divergence_index=1)`. The divergence_index MUST be the FIRST row where folded != persisted (not the last) — a buggy verifier that walks back-to-front and reports the last divergence would surface as `divergence_index=2` here; the test catches the regression.
  5. **Tampered event bytes** (raw-SQLite UPDATE of `event_bytes` to a different valid JSON whose chain-head over the same prior produces a different head) → `ChainMismatch` at the tampered row.
  - A sixth case: **NULL `event_bytes`** (raw-SQLite INSERT with `NULL` despite the NOT NULL constraint — impossible in production; simulated by dropping the constraint in a test fixture) → `TornWrite(reason="null_event_bytes", offending_sequence=<row>)`.
  - A seventh case: **Unparseable `event_bytes`** (raw-SQLite UPDATE of `event_bytes` to `b'{"not": "a transition event"'` — incomplete JSON) → `TornWrite(reason="unparseable_event")`.
  - An eighth case: **Duplicate `next_head`** (raw-SQLite UPDATE making two rows share `next_head` — should be caught by the UNIQUE index, but the verifier MUST defend in depth) → `TornWrite(reason="duplicate_chain_link")`.

  **Mutation thinking:** removing case 4 (middle-tamper) would let a buggy verifier that only checks the tail pass — the AC-11 substrate test catches "store returns persisted tail," but only the verifier middle-tamper test catches "verifier walks the whole chain, not just the tail." Removing case 7 would let `model_validate_json` exceptions escape `verify()` as raw `pydantic.ValidationError` — the orchestrator would see a non-typed exception, not a typed verdict. The whole point of the tagged union is exhaustive verdict carrying.

- [ ] **AC-6 — Parity contract — verifier produces byte-equal verdicts across both `CheckpointStore` adapters.** A parametrized test at `tests/integration/test_replay_verifier_parity.py` exercises the same five-scenario matrix from AC-5 against BOTH `InMemoryCheckpointStore` and `SqliteCheckpointStore` (reuse the `ADAPTER_FACTORIES` list from `tests/integration/test_checkpoint_store_parity.py` — do NOT fork). For the in-memory adapter, "tamper" is direct mutation of the internal `_log` list (an in-memory adapter cannot torn-write but CAN chain-mismatch). For the SQLite adapter, "tamper" is the raw-SQLite UPDATE pattern from S2-01 AC-11. The verdict shape (kind, divergence_index, offending_transition_id) MUST match byte-for-byte across adapters for the same logical tamper. **Mutation thinking:** an executor implements verification via a SQLite-specific `SELECT prior_head, next_head ORDER BY sequence ASC` shortcut (skipping the Protocol abstraction); the in-memory adapter has no such SQL and the test fails LOUD with the directive *"verifier coupled to a substrate-specific read path; route through `store.read_all_for_workflow()` instead — see ADR-0003 §Consequences."*

- [ ] **AC-7 — Sum-type exhaustiveness gate at the `hydrate_or_fail` site.** A `_dispatch_verdict` helper inside `replay.py` uses `match` over the verdict's `kind` literal with a `case _:` arm that raises `AssertionError("verdict_kind drift — amend ReplayVerdict + this match")`. A static test at `tests/unit/workflows/test_replay_exhaustiveness.py` asserts the match has exactly four `case` arms (one per variant kind) plus the `case _:` drift guard; the test parses the AST via `ast.parse(...)` and counts `MatchSingleton` / `MatchValue` patterns. **Mutation thinking:** adding a fifth variant to `ReplayVerdict` (AC-1 rule-of-three note) without updating `_dispatch_verdict` would silently bypass the new verdict — the AST test catches the missing arm at the source level, not at runtime.

### The `hydrate_or_fail` integrity gate (the ADR-0003 §Decision wire-up)

- [ ] **AC-8 — `hydrate_or_fail(store, workflow_id) -> Hydrated | FailedUnrecoverable` is the SOLE site mapping `ChainMismatch | TornWrite` → `FailedUnrecoverable(reason="checkpoint_integrity")`.** Signature + body:
  ```python
  class Hydrated(BaseModel):
      """Successful hydration: verified events + latest legal state."""
      model_config = _FROZEN_FORBID
      events: tuple[TransitionEvent, ...]
      latest_state_kind: LedgerStateKind          # == events[-1].next_state_id, or "needs_plan" if empty

  HydrationResult = Annotated[
      Hydrated | FailedUnrecoverable,
      Field(discriminator="kind"),                # Hydrated.kind = "hydrated"; FailedUnrecoverable.kind = "failed_unrecoverable"
  ]

  def hydrate_or_fail(store: CheckpointStore, workflow_id: WorkflowId) -> HydrationResult:
      verdict = ReplayVerifier(store).verify(workflow_id)
      match verdict:
          case Verified(events=events):
              return Hydrated(events=events, latest_state_kind=events[-1].next_state_id if events else "needs_plan")
          case EmptyWorkflow():
              return Hydrated(events=(), latest_state_kind="needs_plan")
          case ChainMismatch() | TornWrite():
              return FailedUnrecoverable(
                  reason="checkpoint_integrity",
                  error=RemediationError(
                      error_id="workflows.checkpoint_integrity_violation",
                      message=_format_integrity_message(verdict),
                  ),
              )
  ```
  Tests at `tests/unit/workflows/test_hydrate_or_fail_routing.py` cover the four verdict → result mappings. Each mapping has its own test (parametrize fails the mutation-resistance bar — see Notes-for-implementer: "Why per-mapping tests, not parametrize").
  - **`Hydrated.kind` MUST be `"hydrated"`** (a new closed-set tag, NOT reused from `LedgerStateKind`). A `Literal["hydrated"]` discriminator at the variant level. Test (iii) on AC-1 plus a sibling assertion in `test_hydrate_or_fail_routing.py` enforces.
  - **The `error_id` MUST be `"workflows.checkpoint_integrity_violation"`** (Phase-1 ADR-0007 dotted-snake-case format). A `Final[str]` constant `_INTEGRITY_ERROR_ID` declared at the module top.
  - **`_format_integrity_message`** is a pure helper that produces a diagnostic-grade string naming the verdict kind, the offending sequence/transition, the persisted vs recomputed heads. A test asserts the string contains the `divergence_index` for `ChainMismatch` and the `reason` slug for `TornWrite`.
  - **Mutation thinking:** an executor "helpfully" merges the `Verified` and `EmptyWorkflow` arms into `case Verified() | EmptyWorkflow(): return Hydrated(events=verdict.events, ...)`. The `EmptyWorkflow` variant has no `.events` attribute (AC-1 names `genesis_chain_head` only); the merge fails immediately at AttributeError. The per-arm match prevents the regression by construction.

- [ ] **AC-9 — Tamper integration golden test (Scenario #4).** A test at `tests/integration/test_replay_tamper_golden.py` runs the full clean-completion sequence (three boundary appends), tampers the SECOND row's `next_head` via raw SQLite, calls `hydrate_or_fail(store, workflow_id)`, and asserts the result is `FailedUnrecoverable(reason="checkpoint_integrity", error.error_id="workflows.checkpoint_integrity_violation")` AND that the message string contains substring `"divergence_index=1"` AND that the message names the offending `transition_id` of row #1. The test embodies phase-arch-design.md §"Scenarios" #4 verbatim. **Mutation thinking:** dropping the `divergence_index` substring assertion would let a verifier that always reports `divergence_index=0` pass — the test catches the regression by demanding the actual middle-tamper index.

- [ ] **AC-10 — Partial-write integration golden test.** A test at `tests/integration/test_replay_torn_write_golden.py` reuses S2-01 AC-11's NULL-`event_bytes` setup pattern (drop the NOT NULL constraint on the test fixture, INSERT NULL, call `hydrate_or_fail`, assert `FailedUnrecoverable(reason="checkpoint_integrity")` with the `TornWrite.reason == "null_event_bytes"` substring in the message). A sibling test exercises the unparseable-event-bytes path (raw UPDATE to truncated JSON). **Mutation thinking:** an executor catches `sqlite3.IntegrityError` or `pydantic.ValidationError` inside `verify()` and swallows it, returning a synthetic `Verified` verdict with the previous-row events — the orchestrator would resume against a corrupted ledger. The integration test forces the FailedUnrecoverable path; the AC-7 exhaustiveness AST test prevents the missing-case escape.

- [ ] **AC-11 — Fail-closed-before-hydrate property.** A property test at `tests/property/test_hydrate_no_state_leak.py` asserts that for any tampered chain, `hydrate_or_fail` returns `FailedUnrecoverable` WITHOUT having materialized any `VulnLedgerState` model in memory beyond the events tuple inside the verdict (which is the substrate's job to expose). The structural shape: `hydrate_or_fail` does NOT construct any concrete `VulnLedgerState` variant; it returns only the typed sum-type result and lets the subgraph (S3-01) construct the `VulnLedgerState` ONLY if `kind == "hydrated"`. A static AST test at `tests/fence/test_hydrate_no_state_construction.py` walks `replay.py` and asserts no expression matches `NeedsPlan(...)`, `PlanReady(...)`, `PatchApplied(...)`, `GateFailedRetryable(...)`, `AwaitingHumanReview(...)`, `Completed(...)`, `FailedUnrecoverable(...)` ON THE HYDRATED PATH — the only ledger-state construction allowed is `FailedUnrecoverable` on the failed path. **Mutation thinking:** an executor "helpfully" reconstructs `NeedsPlan()` inside the `EmptyWorkflow` arm and returns it; the subgraph then runs with the materialized state — but the integration semantics demand the subgraph OWNS that construction, not the verifier (separation of substrate from state machine). The AST fence catches the leak.

### Sanitization, sanitizer-import discipline, and structural fences (the supporting defenses)

- [ ] **AC-12 — No regex fork; canonical sanitizer-only.** Extend the S2-01 AST fence `tests/fence/test_checkpoint_sanitizer_imports.py` to walk `src/codegenie/workflows/replay.py` AND `src/codegenie/workflows/_replay.py` in addition to the existing two adapters. Both new modules MUST NOT contain `re.compile`, `re.fullmatch`, `re.search`, `regex.`. Neither module needs to import `sanitize_for_persistence` directly (the fold reads bytes already written through the sanitizer); the fence's primary purpose here is to defend against an executor "improving" the verifier by adding ad-hoc regex parsing of the persisted bytes (which would re-introduce primitive-obsession over the typed `TransitionEvent`). **Mutation thinking:** an executor adds a "fast-path" regex extraction of `next_head` from the persisted JSON (avoiding `model_validate_json` for performance); the fence catches it and the executor is forced to surface the substitution.

- [ ] **AC-13 — `mypy --strict` clean.** All new modules pass `make typecheck` with no `Any`, no untyped `dict`, no `# type: ignore` without a comment naming the upstream issue. The discriminator-union return types are the load-bearing strictness check — a consumer that branches on `verdict.kind` without exhausting the four arms is a mypy `error: Missing match case` failure.

- [ ] **AC-14 — Contract snapshot extension (CI-gating).** Extend `tests/integration/test_phase6_sut_contract_snapshot.py` with: (a) the four-variant `ReplayVerdict` schema via `TypeAdapter(ReplayVerdict).json_schema(by_alias=True)`; (b) `inspect.signature` for `ReplayVerifier.__init__`, `ReplayVerifier.verify`, `hydrate_or_fail`, `_format_integrity_message`; (c) the `_INTEGRITY_ERROR_ID` constant value; (d) the `HydrationResult` schema. On failure, the directive prints: *"Phase-6 replay-verifier contract drift. If additive (new variant added to `ReplayVerdict` with corresponding `_dispatch_verdict` arm + ADR-0003 amendment, new optional field on a variant with default), regenerate the golden under `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` AND amend ADR-0003 §Consequences. If breaking (renamed variant, removed variant, changed `verify()` return type, narrowed `TornWrite.reason` Literal), this is an ADR-0003 amendment + downstream Phase-6.5 / Phase-9 review."* The meta-test classifier in `_meta.py` is extended to recognize verdict-shaped deltas (new `kind` literal = additive; removed `kind` = breaking; changed `divergence_index` field type = breaking).

- [ ] **AC-15 — Adapter parity meta-test (mutation guard for AC-6).** A meta-test at `tests/integration/test_replay_verifier_parity_meta.py` constructs a deliberately broken `ReplayVerifier` subclass that returns `Verified` for every input (ignoring tamper) and asserts the AC-6 parity test FAILS when given this broken verifier. Mirrors S2-01 AC-17 precedent. **Mutation thinking:** the parity test itself is mutation-susceptible (a `==` swap, a missing tamper step); the meta-test makes the parity test mutation-resistant by demanding it report the broken verifier as broken.

## Files to touch

- `src/codegenie/workflows/_replay.py` (new) — pure fold helper `_replay_fold(events, *, genesis) -> ChainHead`; module-level imports limited to `codegenie.types.identifiers` + `codegenie.workflows._chain` + `codegenie.workflows.vuln_ledger` + `codegenie.workflows.checkpoints` (the genesis constant); AST fence at `tests/fence/test_chain_head_purity.py` extended to walk this file.
- `src/codegenie/workflows/replay.py` (new) — the `ReplayVerdict` discriminated union (four variants + `Hydrated` + `HydrationResult`); the `ReplayVerifier` class with `__slots__`; the `hydrate_or_fail` function; the `_dispatch_verdict` exhaustive `match`; the `_format_integrity_message` pure helper; the `_INTEGRITY_ERROR_ID: Final[str]` constant.
- `src/codegenie/workflows/__init__.py` (unchanged — no new `__all__` entries).
- `src/codegenie/workflows/errors.py` (unchanged — no new exception classes; `RemediationError` is reused via `codegenie.transforms.outcomes` for the integrity-failure payload).
- `tests/unit/workflows/test_replay_verdict_shape.py` (new) — AC-1 four-variant shape + frozen-forbid + discriminator literal byte-equality + `Field(ge=0)` on `divergence_index`.
- `tests/unit/workflows/test_replay_sanitization_aware.py` (new) — AC-3 sanitization-aware fold round-trip.
- `tests/unit/workflows/test_replay_verify_classifications.py` (new) — AC-5 five-scenario verdict matrix (against the InMemory adapter; SQLite-specific torn-write cases live in AC-10's integration test).
- `tests/unit/workflows/test_replay_exhaustiveness.py` (new) — AC-7 AST match-arm count.
- `tests/unit/workflows/test_hydrate_or_fail_routing.py` (new) — AC-8 four-mapping tests.
- `tests/integration/test_replay_verifier_parity.py` (new) — AC-6 parity matrix parametrized over both adapters.
- `tests/integration/test_replay_tamper_golden.py` (new) — AC-9 Scenario #4 golden (clean-completion + middle-tamper + integrity-failure).
- `tests/integration/test_replay_torn_write_golden.py` (new) — AC-10 NULL-bytes + unparseable-bytes torn-write paths.
- `tests/integration/test_replay_verifier_parity_meta.py` (new) — AC-15 broken-verifier-fails-parity meta-test.
- `tests/property/test_hydrate_no_state_leak.py` (new) — AC-11 fail-closed property.
- `tests/fence/test_chain_head_purity.py` (modify — add `_replay.py` to the walked-modules constant; assert the existing fence still catches planted impurities).
- `tests/fence/test_checkpoint_sanitizer_imports.py` (modify — add `replay.py` + `_replay.py` to the walked-modules constant).
- `tests/fence/test_checkpoint_adapter_slots.py` (modify — extend to assert `ReplayVerifier` declares `__slots__ = ("_store",)`).
- `tests/fence/test_hydrate_no_state_construction.py` (new) — AC-11 AST fence over `replay.py`.
- `tests/integration/test_phase6_sut_contract_snapshot.py` (modify — extend `build_snapshot` with the verifier-shape entries per AC-14).
- `tests/integration/test_phase6_sut_contract_snapshot_meta.py` (modify — extend classifier case set with one additive verdict-shaped delta + one breaking).
- `tests/golden/phase6-contract/snapshot.json` (modify — regenerate under `PHASE6_CONTRACT_GOLDEN_REWRITE=1` after AC-14 implementation).

## TDD plan

**Red.** Land in this order — every step writes a failing test first, then asserts the failure mode is meaningful (the error message + the directive substring, not just the exception class) before writing any production code:

1. AC-1 `ReplayVerdict` four-variant shape test (fails: module doesn't exist; verifies frozen-forbid + discriminator literal byte-equality + `Field(ge=0)`).
2. AC-3 pure-core fold helper test + the sanitization-aware round-trip test (fails: `_replay_fold` doesn't exist; the sanitization round-trip drives the "sanitize-then-fold" discipline).
3. AC-4 `ReplayVerifier` `__slots__` test + constructor test (fails: class doesn't exist).
4. AC-5 verdict-classification matrix — five scenarios against the in-memory adapter (fails: `verify()` doesn't classify).
5. AC-7 AST exhaustiveness test (fails: `_dispatch_verdict` doesn't exist or lacks the four `case` arms).
6. AC-8 four routing tests for `hydrate_or_fail` (fails: function doesn't exist; the per-arm tests drive the per-arm match body).
7. AC-9 tamper integration golden test (fails: integration path absent; verifies `divergence_index` substring).
8. AC-10 torn-write integration golden tests (fails: torn-write path absent; verifies `null_event_bytes` + `unparseable_event` substrings).
9. AC-11 fail-closed property + AST fence (fails: no state construction on the failed path is the load-bearing assertion).
10. AC-6 parity-matrix parametrized over both adapters (fails: substrate-coupled implementation).
11. AC-15 parity meta-test (broken verifier → parity test fails).
12. AC-14 contract-snapshot extension (fails: extension absent; first-run regeneration via `PHASE6_CONTRACT_GOLDEN_REWRITE=1`).
13. AC-12 sanitizer-import + AC-13 `make typecheck` (the final gates).
14. AC-2 `__all__` byte-equality test (fails LOUD if the executor adds any verifier symbol to `__all__`).

**Green.** Implement the minimum that makes all red tests pass:

- Add `_replay.py` with the pure `_replay_fold(events, *, genesis) -> ChainHead` helper. The body is a one-line `reduce`-style fold over `_compute_chain_head` from S1-02. Mark `__all__ = ["_replay_fold"]` (package-internal — no symbol leaks out of `codegenie.workflows.__all__`).
- Add `replay.py` with the four `ReplayVerdict` variants (frozen-forbid + discriminator), the `Hydrated` model, the `HydrationResult` union, the `ReplayVerifier` class with `__slots__ = ("_store",)`, the `verify()` body (round-trips bytes through `TransitionEvent.model_validate_json` + folds via `_replay_fold` + classifies into the union), the `_dispatch_verdict` exhaustive `match`, the `hydrate_or_fail` function, and the `_format_integrity_message` pure helper.
- Extend the S2-01 fences additively: add `_replay.py` to the chain-head purity fence's walked-modules constant; add `replay.py` + `_replay.py` to the sanitizer-import fence; add `ReplayVerifier` to the slots fence's class-list.
- Generate the contract-snapshot golden via `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` and commit it.

**Refactor.** Cleanup only — no new behaviour. Specifically:

- Confirm `_format_integrity_message` is a pure function (no clock, no env, no I/O) — its inputs are the verdict; its output is the message string.
- Confirm `ReplayVerifier.__slots__` enumerates every instance attribute (`("_store",)` — no `_cache`, no `_stats`).
- Confirm the discriminator-union shape uses the same `Annotated[..., Field(discriminator="kind")]` pattern as `VulnLedgerState` (cross-file convention).
- Confirm `_INTEGRITY_ERROR_ID` matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` and is `Final[str]`.

**Anti-refactor (Rule 2 + Open/Closed + composition-over-inheritance).** Do NOT introduce any of the following in this story:

1. **A `BaseReplayVerifier` ABC.** One concrete class today; the Protocol IS `CheckpointStore` (the substrate that's injected). The verifier itself is substrate-agnostic by construction. See AC-4 §Anti-refactor #1.
2. **A `VerifierStrategy` Strategy abstraction over different chain-folding policies.** The fold is the *one* canonical policy (sanitize-then-fold mirroring the write path). A "loose" or "strict" toggle would mask AC-3. See AC-4 §Anti-refactor #2.
3. **A boolean return from `verify()` or a 2-tuple `(verdict_kind, payload)`.** The tagged union IS the return type. See AC-4 §Anti-refactor #3.
4. **A `ReplayVerifierRegistry` or `@register_verifier(SubstrateKind)` decorator.** The verifier is substrate-agnostic; there is no dispatch to register.
5. **An async `verify()`** — the orchestrator wraps the call in `asyncio.to_thread` (same pattern S2-01 pinned for `append()`). Async-by-default leaks the substrate choice.
6. **A separate `ReplayCache`** — verification is idempotent and cheap (a fold over ≤ 100 rows for any realistic resume); caching would couple cache invalidation to tamper detection (which is the exact problem we're solving).
7. **A `ChainHashAlgorithm` strategy abstraction** — `_compute_chain_head` IS the algorithm; ADR-0003 + ADR-0001 chokepoint discipline forbids forking the hash function.
8. **A `Verifier.verify_or_raise()` convenience wrapper that throws on `ChainMismatch`** — the tagged-union-return discipline is the canonical contract; raising would force consumers to wrap try/except, defeating the discriminated-union exhaustiveness guarantee.

## Out of scope

- The LangGraph subgraph nodes that call `hydrate_or_fail` (Phase-6 S3-01) — consumer, not definer.
- The HITL resume validator (Phase-6 S4-01) — reads the `Hydrated.events` to find the latest `awaiting_human_review` row; does NOT modify the verifier.
- The SUT adapter `LocalVulnRemediationSut` (Phase-6 S5-01) — constructs the `ReplayVerifier` via the injected `CheckpointStore`; threads the `HydrationResult` into the subgraph's entry edge.
- The Postgres adapter (Phase-9 S5-01) — the verifier is substrate-agnostic; it dispatches through the Protocol. Adding the Postgres adapter is one row in the AC-6 parity matrix, zero edits to this story's code.
- The forensic two-stream `EventLog` (Phase-3 S6-01) — orthogonal substrate; the verifier reads ONLY from the `CheckpointStore`.
- A retry-on-mismatch loop — by ADR-0003 §Consequences, integrity failure is terminal (`FailedUnrecoverable`). The integrity-policy decision is "fail closed before work resumes" — no retry path.
- The `_INTEGRITY_ERROR_ID` being added to a new `error_id` registry — the project does not yet have one; the constant is module-local. When Phase 9+ adds a registry, the migration adds this constant additively.
- A `BaseReplayVerifier` ABC / `VerifierMixin` / `VerifierStrategy` / `ReplayVerifierRegistry` / async `verify()` / `ReplayCache` — see Anti-refactor #1–6.

## Notes for the implementer

- **Why the sanitization-aware fold is non-negotiable.** Surfaced by the S2-01 attempt log: the chain head is computed over the LIVE event (cleartext); the on-disk row is the SANITIZED bytes (cleartext → `<REDACTED:fingerprint=...>` sentinels). A naive verifier that recomputes by reading the persisted bytes and recomputing via `bytes → _compute_chain_head(prior, bytes)` would compute a DIFFERENT head than was persisted IFF sanitization triggered, and would (falsely) declare `ChainMismatch`. The fix is to round-trip the bytes through `TransitionEvent.model_validate_json(row_bytes)` and call `_compute_chain_head(prior_head, reconstructed_event)` — the SAME write-path call. Because `sanitize_for_persistence` operates on already-canonical-JSON bytes and replaces secret-shaped substrings with redaction sentinels, the reconstructed event's `model_dump_json()` produces byte-equal output (the sentinels are valid JSON strings and Pydantic preserves them in round-trip). The fold is therefore byte-equivalent to the write path by construction. Write the AC-3 test FIRST — without it, the executor will choose the naive path and the integration tests will pass against unsanitized events but fail mysteriously on sanitization-triggering events.

- **Why the verdict is a discriminated union, not a typed exception.** Three reasons: (i) the orchestrator must dispatch on the verdict to choose a recovery path (today only one: `checkpoint_integrity`; tomorrow possibly retry-on-torn-write if the substrate gains atomic-write guarantees); (ii) the `Verified` arm carries the `events` tuple — passing it via exception would couple the error type to a successful payload, an anti-pattern; (iii) the meta-test (AC-14) classifier handles schema deltas, not exception class deltas — sum-type extension is the canonical Phase-6 pattern (mirrors `VulnLedgerState`, `RecipeOutcome`, `FreshnessSignal`).

- **Why `_format_integrity_message` is pure (no clock, no env).** The integrity message is part of the typed `FailedUnrecoverable.error.message` payload that flows into `RepoContext`-style audit artifacts; a wall-clock timestamp inside the message would break golden-test determinism. The "when did this fail" timestamp is the orchestrator's job (it logs the verdict with a clock-injected timestamp at the call site).

- **Why the AC-7 AST exhaustiveness test, not just relying on `mypy --strict` match exhaustiveness.** Mypy's match exhaustiveness check requires `assert_never` at the catch-all arm, which is a Python 3.11+ construct that interacts poorly with pydantic discriminated unions in some mypy versions (false negatives on the "missing case" check). The AST test counts case-arms at the source level and is mypy-version-independent. Land both gates — they catch overlapping but non-identical mutation classes.

- **Why per-mapping tests, not parametrize, for `hydrate_or_fail` routing.** The four mappings have DIFFERENT setup costs (`Verified` needs a 3-event fixture; `EmptyWorkflow` needs zero; `ChainMismatch` needs a raw-SQLite tamper; `TornWrite` needs a constraint-relaxed fixture). A `pytest.parametrize` over the four cases would force a single setup path and either (i) over-build for the simple cases or (ii) under-build for the complex cases. Four separate tests, each with the minimum fixture, are clearer and break with more specificity when one mapping regresses.

- **Why `verify()` reads through `store.read_all_for_workflow()` and `store.tail_chain_head()`, NOT a substrate-specific shortcut.** The whole point of the `CheckpointStore` Protocol (S2-01 AC-1) is that consumers — including this verifier — depend on the Protocol, not on the adapter. A SQLite-specific `SELECT prior_head, next_head ORDER BY sequence ASC` would gain ~10% wall-clock at the cost of breaking parity with `InMemoryCheckpointStore` (no SQL) and Phase-9 `PostgresCheckpointStore` (different SQL dialect). The AC-6 parity test catches the substitution; the AC-12 sanitizer fence catches the read-path-fork variant; the Notes-for-implementer is the prose justification. The Protocol IS the kernel.

- **Why the `Hydrated.kind = "hydrated"` discriminator is a NEW closed-set tag, not reused from `LedgerStateKind`.** The two unions answer different questions: `LedgerStateKind` is "what state is the workflow IN?"; `Hydrated.kind / FailedUnrecoverable.kind` is "what HAPPENED during hydration?". Reusing `LedgerStateKind` would let an executor return `Hydrated(kind="needs_plan", events=())` — a category error that the type system would mask. Separate union, separate discriminator literal.

- **Phase-9 forward dep — what stays the same when Postgres lands.** The Phase-9 `PostgresCheckpointStore` implements `CheckpointStore` byte-equivalently (same `append() -> ChainHead`, same `read_all_for_workflow()` order, same `tail_chain_head()` raw-persisted return). The verifier code in this story is UNCHANGED; the AC-6 parity matrix gains a third adapter in `ADAPTER_FACTORIES`. The proof that the Open/Closed substrate is real: a 100-line Postgres adapter + one parametrize-row addition is the entire migration of THIS story's contract to Postgres.

- **Phase-7 migration forward dep — what changes (and what doesn't).** Phase-7 (distroless-migration task class) gets its own `migration_ledger.py` + `migration_checkpoints.py` + its own boundary catalog (different state machine). It also gets its own verifier IF the failure classification differs (e.g., migration introduces a `RollbackRequired` arm that vuln does not). The Protocol `CheckpointStore` is shared; the verifier may not be. The Open/Closed substrate this story freezes is `CheckpointStore` (the read substrate) and `_compute_chain_head` (the fold) — both are task-class-agnostic. The verdict union is task-class-specific (this story's `ReplayVerdict` is vuln-shaped; Phase-7 will have a `MigrationReplayVerdict` or extend the union additively).
