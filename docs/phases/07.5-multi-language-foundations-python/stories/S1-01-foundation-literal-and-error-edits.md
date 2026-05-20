# Story S1-01 — Foundation loud edits (`SupportedLanguage` +1, `PackageManager` +3, `LanguageRegistryError`)

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001, ADR-0003

## Context
Every downstream Step-1 type — `LanguagePack`, `DetectionResult`, `LANGUAGE_MARKERS` — references identifiers that do not yet exist: a `"python"` grammar key, the `"pip"`/`"poetry"`/`"uv"` package-manager tags, and a `LanguageRegistryError` exception. This story lands those net-new identifier members as the **loud, compiler-policed edits** ADR-0043 sanctions (a `Literal` `+1`/`+3`, a new exception subclass) so the rest of Step 1 has the kernel-tier vocabulary it needs. This is foundational work — nothing else in the phase compiles without it.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Control flow` — the "loud edits" paragraph enumerates `SupportedLanguage` `+1`, `PackageManager` `+3` as compiler-policed, not violations.
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack` — `grammars: tuple[SupportedLanguage, ...]`, `dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]` show why these members are needed.
- **Phase ADRs (rules to honor):** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — adding a grammar is a `SupportedLanguage` `Literal` `+1` plus a `_DISPATCH` `+1` row (the `_DISPATCH` row is S4-01, not this story; the `Literal` member is here).
- **Phase ADRs (rules to honor):** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — `LanguageRegistryError` is the loud import-time failure the `LanguagePack` kernel raises.
- **Existing code:** `src/codegenie/grammars/lock.py` — `SupportedLanguage = Literal["typescript", "tsx", "javascript"]` (line ~50); the `__all__` and the `_DISPATCH` dict. Note the module docstring's own example: "Add a Phase-8 row (e.g. `"python"`)".
- **Existing code:** `src/codegenie/types/identifiers.py` — `PackageManager = Literal["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]` (line ~54); the `_NEWTYPE_REGISTRY` mapping requires a docstring row for every `__all__` member.
- **Existing code:** `src/codegenie/errors.py` — the flat `CodegenieError` hierarchy; `__all__` list; existing `*RegistryError` markers (`FreshnessRegistryError`, `DepGraphRegistryError`) are the precedent shape — marker only, no `__init__`.

## Goal
Add `"python"` to `SupportedLanguage`, `"pip"`/`"poetry"`/`"uv"` to `PackageManager`, and a `LanguageRegistryError` marker to `codegenie.errors`, each a compiler-policed loud edit that type-checks clean.

## Acceptance criteria
- [ ] `SupportedLanguage` includes `"python"`; `codegenie.grammars.lock.supported_languages()` returns a tuple containing `"python"`.
- [ ] `PackageManager` includes `"pip"`, `"poetry"`, `"uv"` (8 members total); `_NEWTYPE_REGISTRY["PackageManager"]` docstring is updated to mention the Phase 7.5 `+3` so `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` stays green.
- [ ] `LanguageRegistryError(CodegenieError)` exists in `codegenie.errors`, is in `__all__`, is a behavior-free marker (no `__init__`, no `__str__`), and has a one-line docstring naming `register_language` / `validate_pack` as its raise sites.
- [ ] The TDD red test for the three additions exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, and `pytest` pass on the touched files; the full existing suite stays green (these are additive Literal/exception edits).
- [ ] Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. Edit `src/codegenie/grammars/lock.py`: add `"python"` to the `SupportedLanguage` `Literal`. Do **not** add the `_DISPATCH` row here — that needs the `tree-sitter-python` wheel and is S4-01.
2. Edit `src/codegenie/types/identifiers.py`: extend the `PackageManager` `Literal` with `"pip"`, `"poetry"`, `"uv"`; update the `_NEWTYPE_REGISTRY["PackageManager"]` docstring entry to cite the Phase 7.5 `+3`.
3. Edit `src/codegenie/errors.py`: add `class LanguageRegistryError(CodegenieError)` with a docstring; add it to `__all__` under a `# --- Phase 7.5 markers ---` comment.
4. Write the red test asserting all three members/types exist; run it red, then green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_foundation_edits.py` (new; create `tests/unit/languages/` + `__init__.py`).

```python
# test_supported_language_includes_python
#   assert "python" in get_args(SupportedLanguage)  -- and in supported_languages()
# test_package_manager_includes_python_managers
#   for pm in ("pip", "poetry", "uv"): assert pm in get_args(PackageManager)
# test_language_registry_error_is_codegenie_marker
#   assert issubclass(LanguageRegistryError, CodegenieError)
#   assert LanguageRegistryError.__init__ is CodegenieError.__init__  -- marker only
#   assert "LanguageRegistryError" in codegenie.errors.__all__
```
Each test imports the symbol; before the edits the `Literal` members are absent (`AssertionError`) and `LanguageRegistryError` raises `ImportError`.

### Green — make it pass
Add the three `Literal` members and the `LanguageRegistryError` class. Smallest possible diff — three string members plus one marker class. No behavior.

### Refactor — clean up
Confirm `__all__` ordering matches the file's existing convention; confirm the `_NEWTYPE_REGISTRY` docstring row is updated (the drift test enforces this); confirm the `LanguageRegistryError` docstring follows the `FreshnessRegistryError` precedent (names the raise sites, marker-only note).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/grammars/lock.py` | `SupportedLanguage` Literal `+1` (`"python"`) |
| `src/codegenie/types/identifiers.py` | `PackageManager` Literal `+3`; `_NEWTYPE_REGISTRY` docstring update |
| `src/codegenie/errors.py` | new `LanguageRegistryError` marker + `__all__` entry |
| `tests/unit/languages/test_foundation_edits.py` | new — red/green test for all three edits |
| `tests/unit/languages/__init__.py` | new — package marker for the new test dir |

## Out of scope
- The `_DISPATCH` `+1` row in `grammars/lock.py` and the `tree-sitter-python` wheel pin — S4-01.
- Any use of `LanguageRegistryError` (raising it) — S2-01/S2-02/S2-03.
- The `LanguagePack` value itself — S1-02.

## Notes for the implementer
- ADR-0003 is explicit: `language` reuses the **existing** `Language` newtype — do **not** mint a `LanguageId`. This story adds no new `NewType`, only `Literal` members and one exception.
- `PackageManager` is a `Literal`, not a `NewType` — extend the membership, do not wrap it.
- `tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all` fences `__all__` against `_NEWTYPE_REGISTRY`. `PackageManager` is already a registry key — you are editing its docstring value, not adding a key. Run that test after the edit.
- Keep `LanguageRegistryError` a pure marker: the structured reason (which field, which colliding site) is constructed at the raise site by S2-02, not embedded on the class — mirror `DepGraphRegistryError`'s docstring note.
- This is a `make check`-green-keeping edit: a `Literal` member-add is additive and should not break any existing test; if a test breaks, surface it — do not weaken it.
