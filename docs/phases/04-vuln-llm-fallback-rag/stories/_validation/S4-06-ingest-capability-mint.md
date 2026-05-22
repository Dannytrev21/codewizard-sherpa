# Validation report: S4-06 - `SolvedExampleWriter` + capability mint boundary

**Validated:** 2026-05-22 13:45 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-06 ships the Phase-4 solved-example writer, the interim write-capability mint, the CI boundary around that mint, and the typed `SolvedExampleHarvested` event S6-03 will emit. The goal is sound and traces to High-level-impl Step 4, phase-arch Component 10, final-design Component 9, ADR-0016, and ADR-0003.

The draft was not executor-ready. It tried to enforce a function-symbol import with import-linter, referenced a non-existent `.importlinter` file, pre-allowed future `codegenie.gates.*` imports that import-linter would treat as unmatched, copied stale S1-04 `RecordProvenance` fields, used stale type names, and placed `SolvedExampleHarvested` in a new `rag/events.py` module instead of the actual `plugins.events` event union. All blockers were fixable in place. The story is now hardened with 18 findings addressed: **5 block, 10 harden, 3 nit**.

## Context brief

- **Story promise:** provide `ingest_solved_example(...)`, an interim Phase-4 mint, a lint/test boundary that makes the mint private by module, and a typed harvest event for caller emission.
- **Source constraints:** import-linter config lives in `pyproject.toml`; existing event log lives in `src/codegenie/plugins/events.py`; S1-04 owns the exact `SolvedExample` / `RecordProvenance` shapes; S4-03 requires `SolvedExample.embedding_vector`.
- **Pattern constraints:** honest Module Boundary + CI enforcement, functional core / imperative shell, dependency inversion through `SolvedExampleStore` and `Embedder`, and extension by addition for Phase 5's gates mint.
- **Open ambiguities after edit:** none. The arch's "mint under ingest.py" shorthand is resolved by a private module because that is the only import-linter-enforceable shape.

## Findings by critic

### Coverage critic

**C1 (block) - The mint boundary was not mechanically enforceable.** import-linter cannot forbid importing a function symbol inside a public module. A contract naming `codegenie.rag.ingest._phase4_local_capability_mint` does not name an importable module.
**Fix:** AC-5 moves the mint to `src/codegenie/rag/_capability_mint.py`; AC-6 adds a module-level forbidden contract; AC-7 adds AST guards for symbol-level bypasses.

**C2 (block) - `.importlinter` does not exist.** The draft referenced `.importlinter`, but the repo uses `pyproject.toml [tool.importlinter]` and `make lint-imports`.
**Fix:** AC-6/AC-7 use `pyproject.toml`, mirroring S1-06 and Phase-3 shape tests.

**C3 (harden) - No live-fire proof the mint contract fires.** A static shape test catches drift but not runtime import-linter behavior.
**Fix:** AC-7 plants a temporary violating module, runs the real `lint-imports` console script, asserts non-zero exit, and cleans up in `finally`.

**C4 (harden) - Deterministic id was underspecified.** The draft said BLAKE3 canonical body bytes but did not say which fields are in or out.
**Fix:** AC-3 pins the exact stable identity fields and excludes workflow/run-context fields.

### Test-Quality critic

**T1 (block) - Pre-allowing future gates imports breaks lint.** S1-06 verified import-linter 2.x defaults unmatched ignores to errors. The draft's `{src/codegenie/gates/}` pre-allowlist would fail until the gates module exists.
**Fix:** AC-6 allows only the real S4-06 edge; Notes instruct Phase 5 to append its edge when real.

**T2 (harden) - Stale provenance fields could survive tests.** The implementation snippet wrote `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, `confidence`, and other fields removed by S1-04.
**Fix:** AC-4 adds an AST/source stale-field guard; AC-2/Outline use only the four S1-04 fields.

**T3 (harden) - Writer silence was untested.** The story said the caller emits `SolvedExampleHarvested`, but no test prevented writer-side event emission.
**Fix:** AC-10 asserts `ingest_solved_example(...)` never reaches `EventLog` / `emit_internal`.

**T4 (harden) - Forged-capability limitation needed a positive assertion.** The design says no runtime unforgeability, but the test plan risked implying fabricated capabilities should fail.
**Fix:** AC-8 documents and tests the intentional runtime limitation.

### Consistency critic

**K1 (block) - Wrong event module and discriminator.** `src/codegenie/rag/events.py` with `kind` would fork the event registry and bypass `EventLog.emit_internal(...)`.
**Fix:** AC-9 registers `SolvedExampleHarvested` in `src/codegenie/plugins/events.py` as a `WorkflowInternalEvent` with `event_type`.

**K2 (block) - Outcome and model names drifted from S1-04/S1-01.** The draft used `TaskClassName`, `LanguageName`, `BuildSystemName`, omitted `advisory_digest`, and left `embedding_vector` ambiguous.
**Fix:** AC-1 uses `TaskClassId`, `Language`, `PackageManager`, includes `advisory_digest`, and AC-2 requires `embedding_vector`.

**K3 (harden) - Dependency list was too narrow.** The draft depended only on S4-05 but imports S1-01, S1-02, S1-03, S1-04, S1-06, S4-01, S4-03, S4-04, and S4-05 surfaces.
**Fix:** header dependencies expanded and preconditions named.

**K4 (harden) - Writer gate responsibility was blurred.** The draft carried confidence into the writer projection even though final-design puts the `TrustOutcome.passed AND confidence == "high"` rule in the caller.
**Fix:** AC-1 omits confidence and AC-2/Notes state the writer must not gate.

### Design-Patterns critic

**D1 (harden) - Functional core / imperative shell needed sharper edges.** The draft built and wrote everything inline, making deterministic-id tests and side-effect tests harder.
**Fix:** Implementation outline names pure helpers for identity bytes, id construction, and record construction; `ingest_solved_example` is the impure shell.

**D2 (harden) - Classmethod mint would defeat the boundary.** The draft's Notes correctly warned against classmethod minting, but the AC shape still made the function public through `ingest.py`.
**Fix:** private module plus `__all__` exclusion keeps the import boundary concrete.

**D3 (harden) - No speculative registry.** A writer registry or plugin architecture is unnecessary for one writer and one interim mint.
**Fix:** Notes explicitly reject a registry for S4-06; the extension point is Phase 5's replacement mint module.

**D4 (nit) - `ModelId(str(embedder.model_digest()))` needs a boundary comment.** `model_digest()` returns `BlobDigest`; S1-04's field is `ModelId`.
**Fix:** Notes call this out as an explicit adapter until the model field is amended.

## Research briefs

None. No finding required external research. The decisive references were in-repo: import-linter config/tests, S1-06 validation, `src/codegenie/plugins/events.py`, prior Phase-4 event-surface validations, S1-04 model contract, and S4-03/S4-04 validator reports.

## Conflict resolutions

- **Arch location vs import-linter mechanics:** arch prose says `_phase4_local_capability_mint` is under `ingest.py`; import-linter cannot enforce that symbol boundary. The enforceable equivalent is a one-purpose private module imported only by `ingest.py`, plus an AST fence for symbol bypasses.
- **Future gates allowlist vs current lint pass:** final-design names `{gates, ingest}` as the long-term allowlist; S1-06 verified unmatched future ignores fail today. The story ships only the current edge and leaves Phase 5 to extend it.
- **Event registration now vs emission later:** registering `SolvedExampleHarvested` here is useful for S6-03, but writer emission would blur responsibilities. AC-9 registers; AC-10 keeps writer silent.

## Edits applied

1. Header set to `HARDENED`; dependency line expanded.
2. Validation notes inserted.
3. Context rewritten around the enforceable private-module mint boundary.
4. Goal rewritten as four deliverables: writer, private mint, pyproject/fence boundary, event registration.
5. AC-1 adds the typed `ValidatedPlanOutcome` shape and removes stale `*Name` aliases.
6. AC-2 pins keyword-only writer behavior, exact embed/store call counts, exact `RecordProvenance` fields, and no event emission.
7. AC-3 adds deterministic id field-inclusion/exclusion rules.
8. AC-4 adds the stale S1-04 field guard.
9. AC-5 moves the mint to `src/codegenie/rag/_capability_mint.py` and forbids re-export from `ingest.py`.
10. AC-6 replaces `.importlinter` with a `pyproject.toml` contract and removes future unmatched ignores.
11. AC-7 adds contract shape, AST, and live-fire planted-violation tests.
12. AC-8 documents the intentional forged-capability runtime limitation.
13. AC-9 moves `SolvedExampleHarvested` to the real `plugins.events` surface.
14. AC-10 pins writer silence.
15. Implementation outline, TDD plan, files-to-touch, out-of-scope, and notes rewritten to match the hardened architecture.

## Verdict rationale

**HARDENED.** The story's goal is valid, but the draft mixed an unenforceable symbol-level lint boundary with stale S1-04 and event-log assumptions. The hardened version keeps the scope intact while making the module boundary observable, preserving the functional-core / imperative-shell split, and using the repo's existing event-sourcing registry. No RESCUE condition remains.

## Recommended next step

`phase-story-executor` can implement S4-06 after the known S4-03/S1-04 precondition is cleared: `SolvedExample` must carry `embedding_vector: EmbeddingVector`. Start with the mint contract tests and event registration, then implement `ingest.py`.
