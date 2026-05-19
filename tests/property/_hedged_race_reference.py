"""Fixture-only deliberately-broken hedged-race reference (S3-04 AC-23).

This module exists ONLY for the property-test ``xfail`` meta-test that proves
:mod:`codegenie.plugins.bundle`'s determinism property has bite. A future
regression that allows hedged-race semantics in production would also pass
this broken impl's determinism test (``xfail(strict=True)`` would then fail
loudly), telling us our property test no longer discriminates.

This module is **never** imported by production code. The fence test in
``tests/fence/test_no_hedged_race_reference_in_prod.py`` asserts that
``src/codegenie/`` contains zero string references to
``_hedged_race_reference``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from codegenie.adapters.confidence import Degraded, Trusted, Unavailable
from codegenie.plugins.bundle import (
    AdapterDispatch,
    AdapterResult,
    Bundle,
    BundleBuilder,
    BundleEntry,
    BundleResolution,
)
from codegenie.plugins.tccm import ContextQuery
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import BlobDigest, PluginId, PrimitiveName


@dataclass
class _HedgedRaceBundleBuilder:
    """Deliberately-broken reference impl that RACES primary vs fallback.

    Under scheduler jitter the winner of the race changes — so two builds
    with the same inputs return different ``Bundle`` bytes. The
    determinism property test should FAIL when run against this impl
    (proves the determinism property would catch a real regression).
    """

    cache_dir: SandboxedPath

    async def build(
        self,
        resolution: BundleResolution,
        repo_ctx: object,
        vuln: object,
        vuln_index: object,
    ) -> Bundle:
        del repo_ctx, vuln
        tccm = resolution.composed_tccm
        dispatch_table = resolution.composed_dispatch
        queries = [*tccm.must_read, *tccm.should_read, *tccm.may_read]
        entries: list[BundleEntry] = []
        for query in queries:
            entry = await self._race(query, dispatch_table)
            entries.append(entry)
        # Type-narrow vuln_index.digest()
        from codegenie.plugins.bundle import _VulnIndexLike  # noqa: PLC0415

        assert isinstance(vuln_index, _VulnIndexLike) or hasattr(vuln_index, "digest")
        return Bundle(
            entries=tuple(entries),
            plugin_id=resolution.plugin_id,
            vuln_index_digest=vuln_index.digest(),  # type: ignore[attr-defined]
        )

    async def _race(
        self,
        query: ContextQuery,
        dispatch_table: Mapping[PrimitiveName, AdapterDispatch],
    ) -> BundleEntry:
        primary_dispatch = dispatch_table[query.primitive]
        if query.fallback is None:
            result = await primary_dispatch(query)
            return _entry_from(query, result, fallback_used=False)
        fallback_dispatch = dispatch_table[query.fallback.primitive]
        # The veto-strength bug: race the two coroutines and pick whichever
        # completes first. Scheduler jitter determines the winner.
        primary_task = asyncio.create_task(primary_dispatch(query))
        fallback_task = asyncio.create_task(fallback_dispatch(query.fallback))
        done, pending = await asyncio.wait(
            {primary_task, fallback_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        winner = next(iter(done))
        result: AdapterResult = winner.result()
        fallback_used = winner is fallback_task
        return _entry_from(query, result, fallback_used=fallback_used)


def _entry_from(query: ContextQuery, result: AdapterResult, *, fallback_used: bool) -> BundleEntry:
    import json  # noqa: PLC0415

    return BundleEntry(
        primitive=query.primitive,
        args_canonical=json.dumps(
            dict(query.args), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ),
        payload=result.payload,
        confidence=result.confidence,
        fallback_used=fallback_used,
        adapter_name=result.adapter_name,
    )


__all__ = ["_HedgedRaceBundleBuilder"]
# Re-export confidence variants so the property test doesn't have to
# import from two places.
_ = (Trusted, Degraded, Unavailable, BundleBuilder, BlobDigest, PluginId)
