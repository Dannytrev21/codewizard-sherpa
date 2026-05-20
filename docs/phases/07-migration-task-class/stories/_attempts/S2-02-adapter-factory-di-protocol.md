# Attempt log: S2-02 — `AdapterFactory` Protocol + DI kwarg vocabulary

## Attempt 1 — 2026-05-19 21:20 — SUCCESS

**Approach:** Straight red-green-refactor. Wrote `test_factory.py` first
(10 tests, one+ per AC), confirmed RED via `ImportError`, then created
`src/codegenie/primitives/vuln_provenance/factory.py` with the
`AdapterFactory` Protocol, `_DI_KWARGS` closed vocabulary,
`DefaultAdapterFactory`, and the `default_adapter_factory` singleton. Wired
the three re-exports into the package `__init__.py` and extended the
`__all__` lock test.

**ReAct cycles:** 1 (no retries needed — story was well-specified).

**What worked:**
- The story's TDD plan was accurate on intent. The provided test code
  needed two mypy-driven adaptations (see Deviations) but the AC coverage
  was complete.
- Fixture adapter classes use `attribute`/`confidence` stubs typed
  `-> Any` (mirrors `test_registry.py`) so they structurally satisfy
  `type[VulnProvenanceAdapter]` at the `factory(...)` call site — the
  `Any` return is what makes `mypy --strict` admit them.
- Recording `__init__` arguments into a closure `dict` instead of
  reading attributes off the factory's `VulnProvenanceAdapter`-typed
  return keeps the assertions mypy-clean (the Protocol has no
  `sbom_reader`/`constructed` attributes) and is mutation-stronger —
  `set(received)` catches a "passes everything" mutant.

**What didn't:** nothing — single clean attempt.

**Root cause:** n/a.

**Lesson for next attempt:** n/a.

**Validator report (Stage 3):**
- AC-1..AC-11: all verified. `test_factory.py` — 10 tests, all green.
- `ruff check` / `ruff format --check`: clean (factory.py, __init__.py,
  test_factory.py, test_types_dunder_all.py).
- `mypy --strict`: clean (factory.py + test_factory.py +
  test_types_dunder_all.py + conftest.py).
- `lint-imports --config pyproject.toml --no-cache`: 5/5 contracts KEPT,
  including "phase-7 primitive does not import LLM SDKs".
- `factory.py` coverage: 100% (21/21 statements).
- Full suite: 6 failed, 5555 passed (was 7 failed / 5541 passed before
  this story + the sibling fence fix). The 6 remaining failures are all
  pre-existing local-environment artifacts unrelated to S2-02, confirmed
  by running them in isolation: `test_lint_imports_canary` (`lint-imports`
  not on the test subprocess `PATH` locally — present on CI via `.[dev]`),
  `test_secret_in_source` ×2 (stale local `.codegenie` scip cache —
  CI uses fresh fixtures), `test_sandbox_exec_*` ×2 (macOS `sandbox-exec`
  substrate — CI Linux uses `bwrap`). No new failures introduced.
- All Phase-7 fences green (`test_phase7_no_llm`,
  `test_no_any_in_provenance_surface`, `test_vuln_provenance_frozen_base`,
  `test_phase7_importlinter_contracts_shape`, `test_per_submodule_cold_start`).

**Final files touched:**
- `src/codegenie/primitives/vuln_provenance/factory.py` — created —
  `AdapterFactory` Protocol, `_DI_KWARGS`, `DefaultAdapterFactory`,
  `default_adapter_factory`.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — modified —
  re-export the three new public names; `__all__` grown additively (sorted).
- `tests/unit/primitives/vuln_provenance/test_factory.py` — created —
  10 mutation-resistant tests, one+ per AC.
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` —
  modified — extended `_EXPECTED_PUBLIC_ALL` (not in the story's "Files to
  touch", but mandatory: it locks `__init__.py.__all__`; S2-01 set the
  same precedent).

**Tests added:**
- `test_default_factory_passes_only_declared_di_kwargs` — AC-10 (RED) + AC-4
- `test_di_kwargs_is_exact_closed_vocabulary` — AC-2
- `test_adapter_factory_protocol_surface` — AC-1
- `test_factory_injects_all_three_closed_vocab_kwargs` — AC-3
- `test_adapter_with_no_kwargs_constructed_cleanly` — AC-5
- `test_adapter_declaring_unknown_kwarg_is_not_passed_it` — AC-6
- `test_default_adapter_factory_module_singleton_works_for_no_kwarg_adapters` — AC-7
- `test_default_adapter_factory_singleton_passes_none_to_required_dep` — AC-7
- `test_runtime_checkable_protocol_smoke` — AC-8
- `test_substitute_factory_satisfies_protocol_via_duck_typing` — AC-9

**Documentation updated:** none beyond the module/class/constant docstrings
in `factory.py` (the story's "Files to touch" named no external docs; the
docstring is the canonical "how to grow the DI vocabulary" reference).

**Deviations from the story spec (surfaced for human review):**
1. **DI parameter types are `object | None`, not `SbomReader | None` /
   `Logger | None` / `ImageManifestCache | None`.** `SbomReader` and
   `ImageManifestCache` do not exist as named types (S1-05 ships the SBOM
   *models*, not a reader abstraction; Phase 2 ADR-0004 ships an
   `image_digest_resolver` *callable*, not an `ImageManifestCache` type).
   The story's AC-3 explicitly permits `object` placeholders for missing
   types, and its Refactor note expects the typing to firm up "when
   S1-05's `SbomReader` shape is stable". `logger` was also typed `object`
   rather than `logging.Logger` — the codebase logs via `structlog`, not
   stdlib `logging`, so `logging.Logger` would be the *wrong* type; the
   factory is a pure pass-through that never invokes any dependency, so
   `object` is the honest interim type for all three. `mypy --strict`
   enforces the real dependency types at each adapter's own `__init__`
   (S3-02+), which is where they are consumed.
2. **`__call__` iterates `_DI_KWARGS` via a dict-comprehension** rather
   than the story outline's three explicit
   `if "x" in declared and "x" in _DI_KWARGS` blocks. Functionally
   identical (each AC still passes), but stronger Open/Closed: the closed
   vocabulary is the *iteration domain*, so a name outside `_DI_KWARGS` is
   structurally unreachable, not merely filtered by a second check.
   Adding a DI kwarg now touches `_DI_KWARGS` + `DefaultAdapterFactory`'s
   constructor/`available` mapping only — `__call__` never changes.

**Follow-ups surfaced this attempt:**
- None. `assemble_provenance` (S2-04) is the consumer of this factory and
  is correctly out of scope.
