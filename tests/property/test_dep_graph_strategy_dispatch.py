"""S7-05 AC-13..AC-18 — Phase-2 zero-strategy invariant for the dep-graph registry.

Phase 2 ships **zero** registered dep-graph strategies. The registry is
the Open/Closed seam Phase 3 plugins fill. This file pins the
zero-strategy invariant via Hypothesis sampling over the closed
``PackageManager`` Literal:

- **AC-14 / AC-15** (property test) — with zero strategies registered,
  every ``PackageManager`` member raises
  :class:`DepGraphRegistryError` whose message begins with the
  documented structural prefix ``"no_strategy_for_ecosystem: "``. The
  prefix is the token :class:`codegenie.probes.layer_b.dep_graph.DepGraphProbe`
  (S4-05) matches when translating the raise into a typed
  ``confidence="low"`` slice.
- **AC-16** (non-property) — a registered mock strategy round-trips
  through dispatch with identity (no copy, no wrapper). Cleanup uses
  the registry's ``unregister_for_tests`` test-only hook (Open/Closed
  seam, **not** ``_strategies`` mutation).

Phase 3 trip-wire: when ``@register_dep_graph_strategy(<member>)`` lands
at module-import time for any production plugin, the autouse fixture's
``registered_ecosystems() == frozenset()`` assertion fires loudly,
forcing the Phase-3 author to explicitly update this file's invariants
rather than silently break them.

Phase 1 ADR-0013 owns the ``PackageManager`` Literal; the source of
truth is :mod:`codegenie.probes.node_build_system` (re-exported through
:mod:`codegenie.types.identifiers`).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, get_args

import networkx as nx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Preload the probes package before codegenie.depgraph to break the
# documented circular import (codegenie.depgraph.registry → ProbeContext
# → codegenie.probes.__init__ → codegenie.probes.layer_b.dep_graph →
# codegenie.depgraph). Other tests that touch codegenie.probes first
# happen to win this race; running tests/property/ in isolation does
# not. The side-effect import is the load-ordering contract.
import codegenie.probes  # noqa: F401 — see docstring above
from codegenie.depgraph import (
    DepGraphRegistryError,
    default_dep_graph_registry,
    register_dep_graph_strategy,
)
from codegenie.types.identifiers import PackageManager

_PACKAGE_MANAGERS: tuple[PackageManager, ...] = get_args(PackageManager)
_package_managers = st.sampled_from(_PACKAGE_MANAGERS)


@pytest.fixture(autouse=True)
def _registry_is_empty() -> Iterator[None]:
    """Phase-2 invariant: the singleton starts (and ends) empty.

    A leftover registration is the load-bearing Phase-3 trip-wire — when
    a Phase-3 plugin registers at module import, this fixture fails
    fast with a pointer to the polluter, rather than corrupting the
    property body's assumptions.
    """
    leftover = default_dep_graph_registry.registered_ecosystems()
    assert leftover == frozenset(), (
        f"depgraph singleton polluted by prior test; leftover ecosystems={leftover!r}"
    )
    yield
    trailing = default_dep_graph_registry.registered_ecosystems()
    assert trailing == frozenset(), f"test leaked a registration; trailing ecosystems={trailing!r}"


@given(ecosystem=_package_managers)
@settings(max_examples=200, deadline=None, database=None)
def test_dispatch_phase2_invariant_raises_documented_error(
    ecosystem: PackageManager,
) -> None:
    """AC-14, AC-15 — Phase-2 zero-strategy invariant.

    With zero strategies registered:

    1. ``has_strategy(member) is False`` for every member.
    2. ``dispatch(member, ctx, manifests)`` raises
       :class:`DepGraphRegistryError` (and never any other exception
       type).
    3. The error message begins with the documented structural prefix
       ``"no_strategy_for_ecosystem: "`` followed by ``repr(member)``.
    4. ``registered_ecosystems()`` remains ``frozenset()``.
    """
    assert default_dep_graph_registry.has_strategy(ecosystem) is False

    manifests: list[Mapping[str, Any]] = []
    with pytest.raises(DepGraphRegistryError) as exc_info:
        # ctx=None is acceptable here: dispatch raises *before* reading
        # ctx because the strategy lookup fails first. Type-ignored for
        # the same reason — the contract is the raise, not the typed
        # path.
        default_dep_graph_registry.dispatch(ecosystem, ctx=None, manifests=manifests)  # type: ignore[arg-type]

    msg = str(exc_info.value)
    assert msg.startswith("no_strategy_for_ecosystem: "), (
        f"missing structural prefix; got message={msg!r}"
    )
    assert repr(ecosystem) in msg, f"member repr missing from message; got {msg!r}"

    # The query mutator-resistance check: the failed dispatch did NOT
    # leave a leftover entry behind.
    assert default_dep_graph_registry.registered_ecosystems() == frozenset()


def test_mock_strategy_registers_dispatches_and_unregisters() -> None:
    """AC-16 — round-trip a mock strategy through the public seams.

    Registration via the public decorator + cleanup via
    ``unregister_for_tests`` — the only legal mutation surface. The
    other ``PackageManager`` members still raise the documented
    ``DepGraphRegistryError`` (proves scope, not global pollution).
    """
    sentinel_graph: nx.DiGraph[str] = nx.DiGraph()
    sentinel_graph.add_node("sentinel")

    call_log: list[tuple[Any, list[Mapping[str, Any]]]] = []

    def _mock_strategy(ctx: Any, manifests: list[Mapping[str, Any]]) -> nx.DiGraph[str]:
        call_log.append((ctx, manifests))
        return sentinel_graph

    target: PackageManager = "npm"
    register_dep_graph_strategy(target)(_mock_strategy)

    try:
        # Identity, not copy — pinned by S1-10 AC-11.
        result = default_dep_graph_registry.dispatch(target, ctx=None, manifests=[])  # type: ignore[arg-type]
        assert result is sentinel_graph
        assert call_log == [(None, [])]

        # has_strategy is now True for the registered member only.
        assert default_dep_graph_registry.has_strategy(target) is True

        # Every other member still raises the documented error — proves
        # the registration is scoped, not global.
        for other in _PACKAGE_MANAGERS:
            if other == target:
                continue
            with pytest.raises(DepGraphRegistryError) as exc_info:
                default_dep_graph_registry.dispatch(other, ctx=None, manifests=[])  # type: ignore[arg-type]
            assert str(exc_info.value).startswith("no_strategy_for_ecosystem: ")
    finally:
        default_dep_graph_registry.unregister_for_tests(target)
