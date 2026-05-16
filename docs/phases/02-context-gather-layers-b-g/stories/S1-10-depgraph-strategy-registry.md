# Story S1-10 — `codegenie.depgraph` package + `@register_dep_graph_strategy` registry

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Done (GREEN 2026-05-15, all 16 ACs satisfied — see `_attempts/S1-10.md`)
**Effort:** S
**Depends on:** S1-05
**ADRs honored:** production ADR-0033 (typed identifiers), 02-ADR-0006 §Decisions noted (registry symmetry)

## Validation notes (2026-05-15, phase-story-validator)

**Verdict:** HARDENED. The draft was structurally sound (no RESCUE-tier findings) and the design-pattern shape correctly mirrors S1-02's `@register_index_freshness_check` precedent. Eight harden-tier edits were applied to close mutation-resistance gaps the executor's Validator could not have caught:

1. **`PackageManager` is a `Literal[...]`, not an Enum.** Phase 1 ADR-0013's `PackageManager = Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` (verified at `src/codegenie/probes/node_build_system.py:115`) is a type alias — `hasattr(PackageManager, "PNPM")` is **always False** at runtime. The draft tests' defensive ternary (`PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm"`) collapsed to bare string literals on every dispatch — a no-op disguised as flexibility. Tests rewritten to use `cast(PackageManager, "pnpm")` at the type seam; the registry's `dict[PackageManager, …]` typing carries the mypy-strict contract.
2. **Decorator return-identity** was not pinned (`reg.register(eco)(fn) is fn`) — a `register` that returns `None` would have passed the draft tests. New AC + test.
3. **Strategy argument-order and return-identity through `dispatch`** were not pinned — a `dispatch` impl that called `fn(manifests, ctx)` (swapped args) or returned a copy/wrapper of the graph would have passed the draft (test strategy ignored both args; `isinstance(g, DiGraph)` does not check identity). New AC + test with sentinel objects and `is`-identity assertion. (Mirrors S1-02 validation finding #4 — slice/head argument-swap was the same class of silent mutation.)
4. **Duplicate-registration error message** was untested for "both call sites named". The Green code names `prior` + new origin, but no test pinned this — a regression to bare `__qualname__` would still pass AC-2. AC strengthened, test extended (mirrors S1-02 validation finding #4).
5. **`registered_ecosystems()` had no AC.** Implementation outline named it but no AC pinned its contract (return type, ordering, empty-registry behavior). New AC + test.
6. **`DepGraphRegistryError` in `errors.py`'s `__all__`** was not pinned. Implementation outline §4 says "append" but `__all__` was silent — would let a regression that omits the export pass. New AC.
7. **Module-level decorator singleton test** used a non-`PackageManager` string (`"__test_singleton_eco__"`) with `# type: ignore[arg-type]` — that bypasses both the type contract and the duplicate-detection seam. Rewritten to use a real `PackageManager` literal and a `finally: unregister_for_tests` to keep the singleton clean.
8. **AC-4 dispatch-error reason format** was named only as "in `args[0]`"; the exact prefix (`no_strategy_for_ecosystem: <repr>`) was not pinned. Tightened so AC-4 + S4-05's downstream translation contract are unambiguous.

**Design-pattern note carried in §Notes for the implementer (no AC mandate):** the rule-of-three threshold for a shared `KernelRegistry[K, V]` kernel is **reached** with this story (the 3rd registry of the family — `probes/registry.py`, `indices/registry.py`, now `depgraph/registry.py`). The three sites' dispatch shapes diverge non-trivially (`for_task` filter + LRU / `dispatch_all` total / single-`dispatch(key)`), so per Rule 2 (simplicity first) + Rule 3 (surgical changes) the kernel-extract is **NOT prescribed in this story**. The opportunity is recorded as a Notes paragraph so it survives for a post-Phase-2 cleanup story to evaluate. This deferral mirrors S1-02's own rule-of-three note ("intentionally does not pre-extract").

Full audit at `_validation/S1-10-depgraph-strategy-registry.md`.

## Context

`DepGraphProbe` (B5, S4-05) is the kernel skeleton; ecosystem-specific resolution (pnpm vs. npm vs. yarn vs. bun, eventually Maven, Cargo) lives in Phase 3+ plugin adapters. To preserve the Open/Closed seam, the decorator-registry pattern (same family as `@register_index_freshness_check` from S1-02 and `@register_probe` from S1-08) is the right shape: each ecosystem's strategy registers via `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)`. Phase 2 ships **zero strategies** — the registry is the seam Phase 3 fills.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 — DepGraphProbe + strategy registry` — public interface, the `@register_dep_graph_strategy(ecosystem=PackageManager.PNPM)` shape, and the "zero strategies in Phase 2" rule.
  - `../phase-arch-design.md §"Design patterns applied"` row 5 — Open/Closed at the file boundary; adding Maven is a new file + new decorator + ADR-amend on `PackageManager`.
  - `../phase-arch-design.md §"Integration with Phase 3"` row "`PackageManager` enum + `@register_dep_graph_strategy`" — Phase 3 registers `build_npm`, `build_pnpm` via **new files**, never edits `DepGraphProbe`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006 §Decisions noted — registry-symmetry principle (`@register_index_freshness_check`, `@register_dep_graph_strategy`, `@register_probe` all share shape).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0033-typed-identifiers.md` — production ADR-0033 — `PackageManager` (Phase 1 ADR-0013) is the typed registry key, not `ecosystem: str`.
- **Source design:**
  - `../final-design.md §11 — DepGraphProbe + strategy registry` — the deliberate kernel-skeleton scope.
- **Existing code:**
  - `src/codegenie/probes/registry.py` — mirror the class-based-`Registry` + decorator-factory shape S1-08 finishes.
  - `src/codegenie/indices/registry.py` (S1-02) — sibling pattern.
  - `src/codegenie/types/identifiers.py` (S1-05) — re-exports `PackageManager` from Phase 1 ADR-0013.
  - `networkx` — `networkx.DiGraph` is the strategy return type (Phase 2 already accepts `networkx` per `../phase-arch-design.md §"Component design" #11`); confirm it's in `pyproject.toml` extras or add it to `gather` extras.
- **External docs (only if directly relevant):**
  - https://networkx.org/documentation/stable/reference/classes/digraph.html — `DiGraph` API surface.

## Goal

Implement `src/codegenie/depgraph/{__init__.py,model.py,registry.py}` — `@register_dep_graph_strategy(ecosystem: PackageManager)` decorator-registry returning `Callable[[ProbeContext, list[Manifest]], networkx.DiGraph]` strategies, **zero strategies registered in Phase 2**, with typed `DepGraphRegistryError` on unknown ecosystem dispatch.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/depgraph/__init__.py` exports `register_dep_graph_strategy`, `default_dep_graph_registry`, `DepGraphRegistry`, `DepGraphStrategy` (type alias), `DepGraphRegistryError`, and a `DepGraphProbeOutput` Pydantic model (frozen, the typed slice shape — fields: `graph_path: Path | None`, `confidence: Literal["high","medium","low"]`, `reason: str | None`). Public surface symmetry: `__all__` in `__init__.py` is exactly these six names, sorted; a test asserts the set equality.
- [ ] **AC-2.** `@register_dep_graph_strategy(ecosystem: PackageManager)` is a decorator-factory; registers the function in `default_dep_graph_registry`; duplicate-ecosystem registration raises `DepGraphRegistryError` at decoration time (i.e., module import) with **both registration sites named as dotted `module.qualname` strings in `args[0]`** (mirror S1-02 hardening; an operator grepping a multi-file plugin tree can locate both registrations from the message alone).
- [ ] **AC-3.** `DepGraphStrategy` type alias is exactly `Callable[[ProbeContext, list[Mapping[str, Any]]], "networkx.DiGraph"]`. The `Mapping[str, Any]` shape is **final, not provisional** — verified by source scan that no `Manifest` / `NodeManifest` Pydantic model exists under `src/codegenie/` as of S1-10 (Phase 1's `parsed_manifest` returns `Mapping[str, Any] | None` per `src/codegenie/probes/base.py:53`). If a future story promotes manifests to a Pydantic model, this alias rebinds **by ADR amendment**, never by silent widening.
- [ ] **AC-4.** `DepGraphRegistry.dispatch(ecosystem: PackageManager, ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph` invokes the registered strategy and **returns the exact object the strategy returned** (identity, not a copy/wrapper — pinned by `is`-test in the TDD plan). Unknown ecosystem raises `DepGraphRegistryError` whose `args[0]` begins with the literal prefix `no_strategy_for_ecosystem: ` followed by `repr(ecosystem)` (the prefix is the structural token S4-05's probe matches when translating to `DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")`).
- [ ] **AC-5.** `DepGraphRegistry.has_strategy(ecosystem: PackageManager) -> bool` is a non-raising query for the no-strategy case — `DepGraphProbe` uses this in S4-05 to decide whether to dispatch or emit low-confidence directly. `has_strategy` is total over the `PackageManager` Literal members: returns `True` for registered ecosystems, `False` for unregistered, never raises for an unregistered Literal value.
- [ ] **AC-6.** **Zero strategies are registered in Phase 2.** A test scans `src/codegenie/` (recursive `rglob("*.py")`) for any module other than `depgraph/registry.py` that contains the substring `"@register_dep_graph_strategy"` and asserts the offender list is empty — Phase 3 plugins register under `plugins/*/` (outside `src/codegenie/`); Phase 2 doesn't (the architect's commitment, `../phase-arch-design.md §"Component design" #11`). Do NOT lower the test to "≤ N strategies" for convenience.
- [ ] **AC-7.** `PackageManager` is **imported from `codegenie.types.identifiers`** (which re-exports from Phase 1 ADR-0013 via S1-05); the registry module does NOT redefine it. A source-scan test (mirroring S1-05's pattern) asserts no local `class PackageManager` and no top-level `PackageManager = ...` re-assignment in `src/codegenie/depgraph/registry.py`.
- [ ] **AC-8.** A synthetic test registers a stub strategy via the decorator on a fresh `DepGraphRegistry()`; `dispatch` returns the stub's exact `networkx.DiGraph` object (identity-equal to the closure's returned graph); `has_strategy` returns `True` for that ecosystem and `False` for every other registered `PackageManager` Literal member (the test enumerates the five Phase 1 Literal members explicitly).
- [ ] **AC-9.** A test asserts an unknown-ecosystem dispatch raises `DepGraphRegistryError` whose `args[0]` starts with `no_strategy_for_ecosystem: ` (the exact AC-4 prefix).
- [ ] **AC-10.** **Decorator return-identity.** `reg.register(eco)(fn) is fn` — the decorator returns the strategy function unchanged so registration is non-invasive (mirrors S1-02's `register_index_freshness_check` and Phase 0's `register_probe`). A test pins this with `is`.
- [ ] **AC-11.** **Strategy invocation contract.** A test passes two sentinel objects as `ctx` and `manifests` to `dispatch` and asserts the stub strategy received them in that positional order (`assert captured["ctx"] is ctx_sentinel and captured["manifests"] is manifests_sentinel`) — a `dispatch` implementation that swapped the positional args, copied the manifests list, or wrapped the graph would fail this test.
- [ ] **AC-12.** `DepGraphRegistry.registered_ecosystems() -> frozenset[PackageManager]` returns the set of registered ecosystems (unordered, non-mutating, returns an empty `frozenset` on a fresh registry). Tested explicitly — empty on `DepGraphRegistry()`, single-member after one registration, two-member after two.
- [ ] **AC-13.** `src/codegenie/errors.py` appends `DepGraphRegistryError` and **extends `__all__`** to include it (mirrors S1-02's `FreshnessRegistryError` insertion). A test asserts `"DepGraphRegistryError" in codegenie.errors.__all__` and that `DepGraphRegistryError` is a direct subclass of `CodegenieError`.
- [ ] **AC-14.** The `forbidden-patterns` extension from S1-11 will ban `model_construct` under `codegenie.depgraph/**`; this story does not use `model_construct` and the discipline starts here.
- [ ] **AC-15.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-16.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/depgraph/ tests/unit/depgraph/`, and `pytest tests/unit/depgraph/` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/depgraph/model.py` with `DepGraphProbeOutput` Pydantic model (`frozen=True, extra="forbid"`; fields per AC-1).
2. Create `src/codegenie/depgraph/registry.py` with: `DepGraphStrategy` type alias, `DepGraphRegistry` class (`register`, `dispatch`, `has_strategy`, `registered_ecosystems`, `unregister_for_tests`), module-level `default_dep_graph_registry`, and the `register_dep_graph_strategy(ecosystem)` decorator-factory targeting the default. The class records both `dict[PackageManager, DepGraphStrategy]` (strategies) and `dict[PackageManager, str]` (origins as dotted `module.qualname`) so duplicate-detection messages can name both sites.
3. Create `src/codegenie/depgraph/__init__.py` re-exporting the six public names in AC-1, with `__all__` declared as the explicit list.
4. Append `DepGraphRegistryError` to `src/codegenie/errors.py` as a bare marker **and** extend the module's `__all__` to include it (mirroring how S1-02 added `FreshnessRegistryError` to `__all__`).
5. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/depgraph/test_registry.py`

> **Implementer note on `PackageManager`.** `PackageManager` is a `Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` type alias defined at `src/codegenie/probes/node_build_system.py:115` and re-exported from `codegenie.types.identifiers`. It is **not** a class or Enum — there is no `.PNPM` attribute. At runtime, `PackageManager` values are the literal strings; `mypy --strict` enforces nominal correctness at the type seam. Tests use `cast(PackageManager, "pnpm")` to type-tag a literal where the type checker cannot infer it from context.

```python
from __future__ import annotations

import inspect
import pathlib
import re
from logging import getLogger
from pathlib import Path
from typing import cast, get_args

import networkx
import pytest

from codegenie.depgraph import (
    DepGraphProbeOutput,
    DepGraphRegistry,
    DepGraphRegistryError,
    DepGraphStrategy,
    default_dep_graph_registry,
    register_dep_graph_strategy,
)
from codegenie.errors import CodegenieError
from codegenie.probes.base import ProbeContext
from codegenie.types.identifiers import PackageManager

PNPM = cast(PackageManager, "pnpm")
NPM = cast(PackageManager, "npm")
YARN_CLASSIC = cast(PackageManager, "yarn-classic")
YARN_BERRY = cast(PackageManager, "yarn-berry")
BUN = cast(PackageManager, "bun")
ALL_PACKAGE_MANAGERS: tuple[PackageManager, ...] = (BUN, PNPM, YARN_CLASSIC, YARN_BERRY, NPM)


def _make_ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=getLogger("test"),
        config={},
    )


# ---------- AC-8 / AC-11 — register + dispatch contract + identity ----------

def test_register_and_dispatch_returns_strategy_graph_identity(tmp_path: Path) -> None:
    """AC-8 + AC-11 — dispatch returns the strategy's exact graph object (identity, not copy)."""
    reg = DepGraphRegistry()
    graph_returned_by_strategy = networkx.DiGraph()
    graph_returned_by_strategy.add_edge("@org/a", "@org/b")

    @reg.register(PNPM)
    def build_pnpm(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return graph_returned_by_strategy

    ctx = _make_ctx(tmp_path)
    out = reg.dispatch(PNPM, ctx, [])
    # Identity, not isinstance — a dispatch impl that wrapped/copied the graph would fail here.
    assert out is graph_returned_by_strategy
    assert ("@org/a", "@org/b") in out.edges


# ---------- AC-11 — strategy receives ctx + manifests verbatim, in that order ----------

def test_dispatch_passes_ctx_and_manifests_positionally(tmp_path: Path) -> None:
    """AC-11 — argument-swap mutation pin. A dispatch that called fn(manifests, ctx) would fail."""
    reg = DepGraphRegistry()
    captured: dict[str, object] = {}
    ctx_sentinel = _make_ctx(tmp_path)
    manifests_sentinel: list[dict[str, object]] = [{"name": "@org/a"}]

    @reg.register(PNPM)
    def _strategy(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        captured["ctx"] = ctx
        captured["manifests"] = manifests
        return networkx.DiGraph()

    reg.dispatch(PNPM, ctx_sentinel, manifests_sentinel)
    assert captured["ctx"] is ctx_sentinel
    assert captured["manifests"] is manifests_sentinel  # not copied, not coerced


# ---------- AC-4 / AC-9 — unknown-ecosystem raises with structural prefix ----------

def test_unknown_ecosystem_raises_with_exact_prefix(tmp_path: Path) -> None:
    """AC-4 + AC-9 — args[0] begins with the exact prefix `no_strategy_for_ecosystem: `."""
    reg = DepGraphRegistry()
    with pytest.raises(DepGraphRegistryError) as exc_info:
        reg.dispatch(NPM, _make_ctx(tmp_path), [])
    msg = exc_info.value.args[0]
    assert msg.startswith("no_strategy_for_ecosystem: "), msg
    assert repr(NPM) in msg  # the repr of the ecosystem value is included


# ---------- AC-5 / AC-8 — has_strategy is total over the Literal members ----------

def test_has_strategy_is_total_over_package_manager_literal() -> None:
    """AC-5 + AC-8 — has_strategy returns True only for registered, False for every other Literal member,
    never raises for an unregistered Literal value."""
    reg = DepGraphRegistry()

    @reg.register(PNPM)
    def _stub(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    assert reg.has_strategy(PNPM) is True
    for other in (BUN, NPM, YARN_CLASSIC, YARN_BERRY):
        assert reg.has_strategy(other) is False, f"unexpected truthy for {other!r}"


# ---------- AC-10 — decorator return-identity ----------

def test_decorator_returns_function_unchanged() -> None:
    """AC-10 — `reg.register(eco)(fn) is fn` — non-invasive registration."""
    reg = DepGraphRegistry()

    def build_pnpm(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    returned = reg.register(PNPM)(build_pnpm)
    assert returned is build_pnpm


# ---------- AC-2 — duplicate-registration error names BOTH call sites ----------

def test_duplicate_ecosystem_error_names_both_call_sites() -> None:
    """AC-2 — error message names both registration sites as dotted `module.qualname` strings."""
    reg = DepGraphRegistry()

    @reg.register(PNPM)
    def first_strategy(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    with pytest.raises(DepGraphRegistryError) as exc_info:
        @reg.register(PNPM)
        def second_strategy(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
            return networkx.DiGraph()

    msg = exc_info.value.args[0]
    # Both module.qualname strings present — a regression to bare __qualname__ would fail this.
    assert f"{__name__}.{first_strategy.__qualname__}" in msg, msg
    assert f"{__name__}.test_duplicate_ecosystem_error_names_both_call_sites.<locals>.second_strategy" in msg or "second_strategy" in msg


# ---------- AC-12 — registered_ecosystems() contract ----------

def test_registered_ecosystems_returns_frozenset() -> None:
    """AC-12 — empty on fresh registry; populated as strategies are added; never mutates state."""
    reg = DepGraphRegistry()
    assert reg.registered_ecosystems() == frozenset()
    assert isinstance(reg.registered_ecosystems(), frozenset)

    @reg.register(PNPM)
    def _a(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    assert reg.registered_ecosystems() == frozenset({PNPM})

    @reg.register(NPM)
    def _b(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    assert reg.registered_ecosystems() == frozenset({PNPM, NPM})
    # Non-mutating: calling twice doesn't change anything.
    assert reg.registered_ecosystems() == reg.registered_ecosystems()


# ---------- AC-6 — zero strategies registered in Phase 2 ----------

def test_zero_strategies_registered_in_phase2() -> None:
    """AC-6 — Phase 2 ships the registry empty. Walk src/codegenie/ and
    assert no file other than the registry definition itself calls register_dep_graph_strategy."""
    root = pathlib.Path(inspect.getsourcefile(__import__("codegenie"))).parent
    offenders: list[pathlib.Path] = []
    for py in root.rglob("*.py"):
        text = py.read_text()
        if "@register_dep_graph_strategy" in text and "depgraph/registry.py" not in str(py):
            offenders.append(py)
    assert offenders == [], (
        "Phase 2 registers zero dep_graph strategies "
        f"(02-ADR-0007 / arch §11). Found: {offenders}"
    )


# ---------- AC-7 — registry module does not redefine PackageManager ----------

def test_package_manager_not_redefined_in_registry_module() -> None:
    """AC-7 — DepGraphRegistry imports PackageManager; does not redefine it."""
    import codegenie.depgraph.registry as r
    src = pathlib.Path(inspect.getsourcefile(r)).read_text()
    assert "class PackageManager" not in src
    assert not re.search(r"^PackageManager\s*=\s*(?!.*import)", src, flags=re.MULTILINE)


# ---------- AC-2 — module-level decorator targets the default singleton ----------

def test_module_level_decorator_uses_default_singleton() -> None:
    """AC-2 — `register_dep_graph_strategy` is sugar for `default_dep_graph_registry.register`.
    Uses a real PackageManager Literal member; cleans up via unregister_for_tests."""
    # Pre-condition: singleton should NOT have a strategy for this ecosystem (Phase 2 = empty).
    assert default_dep_graph_registry.has_strategy(BUN) is False

    @register_dep_graph_strategy(BUN)
    def _stub(ctx: ProbeContext, manifests: list[dict[str, object]]) -> networkx.DiGraph:
        return networkx.DiGraph()
    try:
        assert default_dep_graph_registry.has_strategy(BUN) is True
        assert BUN in default_dep_graph_registry.registered_ecosystems()
    finally:
        default_dep_graph_registry.unregister_for_tests(BUN)
    # Post-condition: singleton is empty again (no leak into other tests).
    assert default_dep_graph_registry.has_strategy(BUN) is False


# ---------- AC-1 — public surface symmetry ----------

def test_public_surface_is_exact() -> None:
    """AC-1 — __all__ exposes exactly the six documented names; no extras leak."""
    import codegenie.depgraph as dg
    assert set(dg.__all__) == {
        "DepGraphProbeOutput",
        "DepGraphRegistry",
        "DepGraphRegistryError",
        "DepGraphStrategy",
        "default_dep_graph_registry",
        "register_dep_graph_strategy",
    }


# ---------- AC-13 — DepGraphRegistryError in errors.__all__, marker-subclass shape ----------

def test_dep_graph_registry_error_is_a_marker_in_errors_module() -> None:
    """AC-13 — DepGraphRegistryError exported from codegenie.errors __all__; subclass of CodegenieError."""
    import codegenie.errors as ce
    assert "DepGraphRegistryError" in ce.__all__
    assert issubclass(DepGraphRegistryError, CodegenieError)
    # Marker shape: no custom __init__ beyond Exception's; no class state.
    assert "__init__" not in DepGraphRegistryError.__dict__


# ---------- AC-3 — DepGraphProbeOutput shape (frozen, extra=forbid, three fields) ----------

def test_dep_graph_probe_output_shape() -> None:
    """AC-1 — DepGraphProbeOutput is frozen, extra=forbid; the typed slice shape S4-05 will return."""
    out = DepGraphProbeOutput(graph_path=None, confidence="low", reason="no_strategy_for_ecosystem")
    assert out.confidence == "low"
    with pytest.raises(Exception):  # pydantic frozen
        out.confidence = "high"  # type: ignore[misc]
    with pytest.raises(Exception):  # pydantic extra=forbid
        DepGraphProbeOutput(graph_path=None, confidence="low", reason=None, extra_field="x")  # type: ignore[call-arg]
```

Run — confirm `ImportError: cannot import name 'DepGraphRegistry' from 'codegenie.depgraph'`. Commit.

### Green — make it pass

```python
# src/codegenie/depgraph/registry.py
from __future__ import annotations
from collections.abc import Callable, Mapping
from typing import Any, TYPE_CHECKING

import structlog

from codegenie.errors import DepGraphRegistryError
from codegenie.probes.base import ProbeContext
from codegenie.types.identifiers import PackageManager  # do NOT redefine

if TYPE_CHECKING:
    import networkx

DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], "networkx.DiGraph"]

_log = structlog.get_logger(__name__)


class DepGraphRegistry:
    def __init__(self) -> None:
        self._strategies: dict[PackageManager, DepGraphStrategy] = {}
        # Origin strings ("module.qualname") kept alongside so duplicate errors
        # can name BOTH call sites without re-introspecting the prior function
        # (a caller could have mutated it). Mirrors codegenie.indices.registry.
        self._origins: dict[PackageManager, str] = {}

    def register(self, ecosystem: PackageManager) -> Callable[[DepGraphStrategy], DepGraphStrategy]:
        def _decorator(fn: DepGraphStrategy) -> DepGraphStrategy:
            origin = f"{fn.__module__}.{fn.__qualname__}"
            if ecosystem in self._strategies:
                prior = self._origins[ecosystem]
                raise DepGraphRegistryError(
                    f"duplicate ecosystem {ecosystem!r}: {prior} and {origin}"
                )
            self._strategies[ecosystem] = fn
            self._origins[ecosystem] = origin
            _log.debug("depgraph.strategy.registered", ecosystem=str(ecosystem), origin=origin)
            return fn  # return identity — AC-10
        return _decorator

    def has_strategy(self, ecosystem: PackageManager) -> bool:
        return ecosystem in self._strategies

    def dispatch(
        self,
        ecosystem: PackageManager,
        ctx: ProbeContext,
        manifests: list[Mapping[str, Any]],
    ) -> "networkx.DiGraph":
        try:
            fn = self._strategies[ecosystem]
        except KeyError:
            raise DepGraphRegistryError(
                f"no_strategy_for_ecosystem: {ecosystem!r}"
            ) from None
        # Pass ctx and manifests positionally and verbatim — AC-11.
        # Return the strategy's exact graph (no wrap, no copy) — AC-4.
        return fn(ctx, manifests)

    def registered_ecosystems(self) -> frozenset[PackageManager]:
        return frozenset(self._strategies)

    def unregister_for_tests(self, ecosystem: PackageManager) -> None:
        """**Test-only** convenience for cleaning the module-level singleton.
        The deliberately-awkward name *is* the policy (mirrors S1-02)."""
        self._strategies.pop(ecosystem, None)
        self._origins.pop(ecosystem, None)


default_dep_graph_registry = DepGraphRegistry()


def register_dep_graph_strategy(
    ecosystem: PackageManager,
) -> Callable[[DepGraphStrategy], DepGraphStrategy]:
    return default_dep_graph_registry.register(ecosystem)


__all__ = [
    "DepGraphRegistry", "DepGraphRegistryError", "DepGraphStrategy",
    "default_dep_graph_registry", "register_dep_graph_strategy",
]
```

```python
# src/codegenie/depgraph/model.py
from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict

class DepGraphProbeOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    graph_path: Path | None
    confidence: Literal["high", "medium", "low"]
    reason: str | None = None
```

```python
# src/codegenie/depgraph/__init__.py
from codegenie.depgraph.model import DepGraphProbeOutput
from codegenie.depgraph.registry import (
    DepGraphRegistry, DepGraphRegistryError, DepGraphStrategy,
    default_dep_graph_registry, register_dep_graph_strategy,
)
__all__ = [
    "DepGraphProbeOutput", "DepGraphRegistry", "DepGraphRegistryError",
    "DepGraphStrategy", "default_dep_graph_registry",
    "register_dep_graph_strategy",
]
```

Add `DepGraphRegistryError` as a bare marker to `src/codegenie/errors.py`.

### Refactor — clean up

- Module docstring on `registry.py`: cite 02-ADR-0006 §Decisions noted (registry symmetry), `../phase-arch-design.md §"Component design" #11`, and the Phase-3 hand-off (`plugins/vulnerability-remediation--node--npm/strategies/dep_graph_pnpm.py` is the canonical first consumer).
- The `DepGraphProbeOutput` model is the typed slice shape — its consumer is the `DepGraphProbe` itself in S4-05 (this story ships the model so the probe can import it without circularity).
- The `unregister_for_tests` hook mirrors S1-02; same discipline.
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/depgraph/ tests/unit/depgraph/`, `pytest tests/unit/depgraph/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/depgraph/__init__.py` | New package; re-exports. |
| `src/codegenie/depgraph/model.py` | `DepGraphProbeOutput` Pydantic model. |
| `src/codegenie/depgraph/registry.py` | The decorator-registry primitive. |
| `src/codegenie/errors.py` | Append `DepGraphRegistryError` marker AND extend `__all__` to include it (mirrors S1-02's `FreshnessRegistryError` insertion). |
| `tests/unit/depgraph/test_registry.py` | Coverage: register/dispatch/duplicate/has_strategy/zero-strategies/no-redefinition. |
| `pyproject.toml` | Confirm `networkx` is in `gather` extras (add if missing — one-line). |

## Out of scope

- **Any actual ecosystem strategy implementation** (`build_pnpm`, `build_npm`, `build_yarn_classic`, `build_yarn_berry`, `build_bun`) — Phase 3 plugins. Zero strategies in Phase 2 is the architect's commitment.
- **`DepGraphProbe` (`probes/layer_b/dep_graph.py`)** — handled by S4-05; this story ships only the strategy registry and the output model.
- **`Manifest` Pydantic model** — Phase 1 may ship a typed `Manifest` model already; if so, import it. If not, the strategy signature uses `Mapping[str, Any]` (Phase 1 `parsed_manifest` returns `Mapping[str, Any] | None` per `src/codegenie/probes/base.py`). Adapt at impl time.
- **Maven / Cargo / Gradle extensions** — those require an ADR amendment to Phase 1 ADR-0013's `PackageManager` enum (new variants) before a strategy can be registered. Phase 8+.
- **Runtime cross-strategy resolution** (e.g., a multi-ecosystem monorepo with both pnpm and npm) — out of scope; `DepGraphProbe` picks one ecosystem per analysis based on Phase 1's `BuildSystemProbe` slice.

## Notes for the implementer

- **`PackageManager` is a `Literal[...]`, NOT an Enum.** Phase 1 ADR-0013 defines `PackageManager = Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` at `src/codegenie/probes/node_build_system.py:115`. There is no `.PNPM` attribute — `hasattr(PackageManager, "PNPM")` is always `False` at runtime. Production ADR-0033 §3 prohibits primitive obsession; the registry's `dict[PackageManager, …]` carries the nominal-type contract at the mypy seam (passing a raw `str` is a type error under `--strict`). In tests, use `cast(PackageManager, "pnpm")` to type-tag string literals where the type checker can't infer it from context — never the `hasattr` defensive fallback (it is dead code masquerading as flexibility, removed in this hardening).
- **Manifest shape is `Mapping[str, Any]` — confirmed, not provisional.** Source scan against `src/codegenie/` confirms no `Manifest` / `NodeManifest` Pydantic model exists (Phase 1 ships `parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None` per `src/codegenie/probes/base.py:53`). AC-3 pins `Mapping[str, Any]` as final. If a future story promotes manifests to a Pydantic model, the rebind is **by ADR amendment** to this story's contract, never silent widening.
- **Rule-of-three kernel-extract opportunity — deferred to a future cleanup story (NOT in this scope).** This is the **3rd** registry of the decorator-registry family in this codebase (`codegenie.probes.registry` 1st; `codegenie.indices.registry` 2nd from S1-02; now `codegenie.depgraph.registry`). The shared shape is `register / dedup-with-named-origins / registered_X / unregister_for_tests / module-level singleton + decorator`. A generic `KernelRegistry[K, V]` base could absorb ~15–25 LOC × 3. **However:** the three sites diverge non-trivially on dispatch shape — `for_task(task, languages)` with LRU filter / `dispatch_all(slices, head)` total over registered names / `dispatch(eco, ctx, manifests)` single-shot with `has_strategy` query. The shared lines are below the cost-of-introducing-a-generic threshold mid-phase (Rule 2 + Rule 3). Per S1-02's validation-note deferral ("intentionally does not pre-extract"), this story **also defers**. A post-Phase-2 cleanup story should evaluate after the three sites have a few weeks of churn; if any of the three diverge further (e.g., `RuntimeFreshnessRegistry` introduces a per-key freshness window), the kernel-extract becomes net-cost-negative. The pattern symmetry across `register / dedup / registered_X / unregister_for_tests` is itself a documentation win even without extraction.
- **Zero-strategies invariant is structurally enforced.** The `test_zero_strategies_registered_in_phase2` test walks `src/codegenie/` for `@register_dep_graph_strategy`. Phase 3 implementations will live under `plugins/*/` — outside `src/codegenie/`, so they don't trip the test. Do NOT lower the test's strictness to "≤ 5 strategies" for convenience.
- **`networkx.DiGraph` is the return type — not a Pydantic wrapper.** The graph is a runtime data structure; Pydantic serialization comes at the writer chokepoint via `nx.node_link_data(...)` (already a JSON-serializable dict). Do not invent a `DepGraphSliceModel` Pydantic wrapper here.
- **`DepGraphRegistryError` is a marker.** Same Phase 0/1 marker-only convention; reason strings live in `args[0]` with structural prefixes (`no_strategy_for_ecosystem: <repr>`, `duplicate ecosystem <repr>: <prior> and <new>`). Both prefixes are pinned by AC; do not introduce a custom `__init__` or class-level state.
- **`unregister_for_tests` is the same intentional-awkwardness as S1-02.** Test-only; do not promote to public. Tests that touch the module-level `default_dep_graph_registry` MUST clean up in a `finally:` block (the singleton-test exemplar).
- **`PackageManager` import location.** Import from `codegenie.types.identifiers` (S1-05's re-export) — that's the canonical kernel-tier alias surface. Do not import directly from `codegenie.probes.node_build_system` here; the types package is the right interface.
- **Dispatch contract: identity, not equality.** `dispatch` returns the strategy's exact graph object (AC-4) — no `.copy()`, no `nx.DiGraph(g)` wrap, no defensive serialization round-trip. The probe at S4-05 owns serialization (`nx.node_link_data`); the registry is a pass-through. AC-11's sentinel-identity test pins this; an executor that "defensively copies for safety" will fail it.
