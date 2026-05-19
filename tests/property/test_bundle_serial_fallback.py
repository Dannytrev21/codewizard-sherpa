"""S3-04 AC-24 — serial-fallback property test.

For each query, primary completes strictly before fallback under seeded
scheduler jitter. Per-query dispatch counts are exact. Per-query
``AdapterDegraded`` event count is exactly 1.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping
from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.adapters.confidence import Degraded, Trusted
from codegenie.plugins.bundle import (
    AdapterDegraded,
    AdapterDispatch,
    AdapterResult,
    BundleBuilder,
)
from codegenie.plugins.tccm import TCCM, ContextQuery
from codegenie.types.identifiers import BlobDigest, PluginId, PrimitiveName


@dataclass(frozen=True)
class _Res:
    composed_tccm: TCCM
    composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]
    plugin_id: PluginId


class _VulnIdx:
    def digest(self) -> BlobDigest:
        return BlobDigest("c" * 64)


@settings(max_examples=50, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=10**9),
    n_queries=st.integers(min_value=1, max_value=4),
)
def test_fallback_invoked_exactly_once_with_seeded_jitter(
    seed: int, n_queries: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    rng = random.Random(seed)

    order: list[str] = []
    primary_calls = 0
    fallback_calls = 0
    events: list = []

    async def _run() -> None:
        # All n queries share the SAME two primitives — the dispatch
        # functions inspect ``query.args["i"]`` to record per-query
        # ordering. This avoids overwriting per-query closures in the
        # dispatch table when distinct primitives are scarce.
        primary_p = "scip.refs"
        fallback_p = "dep_graph.consumers"

        async def primary(query: ContextQuery) -> AdapterResult:
            nonlocal primary_calls
            primary_calls += 1
            i = query.args["i"]
            order.append(f"q{i}-primary:start")
            await asyncio.sleep(rng.uniform(0, 0.002))
            order.append(f"q{i}-primary:done")
            return AdapterResult(
                payload={"q": i},  # type: ignore[dict-item]
                confidence=Degraded(reason="stale"),
                adapter_name="primary",
            )

        async def fallback(query: ContextQuery) -> AdapterResult:
            nonlocal fallback_calls
            fallback_calls += 1
            i = query.args["i"]
            order.append(f"q{i}-fallback:start")
            await asyncio.sleep(rng.uniform(0, 0.002))
            order.append(f"q{i}-fallback:done")
            return AdapterResult(
                payload={"q": i},  # type: ignore[dict-item]
                confidence=Trusted(),
                adapter_name="fallback",
            )

        queries: list[ContextQuery] = []
        for i in range(n_queries):
            fallback_q = ContextQuery.create(
                primitive=fallback_p, args={"i": i, "kind": "fb"}
            ).unwrap()
            primary_q = ContextQuery.create(
                primitive=primary_p, args={"i": i, "kind": "p"}, fallback=fallback_q
            ).unwrap()
            queries.append(primary_q)
        table: dict[PrimitiveName, AdapterDispatch] = {
            PrimitiveName(primary_p): primary,
            PrimitiveName(fallback_p): fallback,
        }

        tccm = TCCM(must_read=queries)
        resolution = _Res(
            composed_tccm=tccm,
            composed_dispatch=table,
            plugin_id=PluginId("p"),
        )
        builder = BundleBuilder(
            cache_dir=tmp_path_factory.mktemp(f"sf-{seed}-{n_queries}"),
            event_emitter=events.append,
        )
        await builder.build(resolution, None, None, _VulnIdx())

    asyncio.run(_run())

    assert primary_calls == n_queries
    assert fallback_calls == n_queries
    degraded_events = [e for e in events if isinstance(e, AdapterDegraded)]
    assert len(degraded_events) == n_queries

    # AC-24: per-query, primary:done precedes fallback:start (robust to
    # inter-query interleaving — index check, not equality).
    for q in range(n_queries):
        i_pdone = order.index(f"q{q}-primary:done")
        i_fstart = order.index(f"q{q}-fallback:start")
        assert i_pdone < i_fstart, f"hedged-race smell q{q}: {order!r}"
