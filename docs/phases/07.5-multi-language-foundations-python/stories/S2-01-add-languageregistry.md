# Story S2-01 — Add `LanguageRegistry` + `default_language_registry`

**Step:** Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`
**Status:** Ready
**Effort:** S
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0001, ADR-0002

## Context
Every conformance test in Step 7 parameterizes over `default_language_registry.all()`, so the registry that *collects* `LanguagePack` values must exist before any pack is constructed or `register_language` is wired. This story lands the plain `dict[Language, LanguagePack]` wrapper — the exact shape of the shipped `DepGraphRegistry` / `FreshnessRegistry` — with build-then-publish `register`, deterministic sorted `all()`, and the process-global singleton that the `packs/` collection point will register into.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — LanguageRegistry + default_language_registry` — the public interface, build-then-publish `register`, sorted `all()`, duplicate-raises semantics.
- **Architecture:** `../phase-arch-design.md §Logical view — components and relationships` — `LanguageRegistry` `o-- LanguagePack` collection arrow.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — build-then-publish for the one registry `register_language` owns; no `unregister`; duplicate registration raises naming both call sites.
- **Phase ADRs:** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — the `LanguagePack` value this registry collects; conformance auto-enrolls because the pack value *is* the enrollment unit.
- **Existing code:** `src/codegenie/depgraph/registry.py` — `DepGraphRegistry` is the shape to mirror: a plain class wrapping a `dict`, an `_origins` map so duplicate errors name both call sites, a module-level `default_dep_graph_registry` singleton, independent test instances.
- **Existing code:** `src/codegenie/errors.py` — `LanguageRegistryError` (landed in S1-01) is the exception this registry raises.
- **Existing code:** `src/codegenie/types/identifiers.py` — `Language` newtype used as the dict key and the `all()` sort key.

## Goal
Land `src/codegenie/languages/registry.py` with a `LanguageRegistry` class (`register`, `get`, `all()`) and the module-level `default_language_registry` singleton.

## Acceptance criteria
- [ ] The TDD red test in `tests/unit/languages/test_language_registry.py` exists, is committed, and was observed failing (`ImportError`/`AttributeError`) before implementation.
- [ ] `LanguageRegistry.register(pack)` uses build-then-publish — the pack is added to a fresh copy of the internal dict, then the copy is swapped in atomically; a unit test asserts the internal dict is never observably partial.
- [ ] `LanguageRegistry.all()` returns a `tuple[LanguagePack, ...]` sorted by `Language` — deterministic across calls and processes.
- [ ] `register` of a duplicate `Language` raises `LanguageRegistryError` whose message names **both** call-site origins (mirrors `DepGraphRegistry`'s `_origins` map).
- [ ] `get(language)` returns the registered pack; `get` on an absent `Language` raises `LanguageRegistryError`.
- [ ] Independent `LanguageRegistry()` instances do not pollute each other; `default_language_registry` is a module-level singleton.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files; `pytest tests/unit/languages/test_language_registry.py` passes; `import-linter` updated for `codegenie.languages.registry` if needed.
- [ ] Story `**Status:**` set to `Done`.

## Implementation outline
1. Create `src/codegenie/languages/registry.py` with `from __future__ import annotations`, a module docstring citing ADR-0002 and the `DepGraphRegistry` shape it mirrors.
2. Define `class LanguageRegistry` wrapping `_packs: dict[Language, LanguagePack]` and `_origins: dict[Language, str]` (origin = `module.qualname` of the registering call site, captured for the duplicate-error message).
3. `register(self, pack: LanguagePack) -> None` — duplicate `Language` raises `LanguageRegistryError` naming both origins; otherwise build a fresh dict copy with the new entry and rebind `self._packs`.
4. `get(self, language: Language) -> LanguagePack` — `KeyError` → `LanguageRegistryError`.
5. `all(self) -> tuple[LanguagePack, ...]` — `tuple(sorted(self._packs.values(), key=lambda p: p.language))`.
6. Module-level `default_language_registry = LanguageRegistry()`; export the names via `__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_language_registry.py`.

```python
# test_all_is_sorted_and_get_round_trips
#   arrange: build two distinct LanguagePack values for Language("python")
#            and Language("typescript") (helper fixture / minimal stub packs)
#   act:     reg = LanguageRegistry(); reg.register(py); reg.register(ts)
#   assert:  reg.all() == tuple sorted by .language;
#            reg.get(Language("python")) is py

# test_duplicate_language_raises_naming_both_sites
#   arrange: reg with Language("python") already registered
#   act/assert: reg.register(<different pack, same Language>)
#               raises LanguageRegistryError whose str names both origins

# test_build_then_publish_never_publishes_partial
#   arrange: a registry; monkeypatch / inspect that a failed register
#            leaves _packs byte-identical to the pre-call dict
```

Must fail with `ImportError` (no `codegenie.languages.registry` module) before any implementation exists.

### Green — make it pass
Add `registry.py` with the minimal `LanguageRegistry` — dict wrapper, `_origins` map, build-then-publish `register`, raising `get`, sorted `all()`, and the singleton. No `validate_pack`/`register_language` yet (those are S2-02/S2-03).

### Refactor — clean up
Docstrings on the class and each method citing ADR-0002; precise type hints (`tuple[LanguagePack, ...]`, no `Any`); a `structlog` debug event on `register` mirroring `depgraph.strategy.registered`; confirm `mypy --strict` clean and the `__all__` surface is minimal.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/registry.py` | New — `LanguageRegistry` + `default_language_registry`. |
| `src/codegenie/languages/__init__.py` | Re-export `LanguageRegistry` / `default_language_registry` (keep `__all__` ≤ 6 names per arch §Development view). |
| `tests/unit/languages/test_language_registry.py` | New — the registry unit tests. |
| `pyproject.toml` / `.importlinter` config | Extend the `codegenie.languages` import contract if a new submodule needs declaring. |

## Out of scope
- `validate_pack` and `register_language` — S2-02 and S2-03.
- The no-shadow check — S2-04.
- Idempotence + `language.registered` event — S2-05.
- The Hypothesis property test — S2-06 (this story's tests are example-based).

## Notes for the implementer
- Build-then-publish here means: construct the *new* dict fully, then rebind `self._packs` — never mutate the live dict in place. This is the only honest atomicity the append-only-substrate constraint (ADR-0002) permits for the one registry this phase owns.
- Mirror `DepGraphRegistry` exactly for the duplicate-error UX: capture `module.qualname` origins so the error message lets a developer locate both registrations without re-running.
- `all()` sort key is `Language` — golden files (S7-04) depend on this ordering; do not sort on anything else.
- Tests must construct independent `LanguageRegistry()` instances — never register into `default_language_registry` from a unit test, or later tests inherit the pollution.
- `Language` is the existing newtype from `codegenie.types.identifiers` — do not introduce a parallel `LanguageId`.
- Keep this module dependency-light: it imports only `LanguagePack`, `Language`, `LanguageRegistryError`, and `structlog`. The validation logic lives in S2-02, not here ("keep the registry dumb; validate on use" — ADR-0002 pattern-fit).
