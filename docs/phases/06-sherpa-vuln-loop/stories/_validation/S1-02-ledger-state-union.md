# Validation report — S1-02 (Ledger state union)

**Date:** 2026-05-25
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief; the story is small enough and the lenses converge sharply enough that spawning four parallel critic agents would have burned tokens without changing the verdict, mirroring the precedent set by the S1-01 validation in this same phase).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S1-02-ledger-state-union.md`](../S1-02-ledger-state-union.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* is correct: it owns the closed sum type the rest of Phase 6 dispatches on, and Step 1 of High-level-impl.md explicitly pairs it with the SUT contract ("Add the closed ledger state union and transition event types"). But every AC was a vague qualitative statement, the Refactor step inverted Rule 2, and three concrete contractual requirements named by `final-design.md §"State model"` were entirely absent. Specifically:

1. **AC-1 was un-verifiable.** "All seven ledger variants exist" — exist with what shape? what discriminator? what evidence payloads? An executor could ship seven empty `BaseModel` subclasses and pass.
2. **AC-2 was vague.** "Illegal transitions are unrepresentable in constructors" — through what mechanism? a `model_validator`? a closed transition table? a class-level `_LEGAL_PREDECESSORS` tuple? Without naming the mechanism, the executor's Validator pass can't binary-pass-fail.
3. **AC-3 was hollow.** "Exhaustive match tests cover every state" — there are several "exhaustiveness" patterns in Python (`assert_never` vs. `pytest.mark.parametrize` over `typing.get_args` vs. registry walk); without naming one, two executor attempts would write two different shapes and the Validator would accept either.
4. **TransitionEvent was missing entirely.** final-design.md §"State model" mandates each transition record `(prior state id, next state id, triggering outcome, evidence digest, chain head)` — *five required fields*. The story didn't name a `TransitionEvent` model or its shape at all. ADR-0003's "verify the previous chain head before hydration on resume" depends on this being a *chained* event, not a snapshot.
5. **Chain-head substrate was unencoded.** ADR-0003's replay-verification gate (S2-01 + S2-02 forward dep) requires that `TransitionEvent.chain_head = BLAKE3(prior_chain_head || canonical_transition_bytes)` is a *pure, byte-deterministic* helper — same discipline as S1-01's `_compute_sut_digest_input`. Without pinning this here, S2-01 would either re-implement the helper differently or push it into an impure context where the AST no-side-effects fence (S1-01 AC-7) can't see it.
6. **Cross-story consistency with S1-01 was unstated.** S1-01 pins `TerminalState = Literal["completed", "awaiting_human_review", "failed_unrecoverable"]`. The terminal partition of the ledger sum type MUST match S1-01's `TerminalState` literal byte-for-byte. Without a cross-story membership-byte-equality test, a future drift (e.g., adding `cancelled` to the ledger but not to `TerminalState`) silently breaks the public Result's invariant.
7. **Refactor step inverted Rule 2.** "Move repeated evidence fields into shared bases" is a textbook premature-DRY refactor. Three similar lines is better than premature abstraction; inheritance for behaviour sharing is also the *wrong* shape per CLAUDE.md "composition over inheritance" precedent. The repo precedent is `transforms/outcomes.py` (composition: shared sub-models like `RecipeError` injected as fields, not inherited).
8. **Discriminated-union convention was unstated.** Every sum type in `codegenie/transforms/outcomes.py`, `codegenie/indices/freshness.py`, `codegenie/probes/_shared/scanner_outcome.py`, and `codegenie/fallback/plan_outcome.py` uses `Annotated[A | B | C, Field(discriminator="kind")]` with each variant carrying `kind: Literal["..."]`. CLAUDE.md "match the existing convention" makes that mandatory. Without naming it, an executor could write a tagged-union-by-`isinstance` and pass a "seven variants exist" AC.
9. **Frozenness + `extra="forbid"` was unstated.** Phase-3 ADR-0010 + S1-01 AC-4 establish `_FROZEN_FORBID` as the single canonical `ConfigDict` constant; every `BaseModel` subclass in `codegenie/workflows/` MUST set `model_config = _FROZEN_FORBID`. Without the AST fence, an executor under deadline pressure ships one variant without `frozen=True` and the ledger becomes silently mutable.
10. **Newtype + registry drift was unstated.** This story adds at least one new identifier (`TransitionId` — the per-transition event id) and reuses several existing newtypes (`WorkflowId`, `EventId`, `ChainHead`, `BlobDigest`, `ErrorId`). The new identifier needs the `_NEWTYPE_REGISTRY` entry in the same commit, with a smart-constructor parser. The Phase-3 ADR-0010 drift test exists precisely so a new newtype lands with its registry entry; the story didn't name the registry.
11. **Mutation-resistance pass was absent.** Every AC was checked: a mutant model with `extra="allow"` would pass "seven variants exist." A mutant `model_validator` that returns `True` for all (prior, next) pairs would pass "illegal transitions are unrepresentable" if the test only checks the legal pairs. A mutant `chain_head` computation that drops a field would pass "exhaustive match tests." The new ACs encode the specific failure modes so mutants die.
12. **`assert_never` exhaustiveness wasn't pinned.** CLAUDE.md "Type everything, strictly" + `mypy --strict` gives `assert_never` real teeth — a missed variant in a `match` statement becomes a *type error*, not a runtime AssertionError. The AC needs to mandate a `match` with `assert_never` on the default arm so adding a new variant without updating every consumer is a CI failure at the next phase boundary.
13. **No public-surface allowlist amendment.** S1-01 AC-12 introduced the `codegenie.workflows.__all__` sentinel; this story adds new names (`VulnLedgerState`, `NeedsPlan`, `PlanReady`, ..., `TransitionEvent`). Without an explicit AC that the sentinel test passes *after* the additive amendment, the executor's first commit fails CI for an opaque reason. Better to name the amendment as an AC up-front.

All in-place fixable, none requires re-running `phase-story-writer`. The story's structure (one-paragraph goal, three-section TDD plan) survives — the three ACs grew to fifteen, the TDD plan was reordered with the anti-refactor note, and References / Files-to-touch / Out-of-scope / Notes-for-implementer were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship `src/codegenie/workflows/vuln_ledger.py` with the closed seven-variant `VulnLedgerState` discriminated union, the `TransitionEvent` model carrying the five fields final-design.md §"State model" mandates, the closed transition table (frozenset of legal `(prior_kind, next_kind)` pairs) enforced via `model_validator`, the `_compute_chain_head` pure helper substrate ADR-0003's replay-verification gate depends on, one new newtype (`TransitionId`) + smart constructor + `_NEWTYPE_REGISTRY` entry, an AST `_FROZEN_FORBID` fence over every `BaseModel` in the new file, a `match`-with-`assert_never` exhaustiveness test, an extended `codegenie.workflows.__all__` allowlist, an extended Phase-6 contract snapshot, and a cross-story membership test pinning the terminal partition byte-equal to S1-01's `TerminalState`.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### What final-design.md §"State model" pins

The ledger uses a closed sum type with exactly seven variants:
- Non-terminal (4): `NeedsPlan`, `PlanReady`, `PatchApplied`, `GateFailedRetryable`
- Terminal (3): `AwaitingHumanReview`, `Completed`, `FailedUnrecoverable`

Every transition records *five* fields: prior state id, next state id, triggering outcome, evidence digest, checkpoint chain head. This is verbatim from final-design.md and is the story's load-bearing contract.

### What ADR-0003 pins

Persist checkpoints only at semantic boundaries; verify the previous chain head before hydration on resume. Failed verification → `FailedUnrecoverable(reason="checkpoint_integrity")` per phase-arch-design §"Scenarios" #4. This story doesn't own the SQLite write path (S2-01) or the replay verification (S2-02), but it owns the *substrate* both depend on: `TransitionEvent` must be a pure, byte-deterministic record so `BLAKE3(prior_head || canonical_event_bytes)` is reproducible across `LocalVulnRemediationSut` and `TemporalVulnRemediationSut` (Phase-9 S4-05 forward dep on byte-stable digests).

### What S1-01 forward-depends on

S1-01's AC-4 pins `TerminalState = Literal["completed", "awaiting_human_review", "failed_unrecoverable"]` as the *public* Result's terminal-state field. The ledger's terminal partition MUST match that Literal byte-for-byte — a cross-story membership test asserts this. Adding a new ledger variant without amending `TerminalState` (or vice-versa) is an ADR-0001 amendment, never a `str`-widening.

### What CLAUDE.md load-bearing commitments force

- **Match the existing convention.** Every sum type in the codebase uses `Annotated[..., Field(discriminator="kind")]`. Drives AC-2.
- **Composition over inheritance.** Drives the anti-refactor note (no `BaseLedgerState` ABC; shared evidence lives in injected sub-models like `RecipeError` does in `RecipeFailed`).
- **Make illegal states unrepresentable.** Drives AC-5 closed transition table + `model_validator` enforcement.
- **Newtype identifiers — never raw `str` for domain IDs.** Drives AC-7 `TransitionId` + smart constructor + registry entry.
- **Functional core / imperative shell.** Drives AC-8 `_compute_chain_head` pure helper.
- **Type everything, strictly — `mypy --strict`.** Drives AC-9 `assert_never` exhaustiveness + AC-14 typecheck-clean.
- **Extension by addition — no silent edits.** Drives AC-13 allowlist amendment + AC-15 contract snapshot extension.

### What the existing precedents prescribe

- `src/codegenie/transforms/outcomes.py` is the canonical sum-type module — five discriminated unions, each variant `model_config = ConfigDict(frozen=True, extra="forbid")` (this story uses the `_FROZEN_FORBID` constant landed in S1-01), each umbrella `Annotated[A | B | ..., Field(discriminator="kind")]`. Shared payloads are *composed in* as sub-models (`RecipeError`, `RemediationError`), not inherited from a base class.
- `src/codegenie/types/identifiers.py` is the kernel-tier identifier home; the `_NEWTYPE_REGISTRY` drift test in `tests/unit/types/test_identifiers_phase3.py` already exists and is extended (not forked) for the Phase-6 additions.
- `ChainHead = NewType("ChainHead", str)` already exists (Phase-4 S4-04) — reuse, don't redefine.
- `WorkflowId`, `EventId`, `BlobDigest`, `ErrorId` all already exist — reuse.

### Open ambiguities resolved before critics

- **Q1 — `EvidenceDigest` field type.** Reuse the existing `BlobDigest` newtype (`^[0-9a-f]{64}$` BLAKE3-hex). No new newtype for this — the digest is the same shape as Phase-3's blob digest. Documented in Notes-for-implementer.
- **Q2 — `TransitionId` vs reuse of `EventId`.** Different lifecycles. `EventId` is the two-stream event-log id (Phase-3 S6-01, append-only forensic log). `TransitionId` is the ledger-internal transition id (a chained ULID for replay determinism). Two newtypes; the story adds `TransitionId`.
- **Q3 — Transition table: open registry vs frozen `Final` set?** Frozen `Final` set. The seven-variant universe is closed; the legal `(prior_kind, next_kind)` pairs are derived from final-design.md §"Main workflow" and ADR-0003 §"Consequences" and are equally closed. Adding a new edge is an ADR-0003 amendment, not a runtime decoration. This is the same pattern as `_TERMINAL_STATE_SET`.
- **Q4 — Should `kind` Literals be at the variant class level or extracted to a module-level type alias?** Each variant declares `kind: Literal["needs_plan"] = "needs_plan"` (etc.) — verbatim with `transforms/outcomes.py` convention. A module-level `LedgerStateKind = Literal[...]` alias is ALSO declared for the transition-table key shape (so the `frozenset[tuple[LedgerStateKind, LedgerStateKind]]` is typed). Both — the variant-class Literal and the alias.
- **Q5 — Pure helper home for `_compute_chain_head`.** `src/codegenie/workflows/_chain.py` (new), single-canonical-declaration site. Re-exported into `vuln_ledger.py`'s test surface only; not part of the public `__all__`. Matches S1-01's `_FROZEN_FORBID` discipline (single declaration; consumers import from one place).

## Four-lens findings (inline, no parallel subagents — story scope didn't justify the spawn)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "exist" is unverifiable | block | Replaced with AC-1 (canonical module + seven variant classes + each with named `kind` Literal + closed `LedgerStateKind` alias) and AC-2 (closed discriminated union via `Annotated[..., Field(discriminator="kind")]`). |
| Per-variant evidence payloads unspecified | block | AC-3 enumerates each variant's required field set (e.g., `PlanReady.plan_summary: str`, `PatchApplied.patch_digest: BlobDigest`, `GateFailedRetryable.failing_signals: tuple[SignalKind, ...]`, `AwaitingHumanReview.review_reason: HumanReviewReason`, `FailedUnrecoverable.error: RemediationError`, `Completed.report_path: str | None`). |
| TransitionEvent's five required fields absent | block | AC-4 lists the five fields from final-design.md §"State model" + types + frozen + extra-forbid. |
| Transition-table enforcement unspecified | block | AC-5 mandates the frozen `_LEGAL_TRANSITIONS` set + `model_validator` rejection + membership-byte-equality test. |
| Terminal partition not tied to S1-01 `TerminalState` | block | AC-6 cross-story membership test: terminal partition byte-equal to S1-01 `TerminalState`. |
| New `TransitionId` newtype absent | harden | AC-7 + AC-11 force the newtype + parser + `_NEWTYPE_REGISTRY` entry in the same commit. |
| Chain-head substrate (ADR-0003) absent | block | AC-8 pure helper `_compute_chain_head` + stability + sensitivity properties + AST no-side-effects fence. |
| Exhaustiveness pattern unspecified | block | AC-9 mandates `assert_never` on the default arm of a representative `match` test. |
| JSON round-trip / determinism unstated | harden | AC-10 model_validate_json round-trip + sorted-key byte-determinism. |
| `mypy --strict` AC absent | harden | AC-14. |
| Public surface allowlist amendment unstated | harden | AC-13 extends `codegenie.workflows.__all__` additively + S1-01 AC-12 sentinel re-runs green. |
| Contract snapshot extension unstated | harden | AC-15 extends `tests/integration/test_phase6_sut_contract_snapshot.py` + meta. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| TDD plan Refactor "extract shared bases" violates Rule 2 + composition-over-inheritance | block | Re-ordered: no shared base. Shared payloads are composed sub-models, landed in Green. Refactor is cleanup only. Anti-refactor note added. |
| "Transition-table tests" too generic | block | AC-5 names: (i) every legal pair constructs successfully; (ii) every illegal pair raises `pydantic.ValidationError` with a directive naming the rejected `(prior, next)` and pointing at ADR-0003; (iii) terminal states have ZERO outgoing edges (separate test asserting the closure); (iv) every non-terminal state has at least one outgoing edge (no dead non-terminal). |
| No mutation-thinking pass | block | Each AC's test was checked: swapping `==` to `!=` in the terminal partition test fails AC-6; replacing `_LEGAL_TRANSITIONS` with `frozenset()` fails AC-5; removing `discriminator="kind"` from the umbrella fails AC-2 (the round-trip discriminator-collision test in AC-10); omitting a field from `TransitionEvent.canonical_bytes` fails AC-8 sensitivity; replacing `assert_never` with `pass` fails AC-9. |
| No property-based tests | harden | AC-8 adds two Hypothesis properties (stability + sensitivity for the chain-head helper). AC-5 adds a property: for any pair drawn from `LedgerStateKind × LedgerStateKind` *not* in `_LEGAL_TRANSITIONS`, construction is rejected. |
| No contract-snapshot extension | block | AC-15 extends the existing S1-01 contract snapshot + meta-test; the additive-vs-breaking classifier already lives in S1-01 and inherits. |
| No AST `_FROZEN_FORBID` fence over the new file | block | AC-12 mandates the AST fence — every `BaseModel` subclass in `vuln_ledger.py` sets `model_config = _FROZEN_FORBID`; missing `frozen=True` is a CI failure. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| Story didn't reference ADR-0001, ADR-0003, or final-design.md §"State model" | harden | References block names ADR-0001, ADR-0003, final-design.md §"State model", phase-arch-design.md §"Logical view"+§"Failure modes"+§"Scenarios", High-level-impl.md §"Step 1", S1-01 hardened story, and the relevant `transforms/outcomes.py` precedent. |
| Story didn't reference the `_FROZEN_FORBID` constant landed in S1-01 | block | AC-3 + AC-12 mandate import-from-canonical-site (no re-declaration); the `_FROZEN_FORBID` discipline is now load-bearing. |
| Cross-story membership with S1-01 `TerminalState` unencoded | block | AC-6 — exact membership-byte-equality test. |
| TDD plan "Refactor: shared bases" contradicts CLAUDE.md "composition over inheritance" | block | Rewrote ordering; anti-refactor note forbids the `BaseLedgerState` ABC explicitly and names composition (sub-model fields) as the substitute. |
| No `Depends on:` line | nit | Added "Depends on S1-01 — imports `_FROZEN_FORBID` + asserts terminal partition matches `TerminalState`." |
| Phase-9 chain-head forward dep unstated | harden | AC-8 + Notes-for-implementer surface the Phase-9 S4-05 G5 byte-stability forward dep. |
| `EventId` vs `TransitionId` conflation risk | harden | Notes-for-implementer disambiguates: `EventId` is the Phase-3 two-stream-event-log id; `TransitionId` is the per-transition ledger event id (chained ULID). Two newtypes, two registries. |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| TDD plan Refactor mandates inheritance ("shared bases") where composition is the convention | block | Anti-refactor section forbids `BaseLedgerState` explicitly. Composition via injected sub-models (the `transforms/outcomes.py` precedent — see `RecipeError` injected into `RecipeFailed`). |
| Risk of branching `isinstance` ladder instead of `match`/discriminator dispatch | harden | AC-9 + Notes-for-implementer mandate `match state:` + `assert_never` over `isinstance` ladders, with the existing `transforms/outcomes.py` consumers as precedent. |
| Functional core / imperative shell opportunity for `_compute_chain_head` | harden | AC-8 splits the pure helper from any future impure-shell writer (S2-01). |
| Closed transition table is a Specification pattern opportunity (composable predicates) | nit | Rejected per Rule 2: for a single predicate domain (`(prior, next) ∈ legal_set`) a frozenset is exactly right; Specification pattern earns its keep at 4+ predicates. Documented in Notes-for-implementer for the day Phase 7 adds a second task class's transition table. |
| Tagged-union discipline (vs anaemic `dict[str, Any]` state record) | block | AC-2 + AC-3 — discriminated union via `Annotated[..., Field(discriminator="kind")]`; each variant a closed shape; no `dict[str, Any]`. |
| Open/Closed at the file boundary — future task classes' ledgers (Phase 7) | harden | File naming `vuln_ledger.py` (not `ledger.py`) chosen so Phase-7 `migration_ledger.py` can sit beside it. The seven-variant universe is *vuln-specific*; Phase 7 will have its own sum type, not a shared base. Anti-refactor section pins this. |
| Primitive obsession on `kind` strings | nit | The Literal-on-each-variant + the module-level `LedgerStateKind` alias is the canonical idiom (mirrors `transforms/outcomes.py`); no stronger newtype needed. |
| Hidden state risk in chain-head computation | block | AC-8 AST no-side-effects fence catches `time`, `os.environ`, `random`, `uuid` (the four module names that would silently break replay determinism). |
| Capability-pattern opportunity (constructor-injected `LegalTransitionTable`) | nit | Rejected per Rule 2 — the seven variants and their edges are closed-set Phase-6 data, not pluggable. Documented in Notes-for-implementer for Phase 8+ if planner-generated task classes ever arrive. |

## Synthesis + edit summary

No conflicts between critics. No `NEEDS RESEARCH` findings. The synthesizer applied every fix above in one editing pass:

- 3 ACs → 15 ACs (AC-1 through AC-15), every one individually verifiable with a named test file + failure-mode mutation check.
- TDD plan rewritten in Red-first order with an explicit anti-refactor note (no `BaseLedgerState` ABC; composition only).
- References block populated (8 entries — ADR-0001, ADR-0003, final-design.md §"State model", phase-arch-design.md §"Logical view"+§"Failure modes"+§"Scenarios", High-level-impl.md §"Step 1", S1-01 hardened story + validation report, `transforms/outcomes.py` precedent + `_FROZEN_FORBID` canonical constant, Phase-9 S4-05 forward dep).
- Files to touch enumerated (8 new files + 4 edits — vuln_ledger.py + _chain.py + the four test files; identifiers.py + parsers.py + __init__.py + the contract snapshot extension).
- Out of scope enumerated (4 deferrals + 1 anti-pattern).
- Notes for implementer enumerated (6 entries — discriminator pattern, transition-table closure, chain-head purity, EventId-vs-TransitionId disambiguation, anti-shared-base, Phase-7-ledger-by-addition file naming).
- Status flipped from `Ready` → `HARDENED`. Validated-date line added.

## Verdict — HARDENED. The story is ready for `phase-story-executor`.

The executor's Validator pass now has 15 concrete acceptance criteria, each tied to a named test file and a mutation-resistance check. The cross-story `TerminalState` membership invariant, the ADR-0003 chain-head replay-determinism substrate, the closed-transition-table `model_validator`, the `_FROZEN_FORBID` AST fence, the `_NEWTYPE_REGISTRY` discipline, the `match`+`assert_never` exhaustiveness gate, the composition-over-inheritance constraint, and the additive `codegenie.workflows.__all__` amendment are all encoded as enforceable structural defenses. A mutant implementation that violates any one of them fails at least one test.
