# S4-01 — HITL interrupt and resume

**Status:** HARDENED
**Validated:** 2026-05-26 — see [`_validation/S4-01-hitl-interrupt-and-resume.md`](_validation/S4-01-hitl-interrupt-and-resume.md).
**Depends on:**
- [`S1-01-sut-contract-types.md`](S1-01-sut-contract-types.md) — `_FROZEN_FORBID`, `__all__` allowlist sentinel, contract-snapshot meta-test.
- [`S1-02-ledger-state-union.md`](S1-02-ledger-state-union.md) — `AwaitingHumanReview` variant, `HumanReviewReason` Literal, `_LEGAL_TRANSITIONS` (`awaiting_human_review → plan_ready` is the legal "approved resume" edge), `TransitionEvent` model, `FailedUnrecoverable.reason` closed set.
- [`S2-01-semantic-checkpoints.md`](S2-01-semantic-checkpoints.md) — `CheckpointStore` Protocol (`tail_chain_head`, `iter_persisted_chain`, `append`), in-memory + SQLite adapter parity matrix.
- [`S2-02-replay-verification.md`](S2-02-replay-verification.md) — `hydrate_or_fail`, `Hydrated`, `HydrationResult` — the resume path runs the integrity gate FIRST; only after `Hydrated` does the resume validator decide.
- [`S3-01-plugin-local-subgraph.md`](S3-01-plugin-local-subgraph.md) — currently emits the placeholder `Escalate(reason="awaiting_human_review")` on retry exhaustion; this story replaces the placeholder with the typed HITL payload and lands the `AwaitingHumanReview` ledger boundary write.

**This story does NOT:**
- Add a new ledger variant or transition edge (`_LEGAL_TRANSITIONS` from S1-02 is byte-equal-unchanged — the `awaiting_human_review → {plan_ready, completed, failed_unrecoverable}` edges already exist).
- Add a new `HumanReviewReason` value (the four S1-02 values cover the universe; an additive value is an ADR-0001 + S1-02 amendment, not this story's scope).
- Touch the `CheckpointStore` Protocol (the resume path reads through existing methods; no new method).
- Own the LangGraph `Interrupt`-node wiring (S3-01 owns the routing; this story ships the typed payload + validator the routing consumes).
- Own the end-to-end kill→approve→resume integration golden (S6-01 owns that scenario; this story ships every unit + boundary test that golden composes).

**Goal:** Land the **typed HITL interrupt + resume-validator substrate** that final-design.md item 5 mandates ("HITL is a discriminated-union outcome carrying reason, evidence, and resumption contract. 'Paused' is not a boolean side channel.") as four additive concerns over S1-02 + S2-01 + S2-02 + S3-01:

1. **The closed `HitlInterrupt` discriminated union** at `src/codegenie/workflows/hitl.py` — one frozen Pydantic variant per `HumanReviewReason` value (`NoConcreteMatch | TrustOutcomeFailed | PolicyViolationUnrecoverable | MultiPackageCve`), each carrying its variant-specific *evidence payload* (the evidence half of final-design.md item 5's "reason, evidence, and resumption contract"). Mirrors the project-canonical `Annotated[..., Field(discriminator="kind")]` over `_FROZEN_FORBID` Pydantic models pattern (`VulnLedgerState` is the in-phase sibling; `ReplayVerdict` is the in-module sibling).
2. **The `ResumeInput` Pydantic model + `ApprovalToken` newtype** — the *resumption contract* half of item 5. Carries `workflow_id`, `approval_token`, `approved_at` (timezone-aware UTC datetime), `expected_chain_head` (binds the approval to a specific checkpoint chain head — prevents approving a stale view of the world), and `expected_handoff_digest` (BLAKE3 of the handoff artifact the human reviewed — prevents approving a token while the artifact was concurrently mutated). Resume input is frozen + `extra="forbid"`; the newtype `ApprovalToken` is constructed by the `mint_approval_token` smart constructor (the SOLE sanctioned construction site).
3. **The `ResumeVerdict` closed sum type + the `resume_or_reject` integrity-policy gate** — mirrors S2-02's `ReplayVerdict` / `hydrate_or_fail` pattern verbatim. `ResumeVerdict = ResumeAccepted | StaleApproval | MalformedApproval | AlreadyResumed | WorkflowNotPaused`. The `resume_or_reject(store, resume_input) -> ResumeAccepted | FailedUnrecoverable` function is the SOLE site mapping any non-`ResumeAccepted` verdict to a structural rejection (returning the typed sum-type variant — NOT raising — so `phase-arch-design.md §"Failure modes"` row 4 "reject and remain paused" is structurally enforced). The resume gate runs `hydrate_or_fail` first; only on `Hydrated` does the resume validator decide.
4. **The retry-exhaustion → `AwaitingHumanReview` ledger boundary write + S3-01 placeholder replacement** — when the subgraph's retry counter hits `MAX_RETRIES` (the S3-01-pinned exact value), the orchestrator emits the typed `HitlInterrupt` (NOT the S3-01 placeholder `Escalate(reason="awaiting_human_review")` — which is replaced byte-for-byte at the relevant boundary), appends the `TransitionEvent(prior_state_id=<gate_failed_retryable | patch_applied>, next_state_id="awaiting_human_review", ...)` via the checkpoint store, and returns clean exit. The "remains paused" invariant is structurally enforced by an AST fence over `resume_or_reject` mirroring S2-02's "fail-closed before hydrate" fence: the reject arms MUST NOT append a `TransitionEvent` with `next_state_id ∈ {"plan_ready", "completed", "failed_unrecoverable"}`.

This story is the fourth-concrete-consumer of the *kernel-tier typed-substrate-and-sole-site-policy-gate* pattern within Phase-6 (S1-02 ledger union + S2-01 store + S2-02 verifier + this) — the rule-of-three threshold for *that pattern* is met; the rule-of-three for *registries of HITL interrupts* is NOT met (we have one HITL surface, not three) — Anti-refactor #1 below explicitly rejects a `HitlInterruptRegistry` premature abstraction.

## References

- [final-design.md](../final-design.md) §"Decisions of record" item 5 (verbatim "Typed interruption. HITL is a discriminated-union outcome carrying reason, evidence, and resumption contract. 'Paused' is not a boolean side channel." — drives AC-1 through AC-4); §"Main workflow" step 6 (the four-routing matrix; `repeated failure or policy block → AwaitingHumanReview` is this story's emission boundary — AC-9); §"State model" (`AwaitingHumanReview` is one of the three terminal variants but is *operationally resumable* via `awaiting_human_review → plan_ready` — AC-7 + Notes-for-implementer on the two-definitions-of-terminal discipline already pinned in `_attempts/_lessons.md`); §"Relationship to Phase 6.5" (Phase 6.5 may NOT depend on the HITL internals — drives AC-12 unchanged-`__all__` only for the public surface; the variant classes and the `resume_or_reject` gate are private to the kernel via convention OR re-exported, see AC-12).
- [phase-arch-design.md](../phase-arch-design.md) §"Scenarios" #3 verbatim ("Gate fails twice, graph emits `AwaitingHumanReview`, process exits cleanly, resume input is validated, approved transition continues from the latest verified checkpoint." — AC-9 + AC-10 integration golden); §"Failure modes" row 4 ("stale human resume token | resume validator | reject and remain paused" — AC-3 + AC-4 + AC-8 AST fence); §"Process view" (the `G->>L: checkpoint terminal / retry / interrupt` arrow is the AC-9 boundary; the resume arc enters back through `G->>L: verify + hydrate` — i.e. `hydrate_or_fail` runs FIRST on resume).
- [ADRs/0001-stable-vuln-remediation-sut-contract.md](../ADRs/0001-stable-vuln-remediation-sut-contract.md) §Decision — `VulnRemediationResult` carries `terminal_state`; `awaiting_human_review` is one of the three `TerminalState` Literal values. The retry-exhaustion path produces a SUT result whose `terminal_state == "awaiting_human_review"` (AC-9). Drift between this story's emission and the `TerminalState` Literal is caught by S1-01's `__all__` allowlist meta-test (Phase-6 contract snapshot extension — AC-13).
- [ADRs/0003-checkpointed-ledger-replay-boundary.md](../ADRs/0003-checkpointed-ledger-replay-boundary.md) §Decision ("verify the previous chain head before hydration on resume" — drives AC-6: `resume_or_reject` runs `hydrate_or_fail` FIRST; resume-validator decides only on `Hydrated`); §Consequences ("Failed verification transitions to `FailedUnrecoverable`" — the integrity-failure path on resume; this story does NOT add a parallel `FailedUnrecoverable` site, it re-uses `hydrate_or_fail`).
- [High-level-impl.md](../High-level-impl.md) §"Step 4 — HITL and failure routing" verbatim ("Add typed interrupt payloads and resume validation. Distinguish retryable, terminal, and failed-unrecoverable states. Prove stale approvals are rejected.").
- [S1-02-ledger-state-union.md](S1-02-ledger-state-union.md) §"Acceptance criteria" — `AwaitingHumanReview.review_reason: HumanReviewReason`; `_LEGAL_TRANSITIONS` includes `(awaiting_human_review, plan_ready)`, `(awaiting_human_review, completed)`, `(awaiting_human_review, failed_unrecoverable)`. AC-7 cross-table-consistency test asserts the four `HitlInterrupt` variant `kind` slugs are byte-equal to `get_args(HumanReviewReason)`.
- [S2-02-replay-verification.md](S2-02-replay-verification.md) §"Acceptance criteria" — `hydrate_or_fail` is the SOLE integrity-policy gate; this story's `resume_or_reject` composes it (does NOT duplicate the chain-recomputation logic). The fail-closed AST fence pattern (`tests/fence/test_hydrate_no_state_construction.py`) is the precedent the AC-8 "remains paused" fence mirrors.
- [S3-01-plugin-local-subgraph.md](S3-01-plugin-local-subgraph.md) §"Goal" + §"Out of scope" — S3-01 emits the placeholder `Escalate(reason="awaiting_human_review")` at the relevant boundary; this story replaces the placeholder. The Phase-6 `EscalationReason` Literal in `transforms/outcomes.py` does NOT currently include `"awaiting_human_review"`; the placeholder is replaced by an *additive* call into `hitl.emit_interrupt(...)` that appends the typed ledger boundary write — `EscalationReason` is NOT amended (AC-7 + Anti-refactor #4).
- [`src/codegenie/workflows/replay.py`](../../../../src/codegenie/workflows/replay.py) — the canonical sibling for AC-1 (closed discriminated union over `_FROZEN_FORBID` variants) + AC-2 (frozen Pydantic `ResumeInput` model) + AC-5 (`resume_or_reject` mirrors `hydrate_or_fail` shape) + AC-8 (AST fence over the reject arms mirrors `test_hydrate_no_state_construction.py`).
- [`src/codegenie/workflows/vuln_ledger.py`](../../../../src/codegenie/workflows/vuln_ledger.py) — `HumanReviewReason` import target; `AwaitingHumanReview` construction site; `_LEGAL_TRANSITIONS` byte-equal-unchanged check.
- [`src/codegenie/workflows/__init__.py`](../../../../src/codegenie/workflows/__init__.py) — current 15-name `__all__` allowlist; AC-12 grows it additively per the S1-01 / S1-02 / S2-01 / S2-02 precedent.
- [`tests/fence/test_workflows_public_surface.py`](../../../../tests/fence/test_workflows_public_surface.py) — public-surface sentinel; AC-12 extends additively.
- [`tests/fence/test_hydrate_no_state_construction.py`](../../../../tests/fence/test_hydrate_no_state_construction.py) — the AC-8 "remains paused on reject" AST fence mirrors this fence's walker.
- [`tests/integration/test_phase6_sut_contract_snapshot.py`](../../../../tests/integration/test_phase6_sut_contract_snapshot.py) — contract-snapshot meta-test; AC-13 extends with the HITL-shaped delta.
- Phase-3 sum-type precedent: [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) §`HumanReviewReason` (the closed four-value Literal this story's variant `kind` slugs are byte-equal to); §`RequiresHumanReview` (the orchestrator-domain sibling — different umbrella; cross-domain identity NOT asserted because the two unions answer different questions, per the `_lessons.md` "Hydrated.kind MUST be a NEW closed tag" rule).
- Cross-cutting AST-fence precedent: [`tests/fence/test_chain_head_purity.py`](../../../../tests/fence/test_chain_head_purity.py) — the pure-helper no-side-effects walker pattern. AC-2 helper `_canonical_approval_message` is a pure helper; the fence walked-modules constant is extended additively.
- [`docs/phases/06-sherpa-vuln-loop/stories/_attempts/_lessons.md`](_attempts/_lessons.md) — the four cross-story lessons this story consumes: (a) "Two definitions of 'terminal' coexist in Phase 6" — `awaiting_human_review` is class-level terminal but operationally resumable; AC-7 enforces; (b) "Store types do NOT enter `codegenie.workflows.__all__`" — AC-12 keeps `ResumeVerdict` variant classes inside the module; only the public-surface contract names land in `__all__`; (c) "Detection-substrate-only vs integrity-policy is a load-bearing separation" — `resume_or_reject` is integrity-policy, the store is detection-only; AC-6 asserts; (d) "Sanitization-aware fold = fold over the sanitized-reconstructed event, not the live event" — the `TransitionEvent` for the resume-accept arm carries a sanitized `triggering_outcome`; AC-9 chain-head computation rides through S2-02's reconstruction pipeline (no parallel sanitization).

## Acceptance criteria

### Typed HITL interrupt (the "reason + evidence" half of item 5)

- [ ] **AC-1 — Canonical module + closed four-variant `HitlInterrupt` discriminated union.** `src/codegenie/workflows/hitl.py` declares exactly four `BaseModel` subclasses, one per `HumanReviewReason` value:
  - `NoConcreteMatch` (`kind: Literal["no_concrete_match"] = "no_concrete_match"`) — payload: `cve_id: str` (Phase-3 newtype if available, else `str` with the `^CVE-\d{4}-\d{4,}$` regex `field_validator`), `failed_strategies: tuple[str, ...]` (capped at 16; each item ≤ 128 chars).
  - `TrustOutcomeFailed` — payload: `failing_signals: tuple[SignalKind, ...]` (reuses existing newtype), `attempt_number: AttemptNumber` (reuses existing newtype; matches `GateFailedRetryable.attempt_number`).
  - `PolicyViolationUnrecoverable` — payload: `policy_id: ErrorId` (reuses existing newtype; dotted-snake-case per Phase-1 ADR-0007 grammar), `details: str` (capped at 1024 chars).
  - `MultiPackageCve` — payload: `cve_id: str` (same regex validator as `NoConcreteMatch`), `affected_packages: tuple[PackageName, ...]` (capped at 64; reuses existing newtype).

  Each variant declares `model_config = _FROZEN_FORBID` imported from the canonical site (no inlined `ConfigDict` — the AST fence at `tests/fence/test_workflows_frozen_forbid.py` walks `hitl.py` after AC-12 extends it). The umbrella:
  ```python
  HitlInterrupt = Annotated[
      NoConcreteMatch | TrustOutcomeFailed
      | PolicyViolationUnrecoverable | MultiPackageCve,
      Field(discriminator="kind"),
  ]
  ```

  A static test asserts (i) exactly four `BaseModel` subclasses are defined in `hitl.py` that are members of `HitlInterrupt` (the `ResumeInput` + `ResumeAccepted` + `StaleApproval` + `MalformedApproval` + `AlreadyResumed` + `WorkflowNotPaused` models are separately enumerated by AC-2 / AC-3 — the AC-1 walker filters by membership in the `HitlInterrupt` union); (ii) the multiset of `kind` Literals across the four `HitlInterrupt` variants is byte-equal to `set(get_args(HumanReviewReason))`; (iii) removing `discriminator="kind"` from the umbrella fails the discriminator-round-trip test (mutation thinking: structural-matching fallback would let `{"kind": "trust_outcome_failed", "failing_signals": (), "attempt_number": 0}` silently decode to `NoConcreteMatch` if field shapes overlap).

  **Mutation thinking:** A mutant that ships only three variants (omitting `MultiPackageCve`) fails the AC-1 byte-equality with `HumanReviewReason` get_args; a mutant that uses `ConfigDict(frozen=True, extra="forbid")` inline fails the AC-12 frozen-forbid fence walker; a mutant that uses raw `str` for `policy_id` instead of `ErrorId` fails the AC-14 mypy --strict closeout.

### Resumption contract (the "resumption contract" half of item 5)

- [ ] **AC-2 — `ApprovalToken` newtype + `mint_approval_token` smart constructor.** `ApprovalToken = NewType("ApprovalToken", str)` lands at the canonical kernel-tier identifier home (`src/codegenie/types/identifiers.py`) — additive Phase-6 catalog entry beneath `TransitionId`. The smart constructor `mint_approval_token(workflow_id, chain_head, handoff_digest, ts_utc) -> ApprovalToken` is the SOLE sanctioned construction site; it returns `f"approval:{blake3_hex(canonical_message_bytes)}"` where `canonical_message_bytes` is the pure helper `_canonical_approval_message(workflow_id, chain_head, handoff_digest, ts_utc) -> bytes` (newline-delimited canonical fields in fixed order, UTF-8 — the bytes-determinism is enforced by an AST no-side-effects fence walker over `_hitl.py`, mirroring `test_chain_head_purity.py`).

  An AST chokepoint test (`tests/fence/test_approval_token_construction.py`) walks `src/codegenie/` and asserts the only call sites that pass `ApprovalToken(...)` directly are inside `mint_approval_token` (mirrors the `BundleCacheKey` chokepoint precedent in `compose_bundle_cache_key` documented in `identifiers.py`). The newtype is added to the `_NEWTYPE_REGISTRY` drift test (Phase-3 ADR-0010 catalog).

  **Mutation thinking:** A mutant that uses `f"approval:{uuid4().hex}"` (non-deterministic) fails the AC-5 idempotency test (same inputs → same token). A mutant that omits `chain_head` from the canonical message fails the AC-3 stale-approval test (a token minted for chain head A would silently accept against chain head B).

- [ ] **AC-3 — `ResumeInput` frozen Pydantic model carrying the seven resumption-contract fields.**
  ```python
  class ResumeInput(BaseModel):
      model_config = _FROZEN_FORBID
      workflow_id: WorkflowId
      approval_token: ApprovalToken
      approved_at: datetime          # timezone-aware UTC; field_validator rejects naive
      expected_chain_head: ChainHead
      expected_handoff_digest: BlobDigest
      approver_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-@.]+$")
      reviewer_note: str = Field(default="", max_length=4096)
  ```
  A `model_validator(mode="after")` recomputes `mint_approval_token(workflow_id, expected_chain_head, expected_handoff_digest, approved_at)` and asserts byte-equality with the carried `approval_token` (binding the token to the four canonical fields prevents partial-record tampering). A static test (`tests/unit/workflows/test_resume_input.py`) parametrizes seven distinct mutation classes: (a) drift the `approval_token` by one hex char; (b) shift `approved_at` by 1 microsecond; (c) replace `expected_chain_head` with a sibling chain head; (d) replace `expected_handoff_digest` with a sibling digest; (e) pass naive `datetime` (no tz); (f) pass `approver_id=""`; (g) pass `approver_id="bob;rm -rf /"` (regex rejects); each mutation MUST surface `pydantic.ValidationError`.

  **Mutation thinking:** A mutant validator that drops the token-recomputation check passes (a)–(d) silently — letting a forged token through. The model-validator AC catches that. A mutant that allows naive datetime (a `field_validator` that returns `v` unchanged for naive timestamps) lets an attacker re-mint a token at a different wall-clock time and pass the recomputation — the (e) test catches that. A mutant that defaults `approver_id=""` to "system" silently approves on behalf of a non-existent reviewer — (f) catches that.

### Resume verdict + sole-site policy gate (mirrors S2-02 `ReplayVerdict` / `hydrate_or_fail`)

- [ ] **AC-4 — `ResumeVerdict` closed five-variant discriminated union.** `src/codegenie/workflows/hitl.py` declares:
  ```python
  class ResumeAccepted(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["accepted"] = "accepted"
      workflow_id: WorkflowId
      transitioned_at: ChainHead          # the new chain head after the resume TransitionEvent is appended
      events: tuple[TransitionEvent, ...] # the hydrated chain up to and including the resume event

  class StaleApproval(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["stale_approval"] = "stale_approval"
      reason: Literal["chain_head_drift", "handoff_digest_drift", "approval_age_exceeded"]
      observed_chain_head: ChainHead
      expected_chain_head: ChainHead

  class MalformedApproval(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["malformed_approval"] = "malformed_approval"
      reason: Literal["token_recompute_mismatch", "workflow_id_unknown", "pydantic_validation_error"]
      detail: str = Field(max_length=512)

  class AlreadyResumed(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["already_resumed"] = "already_resumed"
      observed_state: LedgerStateKind         # whatever the ledger now reports (not "awaiting_human_review")

  class WorkflowNotPaused(BaseModel):
      model_config = _FROZEN_FORBID
      kind: Literal["workflow_not_paused"] = "workflow_not_paused"
      observed_state: LedgerStateKind         # e.g. "needs_plan" if the workflow never reached HITL

  ResumeVerdict = Annotated[
      ResumeAccepted | StaleApproval | MalformedApproval
      | AlreadyResumed | WorkflowNotPaused,
      Field(discriminator="kind"),
  ]
  ```
  A static test asserts (i) exactly five variant classes; (ii) the multiset of `kind` Literals is `{"accepted", "stale_approval", "malformed_approval", "already_resumed", "workflow_not_paused"}`; (iii) the `match` in `_dispatch_resume_verdict` has exactly five `case` arms + `case _: assert_never(verdict)` drift guard (AST-walked, mirroring S2-02's `_dispatch_verdict` arm-counting test).

  **Mutation thinking:** Collapsing `StaleApproval` and `AlreadyResumed` into a single `Rejected(reason=...)` variant breaks AC-8's "remains paused on stale" vs "no-op on already resumed" distinguishability — the integration tests at AC-10 will fail because the `remains_paused` assertion takes a different path from the `idempotent_replay` assertion.

- [ ] **AC-5 — `resume_or_reject(store, resume_input) -> ResumeAccepted | FailedUnrecoverable` — the SOLE integrity-policy site.** The function:
  1. Calls `hydrate_or_fail(store, resume_input.workflow_id)`. If the result is `FailedUnrecoverable`, returns it byte-equal-unchanged (S2-02 owns integrity policy; this story does NOT duplicate or shadow). The resume gate's purpose is to layer the *approval-policy* check on top of the *integrity-policy* check.
  2. Inspects `Hydrated.latest_state_kind`. If `!= "awaiting_human_review"`, returns `WorkflowNotPaused(observed_state=latest_state_kind)` wrapped through `_dispatch_resume_verdict` (see step 5).
  3. Re-mints the canonical approval token from `(workflow_id, expected_chain_head, expected_handoff_digest, approved_at)` and compares byte-for-byte against `resume_input.approval_token`. On mismatch, returns `MalformedApproval(reason="token_recompute_mismatch")`. (The `ResumeInput` model-validator at AC-3 already enforces this; the gate re-checks defense-in-depth — a Pydantic model can be constructed with `.model_construct()` bypassing validators, so the gate MUST NOT trust the model alone.)
  4. Compares `resume_input.expected_chain_head` against `store.tail_chain_head(workflow_id)`. On mismatch, returns `StaleApproval(reason="chain_head_drift", ...)`.
  5. Computes `now_utc - approved_at`; if `> _APPROVAL_TTL_SECONDS` (module-level `Final[int] = 86400` — 24-hour TTL, justified in Notes-for-implementer), returns `StaleApproval(reason="approval_age_exceeded", ...)`.
  6. Walks the hydrated events to detect whether a `TransitionEvent(prior_state_id="awaiting_human_review", next_state_id="plan_ready")` has already been persisted for the same `expected_chain_head`. If yes, returns `AlreadyResumed(observed_state=Hydrated.latest_state_kind)`.
  7. On all checks passing, appends the resume `TransitionEvent(prior_state_id="awaiting_human_review", next_state_id="plan_ready", triggering_outcome={"kind": "resume_accepted", "approval_token": ..., "approver_id": ...}, evidence_digest=blake3(canonical_resume_input_bytes), chain_head=<recomputed by the store>, transition_id=<fresh ULID>, workflow_id=...)` via the `CheckpointStore.append` Protocol method (substrate-agnostic — works for both InMemory and SQLite adapters per the S2-01 parity matrix). Returns `ResumeAccepted(...)`.
  8. The non-accepted verdicts are funneled through `_dispatch_resume_verdict(verdict: ResumeVerdict) -> ResumeAccepted | FailedUnrecoverable` whose four non-accepted arms each return `ResumeAccepted`'s NEGATION — i.e., the function's *return type* is the closed two-variant `ResumeAccepted | FailedUnrecoverable` ONLY when the caller is the public `resume_or_reject` entry point. The non-`ResumeAccepted` verdicts surface through a sibling public function `resume_with_full_verdict(store, resume_input) -> ResumeVerdict` for testability + future telemetry; the integrity-policy gate (`resume_or_reject`) wraps it and folds non-accepted verdicts into `FailedUnrecoverable(reason="policy_violation", error=RemediationError(error_id="workflows.hitl_resume_rejected", message=<verdict.detail or verdict.reason>))` ONLY when the caller explicitly opts into the fold (i.e., `resume_with_full_verdict` is the canonical surface; `resume_or_reject` is the convenience wrapper for the orchestrator code path that maps to `RemediationOutcome`). See Notes-for-implementer §"Why two surfaces" for the rationale.

  **Mutation thinking:** A mutant gate that skips step (1) — runs the approval-policy check without the integrity-policy check first — silently accepts a tampered chain. The AC-6 integration test plants a torn-write and expects `FailedUnrecoverable(reason="checkpoint_integrity")`, NOT a `ResumeAccepted`. A mutant gate that skips step (6) — does NOT detect already-resumed — would let a replayed token append a *second* `(awaiting_human_review, plan_ready)` transition (the `_LEGAL_TRANSITIONS` check passes — that edge IS legal — but the workflow state is already `plan_ready`, so AC-11 cross-table-consistency catches it via a NEW assertion: appending a transition whose `prior_state_id` doesn't match `tail_state_kind` is rejected at the `append` boundary).

### Cross-table consistency, mutation-resistance closeout, and AST fences

- [ ] **AC-6 — Resume runs `hydrate_or_fail` FIRST; integrity failure short-circuits before approval-policy.** Three integration tests at `tests/integration/workflows/test_resume_integrity_precedence.py`:
  1. **Tampered chain + valid approval token** → `resume_or_reject` returns `FailedUnrecoverable(reason="checkpoint_integrity")`; the resume `TransitionEvent` is NOT appended (assert `store.tail_chain_head` is unchanged after the call).
  2. **Empty workflow + valid approval token** → `FailedUnrecoverable(reason="checkpoint_integrity")` (no rows to verify; the resume gate cannot resume a workflow that never started).
  3. **Clean chain + valid approval token + workflow in `awaiting_human_review`** → `ResumeAccepted`; the resume `TransitionEvent` IS appended; `store.tail_chain_head` advances; the latest hydrated state is `plan_ready`.

  **Mutation thinking:** A mutant that runs approval-policy before integrity-policy passes the third test but fails the first — a forged token against a tampered chain would silently accept. The ordering invariant is structurally enforced by the AC-8 AST fence walker.

- [ ] **AC-7 — Cross-table consistency between `HitlInterrupt` variants and the ledger.**
  1. **Forward consistency:** every `HitlInterrupt` variant `kind` slug is a member of `get_args(HumanReviewReason)`. Hypothesis property test at `tests/unit/workflows/test_hitl_consistency.py`: `@given(st.sampled_from([variant.__name__ for variant in get_args(HitlInterrupt)[0]]))` confirms every variant constructs an `AwaitingHumanReview(review_reason=<kind slug>)` without `pydantic.ValidationError`.
  2. **Backward consistency:** every `get_args(HumanReviewReason)` value has exactly one corresponding `HitlInterrupt` variant whose `kind` slug equals that value. Drift in either direction (adding a `HumanReviewReason` value without a matching `HitlInterrupt` variant, or vice versa) fails this test loud with a message naming the missing pair.
  3. **Two-definitions-of-terminal discipline:** an assertion that `awaiting_human_review` IS in `_TERMINAL_LEDGER_KINDS` (class-level terminal) AND `("awaiting_human_review", "plan_ready") IN _LEGAL_TRANSITIONS` (operationally resumable). This documents the in-phase invariant from `_attempts/_lessons.md` "two definitions of terminal coexist."
  4. **Sibling-domain identity NOT asserted:** the test docstring explicitly says "`HitlInterrupt` and `RequiresHumanReview` (transforms/outcomes.py) share the `HumanReviewReason` Literal but are intentionally NOT identity-tested — they answer different questions and live in different umbrellas, per the `_lessons.md` 'Hydrated.kind MUST be a NEW closed tag' rule."

- [ ] **AC-8 — "Remains paused on reject" AST fence.** New fence `tests/fence/test_hitl_no_state_advance_on_reject.py` walks `src/codegenie/workflows/hitl.py` (loaded via `ast.parse(Path(...).read_text())`) and asserts:
  1. Every function with a return annotation of `ResumeVerdict` OR `ResumeAccepted | FailedUnrecoverable` is walked.
  2. In each control-flow arm whose return-value AST traces to a variant that is NOT `ResumeAccepted` (i.e., `StaleApproval`, `MalformedApproval`, `AlreadyResumed`, `WorkflowNotPaused`, `FailedUnrecoverable`), there MUST NOT be any `ast.Call` whose `func` resolves to `<store-name>.append(` (i.e., no `TransitionEvent` appended on reject arms).
  3. Conversely, on the `ResumeAccepted` arm, there MUST be exactly one `store.append(TransitionEvent(...))` call. Mirrors the S2-02 `test_hydrate_no_state_construction.py` pattern.
  4. A meta-test (`tests/fence/test_hitl_no_state_advance_on_reject_meta.py`) plants a broken `hitl.py` fixture in `tests/_fence_fixtures/hitl_broken_reject_arm.py` that appends on the reject arm; the meta-test asserts the AST fence test fails loud when pointed at it. This is the S2-02 AC-15 parity-meta mutation-guard precedent.

  **Mutation thinking:** An executor under time pressure might "helpfully" emit a `TransitionEvent(prior_state_id="awaiting_human_review", next_state_id="failed_unrecoverable")` on the `StaleApproval` arm to "record the rejection in the ledger." That would silently *advance* the workflow into a terminal state — the human reviewer could no longer retry the approval. The "remains paused" invariant requires that the workflow stays in `awaiting_human_review` regardless of how many bad approvals the operator submits. The fence catches this mutation at compile-time-equivalent — before any test ever runs.

### Retry exhaustion → AwaitingHumanReview boundary write + placeholder replacement

- [ ] **AC-9 — `emit_interrupt(store, workflow_id, interrupt, prior_state_id, triggering_outcome_payload)` appends the `AwaitingHumanReview` boundary write.** The public function `emit_interrupt(...)` lives at `src/codegenie/workflows/hitl.py`. It:
  1. Asserts `prior_state_id ∈ {"gate_failed_retryable", "patch_applied", "plan_ready"}` (the three S1-02 ledger states with a legal outgoing edge to `awaiting_human_review`) — via the `_LEGAL_TRANSITIONS` membership check; an illegal `prior_state_id` raises `ValueError` with a message naming the legal set (mutation thinking: a mutant that passes `prior_state_id="needs_plan"` would silently create an illegal transition; the model-validator on `TransitionEvent` already catches this, but the explicit check at the function boundary gives a better diagnostic).
  2. Constructs a `TransitionEvent(prior_state_id=<arg>, next_state_id="awaiting_human_review", triggering_outcome=<serialized HitlInterrupt>, evidence_digest=blake3(canonical_interrupt_bytes), chain_head=<store-computed>, transition_id=<fresh ULID>, workflow_id=...)` and appends via `CheckpointStore.append`. The triggering_outcome is `interrupt.model_dump(mode="json")` — Pydantic-serialised; the `HumanReviewReason` Literal naturally round-trips.
  3. Returns the new `tail_chain_head` (for orchestrator caller to use as the result digest).

  An integration test at `tests/integration/workflows/test_emit_interrupt.py` parametrizes over the four `HitlInterrupt` variants × three legal `prior_state_id` values = 12 cases; each case constructs the interrupt, calls `emit_interrupt`, and asserts (i) the chain head advanced; (ii) the persisted `TransitionEvent` round-trips through `TransitionEvent.model_validate_json(...)` byte-equal to the input; (iii) the `AwaitingHumanReview(review_reason=<interrupt.kind>)` is what `hydrate_or_fail` reports as `Hydrated.latest_state_kind`'s associated review reason (cross-checked via the hydrated events' tail).

  **Mutation thinking:** A mutant `emit_interrupt` that drops `prior_state_id="patch_applied"` from the allowed set silently rejects the most common HITL trigger (gates fail on a patch the planner applied). The 12-case parametrization catches that. A mutant that uses `model_dump()` (Python dict, not JSON-serializable for `JsonValue`) breaks the chain-head computation because the canonical bytes differ; AC-9 (ii) catches that.

- [ ] **AC-10 — End-to-end retry-exhaustion → pause → approve → resume scenario.** Integration test at `tests/integration/workflows/test_phase6_scenario3_hitl_resume.py` codifies phase-arch-design.md §"Scenarios" #3 verbatim:
  1. Start a workflow at `needs_plan`.
  2. Drive it through `plan_ready → patch_applied → gate_failed_retryable` twice (the S3-01 `MAX_RETRIES = 3` boundary).
  3. On the third gate failure, the orchestrator calls `emit_interrupt(store, workflow_id, TrustOutcomeFailed(failing_signals=(...), attempt_number=AttemptNumber(3)), prior_state_id="gate_failed_retryable", ...)`. Assert `store.tail_chain_head` advances; assert `hydrate_or_fail` reports `Hydrated.latest_state_kind == "awaiting_human_review"`; assert process can cleanly exit (no open handles, store closeable).
  4. New process / new `ReplayVerifier` (substrate-agnostic) starts fresh. Operator constructs `ResumeInput(workflow_id=..., approval_token=mint_approval_token(...), approved_at=now_utc(), expected_chain_head=<tail>, expected_handoff_digest=<digest>, approver_id="alice@example.com")`.
  5. `resume_or_reject(store, resume_input)` returns `ResumeAccepted(transitioned_at=<new_chain_head>, events=(...))`. The hydrated state is `plan_ready`. The workflow can continue (next-call into the subgraph would attempt `plan_ready → patch_applied`).

  **Negative scenarios in the SAME test file** to enforce the four reject classes:
  - **Stale chain head:** plant a sibling `TransitionEvent` between pause and resume (mutates the chain head); the resume returns `FailedUnrecoverable(reason="checkpoint_integrity")` (S2-02's gate fires first because the chain doesn't recompute).
  - **Stale handoff digest:** mint the token against handoff digest A; pass handoff digest B in `expected_handoff_digest`; the token recomputation fails → `MalformedApproval(reason="token_recompute_mismatch")` (or `FailedUnrecoverable` if `resume_or_reject` folds — see AC-5 step 8).
  - **Stale approval age:** mint token with `approved_at = now_utc() - timedelta(days=2)` and call `resume_or_reject` with mocked time; returns `StaleApproval(reason="approval_age_exceeded")` (or folded).
  - **Already resumed:** call `resume_or_reject` twice with the same `ResumeInput`; second call returns `AlreadyResumed(observed_state="plan_ready")` (or folded). The store has exactly one `(awaiting_human_review, plan_ready)` transition — not two.
  - **Workflow not paused:** call `resume_or_reject` on a workflow in `patch_applied`; returns `WorkflowNotPaused(observed_state="patch_applied")` (or folded).

- [ ] **AC-11 — InMemory + SQLite adapter parity for the resume path.** The S2-01 parity contract test (`tests/contract/workflows/test_checkpoint_store_parity.py`) is extended additively with a `resume_or_reject` parametrize case: a fixed `(setup_chain, resume_input)` tuple produces byte-equal `ResumeVerdict` instances across both adapters (the `events` tuple inside `ResumeAccepted` is compared element-by-element via the Pydantic `model_dump(mode="json")` round-trip — bytewise canonical). Mirrors the S2-02 AC-6 verifier-parity test verbatim.

  **Mutation thinking:** A SQLite-specific shortcut (e.g., reaching past the Protocol to call `store._conn.execute(SELECT...)`) inside `resume_or_reject` would break the InMemory parity test on the first run. Resist (a Phase-9 Postgres adapter would also break).

### Closeout — `__all__`, contract snapshot, mypy --strict, anti-refactor enforcement

- [ ] **AC-12 — `codegenie.workflows.__all__` allowlist grows additively.** The current 15-name allowlist (from S1-01 + S1-02 + S2-02) grows to 21 by adding the public-surface HITL contract names:
  - `HitlInterrupt` (the umbrella)
  - `NoConcreteMatch`, `TrustOutcomeFailed`, `PolicyViolationUnrecoverable`, `MultiPackageCve` (the four variant classes — needed because Phase 6.5's bench harness builds `HitlInterrupt` instances directly for case fixtures)
  - `ResumeInput`
  - `ApprovalToken` (re-exported from `codegenie.types.identifiers` per the `TransitionId` precedent in `__init__.py`)

  The `ResumeVerdict` variant classes (`ResumeAccepted`, `StaleApproval`, `MalformedApproval`, `AlreadyResumed`, `WorkflowNotPaused`) and the `_dispatch_resume_verdict` helper are NOT in `__all__` (Phase 6.5 may NOT depend on the resume-verdict internals — `_lessons.md` "Store types do NOT enter `codegenie.workflows.__all__`" precedent). The functions `mint_approval_token`, `emit_interrupt`, `resume_or_reject`, `resume_with_full_verdict` ARE in `__all__` (the harness needs them for the bench's HITL fixture builder).

  Total new public names: 8 (4 variant classes + `HitlInterrupt` + `ResumeInput` + `ApprovalToken` + the four functions, minus the existing 15). Final `__all__` byte-equality test at `tests/fence/test_workflows_public_surface.py` asserts the sorted-tuple `("ApprovalToken", "AwaitingHumanReview", "Completed", "FailedUnrecoverable", "GateFailedRetryable", "HitlInterrupt", "LedgerStateKind", "MultiPackageCve", "NeedsPlan", "NoConcreteMatch", "PatchApplied", "PlanReady", "PolicyViolationUnrecoverable", "ResumeInput", "SutDigest", "TransitionEvent", "TransitionId", "TrustOutcomeFailed", "VulnLedgerState", "VulnRemediationCase", "VulnRemediationResult", "VulnRemediationSut", "emit_interrupt", "mint_approval_token", "resume_or_reject", "resume_with_full_verdict")` is exactly the public surface — 26 names total. Drift in either direction (silent addition OR removal) fails the fence test loud.

- [ ] **AC-13 — Contract-snapshot meta-test extended additively.** `tests/integration/test_phase6_sut_contract_snapshot.py` grows three new snapshot rows (one for `HitlInterrupt`, one for `ResumeInput`, one for `ResumeVerdict`) — each a frozen `model_json_schema()` snapshot under `tests/golden/phase6-contract-snapshot/`. The meta-test pairs (one additive case, one breaking case) for each of the three new rows extend the classifier's mutation-resistance per the S1-01 / S1-02 / S2-01 / S2-02 precedent: a new variant added is additive; removing a variant is breaking; removing a required field is breaking; renaming a `kind` Literal is breaking.

- [ ] **AC-14 — `mypy --strict` + `make lint` + `make lint-imports` green on the new modules.** The closed `HumanReviewReason` Literal + `Annotated[..., Field(discriminator="kind")]` umbrella + `_dispatch_resume_verdict` `match` with `assert_never` make the type narrowing load-bearing. `make typecheck` runs to zero errors over the new files; `ruff` is clean; `import-linter` shows no new boundary violations (the `hitl.py` module's imports are confined to `codegenie.workflows`, `codegenie.transforms.outcomes`, `codegenie.types`, `codegenie.workflows.checkpoints`, `codegenie.workflows.replay`; no cross-plugin imports).

  **Mutation thinking:** A mutant that drops `assert_never` from the `_dispatch_resume_verdict` `match` _technically_ passes runtime tests (no path triggers `case _:`) — but `mypy --strict` flags the missing-arm narrowing if a sixth `ResumeVerdict` variant lands later. The AST arm-counting test at AC-4 (iii) is the runtime defense; `assert_never` is the type-system defense; both load-bearing in different mutation classes.

## Files to touch

- `src/codegenie/workflows/hitl.py` — **create** — the four-variant `HitlInterrupt` union + `ResumeInput` + five-variant `ResumeVerdict` union + `emit_interrupt` + `resume_or_reject` + `resume_with_full_verdict` + `_dispatch_resume_verdict`.
- `src/codegenie/workflows/_hitl.py` — **create** — pure helpers (`_canonical_approval_message`, `_now_utc`). Walked by the AC-8 fence + the existing `test_chain_head_purity.py` fence (extended additively).
- `src/codegenie/workflows/__init__.py` — **modify** — re-export the 8 new public names (AC-12).
- `src/codegenie/types/identifiers.py` — **modify** — add the `ApprovalToken` newtype + `_NEWTYPE_REGISTRY` entry.
- `tests/unit/workflows/test_hitl_consistency.py` — **create** — AC-1 variant shape + AC-7 cross-table consistency.
- `tests/unit/workflows/test_resume_input.py` — **create** — AC-3 seven mutation-class tests.
- `tests/unit/workflows/test_resume_verdict_shape.py` — **create** — AC-4 variant shape + dispatch arm count.
- `tests/unit/workflows/test_mint_approval_token.py` — **create** — AC-2 determinism + AST chokepoint mate.
- `tests/integration/workflows/test_resume_integrity_precedence.py` — **create** — AC-6 three scenarios.
- `tests/integration/workflows/test_emit_interrupt.py` — **create** — AC-9 twelve-case parametrize.
- `tests/integration/workflows/test_phase6_scenario3_hitl_resume.py` — **create** — AC-10 end-to-end positive + negatives.
- `tests/contract/workflows/test_checkpoint_store_parity.py` — **modify** — extend AC-11 with `resume_or_reject` parity case.
- `tests/fence/test_hitl_no_state_advance_on_reject.py` — **create** — AC-8 AST fence.
- `tests/fence/test_hitl_no_state_advance_on_reject_meta.py` — **create** — AC-8 (iv) parity-meta mutation guard.
- `tests/fence/test_approval_token_construction.py` — **create** — AC-2 chokepoint walker (only `mint_approval_token` may construct `ApprovalToken(...)`).
- `tests/_fence_fixtures/hitl_broken_reject_arm.py` — **create** — fixture for AC-8 (iv) meta-test.
- `tests/fence/test_workflows_public_surface.py` — **modify** — grow the sentinel allowlist additively (AC-12).
- `tests/fence/test_workflows_frozen_forbid.py` — **modify** — walk `hitl.py` additively.
- `tests/fence/test_chain_head_purity.py` — **modify** — extend walked-modules to include `_hitl.py` additively.
- `tests/integration/test_phase6_sut_contract_snapshot.py` — **modify** — extend with `HitlInterrupt` + `ResumeInput` + `ResumeVerdict` snapshot rows + 6 meta-test cases (AC-13).
- `tests/unit/types/test_identifiers_drift.py` — **modify** — `_NEWTYPE_REGISTRY` extended with `ApprovalToken`.
- `docs/phases/06-sherpa-vuln-loop/ADRs/0001-stable-vuln-remediation-sut-contract.md` — **modify** — append a 2026-05-26 amendment paragraph noting the 8-name `__all__` extension is additive and consequent on Phase-6 S4-01; no breaking change to the `VulnRemediationSut` Protocol or the `TerminalState` Literal.

## TDD plan

### Red phase (write failing tests first; one PR-equivalent commit per AC)

1. AC-1 — write `test_hitl_consistency.py::test_ac1_variant_set` asserting four classes + byte-equal `kind` slugs. Confirm RED (no `hitl.py` module yet).
2. AC-2 — write `test_mint_approval_token.py::test_ac2_determinism` (same args → same token) + `test_ac2_canonical_bytes_purity` (no FS/time side effects in `_canonical_approval_message`). Confirm RED.
3. AC-3 — write `test_resume_input.py::test_ac3_token_recomputation` + seven mutation-class parametrize. Confirm RED.
4. AC-4 — write `test_resume_verdict_shape.py::test_ac4_variant_set` + `test_ac4_dispatch_arm_count`. Confirm RED.
5. AC-5 — write `test_resume_or_reject_unit.py::test_ac5_step_ordering` (mock each step in sequence; assert ordering invariant). Confirm RED.
6. AC-6 — write `test_resume_integrity_precedence.py` three scenarios. Confirm RED.
7. AC-7 — write `test_hitl_consistency.py::test_ac7_forward_backward_cross_table`. Confirm RED.
8. AC-8 — write `test_hitl_no_state_advance_on_reject.py` (fence) + `test_hitl_no_state_advance_on_reject_meta.py` (parity-meta). Confirm RED (the fence has no module to walk; the meta-test has no fixture).
9. AC-9 — write `test_emit_interrupt.py` 12-case parametrize. Confirm RED.
10. AC-10 — write `test_phase6_scenario3_hitl_resume.py` positive + five negative scenarios. Confirm RED.
11. AC-11 — extend `test_checkpoint_store_parity.py` with the resume parametrize. Confirm RED.
12. AC-12 — extend `test_workflows_public_surface.py` sentinel allowlist with the 8 new names (the assertion is `frozenset(actual) == frozenset(expected)`; the new names are not yet exported, so RED).
13. AC-13 — extend `test_phase6_sut_contract_snapshot.py` with three new snapshot rows + six meta-test cases. Confirm RED (no snapshot files yet).
14. AC-14 — run `make typecheck` and `make lint` — confirm RED on the import-but-no-module errors.

### Green phase (minimum code to pass each)

- Land `src/codegenie/workflows/_hitl.py` with `_canonical_approval_message(workflow_id, chain_head, handoff_digest, ts_utc) -> bytes` (pure: tuple of UTF-8 fields joined by `\n`, no FS/time).
- Land `src/codegenie/workflows/hitl.py` with the four `HitlInterrupt` variants + the umbrella; the `ResumeInput` model + its `model_validator`; the five `ResumeVerdict` variants + the umbrella; `mint_approval_token` smart constructor; `emit_interrupt`; `resume_with_full_verdict`; `resume_or_reject` (the convenience wrapper); `_dispatch_resume_verdict`. Module-level constants: `_APPROVAL_TTL_SECONDS: Final[int] = 86400`; `_RESUME_REJECTED_ERROR_ID: Final[ErrorId] = ErrorId("workflows.hitl_resume_rejected")`.
- Land the `ApprovalToken` newtype in `identifiers.py` + drift-registry entry.
- Extend `codegenie.workflows.__all__` with the 8 new names.
- Extend the contract-snapshot golden files under `tests/golden/phase6-contract-snapshot/`.
- Generate the AC-8 meta-test fixture `tests/_fence_fixtures/hitl_broken_reject_arm.py` (the broken module that appends on the reject arm).
- Run `make check` — confirm all GREEN.

### Refactor phase

- Extract any 3+ repeated string-literal `reason` slugs to module-level `Final[str]` constants.
- Replace any boolean intermediate in `resume_or_reject` (e.g., `is_stale: bool`) with the typed verdict directly — the function should walk the step sequence and return early on the first non-`Verified`/`Hydrated` result; intermediate booleans are anti-pattern noise.
- Inline any helper that's used at exactly one site and clarifies nothing.
- Confirm `make typecheck` + `make lint` + `make lint-imports` + `pytest -q` all GREEN after refactor.

### Anti-refactor (REJECT these abstractions — they violate Rule 2 / Open-Closed-at-the-file-boundary discipline)

1. **No `HitlInterruptRegistry` / `@register_hitl_variant` decorator.** Rule-of-three for HITL interrupt-class registration is *not* met (we have one HITL surface — `vulnerability-remediation`; Phase-7 `migration` ships its own HITL surface, not a shared registry). The closed four-variant union with `Annotated[..., Field(discriminator="kind")]` IS the contract; adding a fifth is an ADR amendment, not a runtime decoration. (Mirrors S1-02 Anti-refactor #2 and S3-02 Anti-refactor #1.)
2. **No `BaseHitlInterrupt` ABC.** Composition wins (Phase-3 `transforms/outcomes.py` precedent — `RecipeError` is *composed into* `RecipeFailed`, never inherited). The four variants share `kind: Literal[...]` + `model_config = _FROZEN_FORBID` — that's structural identity at the class level, not subtype identity.
3. **No `ResumeStrategy` Strategy abstraction.** The integrity-policy + approval-policy gate IS the one canonical policy. A `ResumeStrategy` Protocol would let a future plugin substitute a weaker policy — directly contradicting final-design.md item 6 "No new trust bypass."
4. **No amendment of `EscalationReason` to include `"awaiting_human_review"`.** The S3-01 placeholder `Escalate(reason="awaiting_human_review")` is replaced by an *additive* call into `emit_interrupt(...)` — `EscalationReason` is byte-equal-unchanged. The two unions (`EscalationReason` and `HumanReviewReason`) answer different questions (pre-subgraph escalation vs in-subgraph HITL); conflating them would couple the orchestrator pre-subgraph path to the HITL surface.
5. **No `time.time()` / `datetime.utcnow()` in `_hitl.py`.** The canonical message bytes are pure; the wall-clock read happens at the ORCHESTRATOR boundary (the caller passes `now_utc()` into `mint_approval_token`) — mirrors S2-01's `sanitize_for_persistence` purity discipline. The AC-2 chain-head-purity fence walker enforces.
6. **No `HitlResumeCache` / token replay-protection cache.** Replay protection is achieved by the `(workflow_id, expected_chain_head)` pair: once `(awaiting_human_review, plan_ready)` is appended for `chain_head=X`, no second `(awaiting_human_review, plan_ready)` can be appended for the same `chain_head=X` (the next workflow state is `plan_ready`, so AC-5 step (6) "already resumed" detection fires). The CHAIN itself is the replay-protection mechanism; caching tokens externally adds a second source of truth that can drift.
7. **No `Approval` typed exception class.** Reject paths return the typed verdict; they do NOT raise. The integrity-policy gate's contract is total — every input maps to a verdict, never an exception. (Mirrors S2-02 Anti-refactor #3 "No boolean return from `verify()` — the tagged union IS the contract.")
8. **No async `resume_or_reject` / `emit_interrupt`.** Sync. The orchestrator wraps in `asyncio.to_thread` (same pattern S2-01 pinned for `append`). Async would force every Protocol to gain an async sibling, breaking the S2-01 substrate-portability.
9. **No `HitlInterrupt` field promoted to `AwaitingHumanReview` payload.** The interrupt's `evidence` payload lives on the `TransitionEvent.triggering_outcome` field (as the serialized `interrupt.model_dump(mode="json")`). Promoting it to `AwaitingHumanReview` (e.g., `AwaitingHumanReview.evidence: HitlInterrupt`) would couple the ledger sum type to the HITL surface — a Phase-7 ledger amendment for a `migration` HITL flavor would force every Phase-6 ledger row to grow a payload it doesn't need. The `triggering_outcome` carrier is the open generic substrate per S1-02 design.
10. **No new `FailedUnrecoverableReason` value.** The closed five-value Literal in S1-02 covers the HITL-reject mapping via `"policy_violation"`. Adding `"hitl_rejected"` would be a parallel-naming anti-pattern.
11. **No consolidated test file.** Each AC's tests live in their own file (mirrors S1-02 / S2-02 / S3-02 per-AC split discipline). A single `test_hitl.py` covering everything in one file makes the discriminator-collision failure mode harder to debug.
12. **No `ResumeInput.approval_signature: bytes` cryptographic-signature field.** Phase-6 is *local*-only (final-design.md "Phase 6 stays local"); the chain-head + handoff-digest binding IS the integrity defense. A signature field would require key-management infrastructure (out of scope) and could become a false-security blanket. Phase-9 Temporal may add signatures additively if multi-process trust boundaries emerge.

## Out of scope

- LangGraph `Interrupt` node wiring inside the subgraph — S3-01 owns the routing (it currently emits the `Escalate(reason="awaiting_human_review")` placeholder; this story replaces the placeholder via `emit_interrupt(...)` calls from the boundary; the routing-table-shaped substrate is unchanged).
- The end-to-end CLI surface for `codegenie remediate resume <workflow-id> --token=...` — Phase-3 S6-05 owns the `remediate` CLI; the resume subcommand is a Phase-7+ follow-on.
- Multi-reviewer / quorum approval — Phase-9 Temporal durability may grow it; out of scope here.
- Cryptographic-signature backed approval tokens — see Anti-refactor #12.
- Cross-substrate approval-token portability (e.g., a token minted by the InMemory substrate consumable by the SQLite substrate) — the canonical message is byte-deterministic across both, so this is naturally satisfied without dedicated tests; if it diverges, AC-11 catches it.
- Approval-token revocation — no use case; if the chain advances (e.g., `gate_failed_retryable → failed_unrecoverable` from a different operator), the resume's `expected_chain_head` would drift and `StaleApproval(reason="chain_head_drift")` fires automatically.
- Phase-6 row in `tests/e2e/scenarios.yaml` — phase-arch-design.md §"Cross-cutting test-architecture additions" pins the e2e + workflow-replay-determinism property to S6-01 (closeout). This story's `test_phase6_scenario3_hitl_resume.py` is the unit-level slice; the e2e row is S6-01's scope.
- `tests/property/test_workflow_replay_determinism.py` — same; S6-01 owns the workflow-scope Hypothesis property.

## Notes for the implementer

### Why two surfaces (`resume_or_reject` vs `resume_with_full_verdict`)

`resume_with_full_verdict(store, resume_input) -> ResumeVerdict` is the canonical contract — every input maps to one of five verdicts. It's the testable surface (per-verdict integration tests can assert specific reject reasons).

`resume_or_reject(store, resume_input) -> ResumeAccepted | FailedUnrecoverable` is the convenience wrapper for the orchestrator code path: it composes `resume_with_full_verdict` with a folder that maps the four reject variants to `FailedUnrecoverable(reason="policy_violation", error=RemediationError(error_id="workflows.hitl_resume_rejected", ...))`. The fold loses information (the specific reject reason) but gives the orchestrator a closed two-variant union it can `match` on without exhaustiveness ceremony.

This two-surface design mirrors S2-02's `ReplayVerifier.verify(...) -> ReplayVerdict` (canonical) vs `hydrate_or_fail(...) -> HydrationResult` (convenience). The two-surface split is the precedent; do not collapse to one.

### Why the canonical approval message must include `expected_chain_head` AND `expected_handoff_digest`

The chain head pins the ledger state at the time of approval; the handoff digest pins the artifact the human reviewed. Either alone is insufficient:

- **Chain head only:** if the human approves at chain head A but the orchestrator concurrently rewrote the handoff artifact (e.g., a partial-completion bug regenerates `handoff.md` mid-pause), the chain head is unchanged but the artifact is different. The reviewer's mental model is stale; the approval should reject.
- **Handoff digest only:** if the handoff digest is unchanged but the chain head advanced (e.g., another operator approved and resumed concurrently), the workflow is already `plan_ready`; the second approval should detect "already resumed" — `AlreadyResumed` is the right verdict, not silent re-execution.

Both fields together create a *complete pinning* of the system state the reviewer evaluated.

### Why 24-hour TTL for `_APPROVAL_TTL_SECONDS`

Empirical default that matches engineer working-hours patterns (an approval minted Friday afternoon is still valid Monday morning; an approval older than that is suspicious). The constant is module-local; operators can configure via env var in a future story (Phase-7 follow-on). Make the constant a `Final[int]` so a future config-driven version is a one-line refactor.

The constant is NOT in `__all__` — it's a private policy knob. Tests inject mocked time via `freezegun` or a `_now_utc()` indirection in `_hitl.py`.

### Why `WorkflowId` re-export at the boundary, not a "WorkflowId is HITL's primary key" coupling

The `WorkflowId` newtype belongs to the kernel (S1-01 + S1-02). The `ResumeInput` and `HitlInterrupt` types CONSUME it as a foreign key but do not own it. This keeps the substrate identifier home centralized (production ADR-0010) and prevents Phase-7's HITL surface from re-declaring it.

### Why `_lessons.md`'s "two definitions of terminal" matters here

`AwaitingHumanReview` is a class-level terminal (S1-01 `TerminalState` Literal) — i.e., from the `VulnRemediationResult.terminal_state` contract perspective, a workflow that returns there is a "completed run" from the SUT's call.

But `AwaitingHumanReview` is operationally resumable — `_LEGAL_TRANSITIONS` includes `(awaiting_human_review, plan_ready)`. The next call to the SUT for the same `WorkflowId` (via the resume path) re-enters the subgraph.

This means tests that conflate the two definitions trip. AC-7 (iii) explicitly tests the dual nature: assert `"awaiting_human_review" in _TERMINAL_LEDGER_KINDS` AND assert `("awaiting_human_review", "plan_ready") in _LEGAL_TRANSITIONS` — both must hold for the design to work.

### Why `EscalationReason` is NOT amended

S3-01 emits a placeholder `Escalate(reason="awaiting_human_review")` BUT `EscalationReason` does not currently include that value — meaning S3-01's placeholder is technically illegal at the closed-Literal level. This story's `emit_interrupt` call REPLACES that placeholder; after S4-01 lands, the placeholder line in S3-01's implementation should be deleted (an additive cleanup, not a breaking change since the placeholder was unreachable in practice). If the executor finds `EscalationReason` does include the slug (S3-01 amended additively), the cleanup is a no-op.

**Verify during execution:** grep `EscalationReason` for the current literal set; grep `plugins/vulnerability-remediation--node--npm/subgraph/` for `Escalate(reason="awaiting_human_review")`. The two states matter:

- If found in code and NOT in `EscalationReason` → S3-01 has a latent bug; this story's `emit_interrupt` replaces the call site; record in attempt log.
- If found in code and IS in `EscalationReason` → S3-01 amended `EscalationReason`; this story replaces the call site additively + adds an attempt-log note suggesting the future "remove `awaiting_human_review` from `EscalationReason` once all call sites use `emit_interrupt`" cleanup story.
- If not found in code → S3-01 didn't ship the placeholder; this story's `emit_interrupt` lands the FIRST emission boundary (the `subgraph/` boundary node that detects retry exhaustion calls into `emit_interrupt` directly).

### Why the AST fence walks the FULL function-graph, not just direct returns

A mutant could refactor `resume_or_reject` to call a private `_record_rejection(store, resume_input, verdict)` helper that appends a `TransitionEvent` "to log the rejection." The AST fence at AC-8 must walk the full call graph of any function annotated `-> ResumeVerdict | ResumeAccepted | FailedUnrecoverable` — not just the immediate function body. The recommended implementation:

1. Parse `hitl.py` via `ast.parse(Path("src/codegenie/workflows/hitl.py").read_text())`.
2. Build a function-name → AST-node map.
3. For each function `f` with the target return annotation, walk its body; on any `ast.Call` whose function reference resolves (via the name map) to a *local* helper, recurse into that helper.
4. In every walked block, on any control-flow arm whose `ast.Return` value resolves to a non-`ResumeAccepted` variant, assert NO `store.append(...)` call appears between the entry to the arm and the return.

This is more involved than S2-02's fence (which walked a single function); the precedent is the chain-head-purity fence's deep walker. Pin the implementation as a small AST-helper class in `tests/fence/_ast_helpers.py` to keep the test file thin.

### Why per-AC test files (not consolidated)

Mirrors S1-02 / S2-02 / S3-02 per-AC split discipline. A single `test_hitl.py` covering everything in one file:
- Makes the discriminator-collision failure mode (AC-1) hard to triage when an unrelated AC's fixture mutates module-level state.
- Lets a thin parametrize over the four `HitlInterrupt` variants accidentally satisfy AC-1 + AC-7 + AC-9 with the same loop body — masking AC-specific mutation classes.
- Forces test-file imports to grow O(N²) as ACs accumulate.

The 10-test-file count above looks high but each file is small (60-150 lines). Total test code budget is ~1200 lines — same order of magnitude as S2-02's hardened story.

### Why `make refresh-cassettes` is NOT needed for this story

No Anthropic-call replay cassettes are recorded against this story's code path — `hitl.py` is pure Python + checkpoint store reads. The closed-substrate fence at `tests/fence/test_pyproject_fence.py` is unchanged.

### Implementation order suggestion

1. Land `_hitl.py` + `_canonical_approval_message` first (pure, no upstream deps).
2. Land `ApprovalToken` newtype + `mint_approval_token` + the AC-2 chokepoint fence.
3. Land the four `HitlInterrupt` variant classes + the umbrella (AC-1).
4. Land `ResumeInput` + the AC-3 model-validator (AC-3).
5. Land the five `ResumeVerdict` variants + `_dispatch_resume_verdict` (AC-4).
6. Land `emit_interrupt` (AC-9) — needs `HitlInterrupt` but not the resume path.
7. Land `resume_with_full_verdict` (AC-5 + AC-6) — needs everything above.
8. Land `resume_or_reject` (the convenience wrapper) (AC-5 step 8).
9. Grow `codegenie.workflows.__all__` + the public-surface sentinel (AC-12).
10. Extend the contract-snapshot golden files + meta-test cases (AC-13).
11. Run `make check` + the new property tests; iterate to green.
12. AST fence at AC-8 lands LAST — by then `hitl.py` is stable and the fence can be tested against a known-good module.

Anything that breaks the parity matrix (AC-11) likely means a substrate-specific shortcut leaked in; rip it out and route everything through the `CheckpointStore` Protocol.
