# Story S7-01 — Construct `PYTHON_PACK` and register it via `packs/__init__`

**Step:** Step 7 — Land the `tests/conformance/` tier and the `LanguagePack` contract-snapshot fence
**Status:** Ready
**Effort:** M
**Depends on:** S3-04, S4-08, S5-04, S6-03
**ADRs honored:** ADR-0001, ADR-0002, ADR-0003, ADR-0005, ADR-0006

## Context
Steps 4–6 built every Python capability — the four Layer A/B probes, the three dep-graph strategies, the `tree-sitter-python` grammar row, the search adapter, and the `(vuln, python, pip)` plugin — as loose files registered into the existing decomposed registries. This story is the convergence point: it constructs the single frozen `LanguagePack` value that *is* Python (`probes_self_registered=False`), calls `register_language(PYTHON_PACK)`, and wires its module into the explicit-import `packs/__init__.py` collection point so Python becomes the second member of `default_language_registry` — the prerequisite for the conformance tier auto-enrolling it.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack` — the six required fields + `probes_self_registered`; `package_managers` is a derived `@property`, never a field.
- **Architecture:** `../phase-arch-design.md §Process view — runtime behavior` — the `register_language(PY_PACK)` sequence: `validate_pack` runs *all* checks, build-then-publish, then the Python-only probe + strategy fan-out.
- **Architecture:** `../phase-arch-design.md §Development view` — `packs/python.py` carries `PYTHON_PACK` + the `register_language` call; `packs/__init__.py` adds `import .python` after `import .typescript`.
- **Architecture:** `../phase-arch-design.md §Control flow` — the `python` pack module fans `PythonProjectProbe`/`PythonBuildSystemProbe`/`PythonManifestProbe`/`PythonImportGraphProbe` and the `pip`/`poetry`/`uv` strategies.
- **Phase ADRs:** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — an incomplete `LanguagePack(...)` is a `mypy --strict` error; all six capabilities are required fields.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — `register_language` validates everything before any write; a `probes_self_registered=False` pack fans probes out.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — future *new* languages ship `probes_self_registered=False`; only the TS retrofit is `True`.
- **Existing code:** `src/codegenie/languages/packs/__init__.py` (S3-01) — the explicit-import collection point; add `import .python` here.
- **Existing code:** `src/codegenie/languages/packs/typescript.py` (S3-02) — the precedent: a fully enumerated pack + a `register_language(...)` call at module scope.
- **Existing code:** `src/codegenie/probes/python/` (S4-02..S4-07), `src/codegenie/depgraph/python/` (S5-02..S5-04), the Python `ProjectDetector` (S4-03), the search adapter module (S6-01/S6-03) — the references `PYTHON_PACK`'s fields point at.

## Goal
Construct the complete frozen `PYTHON_PACK` value, register it with `register_language(PYTHON_PACK)`, and add `import .python` to `packs/__init__.py` so `default_language_registry.all()` returns both TypeScript and Python.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and was observed failing before `packs/python.py` existed.
- [ ] `PYTHON_PACK` is a `LanguagePack` with all six capability fields explicitly enumerated — `language=Language("python")`, `grammars`, `project_detector` (the real S4-03 detector), `layer_a_probes` (the Python probe classes), `dep_graph_strategies` (`pip`/`poetry`/`uv`), `search_adapter_module` (`"module:ClassName"`) — and `probes_self_registered=False`.
- [ ] Importing `codegenie.languages.packs` (or `.python`) calls `register_language(PYTHON_PACK)`; afterward `default_language_registry.get(Language("python")) == PYTHON_PACK` and `default_language_registry.all()` contains both packs sorted by `Language`.
- [ ] The fan-out actually happened: each `PYTHON_PACK.layer_a_probes` probe is present in `default_probe_registry` and each `PackageManager` in `dep_graph_strategies` resolves in `DepGraphRegistry` — asserted as *dispatchable*, not merely "a key exists" (Rule 9).
- [ ] `PYTHON_PACK.grammars` ⊆ `grammars.lock.supported_languages()` (validated by `validate_pack`; no un-wired key).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on all touched files; `make fence` and `import-linter` stay green.

## Implementation outline
1. Create `src/codegenie/languages/packs/python.py`.
2. Import the concrete capability references: the Python `ProjectDetector` (S4-03), the four Python probe classes (S4-02/04/05/07), and the `pip`/`poetry`/`uv` `DepGraphStrategy` callables (S5-02..S5-04).
3. Construct `PYTHON_PACK = LanguagePack(language=Language("python"), grammars=("python",), project_detector=..., layer_a_probes=(...), dep_graph_strategies={...}, search_adapter_module="codegenie...:PythonImportGraphAdapter", probes_self_registered=False)`.
4. Call `register_language(PYTHON_PACK)` at module scope (mirroring `typescript.py`).
5. Add `import codegenie.languages.packs.python  # noqa: F401` (or the relative form) to `packs/__init__.py`, after the TypeScript import line.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_python_pack.py`.
- `test_python_pack_registers_and_is_complete` — importing `codegenie.languages.packs` enrolls Python; `default_language_registry.get(Language("python"))` returns a `LanguagePack` with all six fields populated and `probes_self_registered is False`.
```python
def test_python_pack_registers_and_is_complete() -> None:
    # arrange: import the collection point (fires register_language at import time)
    import codegenie.languages.packs  # noqa: F401
    from codegenie.languages import default_language_registry
    from codegenie.types.identifiers import Language
    # act
    pack = default_language_registry.get(Language("python"))
    # assert: every capability field is a real reference, not None / empty
    assert pack.probes_self_registered is False
    assert pack.layer_a_probes and pack.dep_graph_strategies
    # intent: a stub pack with empty tuples would fail here, not just type-check
```
- A second case `test_python_probes_are_dispatchable` asserts every `pack.layer_a_probes` probe is in `default_probe_registry` and each `PackageManager` key resolves in `DepGraphRegistry`. Both fail until `packs/python.py` exists and is imported.

### Green — make it pass
Write `packs/python.py` enumerating `PYTHON_PACK` against the real S4–S6 deliverables and calling `register_language`. Add the `import .python` line to `packs/__init__.py`. The minimum is a faithful enumeration — no speculative fields, no helper builder.

### Refactor — clean up
Add a module docstring naming the pack as `LanguagePack` #2 and the S7-01 / ADR-0001 / ADR-0006 lineage. Confirm `grammars` is a `tuple` and `dep_graph_strategies` a plain dict literal (Pydantic coerces to a `Mapping`). Verify `register_language` is called exactly once at module scope. Keep the file structurally identical to `typescript.py` minus `probes_self_registered`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/packs/python.py` | New — `PYTHON_PACK` value + `register_language(PYTHON_PACK)` call. |
| `src/codegenie/languages/packs/__init__.py` | Loud `+1` import line — `import .python` after `import .typescript`. |
| `tests/unit/languages/test_python_pack.py` | New — the registration + dispatchability tests. |

## Out of scope
- The `tests/conformance/` tier itself — S7-02.
- The `EXPECTED_LANGUAGE_COUNT` completeness guard — S7-02.
- Golden fixtures for Python — S7-04.
- Any edit to `register_language` / `validate_pack` behavior — frozen by Step 2.

## Notes for the implementer
- `PYTHON_PACK.layer_a_probes` is *fanned out* (`probes_self_registered=False`) — unlike `TS_PACK`. If a probe is also auto-`@register_probe`'d at its own module import, the fan-out would double-register and raise `ProbeError`; Python probes must rely on the pack fan-out, *not* a module-level `@register_probe`. Verify which mechanism S4 used and ensure exactly one registration path.
- A mid-fan-out crash (probe 3 of 5) leaves the probe registry partly written (edge case #12) — this is contained import-time fail-fast, not a bug to "fix" with rollback. Do not add a rollback.
- `register_language` is idempotent per `Language` (S2-05) — re-importing `packs.python` is a no-op; tests can import freely.
- `search_adapter_module` is a `"module:ClassName"` string — `validate_pack` (S2-02) resolves it; a typo'd path raises `LanguageRegistryError` at import. Point it at the real S6-01/S6-03 adapter class.
- `grammars` is `tuple[SupportedLanguage, ...]` — `"python"` must already be a `SupportedLanguage` Literal member (S1-01) and a wired `_DISPATCH` row (S4-01), or `validate_pack` fails.
