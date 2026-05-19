"""Kernel-tier identifier ``NewType``s — production ADR-0033 + Phase-3 ADR-0010.

Production ADR-0033 §3 names primitive-obsession on domain identifiers as a
review-blocker pattern. Each ``NewType`` below is a nominal type under
``mypy --strict`` (passing an :data:`IndexId` where a :data:`SkillId` is
expected is a type error); at runtime each is identity-to-``str`` (zero
overhead, full ``str`` interop). ``AttemptNumber`` is the lone ``int``-backed
member of the catalog (Phase-3 retry counter).

``PackageManager`` is re-exported **by import** from its Phase 1 ADR-0013
owning module (:mod:`codegenie.probes.node_build_system`). This module never
redefines it — extension is by ADR amendment to Phase 1, not silent
duplication here.

The Phase-3 catalog (14 names) lands the kernel-tier types every Step-1+
story imports: plugin contract IDs, recipe + transform IDs, workflow / event
ULIDs, CVE IDs, package + branch + blob digest, registry URLs, and the
``SignalKind`` / ``PrimitiveName`` / ``TransformKind`` taxonomies the trust
scorer + recipe registry consume. Smart-constructor parsers live next door
at :mod:`codegenie.types.parsers`; ``ParseError`` lives at
:mod:`codegenie.types.errors`; the canonical ``Result`` sum type lives at
:mod:`codegenie.result` (Phase-2 S1-04 — never forked).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Literal, NewType

# DO NOT redefine — Phase 1 ADR-0013 owns this enum; this module re-exports
# it. The re-export is **lazy** via :func:`__getattr__` below: a top-level
# ``from codegenie.probes.node_build_system import PackageManager`` would
# fire ``probes/__init__.py`` (which eagerly loads ``layer_b/*`` probes
# whose modules also reach back into ``codegenie.types.identifiers``),
# forming a cycle the first time anything outside ``probes`` triggers this
# module (e.g., ``transforms.outcomes`` via ``adapters.confidence``). The
# TYPE_CHECKING import below keeps the static-typing contract intact
# (mypy --strict still sees ``PackageManager`` as a re-exported name).
if TYPE_CHECKING:  # pragma: no cover — type-checker-only re-export
    from codegenie.probes.node_build_system import (
        PackageManager as PackageManager,
    )

# --- Phase-2 catalog (5 + 3 amendments) -----------------------------------

IndexId = NewType("IndexId", str)
SkillId = NewType("SkillId", str)
TaskClassId = NewType("TaskClassId", str)
IndexName = NewType("IndexName", str)
# Probe identifier — landed alongside S1-04's TCCM model (which carries
# ``required_probes: list[ProbeId]``). Phase 0/1 did not ship a ProbeId
# newtype; S1-04 routes the kernel-tier addition through this module.
ProbeId = NewType("ProbeId", str)
# Programming-language identifier (S2-01). Phase 1 already detects languages
# as raw ``str`` (``RepoSnapshot.detected_languages``); S2-01 introduces the
# newtype so the kernel-side ``Skill.applies_to_languages`` is typed against
# accidental ``TaskClassId`` substitution (ADR-0033 §1 primitive-obsession).
Language = NewType("Language", str)
# Convention identifier — landed alongside S2-02's ``ConventionsCatalogLoader``.
ConventionId = NewType("ConventionId", str)

# --- Phase-3 catalog (14 new — S1-01) -------------------------------------

# Plugin contract IDs.
PluginId = NewType("PluginId", str)
RecipeId = NewType("RecipeId", str)
# BLAKE3-hex digest of a transform diff; arch §C4 (ADR-0010).
TransformId = NewType("TransformId", str)
# ULID — orchestrator workflow id; consumed by S1-04 ApplyContext + S6-04.
WorkflowId = NewType("WorkflowId", str)
# ULID — append-only event log entry id; S6-01 two-stream event log.
EventId = NewType("EventId", str)
# MITRE CVE ID; S5-04 lockfile recipes consume it as input.
CveId = NewType("CveId", str)
# npm ``<name>@<pinned-semver>`` package coordinate; S7-02 npm recipes.
PackageId = NewType("PackageId", str)
# Git branch name (lowercase, slash-allowed); S6-04 RemediationOrchestrator.
BranchName = NewType("BranchName", str)
# 64-char lowercase hex digest (algorithm-agnostic at the type level).
BlobDigest = NewType("BlobDigest", str)
# Strict-``https://`` ASCII registry URL; ADR-0001 RegistryAllowlist.
RegistryUrl = NewType("RegistryUrl", str)
# snake-case open-registry signal name; S6-02 trust scorer.
SignalKind = NewType("SignalKind", str)
# snake-case open-registry primitive name; S4-05 capabilities catalog.
PrimitiveName = NewType("PrimitiveName", str)
# snake-case open-registry transform kind; S5-01 recipe registry.
TransformKind = NewType("TransformKind", str)
# Bounded retry counter (1..1024); S1-04 AttemptSummary.attempt.
AttemptNumber = NewType("AttemptNumber", int)
# Dotted snake-case error identifier (``^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$``,
# Phase-1 ADR-0007 warning/error-ID format). Carried by ``RecipeError`` and
# ``RemediationError`` on the ``Failed`` variants in S1-03's outcomes module.
ErrorId = NewType("ErrorId", str)

# --- Phase-3 catalog (S3-02 additive — VulnIndex) -------------------------

# Bare npm package name (scoped or unscoped, no ``@<version>``); S3-02
# VulnIndex lookup key. S1-01's ``PackageId`` (``<name>@<pinned-semver>``)
# does not fit per-name-across-versions vuln semantics — this newtype is the
# additive companion to ``PackageId`` at the kernel-tier identifier home.
PackageName = NewType("PackageName", str)

# Closed-set ecosystem tag — Phase-3 ships ``npm``; the remaining four are
# admitted by ADR amendment when their plugin scaffold lands (mirrors the
# ``severity`` / ``source`` Literal-discipline on ``VulnerabilityRecord``).
Ecosystem = Literal["npm", "pypi", "maven", "rubygems", "gomod"]


__all__ = [
    "AttemptNumber",
    "BlobDigest",
    "BranchName",
    "ConventionId",
    "CveId",
    "Ecosystem",
    "ErrorId",
    "EventId",
    "IndexId",
    "IndexName",
    "Language",
    "PackageId",
    "PackageManager",
    "PackageName",
    "PluginId",
    "PrimitiveName",
    "ProbeId",
    "RecipeId",
    "RegistryUrl",
    "SignalKind",
    "SkillId",
    "TaskClassId",
    "TransformId",
    "TransformKind",
    "WorkflowId",
]


# AC-15 — machine-verifiable docstring registry. Every public name in
# ``__all__`` maps to a one-line docstring naming ADR-0010 and (for Phase-3
# additions) the consuming story / arch component. The test in
# ``tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all``
# fences this against drift.
_NEWTYPE_REGISTRY: Final[Mapping[str, str]] = {
    # Phase-2 carryover (ADR-0033 § primitive-obsession).
    "IndexId": "Phase-2 index id (ADR-0010 lineage; ADR-0033).",
    "SkillId": "Phase-2 skill id (ADR-0010 lineage; ADR-0033).",
    "TaskClassId": "Phase-2 task-class id (ADR-0010 lineage; ADR-0033).",
    "IndexName": "Phase-2 index name (ADR-0010 lineage; ADR-0033).",
    "ProbeId": "Phase-2 probe id (ADR-0010 lineage; ADR-0033).",
    "Language": "Phase-2 programming-language id (ADR-0010 lineage; ADR-0033).",
    "ConventionId": "Phase-2 convention id (ADR-0010 lineage; ADR-0033).",
    "PackageManager": "Phase-1 package-manager Literal re-export (ADR-0013; ADR-0010 §catalogue).",
    # Phase-3 (S1-01).
    "PluginId": "Phase-3 plugin id (ADR-0010); S2-01 PluginRegistry key.",
    "RecipeId": "Phase-3 recipe id (ADR-0010); S5-01 RecipeRegistry key.",
    "TransformId": "Phase-3 transform id (ADR-0010); arch §C4 BLAKE3 diff digest.",
    "WorkflowId": "Phase-3 workflow ULID (ADR-0010); arch §C5 ApplyContext.",
    "EventId": "Phase-3 event ULID (ADR-0010); S6-01 two-stream event log.",
    "CveId": "Phase-3 MITRE CVE id (ADR-0010); S5-04 lockfile recipe input.",
    "PackageId": "Phase-3 npm coordinate (ADR-0010); S7-02 npm recipes.",
    "BranchName": "Phase-3 branch name (ADR-0010); S6-04 orchestrator branch.",
    "BlobDigest": "Phase-3 64-hex blob digest (ADR-0010); arch §C4 cache key.",
    "RegistryUrl": "Phase-3 strict-https registry URL (ADR-0010); ADR-0001 allowlist.",
    "SignalKind": "Phase-3 trust signal kind (ADR-0010); S6-02 scorer registry.",
    "PrimitiveName": "Phase-3 sandbox primitive (ADR-0010); S4-05 capabilities.",
    "TransformKind": "Phase-3 transform kind (ADR-0010); S5-01 recipe registry.",
    "AttemptNumber": "Phase-3 retry counter (ADR-0010); S1-04 AttemptSummary.",
    "ErrorId": "Phase-3 dotted snake-case error id (ADR-0010); S1-03 RecipeError/RemediationError.",
    # Phase-3 (S3-02 — VulnIndex additive).
    "PackageName": (
        "Phase-3 bare npm package name (ADR-0010, ADR-0033); S3-02 VulnIndex lookup key."
    ),
    "Ecosystem": (
        "Phase-3 closed-set ecosystem tag (ADR-0010); S3-02 VulnIndex.lookup ecosystem filter."
    ),
}


def __getattr__(name: str) -> object:
    """Lazy re-export of :data:`PackageManager` from
    :mod:`codegenie.probes.node_build_system`.

    Resolved on first attribute access (after the ``probes`` package
    finishes initialising) so the kernel-tier ``types.identifiers`` module
    can be imported by ``transforms.outcomes`` / ``adapters.confidence``
    without forming the ``types ↔ probes`` cycle (see the TYPE_CHECKING
    import block at the top of this file). All other names in
    :data:`__all__` are bound at module load — only ``PackageManager`` is
    resolved lazily.
    """

    if name == "PackageManager":
        from codegenie.probes.node_build_system import PackageManager

        return PackageManager
    raise AttributeError(f"module 'codegenie.types.identifiers' has no attribute {name!r}")
