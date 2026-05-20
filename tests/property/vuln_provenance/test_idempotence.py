"""Phase 7 S2-05 — `assemble_provenance` idempotence, proven with Hypothesis.

**AC-2** — Phase 7 ADR-0008 ships NO `vuln.provenance` cache; idempotence
therefore holds by determinism alone. For any Hypothesis-generated set of
registered adapters, calling `assemble_provenance` twice with byte-identical
inputs returns two `==` equal `Provenance` results.

The test fails loud if a future PR introduces hidden per-call state into the
dispatch path — e.g. an adapter-instance cache that returns a stale value, or
a non-deterministic intra-layer pick — anything that makes the second call
diverge from the first.

Registry isolation follows the same discipline as the sibling property
modules: the autouse `provenance_registry_reset` fixture clears `_REGISTRY`
once per function; each example clears it in `finally:` and asserts it empty
on entry (AC-6).
"""

from __future__ import annotations

from hypothesis import given, note, settings
from hypothesis import strategies as st

from codegenie.primitives.vuln_provenance import assemble_provenance
from codegenie.primitives.vuln_provenance import registry as _registry_mod
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.types import Provenance
from tests.property.vuln_provenance._strategies import (
    adapter_returning,
    app_kind_strategy,
    base_kind_strategy,
    cve,
    empty_sbom,
    image,
    package,
)

# Ecosystem members are partitioned by layer so a generated registration plan
# never assigns an APP-layer ecosystem to a BASE_IMAGE adapter (or vice versa)
# — that pairing is meaningless and `assemble_provenance` routes by the
# registration Layer regardless.
_APP_ECOSYSTEMS = (Ecosystem.NPM, Ecosystem.YARN_BERRY, Ecosystem.PNPM)
_BASE_ECOSYSTEMS = (Ecosystem.APK, Ecosystem.DPKG, Ecosystem.RPM)

_RegistrationPlan = list[tuple[Layer, Ecosystem, Provenance]]


@st.composite
def _registration_plans(draw: st.DrawFn) -> _RegistrationPlan:
    """Generate a registration plan: a list of `(layer, ecosystem, result)`
    adapter specs with unique `(layer, ecosystem)` keys.

    The plan may be empty — the empty case exercises the `(None, None)` arm
    (`assemble_provenance` → `Unknown("no_adapter_resolved")`), which must
    also be idempotent.
    """
    app_specs = draw(
        st.lists(
            st.tuples(st.sampled_from(_APP_ECOSYSTEMS), app_kind_strategy()),
            unique_by=lambda spec: spec[0],
            max_size=3,
        )
    )
    base_specs = draw(
        st.lists(
            st.tuples(st.sampled_from(_BASE_ECOSYSTEMS), base_kind_strategy()),
            unique_by=lambda spec: spec[0],
            max_size=3,
        )
    )
    plan: _RegistrationPlan = [(Layer.APP, eco, result) for eco, result in app_specs]
    plan += [(Layer.BASE_IMAGE, eco, result) for eco, result in base_specs]
    return plan


@settings(max_examples=30, deadline=None)
@given(plan=_registration_plans())
def test_assemble_provenance_is_idempotent(plan: _RegistrationPlan) -> None:
    """AC-2 — Phase 7 ADR-0008: no cache, idempotent by determinism.

    Register the generated adapter plan, then call `assemble_provenance`
    twice with the exact same inputs. The two results must be `==` equal —
    the function holds no per-call state that could make the second call
    diverge.
    """
    assert _registry_mod._REGISTRY == {}, "registry not clean at example start (AC-6)"
    try:
        for layer, eco, result in plan:
            register_provenance_adapter(layer=layer, ecosystem=eco)(adapter_returning(result))

        # Byte-identical inputs across both calls — the same objects.
        cve_id, package_id, image_ref, sbom = cve(), package(), image(), empty_sbom()
        first = assemble_provenance(cve_id, package_id, image_ref, sbom)
        second = assemble_provenance(cve_id, package_id, image_ref, sbom)

        note(f"registration plan: {[(layer.value, eco.value) for layer, eco, _ in plan]}")
        note(f"first call:  {first!r}")
        note(f"second call: {second!r}")

        assert first == second, f"assemble_provenance is not idempotent: {first!r} != {second!r}"
    finally:
        _registry_mod._REGISTRY.clear()
