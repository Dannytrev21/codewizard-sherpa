# Story S5-01b — `TransformRegistry` — the channel by which a `RecipeEngine` surfaces its produced `Transform`

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Done — GREEN 2026-05-20 (phase-story-executor; see [`_attempts/S5-01b.md`](_attempts/S5-01b.md) for the per-AC evidence table + gate log — 14/14 ACs with runtime evidence, 100% branch coverage); validator HARDENED 2026-05-20
**Effort:** S
**Depends on:** S1-01 (`TransformId` newtype), S1-04 (`Transform` ABC + `TransformProvenance`), S5-01 (`RecipeEngine` Protocol — context only, not imported)
**ADRs honored:** ADR-0014 (this story ships the decision), ADR-0010 (newtype identifiers, typed error markers), ADR-0002 (registry-instance discipline)

## Validation notes

Validated: 2026-05-20 23:27 EDT
Verdict: HARDENED
Findings addressed: 5 total — 0 blocks, 4 hardens, 1 nit

Changes applied:
- AC-Surface-1 strengthened so the meta-test checks the exact sorted `__all__` list, not only set equality — Test-Quality finding T1.
- AC-Surface-3 strengthened so the no-singleton test also rejects a `default_transform_registry` name, even if it is not a `TransformRegistry` instance — Coverage finding C1.
- The duplicate-registration TDD case now uses two concrete transform classes and asserts both `module.qualname` origins appear in the raised `TransformAlreadyRegistered` message — Test-Quality finding T2.
- Notes for the implementer now call out why this sixth registry-like surface still does not justify a shared generic registry kernel: its per-workflow lifetime and tiny surface differ from process-wide plugin/recipe registries — Design-Patterns finding D1.
- This post-execution validation is recorded without widening the story scope or changing implementation files; the as-built module already satisfies the strengthened expectations.

Full audit log: `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S5-01b-transform-registry.md`

## Provenance

This story was authored on 2026-05-20 by the `codewizard-executer` scheduled task to resolve the **engine-layer blocker** documented in `_attempts/S5-02.md`, `_attempts/S5-03.md`, and cross-story `_attempts/_lessons.md` #16/#17. It is a small, well-bounded contract component; the architecture decision behind it is fully recorded in [ADR-0014](../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md). It was not run through the full `/phase-story-writer` → `/phase-story-validator` pipeline — the ACs below are written executor-ready against the as-built kernel.

## Context

S5-01 shipped the `RecipeEngine` Protocol GREEN (`src/codegenie/transforms/recipe_engine.py:67-91`): `async def apply(...) -> RecipeOutcome`. `apply` returns a single `RecipeOutcome`; its `Applied` variant (`outcomes.py:190-199`) carries `transform_id: TransformId` — a BLAKE3-hex digest — but **no `Transform` object**.

The orchestrator (S6-04) needs the `Transform` *object*: its Phase-5 wrap seam is `async def _validate_stage6(transform, ctx)`. With `apply` returning only an id, there was no sanctioned channel for the produced `Transform` to reach the orchestrator. The S5-02 / S5-03 validator harden-pass tried to bolt a 2-tuple `(RecipeOutcome, Transform | None)` onto `apply`, which contradicts the `mypy --strict` `RecipeEngine`-Protocol-conformance AC (a tuple is not assignable to `RecipeOutcome`). Both stories were BLOCKED.

[ADR-0014](../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md) resolves it: a `TransformRegistry` is the channel. `apply` stays `-> RecipeOutcome` (the ADR-0001/0009 frozen surface, untouched). A `RecipeEngine` is **constructor-injected** with a `TransformRegistry`; on a successful apply it calls `transform_registry.register(transform)` and returns `Applied(transform_id=transform.transform_id, ...)`. The orchestrator creates one `TransformRegistry` per workflow run, injects it into engines, and after `apply` retrieves the object via `transform_registry.get(applied.transform_id)`.

This story ships **only** the `TransformRegistry` module. Engine construction against it is S5-02/S5-03; orchestrator wiring is S6-04.

The `Applied` docstring (`outcomes.py:191-193`) and the `Transform` ABC docstring (`transform.py:64-96`) already name "the S1-04 `Transform` registry" as the lookup mechanism — this story builds the registry those docstrings promised.

## References — where to look

- **Phase ADRs:**
  - `../ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md` — **ADR-0014, the load-bearing reference** — the decision, the three rejected options, per-workflow-injection rationale, "not a Phase-5 contract symbol".
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — newtype `TransformId`, no raw `str` for domain keys; typed error markers.
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — registry-instance discipline (this registry diverges: per-workflow instance, **no** `default_*` singleton — see ADR-0014).
- **Shape precedent (mirror this):**
  - `src/codegenie/plugins/recipe_registry.py` — `RecipeRegistry` + `RecipeAlreadyRegistered` / `RecipeNotFound` typed markers. The `register` / `get` surface, the typed-error-marker shape (subclass `CodegenieError`, carry a typed id field, name both `module.qualname` origins in the duplicate message) are the precedent to copy.
- **Kernel surfaces consumed:**
  - `src/codegenie/transforms/transform.py` — `Transform` ABC (`transform_id`, `diff_bytes`, `files_changed`, `provenance`) + `TransformProvenance`.
  - `src/codegenie/types/identifiers.py:80` — `TransformId = NewType("TransformId", str)`.
  - `src/codegenie/errors.py` — `CodegenieError` root marker.
- **Sibling stories:**
  - `S5-02-npm-lockfile-recipe-engine.md` / `S5-03-openrewrite-engine-scaffold.md` — the engines that will be constructor-injected with this registry.
  - `S6-04-remediation-orchestrator.md` — constructs the per-workflow `TransformRegistry`, injects it, looks the `Transform` up after `apply`.

## Goal

Ship `src/codegenie/transforms/transform_registry.py` exposing `TransformRegistry`, `TransformAlreadyRegistered`, and `TransformNotFound`. `TransformRegistry` is a per-workflow, in-memory store keyed by `TransformId` with a `register` write path and a `get` read path, so a `RecipeEngine` can surface its produced `Transform` to the orchestrator without widening the frozen `RecipeEngine.apply` return contract.

## Acceptance criteria

### Surface + module shape

- [ ] **AC-Surface-1.** `from codegenie.transforms.transform_registry import TransformRegistry, TransformAlreadyRegistered, TransformNotFound` succeeds. The module's `__all__` is **exactly** `["TransformAlreadyRegistered", "TransformNotFound", "TransformRegistry"]` (sorted; private helpers never re-exported). A meta-test asserts `transform_registry.__all__ == ["TransformAlreadyRegistered", "TransformNotFound", "TransformRegistry"]` so ordering, duplicates, and extra exports are all caught. (validator: hardened — original set-only check could not catch ordering drift or duplicate entries.)
- [ ] **AC-Surface-2.** `TransformRegistry` is **not** re-exported from `codegenie.transforms.__init__` — it is an internal orchestration mechanism, not one of ADR-0001's six Phase-5 contract symbols (ADR-0014 §Decision). A test asserts `"TransformRegistry" not in codegenie.transforms.__all__`. The existing `tests/fence/test_transforms_module_purity.py::test_transforms_all_is_exact_set` superset fence still passes (this story adds nothing to `transforms.__all__`).
- [ ] **AC-Surface-3.** No process-wide singleton: the module declares **no** module-level `TransformRegistry` instance and **no** `default_transform_registry`. A test asserts `"default_transform_registry" not in vars(transform_registry)` and `not any(isinstance(v, TransformRegistry) for v in vars(transform_registry).values())`. Two `TransformRegistry()` instances are fully independent — registering into one leaves the other empty (asserted: `r1.register(t); assert len(r1) == 1 and len(r2) == 0`). (validator: hardened — the original singleton test missed a wrongly named non-registry placeholder.)
- [ ] **AC-Surface-4.** `mypy --strict src/codegenie/transforms/transform_registry.py` exits 0 — no `Any`, no `# type: ignore`, no untyped def. `ruff check` + `ruff format --check` green.

### `register` — write path

- [ ] **AC-Reg-1.** `register(self, transform: Transform) -> Transform` keys the transform by `transform.transform_id` and returns the **same object** unchanged (`registry.register(t) is t` — identity, mirroring `RecipeRegistry.register`'s return).
- [ ] **AC-Reg-2.** After `register(t)`: `t.transform_id in registry is True` and `len(registry) == 1`.
- [ ] **AC-Reg-3.** Registering two transforms with **distinct** `transform_id`s leaves `len(registry) == 2`; each is independently retrievable via `get`.
- [ ] **AC-Reg-4.** Registering a transform whose `transform_id` **equals an already-registered id** raises `TransformAlreadyRegistered`. The raised error carries `.transform_id` equal to the colliding id, and its message names both colliding `type(x).__module__ + "." + type(x).__qualname__` origin strings (mirrors `RecipeAlreadyRegistered`). The **first** registration is unaffected — `registry.get(tid)` still returns the originally-registered object.

### `get` — read path

- [ ] **AC-Get-1.** `get(self, transform_id: TransformId) -> Transform` returns the **exact object** passed to `register` (`registry.get(t.transform_id) is t` — identity, not just equality).
- [ ] **AC-Get-2.** `get(unknown_id)` raises `TransformNotFound`; the raised error carries `.transform_id` equal to the queried id. No `KeyError` ever escapes the registry.
- [ ] **AC-Get-3.** `__contains__` and `__len__` are implemented: `tid in registry` is `True` for a registered id and `False` otherwise; `len(registry)` equals the count of registered transforms. (`__contains__` accepts the `TransformId` key; an unregistered or wrong-typed key returns `False`, never raises.)

### Typed error markers (ADR-0010)

- [ ] **AC-Err-1.** `TransformAlreadyRegistered` and `TransformNotFound` both subclass `codegenie.errors.CodegenieError` (the repo-wide chokepoint marker root). Each carries a typed `.transform_id: TransformId` instance attribute so callers match on a structured field rather than parsing the message — mirrors `codegenie.plugins.recipe_registry.RecipeAlreadyRegistered` / `RecipeNotFound`. A test constructs each and asserts `isinstance(err, CodegenieError)` and `err.transform_id == <id>`.

### Discipline + structural

- [ ] **AC-Disc-1.** An AST-walk import-set assertion in the test file confirms `transform_registry.py` imports only from `{"__future__", "typing", "codegenie.errors", "codegenie.transforms.transform", "codegenie.types.identifiers"}` — no `codegenie.plugins.*` reach-through, no LLM SDK. (The repo-wide `tests/unit/test_pyproject_fence.py` + `make lint-imports` already fence the LLM closure; this AC is a focused, story-local import-set check.)
- [ ] **AC-Disc-2.** The registry key type is `TransformId` (newtype, ADR-0010) — never raw `str`. `register` reads `transform.transform_id` (already typed `TransformId`); `get` and `__contains__` accept `TransformId`. The internal store is annotated `dict[TransformId, Transform]`.
- [ ] **AC-Cov-1.** Branch coverage on `src/codegenie/transforms/transform_registry.py` ≥ 95% (`pytest tests/unit/transforms/test_transform_registry.py --cov=codegenie.transforms.transform_registry --cov-branch --cov-report=term-missing`).

## Implementation outline

1. Create `src/codegenie/transforms/transform_registry.py` with a module docstring referencing ADR-0014 (the decision) and ADR-0010 (newtype + typed-marker discipline). Note in the docstring that this registry is **per-workflow** (constructor-created, no `default_*` singleton) and **not** a Phase-5 contract symbol.
2. Define the two typed error markers, each subclassing `CodegenieError`, mirroring `recipe_registry.py`'s `RecipeAlreadyRegistered` / `RecipeNotFound`:
   ```python
   class TransformAlreadyRegistered(CodegenieError):
       transform_id: TransformId
       def __init__(self, transform_id: TransformId, existing: str, duplicate: str) -> None:
           self.transform_id = transform_id
           self.existing = existing
           self.duplicate = duplicate
           super().__init__(
               f"duplicate transform_id {transform_id!r}: {existing} and {duplicate}"
           )

   class TransformNotFound(CodegenieError):
       transform_id: TransformId
       def __init__(self, transform_id: TransformId) -> None:
           self.transform_id = transform_id
           super().__init__(f"transform {transform_id!r} is not registered")
   ```
3. Define `TransformRegistry`:
   ```python
   class TransformRegistry:
       def __init__(self) -> None:
           self._transforms: dict[TransformId, Transform] = {}
           self._origins: dict[TransformId, str] = {}

       def register(self, transform: Transform) -> Transform:
           tid = transform.transform_id
           new_origin = f"{type(transform).__module__}.{type(transform).__qualname__}"
           if tid in self._transforms:
               raise TransformAlreadyRegistered(tid, self._origins[tid], new_origin)
           self._transforms[tid] = transform
           self._origins[tid] = new_origin
           return transform

       def get(self, transform_id: TransformId) -> Transform:
           try:
               return self._transforms[transform_id]
           except KeyError:
               raise TransformNotFound(transform_id) from None

       def __contains__(self, transform_id: object) -> bool:
           return transform_id in self._transforms

       def __len__(self) -> int:
           return len(self._transforms)
   ```
4. Module `__all__` is the sorted three-name list. Do **not** edit `src/codegenie/transforms/__init__.py` (ADR-0014 — internal mechanism, imported directly).
5. Tests (TDD plan below).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_transform_registry.py`.

```python
# tests/unit/transforms/test_transform_registry.py
from __future__ import annotations

import ast
import inspect

import pytest

import codegenie.transforms as transforms_pkg
import codegenie.transforms.transform_registry as tr_mod
from codegenie.errors import CodegenieError
from codegenie.transforms.transform import Transform, TransformProvenance
from codegenie.transforms.transform_registry import (
    TransformAlreadyRegistered,
    TransformNotFound,
    TransformRegistry,
)
from codegenie.types.identifiers import (
    EventId,
    PluginId,
    RecipeId,
    TransformId,
    TransformKind,
)


# --- Test fixtures: a minimal concrete Transform ----------------------------

def _provenance() -> TransformProvenance:
    return TransformProvenance(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version="0.1.0",
        recipe_id=RecipeId("npm-semver-bump"),
        recipe_version="0.1.0",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
        capability_use_id=EventId("01HX0000000000000000000000"),
    )


class _FakeTransform(Transform):
    """Minimal concrete Transform — the registry never inspects anything
    beyond ``transform_id``, so diff/files are left trivial."""

    def __init__(self, transform_id: str) -> None:
        self.transform_id = TransformId(transform_id)
        self.diff_bytes = b""
        self.files_changed = ()
        self.provenance = _provenance()


class _OtherFakeTransform(_FakeTransform):
    """Second concrete class used to prove duplicate messages name both origins."""


_TID_A = "a" * 64
_TID_B = "b" * 64


# --- Surface ----------------------------------------------------------------

def test_all_is_exact_sorted_list() -> None:
    assert tr_mod.__all__ == [
        "TransformAlreadyRegistered",
        "TransformNotFound",
        "TransformRegistry",
    ]


def test_not_reexported_from_transforms_package() -> None:
    # AC-Surface-2 — internal mechanism, not a Phase-5 contract symbol.
    assert "TransformRegistry" not in transforms_pkg.__all__


def test_no_module_level_singleton() -> None:
    # AC-Surface-3 — per-workflow injection; no default_* singleton.
    assert "default_transform_registry" not in vars(tr_mod)
    assert not any(
        isinstance(v, TransformRegistry) for v in vars(tr_mod).values()
    )


def test_instances_are_independent() -> None:
    r1, r2 = TransformRegistry(), TransformRegistry()
    r1.register(_FakeTransform(_TID_A))
    assert len(r1) == 1
    assert len(r2) == 0


# --- register ---------------------------------------------------------------

def test_register_returns_same_object() -> None:
    reg = TransformRegistry()
    t = _FakeTransform(_TID_A)
    assert reg.register(t) is t


def test_register_then_contains_and_len() -> None:
    reg = TransformRegistry()
    t = _FakeTransform(_TID_A)
    reg.register(t)
    assert t.transform_id in reg
    assert len(reg) == 1


def test_register_two_distinct_ids() -> None:
    reg = TransformRegistry()
    a, b = _FakeTransform(_TID_A), _FakeTransform(_TID_B)
    reg.register(a)
    reg.register(b)
    assert len(reg) == 2
    assert reg.get(a.transform_id) is a
    assert reg.get(b.transform_id) is b


def test_register_duplicate_id_raises_and_first_wins() -> None:
    reg = TransformRegistry()
    first = _FakeTransform(_TID_A)
    second = _OtherFakeTransform(_TID_A)  # same id, different concrete origin
    reg.register(first)
    with pytest.raises(TransformAlreadyRegistered) as exc_info:
        reg.register(second)
    assert exc_info.value.transform_id == TransformId(_TID_A)
    first_origin = f"{type(first).__module__}.{type(first).__qualname__}"
    second_origin = f"{type(second).__module__}.{type(second).__qualname__}"
    assert first_origin in str(exc_info.value)
    assert second_origin in str(exc_info.value)
    # First registration is unaffected.
    assert reg.get(TransformId(_TID_A)) is first
    assert len(reg) == 1


# --- get --------------------------------------------------------------------

def test_get_returns_exact_object() -> None:
    reg = TransformRegistry()
    t = _FakeTransform(_TID_A)
    reg.register(t)
    assert reg.get(t.transform_id) is t


def test_get_miss_raises_transform_not_found() -> None:
    reg = TransformRegistry()
    with pytest.raises(TransformNotFound) as exc_info:
        reg.get(TransformId(_TID_A))
    assert exc_info.value.transform_id == TransformId(_TID_A)


def test_contains_false_for_unregistered() -> None:
    reg = TransformRegistry()
    assert TransformId(_TID_A) not in reg
    assert "not-even-a-transform-id" not in reg  # never raises


# --- Typed error markers ----------------------------------------------------

def test_errors_subclass_codegenie_error() -> None:
    already = TransformAlreadyRegistered(TransformId(_TID_A), "mod.A", "mod.B")
    missing = TransformNotFound(TransformId(_TID_B))
    assert isinstance(already, CodegenieError)
    assert isinstance(missing, CodegenieError)
    assert already.transform_id == TransformId(_TID_A)
    assert missing.transform_id == TransformId(_TID_B)
    # Duplicate message names both colliding origins.
    assert "mod.A" in str(already) and "mod.B" in str(already)


# --- Discipline -------------------------------------------------------------

def test_import_set_is_within_allowlist() -> None:
    # AC-Disc-1 — no codegenie.plugins.* reach-through, no LLM SDK.
    allowed = {
        "__future__",
        "typing",
        "codegenie.errors",
        "codegenie.transforms.transform",
        "codegenie.types.identifiers",
    }
    tree = ast.parse(inspect.getsource(tr_mod))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "<relative>")
    assert imported <= allowed, f"unexpected imports: {sorted(imported - allowed)}"
```

Run; confirm `ImportError` on the `transform_registry` import; commit Red.

### Green — make it pass

- Implement `transform_registry.py` exactly as the Implementation outline prescribes — two typed markers + `TransformRegistry` with `register` / `get` / `__contains__` / `__len__`.
- `from __future__ import annotations` at the top; import `CodegenieError`, `Transform`, `TransformId`. `Transform` may be imported under `if TYPE_CHECKING:` (it is used only in annotations — `register` operates on the object, not the class) — either form satisfies AC-Disc-1's allowlist.

### Refactor — clean up

- Confirm `register`'s duplicate path and `get`'s miss path are both branch-covered (the `_origins` dict exists solely to make the duplicate message name both origins — keep it; it mirrors `RecipeRegistry._origins`).
- Run `pytest tests/unit/transforms/test_transform_registry.py -v`, `mypy --strict src/codegenie/transforms/transform_registry.py`, `ruff check`, `ruff format --check`, and the coverage command from AC-Cov-1.
- Run `pytest tests/fence/test_transforms_module_purity.py` to confirm the new module did not perturb the `transforms.__all__` superset fence.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/transform_registry.py` | New — `TransformRegistry` + `TransformAlreadyRegistered` + `TransformNotFound` |
| `tests/unit/transforms/test_transform_registry.py` | New — surface, register (identity / distinct / duplicate-collision), get (hit / miss), `__contains__` / `__len__`, typed-marker, import-set discipline |

## Out of scope

- **Engine construction against the registry** — S5-02 (`NpmLockfileRecipeEngine`) and S5-03 (`OpenRewriteRecipeEngine`) widen their `__init__` to `(jail, transform_registry)` and call `register` on success. This story ships only the registry.
- **Orchestrator wiring** — S6-04 creates the per-workflow `TransformRegistry`, injects it into engines, and looks the `Transform` up after `apply`.
- **Re-export from `codegenie/transforms/__init__.py`** — deliberately excluded (ADR-0014: not a Phase-5 contract symbol; imported directly like `sandbox_jail.py` / `recipe_registry.py`).
- **Any change to `RecipeEngine`, `RecipeOutcome`, or `Applied`** — ADR-0014's whole point is that the frozen surface is untouched.
- **A `default_transform_registry` singleton / `@register_transform` decorator** — `Transform`s register at runtime, once per workflow; a process-wide singleton would leak across runs (ADR-0014 §Decision).
- **`all()` enumeration / `_reset_for_tests()`** — no consumer needs them; a fresh `TransformRegistry()` per test makes a reset hook unnecessary (Rule 2 — add when a real call site appears).

## Notes for the implementer

- **Mirror `recipe_registry.py`, do not invent.** The typed-error-marker shape (subclass `CodegenieError`, typed `.transform_id` attribute, duplicate message naming both `module.qualname` origins) is copied verbatim from `RecipeAlreadyRegistered` / `RecipeNotFound`. The `_origins` dict serves only the duplicate message — keep it.
- **`register` is strict, not idempotent.** A duplicate `transform_id` raises — it never silently overwrites. Within one workflow the orchestrator registers each transform exactly once; a collision means a real bug (two distinct diffs hashed to the same `TransformId`, or a double-register), and per Rule 12 (fail loud) it must surface, not be swallowed.
- **No `isinstance(transform, Transform)` guard in `register`.** `mypy --strict` enforces the parameter type at every call site; a runtime guard would be redundant defensive code (Rule 2). `register` only ever reads `transform.transform_id` and `type(transform)`.
- **`Transform` is an ABC with class-level annotations** (S1-04) — a concrete subclass declares `transform_id` / `diff_bytes` / `files_changed` / `provenance` as instance or class attributes. The test's `_FakeTransform` is the minimal such subclass; the ABC's `__new__` lets subclasses through and only blocks direct `Transform(...)`.
- **`__contains__(self, transform_id: object)`** takes `object` (not `TransformId`) so `x in registry` never raises on a wrong-typed key — Python's `in` protocol contract. It returns `False` for anything not a registered key.
- **This registry is per-workflow.** It holds at most a handful of transforms for the lifetime of one `RemediationOrchestrator.run()` and is then discarded. No GC, no eviction, no size cap is needed (contrast `BundleCacheGc`, S3-05, which manages an on-disk cache across runs).
- **No shared registry kernel yet.** This is another registry-shaped component, but it is not the same lifecycle as `PluginRegistry` / `RecipeRegistry`: it has no process-wide default, no decorator, no `all()` enumeration, no reset hook, and no plugin import-time behavior. Keep the small concrete class until a second per-workflow runtime-object registry needs the same surface; that is the rule-of-three trigger for extracting a tiny shared kernel or Protocol. (validator: added — design-pattern hardening; prefer extension-by-addition without premature abstraction.)
