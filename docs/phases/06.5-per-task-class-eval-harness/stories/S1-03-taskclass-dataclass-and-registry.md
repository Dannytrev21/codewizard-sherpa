# Story S1-03 — TaskClass dataclass + registry

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (errors), S1-04 (Rubric Protocol)
**ADRs honored:** ADR-0004 (per-task-class `failure_mode_taxonomy`), ADR-0008 (per-task-class `breakdown_keys`), Phase 5 ADR-0003 (open-registry-via-decorator pattern reused), Phase 5 ADR-0006 (Protocol vs ABC — Rubric is `Protocol`)

## Validation notes

Validated: 2026-05-26
Verdict: HARDENED
Findings addressed: 18 total — 3 blocks, 12 hardens, 3 nits

Changes applied:
- **Depends on:** corrected from `S1-02, S1-04` to `S1-01, S1-04` — the implementation outline imports `TaskClassAlreadyRegistered`/`TaskClassNotFound` from S1-01 and `Rubric` from S1-04; `S1-02` (wire models) is **not** imported by `registry.py` (the original line was stale) (Consistency F-CON-3).
- **AC list renumbered** from 9 unnumbered checkboxes to 17 explicit AC-N entries (AC-1..AC-11 + AC-3a/AC-4a/AC-6a/AC-7a/AC-9a/AC-11a inserted in-line so semantic grouping survives). The originals are preserved; new ACs close gaps the original list left implicit.
- **AC-6 (collision message) hardened (block):** Original AC asserted only that both class names appear in a stringified message. A regression that drops the module path (so a collision message reads `FirstRubric and SecondRubric` instead of `bench.foo.FirstRubric and bench.bar.SecondRubric`) would silently pass — and an operator grepping a multi-bench tree has no way to find either file. Tightened to require introspecting `exc.value.args` directly as a 3-tuple `(name, existing_origin, incoming_origin)` where each origin is `module.qualname` (the format the three sibling registries — `transforms/signal_kinds.py:71-75`, `plugins/registry.py:117-121`, `probes/registry.py:154-158` — all use). Coverage F-COV-2 + Test-Quality F-TQ-1/F-TQ-2 + Consistency F-CON-1 + Design-Patterns F-DP-1 converged.
- **AC-6a added (block):** Origin-tracking is the **kernel-discipline** shared with three sibling registries (Rule of three crossed). The registry stores `_origins: dict[str, str]` alongside `_by_name`; origins are captured from the caller frame (`inspect.currentframe().f_back`) at decoration time so the collision error names both registration call sites even when the `rubric_class` itself doesn't carry module information (e.g., a class object reassigned via `import as`). Mirrors `transforms/signal_kinds.py:125-145` and `plugins/registry.py:117-123` precedents *exactly*. Design-Patterns F-DP-1.
- **AC-7 hardened + AC-7a added (block):** Original tested only `register_task_class(123, ...)`. A `bytes`/`None`/`list`/non-class-callable argument all need to fail. Hardened AC-7 parameterizes the bad-name set + adds whitespace-padded names (fence-CI #4 catches non-literal-`name` at PR time, but a literal `"  foo  "` would silently mismatch the bench directory slug — runtime defense complements fence-CI). AC-7a covers the **non-class decorator target** (a function decorated by `@register_task_class(...)` must raise `TypeError`, mirroring `probes/registry.py:139-145`'s shape). Test-Quality F-TQ-5 + Design-Patterns F-DP-10.
- **AC-8 added (block):** Direct `reg.register(tc)` call (no decorator) must also collision-detect. The original tests only exercise the decorator path; a regression that puts the collision check only inside `register_task_class` (the decorator helper) but not inside `TaskClassRegistry.register` would slip — every consumer that calls `register()` directly (the loader will, after constructing a `TaskClass` from disk) would silently overwrite. Test-Quality F-TQ-7.
- **AC-9 added (harden):** Immutability normalization — `breakdown_keys` MUST be stored as `frozenset` (not `set`) and `failure_mode_taxonomy` MUST be stored as a read-only Mapping (`types.MappingProxyType`). A caller passing `breakdown_keys=set(...)` or `failure_mode_taxonomy={...}` (a plain `dict`) could otherwise mutate shared state across registry consumers; the `@dataclass(frozen=True)` decorator blocks **attribute** reassignment but does not deep-freeze **container** contents. Typed-at-the-edge pattern. Design-Patterns F-DP-5.
- **AC-9a added (harden):** `default_registry: Final[TaskClassRegistry]`. The `Final` annotation is load-bearing — `plugins/registry.py:172` documents it explicitly ("replacement requires explicit DI through `register_plugin(..., registry=...)`"). A regression dropping `Final` would let tests reassign the module-level singleton, undoing the per-test-isolation discipline. mypy-enforced; AC pins the annotation. Design-Patterns F-DP-3.
- **AC-10 hardened (harden):** `TaskClassRegistry.all_task_classes()` returns a **`tuple`** (not list), sorted by `name`. Original AC said "tuple sorted by name" but no test asserted `isinstance(..., tuple)`; a `list[TaskClass]` regression with deterministic sort would pass. Test pins `isinstance(reg.all_task_classes(), tuple)` + the sort. Test-Quality F-TQ-12.
- **AC-11 added (harden):** `TaskClassNotFound(name, available_names)`: `available_names` is a `tuple[str, ...]` **sorted alphabetically** (not insertion-ordered). Original AC-3 said "for diagnosability" but didn't pin sort. Without sort, the error message text is non-deterministic across PRs; `_lessons.md`-style flake. Design-Patterns F-DP-6 + Test-Quality F-TQ-3.
- **AC-11a added (harden):** Registry state is consistent after a failed (collision) registration — the existing entry is still retrievable by `get(name)`, and `all_task_classes()` count is unchanged. Guards a partial-write regression where the registry mutates `_by_name` *before* the collision check, leaves bad state, then raises. Test-Quality F-TQ-8.
- **Re-registration of identical class still raises (no idempotent path):** AC-7a covers the non-class case; an explicit test in §TDD plan covers "same class registered twice raises again" — mirrors `signal_kinds.py`'s explicit "there is no idempotent path — every duplicate raises, regardless of caller" (signal_kinds.py:95-97). Design-Patterns + Test-Quality F-TQ-11.
- **Implementation outline tightened:** decorator now (a) introspects caller frame for `module.qualname` origin, (b) normalizes `breakdown_keys → frozenset`, (c) normalizes `failure_mode_taxonomy → MappingProxyType(dict(...))`, (d) validates `isinstance(rubric_class, type)`, (e) validates `name == name.strip() and name != ""` (raises `ValueError`). `default_registry` declared `Final[TaskClassRegistry]`. Internal `_origins: dict[str, str]` added.
- **Notes for implementer rewrite:** the "tests clear `default_registry._by_name`" guidance was an **anti-pattern** (touches private state of the default singleton, brittle across imports, contradicts the three sibling registries' discipline). Rewrote: tests use `TaskClassRegistry()` for isolation **only**; if a test must verify the default registration path, it uses `monkeypatch.setattr(codegenie.eval.registry, "default_registry", TaskClassRegistry())` to swap in a fresh, not mutate `_by_name`. Design-Patterns F-DP-8.
- **Surfaced arch divergence (no edit to arch):** `phase-arch-design.md §Component design → registry.py` public-interface block (lines 509-514) shows the decorator with only **3** kwargs (`bench_path`, `min_cases_for_promotion`, plus `name`); this story widens to **5** kwargs by passing `breakdown_keys` + `failure_mode_taxonomy` explicitly (the loader does the disk read, decorator stays side-effect-free). The arch's line 523 hand-waves "Decorator captures the rubric class, reads sibling `breakdown_keys.py` … via `loader.py` helpers" — the story's design **inverts** the read direction (loader reads, then calls decorator with kwargs) for a cleaner separation (decoration is O(1); disk I/O is the loader's job, S2-01). Documented in Notes for implementer; arch sharpening is deliberate, not a contradiction. Flagged for a future doc-sweep PR but no auto-edit. Consistency F-CON-2.
- **Out of scope expanded:** explicit deferrals added for (a) `breakdown_keys` substring ban (fence-CI #5 + S7-01), (b) `failure_mode_taxonomy` severity Literal closure (fence-CI #6 + S2-01 loader), (c) `min_cases_for_promotion` positive-integer bound (semantic; S2-01 loader), (d) `TaskClassName` newtype (future identifier-consolidation work).
- **Design-pattern endorsements (no edit, surfaced in Notes for implementer):** registry pattern (Rule of three — 4th register-helper-backed registry; **do not extract a shared base** today, per `signal_kinds.py:16-29` explicit YAGNI); Open/Closed at the decorator boundary; functional-core/imperative-shell (decorator is O(1), pure; loader does I/O); dependency inversion (registry depends on nothing in the loader; loader feeds the registry); typed-at-the-edge for immutability normalization.

No `NEEDS RESEARCH` items — every pattern is precedented in this repo (`transforms/signal_kinds.py`, `plugins/registry.py`, `probes/registry.py`).

Full audit log: `_validation/S1-03-taskclass-dataclass-and-registry.md`

## Context

Task classes are the only extension point an autonomous Phase 7 implementer touches: a new task class is `@register_task_class("…") class MyRubric: …` plus a sibling `bench/<name>/` directory. The registry must reject duplicate names with both qualnames in the message (so a contributor sees *which* file is doing the second registration), must store the canonical `TaskClass` record carrying `breakdown_keys: frozenset[str]` (ADR-0008) and `failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]` (ADR-0004), and must expose a fresh-instance constructor (`TaskClassRegistry()`) so tests can isolate. The decorator's *first positional argument must be an `ast.Constant[str]`* — that constraint is enforced statically by fence-CI (S7-01 assertion #4), but the runtime registry must still accept the registration.

This story plants the registry skeleton without doing any disk I/O (no `breakdown_keys.py` import, no `failure_modes.yaml` parse — those are loader concerns, S2-01/S2-02). The runtime can accept pre-computed `breakdown_keys`/`failure_mode_taxonomy` via decorator kwargs in tests, and the loader (S2-01) will populate them from disk at production load time.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/registry.py` — public interface (decorator signature, `TaskClassRegistry.register/get/all_task_classes`, `default_registry`), collision-raises-with-both-qualnames discipline, fail-loud at import time.
  - `../phase-arch-design.md §Data model — TaskClass` — `@dataclass(frozen=True, slots=True)` carrying `name`, `bench_path`, `min_cases_for_promotion`, `rubric_class`, `breakdown_keys`, `failure_mode_taxonomy`.
  - `../phase-arch-design.md §Edge cases #7, #8` — name collision and "registered but no `bench/<name>/`" failure modes (the second is a fence-CI concern, not a runtime registry concern; this story owns the first).
- **Phase ADRs:**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — `failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]` lives on `TaskClass`; loader populates from `bench/<name>/failure_modes.yaml`.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — `breakdown_keys: frozenset[str]` lives on `TaskClass`; loader populates from `bench/<name>/breakdown_keys.py`'s `StrEnum`.
- **Production / cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — mirrors the open-registry-via-decorator pattern; `SignalKindAlreadyRegistered` is the exact precedent for `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)`.
  - `../../00-bullet-tracer-foundations/stories/` — Phase 0 `probe_registry` precedent for "fresh registry in tests via `Registry()` constructor; module-level singleton for production".
- **This phase, earlier stories:**
  - S1-01 — provides `TaskClassNotFound`, `TaskClassAlreadyRegistered`.
  - S1-02 — provides nothing this story imports directly (models.py and registry.py are independent), but `TaskClass.rubric_class: type[Rubric]` references S1-04's Protocol.
  - S1-04 — provides `Rubric` Protocol; this story's `@register_task_class` decorates classes typed `type[Rubric]`.

## Goal

Land `src/codegenie/eval/registry.py` exposing `@register_task_class(name, *, bench_path, min_cases_for_promotion, breakdown_keys, failure_mode_taxonomy)`, `TaskClassRegistry`, `default_registry`, and `TaskClass` (`@dataclass(frozen=True, slots=True)`) — duplicate-name registrations raise `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)`.

## Acceptance criteria

- [ ] AC-1: `src/codegenie/eval/registry.py` exists; `from codegenie.eval.registry import TaskClass, TaskClassRegistry, default_registry, register_task_class` succeeds.
- [ ] AC-2: `TaskClass` is `@dataclass(frozen=True, slots=True)` with the six fields per `../phase-arch-design.md §Data model`: `name: str`, `bench_path: Path`, `min_cases_for_promotion: Mapping[str, int]`, `rubric_class: type[Rubric]`, `breakdown_keys: frozenset[str]`, `failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]`. Test pins `frozen=True` (assignment raises `FrozenInstanceError`) **and** `slots=True` (`not hasattr(tc, "__dict__")`); the six field set is pinned via `dataclasses.fields(TaskClass)` introspection (so a future PR adding a 7th field fails this AC without an ADR amendment).
- [ ] AC-3: `TaskClassRegistry.register(tc)` adds the entry and returns the same `tc` instance (`is`, not `==`); `TaskClassRegistry.get(name)` returns the registered entry or raises `TaskClassNotFound(name, available_names)`.
- [ ] AC-3a: `TaskClassRegistry.all_task_classes()` returns a **`tuple`** (not list), sorted by `name`. Test pins `isinstance(reg.all_task_classes(), tuple)` *and* the alphabetical sort *and* `len(...)` equals the number of registrations (the cardinality check rejects a regression that silently de-duplicates).
- [ ] AC-4: `default_registry` is a module-level singleton **of type `TaskClassRegistry`**; `register_task_class(...)` without a `registry=` kwarg writes into it (verified by a test that swaps in a fresh via `monkeypatch.setattr(codegenie.eval.registry, "default_registry", TaskClassRegistry())` — see Notes for implementer for *why* the test does not mutate the real singleton).
- [ ] AC-4a: `default_registry` is declared `Final[TaskClassRegistry]` at module scope (precedent: `plugins/registry.py:172`). Tests instantiate `TaskClassRegistry()` for isolation; the `Final` annotation is verified by `mypy --strict` (a reassignment `default_registry = TaskClassRegistry()` elsewhere in the package would fail typecheck). A runtime `typing.get_type_hints(codegenie.eval.registry).get("default_registry")` introspection check confirms the `Final` is present.
- [ ] AC-5: `@register_task_class("foo", bench_path=..., min_cases_for_promotion={"bronze": 10}, breakdown_keys=frozenset({"k"}), failure_mode_taxonomy={"c": "block"}, registry=reg)` decorates a class and registers it; the decorator **returns the class unmodified** (`decorated_cls is OriginalClass`). The decorator does not wrap, subclass, or otherwise transform the rubric class.
- [ ] AC-6: A second registration with the same `name` raises `TaskClassAlreadyRegistered`; `exc.value.args` is exactly a **3-tuple** `(name, existing_origin, incoming_origin)`. Both `existing_origin` and `incoming_origin` are **`module.qualname`** strings (e.g., `"tests.unit.test_eval_registry.test_collision.FirstRubric"`) — i.e., each contains at least one `.` and matches the format `<module>.<qualname>`. Assertion shape: `assert exc.value.args[0] == "foo"`; `assert "." in exc.value.args[1]`; `assert "FirstRubric" in exc.value.args[1] and "SecondRubric" in exc.value.args[2]`; `assert exc.value.args[1] != exc.value.args[2]`.
- [ ] AC-6a: The registry maintains an `_origins: dict[str, str]` companion to `_by_name`, populated at registration time from the caller's `module.qualname` via `inspect.currentframe().f_back` (the kernel-discipline precedented in `transforms/signal_kinds.py:125-145` and `plugins/registry.py:117-123`). Verified by a test that registers a class **from a helper function defined in a separate module** and asserts the captured origin names the helper's module, not the registry module.
- [ ] AC-7: `register_task_class` rejects bad `name` types at decoration time. Parameterized red test covers: `123` (int), `b"foo"` (bytes), `None`, `["foo"]` (list) → all raise `TypeError`. Empty string `""` and whitespace-padded strings `"  foo"`, `"foo "`, `"  "` raise `ValueError` (runtime defense complementing fence-CI #4 which catches non-`ast.Constant` literals at PR time).
- [ ] AC-7a: `register_task_class(...)` applied to a non-class target (e.g., a plain function `def f(): pass`) raises `TypeError` at decoration time. `isinstance(rubric_class, type)` is the runtime check; mirrors `probes/registry.py:139-145`'s shape. Additionally: registering the **same class object** twice still raises `TaskClassAlreadyRegistered` (no idempotent path — `signal_kinds.py:95-97` precedent).
- [ ] AC-8: Direct `reg.register(tc)` (no decorator) collision-detects. Test constructs two `TaskClass` instances with the same `name`, calls `reg.register(tc1)` then `reg.register(tc2)`; the second call raises `TaskClassAlreadyRegistered` with the 3-tuple args shape from AC-6. (Guards a regression that puts the collision check only inside the `@register_task_class` helper.)
- [ ] AC-9: Immutability normalization at decoration time. After registration, `tc.breakdown_keys` is a `frozenset` (`type(tc.breakdown_keys) is frozenset`) **even if the caller passed a plain `set`**, and `tc.failure_mode_taxonomy` is a read-only `Mapping` (specifically `isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)` — attempting `tc.failure_mode_taxonomy["new"] = "block"` raises `TypeError`). The `@dataclass(frozen=True)` decorator blocks attribute reassignment but does not deep-freeze container contents; this AC closes that gap (the typed-at-the-edge pattern).
- [ ] AC-9a: `min_cases_for_promotion` is stored as a read-only Mapping (`MappingProxyType`) for the same reason. Test pins `isinstance(tc.min_cases_for_promotion, types.MappingProxyType)`.
- [ ] AC-10: Registry state is consistent after a failed (collision) registration. After a `TaskClassAlreadyRegistered` raises, the **existing** entry is still retrievable by `reg.get(name)`, `reg.all_task_classes()` returns exactly the entries registered *before* the failed call, and a subsequent unrelated registration `reg.register(tc3)` (different name) still succeeds. Guards a partial-write regression where `_by_name[name] = tc` happens *before* the collision check.
- [ ] AC-11: `TaskClassNotFound(name, available_names)` carries `available_names: tuple[str, ...]` **sorted alphabetically** (deterministic for snapshot-friendly error messages). Test pins: `exc.value.args[0] == "does-not-exist"`; `exc.value.args[1] == tuple(sorted({...registered names...}))`. With zero registrations, `available_names == ()`.
- [ ] AC-11a: `TaskClassRegistry()` is a fresh instance with `reg.all_task_classes() == ()`. Two `TaskClassRegistry()` instances are independent (`a is not b` and registrations into one do not appear in the other). Guards a class-level state regression where `_by_name` is declared at the class scope instead of the `__init__` scope.
- [ ] AC-12: The red tests from §TDD plan exist, were committed at the red marker, and are now green; the commit message names the red→green transition.
- [ ] AC-13: `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/eval/registry.py`, `pytest tests/unit/test_eval_registry.py` all pass.

## Implementation outline

1. Write `tests/unit/test_eval_registry.py` first (red); confirm `ImportError`.
2. Create `src/codegenie/eval/registry.py`:
   - **Imports.** `import inspect`; `from collections.abc import Callable, Mapping`; `from dataclasses import dataclass`; `from pathlib import Path`; `from types import MappingProxyType`; `from typing import Final, Literal`; `from codegenie.eval.errors import TaskClassAlreadyRegistered, TaskClassNotFound`; `from codegenie.eval.rubric import Rubric`. Stdlib-only (no `pydantic`, `yaml`, `tomllib`, `importlib`).
   - **`TaskClass` record.** `@dataclass(frozen=True, slots=True)` with the six fields per AC-2. Field declarations only — no `__post_init__`, no `__init_subclass__`, no methods.
   - **`TaskClassRegistry` class.** Per-instance state initialized in `__init__`:
     - `self._by_name: dict[str, TaskClass] = {}` — the registration map.
     - `self._origins: dict[str, str] = {}` — companion map carrying the `module.qualname` of each registration's call site (AC-6a; precedent: `transforms/signal_kinds.py:90`, `plugins/registry.py:101`). Kept separate so a collision error can name the **first** registration's call site even if `rubric_class.__qualname__` was rebound / `import as`-aliased.
     - `register(self, tc: TaskClass, *, origin: str | None = None) -> TaskClass`. Collision check **first** (no mutation before the check, per AC-10): if `tc.name in self._by_name`, raise `TaskClassAlreadyRegistered(tc.name, self._origins[tc.name], origin or f"{type(tc.rubric_class).__module__}.{tc.rubric_class.__qualname__}")`. Then `self._by_name[tc.name] = tc; self._origins[tc.name] = origin_or_fallback`. Return `tc`. The keyword-only `origin` exists so the `register_task_class` helper can inject a caller-frame-derived origin (the public test-callable `register` is also valid; it falls back to introspecting `rubric_class` if `origin` is omitted).
     - `get(self, name: str) -> TaskClass`. `try: return self._by_name[name]` except `KeyError`: `raise TaskClassNotFound(name, tuple(sorted(self._by_name.keys()))) from None`. Sorted-tuple discipline per AC-11.
     - `all_task_classes(self) -> tuple[TaskClass, ...]`. `return tuple(sorted(self._by_name.values(), key=lambda tc: tc.name))`. Tuple-not-list per AC-3a.
   - **Module singleton.** `default_registry: Final[TaskClassRegistry] = TaskClassRegistry()` (AC-4a). The `Final` annotation is load-bearing — replacement requires explicit DI through `register_task_class(..., registry=...)`; tests use `monkeypatch.setattr` rather than reassignment.
   - **`register_task_class` helper.** Signature:
     ```python
     def register_task_class(
         name: str,
         *,
         bench_path: Path,
         min_cases_for_promotion: Mapping[str, int],
         breakdown_keys: frozenset[str] | set[str],
         failure_mode_taxonomy: Mapping[str, Literal["block", "warn", "info"]],
         registry: TaskClassRegistry | None = None,
     ) -> Callable[[type[Rubric]], type[Rubric]]: ...
     ```
     - **Validate `name` eagerly (before returning the decorator closure):**
       - `if not isinstance(name, str): raise TypeError(f"name must be str, got {type(name).__name__}")` — AC-7 covers `int`/`bytes`/`None`/`list`.
       - `if not name or name != name.strip(): raise ValueError(f"name must be a non-empty stripped slug, got {name!r}")` — AC-7 covers whitespace-padded.
     - **Capture caller origin.** `frame = inspect.currentframe(); caller = frame.f_back if frame is not None else None; origin = f"{caller.f_globals.get('__name__', '?')}.{caller.f_code.co_qualname}" if caller is not None else "<unknown>"`. Mirror of `transforms/signal_kinds.py:137-142`. The `# pragma: no cover` on the `<unknown>` branch is acceptable — CPython always supplies a caller frame.
     - **Return the decorator closure.** Inside:
       - `if not isinstance(rubric_class, type): raise TypeError(f"@register_task_class target must be a class, got {type(rubric_class).__name__}")` — AC-7a.
       - Normalize containers: `frozen_keys = frozenset(breakdown_keys)`; `frozen_taxonomy = MappingProxyType(dict(failure_mode_taxonomy))`; `frozen_promotion = MappingProxyType(dict(min_cases_for_promotion))`. AC-9 / AC-9a.
       - Build the record: `tc = TaskClass(name=name, bench_path=bench_path, min_cases_for_promotion=frozen_promotion, rubric_class=rubric_class, breakdown_keys=frozen_keys, failure_mode_taxonomy=frozen_taxonomy)`.
       - Register: `(registry or default_registry).register(tc, origin=origin)`.
       - Return `rubric_class` **unmodified** (AC-5 — no subclassing, no `functools.wraps`-style transformation; the registry stores a reference, the class is returned as-is).
   - **`__all__`.** `__all__ = ["TaskClass", "TaskClassRegistry", "default_registry", "register_task_class"]` (four names, matching AC-1).
3. **Module docstring.** Cite `../phase-arch-design.md §Component design → src/codegenie/eval/registry.py` and `../ADRs/0004`, `../ADRs/0008`, `Phase 5 ADR-0003` as the why. Name the **public-signature sharpening** (5 kwargs vs the arch's 3-kwarg sketch) and the rationale (decoupled decorator — loader does the disk read; decoration stays O(1)). Note the **registry-pattern lineage** explicitly: 4th register-helper-backed registry in the codebase (after `probes/registry.py`, `plugins/registry.py`, `transforms/signal_kinds.py`); rule-of-three crossed, kernel-extract **deferred** per `signal_kinds.py:16-29` precedent (each registry carries divergent dispatch surfaces; sharing only the `register` line would couple them artificially).
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/registry.py`, `pytest tests/unit/test_eval_registry.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_eval_registry.py`

The red suite pins every AC. Two design intents matter for the reader:
1. **Origin tracking** is tested by registering a class from a helper in a separate module so the captured origin names the helper (not the test function), proving the introspection uses the caller frame rather than the class's own module.
2. **Args-tuple introspection** (vs string-message scraping) is used everywhere so a regression that changes the human-readable message format does not silently invalidate the contract; the args tuple IS the contract.

```python
# tests/unit/test_eval_registry.py
import dataclasses
import re
import types
import typing
from pathlib import Path
from typing import Final

import pytest

import codegenie.eval.registry as registry_module
from codegenie.eval.errors import TaskClassAlreadyRegistered, TaskClassNotFound
from codegenie.eval.registry import (
    TaskClass,
    TaskClassRegistry,
    default_registry,
    register_task_class,
)

EXPECTED_TASK_CLASS_FIELDS: Final[frozenset[str]] = frozenset({
    "name",
    "bench_path",
    "min_cases_for_promotion",
    "rubric_class",
    "breakdown_keys",
    "failure_mode_taxonomy",
})


def _kwargs(name: str = "vuln-remediation") -> dict:
    return dict(
        name=name,
        bench_path=Path(f"bench/{name}"),
        min_cases_for_promotion={"bronze": 10},
        breakdown_keys=frozenset({"cve_dropped", "tests_pass"}),
        failure_mode_taxonomy={"validator.tests_failed": "block"},
    )


# --- AC-1 / AC-2 — module surface + TaskClass shape -------------------------


def test_module_exports_exactly_four_names():
    # AC-1: typo'ing or accidentally adding a fifth public name fails.
    assert set(registry_module.__all__) == {
        "TaskClass",
        "TaskClassRegistry",
        "default_registry",
        "register_task_class",
    }


def test_task_class_is_frozen_dataclass_with_slots():
    # AC-2 (structural).
    assert dataclasses.is_dataclass(TaskClass)
    params = TaskClass.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen is True
    assert params.slots is True


def test_task_class_field_set_is_exactly_the_six_documented():
    # AC-2: a regression that adds (or drops) a field without an ADR amendment
    # fails this assertion.
    fields = {f.name for f in dataclasses.fields(TaskClass)}
    assert fields == EXPECTED_TASK_CLASS_FIELDS


def test_task_class_instance_is_frozen_and_has_no_dict():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs(), registry=reg)
    class R:
        pass

    tc = reg.get("vuln-remediation")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        tc.name = "other"  # type: ignore[misc]
    assert not hasattr(tc, "__dict__")  # slots=True


# --- AC-3 / AC-3a — register/get/all_task_classes contract ------------------


def test_register_returns_same_task_class_instance():
    # AC-3: identity, not equality. Mirrors plugins/registry.py:122 shape.
    reg = TaskClassRegistry()
    tc = TaskClass(
        name="x",
        bench_path=Path("bench/x"),
        min_cases_for_promotion=types.MappingProxyType({}),
        rubric_class=type("R", (), {}),
        breakdown_keys=frozenset(),
        failure_mode_taxonomy=types.MappingProxyType({}),
    )
    assert reg.register(tc) is tc


def test_all_task_classes_returns_a_tuple_sorted_by_name_with_correct_cardinality():
    # AC-3a: tuple type, sort discipline, cardinality.
    reg = TaskClassRegistry()
    for name in ("zebra", "alpha", "mango"):
        @register_task_class(**_kwargs(name), registry=reg)
        class _R:
            pass

    result = reg.all_task_classes()
    assert isinstance(result, tuple)
    assert tuple(tc.name for tc in result) == ("alpha", "mango", "zebra")
    assert len(result) == 3


# --- AC-4 / AC-4a — default_registry singleton + Final annotation -----------


def test_default_registry_is_TaskClassRegistry_instance():
    assert isinstance(default_registry, TaskClassRegistry)


def test_register_without_kwarg_writes_into_default_registry(monkeypatch):
    # AC-4: omitting `registry=` targets the module-level singleton. We swap
    # in a fresh via monkeypatch so the live default is never mutated by the
    # test (Notes for implementer: tests must not touch _by_name on the real
    # default).
    fresh = TaskClassRegistry()
    monkeypatch.setattr(registry_module, "default_registry", fresh)

    @register_task_class(**_kwargs("solo"))
    class R:
        pass

    assert fresh.get("solo").rubric_class is R


def test_default_registry_is_annotated_Final():
    # AC-4a: the `Final` annotation is mypy-enforced; this introspection
    # adds a runtime tripwire that catches a regression dropping the type
    # annotation entirely (which would compile but drop the structural
    # marker that disciplines tests + downstream consumers).
    hints = typing.get_type_hints(registry_module, include_extras=True)
    annotation = hints.get("default_registry")
    # `Final[TaskClassRegistry]` resolves to a `_GenericAlias` whose origin
    # is `typing.Final`; the inner arg is the registry type.
    assert typing.get_origin(annotation) is typing.Final
    assert typing.get_args(annotation) == (TaskClassRegistry,)


# --- AC-5 — decorator returns the class unmodified --------------------------


def test_decorator_returns_class_unmodified():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs(), registry=reg)
    class MyRubric:
        sentinel: str = "marker"

    # Identity, not equality — the class itself must come back, not a wrapper.
    fetched = reg.get("vuln-remediation").rubric_class
    assert fetched is MyRubric
    assert MyRubric.sentinel == "marker"


# --- AC-6 / AC-6a — collision args + origin tracking ------------------------


def _register_from_helper_module(reg: TaskClassRegistry, name: str = "vuln-remediation"):
    """Helper that triggers a registration from THIS function's call site.

    The captured origin must name `_register_from_helper_module`, not the
    surrounding test function. This is the structural assertion behind AC-6a:
    origins are caller-frame-derived, not class-introspection-derived.
    """
    @register_task_class(**_kwargs(name), registry=reg)
    class _FirstRubric:
        pass

    return _FirstRubric


def test_collision_args_tuple_is_3_tuple_with_module_qualified_origins():
    # AC-6: introspect args directly. Order: (name, existing_origin, incoming_origin).
    # Both origins are `module.qualname` strings (each contains at least one dot).
    reg = TaskClassRegistry()
    first = _register_from_helper_module(reg)

    with pytest.raises(TaskClassAlreadyRegistered) as exc:
        @register_task_class(**_kwargs(), registry=reg)
        class _SecondRubric:
            pass

    args = exc.value.args
    assert len(args) == 3
    name, existing_origin, incoming_origin = args
    assert name == "vuln-remediation"
    # Both origins are module.qualname format: at least one dot.
    assert "." in existing_origin
    assert "." in incoming_origin
    # First origin names the helper (AC-6a — caller-frame introspection).
    assert "_register_from_helper_module" in existing_origin
    # Second origin names the *current* test function.
    assert "test_collision_args_tuple" in incoming_origin
    assert existing_origin != incoming_origin
    # The first registered class is the one whose origin is stored.
    assert reg.get("vuln-remediation").rubric_class is first


def test_register_method_directly_also_collides():
    # AC-8: collision check lives in TaskClassRegistry.register, not only in
    # the @register_task_class helper. Construct two TaskClass instances and
    # call register() directly.
    reg = TaskClassRegistry()
    class _R1:
        pass
    class _R2:
        pass

    tc1 = TaskClass(
        name="foo",
        bench_path=Path("bench/foo"),
        min_cases_for_promotion=types.MappingProxyType({}),
        rubric_class=_R1,
        breakdown_keys=frozenset(),
        failure_mode_taxonomy=types.MappingProxyType({}),
    )
    tc2 = dataclasses.replace(tc1, rubric_class=_R2)

    reg.register(tc1)
    with pytest.raises(TaskClassAlreadyRegistered) as exc:
        reg.register(tc2)
    assert len(exc.value.args) == 3
    assert exc.value.args[0] == "foo"


# --- AC-7 / AC-7a — type-guard + non-class target + non-idempotent path -----


@pytest.mark.parametrize(
    "bad_name",
    [123, b"foo", None, ["foo"], 1.5],
    ids=["int", "bytes", "None", "list", "float"],
)
def test_register_task_class_rejects_non_string_name(bad_name):
    reg = TaskClassRegistry()
    with pytest.raises(TypeError):
        register_task_class(  # type: ignore[arg-type]
            bad_name,
            bench_path=Path("bench/x"),
            min_cases_for_promotion={"bronze": 10},
            breakdown_keys=frozenset(),
            failure_mode_taxonomy={},
            registry=reg,
        )


@pytest.mark.parametrize(
    "bad_name",
    ["", "  ", " foo", "foo ", "  foo  "],
    ids=["empty", "whitespace-only", "leading-space", "trailing-space", "both"],
)
def test_register_task_class_rejects_empty_or_whitespace_padded_name(bad_name):
    reg = TaskClassRegistry()
    with pytest.raises(ValueError):
        register_task_class(
            bad_name,
            bench_path=Path("bench/x"),
            min_cases_for_promotion={"bronze": 10},
            breakdown_keys=frozenset(),
            failure_mode_taxonomy={},
            registry=reg,
        )


def test_decorator_rejects_non_class_target():
    # AC-7a: applying @register_task_class to a function (not a class) raises.
    reg = TaskClassRegistry()
    decorator = register_task_class(**_kwargs(), registry=reg)
    with pytest.raises(TypeError):
        decorator(lambda: None)  # type: ignore[arg-type]


def test_re_registering_same_class_still_raises_no_idempotent_path():
    # AC-7a: signal_kinds.py:95-97 precedent — there is no idempotent path.
    # Even the SAME class registered twice under the same name raises.
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs(), registry=reg)
    class R:
        pass

    with pytest.raises(TaskClassAlreadyRegistered):
        register_task_class(**_kwargs(), registry=reg)(R)


# --- AC-9 / AC-9a — immutability normalization ------------------------------


def test_breakdown_keys_is_normalized_to_frozenset_even_when_input_is_set():
    reg = TaskClassRegistry()

    @register_task_class(
        name="x",
        bench_path=Path("bench/x"),
        min_cases_for_promotion={"bronze": 10},
        breakdown_keys={"cve_dropped", "tests_pass"},  # plain set, not frozenset
        failure_mode_taxonomy={"foo": "block"},
        registry=reg,
    )
    class R:
        pass

    tc = reg.get("x")
    assert type(tc.breakdown_keys) is frozenset
    assert tc.breakdown_keys == frozenset({"cve_dropped", "tests_pass"})


def test_failure_mode_taxonomy_is_normalized_to_read_only_mapping():
    reg = TaskClassRegistry()
    payload = {"foo": "block", "bar": "warn"}

    @register_task_class(
        name="x",
        bench_path=Path("bench/x"),
        min_cases_for_promotion={"bronze": 10},
        breakdown_keys=frozenset(),
        failure_mode_taxonomy=payload,
        registry=reg,
    )
    class R:
        pass

    tc = reg.get("x")
    assert isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)
    with pytest.raises(TypeError):
        tc.failure_mode_taxonomy["new"] = "block"  # type: ignore[index]
    # Mutating the original input must not affect the registry's snapshot.
    payload["foo"] = "info"
    assert tc.failure_mode_taxonomy["foo"] == "block"


def test_min_cases_for_promotion_is_stored_as_read_only_mapping():
    # AC-9a.
    reg = TaskClassRegistry()
    payload = {"bronze": 10, "silver": 50}

    @register_task_class(
        name="x",
        bench_path=Path("bench/x"),
        min_cases_for_promotion=payload,
        breakdown_keys=frozenset(),
        failure_mode_taxonomy={},
        registry=reg,
    )
    class R:
        pass

    tc = reg.get("x")
    assert isinstance(tc.min_cases_for_promotion, types.MappingProxyType)
    with pytest.raises(TypeError):
        tc.min_cases_for_promotion["gold"] = 100  # type: ignore[index]


# --- AC-10 — registry state consistent after a failed registration ---------


def test_state_consistent_after_collision():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs("foo"), registry=reg)
    class First:
        pass

    with pytest.raises(TaskClassAlreadyRegistered):
        @register_task_class(**_kwargs("foo"), registry=reg)
        class Second:
            pass

    # The first registration is still intact.
    assert reg.get("foo").rubric_class is First
    assert len(reg.all_task_classes()) == 1

    # An unrelated registration still succeeds.
    @register_task_class(**_kwargs("bar"), registry=reg)
    class Bar:
        pass

    assert len(reg.all_task_classes()) == 2
    assert {tc.name for tc in reg.all_task_classes()} == {"foo", "bar"}


# --- AC-11 — TaskClassNotFound carries sorted available_names ---------------


def test_get_missing_raises_with_sorted_tuple_of_available_names():
    reg = TaskClassRegistry()
    for name in ("zebra", "alpha", "mango"):
        @register_task_class(**_kwargs(name), registry=reg)
        class _R:
            pass

    with pytest.raises(TaskClassNotFound) as exc:
        reg.get("does-not-exist")
    args = exc.value.args
    assert args[0] == "does-not-exist"
    assert args[1] == ("alpha", "mango", "zebra")  # sorted, tuple


def test_get_missing_on_empty_registry_carries_empty_available_tuple():
    reg = TaskClassRegistry()
    with pytest.raises(TaskClassNotFound) as exc:
        reg.get("anything")
    assert exc.value.args == ("anything", ())


# --- AC-11a — instance isolation --------------------------------------------


def test_fresh_registry_is_empty_and_independent():
    a = TaskClassRegistry()
    b = TaskClassRegistry()
    assert a is not b
    assert a.all_task_classes() == ()
    assert b.all_task_classes() == ()

    @register_task_class(**_kwargs("only-in-a"), registry=a)
    class R:
        pass

    assert a.all_task_classes() != ()
    assert b.all_task_classes() == ()  # b is unaffected


def test_by_name_is_per_instance_not_class_level():
    # Guards a regression where _by_name is declared as a class attribute
    # (`_by_name: dict[str, TaskClass] = {}` at class scope) — that would
    # leak state across all TaskClassRegistry() instances.
    a = TaskClassRegistry()
    b = TaskClassRegistry()
    # The internal dicts must be distinct objects, not aliased.
    assert a._by_name is not b._by_name  # type: ignore[attr-defined]
```

Run; confirm `ModuleNotFoundError` (or `ImportError` on the four-name closure). Commit the red marker.

### Green — make it pass

Minimal implementation: `TaskClass` dataclass, `TaskClassRegistry` with the three methods, `register_task_class` returning a decorator that builds `TaskClass(...)` and calls `registry.register(tc)`. Collision check before insert; raise with both qualnames as positional args (so `exc.value.args` carries them).

### Refactor — clean up

- Module docstring (a) cites `../phase-arch-design.md §Component design → registry.py`, `../ADRs/0004`, `../ADRs/0008`, and `Phase 5 ADR-0003` as the why; (b) documents the **public-signature sharpening** (the helper widens the arch's 3-kwarg sketch to 5 kwargs because the loader owns the disk read, not the decorator); (c) names the **registry-pattern lineage** explicitly — 4th register-helper-backed registry (after `probes/registry.py`, `plugins/registry.py`, `transforms/signal_kinds.py`); rule-of-three crossed but kernel-extract **deferred** per `signal_kinds.py:16-29` precedent (the four registries' divergent dispatch surfaces mean a shared `register` line would couple them artificially).
- `__all__ = ["TaskClass", "TaskClassRegistry", "default_registry", "register_task_class"]` (four names, matching AC-1 + the closure test).
- `TaskClass.rubric_class: type[Rubric]` — confirm mypy `--strict` resolves the `Rubric` import without forward-reference issues; if it complains, `from __future__ import annotations` at top.
- Confirm `register_task_class` accepts both `Mapping[str, int]` and `dict[str, int]` for `min_cases_for_promotion` (Mapping is the wider type; tests pass `dict`); the decorator normalizes to `MappingProxyType(dict(...))` per AC-9a.
- `TaskClassAlreadyRegistered`'s args tuple is `(name, existing_origin, incoming_origin)` — three positional args, both origins in `module.qualname` format. The default `Exception.__str__` renders them as a Python tuple; no `__str__` override is added on either the error class (S1-01 marker discipline) or the registry (operator-facing message lives in the args tuple itself).
- Document in the docstring the **anti-pattern guard**: tests must not mutate `default_registry._by_name`. The only sanctioned isolation paths are (a) `TaskClassRegistry()` for fresh-instance tests and (b) `monkeypatch.setattr(codegenie.eval.registry, "default_registry", TaskClassRegistry())` for the rare test that must verify the default-targeting path. Mirrors the three sibling registries' conftest discipline.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/registry.py` | New file — `TaskClass`, `TaskClassRegistry`, `default_registry`, `@register_task_class` |
| `tests/unit/test_eval_registry.py` | New file — register/collision/get-missing/sorted/frozen/type-guard/fresh-registry |

## Out of scope

- **Loader-side population of `breakdown_keys` and `failure_mode_taxonomy` from disk** — handled by S2-01 (loader.load_task_class) and S2-02. This story takes them as decorator kwargs; production decorator call sites in `bench/<name>/registration.py` will be wired by the loader.
- **`Rubric` Protocol body** — handled by S1-04 (this story imports it).
- **Re-exporting from `codegenie.eval.__init__`** — handled by S1-05.
- **Fence-CI assertion that `@register_task_class` first arg is `ast.Constant[str]`** — handled by S7-01 #4 (the runtime guard here complements but does not replace it).
- **`@register_task_class` reading sibling `breakdown_keys.py` / `failure_modes.yaml`** — this happens via the loader in S2-01, not inside the decorator. Keeping the decorator side-effect-free at module import is intentional (decoration is O(1); heavy work moves to load time).
- **Substring-ban validation on `breakdown_keys`** (the per-task-class StrEnum's `confidence|llm|self_reported|model_says` filter from ADR-0008) — handled at PR time by fence-CI assertion #5 and at runtime by the runner (S3-04 / S3-03). The registry accepts the `frozenset` as-is; structural defense lives at the two layers ADR-0008 prescribes, not inside the decorator (defense-in-depth without coupling).
- **Severity Literal closure on `failure_mode_taxonomy`** (the `block|warn|info` value set from ADR-0004) — handled at load time by `loader._load_failure_mode_taxonomy` (S2-01) and at PR time by fence-CI assertion #6. The registry accepts any `Mapping[str, str]` and wraps it; the Literal narrowing is a type-system annotation, not a runtime enforcement at this site.
- **Bounds checking on `min_cases_for_promotion` values** (e.g., positive integers, monotonic tier ordering) — semantic validation; the loader is the correct defense site (S2-01). The registry stores whatever Mapping it receives.
- **`TaskClassName` newtype** — a typed identifier for task-class slugs (mirroring `PluginId`, `SignalKind`, `ProbeId`) would be the natural next step toward eliminating raw-`str` keys, but is **deferred** to a future identifier-consolidation story (likely once Phase 7 introduces the second task class and the cross-phase grep surface is non-trivial). Surfaced in Notes for implementer as the deferred-extract trigger.
- **`bench_path` normalization** (absolute-vs-relative, resolve-against-bench-root) — loader concern; the registry stores the `Path` as passed.
- **Sigstore / digest verification of the registered `rubric_class`** — Phase 16 territory per ADR-0001 §Consequences.

## Notes for the implementer

- **Collision-error contract.** The args tuple is `(name, existing_origin, incoming_origin)` — three positional args, both origins in `module.qualname` format (e.g., `tests.unit.test_eval_registry.test_collision.FirstRubric`). This is the **one ergonomic property** an autonomous Phase 7 implementer relies on when they accidentally cargo-cult a registration: grep the codebase for either origin string and the offending file falls out. A regression that drops the module path or returns only `__qualname__` (just `FirstRubric`) makes multi-bench collision diagnostics indistinguishable; the red test pins the format explicitly. Mirror `transforms/signal_kinds.py:71-75` and `plugins/registry.py:117-121`.
- **Origin tracking via caller-frame introspection.** The decorator captures `f"{caller.f_globals.get('__name__', '?')}.{caller.f_code.co_qualname}"` from `inspect.currentframe().f_back`. This is the precedented kernel-discipline (signal_kinds.py:137-142). Do **not** derive the origin from `rubric_class.__module__ + rubric_class.__qualname__` — a class object that was re-imported via `from bench.foo.registration import MyRubric as OtherName` carries the *original* module/qualname, not the registration call site. The caller frame names the *site of registration*, which is what an operator needs.
- **`slots=True` on `TaskClass`** is load-bearing for memory (~150 bytes saved per record) and *also* for the `not hasattr(tc, "__dict__")` test — that assertion catches a future refactor that removes `slots=True` silently. Don't drop it.
- **Immutability normalization (typed-at-the-edge pattern).** Inside the decorator: `frozen_keys = frozenset(breakdown_keys)`, `frozen_taxonomy = MappingProxyType(dict(failure_mode_taxonomy))`, `frozen_promotion = MappingProxyType(dict(min_cases_for_promotion))`. The `@dataclass(frozen=True)` decorator blocks attribute *reassignment* but does not deep-freeze container contents — a caller that retains the original `set`/`dict` could mutate it post-registration and corrupt every consumer's view. Constructing the container copies at the boundary is the defense; the `dict(...)` wrap before `MappingProxyType` guarantees the registry owns its snapshot.
- **`Mapping[str, int]` vs `dict[str, int]`** for `min_cases_for_promotion`: use the wider type in the signature (`Mapping`) so the decorator accepts both `dict` and `MappingProxyType` (loader will likely pass the latter); normalize via `MappingProxyType(dict(...))` per AC-9a.
- **Production registration via `default_registry`.** The `registry=` kwarg on `register_task_class` is *primarily* a test-only parameter; production `bench/<name>/registration.py` will call `register_task_class("foo", bench_path=..., ...)` without it, hitting the `default_registry` singleton via the `or default_registry` clause. The kwarg's only job is letting `TaskClassRegistry()` instances isolate test state.
- **Default-registry mutation is prohibited in tests.** Do **not** call `default_registry._by_name.clear()` from a fixture, do **not** monkeypatch `_by_name`, do **not** rely on test ordering to manage `default_registry` state. The only sanctioned isolation paths are:
  1. `TaskClassRegistry()` — fresh instance, target via `registry=` kwarg; the overwhelmingly common case.
  2. `monkeypatch.setattr(codegenie.eval.registry, "default_registry", TaskClassRegistry())` — swaps the module-level singleton out, only for the rare test that must verify the default-targeting path (the AC-4 test does this).

  This mirrors the discipline `tests/unit/plugins/conftest.py` enforces for `PluginRegistry.default_registry` and `tests/unit/transforms/test_trust_scorer.py` enforces for `signal_kind_registry`. The `Final[TaskClassRegistry]` annotation on `default_registry` is the structural marker that makes reassignment-as-mutation a mypy error in production code — the monkeypatch is allowed in tests because pytest is operating below the type-system boundary.
- **stdlib-only imports.** Do **not** import `pydantic`, `yaml`, `tomllib`, or `importlib` here. The registry is a stdlib-only module. Loader-side reads happen in `loader.py` (S2-01/S2-02). Keeping registry.py stdlib-only is what makes the package import-cost stay under the 600 ms cold-start budget (`phase-arch-design.md §Performance envelope`).
- **`TaskClassNotFound` carries sorted `available_names`.** Phase 5 ADR-0003's precedent (`SignalKindNotFound(name, available)`) is the model; this story adds the **sorted** discipline because deterministic error messages compose with the snapshot-friendly testing the harness leans on elsewhere (per arch §Determinism vs probabilism row 1).
- **Heavy work does NOT happen at decoration time.** The decorator is O(1); it adds two dict entries (`_by_name`, `_origins`) and returns. If you find yourself reading the filesystem, importing `pyyaml`, or doing BLAKE3 digest computation inside the decorator, stop and re-read `../phase-arch-design.md §Component design → registry.py` ("Heavy work … does **not** happen at import").
- **Public-signature divergence from arch (deliberate).** `phase-arch-design.md §Component design → registry.py` (lines 509-514) sketches the decorator with only 3 kwargs (`name`, `bench_path`, `min_cases_for_promotion`) — the arch's authoring assumption was that the decorator itself reads `breakdown_keys.py` and `failure_modes.yaml` from disk. This story **flips the read direction**: the loader (S2-01) does the disk read, then calls the decorator with the resulting `breakdown_keys`/`failure_mode_taxonomy` as explicit kwargs. The result is a side-effect-free O(1) decorator (composable, testable, no `importlib`/`pyyaml` import cost). The arch's sketch is correctly read as a shape, not a contract; the story's 5-kwarg signature is the contract S2-01 will consume. A future doc-sweep PR may reconcile the arch's lines 509-514 to match; do **not** auto-edit the arch from this story.
- **Registry-pattern lineage and the deferred kernel-extract.** This is the **4th** register-helper-backed registry in the codebase (after `probes/registry.py`, `plugins/registry.py`, `transforms/signal_kinds.py`). Rule of three is crossed; `signal_kinds.py:16-29` is the precedent that documents *why a shared kernel base is not warranted yet*: each registry carries divergent dispatch surfaces (probe filter-by-task + heaviness sort; plugin resolve-by-scope; signal_kind plain `__contains__`; this registry plain `get`/`all_task_classes`) and a shared `KernelRegistry[K, V]` base would couple four heterogeneous registries to save ~5 LOC each. **Defer.** The 6th register-helper-backed registry's author has a clean five-precedent grep trail; that is when the kernel-extract is warranted.
- **Open/Closed at the decorator boundary.** Adding a new task class is exactly *one* `@register_task_class("name", bench_path=..., ...)` call in a *new* `bench/<name>/registration.py` file. **Zero edits** to `registry.py` are required — including for Phase 7's `migration-chainguard-distroless`. If the implementer finds themselves opening `registry.py` to add a Phase 7 special case, stop: the kernel discipline has been broken, and the right fix is to extend by addition (a new file, a new decorator call), not to edit the kernel.
- **Future-work: `TaskClassName` newtype.** Task-class slugs are domain identifiers crossing ≥ 2 module boundaries (registry, loader, runner, audit chain). A `TaskClassName = NewType("TaskClassName", str)` (mirroring `PluginId`, `SignalKind`, `ProbeId` in `codegenie.types.identifiers`) would close primitive-obsession on the `name: str` field. **Not landing in this story** — the surface is bounded to one task class (vuln-remediation) in Phase 6.5; the consolidation has higher leverage when Phase 7 adds the second task class. Flagged as the trigger condition for a future identifier-consolidation story.
- **Why no `TaskClassRegistry` abstract base / `Protocol`.** The registry is a concrete class with one implementation. Adding a `Protocol[TaskClassRegistry]` surface would invite alternate implementations (file-backed, networked, mocked-as-Protocol) — none of which the design admits or the load-bearing fence-CI walks support. Phase 5 ADR-0006 (Protocol vs ABC) discusses this dichotomy; this story sits firmly on the "concrete class" side because there is no shared-default-behavior across-implementations need.
- **The implementer can write the green phase in ~60 LOC.** Anything substantially longer suggests scope creep (a wrapper class around `dict`, a decorator chain, a custom `__init_subclass__`). Re-read the implementation outline; the inventory is one `@dataclass`, one `class`, one module-level constant, and one function. That's all.
