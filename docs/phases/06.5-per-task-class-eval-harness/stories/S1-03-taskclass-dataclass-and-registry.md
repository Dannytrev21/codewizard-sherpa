# Story S1-03 — TaskClass dataclass + registry

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-04
**ADRs honored:** ADR-0004 (per-task-class `failure_mode_taxonomy`), ADR-0008 (per-task-class `breakdown_keys`), Phase 5 ADR-0003 (open-registry-via-decorator pattern reused), Phase 5 ADR-0006 (Protocol vs ABC — Rubric is `Protocol`)

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

- [ ] `src/codegenie/eval/registry.py` exists; `from codegenie.eval.registry import TaskClass, TaskClassRegistry, default_registry, register_task_class` succeeds.
- [ ] `TaskClass` is `@dataclass(frozen=True, slots=True)` with the six fields per `../phase-arch-design.md §Data model`: `name: str`, `bench_path: Path`, `min_cases_for_promotion: Mapping[str, int]`, `rubric_class: type[Rubric]`, `breakdown_keys: frozenset[str]`, `failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]`.
- [ ] `TaskClassRegistry.register(tc)` adds the entry and returns `tc`; `TaskClassRegistry.get(name)` returns the entry or raises `TaskClassNotFound(name, available_names)` with `available_names: tuple[str, ...]` for diagnosability; `TaskClassRegistry.all_task_classes()` returns a tuple sorted by `name` for determinism.
- [ ] `default_registry: TaskClassRegistry` is a module-level singleton; `register_task_class` writes into it; tests instantiate `TaskClassRegistry()` to isolate.
- [ ] `@register_task_class("foo", bench_path=..., min_cases_for_promotion={"bronze": 10}, breakdown_keys=frozenset({"k"}), failure_mode_taxonomy={"c": "block"})` decorates a class and registers it; the decorator returns the class unmodified.
- [ ] A second `@register_task_class("foo", ...)` (different class, same name) raises `TaskClassAlreadyRegistered` with a message naming both `__qualname__`s; the assertion in the red test parses the message to confirm both are present.
- [ ] `register_task_class(123, ...)` (non-string name) raises `TypeError` at decoration time; the runtime guard complements the fence-CI literal-only assertion (S7-01 #4).
- [ ] The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/test_eval_registry.py` all pass.

## Implementation outline

1. Write `tests/unit/test_eval_registry.py` first (red); confirm `ImportError`.
2. Create `src/codegenie/eval/registry.py`:
   - Imports: `from collections.abc import Callable, Mapping`, `from dataclasses import dataclass`, `from pathlib import Path`, `from typing import Literal`, `from codegenie.eval.errors import TaskClassAlreadyRegistered, TaskClassNotFound`, `from codegenie.eval.rubric import Rubric`.
   - `@dataclass(frozen=True, slots=True)` `TaskClass` per the AC field list.
   - `class TaskClassRegistry:` with internal `_by_name: dict[str, TaskClass]` (instance attribute, never module-global on the class). Methods `register`, `get`, `all_task_classes`.
   - `default_registry = TaskClassRegistry()` at module scope.
   - `def register_task_class(name: str, *, bench_path: Path, min_cases_for_promotion: Mapping[str, int], breakdown_keys: frozenset[str], failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]], registry: TaskClassRegistry | None = None) -> Callable[[type[Rubric]], type[Rubric]]:` — returns the decorator; `registry` kwarg defaults to `default_registry` and exists so tests can target a fresh registry.
   - Inside the decorator: `if not isinstance(name, str): raise TypeError(...)`; build `TaskClass(...)`; call `(registry or default_registry).register(tc)`.
   - `register` collision: if `name in self._by_name`, raise `TaskClassAlreadyRegistered(name, self._by_name[name].rubric_class.__qualname__, tc.rubric_class.__qualname__)`.
3. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/registry.py`, `pytest`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_eval_registry.py`

```python
# tests/unit/test_eval_registry.py
from pathlib import Path
import pytest

from codegenie.eval.errors import TaskClassAlreadyRegistered, TaskClassNotFound
from codegenie.eval.registry import TaskClass, TaskClassRegistry, register_task_class


def _kwargs(name: str = "vuln-remediation"):
    return dict(
        name=name,
        bench_path=Path(f"bench/{name}"),
        min_cases_for_promotion={"bronze": 10},
        breakdown_keys=frozenset({"cve_dropped", "tests_pass"}),
        failure_mode_taxonomy={"validator.tests_failed": "block"},
    )


def test_decorator_registers_and_returns_class_unchanged():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs(), registry=reg)
    class MyRubric:
        def score(self, case, harness_output):  # type: ignore[no-untyped-def]
            return None

    assert reg.get("vuln-remediation").rubric_class is MyRubric


def test_collision_message_names_both_qualnames():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs(), registry=reg)
    class FirstRubric:
        pass  # first registration

    with pytest.raises(TaskClassAlreadyRegistered) as exc:
        @register_task_class(**_kwargs(), registry=reg)
        class SecondRubric:
            pass  # collision

    msg = str(exc.value) + " ".join(repr(a) for a in exc.value.args)
    assert "FirstRubric" in msg
    assert "SecondRubric" in msg
    assert "vuln-remediation" in msg


def test_get_missing_name_raises_with_available_names_listed():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs("a"), registry=reg)
    class A: pass

    @register_task_class(**_kwargs("b"), registry=reg)
    class B: pass

    with pytest.raises(TaskClassNotFound) as exc:
        reg.get("does-not-exist")
    rendered = " ".join(repr(a) for a in exc.value.args)
    assert "does-not-exist" in rendered
    assert "a" in rendered and "b" in rendered


def test_all_task_classes_returns_deterministic_sorted_tuple():
    # Determinism is the only way fence-CI walks the registry reproducibly.
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs("zebra"), registry=reg)
    class Z: pass

    @register_task_class(**_kwargs("alpha"), registry=reg)
    class A: pass

    names = tuple(tc.name for tc in reg.all_task_classes())
    assert names == ("alpha", "zebra")


def test_task_class_dataclass_is_frozen_and_slotted():
    reg = TaskClassRegistry()

    @register_task_class(**_kwargs(), registry=reg)
    class R: pass

    tc = reg.get("vuln-remediation")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        tc.name = "other"  # type: ignore[misc]
    # slots=True means no __dict__:
    assert not hasattr(tc, "__dict__")


def test_non_string_name_raises_at_decoration_time():
    reg = TaskClassRegistry()
    with pytest.raises(TypeError):
        @register_task_class(123, bench_path=Path("bench/x"),  # type: ignore[arg-type]
                             min_cases_for_promotion={"bronze": 10},
                             breakdown_keys=frozenset(),
                             failure_mode_taxonomy={},
                             registry=reg)
        class R: pass


def test_default_registry_is_module_singleton_separate_from_fresh_instances():
    # Tests must be able to use TaskClassRegistry() to avoid bleed.
    from codegenie.eval.registry import default_registry
    fresh = TaskClassRegistry()
    assert fresh is not default_registry
    assert fresh.all_task_classes() == ()  # fresh starts empty regardless of imports
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

Minimal implementation: `TaskClass` dataclass, `TaskClassRegistry` with the three methods, `register_task_class` returning a decorator that builds `TaskClass(...)` and calls `registry.register(tc)`. Collision check before insert; raise with both qualnames as positional args (so `exc.value.args` carries them).

### Refactor — clean up

- Module docstring naming `../phase-arch-design.md §Component design → registry.py` and `../ADRs/0004`, `../ADRs/0008` as the why.
- Add `__all__ = ["TaskClass", "TaskClassRegistry", "default_registry", "register_task_class"]`.
- `TaskClass.rubric_class: type[Rubric]` — confirm mypy `--strict` resolves the `Rubric` import without forward-reference issues; if it complains, `from __future__ import annotations` at top.
- Confirm `register_task_class` accepts both `Mapping[str, int]` and `dict[str, int]` for `min_cases_for_promotion` (Mapping is the wider type; tests pass `dict`).
- The collision exception's `__str__` is Python's default — `TaskClassAlreadyRegistered("name", "First", "Second").args == ("name", "First", "Second")`. The red test asserts both qualnames are *present* (in `args` or message); this composes with S1-01's behavior-free marker discipline.

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

## Notes for the implementer

- The collision message **must name both qualnames** — that is the one ergonomic property an autonomous Phase 7 implementer relies on when they accidentally cargo-cult a registration. The red test will fail if you only include the incoming class; the existing one must be retrievable from `self._by_name[name].rubric_class.__qualname__`.
- `slots=True` on `TaskClass` is load-bearing for memory (~150 bytes saved per record) and *also* for the `not hasattr(tc, "__dict__")` test — that assertion catches a future refactor that removes `slots=True` silently. Don't drop it.
- `Mapping[str, int]` vs `dict[str, int]` for `min_cases_for_promotion`: use the wider type in the signature (`Mapping`) so the decorator accepts both `dict` and `MappingProxyType` (loader will likely pass the latter). Internally store as `dict` if you need to copy.
- The `registry` kwarg on `register_task_class` is a *test-only* parameter. Production `bench/<name>/registration.py` will call `register_task_class("foo", bench_path=..., ...)` without it (uses `default_registry`). The kwarg's only job is letting `TaskClassRegistry()` instances isolate test state.
- Do **not** import `pydantic`, `yaml`, `tomllib`, or `importlib` here. The registry is a stdlib-only module. Loader-side reads happen in `loader.py` (S2-01/S2-02). Keeping registry.py stdlib-only is what makes the package import-cost stay under the 600 ms cold-start budget (`phase-arch-design.md §Performance envelope`).
- `TaskClassNotFound` takes two positional args: the missing name and the tuple of available names. Phase 5 ADR-0003's precedent (`SignalKindNotFound(name, available)`) is the model.
- Heavy work — digest computation, case loading — does **NOT** happen at decoration time. The decorator is O(1); it adds one dict entry and returns. If you find yourself reading the filesystem inside the decorator, stop and re-read `../phase-arch-design.md §Component design → registry.py "Heavy work … does **not** happen at import"`.
- `default_registry` is mutated by every import that hits a `@register_task_class` call. Tests that use `default_registry` must clear it (`default_registry._by_name.clear()` is acceptable inside a fixture; do not expose this as a public method). Tests that use `TaskClassRegistry()` don't need cleanup.
