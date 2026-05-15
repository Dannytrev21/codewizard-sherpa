# Validation report — S1-03 Adapter `Protocol`s + `AdapterConfidence` discriminated union

**Story:** [`../S1-03-adapter-protocols-confidence.md`](../S1-03-adapter-protocols-confidence.md)
**Validated:** 2026-05-15
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The story implements `codegenie.adapters` — four `@runtime_checkable` Protocols (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`), `AdapterConfidence = Trusted | Degraded | Unavailable` (Pydantic discriminated union), plus `Occurrence` (frozen dataclass) and `TestId` (`NewType`). All references trace cleanly to `02-ADR-0007`, `phase-arch-design.md §"Component design" #7` / §"Data model" / §"Design patterns applied" row 3, and `final-design.md §7`.

The draft was structurally sound — no `RESCUE`-tier findings — but had **ten harden-tier gaps** in AC coverage and test mutation-resistance that would have let an obviously-wrong implementation slip past the executor's Validator pass. Many of the gaps are direct symmetric analogues of the gaps S1-01 closed (this is the 2nd Pydantic-discriminated-union family in Phase 2; symmetric discipline matters).

Twelve edits applied in place; story is ready for `phase-story-executor`. Stage 3 research skipped (no `NEEDS RESEARCH` findings — every gap was answerable from arch + ADR-0007 + S1-01's validation precedent).

## Context Brief (Stage 1)

- **Goal as written:** Implement `src/codegenie/adapters/{__init__.py, protocols.py, confidence.py}` — four `@runtime_checkable Protocol` classes + `AdapterConfidence = Trusted | Degraded | Unavailable` Pydantic discriminated union + per-Protocol `isinstance` conformance tests. **Zero implementations.**
- **Phase 2 exit criteria touched:** Plugin scaffolding ships as documentation-as-code (kernel-only); Phase 3 inherits typed surfaces day-1 (`phase-arch-design.md §"Integration with Phase 3"`); 02-ADR-0007 "Phase 3 first plugin doubles as proof the loader works" survives by *not* shipping implementations here.
- **Load-bearing commitments touched:**
  - CLAUDE.md §"Extension by addition" — adding a fifth Protocol is ADR-amendment; new adapter implementations are new files under `plugins/`.
  - CLAUDE.md §"Honest confidence" + "Facts not judgments" — `AdapterConfidence` is the typed surface for "the adapter doesn't know" (Degraded/Unavailable).
  - `02-ADR-0007 §Decision/§Consequences` — Phase 2 ships zero implementations; `tests/integration/adapters/test_phase3_handoff_smoke.py` lands skipped in S7-04.
  - `phase-arch-design.md §"Data model"` — pins exact Pydantic shape (frozen, extra=forbid, Literal kind, `Annotated[Union[...], Field(discriminator="kind")]`).
  - `phase-arch-design.md §"Design patterns applied"` row 3 — PEP 544 structural subtyping over Abstract Factory.
  - `phase-arch-design.md §"Anti-patterns avoided"` rows 1 (premature pluggability), 2 (pattern soup), 7 (tag-and-dispatch without tagged union), 11 (`model_construct` bypass).
  - `final-design.md §7` — "~80 LOC total, pure types, stdlib + `typing` only".
- **Open/Closed boundaries:**
  - New *adapter implementation* → new file under `plugins/{slug}/adapters/` (Phase 3 + later). Zero edits to `protocols.py`.
  - New *Protocol type* (5th kind of adapter) → deliberately ADR-amendment-gated, NOT Open/Closed.
  - New *AdapterConfidence variant* → deliberately ADR-amendment-gated; `assert_never` enforces.
- **Sibling-family lineage:** **2nd** Pydantic-discriminated-union family in Phase 2 (after S1-01 `IndexFreshness`). Symmetric discipline: discriminator-string pinning, JSON-shape pinning, `extra="forbid"` test, frozen mutation test, exhaustive `match` test, `model_construct` source-scan, module-purity invariant. S1-01's validation report (`_validation/S1-01-…md`) establishes the framing carried forward.
- **Prior validation history:** None for S1-03; cross-referenced S1-01's report for sibling-family pattern.
- **Open ambiguities:** None — proceeded to Stage 2.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN — 10 findings)

- **F1 (harden) — Discriminator strings unpinned.** AC-3 declares the discriminated-union shape but no AC pins the discriminator string values (`"trusted"`, `"degraded"`, `"unavailable"`). A symmetric swap (`Trusted.kind = "degraded"` + `Degraded.kind = "trusted"`) round-trips cleanly while breaking every Phase 3 plugin renderer, golden file, and `repo-context.yaml` consumer. **Smell:** identical to S1-01 F2. **Fix:** strengthen AC-3 + add `test_discriminator_strings_are_exactly_pinned`.
- **F2 (harden) — No exhaustive-match AC.** Arch §"Agentic best practices" lists `AdapterConfidence` alongside `IndexFreshness` as a sum type consumed via `match` + `assert_never` (mypy `--warn-unreachable` per-module). S1-01 codified this with AC-6/6a; symmetric discipline missing in S1-03. **Fix:** add AC-14 + `test_match_is_exhaustive_over_adapter_confidence`.
- **F3 (harden) — `Trusted`-rejects-`reason` is convention, not contract.** Story Notes say "Resist the urge to add `reason` for symmetry" but `extra="forbid"` enforcement is not test-asserted for `Trusted` specifically. A future contributor adding `reason: str | None = None` to `Trusted` for "convenience" wouldn't be caught. **Fix:** add AC-11 + `test_trusted_rejects_reason_field` (named explicitly).
- **F4 (harden) — No runtime-immutability test.** AC-3 mandates `frozen=True` but no AC asserts runtime mutation raises. Round-trip tests don't exercise assignment. **Fix:** add AC-10 + `test_adapter_confidence_instances_are_immutable`.
- **F5 (harden) — `Occurrence` frozen + field-set unasserted.** AC-2 declares `Occurrence` as a frozen dataclass but no AC asserts `__dataclass_params__.frozen`, the exact `{file, line, col}` field set, or `FrozenInstanceError` on mutation. **Fix:** add AC-13 + `test_occurrence_is_frozen_dataclass_with_exact_fields`.
- **F6 (harden) — No JSON-shape pin.** Same gap S1-01 F5 closed: a symmetric `kind` → `tag` discriminator-field rename passes AC-7 (Python-object round-trip) silently. **Fix:** add AC-12 + `test_json_shape_pinned`.
- **F7 (harden) — Module-purity claim is convention.** Story Notes say `confidence.py` is "pure typing — no logger, no I/O, no third-party deps beyond pydantic"; no test enforces. **Fix:** add AC-15 + `test_adapter_modules_are_pure_typing` (AST import scan). Also covers `protocols.py`.
- **F8 (harden) — AC-6 dynamic walk has a known hole.** The story acknowledges that classes requiring constructor args are silently skipped by the `pkgutil` walk. An inheritance-style implementation (`class FooAdapter(DepGraphAdapter): def __init__(self, x): ...`) would slip through. **Fix:** strengthen AC-6 to two arms (dynamic + static AST base-class scan); add `test_no_phase2_module_inherits_adapter_protocol_statically`.
- **F9 (nit) — `__all__` enumeration missing `Occurrence`/`TestId`.** AC-1 lists eight names but the Implementation outline's `__init__.py` exports ten. **Fix:** AC-1 now enumerates the exact ten-name set + `test_adapters_all_is_exactly_the_public_surface`.
- **F10 (nit) — AC-5 only covered DepGraphAdapter.** Original incomplete-stub test only exercised `_IncompleteDepGraph`. The other three Protocols had no parallel rejection test. **Fix:** parametrize over all four Protocols; strengthen AC-5 wording.

### Test quality (verdict: TESTS-HARDEN)

Mutation analysis (12 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity | Closure |
|---|---|---|---|---|
| 1 | Drop `frozen=True` from `Trusted`/`Degraded`/`Unavailable` `model_config` | **No** | harden | AC-10 + `test_adapter_confidence_instances_are_immutable` |
| 2 | Drop `extra="forbid"` from `model_config` | **No** | harden | AC-11 + `test_*_rejects_extra_field` for all 3 variants |
| 3 | Drop `Field(discriminator="kind")` from `AdapterConfidence` Union | Partially (depends on Pydantic fallback) | harden | AC-7 strengthened with `type(decoded) is type(instance)` assertion |
| 4 | Symmetric swap of `Trusted.kind` and `Degraded.kind` literal values | **No** — round-trip equal | harden | AC-3 + `test_discriminator_strings_are_exactly_pinned` |
| 5 | Drop `@runtime_checkable` decorator from a Protocol | Yes — `isinstance` raises `TypeError`; AC-4 fails loud | — | — |
| 6 | Rename `kind` field to `tag` symmetrically | **No** | harden | AC-12 + `test_json_shape_pinned` |
| 7 | Add `reason: str = ""` field to `Trusted` for symmetry | **No** | harden | AC-11 + `test_trusted_rejects_reason_field` |
| 8 | Change `Occurrence` from `frozen=True` dataclass to regular dataclass | **No** | harden | AC-13 + `test_occurrence_is_frozen_dataclass_with_exact_fields` |
| 9 | Implement a Protocol with mutable shared state | N/A — protocols can't define state | — | — |
| 10 | Use `model_construct(...)` inside `confidence.py` for "performance" | **No** | harden | AC-16 + `test_adapter_modules_have_no_model_construct` |
| 11 | Drop one method from `ImportGraphAdapter` / `ScipAdapter` / `TestInventoryAdapter` | DepGraph-only — others uncovered | harden | AC-5 parametrized over all 4 Protocols |
| 12 | Use `Tuple` instead of `list` in a Protocol signature | mypy `--strict` catches; `isinstance` does not | accepted (mypy) | Test docstring cites PEP 544 |

Other test-quality concerns:
- The original `test_no_phase2_module_implements_adapter_protocol` swallowed exceptions on instantiation — documented limitation. Closed by the static-AST arm.
- No `__all__` consistency check — added `test_adapters_all_is_exactly_the_public_surface`.

### Consistency (verdict: CONSISTENCY-CLEAN)

- `@runtime_checkable Protocol` + signatures: exact match to `phase-arch-design.md §"Component design" #7` and §"Data model". ✓
- Module locations `src/codegenie/adapters/{__init__.py, protocols.py, confidence.py}` match 02-ADR-0007 §Decision. ✓
- `AdapterConfidence = Annotated[Union[Trusted, Degraded, Unavailable], Field(discriminator="kind")]`: matches §"Data model" lines 703-707 verbatim. ✓
- `TestId = NewType("TestId", str)` declared in `protocols.py`, not S1-05: consistent with "newtype belongs where its consumer family lives" architect's rule (S1-01's validation precedent #9). ✓
- `Occurrence` as frozen dataclass (not Pydantic): matches refactor #3 docstring rationale ("raw SCIP-decoded position; mmap-friendly"); Pydantic overhead unwarranted for a 3-field positional type. ✓
- 02-ADR-0007 §Decision: Phase 2 ships NO `NullAdapter` fixtures, NO adapter implementations. AC-6 (dynamic + static) enforces. ✓
- `forbidden-patterns` ban on `model_construct` under `src/codegenie/adapters/**`: from arch §"Anti-patterns avoided" row 12 + final-design §"Anti-patterns" + S1-11. Now AC-16. ✓
- CLAUDE.md "Extension by addition": Adding a fifth Protocol type is ADR-amendment, mirroring the variant-set-extension discipline S1-01 ratified. Notes-for-implementer now states explicitly. ✓
- Gap 1 (handoff smoke test in S7-04): out-of-scope here, correctly named. ✓
- `final-design.md §"Patterns considered and deliberately rejected" #7`: `AdapterConfidence` is NOT the type of every probe's freshness output — only adapter outputs. Story respects this (AC-6 enforces zero phase-2-internal consumers). ✓
- No `RESCUE`-tier conflicts. The "Consistency > Coverage > Test-Quality > Design-Patterns" priority did not need to fire.

### Design Patterns (verdict: DESIGN-CLEAN with 3 Notes-for-implementer extensions)

- **Sum type / make-illegal-states-unrepresentable.** Correctly applied. `AdapterConfidence = Trusted | Degraded | Unavailable` is the canonical shape; `Trusted` carries the *absence* of degradation (no `reason`); `Degraded`/`Unavailable` carry the reason inline. No `Optional[str]` stringly-typed alternative. ✓
- **Structural subtyping (PEP 544).** Correct choice over Abstract Factory (`phase-arch-design.md §"Design patterns applied"` row 3). Phase 3 plugin authors do not inherit from our class hierarchy; they implement matching method shapes. ✓
- **Newtype for `TestId`.** Primitive obsession resolved for the one identifier where it crosses ≥2 module boundaries (TestInventory adapter + Phase 3 plugin code). `pkg: str` / `module: str` / `symbol: str` are deliberately NOT newtyped — Phase 2 doesn't yet know if Phase 3 wants `PackageId` vs `PackageName` semantics; ADR-amendment scoping (story Out-of-scope §2). ✓
- **Composition over inheritance.** Four parallel Protocols, no shared base, no mixin. ✓
- **Functional core / imperative shell.** Pure typing — no I/O, no side effects. AC-15 now test-enforces. ✓
- **Smart constructor.** Not applicable here — `AdapterConfidence` variants are direct constructors; introducing a factory for three variants is over-engineering (Rule 2).
- **Open/Closed (variant-set extension).** Deliberately NOT applied — variant set is ADR-amendment-gated, `assert_never` enforces. Notes for implementer now explicit (was implicit via S1-11 reference).

**Three Notes-for-implementer extensions added (not promoted to ACs — pattern names are not testable, but framings prevent the next implementer from misreading the design):**

1. **Deliberate non-extraction of a shared `HasConfidence` Protocol.** All four Protocols declare an identical `confidence(self) -> AdapterConfidence` method. PEP 544 supports protocol inheritance, but extraction is the wrong call here: (a) four identical lines is not Rule-of-Three duplication; (b) Phase 3 may want to evolve signatures independently per adapter; (c) the architect explicitly prescribed four parallel Protocols (final-design §7). Document the deliberate non-abstraction so the next reader doesn't "fix" it.
2. **`Occurrence` and `slots=True`.** Recommended for Phase 3 SCIP adapter's mmap walk (millions of instances). Optional in Phase 2; if adopted, extend AC-13 with `not hasattr(inst, "__dict__")`. If deferred, leave a `TODO(phase-3)` marker.
3. **Variant-set extension is ADR-gated.** Explicitly NOT a `@register_adapter_confidence_variant` decorator-registry (the prevalence of `@register_*` elsewhere in this phase is for *probe/strategy* extension, which is Open/Closed by intent; sum-type variants are deliberately closed).

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:
- `phase-arch-design.md` §"Component design" #7 / §"Data model" / §"Design patterns applied" / §"Anti-patterns avoided"
- `02-ADR-0007` §Decision / §Consequences / §Pattern fit
- `final-design.md` §7 / §"Anti-patterns" / §"Patterns considered and deliberately rejected" #7
- S1-01's validation report (sibling-family pattern precedent)
- PEP 544 (already cited inline in the story's Notes for the implementer)

## Stage 4 — Synthesis: edits applied

Twelve edits applied to [`../S1-03-adapter-protocols-confidence.md`](../S1-03-adapter-protocols-confidence.md):

1. **Validation notes block added** under the header.
2. **AC-1** rewritten — enumerates the exact ten-name `__all__` surface (was eight); promoted to a `test_adapters_all_is_exactly_the_public_surface` assertion.
3. **AC-3** strengthened — discriminator-string-value pinning made an explicit cross-ADR contract; rationale block names 02-ADR-0007 §Consequences as the source of truth.
4. **AC-4** clarified — parametrized over all four Protocols (was implicit).
5. **AC-5** strengthened — parametrized over all four Protocols (was DepGraph-only); test docstring explicitly cites PEP 544.
6. **AC-6** strengthened — split into dynamic + static arms; static arm closes the trivial-instantiation hole.
7. **AC-7** strengthened — `type(decoded) is type(instance)` assertion made explicit (guards against `Field(discriminator="kind")` drop).
8. **New AC-10** — runtime immutability test (`frozen=True` enforcement via mutation attempt).
9. **New AC-11** — `extra="forbid"` enforcement on every variant; `Trusted`-rejects-`reason` named explicitly.
10. **New AC-12** — JSON-shape pin.
11. **New AC-13** — `Occurrence` frozen + exact-field-set + `FrozenInstanceError` test.
12. **New AC-14** — exhaustive `match` with `assert_never` (mirror of S1-01 AC-6a).
13. **New AC-15** — module-purity invariant (AST import scan).
14. **New AC-16** — `model_construct` source-scan ban.
15. **TDD plan rewritten** — sixteen test groups (was eight); parametrization over all four Protocols where applicable; static-AST arm of AC-6; module-purity and forbidden-patterns AST scans. Imports updated to include `Occurrence`/`TestId` (were imported from a sub-module path in the draft; now via `codegenie.adapters` top-level).
16. **Implementation outline** updated — step 1 adds discriminator-string pinning hint; step 2 names `slots=True` as recommended; step 3 enforces exact `__all__` match; step 4 explains the two-arm structure of AC-6.
17. **Notes for the implementer** extended — three design framings (HasConfidence non-extraction; `Occurrence` slots; variant-set ADR-gating); `forbidden-patterns` extension under `adapters/**` made explicit (S1-11 dependency).

## Mutation table — what the hardened story now catches

| Mutation | Was caught? | Now caught? | Test |
|---|---|---|---|
| Drop `frozen=True` | ✗ | ✓ | `test_adapter_confidence_instances_are_immutable` |
| Drop `extra="forbid"` | ✗ | ✓ | `test_*_rejects_extra_field` (3 variants) |
| Symmetric swap discriminator literals | ✗ | ✓ | `test_discriminator_strings_are_exactly_pinned` |
| Rename `kind` → `tag` symmetrically | ✗ | ✓ | `test_json_shape_pinned` |
| Add `reason` to `Trusted` | ✗ | ✓ | `test_trusted_rejects_reason_field` |
| `Occurrence` becomes mutable | ✗ | ✓ | `test_occurrence_is_frozen_dataclass_with_exact_fields` |
| `model_construct` used in `confidence.py` | ✗ | ✓ | `test_adapter_modules_have_no_model_construct` |
| `import structlog` in `confidence.py` | ✗ | ✓ | `test_adapter_modules_are_pure_typing` |
| Drop method from any of 3 non-DepGraph Protocols | ✗ | ✓ | `test_runtime_checkable_rejects_incomplete_stub` (parametrized) |
| Hidden inheritance-based adapter impl in `src/codegenie/` | ✗ | ✓ | `test_no_phase2_module_inherits_adapter_protocol_statically` |
| `__all__` typo / re-order / accidental addition | ✗ | ✓ | `test_adapters_all_is_exactly_the_public_surface` |
| Drop `Field(discriminator="kind")` from union | partial | ✓ | AC-7 `type(decoded) is type(instance)` + AC-12 JSON-shape |
| Drop `@runtime_checkable` decorator | ✓ (TypeError) | ✓ | AC-4 (unchanged — fails loud) |

## Verdict

**HARDENED.** The story now constrains the implementation with sixteen ACs (was nine) and a TDD plan whose tests would fail under twelve plausibly-wrong implementations (was three). The Design-Patterns critic's three Notes framings prevent the next reader from "fixing" deliberate non-abstractions that the architect prescribed.

Ready for [phase-story-executor](../../../../skills/phase-story-executor).
