"""Unit tests for ``codegenie.indices.registry`` — story 02 S1-02.

Covers all 14 hardened acceptance criteria from
``docs/phases/02-context-gather-layers-b-g/stories/S1-02-freshness-check-registry.md``.

Tests use a *local* :class:`FreshnessRegistry` instance unless they are
explicitly verifying the module-level singleton's wiring (in which case they
guard with ``unregister_for_tests`` in a ``finally`` block — AC-9).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from codegenie.errors import FreshnessRegistryError
from codegenie.indices import (
    CommitsBehind,
    Fresh,
    FreshnessRegistry,
    IndexerError,
    Stale,
    register_index_freshness_check,
)
from codegenie.indices.registry import FreshnessCheck  # noqa: F401  (type alias surface)
from codegenie.types.identifiers import IndexName

if TYPE_CHECKING:
    from codegenie.indices import IndexFreshness


def test_register_and_dispatch_routes_each_slice_to_its_own_check() -> None:
    """AC-7 — registration round-trip *and* per-slice routing.

    Captures the slice each check actually receives, so a ``dispatch_all``
    mutation that shuffles slices (e.g., ``fn(slices.get(other_name, {}), head)``)
    fails."""
    reg = FreshnessRegistry()
    scip = IndexName("scip")
    runtime = IndexName("runtime_trace")

    seen_by_scip: list[dict[str, object]] = []
    seen_by_runtime: list[dict[str, object]] = []

    @reg.register(scip)
    def check_scip(slice_: dict[str, object], head: str) -> IndexFreshness:
        seen_by_scip.append(slice_)
        last = slice_.get("last_indexed_commit")
        if last == head:
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))
        return Stale(reason=CommitsBehind(n=1, last_indexed=str(last or "")))

    @reg.register(runtime)
    def check_runtime(slice_: dict[str, object], head: str) -> IndexFreshness:
        seen_by_runtime.append(slice_)
        return Stale(reason=IndexerError(message="upstream_runtime_unavailable"))

    scip_slice: dict[str, object] = {"last_indexed_commit": "deadbeef"}
    runtime_slice: dict[str, object] = {"last_traced_image_digest": "sha256:abc"}
    result = reg.dispatch_all(
        slices={scip: scip_slice, runtime: runtime_slice},
        head="cafef00d",
    )

    assert set(result.keys()) == {scip, runtime}
    assert seen_by_scip == [scip_slice]
    assert seen_by_runtime == [runtime_slice]
    scip_value = result[scip]
    assert isinstance(scip_value, Stale)
    assert isinstance(scip_value.reason, CommitsBehind)
    runtime_value = result[runtime]
    assert isinstance(runtime_value, Stale)
    assert isinstance(runtime_value.reason, IndexerError)


def test_duplicate_name_rejected_at_registration_time() -> None:
    """AC-3 — duplicate raises at decoration time; message contains the offending
    name AND both call sites as dotted ``module.qualname`` strings (catches a
    regression that strips the module path)."""
    reg = FreshnessRegistry()
    name = IndexName("scip")

    @reg.register(name)
    def check_a(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    # Define `check_b` *before* decorating so the local binding survives the
    # raise (decorator-syntax binding only happens after the decorator
    # returns; here it never does).
    def check_b(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    with pytest.raises(FreshnessRegistryError) as exc_info:
        reg.register(name)(check_b)

    msg = exc_info.value.args[0]
    assert "scip" in msg
    # AC-3: both dotted module.qualname forms must appear, not just the bare
    # function names. The qualname includes the test function as its enclosing
    # scope (e.g.,
    # "tests.unit.indices.test_freshness_registry.test_…<locals>.check_a").
    assert check_a.__module__ in msg
    assert f".{check_a.__qualname__}" in msg
    assert f".{check_b.__qualname__}" in msg


def test_decorator_returns_function_unchanged_on_local_registry() -> None:
    """AC-2 — ``Registry.register(name)(fn) is fn``."""
    reg = FreshnessRegistry()

    def f(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    returned = reg.register(IndexName("x"))(f)
    assert returned is f


def test_module_level_decorator_returns_function_unchanged() -> None:
    """AC-2 — symmetric guard at the module-level singleton entrypoint.

    Catches a ``register_index_freshness_check`` that registers correctly but
    returns ``None`` (or a wrapper); operator-visible because the decorated
    name would shadow to ``None`` at every import site."""
    from codegenie.indices import default_freshness_registry

    name = IndexName("__test_module_returns_marker__")

    def f(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    try:
        returned = register_index_freshness_check(name)(f)
        assert returned is f
    finally:
        default_freshness_registry.unregister_for_tests(name)


def test_module_level_decorator_uses_default_singleton() -> None:
    """AC-9 — the convenience decorator delegates to ``default_freshness_registry``;
    verified by registering on it and observing the singleton's
    ``registered_names``."""
    from codegenie.indices import default_freshness_registry

    name = IndexName("__test_singleton_marker__")

    @register_index_freshness_check(name)
    def check_marker(slice_: dict[str, object], head: str) -> IndexFreshness:
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    try:
        assert name in default_freshness_registry.registered_names()
    finally:
        default_freshness_registry.unregister_for_tests(name)


def test_dispatch_invokes_check_with_empty_dict_when_slice_missing() -> None:
    """AC-5/AC-6 — missing slice → check is still invoked with ``{}``;
    result key present (the registry is the source of truth for *expected*
    indices)."""
    reg = FreshnessRegistry()
    name = IndexName("runtime_trace")
    captured: list[dict[str, object]] = []

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> IndexFreshness:
        captured.append(slice_)
        return Stale(reason=IndexerError(message="upstream_runtime_unavailable"))

    out = reg.dispatch_all(slices={}, head="abc123")
    assert name in out
    assert captured == [{}]
    value = out[name]
    assert isinstance(value, Stale)
    assert isinstance(value.reason, IndexerError)


def test_dispatch_all_on_empty_registry_returns_empty_dict() -> None:
    """AC-11 — empty registry → empty dict; never raises.

    B2 dispatches through this primitive even on the first gather where no
    source has registered yet; failing on empty input would deadlock."""
    reg = FreshnessRegistry()
    assert reg.dispatch_all(slices={}, head="any") == {}
    assert reg.dispatch_all(slices={IndexName("orphan"): {"x": 1}}, head="any") == {}


def test_dispatch_all_threads_head_unchanged_to_every_check() -> None:
    """AC-12 — ``head`` propagation determinism.

    A wrong impl that swaps slice/head positional args, drops ``head``, or
    coerces it would fail. The captured list pins the dispatched value
    identity to the value the caller passed."""
    reg = FreshnessRegistry()
    name = IndexName("scip")
    captured_heads: list[str] = []

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> IndexFreshness:
        captured_heads.append(head)
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    reg.dispatch_all(slices={name: {}}, head="cafef00d")
    assert captured_heads == ["cafef00d"]


def test_dispatch_all_propagates_check_exception() -> None:
    """AC-13 — registry does not catch / log-and-continue / wrap.

    An exception from a check is a bug, and per Notes-for-implementer the
    coordinator at S4-01 is the right place to catch."""
    reg = FreshnessRegistry()
    name = IndexName("scip")

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> IndexFreshness:
        raise RuntimeError("synthetic_bug")

    with pytest.raises(RuntimeError, match="synthetic_bug"):
        reg.dispatch_all(slices={name: {}}, head="x")


def test_dispatch_all_iteration_is_registration_order() -> None:
    """AC-14 — ``list(result.keys()) == registration_order``.

    Audit-chain hashing (S3-06) depends on byte-stable output ordering;
    a non-deterministic iteration order would silently corrupt audit chains."""
    reg = FreshnessRegistry()
    order = [IndexName(n) for n in ("first", "second", "third", "fourth")]

    for n in order:

        @reg.register(n)
        def _stub(
            slice_: dict[str, object],
            head: str,
            _n: str = n,
        ) -> IndexFreshness:
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=UTC))

    # Empty `slices` keeps the test focused on order, not on slice routing.
    # `dispatch_all` is the load-bearing ordering contract (audit-hash
    # dependency); `registered_names()` returns an unordered frozenset.
    result = reg.dispatch_all(slices={}, head="x")
    assert list(result.keys()) == order
    assert set(reg.registered_names()) == set(order)


def test_registry_public_surface_has_expected_names() -> None:
    """AC-1 — ``__all__`` exposes the registry surface (mirrors the
    Phase-0 ``probes/registry.py`` precedent)."""
    from codegenie.indices import registry as reg_mod

    expected = {
        "FreshnessCheck",
        "FreshnessRegistry",
        "FreshnessRegistryError",
        "default_freshness_registry",
        "register_index_freshness_check",
    }
    assert expected <= set(reg_mod.__all__)
