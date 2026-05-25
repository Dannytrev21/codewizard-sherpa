# Validation report — S1-01 (SUT contract types)

**Date:** 2026-05-25
**Validator:** phase-story-validator (inline four-lens analysis — Coverage, Test-Quality, Consistency, Design-Patterns — applied directly after Stage 1's Context Brief; the story is small enough and the lenses converge sharply enough that spawning four parallel critic agents would have burned tokens without changing the verdict, per the skill's token-economy guidance).
**Verdict:** **HARDENED**
**Story path:** [`docs/phases/06-sherpa-vuln-loop/stories/S1-01-sut-contract-types.md`](../S1-01-sut-contract-types.md)

## Why HARDENED (not STRONG, not RESCUE)

The story's *architectural intent* is correct: it names the four ADR-0001 symbols and the redaction theme, and Step 1 of High-level-impl.md is the contracts-first foundation the rest of Phase 6 depends on. But every AC was a vague qualitative statement and the TDD plan reversed CLAUDE.md's load-bearing rule. Specifically:

1. **AC-1 was un-verifiable.** `"`X`, Y, Z exist"` — exist with what shape? what fields? what types? An executor could ship four empty `BaseModel` subclasses and pass.
2. **AC-2 was vague.** "Result serialization exposes only sanitized evidence" names no enforcement mechanism. The executor's Validator pass can't binary-pass-fail "sanitized" — needs Pydantic field validators + property-based rejection tests against the canonical regex set.
3. **AC-3 was hollow.** "Contract snapshot tests pass" — what symbols? what shape? Where's the golden? Phase-3 S6-06 validation already showed how badly contract-snapshot stories drift when these aren't pinned (six block-tier corrections).
4. **TDD plan ordering contradicted CLAUDE.md.** "Refactor: extract shared identifiers into newtypes" inverted the rule. CLAUDE.md states *Newtype identifiers under `codegenie.types.identifiers` — never raw `str` for domain IDs* as a load-bearing commitment. Newtypes are Red+Green, not Refactor.
5. **Cross-phase contract was unencoded.** Phase 9 S4-05 already commits the `SutDigest` to byte-identical output across `LocalVulnRemediationSut` and `TemporalVulnRemediationSut`. Without the pure-helper / no-side-effects discipline pinned *here*, the executor of S5-01 (the concrete adapter) would write a `digest()` that touches the clock and silently break the Phase-9 conformance test 800 commits later.
6. **Phase-6.5 import fence was missing.** Phase-arch-design §"Failure modes" mandates "SUT result leaks prompt/raw path → contract serialization test → CI failure" and §"Contract boundary" says Phase 6.5 may not depend on graph internals. There was no AC turning that into an actual test.
7. **No mutation-resistance.** "Forbidden-field tests" is too generic — a mutant model with `extra="allow"` passes. A mutant model with `terminal_state: str` (instead of `Literal[…]`) passes. A mutant `digest()` returning `uuid.uuid4()` passes "serialization tests." The new ACs encode the specific shape so mutants die.
8. **Contract snapshot meta-test missing.** The S6-06 validation report singled this out as the scariest failure mode: an additive-vs-breaking classifier with `==` swapped for `!=` silently leaks breaking changes. Phase 6's snapshot must inherit the meta-test discipline.
9. **Newtype registry drift wasn't required.** Phase-3 ADR-0010 + the existing `_NEWTYPE_REGISTRY` drift test exist precisely so a new newtype lands with its registry entry in the same commit. The story added three newtypes without naming the registry.
10. **Public-surface allowlist sentinel missing.** CLAUDE.md "Extension by addition — no silent edits" needs an actual test; otherwise an executor enthusiastically adds a fifth public name and the next phase inherits it.

All in-place fixable, none requires re-running `phase-story-writer`. The story's structure (one paragraph goal, three-section TDD plan, contract-snapshot ambition) survives — the four ACs grew to twelve, the TDD plan was reordered, and Files-to-touch + Notes-for-implementer were added. Verdict: **HARDENED**.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (post-edit):** ship `src/codegenie/workflows/{__init__.py,vuln_sut.py}` plus three kernel-tier newtypes + smart constructors + `_NEWTYPE_REGISTRY` entries; ship a Phase-6.5-facing public-import boundary with an allowlist sentinel, sanitization-by-construction validators, a digest-substrate pure helper with byte-stability + sensitivity property tests, an AST no-side-effects fence on any future `digest()` implementation, and a contract snapshot + meta-test pair under `tests/integration/`.
- **Status pre-validation:** `Ready` — never executed; never validated.
- **Status post-validation:** `HARDENED`.

### What ADR-0001 commits us to

The four names are the harness-facing public surface. Concrete graph builder stays private. Contract changes require ADR amendment. Phase 6.5 imports the contract only. Future task classes (Phase 7 migration; Phase 8+ planner integration) may add *sibling* SUTs but never modify these four shapes.

### What final-design.md §"State model" pins

Closed sum-type ledger: `NeedsPlan`, `PlanReady`, `PatchApplied`, `GateFailedRetryable`, `AwaitingHumanReview`, `Completed`, `FailedUnrecoverable`. Three of those seven are terminal. The Result's `terminal_state` field is the closed Literal `{completed, awaiting_human_review, failed_unrecoverable}` — the four non-terminal states MUST NOT be reachable through the public Result.

### What phase-arch-design.md §"Failure modes" pins

| Failure | Detection | Required behavior |
|---|---|---|
| SUT result leaks prompt/raw path | contract serialization test | CI failure |
| node attempts direct peer call | AST test | CI failure |

This story owns the *first* row. The second belongs to S3-01 (subgraph topology) but the AC-6 placeholder fence asserts the substrate is in place.

### What Phase 9 S4-05 forward-depends on

S4-05's G5 conformance: `LocalVulnRemediationSut.digest()` and `TemporalVulnRemediationSut.digest()` produce byte-identical bytes for byte-identical input. This story doesn't own G5 — but it owns the *digest substrate* that makes G5 reachable. Pure helper, no I/O, no clock, no env → AST-fenced via AC-7's no-side-effects test.

### What CLAUDE.md load-bearing commitments force

- **Newtype identifiers under `codegenie.types.identifiers` — never raw `str` for domain IDs.**
- **Extension by addition — no silent edits.** Drives AC-12 allowlist sentinel.
- **Functional core / imperative shell.** Drives AC-7 pure-helper structure.
- **Type everything, strictly — `mypy --strict`.** Drives AC-11.
- **Explicit-import collection point — no entry-point scan.** Drives AC-1 explicit `__all__`.

### Open ambiguities resolved before critics

- **Q1 — Where does `_FROZEN_FORBID` live?** Two options: re-export the existing `transforms.outcomes._FROZEN_FORBID`, or declare a new one at `codegenie.workflows._frozen`. Either is consistent with ADR-0010 Amendment 2026-05-18 (single canonical declaration site); the choice is a one-line code comment. The story names this explicitly to prevent two declarations.
- **Q2 — Should the digest's pure helper be a method or free function?** Free function (`_compute_sut_digest_input`). Methods on Protocols are the impure shell; free helpers are the pure core. Phase-3 / Phase-4 follow this — see e.g. `compose_bundle_cache_key`.
- **Q3 — Closed Literal vs. discriminated union for `terminal_state`?** Closed Literal. The full payload-carrying state union is the *ledger* (S1-02), not the public Result. The harness reads `terminal_state` as a string for scorecard grouping.

## Four-lens findings (inline, no parallel subagents — story scope didn't justify the spawn)

### Lens 1 — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| AC-1 "exist" is unverifiable | block | Replaced with AC-1 (canonical module + re-exports + import-identity test) and AC-2 (Protocol shape with byte-exact annotation match). |
| Field list for `VulnRemediationCase` undefined | block | AC-3 lists all five fields + types + smart constructors + closed `execution_mode` Literal. |
| Field list for `VulnRemediationResult` undefined | block | AC-4 lists all eight fields + sub-models + cross-field invariants via `model_validator`. |
| `terminal_state` set not pinned | block | AC-4 explicitly pins `{completed, awaiting_human_review, failed_unrecoverable}` and forbids the four non-terminal ledger names; membership-byte-equality test. |
| Sanitization predicate vague | block | AC-5 three Hypothesis properties + two example-based negatives with directive-text assertion. |
| `SutDigest` semantics unpinned | block | AC-7 stability + sensitivity property tests + AST no-side-effects fence. |
| JSON round-trip / determinism not asserted | harden | AC-8 round-trip + sorted-key byte-determinism. |
| Newtypes added without registry | block | AC-10 forces `_NEWTYPE_REGISTRY` entries + extends the drift test. |
| Phase-6.5 import-boundary not encoded | harden | AC-6 import fence + placeholder Phase-6.5 fence. |
| No `mypy --strict` AC | harden | AC-11. |
| No public-surface allowlist | block | AC-12 allowlist sentinel. |

### Lens 2 — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| TDD plan ordering puts newtypes in Refactor | block | Re-ordered: newtypes land in Green per CLAUDE.md. Refactor is cleanup only. |
| "Serialization tests" too generic | block | Each AC names specific tests + their failure modes. |
| No mutation-thinking pass | block | Each AC's test was checked: a swap from `==` to `!=`, `extra="forbid"` to `extra="allow"`, `Literal[…]` to `str`, `regex.fullmatch` to `regex.search`, or omitting a digest field would each fail at least one test. |
| No property-based tests | harden | AC-5 + AC-7 add four Hypothesis properties covering sanitization + digest stability + digest sensitivity. |
| No contract-snapshot meta-test | block | AC-9 ships both the snapshot test and a meta-test that classifies synthetic additive vs. breaking deltas. Closes the S6-06-flagged failure mode. |
| No AST fence on `digest()` purity | harden | AC-7 ships the AST test as a placeholder; starts trivially passing, starts biting in S5-01. |

### Lens 3 — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| Story didn't reference ADR-0001 | harden | References block now names ADR-0001 + phase-arch-design + final-design + High-level-impl. |
| Story didn't name the canonical module | harden | AC-1 names `src/codegenie/workflows/vuln_sut.py`; matches phase-arch-design §Development view. |
| TDD plan "Refactor: extract newtypes" contradicts CLAUDE.md | block | Rewrote ordering; newtypes are Green. Anti-refactor note added explaining what NOT to do (no registry, no BaseSut). |
| No `Depends on:` line | nit | Added "Foundation — no upstream story deps." |
| Sanitization regex set forking risk | block | Notes-for-implementer explicitly mandates importing the canonical set from `codegenie.output.sanitizer`, not forking. Phase-9 critique report flagged exactly this drift pattern. |
| Cross-phase digest invariance unstated | block | AC-7 + Notes-for-implementer surface the Phase-9 S4-05 G5 forward dep. |
| Phase-6.5 import boundary unstated | block | AC-6 ships the fence test. |

### Lens 4 — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| Risk of locking in a class-hierarchy that prevents future SUT registry | harden | File naming + `__all__` allowlist sentinel chosen so a `@register_sut_kind` registry can be added additively in Phase 9 when rule-of-three is reached. |
| Risk of over-design via premature `BaseSut` ABC | harden | Anti-refactor section forbids it explicitly; Notes-for-implementer cites Rule 2. |
| Functional core / imperative shell opportunity for digest | harden | AC-7 splits the pure helper from the impure Protocol method. |
| Smart constructor opportunity for `EvidenceRef` | harden | AC-4 + AC-5 require a smart-constructed `EvidenceRef` that rejects absolute paths + secret shapes at construction. |
| Tagged-union vs Literal for `terminal_state` | nit (consistency) | Closed Literal is the right shape for the public Result; the full payload-carrying union is the ledger's job. Documented in Notes-for-implementer. |
| Single-source-of-truth for `_FROZEN_FORBID` | harden | Q1 resolved: one canonical declaration site per ADR-0010 Amendment 2026-05-18. |
| Public-surface allowlist sentinel | harden | AC-12 — extension by addition becomes a load-bearing test, not a convention. |
| Newtype catalog discipline | harden | AC-10 — registry-entry-in-same-commit + drift test. |

## Synthesis + edit summary

No conflicts between critics. No NEEDS RESEARCH. The synthesizer applied every fix above in one editing pass:

- 3 ACs → 12 ACs (AC-1 through AC-12), every one individually verifiable with a named test file + failure-mode mutation check.
- TDD plan rewritten in Red-first order with an explicit anti-refactor note.
- Files to touch enumerated (10 new files + 2 edits).
- Out of scope enumerated (5 deferrals + 1 anti-pattern).
- Notes for implementer enumerated (6 entries — covers contract-amendment discipline, terminal-state shape, evidence-ref rationale, functional-core/imperative-shell split, SUT-registry rule-of-three deferral, contract-snapshot meta-test non-negotiability, AST-no-side-effects rationale).
- Status flipped from `Ready` → `HARDENED`. Validated-date line added.

## Verdict — HARDENED. The story is ready for `phase-story-executor`.

The executor's Validator pass now has 12 concrete acceptance criteria, each tied to a named test file and a mutation-resistance check. The Phase-6.5 import boundary, the Phase-9 digest-invariance forward dep, the Phase-1 ADR-0007 error-ID format, the Phase-2/4 sanitization regex set, the ADR-0010 newtype registry discipline, and the CLAUDE.md "extension by addition" allowlist are all encoded as enforceable structural defenses. A mutant implementation that violates any one of them fails at least one test.
