"""Unit tests for :mod:`codegenie.plugins.bundle` (S3-04).

ADRs honored: Phase-3 ADR-0008 (serial fallback, not hedged-race),
Phase-3 ADR-0010 (sum-type dispatch via ``match`` + ``assert_never``).
"""

from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from codegenie.adapters.confidence import Degraded, Trusted, Unavailable
from codegenie.plugins.bundle import (
    AdapterDegraded,
    AdapterResult,
    Bundle,
    BundleBuilder,
    BundleBuilderError,
    BundleBuilderRaise,
    BundleResolution,
    FallbackChainTooDeep,
    _canonicalize_args,
    _compose_entry,
    _read_concurrency_bound,
)
from codegenie.plugins.tccm import TCCM, ContextQuery
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import PluginId, PrimitiveName
from tests.unit.plugins._bundle_fixtures import (
    DispatchSpy,
    FakeResolution,
    FakeVulnIndex,
    _make_dispatch,
    _make_query,
    _resolution_with_bands,
    _resolution_with_chain,
    _resolution_with_empty_tccm,
    _resolution_with_n_queries,
    _resolution_with_one_query_and_fallback,
    _vuln_index_fixture,
)

# ---------------------------------------------------------------------------
# AC-1 — module surface
# ---------------------------------------------------------------------------


def test_module_exports_pinned_set() -> None:
    import codegenie.plugins.bundle as bundle_mod

    assert set(bundle_mod.__all__) == {
        "AdapterDegraded",
        "AdapterDispatch",
        "AdapterResult",
        "Bundle",
        "BundleBuilder",
        "BundleBuilderError",
        "BundleBuilderEvent",
        "BundleBuilderRaise",
        "BundleEntry",
        "BundleResolution",
        "FallbackChainTooDeep",
    }


# ---------------------------------------------------------------------------
# AC-2 — BundleBuilderError shape
# ---------------------------------------------------------------------------


class TestBundleBuilderErrorShape:
    def test_is_basemodel_not_exception(self) -> None:
        err = BundleBuilderError(reason="invalid_concurrency_env", details={"value": "x"})
        assert isinstance(err, BaseModel)
        assert not isinstance(err, Exception)

    def test_unknown_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BundleBuilderError(reason="nope")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        err = BundleBuilderError(reason="invalid_concurrency_env")
        with pytest.raises(ValidationError):
            err.reason = "fallback_chain_too_deep"  # type: ignore[misc]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            BundleBuilderError(  # type: ignore[call-arg]
                reason="invalid_concurrency_env", surprise="forbidden"
            )

    def test_raise_carries_typed_payload(self) -> None:
        payload = BundleBuilderError(reason="fallback_chain_too_deep", details={"depth": 5})
        exc = BundleBuilderRaise(error=payload)
        assert exc.error is payload
        # Inherits CodegenieError -> Exception
        assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# AC-3 — AdapterResult
# ---------------------------------------------------------------------------


class TestAdapterResultShape:
    def test_frozen_and_extra_forbid(self) -> None:
        r = AdapterResult(payload={"k": "v"}, confidence=Trusted(), adapter_name="x")
        with pytest.raises(ValidationError):
            r.adapter_name = "y"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            AdapterResult(  # type: ignore[call-arg]
                payload={}, confidence=Trusted(), adapter_name="x", surprise=1
            )


# ---------------------------------------------------------------------------
# AC-8, AC-9, AC-10 — concurrency env
# ---------------------------------------------------------------------------


class TestConcurrencyEnv:
    @pytest.mark.parametrize("value", ["", "  ", "0", "-1", "3.5", "0x4", "1e2", "not-a-number"])
    def test_invalid_env_raises_with_typed_reason(
        self, monkeypatch: pytest.MonkeyPatch, value: str, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", value)
        # Empty + whitespace fall through to the cpu_count default (no raise);
        # everything else must raise.
        if value.strip() == "":
            builder = BundleBuilder(cache_dir=tmp_path)
            assert builder._concurrency >= 1
            return
        with pytest.raises(BundleBuilderRaise) as exc:
            BundleBuilder(cache_dir=tmp_path)
        assert exc.value.error.reason == "invalid_concurrency_env"
        assert exc.value.error.details["value"] == value

    @pytest.mark.parametrize(("value", "expected"), [("1", 1), ("+4", 4), ("128", 128)])
    def test_valid_env_accepted(
        self,
        monkeypatch: pytest.MonkeyPatch,
        value: str,
        expected: int,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", value)
        builder = BundleBuilder(cache_dir=tmp_path)
        assert builder._concurrency == expected

    def test_unset_uses_min_4_cpu_count(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CODEGENIE_BUNDLE_CONCURRENCY", raising=False)
        monkeypatch.setattr(os, "cpu_count", lambda: 8)
        builder = BundleBuilder(cache_dir=tmp_path)
        assert builder._concurrency == 4

    def test_cpu_count_none_falls_back_to_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CODEGENIE_BUNDLE_CONCURRENCY", raising=False)
        monkeypatch.setattr(os, "cpu_count", lambda: None)
        builder = BundleBuilder(cache_dir=tmp_path)
        assert builder._concurrency == 1

    def test_helper_callable_in_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "7")
        assert _read_concurrency_bound() == 7


# ---------------------------------------------------------------------------
# AC-8 — cache_dir annotation is SandboxedPath, not raw pathlib.Path
# ---------------------------------------------------------------------------


def test_init_cache_dir_annotation_is_sandboxedpath() -> None:
    # ``from __future__ import annotations`` keeps the annotation as a string;
    # we pin the source-text spelling so a regression that replaces it with
    # ``pathlib.Path`` is loud. ``SandboxedPath`` is currently
    # ``TypeAlias = pathlib.Path`` — name-pinning is what AC-8 guards.
    annotation = BundleBuilder.__init__.__annotations__["cache_dir"]
    assert annotation == "SandboxedPath"
    # And the imported name resolves to the canonical alias.
    assert SandboxedPath.__name__ == "Path"  # identity-equal to pathlib.Path today


# ---------------------------------------------------------------------------
# AC-11 — per-call semaphore
# ---------------------------------------------------------------------------


class TestPerCallSemaphore:
    @pytest.mark.asyncio
    async def test_two_concurrent_builds_do_not_share_bound(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "2")
        in_flight = 0
        peak = 0
        gate = asyncio.Event()

        async def gated_dispatch(query: ContextQuery) -> AdapterResult:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await gate.wait()
            in_flight -= 1
            return AdapterResult(payload={}, confidence=Trusted(), adapter_name="g")

        builder = BundleBuilder(cache_dir=tmp_path)
        coros = [
            builder.build(
                _resolution_with_n_queries(4, dispatch=gated_dispatch),
                None,
                None,
                _vuln_index_fixture(),
            ),
            builder.build(
                _resolution_with_n_queries(4, dispatch=gated_dispatch),
                None,
                None,
                _vuln_index_fixture(),
            ),
        ]
        task = asyncio.gather(*coros)
        # Yield so the coroutines reach the gate.
        for _ in range(20):
            await asyncio.sleep(0)
        assert peak == 4, f"per-call semaphore should give peak=4, saw {peak}"
        gate.set()
        await task


# ---------------------------------------------------------------------------
# AC-12 — entry order = concatenated band order, not completion time
# ---------------------------------------------------------------------------


class TestEntryOrder:
    @pytest.mark.asyncio
    async def test_entries_ordered_by_task_index_not_completion(self, tmp_path: Path) -> None:
        slow_done = asyncio.Event()

        async def slow_first(query: ContextQuery) -> AdapterResult:
            await slow_done.wait()
            return AdapterResult(payload={"first": True}, confidence=Trusted(), adapter_name="slow")

        async def fast_second(query: ContextQuery) -> AdapterResult:
            slow_done.set()
            return AdapterResult(
                payload={"second": True}, confidence=Trusted(), adapter_name="fast"
            )

        async def trusted(query: ContextQuery) -> AdapterResult:
            return AdapterResult(payload={}, confidence=Trusted(), adapter_name="t")

        resolution = _resolution_with_bands(
            must_read=[("scip.refs", slow_first), ("dep_graph.consumers", fast_second)],
            should_read=[("import_graph.reverse_lookup", trusted)],
            may_read=[("test_inventory.tests_exercising", trusted)],
        )
        builder = BundleBuilder(cache_dir=tmp_path)
        bundle = await builder.build(resolution, None, None, _vuln_index_fixture())
        assert len(bundle.entries) == 4
        # Order = must_read[0], must_read[1], should_read[0], may_read[0]
        adapter_names = [e.adapter_name for e in bundle.entries]
        assert adapter_names == ["slow", "fast", "t", "t"]
        primitives = [str(e.primitive) for e in bundle.entries]
        assert primitives == [
            "scip.refs",
            "dep_graph.consumers",
            "import_graph.reverse_lookup",
            "test_inventory.tests_exercising",
        ]


# ---------------------------------------------------------------------------
# AC-13 — args_canonical exact format
# ---------------------------------------------------------------------------


class TestCanonicalArgs:
    def test_literal_format(self) -> None:
        assert _canonicalize_args({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'

    def test_insertion_order_independent(self) -> None:
        assert _canonicalize_args({"a": 1, "b": 2}) == _canonicalize_args({"b": 2, "a": 1})

    def test_unicode_passthrough(self) -> None:
        # ensure_ascii=False: code points survive verbatim, no \u escapes.
        out = _canonicalize_args({"name": "café"})
        assert out == '{"name":"café"}'


# ---------------------------------------------------------------------------
# AC-15, AC-19 — serial fallback semantics + AdapterDegraded reason propagation
# ---------------------------------------------------------------------------


class TestSerialFallbackSemantics:
    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_trusted(self, tmp_path: Path) -> None:
        primary = _make_dispatch("primary", Trusted())
        fallback = _make_dispatch("fallback", Trusted())
        resolution = _resolution_with_one_query_and_fallback(primary, fallback)
        builder = BundleBuilder(cache_dir=tmp_path)
        bundle = await builder.build(resolution, None, None, _vuln_index_fixture())
        assert primary.calls == 1
        assert fallback.calls == 0
        assert bundle.entries[0].fallback_used is False
        assert bundle.entries[0].adapter_name == "primary"

    @pytest.mark.asyncio
    async def test_fallback_invoked_once_when_primary_degraded(self, tmp_path: Path) -> None:
        primary = _make_dispatch("primary", Degraded(reason="scip_index_stale"))
        fallback = _make_dispatch("fallback", Trusted())
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(
            _resolution_with_one_query_and_fallback(primary, fallback),
            None,
            None,
            _vuln_index_fixture(),
        )
        assert primary.calls == 1
        assert fallback.calls == 1
        assert bundle.entries[0].fallback_used is True
        assert bundle.entries[0].adapter_name == "fallback"
        degraded_events = [e for e in events if isinstance(e, AdapterDegraded)]
        assert len(degraded_events) == 1
        assert degraded_events[0].reason == "scip_index_stale"
        assert degraded_events[0].adapter_name == "primary"
        # AC-12 — entry.primitive is the ROOT primitive, not the fallback's.
        assert str(bundle.entries[0].primitive) == "scip.refs"

    @pytest.mark.asyncio
    async def test_unavailable_also_triggers_fallback_with_reason(self, tmp_path: Path) -> None:
        primary = _make_dispatch("primary", Unavailable(reason="tool_missing"))
        fallback = _make_dispatch("fallback", Trusted())
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        await builder.build(
            _resolution_with_one_query_and_fallback(primary, fallback),
            None,
            None,
            _vuln_index_fixture(),
        )
        degraded = [e for e in events if isinstance(e, AdapterDegraded)]
        assert degraded[0].reason == "tool_missing"

    @pytest.mark.asyncio
    async def test_primary_strictly_before_fallback_via_order_log(self, tmp_path: Path) -> None:
        rng = random.Random(0xC0DE)
        order: list[str] = []
        primary = _make_dispatch("primary", Degraded(reason="x"), order_log=order, jitter_rng=rng)
        fallback = _make_dispatch("fallback", Trusted(), order_log=order, jitter_rng=rng)
        builder = BundleBuilder(cache_dir=tmp_path)
        await builder.build(
            _resolution_with_one_query_and_fallback(primary, fallback),
            None,
            None,
            _vuln_index_fixture(),
        )
        i_pdone = order.index("primary:done")
        i_fstart = order.index("fallback:start")
        assert i_pdone < i_fstart, f"hedged-race smell — order: {order}"

    @pytest.mark.asyncio
    async def test_two_level_fallback_chain_succeeds(self, tmp_path: Path) -> None:
        a = _make_dispatch("a", Degraded(reason="r1"))
        b = _make_dispatch("b", Degraded(reason="r2"))
        c = _make_dispatch("c", Trusted())
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(
            _resolution_with_chain([a, b, c]), None, None, _vuln_index_fixture()
        )
        assert a.calls == 1 and b.calls == 1 and c.calls == 1
        assert bundle.entries[0].adapter_name == "c"
        assert bundle.entries[0].fallback_used is True
        degraded_events = [e for e in events if isinstance(e, AdapterDegraded)]
        assert [e.reason for e in degraded_events] == ["r1", "r2"]

    @pytest.mark.asyncio
    async def test_depth_exactly_4_succeeds(self, tmp_path: Path) -> None:
        chain: list[DispatchSpy] = [
            _make_dispatch(f"d{i}", Degraded(reason=str(i))) for i in range(3)
        ]
        chain.append(_make_dispatch("d3", Trusted()))
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(
            _resolution_with_chain(list(chain)),
            None,
            None,
            _vuln_index_fixture(),
        )
        assert bundle.entries[0].adapter_name == "d3"
        assert bundle.entries[0].fallback_used is True
        degraded_events = [e for e in events if isinstance(e, AdapterDegraded)]
        assert len(degraded_events) == 3

    @pytest.mark.asyncio
    async def test_depth_5_emits_and_raises(self, tmp_path: Path) -> None:
        chain: list[DispatchSpy] = [
            _make_dispatch(f"d{i}", Degraded(reason=str(i))) for i in range(5)
        ]
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        with pytest.raises(BundleBuilderRaise) as exc:
            await builder.build(
                _resolution_with_chain(list(chain)),
                None,
                None,
                _vuln_index_fixture(),
            )
        assert exc.value.error.reason == "fallback_chain_too_deep"
        assert exc.value.error.details["depth"] == 5
        degraded_events = [e for e in events if isinstance(e, AdapterDegraded)]
        assert len(degraded_events) == 4
        too_deep = [e for e in events if isinstance(e, FallbackChainTooDeep)]
        assert len(too_deep) == 1
        assert too_deep[0].depth == 5

    @pytest.mark.asyncio
    async def test_degraded_with_no_fallback_returns_best_effort(self, tmp_path: Path) -> None:
        primary = _make_dispatch("primary", Degraded(reason="no_chain"))
        # ContextQuery without a declared fallback.
        query = _make_query(primitive="scip.refs", args={"q": "x"})

        resolution = FakeResolution(
            composed_tccm=TCCM(must_read=[query]),
            composed_dispatch={PrimitiveName("scip.refs"): primary},
            plugin_id=PluginId("test-plugin"),
        )
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(resolution, None, None, _vuln_index_fixture())
        assert bundle.entries[0].fallback_used is False
        assert bundle.entries[0].adapter_name == "primary"
        # No AdapterDegraded emitted because no fallback was attempted.
        assert events == []


# ---------------------------------------------------------------------------
# AC-4 — missing dispatch raises
# ---------------------------------------------------------------------------


class TestMissingDispatch:
    @pytest.mark.asyncio
    async def test_missing_primitive_in_dispatch_table_raises(self, tmp_path: Path) -> None:
        # Build a resolution whose dispatch table is missing the query's primitive.
        query = _make_query(primitive="scip.refs", args={"q": "x"})
        resolution = FakeResolution(
            composed_tccm=TCCM(must_read=[query]),
            composed_dispatch={},  # primitive missing
            plugin_id=PluginId("test-plugin"),
        )
        builder = BundleBuilder(cache_dir=tmp_path)
        with pytest.raises(BundleBuilderRaise) as exc:
            await builder.build(resolution, None, None, _vuln_index_fixture())
        assert exc.value.error.reason == "missing_dispatch"
        assert exc.value.error.details["primitive"] == "scip.refs"


# ---------------------------------------------------------------------------
# AC-20, AC-21 — fail-loud error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    @pytest.mark.asyncio
    async def test_adapter_raise_propagates_unchanged(self, tmp_path: Path) -> None:
        spy = _make_dispatch("scip.refs", Trusted(), side_effect=RuntimeError("boom from adapter"))
        fallback = _make_dispatch("dep_graph.consumers", Trusted())
        builder = BundleBuilder(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="boom from adapter"):
            await builder.build(
                _resolution_with_one_query_and_fallback(spy, fallback),
                None,
                None,
                _vuln_index_fixture(),
            )

    @pytest.mark.asyncio
    async def test_event_emitter_raise_propagates(self, tmp_path: Path) -> None:
        primary = _make_dispatch("primary", Degraded(reason="x"))
        fallback = _make_dispatch("fallback", Trusted())

        def buggy_emitter(_e: object) -> None:
            raise ValueError("buggy emitter")

        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=buggy_emitter)
        with pytest.raises(ValueError, match="buggy emitter"):
            await builder.build(
                _resolution_with_one_query_and_fallback(primary, fallback),
                None,
                None,
                _vuln_index_fixture(),
            )


# ---------------------------------------------------------------------------
# AC-26 — empty TCCM bands
# ---------------------------------------------------------------------------


class TestEmptyBands:
    @pytest.mark.asyncio
    async def test_all_empty_bands(self, tmp_path: Path) -> None:
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(
            _resolution_with_empty_tccm(), None, None, _vuln_index_fixture()
        )
        assert bundle.entries == ()
        assert events == []
        assert bundle.plugin_id == PluginId("test-plugin")


# ---------------------------------------------------------------------------
# AC-28 — pure _compose_entry combinations
# ---------------------------------------------------------------------------


class TestComposeEntry:
    @pytest.mark.parametrize(
        ("primary_conf", "fallback_present", "expected_fallback_used"),
        [
            (Trusted(), False, False),
            (Degraded(reason="r"), False, False),
            (Unavailable(reason="r"), False, False),
            (Trusted(), True, True),
            (Degraded(reason="r"), True, True),
            (Unavailable(reason="r"), True, True),
        ],
    )
    def test_compose_entry_combinations(
        self,
        primary_conf: object,
        fallback_present: bool,
        expected_fallback_used: bool,
    ) -> None:
        primary = AdapterResult(payload={"k": "v"}, confidence=primary_conf, adapter_name="p")
        fallback = (
            AdapterResult(payload={"fb": True}, confidence=Trusted(), adapter_name="f")
            if fallback_present
            else None
        )
        query = _make_query(primitive="scip.refs", args={"x": 1})
        entry = _compose_entry(query, primary, fallback)
        assert entry.fallback_used is expected_fallback_used
        if fallback_present:
            assert entry.adapter_name == "f"
            assert entry.payload == {"fb": True}
        else:
            assert entry.adapter_name == "p"
            assert entry.payload == {"k": "v"}
        # args_canonical pinned format
        assert entry.args_canonical == '{"x":1}'


# ---------------------------------------------------------------------------
# Bundle JSON round-trip (AC-25)
# ---------------------------------------------------------------------------


class TestBundleJsonRoundTrip:
    @pytest.mark.asyncio
    async def test_bundle_json_round_trips(self, tmp_path: Path) -> None:
        a = _make_dispatch("a", Degraded(reason="r1"))
        b = _make_dispatch("b", Trusted())
        builder = BundleBuilder(cache_dir=tmp_path)
        bundle = await builder.build(
            _resolution_with_chain([a, b]), None, None, _vuln_index_fixture()
        )
        serialized = bundle.model_dump_json()
        rebuilt = Bundle.model_validate_json(serialized)
        assert rebuilt.model_dump_json() == serialized


# ---------------------------------------------------------------------------
# AC-4 — Protocol structural check
# ---------------------------------------------------------------------------


def test_fake_resolution_satisfies_protocol() -> None:
    primary = _make_dispatch("primary", Trusted())
    fallback = _make_dispatch("fallback", Trusted())
    resolution = _resolution_with_one_query_and_fallback(primary, fallback)
    assert isinstance(resolution, BundleResolution)
    assert isinstance(resolution, FakeResolution)


def test_vuln_index_fixture_returns_digest() -> None:
    vi = FakeVulnIndex()
    assert isinstance(vi.digest(), str)
    assert len(vi.digest()) == 64
