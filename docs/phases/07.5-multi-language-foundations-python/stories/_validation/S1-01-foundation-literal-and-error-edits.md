# Validation report: S1-01 — Foundation loud edits (`PackageManager` +3, `LanguageRegistryError`)

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [../S1-01-foundation-literal-and-error-edits.md](../S1-01-foundation-literal-and-error-edits.md)

## Summary

The story as written carried two structural blockers: (1) its title/Goal/AC-1 claimed to land `SupportedLanguage += "python"`, which would break two shipped grammar-kernel tests because the `_DISPATCH` row and `tree-sitter-python` wheel pin (atomically required to keep those tests green) are explicitly deferred to S4-01 — and S4-01 already independently claims ownership of all three loud edits as one atomic landing. (2) Its `PackageManager += "pip"/"poetry"/"uv"` claim was advertised as additive-and-green-keeping, but the shipped Phase-1 snapshot test `test_package_manager_carries_the_five_adr_0013_values` pins the closed set to exactly five Node members; adding three Python members fails that pin until the snapshot is widened. The `test_no_strategy_per_package_manager_variant` parametrize over `get_args(PackageManager)` ALSO fails because its `_PM_LOCKFILES` fixture only has Node-5 entries.

The validator deferred the `SupportedLanguage += "python"` edit entirely to S4-01 (which already owns it), and made the `PackageManager` widening honest by explicitly including the two test widenings in scope as the documented ADR-0001 snapshot bump. AC-3 was hardened with mutation-resistant marker-only assertions (`__str__` identity + no new class attrs). AC-4 was added to pin the marker's docstring to BOTH `"register_language"` AND `"validate_pack"` substrings (mirroring `FreshnessRegistryError`/`DepGraphRegistryError` precedent). AC-8 was added to turn the "additive" doctrine into a binary `make test` pass/fail criterion. The Notes-for-implementer section now frames the story as the canonical ADR-0043 loud-edit shape in miniature — including the test-widening half.

## Context Brief

### Story snapshot (original)
- **Goal:** Add `"python"` to `SupportedLanguage`, `"pip"`/`"poetry"`/`"uv"` to `PackageManager`, and a `LanguageRegistryError` marker — each a compiler-policed loud edit.
- **Effort:** S, no dependencies, ADRs honored: 0001, 0003.

### ACs as written (original, numbered)
- AC-1: `SupportedLanguage` includes `"python"`; `supported_languages()` returns a tuple containing `"python"`.
- AC-2: `PackageManager` includes pip/poetry/uv (8 total); `_NEWTYPE_REGISTRY["PackageManager"]` docstring is updated.
- AC-3: `LanguageRegistryError(CodegenieError)` exists, is in `__all__`, marker-only, docstring names raise sites.
- AC-4: TDD red test exists, committed, green.
- AC-5: `ruff`, `mypy`, `pytest` all clean; full existing suite stays green.
- AC-6: Status set to Done.

### Constraints discovered during context loading
- ADR-0001: `LanguageRegistryError` is the loud import-time failure the `LanguagePack` kernel raises.
- ADR-0003: `language` reuses the existing `Language` newtype; adding a grammar = `SupportedLanguage Literal +1` + `_DISPATCH +1` row atomically.
- ADR-0043: extension-by-addition means loud, compiler-policed edits — closed-`Literal` membership changes are sanctioned; their *snapshot pins* widen in lockstep, not silently.
- Phase exit criterion G3: "Node/TypeScript regression suite unchanged and green" — hard CI gate.
- Phase exit criterion G1: only `src/codegenie/languages/` is a net-new top-level package.
- `S4-01-wire-tree-sitter-python-grammar.md` (sibling story) explicitly owns `SupportedLanguage += "python"`, `_DISPATCH +1`, and `tree-sitter-python` wheel pin as one atomic landing.

### Shipped tests that interact with the story's edits
- `tests/unit/grammars/test_lock.py::test_supported_languages_matches_literal_type` — asserts `set(get_args(SupportedLanguage)) == set(supported_languages())` (which iterates `_DISPATCH`). Adding `"python"` to Literal without `_DISPATCH` row → RED.
- `tests/unit/grammars/test_lock.py::test_language_for_returns_usable_language` — parametrizes over `get_args(SupportedLanguage)`; would try `language_for("python")` → `GrammarLoadRefused` (no wheel) → RED.
- `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` (lines 41-54) — pins the set to exactly 5 Node members → RED.
- `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant` (line 216) — parametrizes `get_args(PackageManager)` and looks up `_PM_LOCKFILES[pm]`; Python members `KeyError` → RED.
- `tests/property/test_dep_graph_strategy_dispatch.py` — uses `_PACKAGE_MANAGERS = get_args(PackageManager)` for hypothesis sampling, asserts `no_strategy_for_ecosystem` raises for unregistered ecosystems. Python members would ride through unaffected (assertion remains true).
- `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` — enforces `__all__` ⊆ `_NEWTYPE_REGISTRY` and ADR-0010 citation per docstring. Existing `PackageManager` row already cites ADR-0010, so an unchanged docstring would pass — necessitating the stronger AC-2 pin.

### Goal-to-AC trace (original)
- AC-1 → goal: YES — but unsatisfiable as scoped (see Consistency B1).
- AC-2 → goal: YES.
- AC-3 → goal: YES, but lacks `__str__` and no-new-attrs pins.
- AC-4 / AC-5 / AC-6: meta (TDD, lint, status).

## Findings by critic

### Coverage critic
- **C1 (harden)** — AC-3 names "docstring naming `register_language`/`validate_pack` as raise sites" but no AC-level test pin enforces the substring content. Proposed fix: split AC-3 into "marker shape" (AC-3) + "docstring names raise sites" (AC-4); both with explicit assertion templates in the TDD plan.
- **C2 (harden)** — AC-2 docstring update has no specific Phase-7.5 pin; the existing drift test (`test_newtype_registry_matches_all`) would pass even if the docstring were unchanged (it only requires `"ADR-0010"`, which the *old* docstring already contains). Proposed fix: AC-2 must require BOTH `"Phase 7.5"` AND `"ADR-0001"` substrings — the meaningfully-widened docstring.
- **C3 (harden)** — Story claims "additive" but has no AC that turns that into a testable pass/fail. Proposed fix: add AC explicitly demanding the FULL `make test` suite stays green except for the two enumerated widenings.

### Test-Quality critic
- **T1 (harden)** — marker test should also assert `__str__` identity (story prose says "no `__str__`" but the test only checks `__init__`) and that no class-level attributes were silently added — turn the marker discipline into a mutation-resistant assertion.
- **T2 (harden)** — Test names in original TDD plan are pseudocode comments, not executable templates. Provide concrete `assert` lines so the executor doesn't have to translate intent. Hardened TDD plan now carries near-executable templates.
- **T3 (nit)** — `__all__` ordering convention in `codegenie.errors` is by phase banner, not alphabetical. Make this explicit in the Refactor step so the executor doesn't insert alphabetically and surface a code-review nit.

### Consistency critic
- **B1 (block)** — AC-1 contradicts the Implementation outline. AC-1 asserts `supported_languages()` returns `"python"`. `supported_languages()` iterates `_DISPATCH` (line 89 of `src/codegenie/grammars/lock.py`). Implementation outline says "Do not add the `_DISPATCH` row here." So AC-1 is unsatisfiable as scoped.
- **B2 (block)** — Story claims to be "additive and should not break any existing test." Adding `"python"` to `SupportedLanguage` Literal without the `_DISPATCH` row makes `tests/unit/grammars/test_lock.py::test_supported_languages_matches_literal_type` go RED, and `test_language_for_returns_usable_language[python]` go RED (no wheel to load). Both tests are shipped Phase-2 tests; they are not "additive collateral" — they are real broken shipped tests.
- **B3 (block)** — Sibling story `S4-01-wire-tree-sitter-python-grammar.md` ALREADY claims `SupportedLanguage Literal +1` AND `_DISPATCH +1` AND wheel pin as one atomic landing (its AC line: "`SupportedLanguage` Literal is extended with `"python"` and `_DISPATCH` gains exactly one row …"). Duplicate ownership between S1-01 and S4-01.
- **B4 (block)** — `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` (lines 41–54) is a snapshot pin on the ADR-0013 closed set ("`set(get_args(...)) == {5 Node members}`"). Adding pip/poetry/uv fails this test. The widening IS the loud edit per ADR-0043 + Phase-7.5 ADR-0001 — but the original story did not enumerate it in Files-to-touch and the implicit "stays green" claim was false.
- **B5 (block)** — `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant` (line 216) parametrizes `get_args(PackageManager)` and looks up `_PM_LOCKFILES[pm]`, a dict with only Node-5 entries. Adding pip/poetry/uv to the Literal causes a `KeyError` at parametrize-resolution time. The test's INTENT is the Node no-strategy invariant — narrow the parametrize to a Node-5 whitelist; the Python no-strategy mirror is a future Phase-7.5 story.

### Design-Patterns critic
- **D1 (nit)** — Marker shape is correct (behavior-free `CodegenieError` subclass with raise-site-naming docstring) — matches `FreshnessRegistryError` / `DepGraphRegistryError` precedent. No structural changes needed.
- **D2 (nit)** — Closed-`Literal` extension is the canonical sum-type widening (ADR-0033 §primitive-obsession + closed-Literal). No premature `enum.StrEnum` migration needed (Rule 2 — three similar lines).
- **D3 (nit)** — Reusing `Language` newtype (not minting `LanguageId`) is correct per ADR-0003. No new `NewType` introduced.
- **D4 (harden)** — The story did NOT call out that this is the canonical ADR-0043 loud-edit shape in miniature. Naming the pattern in Notes-for-implementer helps future Phase-7.5 stories that touch closed `Literal`s in `types/identifiers.py` mirror the same shape (rename the snapshot test → update the docstring → update the set literal). Surfaced as a Notes paragraph.

## Research briefs

None — no `NEEDS RESEARCH` findings. The patterns and ADRs are all well-established in the codebase; the only resolutions needed were sourcing the right ADR rule and the right precedent test. Stage 3 was skipped.

## Conflict resolutions

- **Consistency B1/B2/B3 vs original AC-1**: Consistency wins (`Consistency > Coverage`). AC-1 deleted; `SupportedLanguage += "python"` deferred to S4-01.
- **Consistency B4 vs "additive" claim**: Consistency wins. The shipped snapshot test widening IS the loud edit; making it explicit is honest; calling the edit "additive" while silently breaking the snapshot would be the violation.
- **Coverage C1/C2 (additional ACs) vs Rule 2 (Simplicity First)**: ACs added are not scaffolding — they pin existing weaknesses in the original ACs that would allow trivially wrong implementations to pass. Kept.
- **Test-Quality T2 (concrete test templates) vs Rule 3 (Surgical Changes)**: kept — original templates were pseudocode comments; the executor benefits from near-executable templates, no scope creep.

## Edits applied

### Edit 1 — Title + Goal narrowed
- Source: Consistency B1/B2/B3
- Before: "Foundation loud edits (`SupportedLanguage` +1, `PackageManager` +3, `LanguageRegistryError`)"
- After: "Foundation loud edits (`PackageManager` +3, `LanguageRegistryError`)"
- Rationale: `SupportedLanguage += "python"` requires atomic `_DISPATCH` + wheel pin to keep grammar-kernel tests green; S4-01 already claims that atomic landing.

### Edit 2 — AC-1 deleted (was: `SupportedLanguage` includes `"python"`)
- Source: Consistency B1/B2/B3
- Rationale: unsatisfiable as scoped; would break two shipped tests; sibling S4-01 owns the atomic landing.

### Edit 3 — AC-2 strengthened
- Source: Coverage C2
- Before: "`_NEWTYPE_REGISTRY["PackageManager"]` docstring is updated to mention the Phase 7.5 `+3`"
- After: explicitly requires BOTH `"Phase 7.5"` AND `"ADR-0001"` substrings in the docstring — so the existing `test_newtype_registry_matches_all` drift test (which only requires `"ADR-0010"`) cannot trivially pass with an unchanged docstring.

### Edit 4 — AC-3 hardened (marker discipline)
- Source: Test-Quality T1
- Added: `__str__` identity assertion; explicit `set(vars(...)) - set(vars(CodegenieError)) ⊆ {dunder set}` assertion to catch silent class-level additions.

### Edit 5 — AC-4 added (docstring names raise sites)
- Source: Coverage C1
- Pins BOTH `"register_language"` AND `"validate_pack"` substrings — a single substring would pass a generic docstring; both force naming the actual raise-site functions.

### Edit 6 — AC-5 added (in-place snapshot widening)
- Source: Consistency B4
- The shipped `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` is widened in place (renamed `test_package_manager_carries_the_adr_0013_plus_phase_7_5_values`, set literal extended, docstring updated). This is the documented ADR-0001 snapshot bump — the widening is loud, traceable in `git blame`, and explicitly visible in the test name.

### Edit 7 — AC-6 added (parametrize narrowed)
- Source: Consistency B5
- `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant`'s parametrize narrowed from `list(get_args(PackageManager))` to the explicit Node-5 whitelist, with comment citing this story and pointing at the future Python mirror.

### Edit 8 — AC-8 added (full suite green)
- Source: Coverage C3
- Turns "additive" into a binary `make test` pass/fail — the full suite must stay green except via the two enumerated widenings.

### Edit 9 — Implementation outline rewritten
- Source: all critics
- 6 numbered steps now reflect the deferred `SupportedLanguage` edit, the explicit `PackageManager` widening + docstring update, the new banner in `__all__`, and the two in-place existing-test widenings.

### Edit 10 — TDD plan rewritten
- Source: Test-Quality T2 + Coverage C1/C2/C3
- Concrete `assert` templates for AC-1..AC-4; concrete code template for AC-5 (renamed + widened test) and AC-6 (narrowed parametrize with the future-story comment).

### Edit 11 — Files-to-touch expanded
- Source: Consistency B4/B5
- Added `tests/unit/types/test_identifiers.py` and `tests/unit/probes/layer_b/test_dep_graph.py` as explicit edits (the loud snapshot widening and parametrize narrowing).

### Edit 12 — Out-of-scope clarified
- Source: Consistency B1/B3
- Explicitly defers `SupportedLanguage += "python"`, `_DISPATCH +1`, wheel pin to S4-01.

### Edit 13 — Notes for implementer reframed
- Source: Design-Patterns D4 + Test-Quality T1/T3
- Frames story as canonical ADR-0043 loud-edit shape in miniature; documents the mutation-resistant assertion intent; flags `__all__` ordering convention.

### Edit 14 — Validation notes block added under header
- Standard validator output recording every change with breadcrumbs.

### Edit 15 — Status `Ready` → `HARDENED`
- Story is now ready for `phase-story-executor`.

## Verdict rationale

The story had real, fixable structural problems — five `block`-severity Consistency findings plus five `harden`-severity Coverage/Test-Quality findings — but the *goal* was sound. The original story-writer correctly identified the foundation work; the failure mode was misjudging which loud edits could land in isolation (`SupportedLanguage += "python"` cannot — it needs atomic `_DISPATCH` + wheel pin) and underestimating which shipped tests would need explicit in-scope widening (the PackageManager snapshot pin + the dep-graph parametrize). The hardened story is honest about both. Verdict: **HARDENED**, not RESCUE — the story's goal and structure survive the audit.

## Recommended next step

`phase-story-executor docs/phases/07.5-multi-language-foundations-python/stories/S1-01-foundation-literal-and-error-edits.md`

The story is now self-consistent, the ACs are individually verifiable and collectively guarantee the goal, the TDD plan would catch a wrong implementation, and the prescribed implementation follows the canonical ADR-0043 loud-edit pattern that future Phase-7.5+ stories should mirror.
