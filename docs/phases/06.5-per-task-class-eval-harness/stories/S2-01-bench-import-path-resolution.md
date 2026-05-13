# Story S2-01 — Bench import-path resolution (`load_task_class`)

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready
**Effort:** S
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-0001 (no in-process rubric import surface), Phase 5 ADR-0006 (Protocol convention upstream of registry)

## Context

The synthesis docs hand-wave `_codegenie_bench.{name}.registration` (`final-design.md §Components → loader.py`); `bench/` lives at repo root and isn't inside `src/codegenie/`, so the import does not resolve as written. `phase-arch-design.md §Gap analysis & improvements §Gap 2` picks **Option A**: prepend the parent of `bench/` to `sys.path` and import `bench.{name}.registration` directly (no synthesized prefix), so `bench/` becomes an implicit namespace package. This story implements that contract — the first concrete loader entry point, with the side-effect import that triggers `@register_task_class("<name>")` exactly once and returns the resolved `TaskClass`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/loader.py` — public-interface signatures (`load_task_class`, `load_cases`); side-effect-import idempotence note
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 2` — full rationale for Option A vs MetaPathFinder; the OQ #3 fallback if packaging conflicts surface
  - `../phase-arch-design.md §Control flow` (Happy path narrative) — the `Runner.plan()` call site that invokes `load_task_class`
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — loader must never import `bench/{name}/rubric.py`; only `registration.py` is in-process
- **Source design:**
  - `../final-design.md §Components → loader.py` — original (hand-wavy) statement of the import target
- **Existing code:**
  - `src/codegenie/eval/registry.py` (S1-03) — `default_registry`, `@register_task_class`; the side-effect target
  - `src/codegenie/eval/models.py` (S1-02) — `TaskClass` shape returned to the caller
  - `src/codegenie/eval/errors.py` (S1-01) — `TaskClassNotFound`, `TaskClassAlreadyRegistered`

## Goal

`codegenie.eval.loader.load_task_class(name, bench_root)` resolves `bench/{name}/registration.py` via `sys.path` prep (Option A), triggers `@register_task_class` exactly once, and returns the registered `TaskClass`; second call with the same name is a no-op that returns the same instance.

## Acceptance criteria

- [ ] `load_task_class(name: str, bench_root: Path = Path("bench")) -> TaskClass` is importable from `codegenie.eval.loader` and exported by `codegenie.eval.__init__`'s loader-internal seam (loader is internal scaffolding; the function itself is not in the ≤9 public-name list).
- [ ] On first call, `load_task_class("vuln-remediation", tmp_bench_root)` runs `bench/vuln-remediation/registration.py`'s module body exactly once (verified by an assertion-counter side-effect in the fixture's registration), inserting the parent of `bench_root` to `sys.path[0]` if not already present and removing it from `sys.modules` cleanup is **not** required (idempotence on the registry side handles re-runs).
- [ ] On second call with the same `(name, bench_root)`, no module re-execution occurs (`importlib.import_module` returns the cached module from `sys.modules`); the function still returns the same `TaskClass` instance from `default_registry`.
- [ ] If the registration import succeeds but does not register `name`, raise `TaskClassNotFound(name, looked_up_in="bench.<name>.registration")` — guards against a `registration.py` typo where the decorator argument doesn't match the directory name.
- [ ] If `bench/{name}/registration.py` does not exist, raise `BenchCaseLoadError(case_dir=bench_root / name, field="registration.py", reason="file not found")` (or `TaskClassNotFound` — pick one and document; test asserts the chosen typed exit).
- [ ] Hyphenated task-class names (`migration-chainguard-distroless`) work: the loader translates the directory name to its Python-import-safe form (`migration_chainguard_distroless`) for `bench.{module}.registration` resolution, while the registered task-class string stays hyphenated.
- [ ] `sys.path` mutation is bounded: the parent-of-`bench_root` entry is inserted only if missing; repeated `load_task_class` calls do not grow `sys.path` (idempotent insert).
- [ ] TDD red test exists, is committed, and passes green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean on `src/codegenie/eval/loader.py` and the test file.

## Implementation outline

1. Create `src/codegenie/eval/loader.py` with module-level docstring naming Option A from Gap #2.
2. Implement a private `_prep_bench_sys_path(bench_root: Path) -> None` that resolves `bench_root.parent.resolve()`, inserts it at `sys.path[0]` if not already present, and returns nothing.
3. Implement `load_task_class(name: str, bench_root: Path = Path("bench")) -> TaskClass`:
   - Call `_prep_bench_sys_path(bench_root)`.
   - Translate `name` → `module_name = name.replace("-", "_")`.
   - `importlib.import_module(f"bench.{module_name}.registration")` (catch `ModuleNotFoundError` → raise the chosen typed error).
   - Look up `name` (the original hyphenated form) in `default_registry`; if missing, raise `TaskClassNotFound`.
   - Return the `TaskClass`.
4. Add a `__all__ = ("load_task_class", "load_cases")` placeholder (S2-02 adds `load_cases`).

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_loader_import_path.py`

```python
def test_load_task_class_triggers_registration_exactly_once(tmp_path, monkeypatch):
    # Arrange: build a fake bench/ at tmp_path/bench/<name>/registration.py
    # whose module body increments a counter and decorates a TaskClass.
    # Act: call load_task_class twice.
    # Assert:
    #   - counter == 1 after first call (module body ran)
    #   - counter == 1 after second call (sys.modules cached)
    #   - both returned values are the same object (identity)
    ...

def test_load_task_class_hyphen_to_underscore_translation(tmp_path):
    # name="migration-chainguard-distroless" must import
    # bench.migration_chainguard_distroless.registration
    ...

def test_load_task_class_missing_registration_raises_typed(tmp_path):
    # bench/<name>/ exists but no registration.py → typed error (TaskClassNotFound or BenchCaseLoadError)
    ...

def test_load_task_class_registration_doesnt_register_name(tmp_path):
    # registration.py imports but never calls @register_task_class("<name>")
    # → TaskClassNotFound(name, looked_up_in=...)
    ...

def test_sys_path_insert_is_idempotent(tmp_path):
    # Two load_task_class calls do not grow sys.path.
    ...
```

### Green

Smallest impl: the four steps in §Implementation outline; ~25 lines of code.

### Refactor

- Add type hints and a docstring quoting Gap #2's Option A decision.
- Inline-comment the hyphen-to-underscore translation (load-bearing for `migration-chainguard-distroless`).
- Add a structlog `info` event `loader.task_class_loaded` with `name` and `bench_root` attributes for traceability (matches Phase 0's logging convention).
- Defensive: catch a bare `ImportError` from `import_module` and surface a typed error chained via `raise ... from`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/loader.py` | New module — Option A `sys.path` prep + `load_task_class` |
| `src/codegenie/eval/__init__.py` | Add internal-seam re-export if needed for tests (`load_task_class` is internal — loader is scaffolding) |
| `tests/unit/eval/test_loader_import_path.py` | Red tests for import-path resolution |
| `tests/fixtures/bench/stub_task_class/registration.py` | Counter-fixture registration used by tests |

## Out of scope

- **Case loading and digest verification** — handled by S2-02 (`load_cases`).
- **MetaPathFinder fallback (Option B)** — surfaces only if Option A causes packaging conflicts in CI; tracked as OQ #3.
- **Bench-root discovery from CWD** — caller passes `bench_root`; auto-discovery is a CLI concern (S4-01/S4-02).

## Notes for the implementer

- `bench/` does **not** need `__init__.py` — implicit namespace packages (PEP 420) work for our case as long as the parent dir is on `sys.path`.
- Don't import `bench/{name}/rubric.py` from anywhere reachable here — ADR-0001 says the rubric is subprocess-only, even though `registration.py` may *reference* the rubric path.
- The fixture in `tests/fixtures/bench/stub_task_class/` doubles as a sanity check for Option A; keep it minimal so Step 3's runner can reuse it.
- If `bench_root.parent.resolve()` differs from `bench_root.parent` (symlinks), prefer the resolved form for `sys.path` — avoids "imported twice under different names" subtlety.
- `name.replace("-", "_")` is the only place we cross between the user-facing slug and Python's module name; surface this clearly so future curators don't accidentally use underscores in `@register_task_class("...")`.
- Phase 0's `codegenie/probes/` registry pattern (`@register_probe`) is the closest precedent; the difference is `bench/` lives outside `src/codegenie/`, which is exactly what Gap #2 calls out.
