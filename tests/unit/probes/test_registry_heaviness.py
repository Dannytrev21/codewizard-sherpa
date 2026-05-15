"""S1-08 — registry heaviness + runs_last + sorted dispatch (02-ADR-0003).

Pins the decorator-factory signature (`@register_probe(heaviness=, runs_last=)`),
the ``ProbeRegEntry`` record shape, the ``sorted_for_dispatch`` ordering
(heavy → medium → light, with ``runs_last=True`` strictly last), backward
compatibility with the bare ``@register_probe`` form, the Phase 0 contract
freeze (``Probe`` ABC not mutated), edge cases (empty registry, single
``runs_last=True``, all-same-heaviness), the ``Heaviness`` exhaustiveness
invariant, and cross-registry cache isolation.

Mutation resistance: thin assertions are replaced by registry-content checks
so that decorator implementations which silently drop registrations or
implementations which alias state across ``Registry`` instances fail loud.
"""

from __future__ import annotations

import typing
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe
from codegenie.probes.registry import (
    _HEAVINESS_RANK,
    Heaviness,
    ProbeRegEntry,
    Registry,
    default_registry,
    register_probe,
)


def _make_probe(name_: str) -> type[Probe]:
    class _P(Probe):
        async def run(self, repo: Any, ctx: Any) -> Any:  # type: ignore[override]
            raise NotImplementedError

    _P.name = name_
    _P.layer = "B"
    _P.tier = "task_specific"
    _P.applies_to_tasks = ["*"]
    _P.applies_to_languages = ["*"]
    _P.requires = []
    _P.declared_inputs = []
    _P.__name__ = name_
    return _P


# ----------------------------------------------------------------------------
# AC-3 / AC-4 — sort order: heavy → medium → light, then runs_last partition
# ----------------------------------------------------------------------------


def test_sorted_dispatch_order_heavy_then_medium_then_light_then_runs_last() -> None:
    reg = Registry()
    reg.register(_make_probe("a_light"))
    reg.register(_make_probe("b_medium"), heaviness="medium")
    reg.register(_make_probe("c_heavy"), heaviness="heavy")
    reg.register(_make_probe("d_index_health"), runs_last=True)
    reg.register(_make_probe("e_runs_last_heavy"), heaviness="heavy", runs_last=True)
    reg.register(_make_probe("f_light"))

    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    assert order == [
        "c_heavy",
        "b_medium",
        "a_light",
        "f_light",
        "e_runs_last_heavy",
        "d_index_health",
    ]


# ----------------------------------------------------------------------------
# AC-2 — ProbeRegEntry record shape
# ----------------------------------------------------------------------------


def test_probe_reg_entry_is_frozen_with_expected_fields() -> None:
    """``ProbeRegEntry`` must be a frozen dataclass with ``cls``, ``heaviness``,
    ``runs_last``, ``registration_index``. A mutable record breaks the
    rule-of-three kernel-extract note in the story's Implementer notes.
    """
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ProbeRegEntry)}
    assert fields == {"cls", "heaviness", "runs_last", "registration_index"}, fields
    # Frozen: setting an attribute must raise.
    cls = _make_probe("frozen_check")
    entry = ProbeRegEntry(cls=cls, heaviness="light", runs_last=False, registration_index=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.heaviness = "heavy"  # type: ignore[misc]


def test_default_heaviness_is_light_and_runs_last_false() -> None:
    reg = Registry()
    reg.register(_make_probe("x"))
    entries = reg.sorted_for_dispatch()
    assert len(entries) == 1
    assert entries[0].heaviness == "light"
    assert entries[0].runs_last is False


# ----------------------------------------------------------------------------
# AC-1 — decorator-factory and bare-decorator shapes
# ----------------------------------------------------------------------------


def test_registry_decorator_factory_shape() -> None:
    reg = Registry()

    @reg.decorator(heaviness="heavy", runs_last=True)
    class P1(Probe):
        name = "p1"
        layer = "B"
        tier = "base"
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        requires: list[str] = []
        declared_inputs: list[str] = []

        async def run(self, repo: Any, ctx: Any) -> Any:  # type: ignore[override]
            raise NotImplementedError

    entries = reg.sorted_for_dispatch()
    assert entries[0].cls is P1
    assert entries[0].heaviness == "heavy"
    assert entries[0].runs_last is True


def test_module_level_decorator_factory_with_parens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``@register_probe(heaviness=..., runs_last=...)`` returns a decorator
    that registers into ``default_registry`` with the passed kwargs."""
    from codegenie.probes import registry as registry_mod

    fresh = Registry()
    monkeypatch.setattr(registry_mod, "default_registry", fresh)

    decorator = registry_mod.register_probe(heaviness="medium", runs_last=False)
    cls = _make_probe("medium_phase2_probe")
    returned = decorator(cls)
    assert returned is cls

    entries = fresh.sorted_for_dispatch()
    assert len(entries) == 1
    assert entries[0].cls is cls
    assert entries[0].heaviness == "medium"
    assert entries[0].runs_last is False


def test_module_level_decorator_backward_compatible_no_parens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Phase 0/1 probe decorated with bare @register_probe (no parens) still
    registers AND lands in the registry with defaults.

    Mutation-resistance: a buggy dual-shape decorator that returns ``cls``
    unchanged but never calls ``register()`` would pass an ``is`` check; this
    test fails that buggy impl by asserting the entry appears in
    ``sorted_for_dispatch()`` with default ``("light", False)``.
    """
    from codegenie.probes import registry as registry_mod

    fresh = Registry()
    monkeypatch.setattr(registry_mod, "default_registry", fresh)

    cls = _make_probe("legacy_phase0_probe")
    returned = register_probe(cls)

    assert returned is cls
    entries = fresh.sorted_for_dispatch()
    assert len(entries) == 1, "decorator must actually register, not just return cls"
    assert entries[0].cls is cls
    assert entries[0].heaviness == "light"
    assert entries[0].runs_last is False


# ----------------------------------------------------------------------------
# AC-8 — Phase 0/1 probes import and register with defaults
# ----------------------------------------------------------------------------


def test_phase_0_1_probes_register_unedited() -> None:
    """AC-8 — importing ``codegenie.probes`` triggers every Phase 0/1
    ``@register_probe`` decoration; all of them must land with defaults.

    The real backward-compat guarantee: a misimplemented dual-shape decorator
    that silently dropped Phase 0/1 registrations on import would surface
    here as missing entries.
    """
    import importlib

    importlib.import_module("codegenie.probes")
    from codegenie.probes.registry import default_registry as live_default

    entries = live_default.sorted_for_dispatch()
    by_name = {e.cls.name: e for e in entries}
    expected_phase01 = {
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
    }
    missing = expected_phase01 - set(by_name.keys())
    assert not missing, f"Phase 0/1 probes dropped on import: {missing}"
    for name in expected_phase01:
        assert by_name[name].heaviness == "light", name
        assert by_name[name].runs_last is False, name


# ----------------------------------------------------------------------------
# AC-14a/b/c — edge cases
# ----------------------------------------------------------------------------


def test_empty_registry_sorted_dispatch_is_empty_tuple() -> None:
    assert Registry().sorted_for_dispatch() == ()


def test_all_runs_last_partition_orders_by_heaviness_then_registration() -> None:
    reg = Registry()
    reg.register(_make_probe("a"), heaviness="light", runs_last=True)
    reg.register(_make_probe("b"), heaviness="heavy", runs_last=True)
    reg.register(_make_probe("c"), heaviness="medium", runs_last=True)
    reg.register(_make_probe("d"), heaviness="heavy", runs_last=True)
    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    assert order == ["b", "d", "c", "a"]


def test_all_same_heaviness_preserves_registration_order() -> None:
    """AC-14c — stable sort guarantee is observable: equal sort keys → input
    order preserved verbatim."""
    reg = Registry()
    for n in ["x1", "x2", "x3", "x4"]:
        reg.register(_make_probe(n))
    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    assert order == ["x1", "x2", "x3", "x4"]


# ----------------------------------------------------------------------------
# AC-17 — Heaviness exhaustiveness via typing.get_args
# ----------------------------------------------------------------------------


def test_heaviness_literal_arms_exhaustively_ranked() -> None:
    """If a 4th tier is added to ``Heaviness`` but ``_HEAVINESS_RANK`` is not
    updated, this fails loud at CI rather than silently mis-sorting."""
    assert set(_HEAVINESS_RANK.keys()) == set(typing.get_args(Heaviness))


# ----------------------------------------------------------------------------
# AC-15 — property-based sort invariants
# ----------------------------------------------------------------------------


_heaviness_st = st.sampled_from(["light", "medium", "heavy"])
_runs_last_st = st.booleans()
_entry_specs_st = st.lists(st.tuples(_heaviness_st, _runs_last_st), min_size=0, max_size=20)


@given(specs=_entry_specs_st)
def test_sort_invariants_hold_for_arbitrary_registries(
    specs: list[tuple[str, bool]],
) -> None:
    reg = Registry()
    for i, (h, rl) in enumerate(specs):
        reg.register(_make_probe(f"p{i}"), heaviness=h, runs_last=rl)  # type: ignore[arg-type]
    out = reg.sorted_for_dispatch()

    # (4) permutation of input — no drops, no dupes, same length.
    assert len(out) == len(specs)
    assert {e.cls.name for e in out} == {f"p{i}" for i in range(len(specs))}

    # (1) every runs_last=True after every runs_last=False.
    seen_runs_last = False
    for e in out:
        if e.runs_last:
            seen_runs_last = True
        else:
            assert not seen_runs_last, "runs_last=False after runs_last=True"

    # (2) within each partition, heaviness rank non-decreasing.
    for partition in (False, True):
        ranks = [_HEAVINESS_RANK[e.heaviness] for e in out if e.runs_last is partition]
        assert ranks == sorted(ranks), f"heaviness rank non-monotonic in {partition=}"

    # (3) ties within (partition, heaviness) preserve registration order.
    for partition in (False, True):
        for h in ("heavy", "medium", "light"):
            idxs = [
                e.registration_index for e in out if e.runs_last is partition and e.heaviness == h
            ]
            assert idxs == sorted(idxs), f"tie-break unstable in {partition=}, {h=}"


# ----------------------------------------------------------------------------
# AC-16 — cross-registry cache isolation
# ----------------------------------------------------------------------------


def test_two_registries_do_not_cross_pollute() -> None:
    """Independent ``Registry()`` instances stay isolated.

    The Phase 0 ``_filter`` cache lives at module scope and takes the
    probes-tuple as a key; any new cache added by this story must preserve
    that property so two distinct registries are not aliased.
    """
    r1 = Registry()
    r2 = Registry()
    r1.register(_make_probe("only_in_r1"))
    r2.register(_make_probe("only_in_r2"))
    names_r1 = {e.cls.name for e in r1.sorted_for_dispatch()}
    names_r2 = {e.cls.name for e in r2.sorted_for_dispatch()}
    assert names_r1 == {"only_in_r1"}
    assert names_r2 == {"only_in_r2"}


# ----------------------------------------------------------------------------
# AC-7 — Probe ABC unchanged (defense in depth alongside contract-freeze test)
# ----------------------------------------------------------------------------


def test_probe_abc_has_no_heaviness_or_runs_last_attrs() -> None:
    """02-ADR-0003 §Decision — the ``Probe`` ABC is not edited.

    A spot-check that ``heaviness`` and ``runs_last`` are NOT class attributes
    on the ABC. The structural-signature snapshot is the load-bearing pin;
    this is a fast, readable, focused complementary assertion.
    """
    assert not hasattr(Probe, "heaviness")
    assert not hasattr(Probe, "runs_last")


# ----------------------------------------------------------------------------
# AC-2 — duplicate-name detection preserved on the new code path
# ----------------------------------------------------------------------------


def test_duplicate_name_still_rejected_at_registration_time() -> None:
    reg = Registry()
    reg.register(_make_probe("dup"), heaviness="heavy")
    with pytest.raises(ProbeError, match=r"dup"):
        reg.register(_make_probe("dup"), heaviness="light")


# ----------------------------------------------------------------------------
# AC-5 — sorted_for_task combines filter + sort
# ----------------------------------------------------------------------------


def test_sorted_for_task_filters_then_sorts() -> None:
    """``sorted_for_task`` applies the Phase 0 ``applies_to_*`` filter, then
    emits the result in ``sorted_for_dispatch`` order.

    Mutation resistance: an implementation that returned the filter result in
    registration order would fail this assertion because the heavy probe
    registered second appears first in the output.
    """
    reg = Registry()
    # Register in registration order: light, then heavy. After sort: heavy, light.
    light_cls = _make_probe("light_match")
    light_cls.applies_to_tasks = ["vuln_remediation"]
    reg.register(light_cls)
    heavy_cls = _make_probe("heavy_match")
    heavy_cls.applies_to_tasks = ["vuln_remediation"]
    reg.register(heavy_cls, heaviness="heavy")
    # Probe that doesn't match the task — must be filtered out.
    other_cls = _make_probe("other_task")
    other_cls.applies_to_tasks = ["distroless_migration"]
    reg.register(other_cls)

    out = reg.sorted_for_task("vuln_remediation", frozenset({"unknown"}))
    names = [e.cls.name for e in out]
    assert names == ["heavy_match", "light_match"]


# ----------------------------------------------------------------------------
# Cleanup — default_registry hygiene
# ----------------------------------------------------------------------------


def test_default_registry_unchanged_when_tests_use_monkeypatch() -> None:
    """Sanity: after the monkeypatched tests above run, ``default_registry``
    (the real singleton) still contains the Phase 0/1 probes."""
    names = {e.cls.name for e in default_registry.sorted_for_dispatch()}
    # At minimum the prelude language-detection probe must be present.
    assert "language_detection" in names
