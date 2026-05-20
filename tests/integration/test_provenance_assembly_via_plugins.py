"""Phase 7 S3-01 — cross-component contract test for npm app-layer provenance.

This is a **red-first TDD story**: the test file is the deliverable. It pins
the cross-component invariant *before* the adapter body lands —

    plugin load (canonical loader)
      -> `@register_provenance_adapter(layer=APP, ecosystem=NPM)` side effect
      -> `assemble_provenance(...)` walks `_ADAPTER_DISPATCH_ORDER`
      -> the NPM adapter class is produced for `(Layer.APP, Ecosystem.NPM)`
      -> `AdapterFactory` constructs it, `.attribute(...)` runs
      -> a typed `Provenance` variant is returned

RED on this branch: no `NpmVulnProvenanceAdapter` is registered, so
`assemble_provenance(...)` composes to `Unknown(reason="no_adapter_resolved")`
(`assembly.py` §`(None, None)` arm). The three positive-path scenarios are
therefore `xfail(strict=True)` — CI stays green, but a scenario that passes
for the *wrong* reason (e.g. a leftover registration) breaks the strict gate.

GREEN handoff: Phase 7 S3-02 lands `NpmVulnProvenanceAdapter`; S3-03 wires the
plugin import. As part of that work the three `xfail` markers are removed and
`test_red_state_when_no_npm_adapter_registered` is deleted or inverted.

Contract discipline (Phase 7 ADR-0006, ADR-0007): the test reads ONLY the
public surface — `assemble_provenance` and `load_plugins`. It never imports an
adapter class directly and never peeks into `_REGISTRY`. A test that side-steps
the assembly seam is a unit test (S3-02's job), not a contract test.

Registry isolation is provided by the autouse `provenance_registry_reset`
fixture in `tests/integration/conftest.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.plugins.loader import load_plugins
from codegenie.primitives.vuln_provenance import (
    AppDirect,
    AppTransitive,
    Provenance,
    Unknown,
    assemble_provenance,
)
from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom
from codegenie.types.identifiers import CveId, ImageRef, PackageId

# Repo-anchored paths: tests/integration/<this file> -> parents[2] is the repo
# root. The test drives the *real* `plugins/` tree so that when S3-02/S3-03
# land the npm plugin there, this exact test transitions red -> green with no
# edit to the loader call. Today `plugins/` holds no `*/plugin.yaml`, so the
# loader returns `Ok(LoadReport(loaded=(), total_walked=0))`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / "plugins"
_PLUGIN_LOCK = _PLUGIN_ROOT / "PLUGINS.lock"

_SBOM_FIXTURE = Path(__file__).parent / "_fixtures" / "syft_sboms" / "npm_lodash_app.json"

# `ImageRef` is a `NewType` over `str` (`codegenie.types.identifiers`); it has
# no smart-constructor `.parse(...)`, so it is constructed directly. The loader
# does not consume the ref — `assemble_provenance` hands it to each adapter.
# An Alpine ref is used only so the value is a real, non-empty reference; this
# story does not exercise any base-image adapter.
_IMAGE_REF = ImageRef("alpine:3.18@sha256:" + "0" * 64)

# A representative npm CVE (lodash prototype pollution). The value is opaque to
# the assembly seam in the red state — it is forwarded to adapters that do not
# yet exist.
_CVE_ID = CveId("CVE-2021-23337")

# Marker xfail reason, shared by the three positive-path scenarios so the
# green-phase handoff (S3-02 removes them) is a single grep.
_GREEN_WHEN = "goes green when Phase 7 S3-02 lands NpmVulnProvenanceAdapter"


def _assemble(package_id: PackageId) -> Provenance:
    """Drive plugin load via the canonical loader, then the public assembly seam.

    The loader call is what makes the contract test honest: registration is a
    side effect of importing each plugin's ``api.py``, never a direct import in
    the test. `assemble_provenance` is the only path to an adapter result —
    `_REGISTRY` is never touched directly.
    """
    load_result = load_plugins(_PLUGIN_ROOT, _PLUGIN_LOCK)
    assert load_result.is_ok(), f"plugin load failed: {load_result!r}"
    sbom = SyftSbom.model_validate_json(_SBOM_FIXTURE.read_bytes())
    return assemble_provenance(
        cve_id=_CVE_ID,
        package_id=package_id,
        image_ref=_IMAGE_REF,
        sbom=sbom,
    )


@pytest.mark.xfail(strict=True, reason=_GREEN_WHEN)
def test_npm_adapter_returns_app_direct_for_root_dependency() -> None:
    """A package declared as a direct dependency resolves to `AppDirect`."""
    result = _assemble(PackageId("lodash"))
    match result:
        case AppDirect() as app:
            assert app.package == PackageId("lodash")
        case _:
            pytest.fail(f"expected AppDirect, got: {result!r}")


@pytest.mark.xfail(strict=True, reason=_GREEN_WHEN)
def test_npm_adapter_returns_app_transitive_for_deep_dependency() -> None:
    """A package pulled in transitively resolves to `AppTransitive` with a
    resolution chain of length >= 2 whose head is the declaring root."""
    result = _assemble(PackageId("lodash"))
    match result:
        case AppTransitive() as app:
            assert len(app.chain) >= 2
            assert app.chain[0] == PackageId("express")
        case _:
            pytest.fail(f"expected AppTransitive, got: {result!r}")


@pytest.mark.xfail(strict=True, reason=_GREEN_WHEN)
def test_npm_adapter_returns_unknown_when_package_absent() -> None:
    """A package the adapter ran against but could not attribute resolves to
    `Unknown(reason="sbom_layer_attribution_absent")` — the typed "ran and
    observed absence" reason, distinct from `no_adapter_resolved`."""
    result = _assemble(PackageId("not-in-this-repo"))
    match result:
        case Unknown(reason="sbom_layer_attribution_absent"):
            pass
        case _:
            pytest.fail(f"expected Unknown(sbom_layer_attribution_absent), got: {result!r}")


def test_red_state_when_no_npm_adapter_registered() -> None:
    """Canary for the TDD red phase.

    With no `(Layer.APP, Ecosystem.NPM)` adapter registered, `assemble_provenance`
    walks an empty dispatch and composes to `Unknown(reason="no_adapter_resolved")`
    — the `(None, None)` arm of `assembly.py`. This test passes today and will
    FAIL once S3-02 registers the adapter; S3-03 deletes or inverts it then.
    """
    result = _assemble(PackageId("lodash"))
    match result:
        case Unknown(reason="no_adapter_resolved"):
            pass
        case _:
            pytest.fail(f"expected Unknown(no_adapter_resolved) in the red state, got: {result!r}")
