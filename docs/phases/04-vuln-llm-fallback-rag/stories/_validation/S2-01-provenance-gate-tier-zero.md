# Validation report: S2-01 — ProvenanceGate as explicit tier-0 short-circuit

**Validated:** 2026-05-21 13:35 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-01's intent is sound: ship a tiny Phase-4 provenance gate that runs before any LLM/RAG/budget surface and emits a typed classification event. The draft was not executor-ready because it forked the already-shipped production `vuln.provenance` primitive, used the wrong event-log API, depended on later sibling S2-05 for a load-bearing test, and named non-importable input types. All four blockers were fixable in place. The hardened story now consumes `codegenie.primitives.vuln_provenance`, tests real Pydantic variants, emits through `codegenie.plugins.events.EventLog.emit_internal`, and proves zero-spend locally with a signature/import fence.

## Context brief

- **Story snapshot:** `ProvenanceGate.classify` is the tier-0 decision used by S6-01's `FallbackTier.run` before any token spend.
- **Phase exit criteria:** G7 says non-app-layer CVEs spend zero LLM tokens; ADR-0012 makes the gate explicit; production ADR-0038 supplies the seven-variant provenance primitive.
- **Existing code reality:** `src/codegenie/primitives/vuln_provenance/` already contains `Provenance`, seven variant classes, `SyftSbom`, `VulnProvenanceAdapter`, `assemble_provenance`, and `ProvenanceError` / `AdapterError`. `src/codegenie/plugins/events.py` contains the actual two-stream `EventLog`; `src/codegenie/audit.py` is the Phase-0 gather audit writer and has no `EventLog`.
- **Open ambiguities:** none requiring user input. The arch shorthand `classify(advisory, repo_ctx)` was resolved against current typed primitives as `classify(cve_id, package_id, image_ref, sbom)`, with S6-01 owning extraction from advisory/repo context.

## Findings by critic

### Coverage critic

- **F1 (harden) — Table coverage used strings, not variants.** The draft table parametrized over `"AppDirect"` / `"BaseImage"` strings. A wrong implementation could accept strings while failing the real Pydantic union. Fixed by requiring real `Provenance` variant instances and lower-case `kind` assertions.
- **F2 (harden) — Event registration not made observable against the actual union.** The draft pointed at a non-existent or optional `test_event_kinds_complete.py` and `src/codegenie/audit.py`. Fixed by asserting `WorkflowInternalEvent`'s discriminator mapping contains `"provenance_classified"` and the event constructs with typed payload.
- **F3 (harden) — Zero-token proof depended on later S2-05.** A skipped `LlmInvocationGuard` test would let S2-01 be marked done without proving G7. Fixed with an AST/signature fence that proves no spend surface is reachable from this primitive.

### Test-Quality critic

- **F4 (harden) — `MagicMock(spec=Protocol)` is too weak.** `@runtime_checkable` Protocols verify method names only at runtime; `MagicMock` would not prove call signature or typed arguments. Fixed with hand-rolled fake classifiers that capture `(CveId, PackageId, ImageRef | None, SyftSbom)`.
- **F5 (harden) — Event assertions read a non-existent `log.events` list.** Current `EventLog` persists zstd streams and exposes `replay()`. Fixed by requiring replay-based assertions.
- **F6 (harden) — Error-path test swallowed too much.** The draft caught any `Exception`; a programming bug could be hidden as `Unknown`. Fixed by folding only `ProvenanceError` (including `AdapterError`) and asserting unrelated exceptions propagate.

### Consistency critic

- **C1 (block) — Duplicate `VulnProvenanceAdapter` / `Provenance` definitions.** Production ADR-0038's primitive is already implemented under `codegenie.primitives.vuln_provenance`; the draft would create a second incompatible `Literal[...]` surface under `fallback/`. Fixed by consuming the existing primitive and forbidding local duplicate definitions.
- **C2 (block) — Wrong event-log module/API.** The draft referenced `codegenie.audit.EventLog` and `event_log.emit(...)`. Actual event sourcing is `codegenie.plugins.events.EventLog` with `emit_internal` / `emit_spanning`. Fixed throughout the ACs, outline, files-to-touch, and TDD plan.
- **C3 (block) — Non-importable input types.** `CveAdvisory` and `RepoContext` are not concrete types in current source. Existing provenance assembly consumes `CveId`, `PackageId`, `ImageRef | None`, and `SyftSbom`. Fixed by making those the primitive inputs and documenting that S6-01 owns extraction.
- **C4 (block) — AC-7 could not be green before S2-05.** The story order allows S2-01 before S2-05. A load-bearing AC cannot require a later sibling. Fixed by replacing the budget-object assertion with a local boundary fence.
- **C5 (harden) — PascalCase kind values contradict production ADR-0038 implementation.** Current discriminators are lower-case (`app_direct`, etc.). Fixed in the constant, event payload, table tests, and notes.

### Design-Patterns critic

- **D1 (harden) — Forking the primitive violates hexagonal/port discipline.** The existing `primitives/vuln_provenance` package is the stable port/adapter kernel. The Phase-4 gate should be a leaf facade, not a second kernel. Fixed by introducing only a local `ProvenanceClassifier` facade.
- **D2 (harden) — Event stream should be event-sourced, not ad hoc audit.** The gate's observable decision belongs in the typed workflow-internal event stream. Fixed by adding `ProvenanceClassified` to `plugins.events`.
- **D3 (nit) — Keep the specification seam narrow.** The draft had `is_app_layer` but used string membership in a way that could drift from model reality. Fixed as one pure predicate over `provenance.kind`.

## Research briefs

None. Every finding was resolved by reading in-repo docs and source files; no external research was needed.

## Conflict resolutions

- **Phase ADR wording vs implemented primitive.** ADR-0012 uses PascalCase names in prose for `_APP_LAYER_PROVENANCE_KINDS`, while production ADR-0038 and `types.py` use lower-case discriminator values. The implementation is the runnable contract; the story now uses lower-case values and notes the class-name/value distinction.
- **Arch shorthand vs current typed inputs.** The arch says `classify(advisory, repo_ctx)`. Current provenance assembly has concrete typed inputs. The story resolves the primitive boundary to those typed inputs and assigns extraction from advisory/repo context to S6-01, preserving scope and strict typing.

## Edits applied

1. Header `Status: Ready -> HARDENED` and added `Validation notes`.
2. Context rewritten to name the existing production primitive and lower-case discriminator contract.
3. References updated from `src/codegenie/audit.py` / `probes/base.py` to `primitives/vuln_provenance/*` and `plugins/events.py`.
4. Goal rewritten to `classify(cve_id, package_id, image_ref, sbom)` and lower-case `_APP_LAYER_PROVENANCE_KINDS`.
5. AC-2 replaced duplicate `VulnProvenanceAdapter`/`Literal` with "consume existing primitive; optional local `ProvenanceClassifier` facade only."
6. AC-5/AC-9 now require `ProvenanceClassified` as a `WorkflowInternalEvent`.
7. AC-7 now folds only `ProvenanceError` / `AdapterError`; unrelated exceptions propagate.
8. AC-8 now proves zero-spend with AST/signature checks instead of importing S2-05's budget guard.
9. Implementation outline and TDD plan rewritten to use real variant fixtures, `EventLog.replay()`, and hand-rolled typed fakes.
10. Files-to-touch updated to include `src/codegenie/plugins/events.py`, `tests/unit/plugins/test_events.py`, and the new zero-spend fence; removed `src/codegenie/audit.py`.
11. Notes for implementer expanded around facade-vs-kernel, lower-case discriminators, error discipline, event stream choice, and no-spend surface.

## Verdict rationale

HARDENED. The story's goal is valid and traces cleanly to ADR-0012 / G7. The blockers were stale-codebase assumptions and weak tests, not a wrong goal. After hardening, every AC is verifiable, the tests would fail against the obvious wrong implementations (string-only provenance, generic emit API, swallowed programming errors, budget-surface import), and the implementation path follows the existing port/adapter and event-sourcing seams.

## Recommended next step

`phase-story-executor` can implement S2-01. The executor should start from the existing `codegenie.primitives.vuln_provenance` fixtures and `codegenie.plugins.events` test conventions, then run strict mypy and the new zero-spend fence before marking the story done.
