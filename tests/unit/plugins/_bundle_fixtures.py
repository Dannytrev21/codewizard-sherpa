"""Spy fixtures for :mod:`codegenie.plugins.bundle` tests (S3-04).

The :class:`BundleResolution` Protocol surface from ``bundle.py`` is satisfied
structurally — a tiny dataclass with the three properties (``composed_tccm``,
``composed_dispatch``, ``plugin_id``) ducks cleanly, and the test code
stays readable. Production wiring is S7-02; until then these fakes hold the
seam together.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from codegenie.adapters.confidence import AdapterConfidence
from codegenie.plugins.bundle import (
    AdapterDispatch,
    AdapterResult,
    BundleResolution,
)
from codegenie.plugins.tccm import TCCM, ContextQuery
from codegenie.types.identifiers import BlobDigest, PluginId, PrimitiveName

# --- DispatchSpy ---------------------------------------------------------------


@dataclass
class DispatchSpy:
    """Async-callable spy that records call counts + optional event ordering.

    The recorded ``order_log`` lets tests pin "primary completes before
    fallback starts" without depending on wall-clock timing.
    """

    name: str
    confidence: AdapterConfidence
    payload: dict[str, Any] = field(default_factory=lambda: {"hit": "ok"})
    order_log: list[str] | None = None
    jitter_rng: random.Random | None = None
    calls: int = 0
    side_effect: BaseException | None = None

    async def __call__(self, query: ContextQuery) -> AdapterResult:
        self.calls += 1
        if self.order_log is not None:
            self.order_log.append(f"{self.name}:start")
        if self.jitter_rng is not None:
            await asyncio.sleep(self.jitter_rng.uniform(0, 0.002))
        else:
            # One scheduler hop for honesty (no synchronous resolve).
            await asyncio.sleep(0)
        if self.order_log is not None:
            self.order_log.append(f"{self.name}:done")
        if self.side_effect is not None:
            raise self.side_effect
        return AdapterResult(
            payload=self.payload,
            confidence=self.confidence,
            adapter_name=self.name,
        )


# --- Resolution stand-in -------------------------------------------------------


@dataclass(frozen=True)
class FakeResolution:
    """Minimal :class:`BundleResolution` Protocol implementation for tests."""

    composed_tccm: TCCM
    composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]
    plugin_id: PluginId


@dataclass(frozen=True)
class FakeVulnIndex:
    """Minimal ``vuln_index.digest()`` Protocol stand-in."""

    _digest: BlobDigest = BlobDigest("a" * 64)

    def digest(self) -> BlobDigest:
        return self._digest


def _make_dispatch(
    name: str,
    confidence: AdapterConfidence,
    *,
    payload: dict[str, Any] | None = None,
    order_log: list[str] | None = None,
    jitter_rng: random.Random | None = None,
    side_effect: BaseException | None = None,
) -> DispatchSpy:
    return DispatchSpy(
        name=name,
        confidence=confidence,
        payload=payload if payload is not None else {"hit": "ok"},
        order_log=order_log,
        jitter_rng=jitter_rng,
        side_effect=side_effect,
    )


def _make_query(
    primitive: str = "scip.refs",
    args: dict[str, Any] | None = None,
    fallback: ContextQuery | None = None,
) -> ContextQuery:
    """Construct a ``ContextQuery`` via the smart-constructor; raise on err."""

    if args is None:
        args = {"q": "ok"}
    res = ContextQuery.create(primitive=primitive, args=args, fallback=fallback)
    if res.is_err():
        raise AssertionError(f"ContextQuery.create failed: {res}")
    return res.unwrap()


# --- Resolution-builder helpers ----------------------------------------------


def _resolution_with_one_query_and_fallback(
    primary_dispatch: AdapterDispatch,
    fallback_dispatch: AdapterDispatch,
    *,
    primary_primitive: str = "scip.refs",
    fallback_primitive: str = "dep_graph.consumers",
) -> FakeResolution:
    """Single ``must_read`` query whose ``fallback`` points at a second primitive."""

    fallback_q = _make_query(primitive=fallback_primitive, args={"q": "fb"})
    primary_q = _make_query(primitive=primary_primitive, args={"q": "pri"}, fallback=fallback_q)
    tccm = TCCM(must_read=[primary_q])
    dispatch_table: dict[PrimitiveName, AdapterDispatch] = {
        PrimitiveName(primary_primitive): primary_dispatch,
        PrimitiveName(fallback_primitive): fallback_dispatch,
    }
    return FakeResolution(
        composed_tccm=tccm,
        composed_dispatch=dispatch_table,
        plugin_id=PluginId("test-plugin"),
    )


_CHAIN_PRIMITIVES = (
    "scip.refs",
    "dep_graph.consumers",
    "import_graph.reverse_lookup",
    "import_graph.transitive_callers",
    "test_inventory.tests_exercising",
)


def _resolution_with_chain(dispatches: list[AdapterDispatch]) -> FakeResolution:
    """Build a resolution whose root query has a fallback chain of length
    ``len(dispatches)``. Each link uses a distinct ADR-0030 primitive name so
    the dispatch table is unambiguous."""

    if len(dispatches) > len(_CHAIN_PRIMITIVES):
        raise AssertionError(
            f"chain length {len(dispatches)} exceeds available primitives {len(_CHAIN_PRIMITIVES)}"
        )
    # Build the chain from leaf up so each ``fallback`` is already constructed.
    current: ContextQuery | None = None
    for i in reversed(range(len(dispatches))):
        primitive = _CHAIN_PRIMITIVES[i]
        current = _make_query(primitive=primitive, args={"i": i}, fallback=current)
    assert current is not None
    tccm = TCCM(must_read=[current])
    dispatch_table: dict[PrimitiveName, AdapterDispatch] = {
        PrimitiveName(_CHAIN_PRIMITIVES[i]): dispatches[i] for i in range(len(dispatches))
    }
    return FakeResolution(
        composed_tccm=tccm,
        composed_dispatch=dispatch_table,
        plugin_id=PluginId("test-plugin"),
    )


def _resolution_with_n_queries(
    n: int,
    *,
    dispatch: Callable[[ContextQuery], Awaitable[AdapterResult]],
) -> FakeResolution:
    """``n`` queries on the same primitive, all routed to the same dispatch."""

    queries = [_make_query(primitive="scip.refs", args={"i": i}) for i in range(n)]
    tccm = TCCM(must_read=queries)
    return FakeResolution(
        composed_tccm=tccm,
        composed_dispatch={PrimitiveName("scip.refs"): dispatch},
        plugin_id=PluginId("test-plugin"),
    )


def _resolution_with_empty_tccm() -> FakeResolution:
    return FakeResolution(
        composed_tccm=TCCM(must_read=[], should_read=[], may_read=[]),
        composed_dispatch={},
        plugin_id=PluginId("test-plugin"),
    )


def _resolution_with_bands(
    must_read: list[tuple[str, AdapterDispatch]],
    should_read: list[tuple[str, AdapterDispatch]],
    may_read: list[tuple[str, AdapterDispatch]],
) -> FakeResolution:
    """Build a TCCM with explicit band membership. Each (primitive,
    dispatch) entry contributes a query and a dispatch-table row. The same
    primitive may appear in multiple bands with the same dispatch."""

    table: dict[PrimitiveName, AdapterDispatch] = {}
    must_q = []
    should_q = []
    may_q = []
    for i, (prim, dispatch) in enumerate(must_read):
        must_q.append(_make_query(primitive=prim, args={"band": "must", "i": i}))
        table[PrimitiveName(prim)] = dispatch
    for i, (prim, dispatch) in enumerate(should_read):
        should_q.append(_make_query(primitive=prim, args={"band": "should", "i": i}))
        table[PrimitiveName(prim)] = dispatch
    for i, (prim, dispatch) in enumerate(may_read):
        may_q.append(_make_query(primitive=prim, args={"band": "may", "i": i}))
        table[PrimitiveName(prim)] = dispatch
    tccm = TCCM(must_read=must_q, should_read=should_q, may_read=may_q)
    return FakeResolution(
        composed_tccm=tccm,
        composed_dispatch=table,
        plugin_id=PluginId("test-plugin"),
    )


def _vuln_index_fixture() -> FakeVulnIndex:
    return FakeVulnIndex()


def _assert_protocol_satisfied(resolution: FakeResolution) -> None:
    """Defensive check — ensures the dataclass actually satisfies the
    ``BundleResolution`` Protocol surface at runtime."""

    assert isinstance(resolution, BundleResolution)
