# Story S1-01 — Foundation loud edits (`PackageManager` +3, `LanguageRegistryError`)

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** HARDENED
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001, ADR-0003

## Validation notes

Validated: 2026-05-26
Verdict: HARDENED
Findings addressed: 11 total — 5 blocks, 5 hardens, 1 nit

Changes applied:
- **Title + Goal narrowed**: `SupportedLanguage += "python"` removed from this story — S4-01 already claims atomic ownership of `SupportedLanguage Literal +1` + `_DISPATCH +1` row + `tree-sitter-python` wheel pin (Consistency B1/B3). Splitting them across stories would leave the grammar-kernel test suite RED between S1-01 landing and S4-01 landing (`tests/unit/grammars/test_lock.py::test_supported_languages_matches_literal_type` enforces Literal == `_DISPATCH` set; `test_language_for_returns_usable_language` parametrizes over `get_args(SupportedLanguage)` and would attempt to load a non-existent wheel for `"python"`). Violates G3 ("Node/TypeScript regression suite unchanged and green").
- **AC-1 removed** (was: "`SupportedLanguage` includes `"python"` …") — see above.
- **PackageManager scope made honest**: `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` pins `set(get_args(PackageManager)) == {bun, pnpm, yarn-classic, yarn-berry, npm}` exactly (line 41–54). Adding `pip`/`poetry`/`uv` breaks this test. The widening IS the loud edit per ADR-0043 + Phase-7.5 ADR-0001 — included explicitly in Files-to-touch (Consistency B4).
- **Dep-graph parametrize narrowed**: `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant` (line 216) parametrizes `get_args(PackageManager)` and looks up `_PM_LOCKFILES[pm]` — only Node 5 entries exist; new Python members would KeyError. Test intent is the Node no-strategy invariant — narrow its parametrize to the explicit Node 5 whitelist; the Python no-strategy mirror is a future Phase 7.5 story's concern (Consistency B5).
- **AC-3 hardened**: marker-only test now also asserts `__str__` identity and no new class-level attributes (so a future commit that secretly adds an `__init__` or class attribute trips the test) (Test-Quality T1).
- **AC for docstring-cites-raise-sites added**: AC-3 now has a TDD pin asserting the docstring contains BOTH "`register_language`" and "`validate_pack`" — mirrors `FreshnessRegistryError` / `DepGraphRegistryError` precedent (Coverage C2).
- **AC for `_NEWTYPE_REGISTRY` Phase-7.5 mention added**: AC-2 now requires the `PackageManager` docstring entry to mention "Phase 7.5" or "ADR-0001" specifically (Coverage C3).
- **Additive-claim AC added**: AC explicitly requiring the full pre-existing suite (`make test`) to stay green after the loud edits + widenings — turns the "additive" doctrine into a binary pass/fail criterion (Coverage C4).
- **Notes section reframes the story as the canonical ADR-0043 loud-edit shape** — including the test-widening half (ADR-0001 snapshot bump) which is *part of* the loud edit, not a violation of "no silent edits to shipped code" (Design-Patterns D4).
- **Files-to-touch updated** to enumerate the two existing test files that legitimately widen as part of the loud edit, with the precise edits needed.

Full audit log: [_validation/S1-01-foundation-literal-and-error-edits.md](_validation/S1-01-foundation-literal-and-error-edits.md)

## Context
Two downstream consumers — `LanguagePack` (S1-02) and `register_language` / `validate_pack` (S2-01/S2-02/S2-03) — reference identifiers that do not yet exist: the `"pip"`/`"poetry"`/`"uv"` package-manager tags (so `LanguagePack.dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]` accepts Python strategy keys), and a `LanguageRegistryError` marker (so `validate_pack` has a single typed raise site). This story lands those net-new identifier members as the **loud, compiler-policed edits** ADR-0043 sanctions (a `Literal` `+3`, a new exception subclass) — and, as part of that loud-edit doctrine, widens the two shipped Phase-1 tests that snapshot the *old* `PackageManager` closed set (so the widening is loud, not silent). The `SupportedLanguage += "python"` part of the foundation is deferred to **S4-01**, which atomically lands the Literal member alongside the `_DISPATCH` row and the `tree-sitter-python` wheel pin — split landings would leave the grammar-kernel test suite red across multiple stories, violating G3 ("Node/TypeScript regression suite unchanged and green"). This is foundational work — nothing else in the phase compiles without it.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Control flow` — the "loud edits" paragraph enumerates `SupportedLanguage` `+1`, `PackageManager` `+3` as compiler-policed, not violations.
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack` — `grammars: tuple[SupportedLanguage, ...]`, `dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]` show why these members are needed.
- **Phase ADRs (rules to honor):** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — `LanguageRegistryError` is the loud import-time failure the `LanguagePack` kernel raises.
- **Phase ADRs (rules to honor):** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — adding a grammar is a `SupportedLanguage` `Literal` `+1` plus a `_DISPATCH` `+1` row — that bundle lands atomically in **S4-01**, not here (the wheel pin is what makes the Literal addition test-green).
- **Sibling story (atomic landing):** `S4-01-wire-tree-sitter-python-grammar.md` — owns `SupportedLanguage += "python"`, the `_DISPATCH` `+1` row, and the `tree-sitter-python` wheel pin together. This story explicitly defers to S4-01 for those three.
- **Existing code:** `src/codegenie/types/identifiers.py` — `PackageManager = Literal["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]` (line ~54); the `_NEWTYPE_REGISTRY` mapping requires a docstring row for every `__all__` member.
- **Existing code:** `src/codegenie/errors.py` — the flat `CodegenieError` hierarchy; `__all__` list grouped by phase banner (`# Phase 1 (Layer A) — S1-01.`, `# Phase 2 (Layers B–G) — S1-02.`, etc.); existing `*RegistryError` markers (`FreshnessRegistryError`, `DepGraphRegistryError`) are the precedent shape — marker only, no `__init__`, docstring naming raise sites.
- **Existing tests (widen as part of the loud edit):** `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` (lines 41–54) pins `set(get_args(PackageManager)) == {5 Node members}` exactly — widening this set IS the loud edit (ADR-0001 snapshot bump).
- **Existing tests (narrow parametrize):** `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant` (line 216) parametrizes `get_args(PackageManager)` and looks up `_PM_LOCKFILES[pm]` — only Node 5 entries exist; the parametrize must be narrowed to the explicit Node 5 whitelist so adding Python managers does not KeyError. The Python no-strategy mirror is a future story.
- **Existing tests (already accommodating):** `tests/property/test_dep_graph_strategy_dispatch.py` uses `_PACKAGE_MANAGERS = get_args(PackageManager)` for hypothesis sampling — the `no_strategy_for_ecosystem` assertion holds for any unregistered ecosystem, so the new Python members ride through without an edit. Verify this stays green after the widening.

## Goal
Add `"pip"`, `"poetry"`, `"uv"` to `PackageManager` and a `LanguageRegistryError` marker to `codegenie.errors`, each a compiler-policed loud edit that type-checks clean — and widen the two shipped Phase-1 tests that snapshot the *old* `PackageManager` closed set as the documented ADR-0001 snapshot bump (so the widening is loud, not silent). `SupportedLanguage += "python"` is deferred to S4-01.

## Acceptance criteria
- [ ] AC-1 — `PackageManager` includes `"pip"`, `"poetry"`, `"uv"` (8 members total). `set(get_args(PackageManager)) == {"bun", "pnpm", "yarn-classic", "yarn-berry", "npm", "pip", "poetry", "uv"}` exactly.
- [ ] AC-2 — `_NEWTYPE_REGISTRY["PackageManager"]` docstring is updated to mention the Phase 7.5 `+3` AND cite Phase-7.5 ADR-0001 (so the docstring's *meaning*, not just its existence, changes). Specifically: the new docstring must contain BOTH the substring `"Phase 7.5"` AND `"ADR-0001"` so `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` stays green AND a new assertion can pin the Phase-7.5 widening.
- [ ] AC-3 — `LanguageRegistryError(CodegenieError)` exists in `codegenie.errors`, is in `__all__` under a new `# --- Phase 7.5 — S1-01 markers ---` banner, is a behavior-free marker — no `__init__` (`LanguageRegistryError.__init__ is CodegenieError.__init__`), no `__str__` (`LanguageRegistryError.__str__ is CodegenieError.__str__`), and no class-level attribute additions beyond Python's default (`set(vars(LanguageRegistryError)) - set(vars(CodegenieError)) ⊆ {"__doc__", "__module__", "__qualname__"}`).
- [ ] AC-4 — `LanguageRegistryError`'s docstring contains BOTH the substrings `"register_language"` AND `"validate_pack"` (naming its raise sites; mirrors the `FreshnessRegistryError`/`DepGraphRegistryError` precedent — a typo'd or generic docstring will fail the assertion).
- [ ] AC-5 — `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` is widened in place to assert the 8-member set AND renamed (e.g. `test_package_manager_carries_the_adr_0013_plus_phase_7_5_values`) AND its docstring updated to cite both ADR-0013 (Node 5) and Phase-7.5 ADR-0001 (Python +3). This is the loud ADR-0001 snapshot bump — the widening MUST be visible in the test name and docstring, not just the set literal.
- [ ] AC-6 — `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant`'s parametrize is narrowed from `list(get_args(PackageManager))` to an explicit Node-5 whitelist `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]` (preserving the test's Node-only intent) with a one-line comment citing this story and noting the Python mirror is a future Phase-7.5 story.
- [ ] AC-7 — The TDD red tests for AC-1..AC-6 exist, are committed under `tests/unit/languages/test_foundation_edits.py` (new) and via the in-place widening of the two named existing files; the new file's `__init__.py` is created.
- [ ] AC-8 — `ruff check`, `ruff format --check`, `mypy --strict src/`, and the FULL `pytest` suite (not a subset) all pass — surfacing the "additive" doctrine as a binary pass/fail criterion. Specifically: every test green on `main` BEFORE this story remains green after, with the only non-trivial diffs being the two existing-test widenings explicitly enumerated in AC-5 and AC-6. Any other shipped test going from green to red is a structural failure of this story and must be surfaced (Rule 12 fail-loud), not silently weakened.
- [ ] AC-9 — Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. Edit `src/codegenie/types/identifiers.py`: extend the `PackageManager` `Literal` with `"pip"`, `"poetry"`, `"uv"`; update the `_NEWTYPE_REGISTRY["PackageManager"]` docstring entry to add both the substring `"Phase 7.5"` and `"ADR-0001"` (so the docstring's meaning changes — a future drift test pins the widening).
2. Edit `src/codegenie/errors.py`: add `class LanguageRegistryError(CodegenieError)` with a docstring that names BOTH `register_language` and `validate_pack` as raise sites (mirrors `FreshnessRegistryError`/`DepGraphRegistryError`); add it to `__all__` under a new `# --- Phase 7.5 — S1-01 markers ---` banner at the end of the list.
3. Widen `tests/unit/types/test_identifiers.py::test_package_manager_carries_the_five_adr_0013_values` in place — rename to `test_package_manager_carries_the_adr_0013_plus_phase_7_5_values`, update the set literal to the 8 members, and update the docstring to cite both ADR-0013 and Phase-7.5 ADR-0001. This is the documented ADR-0001 snapshot bump.
4. Narrow `tests/unit/probes/layer_b/test_dep_graph.py::test_no_strategy_per_package_manager_variant`'s parametrize from `list(get_args(PackageManager))` to the explicit Node-5 whitelist `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]` and add a one-line comment citing this story.
5. Write the new red tests in `tests/unit/languages/test_foundation_edits.py`; create `tests/unit/languages/__init__.py`. Run them red, then green. Run the FULL suite (`make test`) to confirm AC-8 (no other shipped test goes red).
6. `SupportedLanguage += "python"` is NOT touched here — it lands in S4-01 atomically with `_DISPATCH +1` and the `tree-sitter-python` wheel pin.

## TDD plan — red / green / refactor
### Red — write the failing tests first
Test file: `tests/unit/languages/test_foundation_edits.py` (new; create `tests/unit/languages/` + `__init__.py`).

```python
# test_package_manager_includes_python_managers (AC-1)
#   from typing import get_args
#   from codegenie.types.identifiers import PackageManager
#   assert set(get_args(PackageManager)) == {
#       "bun", "pnpm", "yarn-classic", "yarn-berry", "npm",   # Phase 1 ADR-0013
#       "pip", "poetry", "uv",                                  # Phase 7.5 ADR-0001
#   }

# test_newtype_registry_package_manager_docstring_cites_phase_7_5 (AC-2)
#   from codegenie.types.identifiers import _NEWTYPE_REGISTRY
#   doc = _NEWTYPE_REGISTRY["PackageManager"]
#   assert "Phase 7.5" in doc and "ADR-0001" in doc, doc
#   # A drift in the docstring that omits the Phase-7.5 widening fails this assertion —
#   # the existing test_newtype_registry_matches_all only asserts ADR-0010 citation,
#   # which the OLD docstring already satisfied. This is the mutation-resistant pin.

# test_language_registry_error_is_marker (AC-3)
#   from codegenie.errors import CodegenieError, LanguageRegistryError, __all__
#   assert issubclass(LanguageRegistryError, CodegenieError)
#   assert LanguageRegistryError.__init__ is CodegenieError.__init__       # no __init__
#   assert LanguageRegistryError.__str__  is CodegenieError.__str__        # no __str__
#   extra_attrs = set(vars(LanguageRegistryError)) - set(vars(CodegenieError))
#   assert extra_attrs <= {"__doc__", "__module__", "__qualname__"}, extra_attrs
#   assert "LanguageRegistryError" in __all__

# test_language_registry_error_docstring_names_raise_sites (AC-4)
#   from codegenie.errors import LanguageRegistryError
#   doc = LanguageRegistryError.__doc__ or ""
#   assert "register_language" in doc, doc
#   assert "validate_pack"    in doc, doc
#   # Mirrors FreshnessRegistryError / DepGraphRegistryError docstring discipline:
#   # the marker names the raise sites so a grep finds them without `git log`.
```

In-place test widenings (AC-5, AC-6):

```python
# tests/unit/types/test_identifiers.py — rename and widen:
def test_package_manager_carries_the_adr_0013_plus_phase_7_5_values() -> None:
    """ADR-0013 (Node 5) + Phase-7.5 ADR-0001 (Python +3) — the closed
    ``PackageManager`` Literal carries all eight package-manager tags."""
    assert set(get_args(ids.PackageManager)) == {
        # Phase 1 ADR-0013 (yarn split into classic/berry for plugin dispatch).
        "bun", "pnpm", "yarn-classic", "yarn-berry", "npm",
        # Phase 7.5 ADR-0001 (Python +3).
        "pip", "poetry", "uv",
    }

# tests/unit/probes/layer_b/test_dep_graph.py — narrow parametrize:
_NODE_PMS_FOR_NO_STRATEGY: Final[list[PackageManager]] = [
    "bun", "pnpm", "yarn-classic", "yarn-berry", "npm",
]
# Phase 7.5 S1-01 — _PM_LOCKFILES carries only the Node 5 fixtures; the Python
# no-strategy mirror lands in a future Phase-7.5 story (S5-02/S5-03/S5-04 will
# register pip/poetry/uv strategies; until then the Python no-strategy test
# belongs in a Python-side test file with Python-side lockfile fixtures).
@pytest.mark.parametrize("pm", _NODE_PMS_FOR_NO_STRATEGY)
def test_no_strategy_per_package_manager_variant(...):
    ...
```

Each new test imports the symbol; before the edits the `Literal` members are absent (`AssertionError`) and `LanguageRegistryError` raises `ImportError`. The two widened/narrowed existing tests fail before the corresponding edits — proving the test really exercises the new contract.

### Green — make it pass
Land the three `PackageManager` Literal members, the `_NEWTYPE_REGISTRY` docstring widening, and the `LanguageRegistryError` marker class. Smallest possible diff — three string members, one docstring widening, one marker class. No behavior. Then apply the two in-place existing-test widenings.

### Refactor — clean up
- Confirm `__all__` in `codegenie.errors` carries `LanguageRegistryError` under the new Phase-7.5 banner (not inserted alphabetically into a Phase-1 group).
- Confirm `_NEWTYPE_REGISTRY["PackageManager"]` is the only docstring touched; other rows are unchanged.
- Confirm `LanguageRegistryError` docstring follows the `FreshnessRegistryError` / `DepGraphRegistryError` precedent (names the raise sites, marker-only note, no `__init__` doc).
- Run `make check` (`lint → typecheck → test → fence`) and confirm AC-8 is satisfied — no test goes from green to red except via the two enumerated widenings.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | `PackageManager` Literal `+3`; `_NEWTYPE_REGISTRY["PackageManager"]` docstring widening (must contain `"Phase 7.5"` and `"ADR-0001"`) |
| `src/codegenie/errors.py` | new `LanguageRegistryError` marker; new `# --- Phase 7.5 — S1-01 markers ---` banner in `__all__` |
| `tests/unit/types/test_identifiers.py` | Widen `test_package_manager_carries_the_five_adr_0013_values` (rename, set literal, docstring) — AC-5; the loud snapshot bump |
| `tests/unit/probes/layer_b/test_dep_graph.py` | Narrow `test_no_strategy_per_package_manager_variant`'s parametrize to the Node-5 whitelist — AC-6 |
| `tests/unit/languages/test_foundation_edits.py` | new — red/green tests for AC-1..AC-4 |
| `tests/unit/languages/__init__.py` | new — package marker for the new test dir |

## Out of scope
- `SupportedLanguage += "python"`, the `_DISPATCH` `+1` row, and the `tree-sitter-python` wheel pin — all three land atomically in **S4-01**. Splitting them off would leave the grammar-kernel tests RED across story landings.
- Any use of `LanguageRegistryError` (raising it from `validate_pack` / `register_language`) — S2-01/S2-02/S2-03.
- The `LanguagePack` value itself, the `ProjectDetector` Protocol, the `DetectionResult` sum type, the `markers.py` catalog — S1-02 / S1-03 / S1-04 / S1-05.
- A Python no-strategy mirror of `test_no_strategy_per_package_manager_variant` — future Phase-7.5 story (likely paired with S5-02/S5-03/S5-04 when pip/poetry/uv strategies land and need a "still-unregistered before registration" baseline).

## Notes for the implementer
- **This is the canonical ADR-0043 loud-edit pattern in miniature.** The story shape is: (1) extend a closed `Literal` / add a marker exception; (2) widen the shipped snapshot test(s) that *pin* the old closed set — the widening *is* the loud edit, not a silent edit to shipped code. Future Phase 7.5+ stories that touch closed `Literal`s in `types/identifiers.py` should mirror this shape: rename the snapshot test (so the name tells the next reader the contract widened), update the docstring (citing the new ADR), update the set literal. Do not weaken assertions; do not delete the existing pin and write a new one in its place — widen in place so `git blame` traces the contract evolution.
- ADR-0003 is explicit: `language` reuses the **existing** `Language` newtype — do **not** mint a `LanguageId`. This story adds no new `NewType`, only `Literal` members and one exception.
- `PackageManager` is a `Literal`, not a `NewType` — extend the membership, do not wrap it.
- `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` fences `__all__` against `_NEWTYPE_REGISTRY` and enforces ADR-0010 citation in every docstring. `PackageManager` is already a registry key — you are widening its docstring value, not adding a key. The OLD docstring already contains `"ADR-0010"` so the existing test would pass with an unchanged docstring — AC-2's stricter `"Phase 7.5"` + `"ADR-0001"` substring assertion is the mutation-resistant pin that catches a forgotten docstring update.
- Keep `LanguageRegistryError` a pure marker: the structured reason (which field, which colliding site) is constructed at the raise site by S2-02, not embedded on the class — mirror `DepGraphRegistryError`'s docstring note. AC-3's explicit `set(vars(LanguageRegistryError)) - set(vars(CodegenieError)) ⊆ {"__doc__", "__module__", "__qualname__"}` assertion is mutation-resistant against a future commit that secretly adds class state.
- AC-4's BOTH-substrings assertion (`"register_language"` AND `"validate_pack"`) on the docstring is deliberate — a single substring would pass a generic "the registry raises this" docstring; both substrings force the docstring to name the actual raise-site functions.
- `tests/property/test_dep_graph_strategy_dispatch.py` uses `_PACKAGE_MANAGERS = get_args(PackageManager)` for hypothesis sampling — the `no_strategy_for_ecosystem` assertion holds for any unregistered ecosystem, so the new Python members ride through without an edit. Run it after the widening to confirm; if it goes red, surface (Rule 12) — do not edit it.
- AC-8 turns "additive" into a binary pass/fail criterion. Run `make test` (the full suite) end-to-end before declaring the story Done. If any test goes from green to red beyond the two enumerated widenings, that is a structural failure of this story — surface it, do not silently weaken the failing test (Rule 12).
