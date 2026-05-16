"""``codegenie.types`` — kernel-tier domain identifier surface (Phase 2 S1-05).

Per production ADR-0033, identifiers crossing module boundaries are typed
``NewType``s, not raw :class:`str`. This package is the single declaration
point for the four Phase 2 newtypes (:data:`IndexId`, :data:`SkillId`,
:data:`TaskClassId`, :data:`IndexName`) plus the re-exported
:data:`PackageManager` ``Literal`` from Phase 1 ADR-0013.
"""

from codegenie.types.identifiers import (
    IndexId,
    IndexName,
    Language,
    PackageManager,
    SkillId,
    TaskClassId,
)

__all__ = [
    "IndexId",
    "IndexName",
    "Language",
    "PackageManager",
    "SkillId",
    "TaskClassId",
]
