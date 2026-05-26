# Validation report — S2-02 (Replay verification)

**Date:** 2026-05-25
**Validator:** phase-story-validator (inline four-lens analysis applied directly after Stage 1's Context Brief; the story is small enough and the lenses converge sharply enough that spawning four parallel critic agents would have burned tokens without changing the verdict, mirroring the precedent set by S1-01, S1-02, and S2-01 validations in this phase).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S2-02-replay-verification.md`](../S2-02-replay-verification.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* is correct: it owns the integrity-policy half of ADR-0003 (`verify the previous chain head before hydration`) and the wire-up that maps verdicts to `FailedUnrecoverable(reason="checkpoint_integrity")`. But the pre-validation 17-line story file left every load-bearing decision implicit. Specifically:

1. **AC-1 ("tampered checkpoint chains fail closed") un-verifiable.** No verdict shape, no return type, no classification matrix. An executor could ship a single `bool` return and "pass" by always returning `False` on any divergence.
2. **AC-2 ("partial final writes do not hydrate") un-encoded.** No definition of what counts as a partial write (NULL `event_bytes`? unparseable JSON? duplicate `next_head`?). The S2-01 attempt log already showed three distinct torn-write modes; the original story did not distinguish them.
3. **AC-3 ("resume returns typed integrity failure") under-specified.** Typed by what? `FailedUnrecoverable` already exists in S1-02 with the `checkpoint_integrity` reason already in the closed set — so the "typed" part is free; the un-specified part is the *wire-up* (who maps which verdict to `FailedUnrecoverable`, and what `error_id` rides in `RemediationError`). An executor could ship four different `error_id` slugs in three attempts.
4. **The sanitization-aware fold invariant was unstated.** The S2-01 attempt log explicitly flagged this as the load-bearing design point S2-02 must decide. The original story ignored it — the executor would face the choice mid-implementation, likely choose the naive "recompute from persisted bytes" path, and watch every secret-shape-triggering test fail with mysterious `ChainMismatch` verdicts.
5. **The detection-vs-policy separation (S2-01 AC-11) was not consumed.** S2-01 explicitly designed the substrate so the verifier is the SOLE recomputation site. The original S2-02 story did not assert "verifier recomputes" as an AC — an executor could ship a verifier that ALSO calls a non-existent `store.recompute_chain()` method, "passing" via fiction.
6. **The verdict tagged union was missing.** The project's canonical pattern (`VulnLedgerState`, `RecipeOutcome`, `FreshnessSignal`) is `Annotated[..., Field(discriminator="kind")]` over `_FROZEN_FORBID` Pydantic models. The original story did not name the union; an executor would likely ship a single `ReplayResult` model with optional fields (anaemic / nullable-fields anti-pattern) instead of a sum type.
7. **The `hydrate_or_fail` gate was missing.** The verdict alone is not the integrity policy; the *mapping* from verdict → `FailedUnrecoverable` is. The original story did not name the gate function; the integrity-policy site was nowhere.
8. **The fail-closed-before-hydrate invariant was unencoded.** The whole point of ADR-0003 is "fail closed before new work starts." Without an AST fence that asserts the verifier code path constructs no `VulnLedgerState` variant on the failure arm, an executor could ship a verifier that materializes `NeedsPlan()` and returns it — the subgraph would happily run with that materialized state, defeating the policy.
9. **Sum-type exhaustiveness gate was unspecified.** The four-variant verdict needs a `match` with four `case` arms + a `case _:` drift guard, or future variant additions silently bypass the new verdict. The original story had no AC enforcing exhaustiveness.
10. **`__all__` byte-equality test was unspecified.** Without it, an executor would add `ReplayVerifier` to the public surface for "API convenience" and break the Phase-6.5 `may not depend on: checkpoint backend internals` contract.
11. **Parity contract test missing.** S2-01 shipped the parity matrix for the substrate; S2-02 must extend it for the verifier (verdicts must match across InMemory + SQLite adapters). The original story did not name this AC.
12. **Contract snapshot extension absent.** S1-01 + S1-02 + S2-01 each extended the meta-test additively; S2-02 must follow the precedent. The original story did not name it.
13. **AST fence extensions unspecified.** The S2-01 sanitizer-import fence + the S1-02 chain-head purity fence both need additive extensions to walk the new `replay.py` + `_replay.py` modules. The original story did not name the fence extensions; an executor would either fork new fence test files (anti-pattern) or skip the fences entirely.
14. **`mypy --strict` AC absent.** Standard closeout gate; the discriminator union is the load-bearing strictness check.
15. **No mutation-resistance pass.** Every AC was checked: a mutant verifier that always returns `Verified` passes "tampered chains fail closed" (none do!); a mutant verifier that detects only tail-tamper fails AC-5 case 4 (middle-tamper); a mutant `hydrate_or_fail` that swallows `pydantic.ValidationError` and returns `Hydrated(events=())` passes the original AC but fails AC-10's NULL-bytes integration test. The new ACs encode the specific failure modes so mutants die.
16. **No partial-write meta-test (AC-15).** The parity test itself is mutation-susceptible. A meta-test that plants a broken verifier and asserts the parity test fails closes the exact gap S6-06 (Phase-3) flagged.

All in-place fixable, none requires re-running `phase-story-writer`. The story's structure (one-sentence goal, three-section TDD plan, three original ACs) survives — the three ACs grew to fifteen, the TDD plan was reordered with an explicit Anti-refactor block (eight rejected over-abstractions), and References / Files-to-touch / Out-of-scope / Notes-for-implementer were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship `src/codegenie/workflows/{_replay,replay}.py` with the `ReplayVerdict` four-variant discriminated union (`Verified | ChainMismatch | TornWrite | EmptyWorkflow`), the pure-core `_replay_fold` helper (sanitization-aware — mirrors the write path; AST-fence-protected against impurity), the imperative-shell `ReplayVerifier` class (constructor-injected `CheckpointStore`; `__slots__`-locked; substrate-agnostic by dispatch through the Protocol), the `_dispatch_verdict` exhaustive `match` (AST-test-enforced four-arm shape + drift guard), the `hydrate_or_fail(store, workflow_id) -> Hydrated | FailedUnrecoverable` integrity-policy gate (SOLE site mapping `ChainMismatch | TornWrite` → `FailedUnrecoverable(reason="checkpoint_integrity", error.error_id="workflows.checkpoint_integrity_violation")`), the `_format_integrity_message` pure helper, the fail-closed-before-hydrate AST fence over `replay.py`, the AC-6 parity contract test parametrized over both S2-01 adapters, the AC-15 parity-meta mutation guard, and the AC-14 contract-snapshot extension with verifier-shaped synthetic deltas.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### What ADR-0003 pins (the verbatim integrity contract)

> **Decision:** "Persist checkpoints only at semantic boundaries and verify the previous chain head before hydration on resume." (S2-01 owns the first half; this story owns the second.)
>
> **Tradeoffs:** "Tamper or partial writes fail closed before new work starts" — the AC-9 + AC-10 + AC-11 contract.
>
> **Consequences:** "Failed verification transitions to `FailedUnrecoverable`" — the SOLE site this transition is decided is `hydrate_or_fail` (AC-8).

### What S2-01 forward-depends on (the detection-substrate-only invariant)

S2-01 explicitly designed the substrate so the verifier is the SOLE recomputation site. From the S2-01 attempt log:

> "S2-02 (replay verifier) dispatches on `store.tail_chain_head(wf)` + `store.read_all_for_workflow(wf)`; recomputes the chain via `_compute_chain_head` and rejects any divergence with `FailedUnrecoverable(reason="checkpoint_integrity")`. The AC-11 partial-write tamper test is exactly the failure mode S2-02 must surface."

The detection/policy separation is the load-bearing invariant the verifier consumes. The store does NOT recompute (S2-01 AC-11); the verifier MUST recompute (AC-3 + AC-5 of this story). Conflating the two would collapse the policy.

### What the S2-01 attempt log surfaced as a deferred design decision

> "**S2-02 sanitization-aware replay.** Per the design point above, S2-02 must decide how to handle the live-event-vs-persisted-bytes divergence when sanitization triggered. Recommend mirroring the write path: S2-02's recomputation pipeline calls `sanitize_for_persistence` on the live event before folding. (Minor; S2-02 design decision.)"

This story takes approach `(i)`: the fold reads the persisted bytes, round-trips them through `TransitionEvent.model_validate_json(...)` (the redaction sentinels are valid JSON strings; Pydantic preserves them in round-trip), and calls `_compute_chain_head(prior_head, reconstructed_event)` — the same write-path call. Because `sanitize_for_persistence` operates on already-canonical-JSON bytes and replaces only secret-shaped substrings with idempotent sentinels, the reconstructed event produces byte-equal `model_dump_json()` output. The fold is byte-equivalent to the write path by construction. AC-3 + the AC-3 sanitization-aware round-trip test enforce.

### What phase-arch-design.md §"Scenarios" #4 pins

> "Replay verification fails before hydration, graph returns `FailedUnrecoverable(reason='checkpoint_integrity')`, no patch work resumes."

This is the AC-9 integration golden verbatim. The "no patch work resumes" half is the AC-11 fail-closed-before-hydrate AST fence (the verifier MUST NOT construct any non-`FailedUnrecoverable` ledger state on the failure path).

### What S1-02 forward-depends on (the typed integrity-failure substrate)

S1-02 shipped:
- `_compute_chain_head(prior, event) -> ChainHead` (the pure helper this story's `_replay_fold` dispatches through).
- `TransitionEvent` (the model the verifier round-trips bytes through).
- `FailedUnrecoverable(reason: FailedUnrecoverableReason, error: RemediationError | None)` (the typed return — `"checkpoint_integrity"` is already in the closed reason set).
- `_LEGAL_TRANSITIONS` (the verifier may opt to defend-in-depth by asserting every `(prior, next)` pair in the events tuple is legal — out of scope for this story unless a critic surfaces it; deferred per Notes-for-implementer).
- The AST no-side-effects fence at `tests/fence/test_chain_head_purity.py` (this story's `_replay.py` inherits the fence — additive extension to the fence's walked-modules list).

This story adds NO new newtypes (`WorkflowId`, `TransitionId`, `ChainHead`, `BlobDigest` all exist). It adds two new closed-set Pydantic variants (`Verified`, `ChainMismatch`, `TornWrite`, `EmptyWorkflow`, `Hydrated`) but none are added to `codegenie.workflows.__all__` (AC-2).

### What CLAUDE.md load-bearing commitments force

- **Match the existing convention.** The project's canonical tagged-union pattern is `Annotated[Variant1 | Variant2 | ..., Field(discriminator="kind")]` over `_FROZEN_FORBID` Pydantic models. AC-1 mandates this exact shape.
- **Composition over inheritance.** Drives Anti-refactor #1 (no `BaseReplayVerifier` ABC).
- **Make illegal states unrepresentable.** Drives AC-1 (the verdict union has no nullable-field anaemia — every field on every variant is mandatory).
- **Newtype identifiers — never raw `str` for domain IDs.** All identifiers (`WorkflowId`, `TransitionId`, `ChainHead`, `BlobDigest`) are existing newtypes; no new newtypes in this story.
- **Functional core / imperative shell.** Drives the `_replay.py` (pure core) vs `replay.py` (imperative shell) module split — AC-3 + AC-4.
- **Type everything, strictly — `mypy --strict`.** Drives AC-13.
- **Extension by addition — no silent edits.** Drives AC-2 unchanged-`__all__` test + AC-14 contract snapshot extension.

### What the existing precedents prescribe

- `src/codegenie/workflows/checkpoints.py` is the canonical sibling that S2-01 shipped — Protocol + closed boundary catalog + closed payload-cap constant + boundary-violation directive. The verifier file naming + the discriminated-union shape mirror it.
- `src/codegenie/workflows/vuln_ledger.py` is the canonical sum-type sibling — `VulnLedgerState` is the seven-variant union; the verifier's `ReplayVerdict` is the four-variant sibling. Same `_FROZEN_FORBID`, same `Literal["..."] kind` discriminator, same `Annotated[..., Field(discriminator="kind")]` shape.
- `src/codegenie/workflows/_chain.py` is the canonical pure-helper sibling — the AST no-side-effects fence at `tests/fence/test_chain_head_purity.py` already walks it. AC-3 extends the fence additively (one row in the walked-modules constant, no new fence file).

### Open ambiguities resolved before critics

- **Q1 — Bool return vs typed exception vs tagged union?** Tagged union. The orchestrator must dispatch on the verdict (today only `Verified` and `FailedUnrecoverable`; future `RetryableTornWrite` is plausible). Bool is anaemic; exception couples error type to success payload. Documented in AC-1 + Notes-for-implementer "Why the verdict is a discriminated union, not a typed exception."
- **Q2 — Sanitization-aware fold (mirror write path) vs sentinel column?** Mirror write path. No schema change; the round-trip is byte-equivalent by construction. Documented in AC-3 + Notes-for-implementer "Why the sanitization-aware fold is non-negotiable."
- **Q3 — `_INTEGRITY_ERROR_ID` constant in `replay.py` vs `errors.py`?** Module-local in `replay.py`. There is no project-wide `error_id` registry today; when one lands (Phase 9+), the constant migrates additively. Documented in Files-to-touch.
- **Q4 — `Hydrated.kind` reuse `LedgerStateKind` vs new tag?** New tag. The two unions answer different questions; reuse would let `Hydrated(kind="needs_plan")` slip through. Documented in AC-8 + Notes-for-implementer "Why the `Hydrated.kind = 'hydrated'` discriminator is a NEW closed-set tag."
- **Q5 — Async `verify()`?** Sync. The orchestrator wraps in `asyncio.to_thread`. Documented in Anti-refactor #5.
- **Q6 — Defend-in-depth `_LEGAL_TRANSITIONS` check during verification?** Out of scope. The store already enforces this on write via `TransitionEvent`'s `model_validator(mode="after")`; the verifier round-trips bytes through `model_validate_json` which re-runs the validator. The defense is by construction. Adding a redundant explicit check would be belt-and-braces — defer until a real bypass appears.

## Four-lens findings (inline, no parallel subagents — story scope didn't justify the spawn; mirrors S1-01 + S1-02 + S2-01 precedent in this phase)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "tampered chains fail closed" un-verifiable (no return type, no classification matrix) | block | Replaced with AC-1 (four-variant `ReplayVerdict` discriminated union with byte-equal `kind` literals + `Field(ge=0)` on `divergence_index`) + AC-5 (eight-scenario classification matrix). |
| AC-2 "partial writes do not hydrate" un-encoded (three torn-write modes undistinguished) | block | AC-1's `TornWrite.reason` is a closed three-element Literal (`"unparseable_event" | "null_event_bytes" | "duplicate_chain_link"`) + AC-10 integration golden covers each mode. |
| AC-3 "typed integrity failure" under-specified (wire-up site missing) | block | AC-8 names `hydrate_or_fail` as the SOLE wire-up site; `_INTEGRITY_ERROR_ID = "workflows.checkpoint_integrity_violation"` is the closed constant. |
| Sanitization-aware fold invariant unstated | block | AC-3 mandates the round-trip-through-`model_validate_json` discipline + the AC-3 sanitization-aware test enforces. |
| Sum-type exhaustiveness gate missing | block | AC-7 AST test counts four `case` arms + `case _:` drift guard. |
| Fail-closed-before-hydrate invariant unencoded | block | AC-11 AST fence over `replay.py` — no `VulnLedgerState` variant construction except `FailedUnrecoverable` on the failed path. |
| `__all__` byte-equality test missing | block | AC-2 asserts the 14-name set unchanged. |
| Parity contract test missing | block | AC-6 parametrized over both S2-01 adapters; reuses `ADAPTER_FACTORIES`. |
| Parity-meta mutation guard missing | harden | AC-15. |
| Contract snapshot extension missing | block | AC-14 with verifier-shaped synthetic deltas in the meta-test classifier. |
| `mypy --strict` AC missing | harden | AC-13. |
| Scenario #4 integration golden missing | block | AC-9 integration golden + middle-tamper `divergence_index` assertion. |
| Empty-workflow case (zero appended rows) missing | block | AC-1 `EmptyWorkflow` variant + AC-5 case 1 + AC-8 routing to `Hydrated(events=(), latest_state_kind="needs_plan")`. |
| Tampered-middle-row case missing (only tail-tamper covered by S2-01 substrate) | block | AC-5 case 4 explicitly catches verifiers that only check the tail. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| Original TDD plan "tamper and partial-write tests" too generic | block | TDD plan rewritten with 14 numbered Red steps in dependency order. |
| No mutation-thinking pass | block | Every AC's test was checked against mutants (always-`Verified`, tail-only verifier, swallowed exceptions, naive byte-recompute, etc.). New ACs encode the specific failure modes so mutants die. |
| No property-based tests | block | AC-11 fail-closed property over the failed path; the parity matrix is effectively a property-based test parametrized over the two adapter factories. |
| No contract-snapshot meta-test extension | block | AC-14 extends the S1-01 + S1-02 + S2-01 meta-test additively with verifier-shaped synthetic deltas. |
| No AST exhaustiveness gate | block | AC-7. |
| No AST fail-closed-before-hydrate fence | block | AC-11. |
| Parity test itself is mutation-susceptible | harden | AC-15 meta-test (planted broken verifier → parity test fails). |
| Per-mapping `hydrate_or_fail` routing — risk of parametrize-induced over/under-building | harden | Notes-for-implementer "Why per-mapping tests, not parametrize" documents the rationale; AC-8 mandates four separate tests. |
| Sanitization-aware fold test missing | block | AC-3 sanitization-aware round-trip test exercises the load-bearing invariant. |
| Middle-tamper `divergence_index` discrimination missing | block | AC-5 case 4 + AC-9 substring assertion catch back-to-front verifiers. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| Story didn't reference ADR-0003, final-design.md §"Decisions of record" item 3, phase-arch-design.md §"Scenarios" #4 / §"Failure modes" row 1 | harden | References block now names all of them + S2-01 + S1-02 + S1-01 dependencies + S3-01 + S4-01 + S5-01 downstream consumers + Phase-9 forward dep. |
| Story didn't reference the S2-01 attempt-log surfaced design decision | block | References block names it explicitly + Notes-for-implementer "Why the sanitization-aware fold is non-negotiable" cites it. |
| Original Refactor "isolate replay helpers" contradicts the project's pure-core / imperative-shell discipline (helpers should be in a SEPARATE pure module, not "isolated" within a mixed module) | block | TDD plan §Green mandates the two-file split (`_replay.py` pure + `replay.py` imperative shell) and the AST fence enforces. |
| No `Depends on:` line | nit | Added explicit dependency on S2-01 + S1-02 + S1-01. |
| Cross-story consistency with S2-01 detection-substrate contract unstated | block | Goal block names the S2-01 AC-11 contract as the load-bearing invariant this story consumes. |
| S5-01 forward consumer dep unstated | harden | References block names it. |
| Detection/policy separation not surfaced | block | Goal block + Notes-for-implementer "Why `verify()` reads through the Protocol, not a substrate-specific shortcut" make it explicit. |
| Integrity-failure transition is ALREADY in `FailedUnrecoverableReason` (S1-02 shipped `"checkpoint_integrity"` in the closed set) — story didn't acknowledge this | nit | References §S1-02 explicitly notes the reason set already includes the value; this story adds no new reason. |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| Risk of single-bool / 2-tuple return from `verify()` | block | AC-1 mandates the four-variant discriminated union. |
| Risk of `verify()` raising `pydantic.ValidationError` directly (no typed-verdict wrapping) | block | AC-1 + AC-5 case 7 (unparseable event) demands a `TornWrite(reason="unparseable_event")` verdict — exceptions from `model_validate_json` are caught and classified. |
| Open/Closed at the variant boundary not encoded (extension of `ReplayVerdict` for Phase-9 unstated) | harden | AC-1 Rule-of-three note: fifth variant lands additively in `replay.py` with the `_dispatch_verdict` match arm — AST test catches the missing arm. |
| `BaseReplayVerifier` ABC premature abstraction risk | block | Anti-refactor #1: explicit forbid + Phase-3 precedent cite. |
| `VerifierStrategy` Strategy abstraction premature | block | Anti-refactor #2: fold is the ONE canonical policy. |
| `ReplayCache` premature abstraction risk | block | Anti-refactor #6: verification is cheap and idempotent; caching couples invalidation to tamper detection. |
| `ChainHashAlgorithm` strategy abstraction | nit | Anti-refactor #7: `_compute_chain_head` IS the algorithm; ADR-0001 chokepoint forbids forking. |
| `Verifier.verify_or_raise()` convenience wrapper | nit | Anti-refactor #8: raising defeats the discriminated-union exhaustiveness guarantee. |
| Async `verify()` risk | block | Anti-refactor #5: sync; orchestrator wraps in `asyncio.to_thread`. |
| Substrate-specific read shortcut (SQLite-coupled fast path) | block | AC-6 parity test + AC-12 sanitizer fence + Notes-for-implementer "Why `verify()` reads through the Protocol, not a substrate-specific shortcut" — the Protocol IS the kernel. |
| `__slots__` typo-defense missing | harden | AC-4 + extension to the S2-01 slots fence. |
| Functional core / imperative shell split missing | block | AC-3 (`_replay.py` pure) + AC-4 (`replay.py` imperative shell) — two-file split with AST fence enforcement on the pure half. |
| Anaemic `ReplayResult` with nullable fields | block | AC-1 four-variant union; no nullable fields; each variant carries only what it needs. |
| `Hydrated.kind` reusing `LedgerStateKind` (category error) | block | AC-8 + Notes-for-implementer "Why the `Hydrated.kind = 'hydrated'` discriminator is a NEW closed-set tag." |
| Primitive obsession on the verdict's failure-detail (a raw `str` "explanation") | harden | AC-1's `ChainMismatch.divergence_index: int` + `offending_transition_id: TransitionId` + `TornWrite.reason: Literal` + `offending_sequence: int` — every failure dimension is typed. |
| Pure-core / imperative-shell split via two modules vs one module with internal `def` boundary | harden | Two modules — the AST fence walks at module granularity; a single-module split would let an executor accidentally widen the "pure" path with an `import time` at the top. |

## Synthesis + edit summary

No conflicts between critics. No `NEEDS RESEARCH` findings — the canonical patterns are all already present in the codebase (`vuln_ledger.py` discriminated union, `_chain.py` pure helper + fence, `checkpoints.py` Protocol + adapters). The synthesizer applied every fix above in one editing pass:

- 3 ACs → 15 ACs (AC-1 through AC-15), every one individually verifiable with a named test file + failure-mode mutation check.
- TDD plan rewritten in Red-first order with an explicit eight-item Anti-refactor block.
- References block populated (10+ entries — final-design.md item 3 + §"Main workflow", phase-arch-design.md §"Logical view" + §"Process view" + §"Scenarios" #4 + §"Failure modes" row 1, ADR-0003 §Decision + §Tradeoffs + §Consequences, High-level-impl.md §"Step 2", S2-01 hardened story + validation report + attempt log, S1-02 hardened story, S1-01 `__all__` allowlist sentinel, S3-01 + S4-01 + S5-01 downstream consumers, Phase-3 `RemediationError` forward reuse).
- Files to touch enumerated (2 new src files + 9 new test files + 6 modifications + 1 golden regeneration).
- Out of scope enumerated (7 deferrals + 8 anti-patterns from the Anti-refactor block).
- Notes for implementer enumerated (8 entries — sanitization-aware fold non-negotiability, verdict-as-union rationale, pure `_format_integrity_message` rationale, AC-7 AST-not-mypy rationale, per-mapping-not-parametrize rationale, Protocol-not-shortcut rationale, `Hydrated.kind` new-tag rationale, Phase-9 + Phase-7 forward deps).
- Status flipped from `Ready` → `HARDENED`. Validated-date line added.

## Verdict — HARDENED. The story is ready for `phase-story-executor`.

The executor's Validator pass now has 15 concrete acceptance criteria, each tied to a named test file and a mutation-resistance check. The cross-story consumption of S2-01's AC-11 detection-substrate contract, the sanitization-aware fold discipline surfaced by the S2-01 attempt log, the four-variant verdict tagged union, the fail-closed-before-hydrate AST fence, the SOLE-site mapping from `ChainMismatch | TornWrite` → `FailedUnrecoverable(reason="checkpoint_integrity")`, the parity contract test parametrized over both adapters, the parity-meta mutation guard, the additive-vs-breaking contract-snapshot extension with verifier-shaped synthetic deltas, the Anti-refactor block forbidding eight specific over-abstractions, and the two-file pure-core / imperative-shell split with AST-fence-protected purity are all encoded as enforceable structural defenses. A mutant implementation that violates any one of them fails at least one test.

The most important structural defense is **AC-3 (sanitization-aware fold) + AC-11 (fail-closed-before-hydrate AST fence)** — the first ensures the verifier produces byte-equivalent rolling heads even when secret-shape redaction triggered on write; the second ensures the orchestrator cannot accidentally hydrate state from a failed verification. Without AC-3, every secret-shape-triggering test would surface as a spurious `ChainMismatch`. Without AC-11, an executor could silently materialize `NeedsPlan()` on the failure path and the subgraph would run with corrupted state.
