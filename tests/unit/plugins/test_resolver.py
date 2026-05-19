"""Phase-3 S2-04 — unit + parametrized tests for the plugin resolver.

Covers AC-1..AC-12 + AC-15 (named tests). The AC-13 module purity,
AC-14 exhaustiveness, AC-16 property, and AC-17 single-source AST
scans live in sibling files.

Test naming traces directly to the AC-15 enumeration so a future
contributor can grep ``test_<...>`` against the story file.
"""

from __future__ import annotations

from typing import Any

import pytest

from codegenie.plugins.errors import (
    PluginExtendsCycle,
    PluginExtendsDepthExceeded,
    PluginNotRegistered,
    PluginRegistryCorrupted,
)
from codegenie.plugins.manifest import ManifestScope
from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.plugins.resolver import (
    UNIVERSAL_FALLBACK_ID,
    ComposedTccm,
    ConcreteResolution,
    ScopedCandidate,
    UniversalFallbackResolution,
    lift_manifest_scope,
    resolve,
)
from codegenie.plugins.scope import Concrete, PluginScope, Wildcard
from codegenie.types.identifiers import PluginId, PrimitiveName
from tests.fixtures.plugins.fake_plugin import make_fake_plugin
from tests.fixtures.plugins.universal_fallback_fixture import make_universal_fallback

# ---------------------------------------------------------------------------
# Helpers — keep the test bodies readable.
# ---------------------------------------------------------------------------


def _concrete_scope(task: str, language: str, build: str) -> PluginScope:
    return PluginScope(
        task_class=Concrete(value=task),
        language=Concrete(value=language),
        build_system=Concrete(value=build),
    )


def _vuln_node_npm_scope() -> PluginScope:
    return _concrete_scope("vulnerability-remediation", "node", "npm")


def _register(*plugins: Any) -> PluginRegistry:
    registry = PluginRegistry()
    for plugin in plugins:
        register_plugin(plugin, registry=registry)
    return registry


# ---------------------------------------------------------------------------
# AC-1 — module surface __all__ matches the documented export set.
# ---------------------------------------------------------------------------


def test_resolver_all_export_set_is_exact() -> None:
    """``__all__`` must equal the documented surface — stowaway exports
    or accidental removals fail loud (S1-02 AC-2 precedent)."""
    import codegenie.plugins.resolver as mod

    expected = {
        "ComposedTccm",
        "ConcreteResolution",
        "PluginResolution",
        "ScopedCandidate",
        "UNIVERSAL_FALLBACK_ID",
        "UniversalFallbackResolution",
        "compose_extends_chain",
        "lift_manifest_scope",
        "resolve",
    }
    assert set(mod.__all__) == expected


# ---------------------------------------------------------------------------
# AC-15 #1 — no concrete match → universal fallback.
# ---------------------------------------------------------------------------


def test_no_match_returns_universal_fallback() -> None:
    """ADR-0003 §Decision step 3 + §Consequences row 5: when no
    concrete plugin matches and the universal plugin is registered,
    return :class:`UniversalFallbackResolution` whose
    ``candidates_considered`` lists every non-universal plugin
    alphabetised."""
    python_plugin = make_fake_plugin(
        name="vulnerability-remediation--python--pip",
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "python",
            "build_systems": "pip",
        },
    )
    registry = _register(make_universal_fallback(), python_plugin)
    scope = _concrete_scope("distroless-migration", "node", "npm")

    resolution = resolve(registry, scope)

    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.kind == "universal_fallback"
    assert resolution.reason == "no_concrete_match"
    assert resolution.candidates_considered == (PluginId("vulnerability-remediation--python--pip"),)
    assert UNIVERSAL_FALLBACK_ID not in resolution.candidates_considered


# ---------------------------------------------------------------------------
# AC-15 #2 — specificity wins over wildcards.
# ---------------------------------------------------------------------------


def test_exact_match_beats_wildcard() -> None:
    """Specificity-3 plugin AND specificity-1 plugin both match an
    incoming concrete (vuln, node, npm) scope; specificity-3 wins.
    Mutation (sort key reversed) → fails."""
    specific = make_fake_plugin(
        name="vulnerability-remediation--node--npm",
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    catch_all = make_fake_plugin(
        name="catch-all--star--star",
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "*",
            "build_systems": "*",
        },
    )
    registry = _register(make_universal_fallback(), specific, catch_all)

    resolution = resolve(registry, _vuln_node_npm_scope())

    assert isinstance(resolution, ConcreteResolution)
    assert resolution.plugin.manifest.name == PluginId("vulnerability-remediation--node--npm")
    assert resolution.matched_scope == _vuln_node_npm_scope()


# ---------------------------------------------------------------------------
# AC-15 #3 — precedence breaks specificity ties.
# ---------------------------------------------------------------------------


def test_precedence_breaks_specificity_tie() -> None:
    """Two plugins with equal specificity; the one with the higher
    ``precedence`` wins."""
    high_prec = make_fake_plugin(
        name="aaa--node--npm",
        precedence=100,
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    low_prec = make_fake_plugin(
        name="zzz--node--npm",
        precedence=50,
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    registry = _register(make_universal_fallback(), high_prec, low_prec)

    resolution = resolve(registry, _vuln_node_npm_scope())

    assert isinstance(resolution, ConcreteResolution)
    assert resolution.plugin.manifest.name == PluginId("aaa--node--npm")


# ---------------------------------------------------------------------------
# AC-15 #4 — name breaks precedence ties (alphabetical asc).
# ---------------------------------------------------------------------------


def test_name_breaks_precedence_tie() -> None:
    """Two plugins with equal specificity and equal precedence — the
    alphabetically-first name wins."""
    a_plugin = make_fake_plugin(
        name="a-plugin",
        precedence=50,
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    b_plugin = make_fake_plugin(
        name="b-plugin",
        precedence=50,
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    # Register b first to prove order is name-driven, not insertion-driven.
    registry = _register(make_universal_fallback(), b_plugin, a_plugin)

    resolution = resolve(registry, _vuln_node_npm_scope())

    assert isinstance(resolution, ConcreteResolution)
    assert resolution.plugin.manifest.name == PluginId("a-plugin")


# ---------------------------------------------------------------------------
# AC-15 #5 — lift_manifest_scope fan-out parametrized.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (
            {
                "task_class": "vulnerability-remediation",
                "languages": "node",
                "build_systems": "npm",
            },
            (
                PluginScope(
                    task_class=Concrete(value="vulnerability-remediation"),
                    language=Concrete(value="node"),
                    build_system=Concrete(value="npm"),
                ),
            ),
        ),
        (
            {
                "task_class": "vulnerability-remediation",
                "languages": ["node", "python"],
                "build_systems": "*",
            },
            (
                PluginScope(
                    task_class=Concrete(value="vulnerability-remediation"),
                    language=Concrete(value="node"),
                    build_system=Wildcard(),
                ),
                PluginScope(
                    task_class=Concrete(value="vulnerability-remediation"),
                    language=Concrete(value="python"),
                    build_system=Wildcard(),
                ),
            ),
        ),
        (
            {
                "task_class": ["vulnerability-remediation", "distroless-migration"],
                "languages": "*",
                "build_systems": ["npm", "pip"],
            },
            (
                PluginScope(
                    task_class=Concrete(value="vulnerability-remediation"),
                    language=Wildcard(),
                    build_system=Concrete(value="npm"),
                ),
                PluginScope(
                    task_class=Concrete(value="vulnerability-remediation"),
                    language=Wildcard(),
                    build_system=Concrete(value="pip"),
                ),
                PluginScope(
                    task_class=Concrete(value="distroless-migration"),
                    language=Wildcard(),
                    build_system=Concrete(value="npm"),
                ),
                PluginScope(
                    task_class=Concrete(value="distroless-migration"),
                    language=Wildcard(),
                    build_system=Concrete(value="pip"),
                ),
            ),
        ),
        (
            {"task_class": "*", "languages": "*", "build_systems": "*"},
            (
                PluginScope(
                    task_class=Wildcard(),
                    language=Wildcard(),
                    build_system=Wildcard(),
                ),
            ),
        ),
    ],
)
def test_lift_manifest_scope_fans_out(
    kwargs: dict[str, str | list[str]], expected: tuple[PluginScope, ...]
) -> None:
    """The cross-product fan-out is the per-dim list ⇒ separate
    PluginScope behaviour. Wildcard strings lift to
    :class:`Wildcard` (mutation M12 defence)."""
    ms = ManifestScope(**kwargs)
    assert lift_manifest_scope(ms) == expected


# ---------------------------------------------------------------------------
# AC-15 #6 — extends chain composes TCCM + adapters left-to-right.
# ---------------------------------------------------------------------------


def test_extends_chain_composes_tccm_and_adapters_left_to_right() -> None:
    """Plugin ``A`` extends plugin ``B``. ``B.adapters() = {Foo: AdB}``;
    ``A.adapters() = {Foo: AdA, Bar: AdC}``. Composed: ``{Foo: AdA,
    Bar: AdC}`` — later wins on Foo (A wins over B); Bar additive.
    Same shape for ``ComposedTccm.provides`` per-key one-level merge."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _FakeAdapter:
        """Satisfies the :class:`Adapter` Protocol's one attribute."""

        primitive: PrimitiveName

    foo: PrimitiveName = PrimitiveName("foo")
    bar: PrimitiveName = PrimitiveName("bar")
    ad_a = _FakeAdapter(primitive=foo)
    ad_b = _FakeAdapter(primitive=foo)
    ad_c = _FakeAdapter(primitive=bar)

    b_plugin = make_fake_plugin(
        name="b-plugin",
        adapters_map={foo: ad_b},
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    a_plugin = make_fake_plugin(
        name="a-plugin",
        extends=(PluginId("b-plugin"),),
        precedence=99,  # win the sort over b
        adapters_map={foo: ad_a, bar: ad_c},
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "node",
            "build_systems": "npm",
        },
    )
    # Inject a ComposedTccm onto each plugin via the internal hook the
    # resolver reads (``_composed_tccm``) so the merge logic is
    # exercised end-to-end (real TCCM lands in S3-01).
    object.__setattr__(
        b_plugin,
        "_composed_tccm",
        ComposedTccm(provides={"vuln": {"x": "vB"}}),
    )
    object.__setattr__(
        a_plugin,
        "_composed_tccm",
        ComposedTccm(provides={"vuln": {"x": "vA", "y": "vA2"}}),
    )
    registry = _register(make_universal_fallback(), a_plugin, b_plugin)

    resolution = resolve(registry, _vuln_node_npm_scope())

    assert isinstance(resolution, ConcreteResolution)
    assert resolution.composed_adapters == {foo: ad_a, bar: ad_c}
    assert resolution.composed_tccm.provides == {"vuln": {"x": "vA", "y": "vA2"}}


# ---------------------------------------------------------------------------
# AC-15 #7 — depth-4 chain composes (no raise; chain length 4).
# ---------------------------------------------------------------------------


def test_extends_depth_4_composes_correctly() -> None:
    """Chain ``A -> B -> C -> D`` (head A; extends walked first
    applies first). ``len(extends_chain) == 4``; ``extends_chain[-1]``
    is the head plugin itself."""
    d = make_fake_plugin(name="d")
    c = make_fake_plugin(name="c", extends=(PluginId("d"),))
    b = make_fake_plugin(name="b", extends=(PluginId("c"),))
    a = make_fake_plugin(name="a", extends=(PluginId("b"),), precedence=99)
    registry = _register(make_universal_fallback(), a, b, c, d)

    resolution = resolve(registry, _vuln_node_npm_scope())

    assert isinstance(resolution, ConcreteResolution)
    assert len(resolution.extends_chain) == 4
    assert resolution.extends_chain[-1] is a
    assert [p.manifest.name for p in resolution.extends_chain] == [
        PluginId("d"),
        PluginId("c"),
        PluginId("b"),
        PluginId("a"),
    ]


# ---------------------------------------------------------------------------
# AC-15 #8 — depth-5 chain raises PluginExtendsDepthExceeded.
# ---------------------------------------------------------------------------


def test_extends_depth_5_raises_extends_depth_exceeded() -> None:
    """A chain that would require descending into a 5th level raises
    :class:`PluginExtendsDepthExceeded` whose ``chain`` reports the
    visited path at the point of refusal. Mutation M7 (``>`` instead of
    ``>=``) would silently permit depth-5."""
    e = make_fake_plugin(name="e")
    d = make_fake_plugin(name="d", extends=(PluginId("e"),))
    c = make_fake_plugin(name="c", extends=(PluginId("d"),))
    b = make_fake_plugin(name="b", extends=(PluginId("c"),))
    a = make_fake_plugin(name="a", extends=(PluginId("b"),), precedence=99)
    registry = _register(make_universal_fallback(), a, b, c, d, e)

    with pytest.raises(PluginExtendsDepthExceeded) as excinfo:
        resolve(registry, _vuln_node_npm_scope())

    assert excinfo.value.chain == (
        PluginId("a"),
        PluginId("b"),
        PluginId("c"),
        PluginId("d"),
        PluginId("e"),
    )
    assert excinfo.value.reason == "extends_depth_exceeded"


# ---------------------------------------------------------------------------
# AC-15 #9 — A extends B extends A raises PluginExtendsCycle.
# ---------------------------------------------------------------------------


def test_extends_cycle_raises_plugin_extends_cycle() -> None:
    """``A extends B``; ``B extends A``. Cycle exception's ``chain``
    field repeats the entry-point at the tail — an operator reading
    the stack sees "we came back to where we started"."""
    a_name = PluginId("a")
    b_name = PluginId("b")
    a = make_fake_plugin(name=a_name, extends=(b_name,), precedence=99)
    b = make_fake_plugin(name=b_name, extends=(a_name,))
    registry = _register(make_universal_fallback(), a, b)

    with pytest.raises(PluginExtendsCycle) as excinfo:
        resolve(registry, _vuln_node_npm_scope())

    assert excinfo.value.chain == (a_name, b_name, a_name)


# ---------------------------------------------------------------------------
# AC-15 #10 — only universal registered → universal fallback.
# ---------------------------------------------------------------------------


def test_only_universal_registered_returns_universal_fallback() -> None:
    """Registry has only the universal plugin; resolve any scope →
    :class:`UniversalFallbackResolution`. Mutation M8 (raise instead
    of fall-through) would fail this test."""
    registry = _register(make_universal_fallback())

    resolution = resolve(registry, _vuln_node_npm_scope())

    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.reason == "no_concrete_match"
    assert resolution.candidates_considered == ()


# ---------------------------------------------------------------------------
# AC-15 #11 — no universal registered → PluginRegistryCorrupted.
# ---------------------------------------------------------------------------


def test_missing_universal_raises_plugin_registry_corrupted() -> None:
    """Registry contains only concrete plugins; resolving a
    non-matching scope raises
    :class:`PluginRegistryCorrupted(reason="missing_universal")`."""
    python_plugin = make_fake_plugin(
        name="vulnerability-remediation--python--pip",
        manifest_scope_kwargs={
            "task_class": "vulnerability-remediation",
            "languages": "python",
            "build_systems": "pip",
        },
    )
    registry = _register(python_plugin)

    with pytest.raises(PluginRegistryCorrupted) as excinfo:
        resolve(registry, _vuln_node_npm_scope())

    assert excinfo.value.reason == "missing_universal"


# ---------------------------------------------------------------------------
# AC-15 #12 — extends target missing → PluginNotRegistered propagates.
# ---------------------------------------------------------------------------


def test_extends_missing_target_raises_plugin_not_registered() -> None:
    """``A extends B``; ``B`` is not registered.
    ``registry.get(PluginId("B"))`` raises
    :class:`PluginNotRegistered`; the resolver does NOT catch it."""
    a = make_fake_plugin(name="a", extends=(PluginId("b"),), precedence=99)
    registry = _register(make_universal_fallback(), a)

    with pytest.raises(PluginNotRegistered) as excinfo:
        resolve(registry, _vuln_node_npm_scope())

    assert excinfo.value.name == PluginId("b")


# ---------------------------------------------------------------------------
# AC-15 #13 — candidates_considered alphabetised; excludes universal.
# ---------------------------------------------------------------------------


def test_candidates_considered_alphabetized_and_excludes_universal() -> None:
    """Registry has c-plugin, a-plugin, b-plugin (none match) +
    universal. ``candidates_considered`` is the alphabetised tuple
    ``(a-plugin, b-plugin, c-plugin)`` — universal excluded."""
    plugins = [
        make_fake_plugin(
            name=name,
            manifest_scope_kwargs={
                "task_class": "vulnerability-remediation",
                "languages": "python",
                "build_systems": "pip",
            },
        )
        for name in ("c-plugin", "a-plugin", "b-plugin")
    ]
    registry = _register(make_universal_fallback(), *plugins)

    # Incoming scope nothing concrete matches — universal is the head.
    resolution = resolve(registry, _concrete_scope("distroless-migration", "node", "npm"))

    assert isinstance(resolution, UniversalFallbackResolution)
    assert resolution.candidates_considered == (
        PluginId("a-plugin"),
        PluginId("b-plugin"),
        PluginId("c-plugin"),
    )
    assert UNIVERSAL_FALLBACK_ID not in resolution.candidates_considered


# ---------------------------------------------------------------------------
# AC-3 — ScopedCandidate dataclass is frozen + slotted.
# ---------------------------------------------------------------------------


def test_scoped_candidate_is_frozen_and_slotted() -> None:
    """Frozen dataclass prevents accidental mutation between sort and
    use; slots reduces per-instance memory in the lift fan-out."""
    candidate = ScopedCandidate(
        plugin=make_fake_plugin(name="x"),
        lifted_scope=_vuln_node_npm_scope(),
    )
    with pytest.raises((AttributeError, TypeError)):
        candidate.plugin = make_fake_plugin(name="y")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC-12 — registry.resolve delegates (smoke; no NotImplementedError).
# ---------------------------------------------------------------------------


def test_registry_resolve_delegates_to_resolver() -> None:
    """The S2-01 stub raised ``NotImplementedError``; the wired
    delegation returns a typed :data:`PluginResolution`."""
    registry = _register(make_universal_fallback())
    resolution = registry.resolve(_vuln_node_npm_scope())
    assert isinstance(resolution, UniversalFallbackResolution)


# ---------------------------------------------------------------------------
# Defensive — empty registry raises empty_registry corruption.
# ---------------------------------------------------------------------------


def test_empty_registry_raises_plugin_registry_corrupted() -> None:
    """Belt-and-braces: the loader's startup check (S2-03) should
    refuse an empty registry, but the resolver fails loudly too."""
    registry = PluginRegistry()
    with pytest.raises(PluginRegistryCorrupted) as excinfo:
        resolve(registry, _vuln_node_npm_scope())
    assert excinfo.value.reason == "empty_registry"
