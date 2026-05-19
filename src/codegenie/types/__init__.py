"""``codegenie.types`` — kernel-tier domain identifier surface.

Per production ADR-0033 and phase-3 ADR-0010, identifiers crossing module
boundaries are typed ``NewType``s, not raw :class:`str`. This package is the
single declaration point for the Phase-2 + Phase-3 newtype catalog (22 names)
plus the re-exported :data:`PackageManager` ``Literal`` from Phase 1
ADR-0013.

The 14 Phase-3 additions land alongside :class:`~codegenie.types.errors.ParseError`
and the smart-constructor functions in :mod:`codegenie.types.parsers`.
"""

from codegenie.types.identifiers import (
    AttemptNumber,
    BlobDigest,
    BranchName,
    BundleCacheKey,
    ConventionId,
    CveId,
    DockerStageName,
    Ecosystem,
    ErrorId,
    EventId,
    ImageDigest,
    ImageRef,
    IndexId,
    IndexName,
    Language,
    LayerDigest,
    PackageId,
    PackageManager,
    PackageName,
    PluginId,
    PrimitiveName,
    ProbeId,
    ProvenanceAdapterId,
    RecipeId,
    RegistryUrl,
    RuntimeId,
    SemverVersion,
    SignalKind,
    SkillId,
    TaskClassId,
    TransformId,
    TransformKind,
    WorkflowId,
)

__all__ = [
    "AttemptNumber",
    "BlobDigest",
    "BranchName",
    "BundleCacheKey",
    "ConventionId",
    "CveId",
    "DockerStageName",
    "Ecosystem",
    "ErrorId",
    "EventId",
    "ImageDigest",
    "ImageRef",
    "IndexId",
    "IndexName",
    "Language",
    "LayerDigest",
    "PackageId",
    "PackageManager",
    "PackageName",
    "PluginId",
    "PrimitiveName",
    "ProbeId",
    "ProvenanceAdapterId",
    "RecipeId",
    "RegistryUrl",
    "RuntimeId",
    "SemverVersion",
    "SignalKind",
    "SkillId",
    "TaskClassId",
    "TransformId",
    "TransformKind",
    "WorkflowId",
]
