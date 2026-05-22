# Validation report: S4-06 - `SolvedExampleWriter` + Phase-4-local capability mint

**Validated:** 2026-05-22 13:45 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-06 ships the Phase-4 ingestion writer for solved examples: a small `src/codegenie/rag/ingest.py` surface that turns a validated fallback outcome into a canonical `SolvedExample`, writes through `SolvedExampleStore.add(example, capability)`, and exposes the temporary `_phase4_local_capability_mint(...)` used before Phase 5's gates mint exists.

The draft was directionally correct but not executor-ready. It relied on a non-existent `.importlinter` file, asked import-linter to block a function symbol it cannot see, invented a `rag/events.py` event API, and copied stale S1-04 model fields into `RecordProvenance`. The story is now hardened with **4 block, 9 harden, and 1 nit** findings addressed.

## Context brief

- **Story promise:** provide the writer and local mint that S6-03's inline harvest path can call after `TrustOutcome.passed AND confidence == "high"`.
- **Source constraints:** S1-04 owns the `SolvedExample` and four-field `RecordProvenance` shapes; S4-03 owns `SolvedExampleStore.add(example, capability)`; S4-05 established that events live in `codegenie.plugins.events.py` and use `event_type`.
- **Pattern constraints:** module-boundary enforcement, functional core / imperative shell, dependency inversion through the store/embedder protocols, typed event sourcing, and deterministic identifiers.
- **Open ambiguities:** the implementation must stop and surface a conflict if already-landed `SolvedExampleId` code requires full-record hashing, because this story requires a stable ID preimage for ingestion idempotence.

## Findings by critic

### Coverage critic

**C1 (block) - Function-level import-linter contract was impossible.** The draft tried to set `forbidden_modules = codegenie.rag.ingest._phase4_local_capability_mint`. Import-linter reasons about modules/packages, not functions, so the contract would either be invalid or give false confidence.
**Fix:** AC-6/AC-7 now require an AST fence that catches both direct imports and fully-qualified attribute access of the private mint. AC-8 keeps normal import-linter checks green through `pyproject.toml`.

**C2 (block) - Event class used a non-existent RAG event API.** The draft added `src/codegenie/rag/events.py` with a `kind` field. That bypasses the shipped event registry and would not be replayable by `EventLog`.
**Fix:** AC-9 adds `SolvedExampleHarvested` to `src/codegenie/plugins/events.py` as a `WorkflowSpanningEvent` with `event_type`, `prev_hash`, union registration, and replay tests.

**C3 (harden) - Deliberate violation design would break default CI.** The draft put a real forbidden import in `tests/fixtures/violations/` and tried to toggle lint behavior with an env var or special make target.
**Fix:** AC-7 tests the shared AST scanner against fixture source without adding a violating module to the default lint corpus.

**C4 (harden) - Writer/event responsibilities were blurred.** The draft defined the event in the writer story but risked making `ingest_solved_example` emit it.
**Fix:** AC-9 and Notes state that S6-03 emits `SolvedExampleHarvested` after a successful write; the writer remains silent.

### Test-Quality critic

**T1 (harden) - Mint fence only checked `ImportFrom`.** A contributor could bypass the check with `import codegenie.rag.ingest as ingest; ingest._phase4_local_capability_mint(...)`.
**Fix:** AC-6 requires the scanner to catch both `from ... import ...` and fully-qualified attribute access.

**T2 (harden) - No idempotence test.** The draft claimed deterministic IDs but did not require a test that two equivalent outcomes produce the same `SolvedExampleId`.
**Fix:** AC-10 requires an idempotence test over the same outcome and embedder model.

**T3 (harden) - Event registry drift was unpinned.** Adding an event class without union and replay tests could silently leave it unreachable.
**Fix:** AC-11 requires spanning discriminator mapping and `EventLog.emit_spanning(...)` / replay coverage.

**T4 (harden) - Runtime capability limitation needed executable documentation.** The draft mentioned Python cannot prevent hand-forged capabilities, but the test title said `store.add()` rejects them.
**Fix:** AC-10 keeps the documentation test but makes the expected behavior explicit: direct construction still works; CI/review owns the boundary.

### Consistency critic

**K1 (block) - Stale `RecordProvenance` fields were reintroduced.** The draft constructed fields removed by S1-04: `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, and `confidence`.
**Fix:** AC-3 locks the four-field `RecordProvenance` shape and forbids stale fields in the writer.

**K2 (block) - Placeholder outcome used non-existent type names.** `TaskClassName`, `LanguageName`, and `BuildSystemName` conflict with S1-01/S1-04, which established `TaskClassId`, `Language`, and `PackageManager`.
**Fix:** AC-2 uses the canonical newtypes/literal and requires a frozen typed projection instead of dict shuffling.

**K3 (harden) - Story referenced `.importlinter`.** This repo keeps import-linter config in `pyproject.toml`.
**Fix:** references, AC-8, and files-to-touch now name `pyproject.toml` and forbid creating `.importlinter`.

**K4 (harden) - `SolvedExample` embedding storage was ambiguous.** The draft allowed `embedding_vector` to be "depending on schema," which left S4-03/S4-04 integration underspecified.
**Fix:** AC-1 and AC-3 require `embedding_vector` on `SolvedExample`, matching the S4-03 validation caveat that S1-04 must carry the vector.

### Design-Patterns critic

**D1 (harden) - Identity preimage mixed deterministic and per-run fields.** Full-record hashing would include `created_at` or workflow context and break re-ingestion idempotence.
**Fix:** AC-4 defines a deterministic stable preimage and Notes call out the conflict if stricter full-record hashing has already landed.

**D2 (harden) - Keep capability creation off the class.** A `SolvedExampleWriteCapability.mint(...)` classmethod would make minting reachable from every importer of the class.
**Fix:** AC-5 and Notes require a private module function and explain why.

**D3 (harden) - Avoid premature plugin/registry machinery.** A registry would add moving parts before more than one writer exists.
**Fix:** Out of scope explicitly rejects a generic writer registry for this phase.

**D4 (harden) - Preserve functional core / imperative shell.** The writer should orchestrate embed/write; pure identity generation stays isolated.
**Fix:** Implementation outline separates `_solved_example_id_for(...)` from the writer shell.

**D5 (nit) - `record_event_chain_head` needed naming precision.** `chain_head` is overloaded between event-log and content-manifest contexts.
**Fix:** AC-9 names the event field `record_event_chain_head` and defines it as `outcome.event_chain_head`.

## Research briefs

None. The validation used only current repository context: Phase 4 design docs, ADR-0009, ADR-0016, sibling validation reports, `src/codegenie/plugins/events.py`, existing import-linter shape tests, and S1-01/S1-04 story contracts.

## Conflict resolutions

- **Architecture shorthand vs executable lint:** prose that says import-linter blocks the minting symbol is treated as shorthand. The executable boundary is an AST fence because import-linter cannot target a function.
- **Canonical body hashing vs ingestion idempotence:** the story now hashes a stable identity preimage. If implementation code has already made full-body hashing mandatory, the executor must surface the conflict rather than produce nondeterministic solved-example IDs.
- **Writer event visibility vs caller ownership:** `SolvedExampleHarvested` is defined here for S6-03, but emission stays in S6-03 so the writer does not depend on `EventLog`.
- **Capability naming vs runtime guarantee:** the type remains named `SolvedExampleWriteCapability`, but the story explicitly documents that Phase 4 provides a module-boundary convention enforced by tests and review, not runtime unforgeability.

## Edits applied

1. Header updated to `HARDENED`; dependencies expanded to S1-01, S1-04, S4-03, S4-04, and S4-05.
2. Validation notes added with the corrected enforcement and event API decisions.
3. References replaced stale `.importlinter` and `rag/events.py` assumptions with `pyproject.toml` and `src/codegenie/plugins/events.py`.
4. Goal narrowed to writer, temporary mint, and symbol-scope fence.
5. AC-1 through AC-4 now lock writer behavior, typed projection fields, S1-04 model shape, and deterministic ID generation.
6. AC-5 documents the local mint and Phase-5 TODO signature.
7. AC-6 through AC-8 replace the impossible import-linter function contract with an AST fence and normal import-linter verification.
8. AC-9 through AC-11 add the real `SolvedExampleHarvested` event shape and replay tests.
9. Implementation outline, TDD plan, files-to-touch, out-of-scope, and implementer notes were rewritten to match the current repo architecture.

## Verdict rationale

**HARDENED.** The story is now small, typed, and enforceable. It preserves the intended extension path for Phase 5 while avoiding false security guarantees in Phase 4. The remaining risk is explicit: if implementation has already hardened `SolvedExampleId` to require full-record hashing, the executor must reconcile that with ingestion idempotence before coding.

## Recommended next step

`phase-story-executor` can implement S4-06. Start with the tests for `rag/ingest.py` and the AST fence, then extend `src/codegenie/plugins/events.py` by mirroring the existing spanning-event registration pattern.
