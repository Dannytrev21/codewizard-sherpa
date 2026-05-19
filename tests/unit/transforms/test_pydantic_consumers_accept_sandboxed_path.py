"""S4-04 AC-Sub-3 — existing Pydantic consumers accept the new
``SandboxedPath``.

After the ``_forward.py`` flip, every consumer that already imports
``SandboxedPath`` from ``codegenie.transforms`` resolves to the Pydantic
``BaseModel``. Two round-trip tests confirm the consumer-side surface is
not broken:

1. ``Transform.files_changed: tuple[SandboxedPath, ...]`` — Transform is
   the ABC; the field is a class-level annotation on a concrete subclass.
   Construction with a tuple of real ``SandboxedPath`` instances works.
2. ``AttemptSummary.evidence_paths: tuple[SandboxedPath, ...]`` —
   AttemptSummary is a Pydantic ``BaseModel`` with ``extra="forbid"``;
   construction with a tuple of real ``SandboxedPath`` instances passes
   validation (no ``ValidationError``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from codegenie.plugins.sandbox_path import SandboxedPath
from codegenie.transforms import (
    AttemptSummary,
    Transform,
    TransformProvenance,
)
from codegenie.types.identifiers import (
    AttemptNumber,
    EventId,
    PluginId,
    RecipeId,
    SignalKind,
    TransformId,
    TransformKind,
)

_ULID_A: str = "01HXX00000000000000000000Z"


def _provenance() -> TransformProvenance:
    return TransformProvenance(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version="1.0.0",
        recipe_id=RecipeId("npm-lockfile-pin"),
        recipe_version="1.0.0",
        transform_kind=TransformKind("lockfile_pin"),
        applied_at=datetime.now(UTC),
        capability_use_id=EventId(_ULID_A),
    )


def test_transform_files_changed_accepts_sandboxed_path(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()

    class FakeTransform(Transform):
        transform_id: TransformId = TransformId("a" * 64)
        diff_bytes: bytes = b""
        files_changed: tuple[SandboxedPath, ...] = (sp,)
        provenance: TransformProvenance = _provenance()

    t = FakeTransform()
    assert t.files_changed == (sp,)
    assert isinstance(t.files_changed[0], SandboxedPath)


def test_attempt_summary_evidence_paths_accepts_sandboxed_path(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    summary = AttemptSummary(
        attempt=AttemptNumber(1),
        failing_signals=(SignalKind("tests"),),
        prior_failure_summary="ok",
        evidence_paths=(sp,),
        transform_id=TransformId("a" * 64),
    )
    assert summary.evidence_paths == (sp,)
    assert isinstance(summary.evidence_paths[0], SandboxedPath)
