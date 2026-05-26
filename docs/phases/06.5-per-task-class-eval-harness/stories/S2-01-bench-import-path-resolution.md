# Story S2-01 — Bench import-path resolution (`load_task_class`)

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (errors — `TaskClassNotFound`, `BenchCaseLoadError`, `TaskClassAlreadyRegistered`; this story adds `BenchRootNotFound`, `TaskClassRegistrationFailed`, `TaskClassRootConflict`, `InvalidTaskClassName`), S1-03 (`TaskClass`, `TaskClassRegistry`, `default_registry`, `@register_task_class`), S1-05 (locked 9-name public surface — this story must not widen it)
**ADRs honored:** ADR-0001 (no in-process rubric import surface), Phase 5 ADR-0006 (Protocol convention upstream of registry)

## Validation notes

Validated: 2026-05-26
Verdict: HARDENED
Findings addressed: 55 total — 14 block, ~30 harden, ~11 nit
Critic reports: Coverage (15), Test-Quality (15), Consistency (12), Design-Patterns (13). No `NEEDS RESEARCH` — every pattern is precedented in this repo.

Conflict resolutions (priority order: Consistency > Coverage > Test-Quality > Design-Patterns):

- **Public-surface seam (F-COV-1 / F-CON-3 / F-CON-10).** Consistency wins. The original AC-1 phrase `codegenie.eval.__init__`'s loader-internal seam' contradicted S1-05 AC-1 (locked `__all__` of exactly 9 names; the tenth fails CI). Rewrote AC-1 to: `load_task_class` is importable from `codegenie.eval.loader` (sub-module path); it is NOT added to `codegenie.eval.__init__.__all__`. Deleted the Files-to-touch row for `src/codegenie/eval/__init__.py`. Removed the invented `loader-internal seam` phrase.
- **Typed-error / exit-code mapping (F-COV-2 / F-TQ-4 / F-CON-4 / F-DP-3).** Consistency wins via High-level-impl.md line 97 exit-code table. Pinned: missing `registration.py` file → `BenchCaseLoadError(case_dir, field="registration.py", reason="file not found")` → CLI exit code 4; `registration.py` ran but did not register `name` → `TaskClassNotFound(name, looked_up_in=..., available_names=...)` → CLI exit code 3; `registration.py` raised during import → new `TaskClassRegistrationFailed(name, cause_type, cause_message)` chained via `raise ... from` → CLI exit code 1 (generic). All three carry machine-readable attributes (not just message text) for the S4-02 CLI exit-code mapping. AC-5 ambiguity ('pick one') is closed.
- **`__all__` placeholder (F-DP-2).** Pinned: `__all__ = ("load_task_class",)` — single-tuple form. S2-02 will add `"load_cases"` when it lands the function. Naming `load_cases` today breaks `from codegenie.eval.loader import *` and `pydoc` introspection.
- **`Depends on` correction (F-CON-7).** Was `S1-02, S1-03`; corrected to `S1-01, S1-03, S1-05`. The implementation outline imports nothing from S1-02 (wire models). Same correction shape S1-03 itself shipped.
- **Fixture directory naming (F-CON-8).** Changed `tests/fixtures/bench/stub_task_class/` (underscore) → `tests/fixtures/bench/stub-task-class/` (hyphen). The hyphen→underscore translation is import-time only; on-disk directory MUST stay hyphenated to match the registered slug (matches arch line 1016, High-level-impl.md line 77).
- **DI `registry=` kwarg (F-DP-4).** Added: `load_task_class(name, bench_root=..., *, registry: TaskClassRegistry | None = None)`. Mirrors `register_task_class(..., registry=...)` in S1-03 and `register_plugin(..., registry=...)` in `plugins/registry.py`. Enables clean test isolation without monkeypatching the module-level `default_registry`.
- **Concrete TDD assertions (F-TQ-1 through F-TQ-15).** Comment-only test stubs rewritten as runnable Python with explicit `assert` / `pytest.raises` / parametrize lines. Identity (`is`), sys.path index (`== 0`) and count (`== 1`), `looked_up_in` attribute, registry-call-count spy, fixture-counter-EXTERNAL-to-module-being-imported (F-TQ-13), and Hypothesis property test for name→module-name translation all pinned.
- **Test isolation (F-TQ-7 / F-CON-9).** Added an autouse `tests/unit/eval/conftest.py` fixture that snapshots+restores `sys.modules` and `sys.path` around each test, plus monkeypatches `default_registry` to a fresh `TaskClassRegistry()`. The loader itself does NOT provide a teardown helper — global-state hygiene is a test-fixture concern.
- **Structural defense for ADR-0001 (F-CON-5 / F-DP-9).** Added `tests/fence/test_eval_loader_no_rubric_import.py` AST-walking `src/codegenie/eval/loader.py` for any `bench.*.rubric` reference. Pinned as AC; mirrors `tests/fence/_phase4_scanner.py` precedent.
- **`name` validation (F-COV-6).** Pinned regex `^[a-z][a-z0-9-]*[a-z0-9]$` (lowercase alphanumeric + hyphen; must start with letter, must not end with hyphen, min length 2). Rejects `""`, `"a"`, `"-foo"`, `"foo-"`, `"Foo"`, `"foo/bar"`, `"foo.bar"`, `"../etc/passwd"`, `"registration"`, `"_internal"`. New `InvalidTaskClassName(name, reason)` typed exit, raised BEFORE any sys.path or import side effect.
- **Different bench_root same name (F-COV-5).** Pinned: second call with same `name` but different resolved `bench_root` raises `TaskClassRootConflict(name, first_root, second_root)`. Mechanism: module-level `_loaded: dict[str, Path]` tracks the resolved bench_root per name; second call with mismatching resolved path raises before any import.
- **Registered-different-name (F-COV-11 / F-DP-8).** Pinned: snapshot `default_registry`'s name set before/after the import; the diff feeds `TaskClassNotFound(name, looked_up_in=..., available_names=tuple(sorted(diff)))`. Surfaces the typo case cheaply — piggy-backs on S1-03 AC-11's `available_names` contract.
- **Resolved module path verification (F-COV-4).** Pinned: AC asserts `sys.modules[f"bench.{module_name}.registration"].__file__` equals `(bench_root / name / "registration.py").resolve().as_posix()`.
- **Structured-log events (F-COV-12 / F-CON-11 / F-DP-10).** Pinned three event IDs (all matching the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` convention): `loader.task_class_loaded` (first-load success), `loader.task_class_cache_hit` (second call), and per-failure-path warnings/errors (`loader.registration_file_missing`, `loader.task_class_not_registered_after_import`, `loader.registration_import_failed`, `loader.bench_root_not_found`, `loader.task_class_root_conflict`, `loader.invalid_task_class_name`).
- **Surfaced doc drift (no auto-edit).** `final-design.md §loader.py` line 186/289 still says `vuln_remediation.registration` (no `bench.` prefix) — stale wording; phase-arch-design.md Gap 2 Option A is canonical. `phase-arch-design.md` line 1159 incorrectly says "bench/ becomes a `__init__.py`-bearing implicit namespace package" — PEP 420 implicit namespace packages have NO `__init__.py`. `phase-arch-design.md` line 866 says "registry rejects duplicates" but S1-03 made the registry RAISE on duplicate; the actual no-op mechanism is `sys.modules` caching preventing module-body re-execution. All three are flagged for a doc-sweep follow-on, not auto-fixed.
- **Design endorsements deferred (Rule 2 — no premature abstraction).** `TaskClassName` newtype (F-DP-1): deferred to identifier-consolidation work, per S1-03 precedent. `slugify_taskclass_name` helper (F-DP-5): only one consumer today (this loader); fence-CI walks the filesystem directly. `LoaderProtocol` (F-DP-7): three downstream consumers exist on paper but none need an injected fake yet; trigger is "first test that wants an in-memory fake loader". Context-manager `sys.path` shape (F-DP-6): prepend-and-leave is correct for short-lived CLI; a context manager would break `sys.modules` caching that AC-3 depends on. All four surfaced in Notes-for-implementer as explicit deferrals with their trigger conditions.

Full audit log: `_validation/S2-01-bench-import-path-resolution.md`

## Context

The synthesis docs hand-wave `_codegenie_bench.{name}.registration` (`final-design.md §Components → loader.py`); `bench/` lives at repo root and isn't inside `src/codegenie/`, so the import does not resolve as written. `phase-arch-design.md §Gap analysis & improvements §Gap 2` picks **Option A**: prepend the parent of `bench/` to `sys.path` and import `bench.{name}.registration` directly (no synthesized prefix), so `bench/` becomes a PEP 420 implicit namespace package (no `__init__.py`). This story implements that contract — the first concrete loader entry point, with the side-effect import that triggers `@register_task_class("<name>")` exactly once and returns the resolved `TaskClass`.

The loader is *internal scaffolding*: it lives at `codegenie.eval.loader`, is callable from `Runner.plan()` / `audit verify` / `PromotionGate`, but is NOT added to `codegenie.eval.__init__.__all__` (S1-05 locks that surface at 9 names).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/loader.py` (line 556) — public-interface signatures (`load_task_class`, `load_cases`); side-effect-import idempotence note
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 2` (line 1153) — full rationale for Option A vs MetaPathFinder; the OQ #3 fallback if packaging conflicts surface
  - `../phase-arch-design.md §Control flow` (line 826, Happy path narrative) — the `Runner.plan()` call site that invokes `load_task_class`
  - `../phase-arch-design.md §Failure modes` (lines 944–963) — typed-exception mapping for case-load + task-class failures
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — loader must never import `bench/{name}/rubric.py`; only `registration.py` is in-process
- **Source design:**
  - `../final-design.md §Components → loader.py` (line 182) — original (hand-wavy) statement of the import target; stale wording flagged in Validation notes
- **High-level-impl:**
  - `../High-level-impl.md §Step 2` (line 48) — loader scope; Step 4 line 97 — CLI exit-code partitioning that this story's typed exits feed.
- **Existing code (registered by sibling stories):**
  - `src/codegenie/eval/registry.py` (S1-03) — `default_registry`, `@register_task_class`; the side-effect target
  - `src/codegenie/eval/models.py` (S1-02) — `TaskClass` shape (NOT directly imported by this story, but the return type)
  - `src/codegenie/eval/errors.py` (S1-01) — `TaskClassNotFound`, `TaskClassAlreadyRegistered`, `BenchCaseLoadError` (this story adds four new typed errors — see Implementation outline)
  - `src/codegenie/eval/__init__.py` (S1-05) — locked 9-name `__all__` surface; this story does NOT widen it
- **Precedents in this repo:**
  - `src/codegenie/probes/__init__.py` — explicit-imports collection point (S1-05 precedent for the eval package shape)
  - `src/codegenie/probes/registry.py:139-158` — caller-frame origin capture for collision diagnostics
  - `src/codegenie/plugins/registry.py:189-202` — `register_plugin(plugin, *, registry=None)` DI kwarg pattern (mirrored by this story's `registry=` kwarg)
  - `tests/fence/_phase4_scanner.py:walk_imports` — single AST-kernel for `tests/fence/` walks (reused by F-CON-5 / F-DP-9 fence test)
  - `docs/phases/06.5-per-task-class-eval-harness/stories/_validation/S1-03-*.md` — sibling validation discipline (registry-shape, immutability normalization, `Final` discipline)

## Goal

`codegenie.eval.loader.load_task_class(name, bench_root, *, registry=None)` resolves `bench/{name}/registration.py` via `sys.path` prep (Option A), triggers `@register_task_class` exactly once via `importlib.import_module(f"bench.{module_name}.registration")`, and returns the registered `TaskClass`. Second call with the same `(name, bench_root)` returns the cached `TaskClass` without re-executing the module body (no `TaskClassAlreadyRegistered` raised). Six typed failure modes (name validation, bench-root missing, registration-file missing, registration-import-raised, registration-did-not-register-name, bench-root-conflict-across-calls) carry machine-readable attributes that S4-02's CLI maps to exit codes 1/3/4 per High-level-impl.md Step 4.

## Acceptance criteria

- [ ] **AC-1 (public-surface seam):** `load_task_class(name: str, bench_root: Path = Path("bench"), *, registry: TaskClassRegistry | None = None) -> TaskClass` is importable as `from codegenie.eval.loader import load_task_class` (sub-module path). It is NOT added to `codegenie.eval.__init__.__all__` — S1-05's locked 9-name public surface remains unchanged. A fence test asserts `"load_task_class" not in codegenie.eval.__all__` to prevent accidental promotion.
- [ ] **AC-2 (module-level `__all__`):** `codegenie.eval.loader.__all__ == ("load_task_class",)` — a single-element tuple. `"load_cases"` is NOT listed (S2-02 adds it). Test pins the exact tuple via `assert codegenie.eval.loader.__all__ == ("load_task_class",)`. Rationale: naming `load_cases` today breaks `from codegenie.eval.loader import *` until S2-02 lands.
- [ ] **AC-3 (name validation, fail-fast):** `load_task_class(name, ...)` validates `name` against `re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")` BEFORE any `sys.path` mutation, `importlib` call, or filesystem stat. Invalid input raises `InvalidTaskClassName(name, reason)` with `reason ∈ {"empty", "too short", "wrong case", "leading hyphen", "trailing hyphen", "non-slug character", "reserved name"}`. Parametrized test covers: `""` (empty), `"a"` (too short), `"-foo"` (leading hyphen), `"foo-"` (trailing hyphen), `"Foo"` (uppercase), `"foo/bar"` (slash), `"foo.bar"` (dot), `"../etc/passwd"` (path traversal), `"registration"` (would shadow the submodule), `"_internal"` (leading underscore), `123` (non-str) → `TypeError`, `None` → `TypeError`, `b"foo"` (bytes) → `TypeError`.
- [ ] **AC-4 (bench-root validation):** If `bench_root` does not exist or is not a directory, raise `BenchRootNotFound(bench_root=bench_root.resolve())` BEFORE any sys.path mutation or import. Test covers: nonexistent path, regular file masquerading as bench_root, broken symlink.
- [ ] **AC-5 (first-call side effect runs exactly once):** On the first `load_task_class(name, bench_root)` call: (a) `bench/{name}/registration.py`'s module body executes exactly once — verified by an EXTERNAL counter (a file under `tmp_path / "side_effects.txt"` that `registration.py` appends to; the counter MUST NOT live in the imported module's namespace because `importlib.reload` would silently reset it — see F-TQ-13). (b) `sys.path[0] == str(bench_root.resolve().parent)` (parent-of-bench prepended, NOT bench itself); (c) the resolved entry appears in `sys.path` exactly once (`sys.path.count(...) == 1`); (d) `sys.modules[f"bench.{module_name}.registration"]` is set; (e) `sys.modules[f"bench.{module_name}.registration"].__file__ == (bench_root / name / "registration.py").resolve().as_posix()` — pins the resolved module identity, prevents accidental wrong-module import.
- [ ] **AC-6 (second-call cache hit, no re-execution, no duplicate-registration raise):** On the second `load_task_class(name, bench_root)` call with the same `(name, resolved bench_root)`: (a) the external counter is unchanged (module body did not re-run); (b) `TaskClassAlreadyRegistered` is NOT raised (the test wraps the second call in `try/except` and asserts `pytest.fail` if raised) — guards the path that arch line 866 hand-waves as "registry rejects duplicates" but which actually relies on `sys.modules` caching preventing decorator re-firing; (c) `result_first is result_second` (identity, not equality); (d) `result_first is registry.get(name)` (the registry, not the wrapper, is the source of truth); (e) `sys.path.count(str(bench_root.resolve().parent)) == 1` (no growth); (f) a `loader.task_class_cache_hit` structlog event is emitted (distinct from the first-call `loader.task_class_loaded`).
- [ ] **AC-7 (different bench_root, same name → conflict):** `load_task_class("foo", root_A)` then `load_task_class("foo", root_B)` with `root_A.resolve() != root_B.resolve()` raises `TaskClassRootConflict(name="foo", first_root=root_A.resolve(), second_root=root_B.resolve())` — does NOT silently return the first root's TaskClass (a load-bearing footgun for `--bench-root` CLI flag tests). Mechanism: module-level `_loaded: dict[str, Path]` tracks resolved bench_root per name; second call with mismatching resolved path raises BEFORE any sys.path or import.
- [ ] **AC-8 (different bench_root, different name → both work):** `load_task_class("foo", root_A)` then `load_task_class("bar", root_B)` (different names AND different roots) both succeed; both parent-of-bench entries appear in `sys.path` exactly once each; `result_foo is registry.get("foo")` and `result_bar is registry.get("bar")` both hold.
- [ ] **AC-9 (hyphen → underscore translation, parametrized):** Parametrized over `("foo", "foo")`, `("vuln-remediation", "vuln_remediation")`, `("migration-chainguard-distroless", "migration_chainguard_distroless")`, `("a-b-c-d-e", "a_b_c_d_e")`. For each `(name, expected_module)`: `sys.modules[f"bench.{expected_module}.registration"]` exists after the call AND `sys.modules.get(f"bench.{name}.registration")` is None (i.e., the original hyphenated form was NOT used as a module key). Property-based test (Hypothesis or hand-rolled): for any `name` matching the AC-3 regex, `module_name = name.replace("-", "_")` AND `module_name.isidentifier()`.
- [ ] **AC-10 (missing `registration.py` file → typed exit, CLI exit code 4):** If `bench/{name}/registration.py` does not exist, raise `BenchCaseLoadError(case_dir=bench_root.resolve() / name, field="registration.py", reason="file not found")`. Asserted via attribute access (NOT message regex): `assert exc.case_dir == bench_root.resolve() / name`; `assert exc.field == "registration.py"`; `assert exc.reason == "file not found"`. Distinct test from "directory `bench/{name}/` itself missing" (handled identically — both surface as `ModuleNotFoundError` on the top-level `bench.{module}.registration` import; both produce `BenchCaseLoadError`).
- [ ] **AC-11 (`registration.py` imports but does not register `name` → typed exit, CLI exit code 3):** If `importlib.import_module(...)` succeeds but `name` is absent from `registry` after the import, raise `TaskClassNotFound(name, looked_up_in=f"bench.{module_name}.registration", available_names=tuple(sorted(<delta of registry names before vs after import>)))`. Mechanism: snapshot `set(registry._by_name.keys())` before the import, recompute after, take the symmetric difference. Tests: (a) `registration.py` with no decorator call at all → `available_names == ()`; (b) `registration.py` with `@register_task_class("typo")` → `available_names == ("typo",)`. Asserted via attribute access: `assert exc.name == "vuln-remediation"`; `assert exc.looked_up_in == "bench.vuln_remediation.registration"`; `assert exc.available_names == ("typo",)`.
- [ ] **AC-12 (`registration.py` raises during import → typed exit, CLI exit code 1):** If the `registration.py` module body raises any exception (SyntaxError, transitive ImportError of a sibling module, arbitrary RuntimeError), raise `TaskClassRegistrationFailed(name, cause_type=type(e).__name__, cause_message=str(e)[:200])` chained via `raise ... from e`. A `ModuleNotFoundError` whose `.name == f"bench.{module_name}.registration"` is the missing-file case (AC-10); a `ModuleNotFoundError` whose `.name` is a *transitive* missing dep is classified as `TaskClassRegistrationFailed` (AC-12). Tests: (a) `registration.py` with `raise RuntimeError("boom")` → `exc.cause_type == "RuntimeError"`, `exc.cause_message == "boom"`, `exc.__cause__` is the original `RuntimeError`; (b) `registration.py` with `import nonexistent_module` → `exc.cause_type == "ModuleNotFoundError"`, `exc.cause_message.startswith("No module named 'nonexistent_module'")`.
- [ ] **AC-13 (symlinked `bench_root` resolves identically):** Given `tmp_path/real/bench/foo/registration.py` and a symlink `tmp_path/link → tmp_path/real`, `load_task_class("foo", tmp_path/real/bench)` and `load_task_class("foo", tmp_path/link/bench)` produce the same `TaskClass` identity AND `sys.path.count(str((tmp_path/real).resolve())) == 1` (no double-import under two paths). Mechanism: the loader resolves `bench_root.resolve().parent` before any sys.path mutation or `_loaded` lookup.
- [ ] **AC-14 (relative vs absolute `bench_root` equivalence):** Both `load_task_class("foo", Path("bench"))` (relative, CWD-dependent) and `load_task_class("foo", tmp_path / "bench")` (absolute) produce the same module identity and the same `sys.modules` key. The resolved-absolute-string is what lands on `sys.path`; the input form does not change the cache key.
- [ ] **AC-15 (machine-readable exception attributes on all six typed exits):** Each of `InvalidTaskClassName`, `BenchRootNotFound`, `BenchCaseLoadError`, `TaskClassNotFound`, `TaskClassRegistrationFailed`, `TaskClassRootConflict` exposes its diagnostic fields as named attributes (not just `.args[i]`). The CLI in S4-02 maps these to exit codes by `isinstance(exc, …)` + `exc.<field>`. Test asserts attribute access for each.
- [ ] **AC-16 (DI registry= kwarg):** `load_task_class("foo", root, registry=fresh_registry)` registers into `fresh_registry` and reads back from it. The module-level `default_registry` is not touched. Mirrors the DI pattern in S1-03 (`register_task_class(..., registry=...)`) and `plugins/registry.py:189-202` (`register_plugin(..., registry=...)`). When `registry is None`, falls back to `codegenie.eval.registry.default_registry`. Test exercises both paths.
- [ ] **AC-17 (sys.path mutation is bounded — idempotent insert):** Repeated `load_task_class` calls do not grow `sys.path`. After N=5 calls with the same `(name, bench_root)`, `sys.path.count(str(bench_root.resolve().parent)) == 1` AND `sys.path[0] == str(bench_root.resolve().parent)`.
- [ ] **AC-18 (registry-side side-effect verification — INTENT, Rule 9):** The `@register_task_class` side effect must actually fire on the registry. Test: `before = set(registry.all_task_classes()); result = load_task_class("foo", root, registry=registry); after = set(registry.all_task_classes()); assert after - before == {result}; assert result is registry.get("foo")`. Guards a mutant impl that builds and returns a `TaskClass` directly without calling the decorator (the registry would stay empty, but a behavior-only test would pass).
- [ ] **AC-19 (structured-log events on success and every failure path):** Success path emits exactly one `structlog.info` event `loader.task_class_loaded` with `name=<name>`, `bench_root=<resolved-absolute>`, `module=<f"bench.{module_name}.registration">`. Cache-hit emits `loader.task_class_cache_hit` with the same keys. Each failure path emits exactly one `structlog.error` (or `warn`) with a distinct event ID matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`: `loader.invalid_task_class_name`, `loader.bench_root_not_found`, `loader.registration_file_missing`, `loader.task_class_not_registered_after_import`, `loader.registration_import_failed`, `loader.task_class_root_conflict`. Test uses `structlog.testing.capture_logs()` to assert event-ID + key attribute presence.
- [ ] **AC-20 (concurrency contract — caller-serialized):** The loader docstring documents that concurrent `load_task_class` calls within a single process are NOT supported — the caller (`Runner.plan()`) must serialize. The loader does NOT acquire any threading lock. Phase 16 may revisit if multi-task-class concurrent loads land. Test: this is a documentation AC; the docstring contains the literal substring `caller-serialized` and `Runner.plan` (verified via `inspect.getdoc(load_task_class)` substring assertion).
- [ ] **AC-21 (ADR-0001 structural defense — fence test):** `tests/fence/test_eval_loader_no_rubric_import.py` AST-walks `src/codegenie/eval/loader.py` via the shared `walk_imports` kernel (`tests/fence/_phase4_scanner.py`) and asserts: (a) no `Import` / `ImportFrom` node references any module path containing the substring `rubric`; (b) no `importlib.import_module(...)` literal argument contains the substring `rubric` (extracted via `ast.Constant` walk). Fence test runs on every PR. Mirrors `tests/fence/test_pyproject_fence_phase4.py` precedent.
- [ ] **AC-22 (test isolation autouse fixture):** `tests/unit/eval/conftest.py` provides an autouse fixture that (a) snapshots `sys.path` and `dict(sys.modules)` on entry; (b) yields control to the test; (c) restores `sys.path` from snapshot and removes any new `bench.*` keys from `sys.modules` on exit; (d) monkeypatches `codegenie.eval.registry.default_registry` to a fresh `TaskClassRegistry()` for the duration of the test. Loader tests run in arbitrary order without cross-contamination.
- [ ] **AC-23 (typecheck + lint clean):** `ruff format --check`, `ruff check`, and `mypy --strict` are clean on `src/codegenie/eval/loader.py`, `src/codegenie/eval/errors.py` (new exception classes), and the test file. All new exception classes carry `@dataclass(frozen=True)` semantics or explicit `__init__` storing the diagnostic fields as instance attributes.
- [ ] **AC-24 (TDD red→green transition):** The full red test suite (every AC above with at least one runnable test) is committed in a single commit BEFORE any production code lands, with a passing import of `codegenie.eval.loader` blocked (because the module does not yet exist). The green commit implements the loader; all tests pass.

## Implementation outline

1. **Add four new typed errors to `src/codegenie/eval/errors.py`** (S1-01 amendment via additive surface):
   - `BenchRootNotFound(bench_root: Path)` — exit code 4.
   - `InvalidTaskClassName(name: object, reason: str)` — exit code 1 (validation error; `name` typed `object` to accept the `123`/`None` bad-arg cases without coercion).
   - `TaskClassRegistrationFailed(name: str, cause_type: str, cause_message: str)` — exit code 1.
   - `TaskClassRootConflict(name: str, first_root: Path, second_root: Path)` — exit code 1.
   All four expose their fields as named instance attributes (not just `.args`).
2. **Create `src/codegenie/eval/loader.py`** with module docstring quoting Gap #2 Option A, the `caller-serialized` concurrency contract, and the `Runner.plan` call-site reference.
3. **Module-level state:** `_loaded: dict[str, Path] = {}` — tracks the resolved bench_root per name (drives AC-7 conflict detection). `_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")`. `__all__ = ("load_task_class",)`.
4. **Pure helpers (functional core):**
   - `_validate_name(name: object) -> str` — raises `TypeError` for non-str, `InvalidTaskClassName` for regex/reserved-name failures, otherwise returns the validated `str`.
   - `_translate(name: str) -> str` — `name.replace("-", "_")`. Pure; one line.
5. **Impure helper (imperative shell):**
   - `_prep_bench_sys_path(bench_root_parent: Path) -> None` — `bench_root_parent` is already `bench_root.resolve().parent`. Inserts at `sys.path[0]` only if missing. No return.
6. **Implement `load_task_class(name, bench_root=Path("bench"), *, registry=None) -> TaskClass`:**
   1. `name = _validate_name(name)` (AC-3 — fail-fast BEFORE any I/O).
   2. `registry = registry or default_registry`.
   3. `bench_root_resolved = bench_root.resolve()`.
   4. If `not bench_root_resolved.is_dir()`: `structlog.error("loader.bench_root_not_found", ...)`; raise `BenchRootNotFound(bench_root_resolved)`.
   5. AC-7 conflict check: `if name in _loaded and _loaded[name] != bench_root_resolved:` raise `TaskClassRootConflict(name, _loaded[name], bench_root_resolved)`.
   6. AC-6 cache-hit short-circuit: `if name in _loaded:` `structlog.info("loader.task_class_cache_hit", ...)`; return `registry.get(name)`.
   7. `_prep_bench_sys_path(bench_root_resolved.parent)`.
   8. `module_name = _translate(name)`.
   9. Snapshot `before_names = set(registry.all_names())` (or whatever the S1-03 accessor is — use the public accessor, NOT `_by_name`).
   10. Try `importlib.import_module(f"bench.{module_name}.registration")`:
       - On `ModuleNotFoundError` whose `.name == f"bench.{module_name}.registration"`: emit `loader.registration_file_missing`; raise `BenchCaseLoadError(bench_root_resolved / name, "registration.py", "file not found")` chained via `from e`.
       - On any other exception `e`: emit `loader.registration_import_failed`; raise `TaskClassRegistrationFailed(name, type(e).__name__, str(e)[:200])` from `e`.
   11. AC-11 post-import check: `after_names = set(registry.all_names())`; `delta = tuple(sorted(after_names - before_names))`; if `name not in after_names`: emit `loader.task_class_not_registered_after_import`; raise `TaskClassNotFound(name, looked_up_in=f"bench.{module_name}.registration", available_names=delta)`.
   12. `_loaded[name] = bench_root_resolved`.
   13. emit `loader.task_class_loaded`; return `registry.get(name)`.
7. **NOT touched:** `src/codegenie/eval/__init__.py` — S1-05's `__all__` stays locked at 9 names. The loader is reached via `codegenie.eval.loader.load_task_class`.

## TDD plan — red / green / refactor

### Red — test files

- `tests/unit/eval/conftest.py` (new) — autouse `_isolate_eval_globals` fixture (AC-22).
- `tests/unit/eval/test_loader_import_path.py` (new) — ACs 1–20, 23–24.
- `tests/unit/eval/test_loader_errors.py` (new) — AC-3, 4, 7, 10, 11, 12 (every failure path; attribute-shape assertions).
- `tests/fence/test_eval_loader_no_rubric_import.py` (new) — AC-21.
- `tests/fixtures/bench/stub-task-class/registration.py` (new — hyphen NOT underscore; AC-9 + F-CON-8).
- `tests/unit/eval/_bench_factory.py` (new helper — builds parameterized `bench/<name>/registration.py` trees under `tmp_path`; reusable by S3-01 per F-TQ-14).

### Sample concrete tests (NOT comment-only stubs)

```python
# tests/unit/eval/_bench_factory.py
from pathlib import Path
import textwrap

def make_bench(
    tmp_path: Path,
    *,
    name: str = "stub-task-class",
    register_name: str | None = None,  # None → use `name`; "" → omit decorator
    side_effect_log: Path | None = None,
    body_raises: str | None = None,
) -> Path:
    """Builds bench/<name>/registration.py under tmp_path. Returns bench_root."""
    bench_root = tmp_path / "bench"
    pkg_dir = bench_root / name.replace("-", "_")
    pkg_dir.mkdir(parents=True, exist_ok=True)
    register_call = (
        ""
        if register_name == ""
        else f'@register_task_class({register_name or name!r}, ...)'  # ... filled in by caller via S1-03 kwargs
    )
    body = textwrap.dedent(f"""
        from pathlib import Path
        from codegenie.eval.registry import register_task_class
        {f"Path({str(side_effect_log)!r}).open('a').write('x\\n')" if side_effect_log else ""}
        {f"raise {body_raises}" if body_raises else ""}
        {register_call}
        class StubRubric: ...
    """)
    (pkg_dir / "registration.py").write_text(body)
    return bench_root
```

```python
# tests/unit/eval/test_loader_import_path.py
import sys
import pytest
from pathlib import Path
from codegenie.eval.loader import load_task_class
from codegenie.eval.registry import TaskClassRegistry
from ._bench_factory import make_bench

def test_first_call_runs_module_body_exactly_once_with_external_counter(tmp_path):
    log = tmp_path / "side_effects.txt"
    bench_root = make_bench(tmp_path, name="stub-task-class", side_effect_log=log)
    registry = TaskClassRegistry()

    result1 = load_task_class("stub-task-class", bench_root, registry=registry)
    assert log.read_text().count("x\n") == 1  # AC-5(a)

    result2 = load_task_class("stub-task-class", bench_root, registry=registry)
    assert log.read_text().count("x\n") == 1  # AC-6(a) — body did NOT re-run
    assert result1 is result2                  # AC-6(c) — identity, not equality
    assert result1 is registry.get("stub-task-class")  # AC-6(d) — registry is source of truth

def test_sys_path_prepend_is_idempotent_at_index_zero(tmp_path):
    bench_root = make_bench(tmp_path, name="stub-task-class")
    registry = TaskClassRegistry()

    for _ in range(5):
        load_task_class("stub-task-class", bench_root, registry=registry)

    expected = str(bench_root.resolve().parent)
    assert sys.path[0] == expected                # AC-5(b), AC-17
    assert sys.path.count(expected) == 1          # AC-5(c), AC-17

def test_resolved_module_file_matches_registration_path(tmp_path):
    bench_root = make_bench(tmp_path, name="stub-task-class")
    load_task_class("stub-task-class", bench_root, registry=TaskClassRegistry())

    mod = sys.modules["bench.stub_task_class.registration"]   # AC-5(d)
    expected = (bench_root / "stub-task-class" / "registration.py").resolve().as_posix()
    assert Path(mod.__file__).resolve().as_posix() == expected  # AC-5(e), AC-4 (COV-4)

@pytest.mark.parametrize("name, module", [
    ("foo", "foo"),
    ("vuln-remediation", "vuln_remediation"),
    ("migration-chainguard-distroless", "migration_chainguard_distroless"),
    ("a-b-c-d-e", "a_b_c_d_e"),
])
def test_hyphen_to_underscore_translation_parametrized(tmp_path, name, module):
    bench_root = make_bench(tmp_path, name=name)
    load_task_class(name, bench_root, registry=TaskClassRegistry())

    assert f"bench.{module}.registration" in sys.modules  # AC-9
    assert sys.modules.get(f"bench.{name}.registration") is None  # the hyphen form must NOT be a key

def test_second_call_with_different_bench_root_raises_root_conflict(tmp_path):
    root_a = make_bench(tmp_path / "a", name="foo")
    root_b = make_bench(tmp_path / "b", name="foo")
    registry = TaskClassRegistry()
    load_task_class("foo", root_a, registry=registry)

    with pytest.raises(TaskClassRootConflict) as exc:
        load_task_class("foo", root_b, registry=registry)
    assert exc.value.name == "foo"               # AC-7
    assert exc.value.first_root == root_a.resolve()
    assert exc.value.second_root == root_b.resolve()

def test_intent_side_effect_fires_on_registry(tmp_path):
    # Rule 9 / AC-18: verifies INTENT (decorator fired) not just behavior (TaskClass returned).
    bench_root = make_bench(tmp_path, name="stub-task-class")
    registry = TaskClassRegistry()
    before = set(registry.all_task_classes())
    result = load_task_class("stub-task-class", bench_root, registry=registry)
    after = set(registry.all_task_classes())
    assert after - before == {result}            # AC-18
    assert result is registry.get("stub-task-class")
```

```python
# tests/unit/eval/test_loader_errors.py
import pytest
from codegenie.eval.errors import (
    BenchCaseLoadError, BenchRootNotFound, InvalidTaskClassName,
    TaskClassNotFound, TaskClassRegistrationFailed,
)
from codegenie.eval.loader import load_task_class
from codegenie.eval.registry import TaskClassRegistry
from ._bench_factory import make_bench

@pytest.mark.parametrize("bad", ["", "a", "-foo", "foo-", "Foo", "foo/bar", "foo.bar", "../etc", "_internal", "registration"])
def test_invalid_name_raises_typed(tmp_path, bad):
    with pytest.raises(InvalidTaskClassName) as exc:
        load_task_class(bad, tmp_path, registry=TaskClassRegistry())
    assert exc.value.name == bad  # AC-3, AC-15

@pytest.mark.parametrize("bad", [123, None, b"foo", ["foo"], 1.5])
def test_non_str_name_raises_typeerror(tmp_path, bad):
    with pytest.raises(TypeError):
        load_task_class(bad, tmp_path, registry=TaskClassRegistry())  # AC-3

def test_missing_bench_root_raises_typed(tmp_path):
    with pytest.raises(BenchRootNotFound) as exc:
        load_task_class("foo", tmp_path / "nonexistent", registry=TaskClassRegistry())
    assert exc.value.bench_root == (tmp_path / "nonexistent").resolve()  # AC-4

def test_missing_registration_file_raises_bench_case_load_error(tmp_path):
    bench_root = tmp_path / "bench"
    (bench_root / "foo").mkdir(parents=True)  # directory exists but no registration.py
    with pytest.raises(BenchCaseLoadError) as exc:
        load_task_class("foo", bench_root, registry=TaskClassRegistry())
    assert exc.value.case_dir == (bench_root / "foo").resolve()  # AC-10, AC-15
    assert exc.value.field == "registration.py"
    assert exc.value.reason == "file not found"

def test_registration_imports_but_doesnt_register_name_raises_typed(tmp_path):
    bench_root = make_bench(tmp_path, name="foo", register_name="")  # no decorator at all
    with pytest.raises(TaskClassNotFound) as exc:
        load_task_class("foo", bench_root, registry=TaskClassRegistry())
    assert exc.value.name == "foo"            # AC-11, AC-15
    assert exc.value.looked_up_in == "bench.foo.registration"
    assert exc.value.available_names == ()

def test_registration_registers_typo_name_surfaces_in_available_names(tmp_path):
    bench_root = make_bench(tmp_path, name="vuln-remediation", register_name="typo")
    with pytest.raises(TaskClassNotFound) as exc:
        load_task_class("vuln-remediation", bench_root, registry=TaskClassRegistry())
    assert exc.value.available_names == ("typo",)  # AC-11 + F-DP-8

def test_registration_raises_at_import_time_classified(tmp_path):
    bench_root = make_bench(tmp_path, name="foo", body_raises='RuntimeError("boom")')
    with pytest.raises(TaskClassRegistrationFailed) as exc:
        load_task_class("foo", bench_root, registry=TaskClassRegistry())
    assert exc.value.cause_type == "RuntimeError"  # AC-12, AC-15
    assert "boom" in exc.value.cause_message
    assert isinstance(exc.__cause__, RuntimeError) or isinstance(exc.value.__cause__, RuntimeError)
```

```python
# tests/fence/test_eval_loader_no_rubric_import.py
import ast
from pathlib import Path
from tests.fence._phase4_scanner import walk_imports  # reused AST kernel

LOADER = Path("src/codegenie/eval/loader.py")

def test_loader_does_not_import_rubric():
    src = LOADER.read_text()
    tree = ast.parse(src)
    for imp in walk_imports(tree):
        assert "rubric" not in imp.module_path  # AC-21
    # also walk all importlib.import_module(...) literal args
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert "rubric" not in arg.value
```

### Green — smallest impl

The seven-step body in §Implementation outline §6, plus the four typed-error additions to `errors.py` (~30 lines total) and the autouse conftest fixture (~15 lines). Total ~80 lines of code + ~150 lines of test.

### Refactor

- Add Sphinx-style docstrings to `load_task_class`, `_validate_name`, `_translate`, `_prep_bench_sys_path` quoting Gap #2 Option A and the `caller-serialized` concurrency contract.
- Inline-comment the hyphen→underscore translation as the ONE place we cross the slug/module-name boundary (F-DP-5 deferral).
- Ensure every structlog event ID matches the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` regex; add a module-level `_LOG_EVENTS: Final[frozenset[str]]` collection for self-documentation (not enforced, just discoverable).
- Run `mypy --strict` on the module; ensure `Path`, `dict[str, Path]`, `re.Pattern[str]`, `TaskClassRegistry | None` all typecheck cleanly.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/loader.py` | New module — Option A `sys.path` prep + `load_task_class` |
| `src/codegenie/eval/errors.py` | Add `BenchRootNotFound`, `InvalidTaskClassName`, `TaskClassRegistrationFailed`, `TaskClassRootConflict` (additive — S1-01 surface widening) |
| `tests/unit/eval/conftest.py` | Autouse fixture for `sys.modules` + `sys.path` + `default_registry` isolation (AC-22) |
| `tests/unit/eval/test_loader_import_path.py` | Red tests for happy paths + caching + AC-5..AC-9, AC-13..AC-20 |
| `tests/unit/eval/test_loader_errors.py` | Red tests for the six typed exits (AC-3, 4, 7, 10, 11, 12) |
| `tests/unit/eval/_bench_factory.py` | Helper builder for `bench/<name>/registration.py` trees (replaces hard-coded fixture; F-TQ-14) |
| `tests/fence/test_eval_loader_no_rubric_import.py` | Fence test for ADR-0001 (AC-21) |
| `tests/fixtures/bench/stub-task-class/registration.py` | Minimal hyphen-named fixture; reused by S3-01 runner story (F-CON-8) |

**NOT touched:** `src/codegenie/eval/__init__.py` — S1-05's 9-name `__all__` lock stands.

## Out of scope

- **Case loading and digest verification** — handled by S2-02 (`load_cases`).
- **MetaPathFinder fallback (Option B)** — surfaces only if Option A causes packaging conflicts in CI; tracked as OQ #3.
- **Bench-root discovery from CWD** — caller passes `bench_root`; auto-discovery is a CLI concern (S4-01/S4-02). The `Path("bench")` default is a test-convenience only; production callers MUST pass `bench_root` explicitly.
- **`TaskClassName` newtype extraction** — deferred per S1-03's identifier-consolidation precedent. Revisit when Phase 7 ships the second task class.
- **`slugify_taskclass_name(name)` helper extract** — deferred until a second consumer materializes (fence-CI walks the filesystem directly, not the slug→module-name translation). Rule of three not crossed.
- **`LoaderProtocol` extraction** — deferred until the first consumer needs to inject a fake loader (likely Phase 7 multi-task-class runner tests).
- **Context-manager `sys.path` shape** — prepend-and-leave is correct for the short-lived CLI and matches AC-3's `sys.modules`-caching dependency.
- **Threading lock for concurrent calls** — deferred; caller-serialized contract documented in AC-20. Phase 16 may revisit.
- **Doc-sweep for stale `final-design.md` line 186/289 and `phase-arch-design.md` line 866, 1159 wording** — flagged in Validation notes; spawn-task candidate, not a blocker for this story.

## Notes for the implementer

- `bench/` does **not** need `__init__.py` — implicit namespace packages (PEP 420) work as long as the parent dir is on `sys.path`. `phase-arch-design.md` line 1159's wording (`__init__.py`-bearing implicit namespace package) is internally contradictory; this story implements the no-`__init__.py` form.
- **ADR-0001 hard line:** Don't import `bench/{name}/rubric.py` from anywhere reachable here, transitively or otherwise. The decorator's `rubric_class` kwarg captures a *class object* (data), not an import path; the runner (S3-01) reaches the rubric via a subprocess only. AC-21's fence test is the structural defense.
- **Test fixture name is hyphenated** (`tests/fixtures/bench/stub-task-class/`); the underscore form (`stub_task_class`) only exists as the on-the-fly translated module name inside `sys.modules`. This matches the registered slug convention across `bench/vuln-remediation/`, `bench/migration-chainguard-distroless/`, etc.
- `name.replace("-", "_")` is the ONLY place in `src/codegenie/eval/` that crosses between user-facing slug and Python module name. Fence-CI (S7-01 assertion #1) walks `bench/<hyphenated-slug>/` directly — it does NOT do this translation. Keep them separate; if a third consumer materializes (curators-CLI scaffolder, S5-07), extract `slugify_taskclass_name(name)` to `codegenie.eval.naming` then.
- **`sys.path` mutation is intentionally prepend-and-leave**, not a context manager. A context manager would force `importlib.invalidate_caches()` on every call and break the `sys.modules` cache that AC-6 depends on. Rule of three not crossed.
- **Test isolation:** every test that calls `load_task_class` MUST use the autouse fixture in `tests/unit/eval/conftest.py`. The loader does NOT provide a teardown helper — `sys.path`/`sys.modules`/`default_registry` hygiene is a test-fixture concern, mirroring S1-03's discipline (no mutation of singleton private state).
- **The loader READS `default_registry` (when `registry=None`) but never MUTATES it directly.** Registration is the side effect of `importlib.import_module(...)` running `@register_task_class(...)`. Do NOT touch `default_registry._by_name` from the loader — same discipline S1-03 enforces.
- **`default_registry: Final[TaskClassRegistry]`** is locked by S1-03 AC-4a. The loader uses `from codegenie.eval.registry import default_registry` (read-only access via the `Final` annotation); mypy `--strict` blocks any accidental reassignment.
- **Functional core / imperative shell:** `_validate_name` and `_translate` are pure; `_prep_bench_sys_path` and `importlib.import_module` are impure. Don't blend them. A future refactor wrapping the impure surface in a `_load_module(name, bench_root)` private helper is welcome; inlining I/O into the pure helpers is not.
- **The `Path("bench")` default** is a test convenience; production callers MUST pass `bench_root` explicitly (CLI resolves it in S4-02). If a future refactor surfaces CWD-coupling, drop the default to a required kwarg.
- **Caller-serialized concurrency.** `Runner.plan()` is async but the loader contract is single-threaded: callers must serialize. The docstring documents this; the loader does not acquire any threading lock. (Verified by AC-20.)
- **Phase 0's `codegenie/probes/` registry pattern (`@register_probe`)** is the closest precedent overall; the difference is `bench/` lives outside `src/codegenie/`, which is exactly what Gap #2 calls out. `plugins/registry.py:189-202`'s `register_plugin(..., registry=...)` is the closest precedent for the DI kwarg shape adopted in AC-16.
