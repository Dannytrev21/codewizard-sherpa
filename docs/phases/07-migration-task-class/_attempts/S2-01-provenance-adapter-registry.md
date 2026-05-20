# Attempt log — S2-01 `Layer` + `Ecosystem` enums + `_REGISTRY` + `@register_provenance_adapter`

Append-only. Each entry records one executor pass.

---

## Attempt 1 — 2026-05-19 — GREEN (single pass)

**Executor:** Claude Opus 4.7 via `codewizard-executer` scheduled task.

**Strategy:** Red → Green → Refactor TDD per story §"TDD plan".

### Red

1. Wrote `tests/unit/primitives/vuln_provenance/conftest.py` with the autouse
   `provenance_registry_reset` fixture (function-scoped snapshot/clear/restore
   of `_REGISTRY`).
2. Wrote `tests/unit/primitives/vuln_provenance/test_registry.py` with 12 tests,
   one per acceptance criterion (AC-1 .. AC-12). The canary red test is
   `test_duplicate_registration_raises_registry_error`.
3. Ran the suite — failed with `ImportError: cannot import name 'registry' from
   'codegenie.primitives.vuln_provenance'`. RED confirmed.

### Green — minimal impl

1. Created `src/codegenie/primitives/vuln_provenance/registry.py`:
   - `Layer` + `Ecosystem` `StrEnum` subclasses (codebase convention; arch
     §4 shows `class Layer(str, Enum)` but the codebase already uses
     `StrEnum` for `AdapterConfidence` in `types.py`; UP042 enforces the
     newer form — see "Deviation from arch text" below).
   - `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}`.
   - `register_provenance_adapter(*, layer, ecosystem)` — three lines of
     behavior: collision-check, assign, return.
2. Extended `src/codegenie/primitives/vuln_provenance/errors.py`:
   - Added `RegistryError.key: ProvenanceAdapterId | None = None` typed
     attribute.
   - Added `RegistryError.duplicate(*, key, existing_qualname,
     duplicate_qualname)` classmethod that formats the canonical message
     `"duplicate adapter for {key!r}: {existing} and {duplicate}"` and
     pins the `.key` payload.
3. Extended `src/codegenie/primitives/vuln_provenance/__init__.py` to
   re-export `Layer`, `Ecosystem`, `register_provenance_adapter` (kept
   `_REGISTRY` module-private).
4. All 12 registry tests pass.

### Touched existing fences (expected ADR-amendment-level changes)

S1-04 shipped `RegistryError` as a marker-only `Exception` subclass; S2-01
AC-6 requires a typed `.key` attribute + `duplicate(...)` classmethod for
the plugin loader (S8-03) to render structured diagnostics. Three sibling
fence tests were updated to accommodate the new shape:

| Fence | Update | Why |
|---|---|---|
| `test_types_dunder_all.py::test_public_init_all_is_exact_and_sorted_and_omits_private` | Added `Ecosystem`, `Layer`, `register_provenance_adapter` to `_EXPECTED_PUBLIC_ALL`. | S2-01 AC-10 — new public-surface members. |
| `test_adapter_protocol_shape.py::test_error_class_is_markers_only` | Removed `RegistryError` from the parametrize list; added new `test_registry_error_payload_shape` that locks the new body (docstring + AnnAssign + FunctionDef). | S2-01 AC-6 — `RegistryError` is now a typed-payload error, NOT a marker. The new test pins the exact body shape so any future drift fails loud. |
| `test_protocols_module_purity.py::test_errors_module_imports_are_subset_of_allowlist` | Added `typing` + `codegenie.types.identifiers` to `_ALLOWED_ERRORS_IMPORTS`. | The `ProvenanceAdapterId` type annotation on `.key` is `TYPE_CHECKING`-guarded but the AST scanner picks up the import. |

### Refactor

- Module docstring on `registry.py` cites Phase 7 ADR-0004 / ADR-0006 /
  ADR-0007, names the five-precedent registry pattern, and pins the
  N≥5 rule-of-three deferral observation (no kernel-extract this story).
- `RegistryError.duplicate(...)` docstring names the dual-qualname
  diagnostic and mirrors `codegenie.probes.registry` precedent.
- Inline comment on `_REGISTRY[key] = cls` line: `# CLASS, NOT cls() —
  see ADR-0007 §Decision; BP-3 regression guard`.

### Deviation from arch text — StrEnum vs (str, Enum)

The arch §4 sample code shows `class Layer(str, Enum):`. The codebase
convention (see `primitives/vuln_provenance/types.py:100 AdapterConfidence`)
uses `enum.StrEnum` (Python 3.11+). Ruff UP042 flags `class Layer(str, Enum)`
and recommends `StrEnum`. Per global Rule 11 ("Match the codebase's
conventions, even if you disagree") + Rule 7 ("Surface conflicts — pick the
more recent / more tested"), `StrEnum` is the right call:

- `StrEnum` is **behaviorally identical** to `class Layer(str, Enum)` for
  the load-bearing properties (string equality, JSON serialization, iteration
  order, `tuple(Layer) == (...)`).
- All AC tests pin behavior, not the declaration syntax — they pass under
  both spellings.
- The other `vuln_provenance` enum (`AdapterConfidence`) uses `StrEnum`;
  homogeneity > arch-text fidelity here.

The deviation is recorded; no ADR amendment is required because the
contract surface is unchanged.

### Verification

| Check | Result |
|---|---|
| `pytest tests/unit/primitives/vuln_provenance/test_registry.py` | 12/12 PASSED |
| `pytest tests/unit/primitives/vuln_provenance/` (full) | 174/174 PASSED |
| `ruff check src/codegenie/primitives/vuln_provenance/ tests/unit/primitives/vuln_provenance/` | All checks passed |
| `ruff format --check ...` | 20 files already formatted |
| `mypy --strict src/codegenie/primitives/vuln_provenance/` | Success: no issues found in 6 source files |
| `lint-imports` (5 contracts) | Contracts: 5 kept, 0 broken |
| `pytest tests/unit/test_pyproject_fence.py` | 9/9 PASSED |
| Coverage on `src/codegenie/primitives/vuln_provenance/registry.py` | 100% (28/28 lines) |
| Coverage on `src/codegenie/primitives/vuln_provenance/errors.py` | 100% |

Pre-existing local-only failures unrelated to S2-01:
- `tests/unit/test_lint_imports_canary.py` (2 failures) — `lint-imports`
  console script not on `PATH` outside `.venv`. CI runs with the venv
  active and is green.
- `tests/unit/test_precommit_and_docs_config.py::test_pre_commit_run_all_files_exits_zero`
  — pre-commit hooks not installed in this checkout. Confirmed identical
  state on clean `master` via `git stash`.

### AC checklist — all ✓

- [x] AC-1 — `Layer` enum (APP, BASE_IMAGE, RUNTIME) in declaration order.
- [x] AC-2 — `Ecosystem` enum (NPM, YARN_BERRY, PNPM, APK, DPKG, RPM) in declaration order.
- [x] AC-3 — `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}`.
- [x] AC-4 — Decorator stores the class (identity check), not an instance.
- [x] AC-5 — Decorator returns `cls` unchanged.
- [x] AC-6 — Duplicate key raises `RegistryError` at decoration time; `.key` payload + both qualnames in message.
- [x] AC-7 — No instance construction at decoration time (exploding-`__init__` test green).
- [x] AC-8 — No `isinstance` runtime contract guard (wrong-signature class registers).
- [x] AC-9 — `provenance_registry_reset` autouse fixture in conftest.
- [x] AC-10 — Public surface re-exports `Layer`, `Ecosystem`, `register_provenance_adapter`; `_REGISTRY` is module-private.
- [x] AC-11 — Red test (`test_duplicate_registration_raises_registry_error`) was first failing test; impl makes it green.
- [x] AC-12 — `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports` all clean.

### What's deferred / out of scope (unchanged from story)

- `AdapterFactory` Protocol + DI-aware construction → S2-02.
- `_ADAPTER_DISPATCH_ORDER` + `Ecosystem`-sorted iteration → S2-03.
- `assemble_provenance(...)` free function → S2-04.
- Hypothesis property tests (50 permutations, idempotence) → S2-05.
