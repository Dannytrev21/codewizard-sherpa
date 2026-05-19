"""S3-04 determinism property tests (ADR-0008).

Two same-input builds must produce byte-identical ``Bundle.model_dump_json()``
output even with seeded scheduler jitter injected at every adapter dispatch.
A deliberately-broken hedged-race reference impl is exercised in an
``xfail(strict=True)`` meta-test — if a future regression makes the broken
impl pass, the test suite fails loudly.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.adapters.confidence import Degraded, Trusted
from codegenie.plugins.bundle import (
    AdapterResult,
    Bundle,
    BundleBuilder,
)
from codegenie.plugins.tccm import TCCM, ContextQuery
from codegenie.types.identifiers import PluginId, PrimitiveName
from tests.property._hedged_race_reference import _HedgedRaceBundleBuilder

# --- Helpers -----------------------------------------------------------------


def _build_resolution(degraded_chain: bool = True):
    """Construct a small fixed-shape resolution.

    Two queries: one Trusted-primary, one Degraded-primary-with-Trusted-fallback.
    """
    from collections.abc import Mapping
    from dataclasses import dataclass

    from codegenie.plugins.bundle import AdapterDispatch

    q_trusted = ContextQuery.create(primitive="scip.refs", args={"q": "t"}).unwrap()
    q_fallback = ContextQuery.create(primitive="dep_graph.consumers", args={"q": "fb"}).unwrap()
    q_primary = ContextQuery.create(
        primitive="import_graph.reverse_lookup",
        args={"q": "p"},
        fallback=q_fallback,
    ).unwrap()
    if degraded_chain:
        tccm = TCCM(must_read=[q_trusted, q_primary])
    else:
        tccm = TCCM(must_read=[q_trusted])

    @dataclass(frozen=True)
    class _Res:
        composed_tccm: TCCM
        composed_dispatch: Mapping[PrimitiveName, AdapterDispatch]
        plugin_id: PluginId

    return _Res, tccm, q_trusted, q_primary, q_fallback


def _make_jittered_dispatch(name: str, confidence, seed: int):
    """Return an async callable that injects seeded jitter at every dispatch."""

    rng = random.Random(seed)

    async def dispatch(query: ContextQuery) -> AdapterResult:
        await asyncio.sleep(rng.uniform(0, 0.002))
        return AdapterResult(
            payload={"name": name, "primitive": str(query.primitive)},
            confidence=confidence,
            adapter_name=name,
        )

    return dispatch


class _VulnIdx:
    def digest(self):
        from codegenie.types.identifiers import BlobDigest

        return BlobDigest("b" * 64)


async def _run_build_with_seed(seed: int, tmp_path: Path) -> Bundle:
    _Res, tccm, _, _, _ = _build_resolution(degraded_chain=True)
    primary_disp = _make_jittered_dispatch("scip", Trusted(), seed=seed)
    degraded_disp = _make_jittered_dispatch("import_graph", Degraded(reason="stale"), seed=seed + 1)
    fallback_disp = _make_jittered_dispatch("dep_graph", Trusted(), seed=seed + 2)
    dispatch_table = {
        PrimitiveName("scip.refs"): primary_disp,
        PrimitiveName("import_graph.reverse_lookup"): degraded_disp,
        PrimitiveName("dep_graph.consumers"): fallback_disp,
    }
    resolution = _Res(
        composed_tccm=tccm,
        composed_dispatch=dispatch_table,
        plugin_id=PluginId("p"),
    )
    builder = BundleBuilder(cache_dir=tmp_path)
    return await builder.build(resolution, None, None, _VulnIdx())


# --- AC-22 + AC-25 -----------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9))
def test_bundle_byte_identical_under_seeded_jitter(
    seed: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """ADR-0008 / Goal G4 — two builds with the same inputs return
    byte-identical ``Bundle.model_dump_json()`` even under seeded jitter."""

    async def _run_pair() -> tuple[Bundle, Bundle]:
        b1 = await _run_build_with_seed(seed, tmp_path_factory.mktemp(f"a-{seed}"))
        b2 = await _run_build_with_seed(seed, tmp_path_factory.mktemp(f"b-{seed}"))
        return b1, b2

    b1, b2 = asyncio.run(_run_pair())
    assert b1.model_dump_json() == b2.model_dump_json()

    # AC-25 — JSON round-trip stability
    rebuilt = Bundle.model_validate_json(b1.model_dump_json())
    assert rebuilt.model_dump_json() == b1.model_dump_json()


# --- AC-23 — xfail meta-test against the broken hedged-race reference ---------


@pytest.mark.xfail(strict=True, reason="hedged-race violates ADR-0008 — broken reference must fail")
@settings(max_examples=20, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9))
def test_hedged_race_reference_fails_determinism(
    seed: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Run the same property against a deliberately-broken hedged-race impl.

    The impl races primary vs fallback and picks the winner — scheduler
    jitter changes the winner across runs, so the property must FAIL.
    ``xfail(strict=True)`` flips the test green only when the impl fails;
    a future regression that lets hedged-race semantics into production
    would make this test pass, surfacing the regression via STRICT xfail.
    """

    async def _run_pair() -> tuple[Bundle, Bundle]:
        rng_seed = seed
        b1 = await _run_hedged_with_seed(rng_seed, tmp_path_factory.mktemp(f"hx-{seed}-a"))
        b2 = await _run_hedged_with_seed(rng_seed, tmp_path_factory.mktemp(f"hx-{seed}-b"))
        return b1, b2

    b1, b2 = asyncio.run(_run_pair())
    assert b1.model_dump_json() == b2.model_dump_json()


async def _run_hedged_with_seed(seed: int, tmp_path: Path) -> Bundle:
    _Res, tccm, _, _, _ = _build_resolution(degraded_chain=True)
    # Different sleeps for primary vs fallback so the race outcome flips with
    # jitter — that's how we surface the determinism violation.
    rng_p = random.Random(seed)
    rng_f = random.Random(seed + 7)

    async def primary_d(q):
        await asyncio.sleep(rng_p.uniform(0, 0.002))
        return AdapterResult(
            payload={"who": "primary", "primitive": str(q.primitive)},
            confidence=Degraded(reason="stale"),
            adapter_name="primary",
        )

    async def fallback_d(q):
        await asyncio.sleep(rng_f.uniform(0, 0.002))
        return AdapterResult(
            payload={"who": "fallback", "primitive": str(q.primitive)},
            confidence=Trusted(),
            adapter_name="fallback",
        )

    async def trusted_top(q):
        return AdapterResult(payload={"who": "top"}, confidence=Trusted(), adapter_name="top")

    dispatch_table = {
        PrimitiveName("scip.refs"): trusted_top,
        PrimitiveName("import_graph.reverse_lookup"): primary_d,
        PrimitiveName("dep_graph.consumers"): fallback_d,
    }
    resolution = _Res(
        composed_tccm=tccm,
        composed_dispatch=dispatch_table,
        plugin_id=PluginId("p"),
    )
    builder = _HedgedRaceBundleBuilder(cache_dir=tmp_path)
    return await builder.build(resolution, None, None, _VulnIdx())
