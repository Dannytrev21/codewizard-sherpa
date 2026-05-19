"""Phase-3 S2-04 AC-16 — Hypothesis property test for resolver totality.

The contract: for any well-formed registry containing the universal
fallback plus 0..5 concrete plugins with random scopes, and any
incoming :class:`PluginScope`, :func:`resolve` returns either a
:class:`ConcreteResolution` (whose ``matched_scope`` admits the
incoming scope) or a :class:`UniversalFallbackResolution`. It never
raises (modulo well-formedness — no cycles, depth ≤ 4 — both held
trivially by 0-extends fakes), never returns ``None``.

The strategy MUST NOT generate ``UNIVERSAL_FALLBACK_ID`` as a concrete
plugin name; reserving the literal for the fallback fixture is what
makes the resolver's "head is universal" narrowing observable.
"""

from __future__ import annotations

from typing import assert_never

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from codegenie.plugins.registry import PluginRegistry, register_plugin
from codegenie.plugins.resolver import (
    UNIVERSAL_FALLBACK_ID,
    ConcreteResolution,
    UniversalFallbackResolution,
    resolve,
)
from codegenie.plugins.scope import Concrete, PluginScope, ScopeDim, Wildcard
from codegenie.types.identifiers import PluginId
from tests.fixtures.plugins.fake_plugin import make_fake_plugin
from tests.fixtures.plugins.universal_fallback_fixture import make_universal_fallback


def _dim_value() -> st.SearchStrategy[str]:
    """Lowercase alpha word — matches the S1-02 dim regex
    ``^[a-z0-9_-]+$`` while avoiding leading/trailing dashes that the
    parser rejects."""
    return st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=8,
    )


def _scope_dim() -> st.SearchStrategy[ScopeDim]:
    return st.one_of(
        st.just(Wildcard()),
        _dim_value().map(lambda v: Concrete(value=v)),
    )


def _plugin_scope() -> st.SearchStrategy[PluginScope]:
    return st.builds(
        PluginScope,
        task_class=_scope_dim(),
        language=_scope_dim(),
        build_system=_scope_dim(),
    )


def _concrete_plugin_name() -> st.SearchStrategy[str]:
    """Plugin names that cannot collide with the universal fallback."""
    base = st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=24,
    )
    return base.filter(lambda s: s != UNIVERSAL_FALLBACK_ID)


def _manifest_scope_kwargs() -> st.SearchStrategy[dict[str, str | list[str]]]:
    def _one(dim_value_strategy: st.SearchStrategy[str]) -> st.SearchStrategy[str | list[str]]:
        return st.one_of(
            st.just("*"),
            dim_value_strategy,
            st.lists(dim_value_strategy, min_size=1, max_size=2),
        )

    return st.fixed_dictionaries(
        {
            "task_class": _one(_dim_value()),
            "languages": _one(_dim_value()),
            "build_systems": _one(_dim_value()),
        }
    )


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    plugin_specs=st.lists(
        st.tuples(_concrete_plugin_name(), _manifest_scope_kwargs(), st.integers(0, 100)),
        max_size=5,
    ),
    incoming_scope=_plugin_scope(),
)
def test_resolve_is_total(
    plugin_specs: list[tuple[str, dict[str, str | list[str]], int]],
    incoming_scope: PluginScope,
) -> None:
    """Exhaustive ``match`` over :data:`PluginResolution` proves
    totality at the type level; ``assert_never`` traps a future
    third variant. Runtime asserts pin the two real-world cases."""
    # Deduplicate names so registration never collides.
    seen: set[str] = set()
    unique_specs: list[tuple[str, dict[str, str | list[str]], int]] = []
    for spec in plugin_specs:
        if spec[0] in seen:
            continue
        seen.add(spec[0])
        unique_specs.append(spec)
    assume(UNIVERSAL_FALLBACK_ID not in seen)

    registry = PluginRegistry()
    register_plugin(make_universal_fallback(), registry=registry)
    for name, kwargs, precedence in unique_specs:
        register_plugin(
            make_fake_plugin(
                name=name,
                precedence=precedence,
                manifest_scope_kwargs=kwargs,
            ),
            registry=registry,
        )

    resolution = resolve(registry, incoming_scope)

    match resolution:
        case ConcreteResolution():
            # matched_scope.admits(incoming) — when incoming has
            # Wildcard dims those materialise as "*" and admit
            # anything (operator did not specify).
            scope = resolution.matched_scope
            assert scope.matches(
                task=_unpack(incoming_scope.task_class),
                language=_unpack(incoming_scope.language),
                build=_unpack(incoming_scope.build_system),
            )
            # Plugin is one of the registered concretes.
            registered_names = {p.manifest.name for p in registry.all()}
            assert resolution.plugin.manifest.name in registered_names
            # And it is NOT the universal fallback.
            assert resolution.plugin.manifest.name != UNIVERSAL_FALLBACK_ID
        case UniversalFallbackResolution():
            # The universal plugin must be registered (precondition).
            registered_names = {p.manifest.name for p in registry.all()}
            assert UNIVERSAL_FALLBACK_ID in registered_names
            assert UNIVERSAL_FALLBACK_ID not in resolution.candidates_considered
            assert resolution.reason == "no_concrete_match"
        case _:  # pragma: no cover — exhaustiveness guarantee.
            assert_never(resolution)


def _unpack(dim: ScopeDim) -> str:
    """Local copy of the resolver's ``_unpack`` so this test doesn't
    reach into the private helper."""
    match dim:
        case Wildcard():
            return "*"
        case Concrete(value=v):
            return v
        case _:  # pragma: no cover — exhaustiveness guarantee.
            assert_never(dim)


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(plugin_name=_concrete_plugin_name(), kwargs=_manifest_scope_kwargs())
def test_property_strategy_never_generates_universal_id(
    plugin_name: str, kwargs: dict[str, str | list[str]]
) -> None:
    """Meta-property: the strategy MUST NOT mint
    ``UNIVERSAL_FALLBACK_ID`` as a concrete plugin name. If it does,
    the totality test invariants would break silently."""
    del kwargs  # only the name is the meta-property target.
    assert plugin_name != UNIVERSAL_FALLBACK_ID, (
        "strategy minted the universal fallback id as a concrete name — "
        "the totality test would have been corrupted"
    )
    assert PluginId(plugin_name) != UNIVERSAL_FALLBACK_ID
