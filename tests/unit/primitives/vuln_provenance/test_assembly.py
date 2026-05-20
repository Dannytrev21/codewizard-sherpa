"""Phase 7 S2-04 — `assemble_provenance(...)` free-function composition tests.

Covers AC-1..AC-8 + AC-10..AC-14. The `match (app_result, base_result)`
exhaustiveness AST-walk (AC-9) lives in the sibling
`test_assemble_match_exhaustive.py`.

ADRs exercised: Phase 7 ADR-0006 (walk `_ADAPTER_DISPATCH_ORDER`;
`Ecosystem`-sorted intra-layer), ADR-0007 (construct via `AdapterFactory`;
`ProvenanceError` → `Unknown`), ADR-0001 (`Both` is a typed `Provenance`
variant — no coordinator). The TDD-plan red test is
`test_both_app_and_base_compose_into_both_variant`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from codegenie.primitives.vuln_provenance import assemble_provenance
from codegenie.primitives.vuln_provenance.errors import AdapterError
from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom
from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    AppDirect,
    AppTransitive,
    AppVendored,
    BaseImage,
    Both,
    DistroPackage,
    Provenance,
    Unknown,
)
from codegenie.types.identifiers import CveId, ImageRef, PackageId
from codegenie.types.parsers import (
    parse_cve_id,
    parse_docker_stage_name,
    parse_image_digest,
    parse_image_ref,
    parse_layer_digest,
    parse_package_id,
)

# ---------------------------------------------------------------------------
# Fixtures — smart-constructed identifier values (S1-01 / S1-02 parsers).
# ---------------------------------------------------------------------------


def _cve() -> CveId:
    return parse_cve_id("CVE-2025-12345").unwrap()


def _package() -> PackageId:
    return parse_package_id("lodash@4.17.21").unwrap()


def _image() -> ImageRef:
    return parse_image_ref("docker.io/example/app:1.2.3").unwrap()


def _empty_syft_sbom() -> SyftSbom:
    """An SBOM with no artifacts — `assemble_provenance` never inspects it
    (the stub adapters return canned `Provenance` values); it only needs to
    be a structurally valid `SyftSbom` to satisfy the call signature."""
    return SyftSbom()


def _app_direct() -> AppDirect:
    return AppDirect(
        manifest_path=Path("package.json"),
        package=_package(),
        confidence=AdapterConfidence.HIGH,
    )


def _app_transitive() -> AppTransitive:
    pkg = _package()
    return AppTransitive(
        manifest_path=Path("package.json"),
        package=pkg,
        chain=(pkg, pkg),
        confidence=AdapterConfidence.HIGH,
    )


def _app_vendored() -> AppVendored:
    return AppVendored(
        vendored_path=Path("vendor/lodash"),
        package=_package(),
        confidence=AdapterConfidence.DEGRADED,
    )


def _base_image() -> BaseImage:
    return BaseImage(
        image_digest=parse_image_digest("sha256:" + "a" * 64).unwrap(),
        layer_digest=parse_layer_digest("sha256:" + "b" * 64).unwrap(),
        distro_pkg=DistroPackage(name="openssl", version="3.0.0", distro="alpine"),
        stage=parse_docker_stage_name("runtime").unwrap(),
        confidence=AdapterConfidence.HIGH,
    )


def _make_returning_adapter(returns: Provenance) -> type[VulnProvenanceAdapter]:
    """Build a one-off `VulnProvenanceAdapter`-shaped stub whose
    `attribute(...)` returns a fixed `Provenance`. The caller decorates the
    result with `@register_provenance_adapter(...)` to place it in the
    registry — a fresh class per call so `(Layer, Ecosystem)` keys never
    collide across registrations within one test."""

    class _ReturningAdapter:
        def attribute(
            self,
            cve_id: CveId,
            package_id: PackageId,
            image_ref: ImageRef | None,
            sbom: SyftSbom,
        ) -> Provenance:
            return returns

        def confidence(self) -> AdapterConfidence:
            return AdapterConfidence.HIGH

    return _ReturningAdapter


def _register(layer: Layer, ecosystem: Ecosystem, returns: Provenance) -> None:
    """Register a fixed-result stub adapter under `(layer, ecosystem)`."""
    register_provenance_adapter(layer=layer, ecosystem=ecosystem)(_make_returning_adapter(returns))


# ---------------------------------------------------------------------------
# AC-14 / AC-5 — TDD red test: Both composition.
# ---------------------------------------------------------------------------


def test_both_app_and_base_compose_into_both_variant() -> None:
    """ADR-0006 + ADR-0001: when one APP adapter and one BASE_IMAGE adapter
    both return a non-`Unknown` result, the assembly composes
    `Both(app_record, base_record)` — `Both` becomes evidence (Step 11
    emits `RequiresMultiPluginCoordination`), never a coordinator call.

    Identity (`is`) is asserted, not just value equality: the assembly must
    thread the adapter's exact instance through to `Both` without re-copying
    — that is what lets the Step 11 event log point at the same record."""
    expected_app = _app_transitive()
    expected_base = _base_image()
    _register(Layer.APP, Ecosystem.NPM, expected_app)
    _register(Layer.BASE_IMAGE, Ecosystem.APK, expected_base)

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert isinstance(result, Both)
    assert result.app_record is expected_app
    assert result.base_record is expected_base


# ---------------------------------------------------------------------------
# AC-2 — (None, None) arm.
# ---------------------------------------------------------------------------


def test_empty_registry_returns_unknown_no_adapter_resolved() -> None:
    """AC-2 — with no adapters registered, no layer resolves; the
    `(None, None)` arm returns `Unknown(reason="no_adapter_resolved")`.
    `no_adapter_resolved` (not `adapter_error`) because nothing raised."""
    result = assemble_provenance(_cve(), _package(), None, _empty_syft_sbom())

    assert isinstance(result, Unknown)
    assert result.reason == "no_adapter_resolved"


# ---------------------------------------------------------------------------
# AC-3 — (app, None) arm.
# ---------------------------------------------------------------------------


def test_app_only_returns_app_result_unchanged() -> None:
    """AC-3 — one APP adapter, no BASE_IMAGE adapter: the `(app, None)` arm
    returns the adapter's exact `AppDirect` instance, not a copy and not a
    `Both`. Identity is the contract — the assembly does not re-wrap a
    single-layer result."""
    expected = _app_direct()
    _register(Layer.APP, Ecosystem.NPM, expected)

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert isinstance(result, AppDirect)
    assert result is expected


# ---------------------------------------------------------------------------
# AC-4 — (None, base) arm.
# ---------------------------------------------------------------------------


def test_base_only_returns_base_result_unchanged() -> None:
    """AC-4 — one BASE_IMAGE adapter, no APP adapter: the `(None, base)` arm
    returns the adapter's exact `BaseImage` instance unchanged."""
    expected = _base_image()
    _register(Layer.BASE_IMAGE, Ecosystem.APK, expected)

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert isinstance(result, BaseImage)
    assert result is expected
    assert result.image_digest == expected.image_digest


# ---------------------------------------------------------------------------
# AC-6 — first non-Unknown per layer wins, in Ecosystem-sort order.
# ---------------------------------------------------------------------------


def test_first_non_unknown_adapter_in_layer_wins() -> None:
    """AC-6 — the first adapter (NPM, `Ecosystem` index 0) returns
    `Unknown`; the second (YARN_BERRY, index 1) returns `AppDirect`. The
    `Unknown` is skipped and the layer keeps walking, so the resolved
    result is the `AppDirect`."""
    expected = _app_direct()
    _register(Layer.APP, Ecosystem.NPM, Unknown(reason="sbom_layer_attribution_absent"))
    _register(Layer.APP, Ecosystem.YARN_BERRY, expected)

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert result is expected


def test_ecosystem_sort_order_decides_winner_not_registration_order() -> None:
    """AC-6 — both APP adapters return a non-`Unknown` result. YARN_BERRY is
    registered FIRST, NPM SECOND, but NPM wins because `Ecosystem` index 0
    sorts ahead of index 1 — registration order is not load-bearing
    (ADR-0006 §Consequences; BP-1 closure). Pinning identity to the NPM
    result proves the `Ecosystem`-sort, not insertion order, picks first."""
    npm_result = _app_direct()
    yarn_result = _app_vendored()
    _register(Layer.APP, Ecosystem.YARN_BERRY, yarn_result)  # registered first
    _register(Layer.APP, Ecosystem.NPM, npm_result)  # registered second

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert result is npm_result


# ---------------------------------------------------------------------------
# AC-7 — ProvenanceError folds into Unknown(reason="adapter_error").
# ---------------------------------------------------------------------------


def test_provenance_error_folds_into_unknown_adapter_error() -> None:
    """AC-7 — an adapter raising a `ProvenanceError` subclass
    (`AdapterError`) does not crash the assembly; it is caught and, when no
    other adapter resolves, the final `Unknown` carries
    `reason="adapter_error"` — distinguishing genuine adapter failure from
    `no_adapter_resolved` (ADR-0007 + Rule 12: fail loud over partial
    data)."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _BrokenAdapter:
        def attribute(
            self,
            cve_id: CveId,
            package_id: PackageId,
            image_ref: ImageRef | None,
            sbom: SyftSbom,
        ) -> Provenance:
            raise AdapterError("kaboom")

        def confidence(self) -> AdapterConfidence:
            return AdapterConfidence.UNAVAILABLE

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert isinstance(result, Unknown)
    assert result.reason == "adapter_error"


# ---------------------------------------------------------------------------
# AC-8 — non-ProvenanceError exceptions propagate (Rule 12).
# ---------------------------------------------------------------------------


def test_runtime_error_propagates_and_is_not_swallowed() -> None:
    """AC-8 — a `RuntimeError` (NOT a `ProvenanceError`) raised inside an
    adapter MUST propagate out of `assemble_provenance` unchanged. The
    function catches `ProvenanceError` and nothing wider — swallowing a
    `RuntimeError` would hide a real bug (Rule 12)."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _BuggyAdapter:
        def attribute(
            self,
            cve_id: CveId,
            package_id: PackageId,
            image_ref: ImageRef | None,
            sbom: SyftSbom,
        ) -> Provenance:
            raise RuntimeError("bug")

        def confidence(self) -> AdapterConfidence:
            return AdapterConfidence.HIGH

    with pytest.raises(RuntimeError, match="bug"):
        assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())


# ---------------------------------------------------------------------------
# AC-10 — registry=None defaults to the module _REGISTRY.
# ---------------------------------------------------------------------------


def test_registry_kwarg_defaults_to_module_registry() -> None:
    """AC-10 — an adapter registered via `@register_provenance_adapter`
    mutates the module `_REGISTRY`; calling `assemble_provenance` with
    `registry=None` (the default) dispatches against that registry, so the
    registered adapter runs and its result is returned."""
    expected = _app_direct()
    _register(Layer.APP, Ecosystem.NPM, expected)

    result = assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom(), registry=None)

    assert result is expected


# ---------------------------------------------------------------------------
# AC-11 — adapter_factory=None defaults to default_adapter_factory.
# ---------------------------------------------------------------------------


def test_default_factory_constructs_each_adapter_exactly_once() -> None:
    """AC-11 — with no `adapter_factory` kwarg, `assemble_provenance` builds
    the adapter through `default_adapter_factory`. A dependency-free adapter
    is constructed exactly once per dispatch — construction is lazy
    (dispatch-time), not eager (decoration-time)."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _CountingAdapter:
        construct_count = 0

        def __init__(self) -> None:
            type(self).construct_count += 1

        def attribute(
            self,
            cve_id: CveId,
            package_id: PackageId,
            image_ref: ImageRef | None,
            sbom: SyftSbom,
        ) -> Provenance:
            return _app_direct()

        def confidence(self) -> AdapterConfidence:
            return AdapterConfidence.HIGH

    assemble_provenance(_cve(), _package(), _image(), _empty_syft_sbom())

    assert _CountingAdapter.construct_count == 1


# ---------------------------------------------------------------------------
# AC-1 — exact public signature.
# ---------------------------------------------------------------------------


def test_function_signature_is_exact() -> None:
    """AC-1 — the signature is the downstream contract S8 (TCCM resolver)
    binds against. Pins parameter names, positional-vs-keyword-only kinds,
    and the `None` defaults on the two keyword-only kwargs."""
    params = list(inspect.signature(assemble_provenance).parameters.values())

    assert [p.name for p in params] == [
        "cve_id",
        "package_id",
        "image_ref",
        "sbom",
        "registry",
        "adapter_factory",
    ]
    positional = inspect.Parameter.POSITIONAL_OR_KEYWORD
    keyword_only = inspect.Parameter.KEYWORD_ONLY
    assert [p.kind for p in params[:4]] == [positional] * 4
    assert params[4].kind == keyword_only
    assert params[5].kind == keyword_only
    assert params[4].default is None
    assert params[5].default is None


# ---------------------------------------------------------------------------
# AC-12 — function body ≤ 80 LOC.
# ---------------------------------------------------------------------------


def test_function_body_is_at_most_80_loc() -> None:
    """AC-12 — arch §6 budgets `assemble_provenance` at ≤ 80 LOC. A larger
    body means the composition grew a branch it should not have; the fix is
    extracting a helper, never widening the function."""
    func = ast.parse(inspect.getsource(assemble_provenance)).body[0]
    assert isinstance(func, ast.FunctionDef)
    body = func.body[1:] if isinstance(func.body[0], ast.Expr) else func.body
    line_count = (body[-1].end_lineno or 0) - (body[0].lineno or 0) + 1

    assert line_count <= 80, f"assemble_provenance body is {line_count} LOC (budget 80)"


# ---------------------------------------------------------------------------
# AC-13 — `provenance` re-export alias.
# ---------------------------------------------------------------------------


def test_provenance_alias_is_assemble_provenance() -> None:
    """AC-13 — `provenance` is the TCCM-facing name S8-02's
    `compute: vuln.provenance` resolves to. It is a pure re-export alias of
    `assemble_provenance` — same object, hence same signature."""
    from codegenie.primitives.vuln_provenance import (
        assemble_provenance as ap,
    )
    from codegenie.primitives.vuln_provenance import (
        provenance,
    )

    assert provenance is ap
