# Validation report — S4-01 (HITL interrupt and resume)

**Date:** 2026-05-26
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief. Mirrors the in-phase precedent set by the S1-01, S1-02, S2-01, S2-02, S3-01, and S3-02 validations: the pre-validation file was a 17-line stub, the four lenses converged sharply, and spawning four parallel critic agents would have burned tokens without changing the verdict.)
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S4-01-hitl-interrupt-and-resume.md`](../S4-01-hitl-interrupt-and-resume.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* matches the design — `final-design.md §"Decisions of record"` item 5 ("Typed interruption. HITL is a discriminated-union outcome carrying reason, evidence, and resumption contract. 'Paused' is not a boolean side channel.") + `phase-arch-design.md §"Scenarios"` #3 (retry-exhaustion → pause → approve → resume) + `phase-arch-design.md §"Failure modes"` row 4 ("stale human resume token | resume validator | reject and remain paused") + `High-level-impl.md §"Step 4 — HITL and failure routing"` triple-pin the substrate concerns. But the pre-validation 17-line story file left every load-bearing decision implicit. Specifically:

1. **Goal vague.** "Emit typed HITL interrupts and validate resume input" doesn't name the artifact (module path), the type universe (which discriminated union? which variant classes?), the resume-input fields, or the integrity-policy gate. The executor would invent shapes incompatible with the rest of Phase-6.
2. **Zero AC checkboxes (three dash bullets).** No individually-verifiable assertions; the Validator pass downstream could not binary-pass-fail. Mirrors the exact failure pattern S1-02, S2-01, S2-02, S3-01, S3-02 all surfaced in pre-validation.
3. **"Retry exhaustion" undefined.** No definition of *when* retry exhausts — `attempt_number >= MAX_RETRIES` (the S3-01-pinned exact value)? `GateFailedRetryable` count? A mutant `MAX_RETRIES = 1` would silently pause on the first gate failure and "pass" the original AC.
4. **"Typed HITL interrupts" un-typed.** No payload shape, no variant universe, no `Annotated[..., Field(discriminator="kind")]` discipline named. An executor would likely ship a single `HitlInterrupt(reason: str, evidence: dict)` anaemic model — directly contradicting final-design.md item 5's "discriminated-union" mandate.
5. **"Stale" undefined.** By timestamp? By chain head? By handoff digest? By workflow_id binding? By approver_id replay? The phase-arch-design.md row 4 ("stale human resume token") gives no further guidance. An executor would pick one staleness dimension, miss the others, and silently accept a forged token.
6. **"Malformed" undefined.** Unparseable JSON? Missing required fields? Wrong workflow_id? Token-signature mismatch? Each is a different Pydantic + control-flow path. The mutation-resistance bar is invisible without enumeration.
7. **No integrity-policy precedence.** Resume input validation must run AFTER `hydrate_or_fail` succeeds — otherwise a tampered chain plus a *legitimate* approval token would be silently accepted. The story didn't name this ordering; an executor would either invent a parallel chain-recomputation (duplicating S2-02 — anti-pattern, drift hazard) or skip the integrity check entirely (silent-tamper-acceptance hazard).
8. **"Latest verified checkpoint" un-anchored.** The phrase appears in `phase-arch-design.md §"Scenarios" #3` verbatim but the resume gate must consume S2-02's `Hydrated.latest_state_kind` — the story didn't say so. An executor might re-query `store.tail_chain_head()` directly (substrate-only, no integrity check — silent regression).
9. **No "remains paused" structural enforcement.** `phase-arch-design.md §"Failure modes"` row 4 says "reject AND remain paused." Without an AST fence ensuring the reject arms don't append a `TransitionEvent`, an executor could "helpfully" emit a `(awaiting_human_review, failed_unrecoverable)` row on the stale-approval arm — silently advancing the workflow into a terminal state where the human reviewer can no longer retry.
10. **No interaction with S3-01 placeholder.** S3-01's hardened story explicitly defers the typed payload + resume validator to S4-01 and emits a placeholder `Escalate(reason="awaiting_human_review")`. But `EscalationReason` (in `transforms/outcomes.py`) does NOT currently include `"awaiting_human_review"` — the placeholder is technically illegal at the closed-Literal level. The pre-validation story did not address the boundary handoff at all.
11. **No `HumanReviewReason` cross-table consistency.** The S1-02 `AwaitingHumanReview.review_reason: HumanReviewReason` Literal is the closed four-value universe. Without a cross-table assertion that every `HitlInterrupt` variant maps to exactly one `HumanReviewReason` value (and vice versa), a future fifth `HumanReviewReason` value would land silently with no matching interrupt payload — a drift hazard that compounds across Phase-7's `migration` HITL surface.
12. **No idempotency / replay-protection discipline.** Replaying the same approval token must be a no-op (or rejected); the original story didn't address this. An executor might detect this only via runtime test flakiness ("works once, fails on the second test run because the chain advanced").
13. **No `__all__` / contract-snapshot extension.** Every Phase-6 story (S1-01, S1-02, S2-01, S2-02, S3-01, S3-02) extends the public-surface allowlist + the contract-snapshot meta-test additively. The pre-validation file said nothing.
14. **No `mypy --strict` AC.** Standard closeout gate; the discriminator union + `match`-with-`assert_never` are the load-bearing strictness checks.
15. **No anti-refactor block.** The "make it pluggable" reflex was unguarded: an executor under deadline pressure could ship a `HitlInterruptRegistry` / `@register_hitl_variant` decorator + `BaseHitlInterrupt` ABC + `ResumeStrategy` Protocol — every one a premature abstraction the Phase-6 architectural decisions explicitly reject (ADR-0001 stable contract + final-design.md item 5 closed-union mandate + Rule 2 "Simplicity first").
16. **No mutation-resistance pass.** Every original AC was satisfiable by a trivial implementation: "Retry exhaustion enters `AwaitingHumanReview`" passes with a mutant that *always* enters `AwaitingHumanReview` regardless of retry state; "Resume rejects stale or malformed approval payloads" passes with a mutant that *always* rejects (the "approved resume" AC catches one direction but not the other); "Approved resume continues from latest verified checkpoint" passes with a mutant that ignores the resume input entirely and just calls `hydrate_or_fail`.

All in-place fixable, none requires re-running `phase-story-writer`. The story's structure (one-sentence goal, three vague ACs, three-line TDD plan) survives in shape — three ACs grew to 14 numbered checkbox ACs across five labeled sub-sections, the TDD plan was reordered with the 12-item anti-refactor block, References / Files-to-touch / Out-of-scope / Notes-for-implementer were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (pre-validation):** "Emit typed HITL interrupts and validate resume input before continuation." Vague — no module path, no type universe, no integrity-policy ordering, no replay protection.
- **Goal (post-validation):** ship `src/codegenie/workflows/{_hitl,hitl}.py` carrying (i) the closed four-variant `HitlInterrupt` discriminated union (one variant per `HumanReviewReason` Literal value), (ii) the `ResumeInput` Pydantic model + `ApprovalToken` newtype + `mint_approval_token` smart constructor, (iii) the closed five-variant `ResumeVerdict` sum type + `_dispatch_resume_verdict` with exhaustive `match`, (iv) the `resume_or_reject` integrity-policy gate (which runs `hydrate_or_fail` FIRST then layers approval-policy on `Hydrated`), (v) the `emit_interrupt` boundary-write function replacing S3-01's `Escalate(reason="awaiting_human_review")` placeholder, (vi) the AC-8 "remains paused on reject" AST fence + meta-mutation guard, and (vii) the parity matrix + contract-snapshot + `__all__` closeout. This story is the fourth concrete consumer of the *typed-substrate-and-sole-site-policy-gate* pattern in Phase-6 (S1-02 ledger + S2-01 store + S2-02 verifier + this).
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### Authoritative sources

- **final-design.md** §"Decisions of record" item 5 verbatim (typed interruption with reason + evidence + resumption contract; "'Paused' is not a boolean side channel" — drives AC-1 + AC-3 + AC-4 closed-union shape); §"Main workflow" step 6 ("repeated failure or policy block → `AwaitingHumanReview`" — drives AC-9 retry-exhaustion emission); §"State model" (`AwaitingHumanReview` is class-level terminal but operationally resumable — drives AC-7 (iii) dual-nature invariant).
- **phase-arch-design.md** §"Scenarios" #3 verbatim ("Gate fails twice, graph emits `AwaitingHumanReview`, process exits cleanly, resume input is validated, approved transition continues from the latest verified checkpoint." — AC-9 + AC-10 integration scenario); §"Failure modes" row 4 verbatim ("stale human resume token | resume validator | reject and remain paused" — AC-3 + AC-4 + AC-8 fence + AC-10 negative scenarios); §"Process view" (`G->>L: checkpoint terminal / retry / interrupt` is AC-9's emission boundary; `G->>L: verify + hydrate` on resume is AC-5 / AC-6's integrity-policy precedence).
- **ADR-0001** §Decision — `VulnRemediationResult.terminal_state` carries `awaiting_human_review`; AC-12 + AC-13 keep the public surface byte-equal.
- **ADR-0003** §Decision ("verify the previous chain head before hydration on resume" — drives AC-6 integrity-policy precedence) + §Consequences ("Failed verification transitions to `FailedUnrecoverable`" — the integrity-failure path on resume; this story re-uses `hydrate_or_fail`, does NOT add a parallel site).
- **High-level-impl.md** §"Step 4 — HITL and failure routing" verbatim ("Add typed interrupt payloads and resume validation. Distinguish retryable, terminal, and failed-unrecoverable states. Prove stale approvals are rejected.").
- **S2-02 hardened story** — the SOLE-site integrity-policy gate (`hydrate_or_fail`) precedent + the AST fence (`test_hydrate_no_state_construction.py`) precedent + the parity matrix + the contract-snapshot extension pattern + the "two surfaces" public-API split (canonical + convenience wrapper). This story mirrors S2-02 line-by-line at the structural level.
- **S3-01 hardened story** — currently emits `Escalate(reason="awaiting_human_review")` placeholder; this story replaces the placeholder via `emit_interrupt(...)`. The `EscalationReason` Literal in `transforms/outcomes.py` does NOT currently include the value — surfaced in Notes-for-implementer §"Why `EscalationReason` is NOT amended" with explicit grep instructions for the executor.
- **`src/codegenie/workflows/vuln_ledger.py`** — `HumanReviewReason` import; `AwaitingHumanReview` construction; `_LEGAL_TRANSITIONS` byte-equal-unchanged check.
- **`src/codegenie/workflows/replay.py`** — `hydrate_or_fail` (the AC-5 dependency); the `Hydrated.latest_state_kind` field (AC-5 step 2 dispatch); the fence at `test_hydrate_no_state_construction.py` (AC-8 pattern precedent).
- **`src/codegenie/transforms/outcomes.py`** §`HumanReviewReason` (closed four-value Literal — AC-7 byte-equality target); §`HumanReviewReason` value set: `"no_concrete_match"`, `"trust_outcome_failed"`, `"policy_violation_unrecoverable"`, `"MULTI_PACKAGE_CVE"`; §`EscalationReason` (closed seven-value Literal that does NOT currently include `"awaiting_human_review"` — Notes-for-implementer addresses the S3-01 placeholder).
- **`_attempts/_lessons.md`** — four cross-story lessons consumed: (a) "two definitions of terminal coexist" — AC-7 (iii); (b) "store types do NOT enter `__all__`" — AC-12 keeps `ResumeVerdict` variants private; (c) "detection-substrate-only vs integrity-policy" — AC-6 ordering invariant; (d) "sanitization-aware fold" — AC-9 (ii) round-trip via the S2-02 reconstruction pipeline.

### Hardest design tensions resolved

**Tension 1 — `HitlInterruptRegistry` vs closed-`Annotated[..., Field(discriminator="kind")]`.** The Phase-6 architectural decision (final-design.md item 5 closed-union mandate + ADR-0001 stable contract + S1-02 sum-type precedent + Anti-refactor #2 of every Phase-6 story so far) makes the closed union the right shape. Rule-of-three for *registries of HITL interrupts* is unmet (we have one HITL surface — `vulnerability-remediation`; Phase-7 ships its own HITL surface, not a shared registry). Resolution: closed `Annotated[..., Field(discriminator="kind")]`, fourth concrete consumer of the closed-Pydantic-sum-type pattern (S1-02 ledger + S2-02 verdict + S2-02 hydration result + this). Anti-refactor #1 explicit.

**Tension 2 — `HitlInterrupt` payload coupling to the ledger.** Should `AwaitingHumanReview` grow an `evidence: HitlInterrupt` field? The S1-02 design left the `TransitionEvent.triggering_outcome: JsonValue` open generic substrate precisely for this case — domain payloads ride through `triggering_outcome`, the ledger sum type stays neutral. Coupling `AwaitingHumanReview.evidence` to `HitlInterrupt` would force a Phase-7 ledger amendment for `migration` HITL flavors (a sibling sum type) — the ledger would need an `evidence: HitlInterrupt | MigrationHitl` union. Resolution: keep the payload at `TransitionEvent.triggering_outcome`; the ledger sum type is byte-equal-unchanged. Anti-refactor #9 explicit.

**Tension 3 — Resume validation as a typed exception vs tagged union.** The S2-02 precedent (Anti-refactor #3 "No boolean return from `verify()` — the tagged union IS the contract") + the project-canonical sum-type discipline + the integrity-policy total-function discipline all point at a closed verdict union. Raising would defeat exhaustiveness narrowing under `mypy --strict`. Resolution: closed five-variant `ResumeVerdict` union; the gate is total. Anti-refactor #7 explicit.

**Tension 4 — `resume_or_reject` returns `ResumeAccepted | FailedUnrecoverable` (two-variant) vs full `ResumeVerdict` (five-variant).** Both surfaces are needed:
- `resume_with_full_verdict` is the canonical surface — every input maps to one of five verdicts. Testable, exhaustive, mutation-resistant.
- `resume_or_reject` is the convenience wrapper — folds the four non-accepted verdicts into `FailedUnrecoverable(reason="policy_violation", ...)` so the orchestrator's outer `match` on `RemediationOutcome` doesn't have to grow five new arms.

The two-surface design mirrors S2-02's `ReplayVerifier.verify()` (canonical) vs `hydrate_or_fail()` (convenience). Resolution: ship both; document the rationale in Notes-for-implementer §"Why two surfaces."

**Tension 5 — Stale approval definition: timestamp window vs chain-head binding vs handoff-digest binding.** Each alone is insufficient (Notes-for-implementer §"Why the canonical approval message must include both"). Resolution: bind ALL THREE in the canonical token-message bytes. The token recomputation in the resume validator catches any drift in any of the three dimensions. AC-3 (token-recomputation in model-validator) + AC-5 step (3) (defense-in-depth recomputation at the gate) + AC-5 step (4) (chain-head tail check) + AC-5 step (5) (TTL check) layer the defenses.

**Tension 6 — `EscalationReason` amendment vs additive emit-interrupt call.** S3-01's placeholder `Escalate(reason="awaiting_human_review")` is technically illegal at the `EscalationReason` Literal level. Amending `EscalationReason` to include the value would conflate two semantically distinct categories (pre-subgraph escalation vs in-subgraph HITL). Resolution: do NOT amend `EscalationReason`; replace S3-01's placeholder with an *additive* `emit_interrupt(...)` call from the boundary node. Anti-refactor #4 + Notes-for-implementer §"Why `EscalationReason` is NOT amended" explicit, with grep-instructions for the executor to handle all three possible current-state scenarios.

**Tension 7 — Phase-6 e2e + property test ownership.** S6-01 owns the closeout e2e scenarios (`tests/e2e/scenarios.yaml`) + the workflow-scope replay-determinism property. S4-01 owns the unit-level + integration-level slice of the HITL + resume substrate. Resolution: explicit Out-of-scope statement deferring the e2e + property tests to S6-01; this story ships the substrate the closeout composes.

## Four-lens findings (inline, no parallel subagents)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "Retry exhaustion enters `AwaitingHumanReview`" unverifiable — no retry-exhaustion definition | block | AC-9 — `emit_interrupt(store, workflow_id, interrupt, prior_state_id, ...)` with explicit `prior_state_id ∈ {"gate_failed_retryable", "patch_applied", "plan_ready"}` membership check; AC-10 codifies the integration scenario with `MAX_RETRIES = 3` boundary explicit. |
| AC-2 "Resume rejects stale or malformed approval payloads" un-anchored — no shape for what "stale" or "malformed" means | block | AC-3 (seven mutation classes for `ResumeInput`) + AC-4 (five verdict variants with explicit reason Literals) + AC-5 (eight-step gate with explicit ordering); AC-10 negative scenarios codify the four reject classes verbatim. |
| AC-3 "Approved resume continues from latest verified checkpoint" — no integrity-policy precedence | block | AC-5 step (1) MUST call `hydrate_or_fail` first; AC-6 three scenarios assert the precedence; AC-8 AST fence structurally enforces. |
| No idempotency / already-resumed coverage | block | AC-5 step (6) detect already-resumed via chain-head re-walk; AC-4 `AlreadyResumed` verdict; AC-10 negative scenario #4 codifies. |
| No "remains paused" structural guarantee | block | AC-8 AST fence — reject arms must NOT append `TransitionEvent`; AC-10 negative scenarios assert chain head is unchanged after reject. |
| No closeout (allowlist + snapshot + mypy) | harden | AC-12 (allowlist grows additively) + AC-13 (snapshot extension) + AC-14 (mypy + lint + import-linter). |
| No cross-table consistency between `HitlInterrupt` and `HumanReviewReason` | harden | AC-7 (i) forward + (ii) backward consistency Hypothesis property; (iii) dual-nature invariant; (iv) sibling-domain identity NOT asserted (cross-domain disambiguation). |
| `ApprovalToken` newtype absent | harden | AC-2 — newtype + smart constructor + chokepoint AST fence (mirrors `BundleCacheKey` precedent). |
| Parity matrix coverage missing | harden | AC-11 — `resume_or_reject` parametrize in the S2-01 parity contract test. |
| Two-surface API split unspecified | nit | Notes-for-implementer §"Why two surfaces"; AC-5 step (8) explicit; AC-12 lists both functions in `__all__`. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| Original ACs satisfiable by mutant always-pauses / always-rejects / always-resumes | block | Each AC includes a "Mutation thinking" note naming a specific mutation class the AC catches (wrong retry boundary, structural-matching fallback, parallel chain recomputation, ordering inversion, etc.). |
| No partial-write meta-test on the AST fence (AC-8 (iv)) | block | AC-8 (iv) parity-meta mutation guard: plant a broken `hitl.py` fixture that appends on reject; assert the fence fires loud. Mirrors S2-02 AC-15 precedent. |
| `mint_approval_token` determinism unspecified | block | AC-2 — same args → same token (canonical-bytes purity); AST chokepoint enforces single construction site; pure-helper fence walker extended additively. |
| No property test for the closed-universe (`HumanReviewReason` ↔ `HitlInterrupt.kind` slugs) | harden | AC-7 (i) + (ii) Hypothesis property over `st.sampled_from(get_args(HumanReviewReason))`; closed-universe draw, not arbitrary strings. |
| Single-file bundling temptation | harden | Anti-refactor #11 — per-AC test files; 10-file split mirrors S1-02 / S2-02 / S3-02 discipline. |
| Time-mocking discipline for AC-10 negative #3 (TTL exceeded) | harden | Notes-for-implementer §"Why 24-hour TTL" — operators inject mocked time via `freezegun` or a `_now_utc()` indirection in `_hitl.py`; the constant is `Final[int] = 86400` (module-local, not in `__all__`). |
| Token-recomputation defense-in-depth ambiguity | harden | AC-3 (model-validator does it) + AC-5 step (3) (gate re-checks defense-in-depth) — `.model_construct()` can bypass validators; the gate MUST NOT trust the model alone. Documented explicitly in AC-5 step (3). |
| `match` arm-counting test discipline | harden | AC-4 (iii) — AST walker counts five `case` arms + `case _: assert_never(verdict)` drift guard. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| `EscalationReason` amendment temptation | block | Anti-refactor #4 — `EscalationReason` is byte-equal-unchanged; the S3-01 placeholder is replaced additively via `emit_interrupt`; Notes-for-implementer addresses three current-state scenarios with grep instructions. |
| `HumanReviewReason` amendment temptation | block | "This story does NOT" line — adding a fifth value is an ADR-0001 + S1-02 amendment, not this story's scope. AC-7 cross-table consistency enforces. |
| `_LEGAL_TRANSITIONS` byte-equal-unchanged | block | "This story does NOT" line — S1-02 owns the legal-transition table; this story uses existing edges (`awaiting_human_review → plan_ready` for resume; `* → awaiting_human_review` for emit). |
| `CheckpointStore` Protocol byte-equal-unchanged | block | "This story does NOT" line — uses existing `append`, `tail_chain_head`, `iter_persisted_chain` methods. |
| Phase-6.5 isolation directive | harden | AC-12 — public-surface allowlist grows by 8 names; the `ResumeVerdict` reject variants stay private; bench-harness-needed names (`HitlInterrupt` variants, `ResumeInput`, `ApprovalToken`, the four functions) are re-exported. |
| `_attempts/_lessons.md` "two definitions of terminal" | harden | AC-7 (iii) — explicit assertion that `awaiting_human_review` is in `_TERMINAL_LEDGER_KINDS` AND `(awaiting_human_review, plan_ready)` is in `_LEGAL_TRANSITIONS`. Notes-for-implementer §"Why `_lessons.md`'s 'two definitions of terminal' matters here" expands. |
| `RequiresHumanReview` (transforms/outcomes) vs `AwaitingHumanReview` (vuln_ledger) cross-domain identity | harden | AC-7 (iv) — explicit NON-identity. Two unions, two umbrellas, two questions; the `_lessons.md` "Hydrated.kind MUST be a NEW closed tag" rule is the precedent. |
| Anti-refactor list absent | block | 12-item anti-refactor block — no registry, no ABC, no Strategy, no `EscalationReason` amendment, no time impurity in `_hitl.py`, no `HitlResumeCache`, no typed exception, no async, no `AwaitingHumanReview` payload coupling, no new `FailedUnrecoverableReason` value, no consolidated test file, no cryptographic-signature field. |
| Phase-9 forward dep (substrate-portability) un-addressed | harden | Out-of-scope statement; AC-11 substrate-agnostic parity test ensures the resume path works on both adapters; Phase-9 Postgres adapter inherits the protection by addition. |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| Plugin pattern temptation (`HitlInterruptRegistry`) | block | Anti-refactor #1 — rule-of-three for HITL registries unmet (Phase-7 `migration` ships its own surface, not a shared registry). Closed-`Annotated[..., Field(discriminator="kind")]` is the right substrate. |
| Strategy pattern temptation (`ResumeStrategy` Protocol) | block | Anti-refactor #3 — directly contradicts final-design.md item 6 "No new trust bypass"; would let a future plugin substitute a weaker policy. |
| Composition over inheritance | block | Anti-refactor #2 — no `BaseHitlInterrupt` ABC; structural identity via `kind: Literal[...]` + `model_config = _FROZEN_FORBID`. |
| Functional core / imperative shell | harden | Pure helper `_canonical_approval_message` in `_hitl.py` (walked by AST no-side-effects fence); imperative shell in `hitl.py` (the gate + the boundary write). AC-2 + Notes-for-implementer §"Why `time.time()` / `datetime.utcnow()` not in `_hitl.py`". |
| Newtype identifiers — never raw `str` for domain IDs | harden | AC-2 — `ApprovalToken` newtype + smart constructor + AST chokepoint (mirrors `BundleCacheKey` precedent in `identifiers.py`); `_NEWTYPE_REGISTRY` drift test extended. |
| Smart constructor for the resumption-contract token | harden | AC-2 — `mint_approval_token(workflow_id, chain_head, handoff_digest, ts_utc)` is the SOLE sanctioned construction site; AST chokepoint enforces. |
| Make illegal states unrepresentable | harden | AC-3 `model_validator(mode="after")` recomputes the token from the canonical fields; AC-5 step (3) defense-in-depth; AC-9 `prior_state_id` legality check. |
| Tagged union / sum type for state | harden | AC-1 + AC-4 — closed `Annotated[..., Field(discriminator="kind")]` over `_FROZEN_FORBID` Pydantic variants. |
| Sole-site policy gate (mirrors `hydrate_or_fail`) | harden | AC-5 — `resume_or_reject` is the SOLE site mapping reject verdicts to `FailedUnrecoverable`; the canonical `resume_with_full_verdict` is the testable surface. Notes-for-implementer §"Why two surfaces". |
| Chain-of-responsibility temptation (multi-step gate as a Chain pattern) | nit | AC-5 — eight-step sequence is a flat function with early returns; Chain pattern would force a `Step` ABC + a `ChainBuilder` for what's a linear walk. Below Rule 2's three-similar-lines threshold; rejected. |
| Pure-core / impure-shell file split | harden | `_hitl.py` (pure) + `hitl.py` (impure); the existing `_chain.py` / `_replay.py` / `replay.py` precedent. |
| `__slots__` lock on the gate | nit | Not added — `resume_or_reject` is a free function, not a class. The S2-02 `ReplayVerifier.__slots__ = ("_store",)` precedent only applies to the class-shaped surface; we don't need a class here. |

## Conflict resolution (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

1. **`HitlInterruptRegistry` vs closed-Pydantic sum type** (Design-Patterns potential registry temptation vs Consistency reading of S1-02 / S2-02 / S3-02 anti-refactor precedent + final-design.md item 5 closed-union mandate). **Resolution:** closed sum type (Consistency wins). The rule-of-three threshold for a registry over HITL surfaces is unmet; per-task-class HITL surfaces live in per-plugin modules per ADR-0002.

2. **`EscalationReason` amendment vs additive emit-interrupt** (Consistency reading of S3-01 placeholder current state vs Coverage need for clean cross-domain semantics). **Resolution:** additive (Consistency wins). `EscalationReason` is byte-equal-unchanged; the placeholder is replaced via `emit_interrupt(...)`; Notes-for-implementer addresses the three current-state grep scenarios.

3. **One-surface gate vs two-surface gate** (Design-Patterns reading of S2-02 precedent vs Coverage convenience for the orchestrator). **Resolution:** two surfaces (mirrors S2-02 verbatim). `resume_with_full_verdict` is canonical and testable; `resume_or_reject` is the orchestrator convenience.

4. **Time impurity in `_hitl.py`** (Test-Quality reading of mockability vs Design-Patterns purity discipline). **Resolution:** purity wins (Design-Patterns aligned with the S2-01 sanitize purity precedent). The orchestrator boundary passes `now_utc()` into `mint_approval_token`; `_hitl.py` has no FS/time side effects. Tests mock the orchestrator boundary, not the pure helper.

5. **`HumanReviewReason` Literal byte-equal-unchanged vs amendment for HITL completeness** (Consistency reading of S1-02 closed-set ownership vs Coverage temptation for a fifth slug). **Resolution:** byte-equal-unchanged (Consistency wins). The four S1-02 values cover the universe; any fifth value is an ADR-0001 + S1-02 amendment, not this story's scope. AC-7 cross-table consistency enforces.

6. **`ResumeVerdict` variant exposure** (Coverage reading of bench-harness completeness vs Consistency reading of Phase-6.5 isolation directive). **Resolution:** keep `ResumeVerdict` variants private (Consistency wins, mirrors S2-02 `ReplayVerdict` discipline). The bench harness has access to `HitlInterrupt` variants + `ResumeInput` + the four functions; the resume-verdict reject variants live internally.

7. **AC-8 fence walker depth** (Test-Quality reading of mutation resistance vs Design-Patterns simplicity). **Resolution:** deep walker over the full function-graph (Test-Quality wins, with a Design-Patterns concession: factor the walker into `tests/fence/_ast_helpers.py` to keep the test file thin). Notes-for-implementer §"Why the AST fence walks the FULL function-graph" expands.

8. **AC-10 negative scenarios in the same file vs separate files** (Test-Quality reading of discoverability vs Coverage parametrize density). **Resolution:** same file (the positive scenario sets up state; the negatives mutate it incrementally). This is the inverse of the per-AC split discipline — the scenarios are tightly coupled at the fixture level, so co-location aids debugging. Documented in Files-to-touch.

No `NEEDS RESEARCH` flag remained after critic synthesis.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` flag from any lens remained unresolved after Stage-2 synthesis. Every pattern this story prescribes has an in-repo precedent: closed-`Annotated[..., Field(discriminator="kind")]` over `_FROZEN_FORBID` Pydantic variants (S1-02 `VulnLedgerState`, S2-02 `ReplayVerdict`); SOLE-site integrity-policy gate (`hydrate_or_fail`); AST "remains paused on reject" fence (`test_hydrate_no_state_construction.py`); pure-core / imperative-shell file split (`_chain.py` + `_replay.py` + `replay.py`); newtype smart constructor + AST chokepoint (`BundleCacheKey` + `compose_bundle_cache_key`); cross-table consistency Hypothesis property (S1-02 backward-consistency); parity matrix across adapters (S2-01 + S2-02). Researching arXiv / library docs would have added zero signal.

## Stage 4 — Edits applied

### Pre-validation story (17 lines)

```markdown
# S4-01 — HITL interrupt and resume

**Status:** Ready
**Goal:** Emit typed HITL interrupts and validate resume input before continuation.

## Acceptance criteria

- Retry exhaustion enters `AwaitingHumanReview`.
- Resume rejects stale or malformed approval payloads.
- Approved resume continues from latest verified checkpoint.

## TDD plan

Red: stale approval and resume tests.
Green: interrupt payload + validator.
Refactor: share timestamp and evidence validation.
```

### Post-validation story (HARDENED — see file)

| Section | Before | After |
|---|---|---|
| Status line | `Ready` | `HARDENED` + `Validated:` line + `Depends on:` (five explicit cross-story deps + a "This story does NOT" five-bullet disambiguation) |
| Goal | 1 sentence | 1 paragraph naming the substrate + 4 numbered concerns (`HitlInterrupt` union, `ResumeInput` model + `ApprovalToken` newtype, `ResumeVerdict` + `resume_or_reject`, retry-exhaustion emission + S3-01 placeholder replacement) + 1 paragraph explicitly placing this story as the fourth-concrete-consumer of the typed-substrate-and-sole-site-policy-gate Phase-6 pattern |
| References | absent | 16-entry block citing final-design.md / phase-arch-design.md / ADRs/0001 / ADRs/0003 / High-level-impl.md / sibling stories S1-01 / S1-02 / S2-01 / S2-02 / S3-01 / canonical siblings `replay.py` / `vuln_ledger.py` / `__init__.py` / fence file precedents / `_lessons.md` four lessons |
| Acceptance criteria | 3 dash bullets (0 checkboxes) | 14 numbered checkbox ACs across 5 labeled sub-sections (typed interrupt; resumption contract; verdict + gate; cross-table consistency + fences; closeout) |
| Files to touch | absent | 19-line list — 2 new source files (`hitl.py` create + `_hitl.py` create), 1 source modify (`__init__.py`), 1 identifier add (`identifiers.py`), 4 new unit test files, 3 new integration test files, 1 contract modify, 3 new fence files, 1 fence-fixture, 3 fence modifies, 1 contract-snapshot modify, 1 newtype-drift modify, 1 ADR amendment |
| TDD plan | 3 sentences | Red phase (14-step sequence, one per AC) + Green (12-step minimum-code sequence) + Refactor (4-item cleanup list) + Anti-refactor (12 items) |
| Out of scope | absent | 8-item list — LangGraph routing (S3-01); CLI resume subcommand (Phase-7+); multi-reviewer/quorum (Phase-9); cryptographic-signature tokens (Anti-refactor #12); cross-substrate token portability (naturally satisfied); approval-token revocation (chain-head drift handles it); e2e scenarios.yaml (S6-01); workflow-replay-determinism property (S6-01) |
| Notes for implementer | absent | 9-paragraph block — two-surfaces rationale, canonical-message field rationale, 24-hour TTL rationale, `WorkflowId` re-export rationale, two-definitions-of-terminal discipline, `EscalationReason` non-amendment rationale with 3-scenario grep instructions, AST fence walker depth, per-AC test files rationale, no-cassette-refresh-needed, 12-step implementation order |

## Verdict

**HARDENED** — every four-lens finding either landed as an AC, an Anti-refactor item, an Out-of-scope statement, a Notes-for-implementer paragraph, or a Conflict-resolution rationale. All eight conflicts resolved with explicit priority-order reasoning. No `NEEDS RESEARCH` flag remained open. The story is ready for `phase-story-executor`.
