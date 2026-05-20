# Story S3-01 — Add the `packs/` explicit-import collection point

**Step:** Step 3 — Retrofit TypeScript as `LanguagePack` #1 (by reference)
**Status:** Ready
**Effort:** S
**Depends on:** S2-03
**ADRs honored:** ADR-0006, ADR-0002

## Context
Every `LanguagePack` value must be *constructed and registered* somewhere, and — exactly like `codegenie/probes/__init__.py` — the language axis needs one explicit-import collection point so adding a pack is a new module plus one additive `import` line, never an `importlib.metadata` scan. This story lands that empty collection point so S3-02 (TypeScript) and later S7-01 (Python) have a home and a registration trigger.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Development view — source code organization` — the `src/codegenie/languages/packs/` sub-package and the "explicit-import collection point" mandate.
- **Architecture:** `../phase-arch-design.md §Component design — register_language() + validate_pack()` — `register_language` is the privileged op the pack modules call at import.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — `packs/__init__.py` imports `.typescript` first; the pack-module import is what fires `register_language`.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — Open/Closed at the file boundary: a new language is new files plus one import line.
- **Existing code:** `src/codegenie/probes/__init__.py` — the precedent: explicit `from codegenie.probes import (...)` block, no entry-point scan, `noqa: F401 — registration` comments on side-effecting imports.

## Goal
Land `src/codegenie/languages/packs/__init__.py` as the empty explicit-import collection point for the language axis, mirroring `probes/__init__.py`'s no-scan registration idiom.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and is green: `tests/unit/languages/test_packs_collection.py` imports `codegenie.languages.packs` and asserts it imports cleanly with no `default_language_registry` entries added yet (collection point is empty at this story).
- [ ] `src/codegenie/languages/packs/__init__.py` exists with a module docstring stating it is the explicit-import collection point and that pack modules are added one additive `import` line at a time (no `importlib.metadata` scan).
- [ ] No `importlib.metadata` / entry-point discovery anywhere in the new file (grep-asserted in the test, mirroring the `probes/__init__.py` discipline).
- [ ] `import-linter` has a contract (or the existing `codegenie.languages` contract is confirmed to cover `codegenie.languages.packs`); `make lint-imports` passes.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, and `pytest` pass on the touched files; `make fence` stays green.
- [ ] Status set to `Done` on completion.

## Implementation outline
1. Create `src/codegenie/languages/packs/__init__.py` with only a module docstring — no imports of pack modules yet (S3-02 adds `from codegenie.languages.packs import typescript`).
2. The docstring states: this is the explicit-import collection point; adding a language pack = new `packs/<lang>.py` module + one additive import line here; no entry-point scan (supply-chain + cold-start hygiene), mirroring `probes/__init__.py`.
3. Confirm `import-linter` config covers `codegenie.languages.packs`; if `codegenie.languages` already has a contract, verify the sub-package is included.
4. Run `make fence`, `make lint-imports`, `mypy --strict src/`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_packs_collection.py`.
Test name: `test_packs_module_imports_cleanly_and_is_empty` — asserts `importlib.import_module("codegenie.languages.packs")` succeeds and `default_language_registry.all()` is empty after the import (no pack registered yet at this step).
```python
# arrange: nothing — fresh process import
# act: import codegenie.languages.packs ; read default_language_registry.all()
# assert: import raises no exception AND len(default_language_registry.all()) == 0
#   intent: the collection point exists and is genuinely empty until S3-02 adds a row
```
Add a second test `test_packs_module_has_no_entrypoint_scan` reading the module source and asserting `"importlib.metadata"` and `"entry_points"` do not appear — encodes the no-scan invariant. Both fail until the file exists.

### Green — make it pass
Create the `packs/__init__.py` file with only a docstring. The import succeeds; the registry stays empty; the source has no scan strings.

### Refactor — clean up
Tighten the docstring to name the `probes/__init__.py` precedent and the ADR-0006 ordering note (`.typescript` will be imported first). Confirm `__all__` is unnecessary (the file exports nothing yet) or add an empty `__all__: list[str] = []` if the codebase convention prefers an explicit one — match `probes/__init__.py`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/packs/__init__.py` | New explicit-import collection point (empty this story). |
| `tests/unit/languages/test_packs_collection.py` | Red test: clean import, empty registry, no entry-point scan. |
| `.importlinter` / `pyproject.toml` (import-linter config) | Confirm/extend the contract to cover `codegenie.languages.packs`. |

## Out of scope
- Constructing or registering `TS_PACK` — that is S3-02.
- Constructing or registering `PYTHON_PACK` and adding `import .python` — that is S7-01.
- Any `ProjectDetector` implementation — S3-03.

## Notes for the implementer
- Keep the file genuinely empty of pack imports — a premature `import .typescript` would fail because `packs/typescript.py` does not exist until S3-02.
- The `noqa: F401 — registration` comment idiom from `probes/__init__.py` is what S3-02/S7-01 will use; do not add it now (nothing to suppress yet).
- Do not invent an entry-point/plugin-discovery mechanism — the supply-chain + cold-start rationale in `probes/__init__.py` applies identically here.
- The collection point's *import* is the registration trigger: when S3-02 lands, importing `codegenie.languages.packs` must transitively call `register_language(TS_PACK)`. Leave the docstring noting that contract so the next implementer wires it correctly.
