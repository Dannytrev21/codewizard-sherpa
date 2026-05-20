"""Phase 7 S2-05 — Hypothesis strategies + the `adapter_returning` adapter
factory shared by the vuln-provenance property tests.

Two responsibilities:

- **`adapter_returning(expected)`** builds a fresh, dependency-free
  `VulnProvenanceAdapter`-shaped class whose `attribute(...)` returns a fixed
  `Provenance` value. A new class per call means `(Layer, Ecosystem)` registry
  keys never collide when one test registers several adapters, and the
  `default_adapter_factory` constructs it with no DI kwargs (no `__init__`).

- **`app_kind_strategy()` / `base_kind_strategy()`** generate the non-`Both`,
  non-`Unknown` variants of `Provenance` — `AppKind`
  (`AppDirect | AppTransitive | AppVendored`) and `BaseKind`
  (`BaseImage | RuntimeBundled`). Every identifier field is smart-constructed
  through `codegenie.types.parsers` (S1-01), so each generated value is a
  validated domain object, never a raw string.

The fixed call-argument helpers (`cve`, `package`, `image`, `empty_sbom`) and
the concrete `an_app_direct` / `a_base_image` builders keep the three property
modules DRY — they all assemble against the same canned inputs.

This module is `_`-prefixed so pytest never collects it as a test file; it is
imported explicitly by the sibling `test_*.py` modules.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import strategies as st

from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom
from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    AppDirect,
    AppKind,
    AppTransitive,
    AppVendored,
    BaseImage,
    BaseKind,
    DistroPackage,
    Provenance,
    RuntimeBundled,
)
from codegenie.types.identifiers import CveId, ImageRef, PackageId
from codegenie.types.parsers import (
    parse_cve_id,
    parse_docker_stage_name,
    parse_image_digest,
    parse_image_ref,
    parse_layer_digest,
    parse_package_id,
    parse_runtime_id,
)

# ---------------------------------------------------------------------------
# adapter_returning — the dynamic test-only adapter factory (AC-5).
# ---------------------------------------------------------------------------


def adapter_returning(expected: Provenance) -> type[VulnProvenanceAdapter]:
    """Build a fresh `VulnProvenanceAdapter`-shaped class returning `expected`.

    The class is dependency-free (no `__init__`), so S2-02's
    `default_adapter_factory` constructs it with zero DI kwargs. A new class
    object per call keeps `(Layer, Ecosystem)` registry keys collision-free
    across multiple registrations within a single property example.
    """

    class _ReturningAdapter:
        def attribute(
            self,
            cve_id: CveId,
            package_id: PackageId,
            image_ref: ImageRef | None,
            sbom: SyftSbom,
        ) -> Provenance:
            return expected

        def confidence(self) -> AdapterConfidence:
            return AdapterConfidence.HIGH

    return _ReturningAdapter


# ---------------------------------------------------------------------------
# Fixed call-argument helpers — `assemble_provenance` positional inputs.
#
# The stub adapters built by `adapter_returning` ignore these and return a
# canned `Provenance`; the values only need to be structurally valid so the
# call signature is satisfied.
# ---------------------------------------------------------------------------


def cve() -> CveId:
    """A fixed, valid `CveId` for `assemble_provenance` calls."""
    return parse_cve_id("CVE-2025-12345").unwrap()


def package() -> PackageId:
    """A fixed, valid `PackageId` for `assemble_provenance` calls."""
    return parse_package_id("lodash@4.17.21").unwrap()


def image() -> ImageRef:
    """A fixed, valid `ImageRef` for `assemble_provenance` calls."""
    return parse_image_ref("docker.io/example/app:1.2.3").unwrap()


def empty_sbom() -> SyftSbom:
    """An artifact-free `SyftSbom` — structurally valid, never inspected by
    the stub adapters."""
    return SyftSbom()


# ---------------------------------------------------------------------------
# Concrete variant builders — fixed values for the dispatch-order test.
# ---------------------------------------------------------------------------


def an_app_direct() -> AppDirect:
    """A fixed `AppDirect` — the APP-layer result in the dispatch-order spec."""
    return AppDirect(
        manifest_path=Path("package.json"),
        package=package(),
        confidence=AdapterConfidence.HIGH,
    )


def a_base_image(digest_char: str) -> BaseImage:
    """A fixed `BaseImage` whose `image_digest` varies by `digest_char` — lets
    the dispatch-order spec carry two distinct BASE_IMAGE results."""
    return BaseImage(
        image_digest=parse_image_digest("sha256:" + digest_char * 64).unwrap(),
        layer_digest=parse_layer_digest("sha256:" + "b" * 64).unwrap(),
        distro_pkg=DistroPackage(name="openssl", version="3.0.0", distro="alpine"),
        stage=parse_docker_stage_name("runtime").unwrap(),
        confidence=AdapterConfidence.HIGH,
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies for the AppKind / BaseKind variant unions.
#
# Component strategies are module-level (built once at import); the public
# `app_kind_strategy()` / `base_kind_strategy()` compose them with `st.one_of`
# so a generated value spans every variant of its union.
# ---------------------------------------------------------------------------

_CONFIDENCE: st.SearchStrategy[AdapterConfidence] = st.sampled_from(list(AdapterConfidence))

_PACKAGE_IDS: st.SearchStrategy[PackageId] = st.sampled_from(
    [
        parse_package_id(spec).unwrap()
        for spec in ("lodash@4.17.21", "react@18.2.0", "express@4.18.2")
    ]
)

_MANIFEST_PATHS: st.SearchStrategy[Path] = st.sampled_from(
    [Path("package.json"), Path("app/package.json"), Path("packages/api/package.json")]
)

_VENDORED_PATHS: st.SearchStrategy[Path] = st.sampled_from(
    [Path("vendor/lodash"), Path("third_party/react"), Path("vendor/nested/express")]
)

_IMAGE_DIGESTS: st.SearchStrategy = st.sampled_from(
    [parse_image_digest("sha256:" + char * 64).unwrap() for char in "abcdef"]
)

_LAYER_DIGESTS: st.SearchStrategy = st.sampled_from(
    [parse_layer_digest("sha256:" + char * 64).unwrap() for char in "0123456789"]
)

_DOCKER_STAGES: st.SearchStrategy = st.sampled_from(
    [
        parse_docker_stage_name("runtime").unwrap(),
        parse_docker_stage_name("builder").unwrap(),
        None,
    ]
)

_RUNTIME_IDS: st.SearchStrategy = st.sampled_from(
    [parse_runtime_id(spec).unwrap() for spec in ("node20", "python3-11", "openjdk-21")]
)

_DISTRO_PACKAGES: st.SearchStrategy[DistroPackage] = st.builds(
    DistroPackage,
    name=st.sampled_from(["openssl", "zlib", "libcrypto"]),
    version=st.sampled_from(["3.0.0", "1.2.13", "1.1.1w"]),
    distro=st.sampled_from(["alpine", "debian", "ubuntu", "rhel"]),
)

_APP_DIRECT: st.SearchStrategy[AppDirect] = st.builds(
    AppDirect,
    manifest_path=_MANIFEST_PATHS,
    package=_PACKAGE_IDS,
    confidence=_CONFIDENCE,
)

_APP_TRANSITIVE: st.SearchStrategy[AppTransitive] = st.builds(
    AppTransitive,
    manifest_path=_MANIFEST_PATHS,
    package=_PACKAGE_IDS,
    # AppTransitive.chain is Field(min_length=2): a resolution path of >= 2 hops.
    chain=st.lists(_PACKAGE_IDS, min_size=2, max_size=4).map(tuple),
    confidence=_CONFIDENCE,
)

_APP_VENDORED: st.SearchStrategy[AppVendored] = st.builds(
    AppVendored,
    vendored_path=_VENDORED_PATHS,
    package=_PACKAGE_IDS,
    confidence=_CONFIDENCE,
)

_BASE_IMAGE: st.SearchStrategy[BaseImage] = st.builds(
    BaseImage,
    image_digest=_IMAGE_DIGESTS,
    layer_digest=_LAYER_DIGESTS,
    distro_pkg=_DISTRO_PACKAGES,
    stage=_DOCKER_STAGES,
    confidence=_CONFIDENCE,
)

_RUNTIME_BUNDLED: st.SearchStrategy[RuntimeBundled] = st.builds(
    RuntimeBundled,
    runtime=_RUNTIME_IDS,
    bundled_path=st.sampled_from([Path("/usr/local/lib/node"), Path("/opt/python")]),
    package=_PACKAGE_IDS,
    confidence=_CONFIDENCE,
)


def app_kind_strategy() -> st.SearchStrategy[AppKind]:
    """Generate any `AppKind` variant — `AppDirect | AppTransitive |
    AppVendored`. Used by `test_both_invariant.py` for the APP-layer record."""
    return st.one_of(_APP_DIRECT, _APP_TRANSITIVE, _APP_VENDORED)


def base_kind_strategy() -> st.SearchStrategy[BaseKind]:
    """Generate any `BaseKind` variant — `BaseImage | RuntimeBundled`. Used by
    `test_both_invariant.py` for the BASE_IMAGE-layer record."""
    return st.one_of(_BASE_IMAGE, _RUNTIME_BUNDLED)
