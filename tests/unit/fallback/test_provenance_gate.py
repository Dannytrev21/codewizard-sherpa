"""Phase-4 S2-01 — ``ProvenanceGate`` red-green-refactor TDD suite.

Verifies the tier-0 short-circuit primitive that runs before any LLM tokens
are spent: classifier delegation, ``ProvenanceClassified`` event emission,
``ProvenanceError`` folding to ``Unknown``, propagation of unrelated
exceptions, the exact ``_APP_LAYER_PROVENANCE_KINDS`` constant, and the
``is_app_layer`` predicate over all seven real ``Provenance`` variants.

ADRs honored: Phase-4 ADR-0012 (explicit tier-0 gate), Phase-4 ADR-0003
(path-scoped fence — module lives under ``src/codegenie/fallback/``),
production ADR-0038 (the seven-variant ``Provenance`` primitive consumed
here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from codegenie.fallback.provenance_gate import (
    _APP_LAYER_PROVENANCE_KINDS,
    ProvenanceClassifier,
    ProvenanceGate,
    is_app_layer,
)
from codegenie.plugins.events import EventLog, ProvenanceClassified
from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AdapterError,
    AppDirect,
    AppTransitive,
    AppVendored,
    BaseImage,
    Both,
    DistroPackage,
    Provenance,
    ProvenanceError,
    RuntimeBundled,
    SyftSbom,
    Unknown,
)
from codegenie.types.identifiers import CveId, ImageRef, PackageId, WorkflowId
from codegenie.types.parsers import (
    parse_docker_stage_name,
    parse_image_digest,
    parse_layer_digest,
    parse_runtime_id,
)

# ---------------------------------------------------------------------------
# Real-variant constructors — typed provenance instances, not strings.
# ---------------------------------------------------------------------------


def _cve() -> CveId:
    return CveId("CVE-2025-12345")


def _package() -> PackageId:
    return PackageId("lodash@4.17.21")


def _image() -> ImageRef:
    return ImageRef("docker.io/example/app:1.2.3")


def _sbom() -> SyftSbom:
    return SyftSbom()


def _workflow() -> WorkflowId:
    return WorkflowId("01HWF00000000000000000000")


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
        chain=(PackageId("express@5.0.0"), pkg),
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


def _runtime_bundled() -> RuntimeBundled:
    return RuntimeBundled(
        runtime=parse_runtime_id("node20").unwrap(),
        bundled_path=Path("lib/node/npm"),
        package=_package(),
        confidence=AdapterConfidence.DEGRADED,
    )


def _both() -> Both:
    return Both(app_record=_app_direct(), base_record=_base_image())


def _unknown() -> Unknown:
    return Unknown(reason="no_adapter_resolved")


_PROVENANCE_CASES: tuple[tuple[Provenance, bool], ...] = (
    (_app_direct(), True),
    (_app_transitive(), True),
    (_app_vendored(), True),
    (_both(), True),
    (_base_image(), False),
    (_runtime_bundled(), False),
    (_unknown(), False),
)


# ---------------------------------------------------------------------------
# Typed fakes — hand-rolled so type errors surface at call site, not in
# MagicMock(spec=Protocol) ducked-typing dynamism.
# ---------------------------------------------------------------------------


@dataclass
class ReturningClassifier:
    """Records every call and returns a pre-configured ``Provenance``."""

    result: Provenance
    calls: list[tuple[CveId, PackageId, ImageRef | None, SyftSbom]] = field(default_factory=list)

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        self.calls.append((cve_id, package_id, image_ref, sbom))
        return self.result


class FailingClassifier:
    """Raises ``AdapterError`` — a ``ProvenanceError`` subclass the gate folds."""

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        raise AdapterError("npm registry timeout")


class ProvenanceErrorClassifier:
    """Raises the bare ``ProvenanceError`` base — also fold-able by AC-7."""

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        raise ProvenanceError("upstream provenance subsystem unavailable")


class BuggyClassifier:
    """Raises ``TypeError`` — an unrelated bug; AC-7 says do NOT swallow."""

    def classify(
        self,
        cve_id: CveId,
        package_id: PackageId,
        image_ref: ImageRef | None,
        sbom: SyftSbom,
    ) -> Provenance:
        raise TypeError("programming bug")


def _make_gate(classifier: ProvenanceClassifier, tmp_path: Path) -> tuple[ProvenanceGate, EventLog]:
    log = EventLog(root=tmp_path, workflow_id=_workflow())
    gate = ProvenanceGate(classifier=classifier, event_log=log)
    return gate, log


def _events(log: EventLog) -> list[ProvenanceClassified]:
    return [e for e in log.replay() if isinstance(e, ProvenanceClassified)]


# ---------------------------------------------------------------------------
# AC-3 — `_APP_LAYER_PROVENANCE_KINDS` is exact and immutable
# ---------------------------------------------------------------------------


def test_app_layer_kinds_are_exact_lowercase_values() -> None:
    assert _APP_LAYER_PROVENANCE_KINDS == frozenset(
        {"app_direct", "app_transitive", "app_vendored", "both"}
    )


def test_app_layer_kinds_is_a_frozenset_and_immutable() -> None:
    assert isinstance(_APP_LAYER_PROVENANCE_KINDS, frozenset)
    # frozenset has no mutating ops — defense against accidental conversion.
    assert not hasattr(_APP_LAYER_PROVENANCE_KINDS, "add")


# ---------------------------------------------------------------------------
# AC-4 — `is_app_layer` predicate over real `Provenance` variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("provenance", "expected"), _PROVENANCE_CASES)
def test_is_app_layer_table(provenance: Provenance, expected: bool) -> None:
    assert is_app_layer(provenance) is expected


# ---------------------------------------------------------------------------
# AC-6 — `ProvenanceGate.classify` delegates exactly once and emits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("provenance", "_expected"), _PROVENANCE_CASES)
def test_classify_delegates_once_and_emits_event(
    tmp_path: Path, provenance: Provenance, _expected: bool
) -> None:
    classifier = ReturningClassifier(provenance)
    gate, log = _make_gate(classifier, tmp_path)

    result = gate.classify(_cve(), _package(), _image(), _sbom())

    assert result is provenance
    assert classifier.calls == [(_cve(), _package(), _image(), _sbom())]
    events = _events(log)
    assert len(events) == 1
    assert events[0].provenance_kind == provenance.kind
    assert events[0].adapter_error is None


def test_classify_passes_through_none_image_ref(tmp_path: Path) -> None:
    classifier = ReturningClassifier(_app_direct())
    gate, log = _make_gate(classifier, tmp_path)

    gate.classify(_cve(), _package(), None, _sbom())

    assert classifier.calls == [(_cve(), _package(), None, _sbom())]
    assert len(_events(log)) == 1


# ---------------------------------------------------------------------------
# AC-7 — `ProvenanceError` folds to `Unknown`; bugs propagate
# ---------------------------------------------------------------------------


def test_adapter_error_folds_to_unknown_and_emits_structured_event(
    tmp_path: Path,
) -> None:
    gate, log = _make_gate(FailingClassifier(), tmp_path)

    result = gate.classify(_cve(), _package(), _image(), _sbom())

    assert isinstance(result, Unknown)
    assert result.reason == "adapter_error"
    assert result.details == {"error": "npm registry timeout"}
    events = _events(log)
    assert len(events) == 1
    assert events[0].provenance_kind == "unknown"
    assert events[0].adapter_error == "npm registry timeout"


def test_bare_provenance_error_also_folds_to_unknown(tmp_path: Path) -> None:
    """AC-7: ``ProvenanceError`` *base* (not just ``AdapterError``) folds too."""
    gate, log = _make_gate(ProvenanceErrorClassifier(), tmp_path)

    result = gate.classify(_cve(), _package(), _image(), _sbom())

    assert isinstance(result, Unknown)
    assert result.reason == "adapter_error"
    events = _events(log)
    assert len(events) == 1
    assert events[0].adapter_error == "upstream provenance subsystem unavailable"


def test_non_provenance_exception_is_not_swallowed(tmp_path: Path) -> None:
    gate, _log = _make_gate(BuggyClassifier(), tmp_path)

    with pytest.raises(TypeError, match="programming bug"):
        gate.classify(_cve(), _package(), _image(), _sbom())


def test_non_provenance_exception_emits_no_event(tmp_path: Path) -> None:
    """A propagated bug must not leak a partial ``ProvenanceClassified`` event."""
    gate, log = _make_gate(BuggyClassifier(), tmp_path)

    with pytest.raises(TypeError):
        gate.classify(_cve(), _package(), _image(), _sbom())

    assert _events(log) == []


# ---------------------------------------------------------------------------
# AC-2 — facade discipline: no second adapter family under fallback/
# ---------------------------------------------------------------------------


def test_provenance_classifier_is_runtime_checkable_protocol() -> None:
    """The Phase-4 facade Protocol uses structural typing — a duck-typed
    classifier (no inheritance) satisfies ``isinstance(_, ProvenanceClassifier)``."""

    classifier = ReturningClassifier(_app_direct())
    assert isinstance(classifier, ProvenanceClassifier)


# ---------------------------------------------------------------------------
# AC-10 — Public surface forbids `Any` (compile-time via mypy; runtime smoke).
# ---------------------------------------------------------------------------


def test_public_surface_is_exported() -> None:
    """The fallback package re-exports the gate surface for downstream callers."""
    from codegenie.fallback import (
        _APP_LAYER_PROVENANCE_KINDS as _re_kinds,
    )
    from codegenie.fallback import (
        ProvenanceClassifier as _re_classifier,
    )
    from codegenie.fallback import (
        ProvenanceGate as _re_gate,
    )
    from codegenie.fallback import (
        is_app_layer as _re_predicate,
    )

    assert _re_gate is ProvenanceGate
    assert _re_classifier is ProvenanceClassifier
    assert _re_kinds is _APP_LAYER_PROVENANCE_KINDS
    assert _re_predicate is is_app_layer
