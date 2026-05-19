# Validation report — S1-05 SyftSbom Pydantic reader

**Date:** 2026-05-19
**Validator:** phase-story-validator skill (single-pass synthesis)
**Verdict:** **HARDENED** — real, fixable weaknesses; story edited in place.
**Story file:** [`../S1-05-syft-sbom-reader-models.md`](../S1-05-syft-sbom-reader-models.md)

## Inputs read

- The story file (260 lines pre-edit).
- `../../phase-arch-design.md` §Development view / §Data model / §Component design §1–2 / §Edge cases row 1 / §Gap analysis Gap-3 / §Anti-patterns avoided.
- `../../ADRs/0004-vuln-provenance-primitive-home.md` (Decision, Consequences — incl. `model_construct()` fence + enumerated `__init__.py` re-export list).
- `../../final-design.md §Synthesis ledger` (cross-checked the "extra='allow' + S4-04 fence" carry-forward).
- Existing implementation surface (already landed but uncommitted): `src/codegenie/primitives/vuln_provenance/syft_reader.py`, `src/codegenie/primitives/vuln_provenance/__init__.py`, the untracked test files `tests/unit/primitives/vuln_provenance/test_syft_reader.py` + `test_syft_reader_module_purity.py`, and `tests/fixtures/syft/minimal_alpine.json`. The implementation was read for *consistency-cross-check only*; the validator's job is to harden the spec, not the impl.
- Sibling story `_validation/S1-04-vuln-provenance-adapter-protocol.md` was *not* opened — that's a sibling validation report, not an arch source. Other `_validation/` reports for S1-01/02/03 were not load-bearing for this story.

## Context Brief

S1-05 lands the three Pydantic models for the upstream syft SBOM schema (`SyftSbom`, `SyftArtifact`, `SyftLocation`) at `src/codegenie/primitives/vuln_provenance/syft_reader.py`. Types-only — no I/O, no logging. The load-bearing posture is `extra="allow"` (the single primitive-tree exception to the project-wide `extra="forbid"` default), with defense pushed to the consumer boundary: adapters read only the fields listed in module-private `_KNOWN_*_FIELDS` catalogs, enforced by S4-04's AST-walk fence. The `locations[].layerID` camelCase field name is the load-bearing contract — adapters (Alpine S4-02, Distroless S4-03) read it to attribute a CVE to an image layer.

Pre-edit, the story had a coherent skeleton (9 ACs, a TDD plan with two test files named) but several mutation-resistance weaknesses + one structural gap that the validator surfaced.

## Findings

### F1 — AC-4 round-trip claim was asserted in prose, not by test (Test-Quality, harden)

Pre-edit text:
> `SyftSbom.model_validate_json(...).model_dump_json()` losslessly preserves the known fields (the unknown ones round-trip through `extra="allow"`)

…but the TDD-plan test `test_minimal_alpine_fixture_round_trips` only validated → read back known fields. It never re-serialized to verify lossless behavior. An implementation that silently used `model_config = ConfigDict(extra="ignore")` or called `model_dump(exclude_unset=True)` internally would pass AC-2 (admits unknown fields) and the pre-edit AC-4 test (knowns survive parsing), but would silently drop unknowns on the encode side — the exact failure mode `extra="allow"` is supposed to prevent.

**Fix:** AC-4 strengthened to require a full *encode → decode → encode* cycle, and a new test `test_unknown_fields_survive_full_encode_decode_encode_cycle` added that asserts the unknown top-level fields (`schema`, `descriptor`, `source`) appear in the `model_dump(mode="json")` output. Mutation defense recorded explicitly in the AC body.

### F2 — No multi-location coverage (Coverage, harden)

Pre-edit, the TDD plan only exercised single-location artifacts (the fixture has one `locations[]` entry). Real syft outputs commonly carry several `locations[]` entries per artifact — and the Alpine / Distroless adapters' logic (in S4-02 / S4-03) is "iterate `locations[]`, take the first non-empty `layerID`." That adapter-side invariant is out of scope here, but this story's *model contract must at minimum admit + iterate `len(locations) > 1` without surprise* — otherwise the adapter side has nowhere to stand.

**Fix:** AC-3 extended with a multi-location matrix row + new test `test_artifact_admits_multiple_locations_preserving_order` that pins iteration order matches input order and a mixed-`layerID` case (some present, some absent).

### F3 — Empty-SBOM happy path was implicit (Coverage, harden)

Pre-edit, `SyftSbom.model_validate({"artifacts": []})` was tested only as a side effect inside `test_syft_sbom_admits_unknown_fields` (AC-2). The "empty SBOM is a legitimate state" invariant wasn't an explicit AC. An impl that made `artifacts` mandatory (`artifacts: list[SyftArtifact]` without `= []`) — which is exactly what `phase-arch-design.md §Data model` shows verbatim — would pass AC-2 (the test happens to pass `"artifacts": []` explicitly) but would silently break real syft outputs that omit the top-level `artifacts` key.

**Fix:** new AC-2.5 promotes the empty-SBOM and empty-locations defaults to explicit positive constraints + dedicated tests (`test_empty_sbom_validates`, `test_artifact_default_empty_locations`).

### F4 — `model_construct()` smart-constructor-bypass fence missing (Consistency, harden)

ADR-0004 §Consequences enumerates a primitive-tree-wide fence: "A fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/`". Pre-edit, the story didn't pin this fence at all. Of all the modules in the primitive tree, `syft_reader.py` is the most likely site to attract a `model_construct(...)` shortcut: it's the only deserialization surface, and a tempted impl could "skip Pydantic validation for performance" by calling `SyftSbom.model_construct(**dict_payload)` — which would bypass the very `extra="allow"`-with-typed-knowns posture this story is supposed to anchor.

**Fix:** new AC-8.5 plus concrete test body `test_syft_reader_has_no_model_construct_call_sites` in the module-purity test file. AST-walks the source and asserts no `Call` node has `attr == "model_construct"`. The structural defense is now per-file rather than relying solely on a primitive-tree-level fence that may or may not exist yet.

### F5 — Module-purity test body was named but not specified (Test-Quality, harden)

Pre-edit, AC-8 said "AST-walk test on `syft_reader.py` asserts imports are a subset of `{__future__, typing, pydantic}`" and the Files-to-touch table listed `test_syft_reader_module_purity.py` — but the TDD plan never provided the test body. The executor would have to invent one, with risk of either over-restriction (banning legitimate future imports) or under-restriction (passing imports of `os` or `logging`).

**Fix:** TDD plan now contains a concrete `test_syft_reader_imports_are_minimal` body parameterized off a module-level `_ALLOWED_TOP_LEVEL_IMPORTS: Final[frozenset[str]]` so the allowlist is one explicit edit away from being grown when the I/O reader lands in a future story.

### F6 — ADR-0004 §Consequences enumerates only `SyftSbom` in `__init__.py` (Consistency, nit)

ADR-0004 §Consequences lists `SyftSbom` as the only `syft_reader`-sourced re-export in `vuln_provenance/__init__.py`. AC-7 (and the existing impl) re-exports all three: `SyftSbom`, `SyftArtifact`, `SyftLocation`. The pragmatic reason is that downstream adapters (Npm S3-02, Alpine S4-02, Distroless S4-03) and `sbom_verifier.py` (S4-01) will all need to type-annotate parameters as `SyftArtifact` / `SyftLocation`, and ADR-0004 §Consequences says "consumers depend on the primitive's public `__init__.py` surface, not on internal modules." So the three-re-export choice is correct; ADR-0004's enumeration is implicitly incomplete.

**Fix:** `ADRs honored` line on the story updated to call this out as an implicit ADR-0004 amendment. No edit to ADR-0004 itself (that would exceed the story's scope and require a separate `phase-architect` re-run). Recorded here so any future architect-pass can pick it up.

### F7 — `frozen=True` not considered (Design-Patterns, note-only)

`frozen=True` on the three models would make any post-deserialization mutation a `ValidationError`. The codebase's `_Frozen` base (from S1-02) bundles `frozen=True, extra="forbid"`; this story can't subclass `_Frozen` because of the `extra` inversion, but `frozen=True` independently is available. Pre-edit, the story neither adopted nor explicitly rejected it.

**Resolution:** Rule 2 (Simplicity First) — no caller in Phase 7 mutates an `SyftSbom`. Recorded in *Evaluated-and-rejected design-pattern alternatives* with a clear re-open trigger (the first `.model_copy(update=...)` call site). This is so the executor doesn't silently add `frozen=True` and so a future story can pick this up cleanly.

### F8 — `LayerID` newtype not considered (Design-Patterns, note-only)

`layerID: str` is structurally indistinguishable from arbitrary strings; a `NewType("LayerID", str)` would prevent the "passed `path` where `layerID` is expected" bug class. CLAUDE.md §Conventions explicitly endorses newtypes for domain IDs (`ProbeId`, `IndexName`, `PackageManager`).

**Resolution:** Rule-of-three not yet hit — only two consumers read this field (Alpine S4-02 + Distroless S4-03). Recorded in *Evaluated-and-rejected* alternatives with the rule-of-three re-open trigger.

### F9 — Hypothesis property-based fuzz opportunity (Test-Quality, note-only)

A `@given(st.dictionaries(...))` test could fuzz the `extra="allow"` surface and assert random unknown-field shapes round-trip. Powerful, but overkill given the single realistic fixture + the multi-location case + the explicit unknown-fields round-trip test now collectively exert enough mutation pressure for a types-only story. The S4-04 AST fence is the consumer-side structural defense; Hypothesis here would mostly duplicate that.

**Resolution:** Recorded in *Evaluated-and-rejected* alternatives with a re-open trigger (a real-world syft schema-drift incident slipping through). No AC added.

## Conflict resolution

- **Coverage vs Consistency + Rule 2.** Coverage wanted Hypothesis fuzz on every unknown-field topology; Consistency + Rule 2 said "single fixture + multi-location case + explicit unknown-fields round-trip is enough mutation pressure for a types-only story." **Consistency wins** (it's source-of-truth aligned with Rule 2's YAGNI position). Surfaced as a Notes hint, not promoted to AC.
- **Design-Patterns vs Consistency + Rule 2.** Design-Patterns wanted `frozen=True` adopted. Consistency + Rule 2 said "no Phase 7 caller mutates an `SyftSbom`; adopting `frozen=True` now is premature abstraction." **Consistency wins.** Recorded as an evaluated-and-rejected alternative so the executor doesn't silently adopt it.

The priority `Consistency > Coverage > Test-Quality > Design-Patterns` from the validator skill held — pattern advice gave way to source-of-truth alignment in both conflicts.

## Edits applied

All edits are in-place on `../S1-05-syft-sbom-reader-models.md`:

1. **Status** flipped `Ready` → `HARDENED`.
2. **ADRs honored** line extended with the ADR-0004 §Consequences re-export-implicit-amendment note and the `model_construct()` smart-constructor-bypass fence anchor.
3. **Validation notes** block inserted under the header summarizing changes + conflict resolution + report pointer.
4. **AC-2.5 (new)** — explicit empty-SBOM / empty-locations positive constraint.
5. **AC-3 extended** — multi-location matrix row.
6. **AC-4 strengthened** — full encode → decode → encode cycle requirement; mutation defense rationale.
7. **AC-8.5 (new)** — no `model_construct()` call sites in `syft_reader.py`; AST fence; ADR-0004 §Consequences pointer.
8. **TDD plan extended** — concrete test bodies for `test_empty_sbom_validates`, `test_artifact_default_empty_locations`, `test_artifact_admits_multiple_locations_preserving_order`, `test_unknown_fields_survive_full_encode_decode_encode_cycle`. New "Module-purity + smart-constructor-bypass fence" sub-section with full test-file body (`test_syft_reader_imports_are_minimal` + `test_syft_reader_has_no_model_construct_call_sites`).
9. **Notes for the implementer** extended with a new *Evaluated-and-rejected design-pattern alternatives* sub-section covering `frozen=True`, `LayerID` newtype, Hypothesis property-based fuzz, and smart-constructor "narrow view" — each with a re-open trigger condition.

No code was changed by this validation pass. The story is the spec; the executor (or a re-validation against the existing untracked implementation) will close the loop.

## Goodness check — does the story now meet the bar?

- ✅ Every AC is individually verifiable — each has a concrete test or a structural assertion.
- ✅ The AC set collectively guarantees the goal — the load-bearing invariants (`extra="allow"`, camelCase `layerID`, module-private catalogs, types-only purity, no `model_construct` bypass, lossless unknown-field round-trip) are each pinned.
- ✅ Mutation-resistance — for each AC, named the failure mode a wrong impl would exhibit (extra="ignore" silently dropping unknowns; mandatory `artifacts`; `model_construct` shortcut; non-camelCase `layerID`; growing the imports beyond `{__future__, typing, pydantic}`).
- ✅ No tautologies, no "no exception thrown" checks (every test either asserts a concrete value or asserts a `ValidationError`).
- ✅ No contradictions with phase arch / ADRs — the ADR-0004 §Consequences re-export-list mismatch is surfaced explicitly as an implicit-amendment note rather than ignored.
- ✅ Edge cases covered for the problem domain — empty input, multi-location, unknown-field preservation, deserialization-bypass attempt, mandatory-vs-optional default behavior.
- ✅ Open/Closed at module boundary preserved — adding a known field is a two-line catalog edit + a one-line fence-test update; no kernel surgery.
- ✅ Domain modeling — typed Pydantic records rather than `dict[str, Any]`; `_KNOWN_*_FIELDS` as `Final[frozenset[str]]` catalogs (Registry pattern).
- ✅ Deferred-design alternatives explicitly recorded so future stories don't accidentally re-litigate.

Story is **ready for the executor** (or for a re-validation pass against the already-landed implementation).
