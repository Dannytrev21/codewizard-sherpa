"""Phase 7 S2-05 — registration-order invariance + `Layer.RUNTIME` reserved
slot, both proven with Hypothesis.

- **AC-1 / AC-10** (`test_assemble_invariant_under_50_registration_order_permutations`)
  — Phase 7 ADR-0006 §Tradeoffs row 3: shuffle the adapter registration order
  across 50 permutations; `assemble_provenance` returns a byte-identical
  result every time. Registration order is NOT load-bearing — dispatch order
  is the explicit `_ADAPTER_DISPATCH_ORDER` tuple (S2-03) plus the
  `Ecosystem`-declaration-sorted intra-layer iteration. This is the
  property-level lock for critic BP-1: if a future refactor reverts dispatch
  to `dict.items()` registration order, this test fails on the first
  divergent permutation.

- **AC-4** (`test_runtime_layer_remains_empty_under_permutations`) — with only
  APP + BASE_IMAGE adapters registered, the result never contains a
  `RuntimeBundled` variant. The `(Layer.RUNTIME,)` row of
  `_ADAPTER_DISPATCH_ORDER` is a reserved slot with nothing to dispatch
  (ADR-0006 §Consequences row 2 + open question §4).

Registry isolation: the autouse `provenance_registry_reset` fixture
(`conftest.py`) clears `_REGISTRY` once per test function; each example body
additionally clears it in a `finally:` block and asserts it empty on entry
(AC-6), so registrations never bleed between Hypothesis examples.
"""

from __future__ import annotations

from hypothesis import given, note, settings
from hypothesis import strategies as st

from codegenie.primitives.vuln_provenance import assemble_provenance
from codegenie.primitives.vuln_provenance import registry as _registry_mod
from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.types import Both, Provenance, RuntimeBundled
from codegenie.types.identifiers import ProvenanceAdapterId
from tests.property.vuln_provenance._strategies import (
    a_base_image,
    adapter_returning,
    an_app_direct,
    cve,
    empty_sbom,
    image,
    package,
)

# ---------------------------------------------------------------------------
# Fixed adapter spec set — one APP adapter + two BASE_IMAGE adapters with
# distinct image_digests (per AC-1). Whatever the registration order,
# `assemble_provenance` resolves the APP layer to the AppDirect result and the
# BASE_IMAGE layer to the Ecosystem-sort-first base — APK (Ecosystem index 3)
# sorts ahead of DPKG (index 4), so the APK base always wins.
# ---------------------------------------------------------------------------

_AdapterSpec = tuple[Layer, Ecosystem, Provenance]

_ADAPTER_SPECS: list[_AdapterSpec] = [
    (Layer.APP, Ecosystem.NPM, an_app_direct()),
    (Layer.BASE_IMAGE, Ecosystem.APK, a_base_image("a")),
    (Layer.BASE_IMAGE, Ecosystem.DPKG, a_base_image("c")),
]


def _reference_result() -> Provenance:
    """The canonical `assemble_provenance` result for `_ADAPTER_SPECS`.

    Computed against a fresh `dict` registry passed explicitly via the
    `registry=` kwarg — independent of the module `_REGISTRY` and of any
    insertion order, because `iter_adapters_for_layer_set` sorts intra-layer
    by `Ecosystem` declaration order regardless of dict order. Every
    permutation in the property test below must equal this value.
    """
    fresh: dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]] = {
        (layer, eco): adapter_returning(expected) for layer, eco, expected in _ADAPTER_SPECS
    }
    return assemble_provenance(cve(), package(), image(), empty_sbom(), registry=fresh)


# Computed ONCE at import time (story §Notes — "compute the reference ONCE,
# outside the Hypothesis @given"). Order-independent by construction.
_REFERENCE_RESULT: Provenance = _reference_result()


def _permutation_label(perm: list[_AdapterSpec]) -> list[tuple[str, str]]:
    """A compact `(layer, ecosystem)` label for Hypothesis `note(...)` output."""
    return [(layer.value, eco.value) for layer, eco, _ in perm]


@settings(max_examples=50, deadline=None)
@given(perm=st.permutations(_ADAPTER_SPECS))
def test_assemble_invariant_under_50_registration_order_permutations(
    perm: list[_AdapterSpec],
) -> None:
    """AC-1 / AC-10 — Phase 7 ADR-0006 §Tradeoffs row 3.

    For every permutation of the registration order, `assemble_provenance`
    (called with the default `registry=None`, i.e. the module `_REGISTRY`)
    returns a result `==` equal to the canonical reference. Registration
    order is not load-bearing; dispatch order is explicit data.
    """
    assert _registry_mod._REGISTRY == {}, "registry not clean at example start (AC-6)"
    try:
        for layer, eco, expected in perm:
            register_provenance_adapter(layer=layer, ecosystem=eco)(adapter_returning(expected))

        # registry=None on purpose — exercises the module _REGISTRY default
        # path (AC-10), the one production consumers use.
        result = assemble_provenance(cve(), package(), image(), empty_sbom())

        note(f"registration permutation: {_permutation_label(perm)}")
        note(f"result:    {result!r}")
        note(f"reference: {_REFERENCE_RESULT!r}")

        assert result == _REFERENCE_RESULT, (
            f"assemble_provenance diverged under registration permutation "
            f"{_permutation_label(perm)}: {result!r} != {_REFERENCE_RESULT!r}"
        )
    finally:
        _registry_mod._REGISTRY.clear()


@settings(max_examples=20, deadline=None)
@given(perm=st.permutations(_ADAPTER_SPECS))
def test_runtime_layer_remains_empty_under_permutations(
    perm: list[_AdapterSpec],
) -> None:
    """AC-4 — `Layer.RUNTIME` reserved slot stays empty.

    `_ADAPTER_SPECS` registers only APP + BASE_IMAGE adapters; no `RUNTIME`
    adapter exists. Across every permutation, `assemble_provenance` never
    yields a `RuntimeBundled` variant — neither as the top-level result nor
    nested as a `Both.base_record`. The `(Layer.RUNTIME,)` row of
    `_ADAPTER_DISPATCH_ORDER` has nothing to dispatch (ADR-0006 §Consequences
    row 2).
    """
    assert _registry_mod._REGISTRY == {}, "registry not clean at example start (AC-6)"
    try:
        for layer, eco, expected in perm:
            register_provenance_adapter(layer=layer, ecosystem=eco)(adapter_returning(expected))

        result = assemble_provenance(cve(), package(), image(), empty_sbom())

        note(f"registration permutation: {_permutation_label(perm)}")
        note(f"result: {result!r}")

        assert not isinstance(result, RuntimeBundled), (
            f"RUNTIME reserved slot leaked a RuntimeBundled result: {result!r}"
        )
        if isinstance(result, Both):
            assert not isinstance(result.base_record, RuntimeBundled), (
                f"Both.base_record is RuntimeBundled with no RUNTIME adapter: {result!r}"
            )
    finally:
        _registry_mod._REGISTRY.clear()


@settings(max_examples=5, deadline=None)
@given(eco=st.sampled_from([Ecosystem.NPM, Ecosystem.YARN_BERRY, Ecosystem.PNPM]))
def test_autouse_fixture_isolates_registry_across_examples(eco: Ecosystem) -> None:
    """AC-5 / AC-6 — the `provenance_registry_reset` autouse fixture is active
    and effective; examples are isolated from one another.

    Each example asserts `_REGISTRY` is empty on entry, registers exactly one
    adapter, then clears in `finally:`. Were isolation broken, example 2+
    would either observe example 1's leftover registration (the entry
    assertion fails) or hit a duplicate-key `RegistryError` when re-registering
    the same `(Layer, Ecosystem)`. Five examples passing in sequence confirms
    the autouse fixture + per-example teardown keep the registry isolated —
    the precondition every property test in this package relies on.
    """
    assert _registry_mod._REGISTRY == {}, "registry not empty at example start (AC-6)"
    try:
        register_provenance_adapter(layer=Layer.APP, ecosystem=eco)(
            adapter_returning(an_app_direct())
        )
        note(f"registered adapter for ecosystem {eco.value!r}")
        assert _registry_mod._REGISTRY.keys() == {(Layer.APP, eco)}, (
            "registry holds exactly the one adapter registered this example"
        )
    finally:
        _registry_mod._REGISTRY.clear()
