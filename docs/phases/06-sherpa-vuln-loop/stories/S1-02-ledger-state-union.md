# S1-02 — Ledger state union

**Status:** HARDENED
**Validated:** 2026-05-25 — see [`_validation/S1-02-ledger-state-union.md`](_validation/S1-02-ledger-state-union.md).
**Depends on:** [`S1-01-sut-contract-types.md`](S1-01-sut-contract-types.md) — imports `_FROZEN_FORBID` from the canonical site landed in S1-01; AC-6 asserts the terminal partition of this story's sum type is byte-equal to S1-01's `TerminalState` Literal.

**Goal:** Land the closed seven-variant `VulnLedgerState` discriminated union, the `TransitionEvent` record carrying the five fields `final-design.md §"State model"` mandates, the closed legal-transition table enforced at construction, and the BLAKE3 chain-head substrate ADR-0003's replay-verification gate depends on — and *only* those — so every later Phase-6 story (checkpoint store S2-01, replay verification S2-02, subgraph nodes S3-01, HITL resume S4-01, SUT adapter S5-01) can target a frozen, byte-deterministic ledger contract that the Phase-6.5 bench and Phase-9 Temporal worker will later assert byte-identical across substrates.

This is the second half of High-level-impl.md §"Step 1 — Public contracts and typed ledger." S1-01 shipped the public Result + Case + Protocol + digest substrate; this story ships the *internal* state-machine substrate every node and the checkpoint store will dispatch on. The concrete SQLite checkpoint writer (S2-01), the replay verifier (S2-02), the LangGraph subgraph (S3-01), and the SUT adapter (S5-01) all consume types defined here — none of them define new ones.

## References

- [final-design.md](../final-design.md) §"State model" (verbatim seven-variant universe + the five transition-event fields), §"Main workflow" (legal transition edges), §"Decisions of record" items 3 + 4 (semantic checkpoints; edges own control flow).
- [phase-arch-design.md](../phase-arch-design.md) §"Logical view" (where `VulnLedger` sits), §"Failure modes" (checkpoint-chain-mismatch row → drives AC-8 chain-head substrate), §"Scenarios" #4 (tampered checkpoint → `FailedUnrecoverable(reason="checkpoint_integrity")`).
- [ADRs/0001-stable-vuln-remediation-sut-contract.md](../ADRs/0001-stable-vuln-remediation-sut-contract.md) — `TerminalState` Literal pinning is part of the same contract this ledger feeds; AC-6 cross-story membership test enforces.
- [ADRs/0003-checkpointed-ledger-replay-boundary.md](../ADRs/0003-checkpointed-ledger-replay-boundary.md) — verify previous chain head before hydration; failed verification → `FailedUnrecoverable(reason="checkpoint_integrity")`. Drives AC-4 (chain_head field on `TransitionEvent`) + AC-8 (pure helper substrate).
- [High-level-impl.md](../High-level-impl.md) §"Step 1 — Public contracts and typed ledger" (this story is the second half).
- [S1-01-sut-contract-types.md](S1-01-sut-contract-types.md) + [_validation/S1-01-sut-contract-types.md](_validation/S1-01-sut-contract-types.md) — the public Result + Case + `_FROZEN_FORBID` canonical site this story consumes; the `__all__` allowlist sentinel (AC-12) that AC-13 extends additively here.
- Phase-3 sum-type precedent: [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) — five canonical discriminated unions, each variant `model_config = _FROZEN_FORBID`, each umbrella `Annotated[A | B | ..., Field(discriminator="kind")]`, shared payloads injected as sub-models (composition, not inheritance — see `RecipeError` inside `RecipeFailed`).
- Phase-3 ADR-0010 (newtype-identifier catalog + drift test) + the existing `_NEWTYPE_REGISTRY` in [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) that AC-11 extends.
- Phase-4 forward reuse: `ChainHead = NewType("ChainHead", str)` from `codegenie.types.identifiers` (Phase-4 S4-04 manifest chain-head). This story reuses the existing newtype + its parser; does NOT redeclare.
- Phase-9 forward dep: [`docs/phases/09-temporal-durable-workflow/stories/S4-05-run-vuln-subgraph-activity.md`](../../09-temporal-durable-workflow/stories/S4-05-run-vuln-subgraph-activity.md) — `digest()` byte-equality across `LocalVulnRemediationSut` / `TemporalVulnRemediationSut`. The chain-head helper landed here is the substrate that makes that G5 invariance reachable for the ledger half.

## Acceptance criteria

### Sum type (the seven ADR-0001 / final-design.md variants)

- [ ] **AC-1 — Canonical module + seven variant classes.** `src/codegenie/workflows/vuln_ledger.py` declares exactly seven `BaseModel` subclasses:
  - **Non-terminal (4):** `NeedsPlan`, `PlanReady`, `PatchApplied`, `GateFailedRetryable`.
  - **Terminal (3):** `AwaitingHumanReview`, `Completed`, `FailedUnrecoverable`.

  Each variant declares `kind: Literal["..."] = "..."` with the canonical snake_case slug:
  ```python
  class NeedsPlan(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["needs_plan"] = "needs_plan"
      # …per-variant evidence payload — see AC-3
  ```
  A module-level `LedgerStateKind = Literal["needs_plan", "plan_ready", "patch_applied", "gate_failed_retryable", "awaiting_human_review", "completed", "failed_unrecoverable"]` alias is also declared so the transition table (AC-5) and exhaustiveness tests (AC-9) are typed against an *enumerable* closed set. A static test asserts (i) exactly seven `BaseModel` subclasses are defined in the module; (ii) the multiset of `kind` Literals across the seven variants is byte-equal to the membership of `LedgerStateKind`; (iii) adding an eighth variant fails this test loud, directing the implementer to "amend ADR-0001 + ADR-0003 + S1-01's `TerminalState` Literal before adding a ledger variant."

- [ ] **AC-2 — Closed discriminated union via `Annotated[..., Field(discriminator="kind")]`.** The module declares:
  ```python
  VulnLedgerState = Annotated[
      NeedsPlan | PlanReady | PatchApplied | GateFailedRetryable
      | AwaitingHumanReview | Completed | FailedUnrecoverable,
      Field(discriminator="kind"),
  ]
  ```
  This is the convention every Phase-3 sum type uses (`codegenie/transforms/outcomes.py` — five canonical examples). A static test asserts (i) the umbrella is `Annotated[..., Field(discriminator="kind")]`; (ii) `pydantic.TypeAdapter(VulnLedgerState).validate_python({"kind": "needs_plan", …})` round-trips to a `NeedsPlan` instance and never to any other variant; (iii) a payload with `{"kind": "nonsense"}` raises `pydantic.ValidationError` with the discriminator-collision message (not a structural-mismatch message — the discriminator is the rejection mechanism). **Mutation thinking:** removing `discriminator="kind"` from the umbrella silently lets Pydantic fall back to structural matching, which lets a `{"kind": "completed", "patch_digest": null}` payload silently decode to `NeedsPlan` if the field shapes happen to overlap; the round-trip test in (ii) catches this.

- [ ] **AC-3 — Per-variant evidence payloads (frozen, `extra="forbid"`, sanitization-enforcing).** Each of the seven variants carries `model_config = _FROZEN_FORBID` (imported from the single canonical site landed in S1-01) and the following payload:
  - `NeedsPlan` — no payload beyond `kind`. Initial state; no evidence accumulated yet.
  - `PlanReady` — `plan_summary: str` (capped at 4096 chars via `field_validator`, mirroring `RecipeError._message_length`).
  - `PatchApplied` — `patch_digest: BlobDigest` (reuses existing newtype; never raw `str`).
  - `GateFailedRetryable` — `failing_signals: tuple[SignalKind, ...]` (immutable; reuses existing `SignalKind` newtype); `attempt_number: AttemptNumber` (reuses existing newtype); the field is `tuple`, not `list`, so the variant is genuinely hashable / frozen.
  - `AwaitingHumanReview` — `review_reason: HumanReviewReason` (reuses the existing closed Literal from `transforms.outcomes`); `handoff_path: str | None = None`.
  - `Completed` — `report_path: str | None = None` (None when the orchestrator failed to allocate before completion); a `model_validator` asserts the upstream chain head's variant immediately before `Completed` was either `PatchApplied` or `AwaitingHumanReview` (the only legal predecessors — see AC-5 transition table).
  - `FailedUnrecoverable` — `reason: Literal["checkpoint_integrity", "subgraph_aborted", "manifest_rejected", "policy_violation", "internal_invariant_violated"]` (closed set, byte-equal to the row keys of `phase-arch-design.md §"Failure modes"`; adding a sixth reason is an ADR-0003 amendment); `error: RemediationError | None = None` (reuses the existing payload type from `transforms.outcomes`).

  Every payload field type is either an existing kernel newtype, an existing Literal closed set, or a primitive constrained by a `field_validator`. No raw `str` for domain identifiers (CLAUDE.md "newtype identifiers" load-bearing commitment). An AST test walks `vuln_ledger.py` and asserts every `BaseModel` subclass sets `model_config = _FROZEN_FORBID` (no `ConfigDict(frozen=True, extra="forbid")` re-declarations — the canonical constant must be imported, never inlined).

- [ ] **AC-4 — `TransitionEvent` model carries the five fields `final-design.md §"State model"` mandates.** A single frozen Pydantic model:
  ```python
  class TransitionEvent(BaseModel):
      model_config = _FROZEN_FORBID
      transition_id: TransitionId            # AC-7 — new newtype, ULID
      prior_state_id: LedgerStateKind        # the kind discriminator of the prior state
      next_state_id: LedgerStateKind         # the kind discriminator of the next state
      triggering_outcome: RecipeOutcome | NodeTransition | GateOutcome  # tagged-union; see Notes
      evidence_digest: BlobDigest            # reuses existing newtype; 64-hex BLAKE3
      chain_head: ChainHead                  # reuses existing Phase-4 newtype
      workflow_id: WorkflowId                # reuses existing newtype; ties to the SUT case
  ```
  A static test asserts the field set is byte-equal to that seven-field shape (the five named by `final-design.md` + `transition_id` + `workflow_id`); a missing or extra field fails. **Mutation thinking:** dropping `chain_head` from the model would make replay verification impossible; the field-set test catches this immediately.

- [ ] **AC-5 — Closed legal-transition table (`_LEGAL_TRANSITIONS`) + `model_validator` enforcement.** A module-level `_LEGAL_TRANSITIONS: Final[frozenset[tuple[LedgerStateKind, LedgerStateKind]]]` declares the closed set of legal `(prior, next)` pairs derived verbatim from `final-design.md §"Main workflow"` + ADR-0003's consequence list. Concretely the executor enumerates the edges (legal moves are: `needs_plan → plan_ready`; `plan_ready → patch_applied`, `→ awaiting_human_review`, `→ failed_unrecoverable`; `patch_applied → completed`, `→ gate_failed_retryable`, `→ awaiting_human_review`, `→ failed_unrecoverable`; `gate_failed_retryable → needs_plan`, `→ awaiting_human_review`, `→ failed_unrecoverable`; `awaiting_human_review → plan_ready`, `→ completed`, `→ failed_unrecoverable`; terminal states `completed` and `failed_unrecoverable` have zero outgoing edges). `TransitionEvent.model_validator(mode="after")` rejects any `(prior_state_id, next_state_id)` pair not in `_LEGAL_TRANSITIONS` with `pydantic.ValidationError` whose message names the pair *and* points at ADR-0003 §"Consequences" for the legal-edge inventory.

  Three tests:
  1. **Positive parametrize over `_LEGAL_TRANSITIONS`** — every listed pair constructs successfully.
  2. **Negative property** (Hypothesis): for any pair drawn from `LedgerStateKind × LedgerStateKind` *not* in `_LEGAL_TRANSITIONS`, construction raises `ValidationError` and the error message contains the directive substring.
  3. **Terminal-closure test** — for every `terminal ∈ {"completed", "failed_unrecoverable"}` and every `next ∈ LedgerStateKind`, the pair `(terminal, next)` is NOT in `_LEGAL_TRANSITIONS` (terminal states have no outgoing edges; "terminal" is the *operational* definition of terminal, not a class-level annotation).
  4. **Non-terminal-liveness test** — for every non-terminal `s ∈ {"needs_plan", "plan_ready", "patch_applied", "gate_failed_retryable", "awaiting_human_review"}`, there is at least one `next` such that `(s, next) ∈ _LEGAL_TRANSITIONS` (no dead non-terminal — a state with no exit is a soft-lock bug).

  **Mutation thinking:** replacing `_LEGAL_TRANSITIONS` with `frozenset()` fails test (1) immediately; replacing the model_validator with `return self` fails test (2); accidentally adding `(completed, needs_plan)` (e.g., a re-run shortcut) fails test (3).

- [ ] **AC-6 — Cross-story consistency: terminal partition ≡ S1-01 `TerminalState`.** A test in `tests/integration/test_phase6_terminal_state_consistency.py` imports both `codegenie.workflows.vuln_sut.TerminalState` (the S1-01 Literal) and the `_TERMINAL_LEDGER_KINDS: Final[frozenset[LedgerStateKind]]` constant landed in this story, and asserts:
  - `set(get_args(TerminalState)) == _TERMINAL_LEDGER_KINDS == frozenset({"completed", "awaiting_human_review", "failed_unrecoverable"})` — membership byte-equality across all three sources.
  - The four non-terminal kinds — `{"needs_plan", "plan_ready", "patch_applied", "gate_failed_retryable"}` — are NOT in `get_args(TerminalState)` (so a future drift like adding `cancelled` to the ledger but not to `TerminalState` fails CI loud).

  On failure the test prints a directive: *"Phase-6 ledger / SUT terminal-state drift. The seven-variant ledger universe (vuln_ledger.py) and the public Result's TerminalState Literal (vuln_sut.py) must agree on the terminal partition. Adding or removing a terminal kind is an ADR-0001 + ADR-0003 amendment; touching one without the other is forbidden."*

- [ ] **AC-7 — `TransitionId` newtype + smart constructor.** A new kernel-tier identifier:
  ```python
  TransitionId = NewType("TransitionId", str)  # ULID, 26-char Crockford base32
  ```
  added to `codegenie/types/identifiers.py` and `__all__`, with smart constructor `parse_transition_id` in `codegenie/types/parsers.py` accepting only `^[0-7][0-9A-HJKMNP-TV-Z]{25}$` (ULID canonical regex). **Disambiguation note:** `TransitionId` is the *per-transition ledger event id* (chained for replay determinism). It is distinct from the existing `EventId` (the Phase-3 two-stream event-log id — append-only forensic event log, S6-01). The two newtypes have different lifecycles and different consumers; conflating them would couple the replay-verification path to the forensic-log path.

- [ ] **AC-8 — Chain-head pure helper substrate (ADR-0003 replay-verification gate).** A pure helper `_compute_chain_head` lives in `src/codegenie/workflows/_chain.py`:
  ```python
  def _compute_chain_head(prior_head: ChainHead, event: TransitionEvent) -> ChainHead:
      """Pure: BLAKE3(prior_head_bytes || canonical_event_bytes); returns ChainHead("blake3:<64hex>")."""
  ```
  Three Hypothesis properties + one AST test:
  - **Stability:** for any drawn `(prior_head, event)`, computing the chain head twice yields byte-equal output. Functional-core determinism.
  - **Sensitivity:** for any two drawn `(prior_head, event)` pairs differing on any field, the resulting chain heads differ. **Mutation thinking:** a buggy implementation that omits `evidence_digest` from the canonical-event bytes would silently collide on otherwise-identical events with different evidence; this property catches it.
  - **Chain-forward extension:** for any drawn sequence `[e0, e1, ..., eN]`, computing the chain step-by-step (`head_i = _compute_chain_head(head_{i-1}, e_i)`) yields the same final head as a *recomputed* walk from the same starting head — i.e., the chain is purely a function of the event sequence, not of any hidden state. Replay-determinism floor.
  - **No-side-effects AST fence:** a test at `tests/fence/test_chain_head_purity.py` walks the AST of `_chain.py` and forbids the names `open`, `socket`, `urllib`, `httpx`, `requests`, `time.time`, `time.monotonic`, `time.perf_counter`, `datetime.now`, `datetime.utcnow`, `random`, `uuid`, `os.environ`, `os.getenv`. (`uuid` is forbidden because a chain-head computation that ever calls `uuid4()` would diverge across substrates — Phase-9 S4-05 G5 invariance failure mode.)

- [ ] **AC-9 — Exhaustiveness via `match` + `assert_never`.** A representative test in `tests/unit/workflows/test_vuln_ledger_exhaustiveness.py`:
  ```python
  def _describe(state: VulnLedgerState) -> str:
      match state:
          case NeedsPlan(): return "needs_plan"
          case PlanReady(): return "plan_ready"
          # ... five more
          case _ as unreachable:
              assert_never(unreachable)  # mypy --strict catches missing variants
  ```
  The test parametrizes over instances of all seven variants and asserts `_describe(v)` returns the expected slug. **Mutation thinking:** if a future story adds an eighth variant *without* updating `_describe`, `mypy --strict` flags the missing `case` at typecheck time (`assert_never` becomes reachable); this AC mandates that exhaustiveness is enforced at typecheck-time, not just runtime. Replacing `assert_never(unreachable)` with `return "unknown"` would silently pass for an unhandled variant at runtime but fails `make typecheck` — the AC requires both runtime parametrize and typecheck pass.

- [ ] **AC-10 — JSON round-trip + byte-determinism.** For each of the seven variants and for `TransitionEvent`, `Model.model_validate_json(m.model_dump_json()) == m` (round-trip) AND `m.model_dump_json()` is byte-deterministic across two independent dumps (sorted keys; a future Pydantic config flip catches here, not in Phase-6.5 / Phase-9). For the `VulnLedgerState` umbrella, `TypeAdapter(VulnLedgerState).validate_python(adapter.dump_python(v))` round-trips to the same variant (discriminator round-trips). The test additionally asserts that a JSON payload with an unknown `kind` value (e.g., `{"kind": "cancelled"}`) raises `pydantic.ValidationError` with a discriminator-not-matched message — not silently accepted.

- [ ] **AC-11 — Newtype registry registration.** `TransitionId` is added to:
  - `codegenie.types.identifiers.__all__`,
  - the `_NEWTYPE_REGISTRY` mapping with a one-line docstring naming ADR-0010 + Phase-6 ADR-0003 + this story,
  - its smart constructor lands in `codegenie.types.parsers`.

  The existing identifier registry drift test (`tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` and the Phase-4 / Phase-7 equivalents) is extended (or a Phase-6 sibling added) so an unregistered newtype fails CI. The registry entry MUST land in the *same commit* as the newtype declaration — the existing drift test enforces this.

- [ ] **AC-12 — AST `_FROZEN_FORBID` fence over the new module.** A test at `tests/fence/test_workflows_frozen_forbid.py` (extends the S1-01 fence over `vuln_sut.py` if one was landed; otherwise creates the new fence) AST-walks every `.py` file under `src/codegenie/workflows/` and asserts that every `class X(BaseModel)` declaration carries `model_config = _FROZEN_FORBID` (literal attribute assignment; no `ConfigDict(frozen=True, extra="forbid")` re-declaration; the canonical constant must be imported). **Mutation thinking:** an executor under deadline pressure ships `class FailedUnrecoverable(BaseModel): kind: ...` without the `model_config = _FROZEN_FORBID` line; the AST fence catches this immediately and CI fails loud.

- [ ] **AC-13 — Public-surface allowlist amended additively.** S1-01's AC-12 introduced the `codegenie.workflows.__all__` allowlist sentinel. This story adds the following names to `__all__` (additively):
  - `VulnLedgerState` (the umbrella alias)
  - The seven variant classes (`NeedsPlan`, `PlanReady`, `PatchApplied`, `GateFailedRetryable`, `AwaitingHumanReview`, `Completed`, `FailedUnrecoverable`)
  - `LedgerStateKind` (the Literal alias)
  - `TransitionEvent`
  - `TransitionId` (re-exported from `codegenie.types.identifiers` for harness convenience)

  A test asserts `codegenie.workflows.__all__` is byte-equal to the union of S1-01's four names + this story's ten names — i.e., 14 names total, no more, no less. Adding any other public name is an additive ADR amendment, never an accidental `__all__` edit. The S1-01 AC-12 allowlist-sentinel test continues to pass after the amendment.

- [ ] **AC-14 — `mypy --strict` clean.** All new modules pass `make typecheck` with no `Any`, no untyped `dict`, no `# type: ignore` without a comment naming the upstream issue. The `assert_never` in AC-9's representative test is the load-bearing strictness check — a missed variant becomes a typecheck failure.

- [ ] **AC-15 — Contract snapshot extension (CI-gating).** Extend `tests/integration/test_phase6_sut_contract_snapshot.py` + the meta-test landed in S1-01 to additionally byte-compare the JSON schemas of `VulnLedgerState` (via `TypeAdapter(VulnLedgerState).json_schema()`), `TransitionEvent`, and a structural snapshot of `_LEGAL_TRANSITIONS` (the sorted list of `(prior, next)` strings). On failure, the directive prints: *"Phase-6 ledger contract drift. If additive (new variant with no removed / renamed predecessors, new transition edge), regenerate the golden under `PHASE6_CONTRACT_GOLDEN_REWRITE=1 pytest tests/integration/test_phase6_sut_contract_snapshot.py` AND amend ADR-0003 §Consequences AND verify the terminal partition still matches S1-01's `TerminalState` (AC-6). If breaking (rename of a `kind` slug, removal of a variant or edge, narrowing of a payload field), this is an ADR-0001 + ADR-0003 amendment + downstream Phase-6.5 / Phase-9 review per ADR-0001 §Consequences."* The meta-test inherits S1-01's additive-vs-breaking classifier; this AC adds two synthetic snapshots (one additive — new transition edge; one breaking — removed variant) to the meta-test's case set so the classifier is exercised on ledger-shaped deltas, not only on SUT-result-shaped ones.

## Files to touch

- `src/codegenie/workflows/vuln_ledger.py` (new) — seven variant classes + `VulnLedgerState` umbrella + `LedgerStateKind` alias + `_TERMINAL_LEDGER_KINDS` constant + `_LEGAL_TRANSITIONS` table + `TransitionEvent`.
- `src/codegenie/workflows/_chain.py` (new) — `_compute_chain_head` pure helper.
- `src/codegenie/workflows/__init__.py` (modify — extend `__all__` per AC-13).
- `src/codegenie/types/identifiers.py` (modify — add `TransitionId` newtype + `_NEWTYPE_REGISTRY` entry).
- `src/codegenie/types/parsers.py` (modify — add `parse_transition_id` smart constructor).
- `tests/unit/workflows/test_vuln_ledger_shape.py` (new) — AC-1 seven-variant enumeration; AC-3 per-variant payload fields; frozenness; `extra="forbid"`.
- `tests/unit/workflows/test_vuln_ledger_discriminator.py` (new) — AC-2 `Annotated[..., Field(discriminator="kind")]` round-trip + discriminator-collision rejection.
- `tests/unit/workflows/test_transition_event_shape.py` (new) — AC-4 seven-field shape + frozenness + `extra="forbid"`.
- `tests/unit/workflows/test_legal_transitions.py` (new) — AC-5 parametrize-over-legal + Hypothesis-negative + terminal-closure + non-terminal-liveness.
- `tests/unit/workflows/test_vuln_ledger_exhaustiveness.py` (new) — AC-9 `match` + `assert_never`.
- `tests/unit/workflows/test_vuln_ledger_roundtrip.py` (new) — AC-10 round-trip + byte-determinism + umbrella discriminator round-trip + unknown-kind rejection.
- `tests/unit/workflows/test_chain_head_properties.py` (new) — AC-8 Hypothesis stability + sensitivity + chain-forward extension.
- `tests/fence/test_chain_head_purity.py` (new) — AC-8 AST no-side-effects fence.
- `tests/fence/test_workflows_frozen_forbid.py` (new) — AC-12 AST `_FROZEN_FORBID` fence over `src/codegenie/workflows/*.py`.
- `tests/integration/test_phase6_terminal_state_consistency.py` (new) — AC-6 cross-story membership equality.
- `tests/integration/test_phase6_sut_contract_snapshot.py` (modify — extend per AC-15) + `..._meta.py` (modify — add two synthetic ledger-shaped deltas).
- `tests/golden/phase6-contract/snapshot.json` (modify — regenerate under `PHASE6_CONTRACT_GOLDEN_REWRITE=1` after AC-15 implementation).
- `tests/unit/types/test_identifiers_phase3.py` (or Phase-6 sibling) — extend drift test for `TransitionId`.

## TDD plan

**Red.** Land in this order — every step writes a failing test first, then asserts the failure mode is meaningful (the error message, not just the exception class) before writing any production code:

1. AC-1 seven-variant enumeration test (fails: module doesn't exist).
2. AC-3 per-variant payload field tests + `extra="forbid"` + frozenness (fails: variants don't exist).
3. AC-2 discriminated-union round-trip + discriminator-collision test (fails: umbrella doesn't exist; the collision test specifically asserts the directive substring).
4. AC-4 `TransitionEvent` seven-field shape test (fails: class doesn't exist; the field-set test asserts byte-equality so a missing `chain_head` is caught loud).
5. AC-5 legal-transition parametrize + Hypothesis negative + terminal-closure + non-terminal-liveness tests (fails: `_LEGAL_TRANSITIONS` doesn't exist).
6. AC-7 `TransitionId` parser test (fails: newtype + parser don't exist).
7. AC-8 chain-head stability + sensitivity + chain-forward properties (fails: helper doesn't exist).
8. AC-8 AST no-side-effects fence (fails: `_chain.py` doesn't exist; once it does, fence starts trivially passing and starts *biting* if S2-01 / S5-01 ever import `time` / `uuid` into the chain-head path).
9. AC-9 exhaustiveness `match` + `assert_never` test (fails: variants don't exist; once they do, fails at the typecheck step if any variant is missing from the `match`).
10. AC-10 round-trip + byte-determinism tests for each variant + `TransitionEvent` + umbrella.
11. AC-6 cross-story `TerminalState` membership test (fails: `_TERMINAL_LEDGER_KINDS` doesn't exist; depends on S1-01's `TerminalState` Literal being landed first).
12. AC-12 AST `_FROZEN_FORBID` fence (fails: at least one variant without the constant — write production code in (13) below to make this pass).
13. AC-13 `__all__` allowlist amendment test + AC-15 contract snapshot extension (fails on first run with the directive; commit the regenerated golden in Green).

**Green.** Implement the minimum that makes all red tests pass:

- Add `TransitionId` newtype + `_NEWTYPE_REGISTRY` entry + `parse_transition_id` smart constructor in the same commit (AC-11) — the existing drift test will fail otherwise.
- Implement the seven variant classes in `vuln_ledger.py`. Each variant: `model_config = _FROZEN_FORBID` (imported from S1-01's canonical site; no re-declaration), `kind: Literal["..."]`, and the per-variant payload fields named in AC-3.
- Implement `LedgerStateKind` (module-level Literal alias) + `VulnLedgerState` umbrella (`Annotated[..., Field(discriminator="kind")]`) + `_TERMINAL_LEDGER_KINDS` constant + `_LEGAL_TRANSITIONS` frozenset.
- Implement `TransitionEvent` with the seven fields named in AC-4 and the `model_validator(mode="after")` that rejects `(prior, next) ∉ _LEGAL_TRANSITIONS` with the directive message.
- Implement `_compute_chain_head` as a *pure* helper in `_chain.py`: take `prior_head` + `event`, serialize the event via `event.model_dump_json(sort_keys=True).encode()`, prefix with `prior_head.removeprefix("blake3:").encode()`, feed to BLAKE3, return `ChainHead(f"blake3:{hex}")`. No I/O, no env, no clock — the AST fence enforces this.
- Extend `codegenie/workflows/__init__.py` `__all__` additively (AC-13).
- Generate the contract golden via `PHASE6_CONTRACT_GOLDEN_REWRITE=1` and commit it (AC-15).

**Refactor.** Cleanup only — no new behaviour. Specifically:

- Confirm `_FROZEN_FORBID` is imported once at the top of `vuln_ledger.py` (the AST fence catches drift).
- Confirm `_LEGAL_TRANSITIONS` and `_TERMINAL_LEDGER_KINDS` are `Final` and at module level (not class-level — the transition table is a module-level constant, mirroring the `_TERMINAL_STATE_SET` pattern in `transforms/outcomes.py`).
- Verify the seven `match` cases in the exhaustiveness test are in declaration order (cosmetic; aids review).

**Anti-refactor (Rule 2 + composition-over-inheritance).** Do NOT introduce any of the following in this story:

1. A `BaseLedgerState` ABC or `BaseLedgerVariant` mixin. The original story's Refactor step ("move repeated evidence fields into shared bases") is a *premature DRY* anti-pattern AND a composition-vs-inheritance violation. The Phase-3 precedent (`transforms/outcomes.py`) deliberately rejects this: `RecipeError` is composed *into* `RecipeFailed.error: RecipeError`, never inherited. If two variants need the same payload type, declare that payload as a frozen sub-model and inject it as a field — composition wins.
2. A `LedgerStateRegistry` or `@register_ledger_variant` decorator. The seven-variant universe is closed; making it pluggable is a Rule-2 violation (no third concrete user exists).
3. A `Specification`-pattern transition-predicate framework. The single `(prior, next) ∈ frozenset` predicate doesn't earn composable specifications.
4. A `migration_ledger.py` placeholder for Phase 7. The file naming (`vuln_ledger.py`, not `ledger.py`) is the Open/Closed substrate; the actual sibling file lands in Phase 7 with its own seven-or-more variants and its own transition table. Surfacing the opportunity is a Notes-for-implementer concern, not an AC.
5. A `transition_log: list[TransitionEvent]` field on any variant. The chain of `TransitionEvent`s lives in the checkpoint store (S2-01) and is queried via the chain-head walk; it is not embedded in the state variants. Embedding it would either (a) make every variant carry the full history, ballooning the snapshot bytes, or (b) require a circular import.

## Out of scope

- The concrete SQLite checkpoint store (Phase-6 S2-01) — implements append/read against `TransitionEvent` but is not part of this story.
- The replay verifier (Phase-6 S2-02) — consumes `_compute_chain_head` and `_LEGAL_TRANSITIONS` but does not define them.
- The LangGraph subgraph topology (Phase-6 S3-01) — emits `TransitionEvent`s via its conditional edges but does not define them.
- The HITL resume validator (Phase-6 S4-01) — consumes `AwaitingHumanReview.handoff_path` and the `awaiting_human_review → plan_ready` legal transition but does not define them.
- A `BaseLedgerState` / `BaseLedgerVariant` ABC — see Anti-refactor #1 above.

## Notes for the implementer

- **Why the seven variants + closed transition table matter so much.** `final-design.md §"State model"` commits the entire Phase-6 + Phase-6.5 + Phase-9 stack to those exact seven names + the closed-set of legal edges. The Phase-9 worker (`TemporalVulnRemediationSut`) will replay events through the *same* transition table, byte-for-byte; the Phase-6.5 bench harness will score scorecards keyed on the *same* terminal partition. Adding an eighth variant or a new transition edge is an ADR-0001 + ADR-0003 amendment; do not silently expand `_LEGAL_TRANSITIONS`. The AC-15 contract snapshot test fails loud if you do.

- **Why composition (not inheritance) for shared payloads.** Phase-3 `transforms/outcomes.py` is the canonical precedent: `RecipeError` is a frozen sub-model injected as a field, never inherited. If `GateFailedRetryable.failing_signals` and (say) `AwaitingHumanReview.failing_signals_at_handoff` end up looking similar in S2-01 / S4-01, the right move is to extract a `GateFailureEvidence` frozen sub-model and inject it as a field on both — NOT to introduce a `WithFailingSignals` mixin. CLAUDE.md "composition over inheritance" is load-bearing here.

- **Why `_LEGAL_TRANSITIONS` is a `frozenset`, not a registry.** The seven-variant universe + the legal edges are closed-set Phase-6 data, not pluggable strategies. Three similar lines is better than premature abstraction (Rule 2). The rule-of-three threshold for a transition-table *registry* would be hit only when Phase 7 (migration), Phase 8+ (hierarchical planner task classes), and a hypothetical Phase 10+ each have their own ledger sum types and their own transition tables. At that point, a `@register_ledger_kind(LedgerKind)` registry mirroring `@register_probe` / `@register_dep_graph_strategy` would let new ledgers land additively. This story deliberately does NOT build that registry — but the file naming (`vuln_ledger.py`, not `ledger.py`) and the per-phase home (`codegenie/workflows/`, scoped to vuln) are written so the registry can be introduced additively when the threshold is reached. If you find yourself wanting to add a second ledger sum type in this story, stop and re-scope.

- **`TransitionId` vs `EventId` — keep them distinct.** They have different lifecycles and different consumers:
  - `EventId` (Phase-3 S6-01) — the append-only forensic two-stream event-log id; consumed by the event-log writer + log readers; never participates in replay verification.
  - `TransitionId` (this story) — the per-transition ledger event id; chained for replay determinism; consumed by the checkpoint store (S2-01) + replay verifier (S2-02); the chain-head walk reads `TransitionId` order, not `EventId` order.

  Conflating them would couple the replay path to the forensic-log path and break the Phase-9 substrate-portability story.

- **Why the chain-head helper has an AST no-side-effects fence.** ADR-0003 §"Consequences" requires that "Failed verification transitions to `FailedUnrecoverable`." If the chain-head computation ever depends on the clock, env, randomness, or filesystem state, the *same* event sequence would produce *different* chain heads across the `LocalVulnRemediationSut` (in-process LangGraph) and `TemporalVulnRemediationSut` (Temporal Activity worker) substrates — every Phase-9 replay would fail verification and emit `FailedUnrecoverable(reason="checkpoint_integrity")` *spuriously*. The AST fence catches the moment any future story adds an offending import; it starts trivially passing in this story and starts biting in S2-01 / S5-01.

- **Why `_FROZEN_FORBID` must be imported, not re-declared.** S1-01's AC-4 + the validation report establish single-canonical-declaration as load-bearing — multiple declarations would let a future drift land on one of them and leave the other stale (e.g., `ConfigDict(frozen=False, extra="forbid")`). The AC-12 AST fence enforces. Import once at module top; use as `model_config = _FROZEN_FORBID` on every `BaseModel` subclass.

- **Phase-7 migration ledger — file naming is the Open/Closed substrate.** Today there is one ledger (this story's `VulnLedgerState`). Phase 7 will add `MigrationLedgerState` for the distroless-migration task class. The two are *different* sum types with *different* transition tables — there is no shared base, no shared registry yet. The file lives at `src/codegenie/workflows/vuln_ledger.py` (vuln-specific name) so Phase 7 can land `src/codegenie/workflows/migration_ledger.py` beside it without editing this story's file. Open/Closed at the file boundary, anticipating but not building the ledger registry the rule-of-three would justify only at the third concrete ledger.
