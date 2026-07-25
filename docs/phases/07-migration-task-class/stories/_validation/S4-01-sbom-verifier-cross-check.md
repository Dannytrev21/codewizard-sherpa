# Validation report — S4-01 `sbom_verifier.py` cross-check pure function

**Validated:** 2026-07-24 (pre-executor pass)
**Validator:** phase-story-validator
**Verdict:** **HARDENED**
**Story file:** `docs/phases/07-migration-task-class/stories/S4-01-sbom-verifier-cross-check.md`

## Context

Pre-executor validation on a `Ready` (never-shipped) story. Story shape was already strong (sum-type discipline, purity discipline, ADR alignment, functional-core framing) but had **three block-severity structural issues** that would have caused the executor to either produce a fence collision, hit an import wall, or write a smart-constructor with nothing to catch:

1. **Fence-file collision with S4-04** — S4-01 AC-14 named a standalone fence file; S4-04 AC-10 explicitly says its fence walks the same three modules including `sbom_verifier.py`. Two owners, one policy — the story that shipped later would silently overwrite the earlier.
2. **Import allowlist blocked the actual smart constructor** — AC-6's frozen import set omitted `codegenie.types.parsers`, but AC-11 requires calling `parse_layer_digest`. `identifiers.py`'s `LayerDigest` is a bare `NewType` with no validation, so the fence would have to fail on any real implementation of AC-11.
3. **`try_cross_check` had no `ValidationError` to catch** — AC-7 typed the parameter as already-constructed `ImageManifest` (Pydantic-guaranteed valid), then said "returns `Err(MismatchError(...))` only when the inputs cannot be type-checked". A frozen validated model can't fail validation again. The smart constructor was dead code with a fictitious rationale.

All three fixed via surgical AC rewrites; no goal or scope change. Twelve additional harden-level findings tightened test-quality (mutation-resistance), coverage (edge cases, closed-set positive fence, re-export test), and Notes-for-implementer accuracy.

## Context Brief

**Goal (from story):** Ship `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` — pure function `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` + smart constructor `try_cross_check(sbom, image_manifest_raw, ...) -> Result[Verification, MismatchError]`. Read only load-bearing fields (`locations[].layerID`, `name`, `version`); never touch `SyftSbom` `extra` content.

**Phase-arch constraint:**
- Scenario D (`phase-arch-design.md` lines 488–515): verifier returns typed mismatch; adapter maps to `Unknown(reason="sbom_layer_attribution_absent")`; orchestrator emits `sbom.routing_anomaly`.
- Gap 3 (lines 1423–1428): Phase 12 owns the deeper signature check; Phase 7's defensive guard is read-only-known-fields (this story) + AST fence (S4-04).
- Data model (lines 1080–1180): `Verification` is a tagged sum; `MismatchError` is a typed record; identifiers are newtypes (`LayerDigest`, `ImageDigest`).

**Phase ADRs honored:**
- ADR-0004 — primitive home (`primitives/vuln_provenance/`).
- ADR-0008 — no cache (pure function only).

**CLAUDE.md commitments:**
- Functional core / imperative shell (verifier is pure; smart constructor is the only I/O-adjacent surface, catching Pydantic `ValidationError` at the raw-bytes boundary).
- Extension by addition — no silent edits (ADR-0043): `MismatchReason` closed literal; adding a sixth requires ADR amendment + fence break.
- Newtype identifiers: `LayerDigest`, `ImageDigest` throughout.
- Rule 2 (Simplicity First): no `ImageManifestSource` port (rule-of-three not met); no per-reason `MismatchDetails` sub-models (four reasons fit a flat record).
- Rule 9 (tests verify intent): metamorphic property added to catch determinism-passing-but-broken impls.

**Precedent (codebase shape to mirror):**
- `src/codegenie/primitives/vuln_provenance/types.py` — 7-variant `Provenance` discriminated union with `assert_never` exhaustiveness.
- `src/codegenie/result.py` — canonical `Result[T, E]`.
- `src/codegenie/types/parsers.py` — smart-constructor pattern (`parse_layer_digest(s) -> Result[LayerDigest, ParseError]`).
- Sibling story `S4-04` — AST fence for the shared SBOM read-set (three modules including `sbom_verifier.py`).
- Sibling story `S2-01` — closed-tuple discipline for `_ADAPTER_DISPATCH_ORDER`; `.value` assertions on `Layer` / `Ecosystem` StrEnum members.

## Critics — findings

### Critic A — Coverage

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-COV-1 | Impl-outline §3 conflated "artifact absent from SBOM" and "artifact present with `locations=[]`" into `sbom_artifact_has_no_locations`. Operators triaging `sbom.routing_anomaly` dashboards cannot distinguish "SBOM never heard of `left-pad@1.0.0`" (likely upstream indexer failure) from "SBOM has the package with zero location metadata" (likely Syft bug). | HARDEN | Added distinct `"artifact_not_in_sbom"` to `MismatchReason` (AC-3 → 5 members). Split AC-10 into AC-10a (locations empty) / AC-10b (all layerID None) / AC-10c (artifact not in SBOM, new). |
| F-COV-2 | AC-14 fence rejection list missed Pydantic v2 escape hatches: `.model_dump()`, `.model_dump_json()`, `.dict()` (v1 shim), `.model_fields_set`, `for f in artifact.model_fields`, `pickle.dumps`, `__pydantic_fields_set__`. Any gives read-access to `extra="allow"` payload. | HARDEN | S4-04 is the fence owner; added the escape-hatch list to S4-01's `Notes for the implementer §"Fence discipline"` so the executor doesn't ship a violation. Note recommends S4-04 extend its list when it ships (flagged inline). |
| F-COV-3 | AC-11 discarded the raw offending `layerID` string when `parse_layer_digest` failed. `claimed_layer: LayerDigest \| None` type means the raw malformed string is lost. Operators triaging `layer_id_malformed` events have no evidence of what was actually claimed — cannot distinguish `""`, `"sha256:GARBAGE"`, `"md5:..."`, or truncated. | HARDEN | Added `claimed_layer_raw: str \| None` to `VerificationMismatch` (AC-2). Populated only for `reason="layer_id_malformed"`. AC-11 tightened to assert the raw string round-trips. |
| F-COV-4 | `ImageManifest.image_digest: ImageDigest` was declared (AC-4) but unused in impl-outline §3 — dead weight OR premature abstraction. | HARDEN | Elevated to load-bearing: `VerificationMismatch.image_digest` populated on every mismatch (AC-2). Enables cross-workflow correlation of poisoned SBOMs against the same image on the `sbom.routing_anomaly` dashboard. |
| F-COV-5 | Missing edge cases: duplicate `(name, version)` in `sbom.artifacts` (Syft legitimately emits this for cross-stage artifacts) — impl-outline §3's "find the artifact" was silent-first-match. Empty `image_manifest.layers=()` — no AC. Precedence when malformed AND not-in-manifest both apply — undocumented. | HARDEN | Added AC-11b (priority: malformed wins over not-in-manifest), AC-11c (empty manifest layers), AC-12b (duplicate artifacts use union of locations). Impl-outline §3 first bullet rewritten to "find **all** artifacts... take the **union** of locations". |
| F-COV-6 | No AC pinned `__init__.py` re-exports; "Files to touch" edits the file but nothing asserted the exports. Executor could ship without re-exports, forcing consumers to import from the submodule directly and defeat the primitive boundary. Compare S2-01. | HARDEN | Added AC-15b: `test_public_names_are_reachable_from_package` — asserts `__all__` superset + attribute reachability. |
| F-COV-7 | Priority conflict between `layer_id_malformed` and `layer_id_not_in_manifest` when both apply — no AC pins the outcome; a refactor could flip it silently. | NIT (folded into HARDEN) | AC-11b (priority) has a named test `test_priority_malformed_over_not_in_manifest`. |

### Critic B — Test Quality

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-TQ-1 | AC-8's happy-path test asserts `kind == "ok"` on a single fixture. A mutant returning `VerificationOk` unconditionally passes. Assertion is a constant, not a function of input variance. | HARDEN | Parameterized AC-8 with paired positive/negative fixtures (same SBOM, two manifests — one with matching layer, one without). Kills `Ok`-always mutants. |
| F-TQ-2 | AC-11 named `reason="layer_id_malformed"` only; a mutant that sets `claimed_layer=<some LayerDigest>` (violating spec) or leaks the raw string into `known_layers` slips through. | HARDEN | AC-11 rewritten to assert full record shape — `claimed_layer is None`, `claimed_layer_raw == "<offending>"`, `known_layers == image_manifest.layers` (exact tuple). |
| F-TQ-3 | AC-16 determinism (`f(x) == f(x)`) alone passes for any pure-but-wrong impl. `return VerificationOk` always wins the determinism property. | BLOCK-RESOLVED | Added AC-16b metamorphic property: adding a matching `LayerDigest` to `image_manifest.layers` must never flip `Ok → Mismatch`. Catches `all` vs `any` swaps and off-by-one set-membership bugs. |
| F-TQ-4 | `test_multi_location_ok_if_any_matches` tests only the positive direction. A mutant returning `layer_id_malformed` for the multi-loc all-mismatch case slips. | HARDEN | Added inverse test `test_multi_location_mismatch_when_none_match` under AC-12. |
| F-TQ-5 | AC-13 runtime `assert_never` only catches missing branches when the missing branch's input reaches the test. Static enforcement is what closed sum types actually buy. | HARDEN | Added AC-13b: `test_missing_arm_surfaces_mypy_error` runs `mypy --strict` against an inline fixture omitting the `mismatch` arm; asserts mypy emits an `assert_never` error. Precedent: sibling `test_provenance_mypy_negative.py`. |
| F-TQ-6 | AC-14 AST fence had no planted-positive self-test → silent-green risk if the AST walker's node-matcher regexes are wrong. | RESOLVED VIA F-CON-1 | S4-04 owns the fence and ships its own planted-positive self-test (S4-04 AC-11). S4-01's AC-14 downgraded to a conformance requirement; no self-test needed here. |
| F-TQ-7 | AC-10 conflated two reasons (`sbom_artifact_has_no_locations` for `locations=[]`, `sbom_layer_attribution_absent` for all-None). Only one test in the TDD plan; a mutant returning `sbom_layer_attribution_absent` for empty-list slips. | HARDEN | Split into AC-10a / AC-10b / AC-10c with three distinct named tests. |
| — | No test for `try_cross_check`'s `Err(MismatchError)` path (only prose in AC-7). | HARDEN | Added AC-17b: `test_err_on_malformed_manifest_raw` — passes malformed `image_manifest_raw` dict; asserts `Err(MismatchError)` with populated `details["validation_error"]`. |

### Critic C — Consistency

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-CON-1 | AC-14 introduced `tests/fence/test_sbom_verifier_reads_known_fields_only.py`; S4-04 AC-10 explicitly says its `test_alpine_adapter_reads_known_fields_only.py` walks THREE modules including `sbom_verifier.py`. Two owners, one policy — the story that ships later silently overwrites. | BLOCK-RESOLVED | Deleted standalone fence from Files-to-touch + Implementation outline. AC-14 downgraded to a conformance requirement: shipped module must pass S4-04's fence. Added "Do NOT touch" note for `test_alpine_adapter_reads_known_fields_only.py`. |
| F-CON-2 | AC-6's frozen import set `{__future__, typing, pydantic, codegenie.result, ..syft_reader, ..errors, codegenie.types.identifiers}` omits `codegenie.types.parsers`, but AC-11 requires wrapping `LayerDigest`'s smart constructor. `identifiers.py`'s `LayerDigest` is a bare `NewType` (identity, no validation); the smart constructor is `parse_layer_digest` in `types/parsers.py`. | BLOCK-RESOLVED | Added `codegenie.types.parsers` to AC-6 import-set allowlist. Also added `collections.abc` (for `Mapping` in new `try_cross_check` signature). |
| F-CON-3 | `try_cross_check` typed `image_manifest: ImageManifest` (already-validated frozen Pydantic model) but impl-outline §4 said "catches `ValidationError` on `ImageManifest` and returns `Err(MismatchError(...))`". A pre-validated model cannot raise `ValidationError` at call time. Smart constructor was dead code with a fictitious rationale. | BLOCK-RESOLVED | Changed signature to `image_manifest_raw: Mapping[str, Any]`. Smart constructor builds `ImageManifest(**image_manifest_raw)` inside try/except; `ValidationError` is now a real thing. Preserves the goal's smart-constructor discipline. |
| F-CON-4 | AC-14 + Notes claimed `SyftSbom.descriptor: dict[str, Any]` "is poison" — the arch data model conceptually mentions it (line 1164) but S1-05 explicitly deferred it via `# TODO(future)` (shipped `syft_reader.py` line 27). Story assumed a shape S1-05 didn't ship. | HARDEN | Notes rewritten: `descriptor` is a *future* concern; S4-04's fence still rejects `sbom.descriptor[...]` defensively so no adapter can silently start reading it when a later story lands the field. Dropped stale "confirm with S1-05 implementer" clause (S1-05 is GREEN). |
| F-CON-5 | Arch Scenario D collapses all `MismatchReason` values to the single `UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT` on the adapter surface. Story didn't document the lossy 4→1 (now 5→1) mapping; adapters (S4-02/S4-03) would drop reason granularity silently. | HARDEN | Added Notes-for-implementer paragraph "Adapter-side lossy mapping (S4-02/S4-03 will need this)" documenting the collapse and prescribing that adapters MUST forward the specific `MismatchReason` on a structured `sbom.routing_anomaly` event field. Preserves operator diagnosability without breaking the seven-variant `Unknown` contract. |
| F-CON-6 | AC-5 added `MismatchError(ProvenanceError)`. Shipped `errors.py` already has `AdapterError(ProvenanceError)` for "adapter-specific failures (e.g., SBOM layer attribution absent for a specific row)". Semantic overlap risks conflation. | NIT | AC-5 extended with distinction sentence: `MismatchError` = verifier input boundary; `AdapterError` = adapter runtime failure. Note added to Notes-for-implementer. |
| F-CON-7 | AC-1 pinned `__all__` to include `MismatchError` but per AC-5 the class lives in `errors.py`. Re-exporting is legal but undocumented — executor may miss. | NIT | AC-1 clarified: `MismatchError` re-exported for one-import ergonomics; canonical home is `errors.py`. |
| F-CON-8 | The `_WARNING_IDS: Final[frozenset[str]]` + `raise AssertionError` discipline is probe-only (Phase 1 ADR-0007). Verifier is silent. Reviewer might over-apply. | NIT | Notes-for-implementer paragraph "Do NOT add `_WARNING_IDS`" added. |

### Critic D — Design Patterns

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-DP-1 | `try_cross_check` conflated type-validation with business-rule (per AC-7 rationale) — for an already-typed input, `ValidationError` cannot fire. Two options: (a) drop the smart constructor, or (b) shift to raw-dict input. | BLOCK-RESOLVED | Chose option (b) per F-CON-3 resolution — preserves the goal statement's smart-constructor discipline while making `MismatchError` meaningful. Option (a) would rewrite the goal (validator anti-goal). |
| F-DP-2 | `MismatchReason` closed-set had no positive fence — only consumer-side `match` + `assert_never` (AC-13). A sixth reason snuck in silently would still compile until a `match` is edited elsewhere. | HARDEN | Added AC-20b: `typing.get_args(MismatchReason) == (...)` exact-tuple assertion. Mirrors Phase 7's `_ADAPTER_DISPATCH_ORDER` closed-tuple discipline. Adding a sixth surfaces as a fence break, not a silent additive. |
| F-DP-3 | Refactor step in TDD plan prescribed the exact private-helper name `_classify_location(loc: SyftLocation, known_layers: frozenset[LayerDigest]) -> _LocationStatus`. Compiler-writer overreach. | NIT | Reworded: "extract a per-location classification helper (implementer's choice of name and signature)". |
| — (endorsed as-is) | `MismatchReason` as `Literal[...]` — consistent with sibling `UnknownReason` in `types.py`. `StrEnum` is used for *dispatch keys* (`Layer`, `Ecosystem`), Literal for *reason taxonomies*. Correct precedent chosen. | ENDORSE | No edit. |
| — (endorsed as-is) | No `ImageManifestSource` port — N=2 consumers (S4-02, S4-03), both build via `image_digest_resolver`. YAGNI; rule-of-three not met. | ENDORSE | Note added to Out-of-scope + Notes-for-implementer. |
| — (endorsed as-is) | Flat `VerificationMismatch` record (no per-reason `MismatchDetails` sub-models) — 5 reasons all fit `(claimed_layer, claimed_layer_raw, known_layers, image_digest)`. Sub-models would be premature abstraction. | ENDORSE | No edit. |
| — (endorsed as-is) | Per-call API (no `cross_check_many` batch) — 5–10 μs per call at 10⁴/gather = ~100ms envelope. No perf justification for the extra API surface. | ENDORSE | No edit. |

## Stage 3 — Researcher

Not invoked. No `NEEDS RESEARCH` findings; every pattern (metamorphic property, closed-set fence, smart-constructor at raw-bytes boundary, `mypy --strict` negative fixture) has a direct precedent in this repo.

## Stage 4 — Synthesizer / Editor

Priority conflicts resolved:

- **F-DP-1 (drop the smart constructor) vs F-CON-3 (fix the signature)** — F-CON-3 wins because F-DP-1's fix rewrites the story's goal, which the validator's anti-goals forbid. Fix reframes the smart constructor to accept raw bytes so `ValidationError` is a real boundary; the story's `try_cross_check` name and `Result` return survive.
- **F-COV-2 (expand fence rejection list) vs F-CON-1 (S4-04 owns the fence)** — F-CON-1 wins for ownership. The additional escape-hatch patterns land in S4-01's Notes-for-implementer so the executor avoids them; S4-04's fence extension is flagged inline for a future S4-04 hardening pass.
- **F-COV-4 (elevate `image_digest` to output) vs drop it (YAGNI)** — elevate wins because the field is already spec'd in AC-4 and the ecosystem cost of correlating poisoned SBOMs on the operator dashboard is real (`sbom.routing_anomaly` dashboard needs the join key).

Edits applied to `docs/phases/07-migration-task-class/stories/S4-01-sbom-verifier-cross-check.md`:

1. **Status line** → `HARDENED (phase-story-validator, 2026-07-24 — pre-executor pass; see _validation/S4-01-sbom-verifier-cross-check.md)`.
2. **`Validation notes` block** inserted after `ADRs honored:` line — summarizes 3 block-severity resolutions, 12 harden-severity edits, 4 nit-severity edits.
3. **Context §3** updated to describe `try_cross_check` accepting raw manifest bytes.
4. **References — where to look** — added sibling S4-04 pointer as the fence owner; corrected S1-05 note about the deferred `descriptor` field; added `codegenie/types/parsers.py` as the actual smart-constructor home.
5. **Goal** — updated to reflect `try_cross_check(sbom, image_manifest_raw, ...)` signature.
6. **AC-1** — `__all__` re-sorted (`MismatchError` re-export rationale added).
7. **AC-2** — added `claimed_layer_raw: str \| None` and `image_digest: ImageDigest` fields with populated-when semantics.
8. **AC-3** — 5-member `MismatchReason` (added `"artifact_not_in_sbom"`, sorted); per-member semantic tag.
9. **AC-4** — added note that `layers=()` is valid; forward-ref to AC-11c.
10. **AC-5** — added `MismatchError` vs. `AdapterError` distinction sentence.
11. **AC-6** — added `codegenie.types.parsers`, `collections.abc` to import allowlist. Renamed the test file `test_sbom_verifier_module_purity.py` to disambiguate from S4-04's fence.
12. **AC-7** — signature changed to `image_manifest_raw: Mapping[str, Any]`; describes real `ValidationError` boundary.
13. **AC-8** — parameterized happy/inverse test — kills `Ok`-always mutants.
14. **AC-9** — asserts full record shape (not just `reason`).
15. **AC-10** — split into AC-10a (locations empty), AC-10b (all layerID None), AC-10c (artifact not in SBOM — new distinct reason).
16. **AC-11** — asserts `claimed_layer_raw` exact-matches; MUST NOT raise.
17. **AC-11b** — priority: malformed wins over not-in-manifest.
18. **AC-11c** — empty `image_manifest.layers=()` case.
19. **AC-12** — split into positive + inverse; added AC-12b (duplicate artifacts use union).
20. **AC-13b** — static exhaustiveness via `mypy --strict` negative fixture.
21. **AC-14** — downgraded from "ship a fence file" to "shipped module must pass S4-04's fence"; added conformance requirement + escape-hatch list.
22. **AC-15b** — `__init__.py` re-export test.
23. **AC-16b** — metamorphic property (adding matching layer never flips `Ok → Mismatch`).
24. **AC-17b** — `try_cross_check` boundary test.
25. **AC-20b** — positive closed-set fence for `MismatchReason` via `typing.get_args`.
26. **Implementation outline §3** — union-of-locations discipline; five-reason decision tree with priority.
27. **Implementation outline §4** — `try_cross_check` accepts raw `Mapping`; catches `ValidationError`.
28. **TDD plan** — 20 named tests reflecting the ACs above.
29. **Files to touch** — dropped `tests/fence/test_sbom_verifier_reads_known_fields_only.py`; added the seven new test files; added "Do NOT touch" line for S4-04's fence.
30. **Out of scope** — added S4-04 AST fence ownership + no `ImageManifestSource` port.
31. **Notes for the implementer** — rewritten: fence discipline (S4-04-owned + escape-hatch list); `descriptor` future-concern reframing; adapter-side lossy mapping documentation; `MismatchError` vs. `AdapterError`; no `_WARNING_IDS`; no `ImageManifestSource` port.

No edits to: overall Goal *intent* (unchanged), story dependency (S1-05).

## Verdict

**HARDENED.** Story was strong on sum-type / purity / ADR-alignment discipline but had three block-severity structural issues (fence collision, import-allowlist gap, dead smart constructor) that would have derailed the executor. All resolved surgically without rewriting scope. Coverage tightened by adding a fifth `MismatchReason` (`artifact_not_in_sbom`), capturing malformed raw strings, using `image_digest` for correlation, and pinning duplicate-artifact + empty-manifest + priority edge cases. Test-quality hardened by paired positive/negative fixtures, a metamorphic property, mypy-negative static exhaustiveness, and a boundary test for the smart constructor. Design-patterns endorsed the tagged sum, closed `MismatchReason` literal, flat mismatch record, and no-port choice — added a positive closed-set fence to backstop the closed set at import time.

Story is ready for `phase-story-executor` to pick up. The executor's Validator pass will now have concrete, mutation-resistant, unambiguous acceptance criteria to verify against.

## Files written

- This report: `docs/phases/07-migration-task-class/stories/_validation/S4-01-sbom-verifier-cross-check.md`
- Edited story: `docs/phases/07-migration-task-class/stories/S4-01-sbom-verifier-cross-check.md`
