"""Phase 7 S2-05 — the `Both` no-recursion invariant, proven with Hypothesis.

**AC-3** — Phase 7 ADR-0006 §Consequences last bullet: for ANY non-`Unknown`
`(AppKind, BaseKind)` pair, `assemble_provenance` returns
`Both(app_record=app, base_record=base)` where

- `app_record` is always an `AppKind` variant (`AppDirect | AppTransitive |
  AppVendored`),
- `base_record` is always a `BaseKind` variant (`BaseImage | RuntimeBundled`),
- and **neither field is itself a `Both`**.

S1-03 makes nested `Both` unrepresentable at the type level — `Both.app_record`
and `Both.base_record` are discriminated unions over non-`Both`, non-`Unknown`
variants only. This property test proves that guard holds end-to-end: from the
adapter return values, through `assemble_provenance`'s `match` composition, to
the constructed `Both`.

`test_both_invariant.py` is cross-referenced by S12-03, which extends it to
the end-to-end `RequiresMultiPluginCoordination` event emission.

Registry isolation mirrors the sibling property modules (autouse
`provenance_registry_reset` fixture + per-example `finally:` clear + AC-6
sanity assertion).
"""

from __future__ import annotations

from hypothesis import given, note, settings

from codegenie.primitives.vuln_provenance import assemble_provenance
from codegenie.primitives.vuln_provenance import registry as _registry_mod
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.types import (
    AppDirect,
    AppKind,
    AppTransitive,
    AppVendored,
    BaseImage,
    BaseKind,
    Both,
    Provenance,
    RuntimeBundled,
)
from tests.property.vuln_provenance._strategies import (
    adapter_returning,
    app_kind_strategy,
    base_kind_strategy,
    cve,
    empty_sbom,
    image,
    package,
)

_APP_VARIANTS = (AppDirect, AppTransitive, AppVendored)
_BASE_VARIANTS = (BaseImage, RuntimeBundled)


@settings(max_examples=30, deadline=None)
@given(app_value=app_kind_strategy(), base_value=base_kind_strategy())
def test_both_app_record_is_appkind_base_record_is_basekind_never_both(
    app_value: AppKind,
    base_value: BaseKind,
) -> None:
    """AC-3 — Phase 7 ADR-0006 §Consequences last bullet.

    Register exactly one APP adapter returning a Hypothesis-generated
    `AppKind` and one BASE_IMAGE adapter returning a generated `BaseKind`.
    `assemble_provenance` must compose them into a `Both` whose `app_record`
    is an `AppKind` variant and `base_record` a `BaseKind` variant — and
    neither nested record is itself a `Both`. S1-03's type-level recursion
    guard holds for every generated pair.
    """
    assert _registry_mod._REGISTRY == {}, "registry not clean at example start (AC-6)"
    try:
        register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)(
            adapter_returning(app_value)
        )
        register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)(
            adapter_returning(base_value)
        )

        result = assemble_provenance(cve(), package(), image(), empty_sbom())

        note(f"app_value:  {app_value!r}")
        note(f"base_value: {base_value!r}")
        note(f"result:     {result!r}")

        assert isinstance(result, Both), (
            f"non-Unknown (AppKind, BaseKind) pair must compose to Both; "
            f"got {type(result).__name__}: {result!r}"
        )

        # Widen the nested records to the full `Provenance` union before the
        # guard checks below. `Both` IS a member of `Provenance`, so the
        # `not isinstance(..., Both)` assertions are LIVE runtime checks — not
        # statically-dead ones. S1-03 makes `Both.app_record: AppKind` /
        # `Both.base_record: BaseKind` exclude `Both` at the type level; this
        # test proves that type-level guarantee survives assembly at runtime.
        # If a future change weakens S1-03's union so a nested `Both` becomes
        # representable, these assertions start failing loud.
        app_record: Provenance = result.app_record
        base_record: Provenance = result.base_record

        assert not isinstance(app_record, Both), (
            f"Both.app_record is itself a Both — recursion guard breached: {result!r}"
        )
        assert not isinstance(base_record, Both), (
            f"Both.base_record is itself a Both — recursion guard breached: {result!r}"
        )
        assert isinstance(app_record, _APP_VARIANTS), (
            f"Both.app_record is not an AppKind variant: {app_record!r}"
        )
        assert isinstance(base_record, _BASE_VARIANTS), (
            f"Both.base_record is not a BaseKind variant: {base_record!r}"
        )
    finally:
        _registry_mod._REGISTRY.clear()
