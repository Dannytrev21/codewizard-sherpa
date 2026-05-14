# Story S1-10 — `codegenie.depgraph` package + `@register_dep_graph_strategy` registry

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** S
**Depends on:** S1-05
**ADRs honored:** production ADR-0033 (typed identifiers), 02-ADR-0006 §Decisions noted (registry symmetry)

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

- [ ] **AC-1.** `src/codegenie/depgraph/__init__.py` exports `register_dep_graph_strategy`, `default_dep_graph_registry`, `DepGraphRegistry`, `DepGraphStrategy` (type alias), `DepGraphRegistryError`, and a `DepGraphProbeOutput` Pydantic model (frozen, the typed slice shape — fields: `graph_path: Path | None`, `confidence: Literal["high","medium","low"]`, `reason: str | None`).
- [ ] **AC-2.** `@register_dep_graph_strategy(ecosystem: PackageManager)` is a decorator-factory; registers the function in `default_dep_graph_registry`; duplicate-ecosystem registration raises `DepGraphRegistryError` at import time.
- [ ] **AC-3.** `DepGraphStrategy` type alias is exactly `Callable[[ProbeContext, list[Mapping[str, Any]]], "networkx.DiGraph"]` (the manifest list is `parsed_manifest` outputs from Phase 1; ADR-0033 §3 says use the actual `Manifest` Pydantic model if Phase 1 ships one — adapt at impl time).
- [ ] **AC-4.** `DepGraphRegistry.dispatch(ecosystem: PackageManager, ctx, manifests) -> networkx.DiGraph` invokes the registered strategy; unknown ecosystem → `raise DepGraphRegistryError(f"no_strategy_for_ecosystem: {ecosystem}")`. (The probe at S4-05 catches and translates to `DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")`; the registry itself raises.)
- [ ] **AC-5.** `DepGraphRegistry.has_strategy(ecosystem: PackageManager) -> bool` is a non-raising query — `DepGraphProbe` uses this in S4-05 to decide whether to dispatch or emit low-confidence directly.
- [ ] **AC-6.** **Zero strategies are registered in Phase 2.** A test scans `src/codegenie/` for any module that calls `register_dep_graph_strategy` and asserts `len(matches) == 0` — Phase 3 plugins register; Phase 2 doesn't (the architect's commitment, `../phase-arch-design.md §"Component design" #11`).
- [ ] **AC-7.** `PackageManager` is **imported from `codegenie.types.identifiers`** (which re-exports from Phase 1 ADR-0013 via S1-05); the registry module does NOT redefine it (a source-scan test like S1-05's asserts no local `class PackageManager` or `PackageManager =` reassignment in `registry.py`).
- [ ] **AC-8.** A synthetic test registers a stub strategy via the decorator on a fresh `DepGraphRegistry()`; `dispatch` returns the stub's `networkx.DiGraph`; `has_strategy` returns `True` for that ecosystem and `False` for every other.
- [ ] **AC-9.** A test asserts an unknown-ecosystem dispatch raises `DepGraphRegistryError` with `no_strategy_for_ecosystem` in `args[0]`.
- [ ] **AC-10.** The `forbidden-patterns` extension from S1-11 will ban `model_construct` under `codegenie.depgraph/**`; this story does not use `model_construct` and the discipline starts here.
- [ ] **AC-11.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/depgraph/` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/depgraph/model.py` with `DepGraphProbeOutput` Pydantic model (`frozen=True, extra="forbid"`).
2. Create `src/codegenie/depgraph/registry.py` with: `DepGraphRegistryError` (marker subclass of `CodegenieError`), `DepGraphStrategy` type alias, `DepGraphRegistry` class (`register`, `dispatch`, `has_strategy`, `registered_ecosystems`), module-level `default_dep_graph_registry`, and the `register_dep_graph_strategy(ecosystem)` decorator-factory targeting the default.
3. Create `src/codegenie/depgraph/__init__.py` re-exporting all public names.
4. Append `DepGraphRegistryError` to `src/codegenie/errors.py` as a bare marker.
5. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/depgraph/test_registry.py`

```python
from __future__ import annotations

import inspect
import pathlib
import re
from logging import getLogger
from pathlib import Path

import networkx
import pytest

from codegenie.depgraph import (
    DepGraphRegistry,
    DepGraphRegistryError,
    DepGraphStrategy,
    register_dep_graph_strategy,
)
from codegenie.probes.base import ProbeContext
from codegenie.types.identifiers import PackageManager


def _make_ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=getLogger("test"),
        config={},
    )


def test_register_and_dispatch_pnpm_strategy(tmp_path: Path) -> None:
    reg = DepGraphRegistry()

    @reg.register(PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm")
    def build_pnpm(ctx, manifests):
        g = networkx.DiGraph()
        g.add_edge("@org/a", "@org/b")
        return g

    g = reg.dispatch(
        PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm",
        _make_ctx(tmp_path),
        [],
    )
    assert isinstance(g, networkx.DiGraph)
    assert ("@org/a", "@org/b") in g.edges


def test_unknown_ecosystem_raises(tmp_path: Path) -> None:
    reg = DepGraphRegistry()
    with pytest.raises(DepGraphRegistryError) as exc_info:
        reg.dispatch(
            PackageManager.NPM if hasattr(PackageManager, "NPM") else "npm",
            _make_ctx(tmp_path),
            [],
        )
    assert "no_strategy_for_ecosystem" in exc_info.value.args[0]


def test_has_strategy_query_does_not_raise() -> None:
    reg = DepGraphRegistry()

    @reg.register(PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm")
    def _stub(ctx, manifests):
        return networkx.DiGraph()

    assert reg.has_strategy(PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm") is True
    assert reg.has_strategy(PackageManager.NPM if hasattr(PackageManager, "NPM") else "npm") is False


def test_duplicate_ecosystem_rejected_at_registration_time() -> None:
    reg = DepGraphRegistry()
    eco = PackageManager.PNPM if hasattr(PackageManager, "PNPM") else "pnpm"

    @reg.register(eco)
    def a(ctx, manifests):
        return networkx.DiGraph()

    with pytest.raises(DepGraphRegistryError):
        @reg.register(eco)
        def b(ctx, manifests):
            return networkx.DiGraph()


def test_zero_strategies_registered_in_phase2() -> None:
    """AC-6 — Phase 2 ships the registry empty. Walk src/codegenie/ and
    assert no file calls register_dep_graph_strategy."""
    root = pathlib.Path(inspect.getsourcefile(__import__("codegenie"))).parent
    offenders: list[pathlib.Path] = []
    for py in root.rglob("*.py"):
        text = py.read_text()
        # Match the decorator usage; skip the registry module itself + tests.
        if "@register_dep_graph_strategy" in text and "depgraph/registry.py" not in str(py):
            offenders.append(py)
    assert offenders == [], (
        "Phase 2 registers zero dep_graph strategies "
        f"(02-ADR-0007 / arch §11). Found: {offenders}"
    )


def test_package_manager_not_redefined_in_registry_module() -> None:
    """AC-7 — DepGraphRegistry imports PackageManager; does not redefine it."""
    import codegenie.depgraph.registry as r
    src = pathlib.Path(inspect.getsourcefile(r)).read_text()
    assert "class PackageManager" not in src
    assert not re.search(r"^PackageManager\s*=\s*(?!.*import)", src, flags=re.MULTILINE)


def test_module_level_decorator_uses_default_singleton() -> None:
    from codegenie.depgraph import default_dep_graph_registry
    eco_value = "__test_singleton_eco__"  # bypass PackageManager nominal type at runtime

    @register_dep_graph_strategy(eco_value)  # type: ignore[arg-type]
    def _stub(ctx, manifests):
        return networkx.DiGraph()
    try:
        assert default_dep_graph_registry.has_strategy(eco_value)
    finally:
        default_dep_graph_registry.unregister_for_tests(eco_value)
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
        self._origins: dict[PackageManager, str] = {}

    def register(self, ecosystem: PackageManager) -> Callable[[DepGraphStrategy], DepGraphStrategy]:
        def _decorator(fn: DepGraphStrategy) -> DepGraphStrategy:
            if ecosystem in self._strategies:
                prior = self._origins[ecosystem]
                raise DepGraphRegistryError(
                    f"duplicate ecosystem {ecosystem!r}: {prior} and "
                    f"{fn.__module__}.{fn.__qualname__}"
                )
            self._strategies[ecosystem] = fn
            self._origins[ecosystem] = f"{fn.__module__}.{fn.__qualname__}"
            _log.debug("depgraph.strategy.registered", ecosystem=str(ecosystem))
            return fn
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
        return fn(ctx, manifests)

    def registered_ecosystems(self) -> frozenset[PackageManager]:
        return frozenset(self._strategies)

    def unregister_for_tests(self, ecosystem: PackageManager) -> None:
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
| `src/codegenie/errors.py` | Append `DepGraphRegistryError` marker; extend `__all__`. |
| `tests/unit/depgraph/test_registry.py` | Coverage: register/dispatch/duplicate/has_strategy/zero-strategies/no-redefinition. |
| `pyproject.toml` | Confirm `networkx` is in `gather` extras (add if missing — one-line). |

## Out of scope

- **Any actual ecosystem strategy implementation** (`build_pnpm`, `build_npm`, `build_yarn_classic`, `build_yarn_berry`, `build_bun`) — Phase 3 plugins. Zero strategies in Phase 2 is the architect's commitment.
- **`DepGraphProbe` (`probes/layer_b/dep_graph.py`)** — handled by S4-05; this story ships only the strategy registry and the output model.
- **`Manifest` Pydantic model** — Phase 1 may ship a typed `Manifest` model already; if so, import it. If not, the strategy signature uses `Mapping[str, Any]` (Phase 1 `parsed_manifest` returns `Mapping[str, Any] | None` per `src/codegenie/probes/base.py`). Adapt at impl time.
- **Maven / Cargo / Gradle extensions** — those require an ADR amendment to Phase 1 ADR-0013's `PackageManager` enum (new variants) before a strategy can be registered. Phase 8+.
- **Runtime cross-strategy resolution** (e.g., a multi-ecosystem monorepo with both pnpm and npm) — out of scope; `DepGraphProbe` picks one ecosystem per analysis based on Phase 1's `BuildSystemProbe` slice.

## Notes for the implementer

- **`PackageManager` is the typed registry key — strings are a review-blocker.** Production ADR-0033 §3 prohibits primitive obsession; the registry's `dict[PackageManager, …]` is what the architecture mandates. If `PackageManager` is currently a `Literal["bun","pnpm","yarn-classic","yarn-berry","npm"]` rather than an `Enum`, the keys are still type-checkable strings at the mypy boundary — but the registration *contract* says the value comes from the Phase 1 enum source, never raw user input.
- **Zero-strategies invariant is structurally enforced.** The `test_zero_strategies_registered_in_phase2` test walks `src/codegenie/` for `@register_dep_graph_strategy`. Phase 3 implementations will live under `plugins/*/` — outside `src/codegenie/`, so they don't trip the test. Do NOT lower the test's strictness to "≤ 5 strategies" for convenience.
- **`networkx.DiGraph` is the return type — not a Pydantic wrapper.** The graph is a runtime data structure; Pydantic serialization comes at the writer chokepoint via `nx.node_link_data(...)` (already a JSON-serializable dict). Do not invent a `DepGraphSliceModel` Pydantic wrapper here.
- **`DepGraphRegistryError` is a marker.** Same Phase 0/1 marker-only convention; reason strings live in `args[0]` (`no_strategy_for_ecosystem: pnpm`, `duplicate ecosystem ...`).
- **`unregister_for_tests` is the same intentional-awkwardness as S1-02.** Test-only; do not promote to public.
- **`PackageManager` import location.** Import from `codegenie.types.identifiers` (S1-05's re-export) — that's the canonical kernel-tier alias surface. Do not import directly from `codegenie.probes.node_build_system` here; the types package is the right interface.
- **`Mapping[str, Any]`-typed manifests vs. typed Manifest.** Pick the *more specific* type that exists. If Phase 1 ships `Manifest` (or `NodeManifest`), use it. The architecture (`../phase-arch-design.md §"Component design" #11 — Dependencies`) names "Phase 1 `PackageManager` enum" but is intentionally lenient on the manifest shape — adapt at impl time, document the choice in the strategy's type alias docstring.
