"""S1-10 — `codegenie.depgraph` decorator-registry coverage.

Pins:

* The decorator-registry primitive itself (register / dispatch /
  has_strategy / registered_ecosystems / unregister_for_tests) with the
  shape mirrored from :mod:`codegenie.indices.registry` (02-ADR-0006
  §Decisions noted — registry symmetry).
* The Open/Closed seam: Phase 2 ships **zero** registered strategies —
  enforced by a source scan of ``src/codegenie/`` (AC-6).
* The typed slice shape (:class:`DepGraphProbeOutput`) S4-05 will return
  when no strategy is registered (or when the strategy itself emits low
  confidence).

References:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-10-depgraph-strategy-registry.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Component design" #11
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
"""

from __future__ import annotations

import inspect
import pathlib
import re
from collections.abc import Mapping
from logging import getLogger
from pathlib import Path
from typing import Any

import networkx
import pytest
from pydantic import ValidationError

from codegenie.depgraph import (
    DepGraphProbeOutput,
    DepGraphRegistry,
    DepGraphRegistryError,
    default_dep_graph_registry,
    register_dep_graph_strategy,
)
from codegenie.errors import CodegenieError
from codegenie.probes.base import ProbeContext
from codegenie.types.identifiers import PackageManager

# ``PackageManager`` is a ``Literal[...]`` alias (Phase 1 ADR-0013); there is
# no ``.PNPM`` attribute. The literal string IS the value at runtime; under
# ``mypy --strict`` the bare string narrows directly to the ``Literal``
# (no ``cast`` needed — that would be a redundant-cast error).
PNPM: PackageManager = "pnpm"
NPM: PackageManager = "npm"
YARN_CLASSIC: PackageManager = "yarn-classic"
YARN_BERRY: PackageManager = "yarn-berry"
BUN: PackageManager = "bun"
ALL_PACKAGE_MANAGERS: tuple[PackageManager, ...] = (
    BUN,
    PNPM,
    YARN_CLASSIC,
    YARN_BERRY,
    NPM,
)


def _make_ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=getLogger("test"),
        config={},
    )


# ---------- AC-8 / AC-11 — register + dispatch contract + identity ----------


def test_register_and_dispatch_returns_strategy_graph_identity(
    tmp_path: Path,
) -> None:
    """AC-8 + AC-11 — dispatch returns the strategy's exact graph (no copy/wrap)."""
    reg = DepGraphRegistry()
    graph_returned_by_strategy = networkx.DiGraph()
    graph_returned_by_strategy.add_edge("@org/a", "@org/b")

    @reg.register(PNPM)
    def build_pnpm(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        return graph_returned_by_strategy

    ctx = _make_ctx(tmp_path)
    out = reg.dispatch(PNPM, ctx, [])
    # Identity, not isinstance — a dispatch impl that wrapped/copied the graph
    # would silently pass an isinstance check.
    assert out is graph_returned_by_strategy
    assert ("@org/a", "@org/b") in out.edges


# ---------- AC-11 — strategy receives ctx + manifests verbatim, in that order ----------


def test_dispatch_passes_ctx_and_manifests_positionally(tmp_path: Path) -> None:
    """AC-11 — argument-swap mutation pin. A dispatch impl that called
    fn(manifests, ctx) (swapped args) or copied the manifests list would fail.
    """
    reg = DepGraphRegistry()
    captured: dict[str, object] = {}
    ctx_sentinel = _make_ctx(tmp_path)
    manifests_sentinel: list[Mapping[str, Any]] = [{"name": "@org/a"}]

    @reg.register(PNPM)
    def _strategy(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        captured["ctx"] = ctx
        captured["manifests"] = manifests
        return networkx.DiGraph()

    reg.dispatch(PNPM, ctx_sentinel, manifests_sentinel)
    assert captured["ctx"] is ctx_sentinel
    assert captured["manifests"] is manifests_sentinel  # not copied, not coerced


# ---------- AC-4 / AC-9 — unknown-ecosystem raises with structural prefix ----------


def test_unknown_ecosystem_raises_with_exact_prefix(tmp_path: Path) -> None:
    """AC-4 + AC-9 — args[0] begins with the literal prefix
    ``no_strategy_for_ecosystem: `` followed by repr(ecosystem). The prefix
    is the structural token S4-05's probe matches when translating to
    ``DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")``.
    """
    reg = DepGraphRegistry()
    with pytest.raises(DepGraphRegistryError) as exc_info:
        reg.dispatch(NPM, _make_ctx(tmp_path), [])
    msg = exc_info.value.args[0]
    assert msg.startswith("no_strategy_for_ecosystem: "), msg
    assert repr(NPM) in msg  # the repr of the ecosystem value is included


# ---------- AC-5 / AC-8 — has_strategy is total over the Literal members ----------


def test_has_strategy_is_total_over_package_manager_literal() -> None:
    """AC-5 + AC-8 — has_strategy returns True only for registered, False for
    every other Literal member, never raises for an unregistered Literal."""
    reg = DepGraphRegistry()

    @reg.register(PNPM)
    def _stub(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    assert reg.has_strategy(PNPM) is True
    for other in (BUN, NPM, YARN_CLASSIC, YARN_BERRY):
        assert reg.has_strategy(other) is False, f"unexpected truthy for {other!r}"


# ---------- AC-10 — decorator return-identity ----------


def test_decorator_returns_function_unchanged() -> None:
    """AC-10 — ``reg.register(eco)(fn) is fn`` — non-invasive registration
    (mirrors S1-02's ``register_index_freshness_check`` and Phase 0's
    ``register_probe``)."""
    reg = DepGraphRegistry()

    def build_pnpm(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    returned = reg.register(PNPM)(build_pnpm)
    assert returned is build_pnpm


# ---------- AC-2 — duplicate-registration error names BOTH call sites ----------


def test_duplicate_ecosystem_error_names_both_call_sites() -> None:
    """AC-2 — error message names both registration sites as dotted
    ``module.qualname`` strings (operator-grep-friendly across multi-file
    plugin trees). A regression to bare ``__qualname__`` (only the new
    site) would fail this."""
    reg = DepGraphRegistry()

    @reg.register(PNPM)
    def first_strategy(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    # Define the second function *outside* the `with` block to avoid the
    # `UnboundLocalError` trap documented in `_lessons.md` §L11 — the
    # decorator raises before the assignment, so referencing
    # `second_strategy` after the block by *name* (variable) would blow
    # up. Here we reference its source-text token in the substring assert,
    # not the bound name, so the trap doesn't apply; defining it inside
    # `with` keeps the qualname tied to the test function scope.
    with pytest.raises(DepGraphRegistryError) as exc_info:

        @reg.register(PNPM)
        def second_strategy(  # noqa: F841 — qualname is the assertion target
            ctx: ProbeContext, manifests: list[Mapping[str, Any]]
        ) -> networkx.DiGraph:
            return networkx.DiGraph()

    msg = exc_info.value.args[0]
    # Both module.qualname strings present.
    assert f"{__name__}.{first_strategy.__qualname__}" in msg, msg
    assert "second_strategy" in msg, msg


# ---------- AC-12 — registered_ecosystems() contract ----------


def test_registered_ecosystems_returns_frozenset() -> None:
    """AC-12 — empty on fresh registry; populated as strategies are added;
    never mutates state. Returns ``frozenset`` (immutable, unordered)."""
    reg = DepGraphRegistry()
    assert reg.registered_ecosystems() == frozenset()
    assert isinstance(reg.registered_ecosystems(), frozenset)

    @reg.register(PNPM)
    def _a(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    assert reg.registered_ecosystems() == frozenset({PNPM})

    @reg.register(NPM)
    def _b(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
        return networkx.DiGraph()

    assert reg.registered_ecosystems() == frozenset({PNPM, NPM})
    # Non-mutating: calling twice doesn't change anything.
    assert reg.registered_ecosystems() == reg.registered_ecosystems()


# ---------- AC-6 — zero strategies registered in Phase 2 ----------


def test_zero_strategies_registered_in_phase2() -> None:
    """AC-6 — Phase 2 ships the registry empty. Walk ``src/codegenie/`` and
    assert no file other than the registry definition itself contains
    ``@register_dep_graph_strategy``. Phase 3 plugins live under
    ``plugins/*/`` (outside ``src/codegenie/``); Phase 2 doesn't register
    any strategy itself (the architect's commitment, arch §11)."""
    root = pathlib.Path(inspect.getsourcefile(__import__("codegenie")) or "").parent
    offenders: list[pathlib.Path] = []
    for py in root.rglob("*.py"):
        text = py.read_text()
        if "@register_dep_graph_strategy" in text and "depgraph/registry.py" not in str(py):
            offenders.append(py)
    assert offenders == [], (
        f"Phase 2 registers zero dep_graph strategies (arch §11). Found: {offenders}"
    )


# ---------- AC-7 — registry module does not redefine PackageManager ----------


def test_package_manager_not_redefined_in_registry_module() -> None:
    """AC-7 — DepGraphRegistry imports ``PackageManager``; does not redefine
    it. Mirrors the S1-05 pattern (production ADR-0033 §3 — primitive
    obsession is a review blocker; redefinition is the same family)."""
    import codegenie.depgraph.registry as r

    src = pathlib.Path(inspect.getsourcefile(r) or "").read_text()
    assert "class PackageManager" not in src
    # Re-assignment (not the import line itself) — the lookahead excludes
    # an `import` token on the same line.
    assert not re.search(r"^PackageManager\s*=\s*(?!.*import)", src, flags=re.MULTILINE)


# ---------- AC-2 — module-level decorator targets the default singleton ----------


def test_module_level_decorator_uses_default_singleton() -> None:
    """AC-2 — ``register_dep_graph_strategy`` is sugar for
    ``default_dep_graph_registry.register``. Uses a real ``PackageManager``
    Literal member; cleans up via ``unregister_for_tests`` so the singleton
    stays empty (zero-strategies invariant) for other tests."""
    # Pre-condition: singleton should NOT have a strategy for this ecosystem
    # (Phase 2 = empty).
    assert default_dep_graph_registry.has_strategy(BUN) is False

    @register_dep_graph_strategy(BUN)
    def _stub(ctx: ProbeContext, manifests: list[Mapping[str, Any]]) -> networkx.DiGraph:
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
    """AC-1 — ``__all__`` exposes exactly the six documented names; no
    extras leak."""
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
    """AC-13 — ``DepGraphRegistryError`` exported from
    :mod:`codegenie.errors` ``__all__``; subclass of
    :class:`CodegenieError`; marker shape (no custom ``__init__``)."""
    import codegenie.errors as ce

    assert "DepGraphRegistryError" in ce.__all__
    assert issubclass(DepGraphRegistryError, CodegenieError)
    # Marker shape: inherits __init__ from Exception/CodegenieError; no class state.
    assert "__init__" not in DepGraphRegistryError.__dict__


# ---------- AC-1 / AC-3 — DepGraphProbeOutput shape (frozen, extra=forbid, three fields) ----------


def test_dep_graph_probe_output_shape() -> None:
    """AC-1 — ``DepGraphProbeOutput`` is frozen, ``extra=forbid``, three
    fields per AC-1; the typed slice shape S4-05 will return."""
    out = DepGraphProbeOutput(graph_path=None, confidence="low", reason="no_strategy_for_ecosystem")
    assert out.confidence == "low"
    with pytest.raises(ValidationError):  # pydantic frozen
        out.confidence = "high"
    with pytest.raises(ValidationError):  # pydantic extra=forbid
        DepGraphProbeOutput(
            graph_path=None,
            confidence="low",
            reason=None,
            extra_field="x",  # type: ignore[call-arg]
        )


# ---------- AC-3 — DepGraphStrategy alias shape ----------


def test_dep_graph_strategy_alias_shape() -> None:
    """AC-3 — ``DepGraphStrategy`` is the exact
    ``Callable[[ProbeContext, list[Mapping[str, Any]]], networkx.DiGraph]``
    alias. We re-import to confirm the binding exists and is callable-shaped
    (full structural-type check is the mypy contract)."""
    from codegenie.depgraph import DepGraphStrategy

    # The alias is a typing construct, but it must be importable.
    assert DepGraphStrategy is not None
