# Story S1-02 — Add the `LanguagePack` frozen total value

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-04
**ADRs honored:** ADR-0001, ADR-0003, ADR-0006

## Context
`LanguagePack` is the load-bearing value of the phase: a frozen Pydantic model that *is* a language — six required capability fields plus one typed retrofit discriminator. A partial language is a real bug, and a total frozen value pushes that bug to the construction site where `mypy --strict` catches it for free (G2). This story lands the new `src/codegenie/languages/` package's `LanguagePack` definition; it is the seam every Phase 8+ target language registers through and the type `S2-01`'s registry and `S3-02`/`S7-01`'s packs construct.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack` — the full public-interface code block (`model_config`, six fields, `package_managers` `@property`).
- **Architecture:** `../phase-arch-design.md §Data model` — the `LanguagePack — contract (stable, in-memory; pinned by snapshot fence)` block — the canonical field list and order.
- **Phase ADRs (rules to honor):** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — frozen Pydantic v2, `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`; `package_managers` is a derived `@property`, NOT a field.
- **Phase ADRs (rules to honor):** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — `language: Language` reuses the existing newtype; `grammars: tuple[SupportedLanguage, ...]` models the one-to-many relation.
- **Phase ADRs (rules to honor):** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — `probes_self_registered: bool = False` is the typed retrofit discriminator.
- **Source design:** `../final-design.md §Departures` item 5 — `package_managers` derived `@property` over `dep_graph_strategies.keys()`, never a seventh field (drift-prone dual source of truth).
- **Existing code:** `src/codegenie/types/identifiers.py` — `Language`, `PackageManager` (the `+3` from S1-01).
- **Existing code:** `src/codegenie/grammars/lock.py` — `SupportedLanguage` (the `+1` from S1-01).
- **Existing code:** `src/codegenie/probes/base.py` — `Probe` ABC (`layer_a_probes: tuple[type[Probe], ...]`).
- **Existing code:** `src/codegenie/depgraph/registry.py` — `DepGraphStrategy` callable alias.

## Goal
Land the `src/codegenie/languages/` package carrying the frozen Pydantic `LanguagePack` with six required capability fields, the `probes_self_registered` discriminator, and the derived `package_managers` property — such that an incomplete construction is a `mypy --strict` error.

## Acceptance criteria
- [ ] `LanguagePack` is a `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`.
- [ ] It carries exactly: `language: Language`, `grammars: tuple[SupportedLanguage, ...]`, `project_detector: ProjectDetector`, `layer_a_probes: tuple[type[Probe], ...]`, `dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]`, `search_adapter_module: str`, `probes_self_registered: bool = False` — and `package_managers` as a `@property`, not a field.
- [ ] An incomplete `LanguagePack(...)` (a field omitted) is a `mypy --strict` construction-site error — verified by S1-06's harness (this story provides the type; S1-06 the test machinery; the criterion here is "a runtime `LanguagePack()` with a missing field raises `pydantic.ValidationError`").
- [ ] An extra/typo'd field is a `pydantic.ValidationError` (`extra="forbid"` unit test); the value is genuinely frozen — a mutation raises (`ValidationError` or `frozen` error under Pydantic v2).
- [ ] `arbitrary_types_allowed=True` still enforces `frozen` and `extra="forbid"` — an explicit unit test asserts both under that mode (arch §Step 1 risk).
- [ ] `package_managers` returns `tuple(dep_graph_strategies.keys())`; a unit test asserts it tracks the mapping (no second source of truth).
- [ ] `src/codegenie/languages/__init__.py` `__all__` is ≤ 6 names; `import-linter` has a contract for the new `codegenie.languages` package; `make fence` green (no `FORBIDDEN_LLM_SDK` rode in).
- [ ] The TDD red test exists, is committed, and is green; `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files.
- [ ] Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. Ensure `src/codegenie/languages/` exists with `__init__.py`; define `LanguagePack` in `src/codegenie/languages/pack.py` (alongside `DetectionResult`/`ProjectDetector` from S1-03/S1-04).
2. Import the field types: `Language`/`PackageManager` from `codegenie.types.identifiers`, `SupportedLanguage` from `codegenie.grammars.lock`, `Probe` from `codegenie.probes.base`, `DepGraphStrategy` from `codegenie.depgraph.registry`.
3. Declare the model with `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`, the six fields, the discriminator, and the `package_managers` `@property`.
4. Export the package-surface names from `__init__.py` (`LanguagePack` at minimum; ≤ 6 total — leave room for S2-01's `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`).
5. Add an `import-linter` contract for `codegenie.languages` in `pyproject.toml`.
6. Write the red tests; run red, then green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_language_pack.py` (new).

```python
# test_language_pack_rejects_extra_field
#   with pytest.raises(ValidationError):
#       LanguagePack(language=Language("python"), grammars=(...), project_detector=...,
#                    layer_a_probes=(), dep_graph_strategies={}, search_adapter_module="m:C",
#                    bogus_field=1)            # extra="forbid"
#
# test_language_pack_missing_field_raises
#   with pytest.raises(ValidationError):
#       LanguagePack(language=Language("python"))   # five required fields omitted
#
# test_language_pack_is_frozen
#   pack = _valid_pack()
#   with pytest.raises(ValidationError):           # pydantic v2 frozen
#       pack.language = Language("typescript")
#
# test_frozen_and_extra_forbid_hold_under_arbitrary_types_allowed  (Step-1 risk)
#   -- construct a pack carrying a real type[Probe] and a real DepGraphStrategy callable;
#      assert both the frozen mutation AND the extra-field rejection still fire.
#
# test_package_managers_is_derived_property
#   pack = _valid_pack(dep_graph_strategies={PackageManager("pip"): _strategy})
#   assert pack.package_managers == (PackageManager("pip"),)
#   assert "package_managers" not in LanguagePack.model_fields   # NOT a field
```
Use a `_valid_pack()` helper building a complete pack from a stub `ProjectDetector` and stub probe class. Before `pack.py` exists, every import is an `ImportError`.

### Green — make it pass
The Pydantic model exactly as the arch §Data model block specifies — six fields, the discriminator, the `@property`. No validators beyond Pydantic's built-in totality. No registration logic (that is S2-01+).

### Refactor — clean up
Module + field docstrings naming ADR-0001/0003/0006; confirm `tuple`/`Mapping` (not `list`/`dict`) so the frozen value is genuinely immutable; confirm `__all__` discipline; add the `import-linter` contract and run `make lint-imports` + `make fence`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/__init__.py` | new/append — package surface, `__all__` ≤ 6 |
| `src/codegenie/languages/pack.py` | new/append — `LanguagePack` definition |
| `pyproject.toml` | `[[tool.importlinter.contracts]]` for `codegenie.languages` |
| `tests/unit/languages/test_language_pack.py` | new — totality, frozen, extra-forbid, derived-property tests |

## Out of scope
- The `mypy`-must-fail snippet harness (the *compile-time* incompleteness proof) — S1-06.
- `LanguageRegistry` / `register_language` / `validate_pack` — Step 2.
- The contract-snapshot fence (`test_language_pack_contract.py`) — S7-05.
- Constructing `TS_PACK` / `PYTHON_PACK` — S3-02 / S7-01.

## Notes for the implementer
- `arbitrary_types_allowed=True` is **required** — `type[Probe]` and the `DepGraphStrategy` callable are not Pydantic-native. The Step-1 risk (arch) is that this mode might weaken `frozen`/`extra="forbid"` — it does not, but you must *assert* it in a test, not assume it.
- `package_managers` is a `@property` returning `tuple(self.dep_graph_strategies.keys())` — **never** a seventh field. A second field would drift (final-design §Departures item 5). The test must assert it is absent from `model_fields`.
- Reuse `Language` — do **not** mint a `LanguageId` (ADR-0003). Reuse `Probe` and `DepGraphStrategy` unchanged — they are referenced, not redefined.
- Keep `__init__.py` `__all__` ≤ 6 names (arch §Development view: `LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`) — Step 1 ships only `LanguagePack`; reserve the rest.
- `import codegenie.languages` must not import any grammar wheel — `LanguagePack` holds grammar *keys* (the `SupportedLanguage` Literal tuple), not loaded `Language` objects; the wheel loads lazily on first `language_for`.
- The model is `Provisional Accepted` and frozen (ADR-0001) — S7-05's snapshot fence pins it; do not over-build it. Six fields + one discriminator, no speculative seventh.
