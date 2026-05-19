"""Phase 7 S1-03 AC-9 — exhaustiveness via `match` + `assert_never`.

ADR-0006 requires every downstream consumer of `Provenance` to `match` on
the discriminator and call `assert_never(p)` in the wildcard arm so a
missing variant is a mypy --strict error, not a silent fall-through at
runtime. This test exercises a reference summariser that does exactly
that — adding an 8th variant without growing this `match` is an
intentional type error (the wildcard `assert_never(p)` makes the
parameter's type narrow to `Never`).

The runtime assertions pin behaviour (each fixture maps to the correct
arm string). The static contract (no missing arm) is enforced by
`mypy --strict` running over this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

import pytest

from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AppDirect,
    AppTransitive,
    AppVendored,
    BaseImage,
    Both,
    DistroPackage,
    Provenance,
    RuntimeBundled,
    Unknown,
)
from codegenie.types.identifiers import (
    DockerStageName,
    ImageDigest,
    LayerDigest,
    PackageId,
    RuntimeId,
)


def _summarise(p: Provenance) -> str:
    """Reference exhaustive matcher — drift here breaks `mypy --strict`."""
    match p:
        case AppDirect():
            return "app_direct"
        case AppTransitive():
            return "app_transitive"
        case AppVendored():
            return "app_vendored"
        case BaseImage():
            return "base_image"
        case RuntimeBundled():
            return "runtime_bundled"
        case Both():
            return "both"
        case Unknown():
            return "unknown"
        case _:  # pragma: no cover — unreachable; mypy enforces.
            assert_never(p)


@pytest.fixture
def app_direct() -> AppDirect:
    return AppDirect(
        manifest_path=Path("package.json"),
        package=PackageId("lodash@4.17.21"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def app_transitive() -> AppTransitive:
    return AppTransitive(
        manifest_path=Path("package.json"),
        package=PackageId("nested@1.0.0"),
        chain=(PackageId("a@1.0.0"), PackageId("nested@1.0.0")),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def app_vendored() -> AppVendored:
    return AppVendored(
        vendored_path=Path("vendor/some-lib"),
        package=PackageId("v@1.0.0"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def base_image() -> BaseImage:
    return BaseImage(
        image_digest=ImageDigest("sha256:" + "0" * 64),
        layer_digest=LayerDigest("sha256:" + "a" * 64),
        distro_pkg=DistroPackage(name="openssl", version="3.0.7", distro="alpine"),
        stage=DockerStageName("builder"),
        confidence=AdapterConfidence.HIGH,
    )


@pytest.fixture
def runtime_bundled() -> RuntimeBundled:
    return RuntimeBundled(
        runtime=RuntimeId("node20"),
        bundled_path=Path("/usr/lib/node_modules/x"),
        package=PackageId("x@1.0.0"),
        confidence=AdapterConfidence.HIGH,
    )


def test_summarise_app_direct(app_direct: AppDirect) -> None:
    assert _summarise(app_direct) == "app_direct"


def test_summarise_app_transitive(app_transitive: AppTransitive) -> None:
    assert _summarise(app_transitive) == "app_transitive"


def test_summarise_app_vendored(app_vendored: AppVendored) -> None:
    assert _summarise(app_vendored) == "app_vendored"


def test_summarise_base_image(base_image: BaseImage) -> None:
    assert _summarise(base_image) == "base_image"


def test_summarise_runtime_bundled(runtime_bundled: RuntimeBundled) -> None:
    assert _summarise(runtime_bundled) == "runtime_bundled"


def test_summarise_both(app_direct: AppDirect, base_image: BaseImage) -> None:
    both = Both(app_record=app_direct, base_record=base_image)
    assert _summarise(both) == "both"


def test_summarise_unknown() -> None:
    assert _summarise(Unknown(reason="no_adapter_resolved")) == "unknown"
