# Validation report: S1-04 — RAG-side Pydantic models

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-04 lands seven Phase-4 contract surfaces as frozen Pydantic v2 models — `SolvedExample`, `Query`, `RecordProvenance`, the `RetrievalOutcome` discriminated union (`RagHit | RagMiss | RagDegraded`), `BudgetSnapshot`, `BudgetToken`, `TypecheckNodeSignal` — that every Step 2–7 consumer types against. The goal is sound and traces cleanly to the phase arch; no RESCUE.

Four parallel critics (Coverage, Test-Quality, Consistency, Design-Patterns) found 21 actionable findings — **6 blocks, 11 hardens, 4 nits**. The dominant pattern was *arch-doc drift the story faithfully copied*: two contract surfaces (`RetrievalOutcome` and `BudgetToken`) were specified divergent from their governing ADRs (ADR-0008, ADR-0010), a `PackageManager` import path and type were stale (it is a `Literal` in `codegenie.types.identifiers`, not an `Enum` in `probes.node_build_system`), and a load-bearing dependency on S1-02 was undeclared. The TDD plan was thorough for `SolvedExample` but treated the other six models as second-class — `extra="forbid"`, `frozen`, `Literal`-field, naive-datetime checks each covered exactly one model when the ACs promised all. Every finding had a clear in-place fix; the story was conformed to its ADRs, the TDD plan rewritten to parametrize over all models, and three new ACs added (AC-16 Literal rejection, AC-17 range constraints, AC-18 `_marker` private-attr behavior). Verdict: **HARDENED**.

## Findings by critic

### Coverage critic

- **F1 (block)** — AC-2's `task_class: TaskClassId` "(or `TaskClassName`)" / `language: Language` "(or `LanguageName`)" parentheticals: an AC with an unresolved disjunction is not individually verifiable. `identifiers.py` ships `TaskClassId`/`Language` and no `*Name` variants — the answer is already determined.
- **F2 (block)** — AC-10's TDD code only exercises `extra="forbid"`/`frozen` for `SolvedExample`; `RecordProvenance`, `BudgetToken`, `TypecheckNodeSignal`, `RagDegraded` get no sad-path tests. A lazy impl shipping them `extra="allow"` + mutable passes every test.
- **F3 (harden)** — no `Literal`-field rejection tests for `plan_kind`, `origin`, `signing_method`, `confidence` (only `Query.failure_mode` tested).
- **F4 (harden)** — `RagMiss.reason` literals never exercised; arch edge cases #10/#14/#19 untraced.
- **F5 (nit)** — budget-model tests: AC-10 names `test_models.py` but Files-to-touch names a separate `test_budget_models.py` — ambiguous home.
- Strengths recorded: `Query.digest()` coverage, `BudgetSnapshot` invariants, real `Out of scope`, tz-aware enforcement intent.

### Test-Quality critic

- **F1/F2 (harden)** — `extra="forbid"` and `frozen=True` each tested on `SolvedExample` only; mutation "remove from any other model" survives. Adjacent `tests/unit/transforms/test_outcomes.py` parametrizes over all 16 variants — the idiom to match.
- **F3 (harden)** — `test_query_digest_changes_with_field` perturbs only 3 of `Query`'s 6 fields; a `digest()` ignoring `task_class`/`language`/`build_system` passes.
- **F4 (harden)** — `Query.digest()` constant-return mutation (`return "a"*64`) survives every test except the (under-powered) perturbation table.
- **F5 (harden)** — the Hypothesis property generates only `cve_id`; the other 5 fields are hardcoded. AC-12 round-trip had no concrete test body.
- **F6 (block)** — `test_budget_token_marker` pins a Pydantic v2 *private attribute* default; no test that a forged `_marker=` kwarg is rejected.
- **F7 (harden)** — swapped/loosened `Literal` discriminators survive (`confidence: Literal[...]` → `str`).
- **F8 (harden)** — naive-datetime enforcement tested on `SolvedExample` only; `RecordProvenance` survives validator removal.
- **F9 (harden)** — `RagHit`/`RagDegraded` missing-`record` mutation survives; no keyset pin.
- **F10 (nit)** — `_SOLVED["build_system"]` `hasattr` fallback hides contract uncertainty instead of failing loud.

### Consistency critic

- **F1 (block)** — TDD-plan import `from codegenie.probes.node_build_system import PackageManager` is stale; ADR-0013 Amendment 2026-05-20 moved `PackageManager` to `codegenie.types.identifiers`.
- **F2 (block)** — `PackageManager` mislabeled "enum"; it is a `Literal`. `PackageManager.NPM.value` is invalid (no `.NPM`/`.value` on a `Literal`).
- **F3 (harden)** — field-type names `TaskClassName`/`LanguageName`/`BuildSystemName` (arch §Data model) do not exist in code; canonical names are `TaskClassId`/`Language`/`PackageManager`.
- **F4 (block)** — missing declared dependency on S1-02 (imports `PlanProposal`, writes into the `fallback/` package S1-02 creates).
- **F5 (block)** — `RagHit`/`RagMiss`/`RagDegraded` field shapes contradict ADR-0008 §Decision + arch §Component 9: ADR specifies `RagHit(few_shot, score)`, `RagDegraded(near_match, score)`, `RagMiss` bare. Story shipped `record`/`similarity` and a 4-literal `RagMiss.reason`.
- **F6 (block)** — `BudgetToken` field shape contradicts ADR-0010 §Decision + arch §Component 5: ADR specifies `precharged_tokens`/`precharged_dollars`/`issued_at`/`_marker`. Story shipped `id: BudgetTokenId`/`precharge_tokens`/`_marker`.
- **F7/F9 (nit)** — `BudgetSnapshot` and `TypecheckNodeSignal` shapes confirmed *consistent* with arch/ADRs.
- **F8 (harden)** — `RecordProvenance.signing_method` literal set is unsourced (no ADR enumerates it).
- **F10 (harden)** — Files-to-touch omits `tests/unit/fallback/__init__.py`.
- **F11 (nit)** — AC-to-source traceability: no orphan ACs; three traced to a contradiction (F5/F6/F8) rather than an absence.

### Design-Patterns critic

- **F1 (harden)** — `Similarity`/`TokenCount` range constraints unenforced at the model boundary: both are `NewType`s, Pydantic sees only the base `float`/`int`. `RetrievalOutcome` is built internally from a raw ChromaDB score that never passes `parse_similarity` — an out-of-range `RagHit` is a representable illegal state. Repo idiom `Annotated[..., Field(ge=…, le=…)]` (`scip_slice.py`, `sandbox_jail.py`, `redacted_slice.py`).
- **F2 (harden)** — `BudgetToken._marker` is a Pydantic v2 `ModelPrivateAttr` (leading underscore): not validated, not serialized, not constructor-settable, not `frozen`-protected. The story is not explicit that this is intended.
- **F3 (nit)** — `RetrievalOutcome` uses `Discriminator("kind")`; the implemented repo convention (`transforms/outcomes.py`, 5 unions) is `Field(discriminator="kind")`.
- **F4 (nit, confirmation)** — no shared `FrozenModel` base exists; 40+ modules repeat `ConfigDict(...)` inline. The story's seven inline repetitions are correct (Rule 11) — do NOT introduce a base class.
- **F5 (nit)** — `FailureModeTag` placement: rag-local is defensible (`outcomes.py` keeps reason-taxonomies module-local) but a competing `identifiers.py` precedent exists; document the choice (Rule 7).
- **F6 (nit, confirmation)** — primitive-obsession + functional-core are clean; all identifier fields use existing newtypes; `Query.digest()` is pure.

## Research briefs

None — no finding was tagged `NEEDS RESEARCH`. The two `block` contradictions were resolved by reading the governing ADRs (ADR-0008, ADR-0010) and the arch §Component 5/9 sections directly; the patterns invoked (discriminated union, capability, `Field(ge=…)` range constraint) are all already established in the codebase.

## Conflict resolutions

- **Design-Patterns F2 vs ADR-0010 (Consistency-priority).** The Design-Patterns critic offered, as its preferred option, renaming `_marker` to a public `marker` field. ADR-0010 §Decision explicitly specifies a **"private"** `_marker`. Consistency wins: `_marker` stays a leading-underscore Pydantic v2 `PrivateAttr`; the harden is to make that explicit (`PrivateAttr(default=…)`) and pin the behavior with AC-18 tests, not to rename it.
- **Coverage F4 (`RagMiss.reason`) vs Consistency F5 (Consistency-priority).** Coverage wanted the 4-literal `RagMiss.reason` exercised by tests. Consistency found `RagMiss.reason` itself contradicts ADR-0008 (which specifies a bare `RagMiss`). Consistency wins: `RagMiss` is conformed to bare; the `reason` tests are dropped with it. Chain-orphan / model-mismatch observability lives in the emitted events per edge cases #14/#19, not in the `RagMiss` shape.
- **Design-Patterns F1 vs AC-6's documented "boundary validates" stance (Coverage-priority + repo precedent).** AC-6 originally deferred all `TokenCount ≥ 0` checks to the smart constructor. Design-Patterns showed `RetrievalOutcome`/`BudgetToken` are constructed on internal paths that bypass the smart constructor. The observable illegal-state risk + the unambiguous repo idiom (`Field(ge=…)`) win: AC-17 adds the model-boundary range constraint. This is matching convention, not premature abstraction (Rule 2 check passes).

Synthesis priority chain applied: `Consistency > Coverage > Test-Quality > Design-Patterns`.

## Edits applied

### Edit 1 — story header
- `Status: Ready → HARDENED`; `Depends on: S1-01 → S1-01, S1-02` (Consistency F4); `## Validation notes` block inserted.

### Edit 2 — AC-2 (Consistency F3, Coverage F1)
- `task_class`/`language` "or `*Name`" parentheticals removed — resolved to `TaskClassId`/`Language`.
- `build_system: PackageManager` — "enum" → "`Literal` defined in `codegenie.types.identifiers`".

### Edit 3 — AC-3 (`digest()` wording, F21)
- "(sorted keys, no spaces)" replaced with an accurate description (Pydantic v2 emits definition order; deterministic for a frozen model).

### Edit 4 — AC-4 (Consistency F5, Design-Patterns F3) — block
- `RagHit(kind, few_shot, score)` / `RagDegraded(kind, near_match, score)` / `RagMiss(kind)` bare — conformed to ADR-0008 §Decision + arch §Component 9.
- `RetrievalOutcome` uses `Field(discriminator="kind")`.

### Edit 5 — AC-7 (Consistency F6, Test-Quality F6, Design-Patterns F2) — block
- `BudgetToken` fields conformed to ADR-0010 §Decision + arch §Component 5: `precharged_tokens`, `precharged_dollars`, `issued_at`, `_marker`. `id: BudgetTokenId` dropped.

### Edit 6 — AC-10 (Coverage F2, Test-Quality F1/F2/F8/F9, F5/F19)
- Names both test files; `extra="forbid"`/`frozen`/keyset parametrized over all seven models; `RagHit`/`RagDegraded` required-payload rejection added.

### Edit 7 — AC-13 (Test-Quality F8)
- Naive-datetime test extended to `BudgetToken.issued_at` (was `SolvedExample` only in the TDD code).

### Edit 8 — AC-12 (Test-Quality F5)
- Reworded from "Hypothesis-generated" to a concrete example-based JSON round-trip with a real test body.

### Edit 9 — new ACs AC-16/AC-17/AC-18
- AC-16: `Literal`-field rejection for `plan_kind`/`origin`/`signing_method`/`confidence` (Coverage F3, Test-Quality F7).
- AC-17: range constraints on `score` and `TokenCount` fields via `Annotated[..., Field(ge=…, le=…)]` (Design-Patterns F1).
- AC-18: `_marker` is a Pydantic v2 `PrivateAttr`; default / not-serialized / forged-kwarg-rejected tests (Test-Quality F6, Design-Patterns F2).

### Edit 10 — TDD plan code rewritten
- Import corrected to drop the stale `probes.node_build_system` line (Consistency F1) and the now-unused `Decimal` import in the rag file.
- Fixtures use the bare string `"npm"` (Consistency F2; the `hasattr` fallback dropped — Test-Quality F10).
- `extra="forbid"`/`frozen`/keyset parametrized over all models; `Literal`-rejection, range, naive-datetime, required-payload tests added.
- `digest()` perturbation extended to all six `Query` fields (Test-Quality F3/F4); the Hypothesis property draws all six fields with a metamorphic field-sensitivity relation (Test-Quality F5).
- `BudgetSnapshot`/`BudgetToken` tests moved into a separate `tests/unit/fallback/test_budget_models.py` block (Coverage F5).
- AC-12 round-trip got a concrete example-based test body.

### Edit 11 — Implementation outline / Files to touch
- `tests/unit/fallback/__init__.py` added (Consistency F10); outline steps updated for the conformed shapes, the shared datetime validator, and `Field(ge=…)`.

### Edit 12 — Notes for the implementer
- Rewrote the canonical-names, `PackageManager`, `digest()`, `_marker`, `RetrievalOutcome` notes; added notes for the range constraints, the unsourced `signing_method` literals (verify before GREEN — F8/F17), `FailureModeTag` placement (F5/F20), and the no-shared-base confirmation (F4).

## Verdict rationale

**HARDENED.** The story's goal — ship seven RAG-side contract models — is sound and traces to the phase arch; no goal rewrite is needed, so this is not a RESCUE. All six `block` findings have clear, mechanical in-place fixes: conform two model shapes to their governing ADRs, correct a stale import path and a `Literal`-vs-`Enum` misconception, resolve an unverifiable "or" by reading the authoritative `identifiers.py`, and declare a missing dependency. The eleven `harden` findings are the standard TDD-plan strengthening (parametrize the contract checks over every model, kill the constant-`digest()` mutation, enforce range constraints). This is the same arch-doc-drift failure mode that S1-02 and S1-03 hardening already corrected for this phase — the story was a faithful copy of an arch doc that itself drifted from the ADRs and the implemented codebase.

## Recommended next step

`phase-story-executor` to implement S1-04. The executor must, per the hardened story: import `PackageManager` from `codegenie.types.identifiers`; verify the `RecordProvenance.signing_method` literal set against the Phase-3 spanning-log chain implementation before declaring GREEN; and confirm Pydantic v2's `extra="forbid"` rejects a forged `_marker=` kwarg (AC-18) during the red phase.
