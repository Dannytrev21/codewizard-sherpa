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

__all__ = [
    "IndexId",
    "IndexName",
    "PackageManager",
    "SkillId",
    "TaskClassId",
]
