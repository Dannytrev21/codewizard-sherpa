"""Phase 2 kernel-tier identifier ``NewType``s (production ADR-0033).

Production ADR-0033 §3 names primitive-obsession on domain identifiers as a
review-blocker pattern. Each ``NewType`` below is a nominal type under
``mypy --strict`` (passing an :data:`IndexId` where a :data:`SkillId` is
expected is a type error); at runtime each is identity-to-``str`` (zero
overhead, full ``str`` interop).

``PackageManager`` is re-exported **by import** from its Phase 1 ADR-0013
owning module (:mod:`codegenie.probes.node_build_system`). This module never
redefines it — extension is by ADR amendment to Phase 1, not silent
duplication here.
"""

from __future__ import annotations

from typing import NewType

# DO NOT redefine — Phase 1 ADR-0013 owns this enum; this is a re-export.
from codegenie.probes.node_build_system import PackageManager as PackageManager

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
# Convention identifier — landed alongside S2-02's ``ConventionsCatalogLoader``
# (which carries ``ConventionRule*.id: ConventionId`` and propagates the
# id into every ``Pass`` / ``Fail`` / ``NotApplicable`` result). Five Phase-2+
# consumers (loader.py, model.py, catalog.py, the future Layer-D
# ``ConventionsProbe``, Layer-E stubs) import from this canonical home;
# AST source-scans under ``src/codegenie/conventions/`` forbid local
# ``NewType("ConventionId", ...)`` redefinition (S2-02 AC-1a / B2).
ConventionId = NewType("ConventionId", str)

__all__ = [
    "ConventionId",
    "IndexId",
    "IndexName",
    "Language",
    "PackageManager",
    "ProbeId",
    "SkillId",
    "TaskClassId",
]
