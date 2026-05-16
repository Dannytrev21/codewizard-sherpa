"""``codegenie.skills`` — kernel-side ``SKILL.md`` loader (Phase 2 S2-01).

Public surface: :class:`Skill`, :class:`SkillsLoader`, :class:`LoadOutcome`,
:class:`FatalLoadError`, :class:`EvidenceQuery`, and the typed per-file
error union :data:`SkillsLoadError` (sum of :class:`SymlinkRefused`,
:class:`UnsafeYaml`, :class:`FrontmatterUnterminated`,
:class:`SchemaViolation`, :class:`IoFailure`).

02-ADR-0007 keeps Phase 2 kernel-only — no plugin loader yet. Phase 3+
``Skill`` consumers (the Planner) read this surface; the
:class:`SkillsIndexProbe` (S6-01) projects it into the gather artifact.
"""

from codegenie.skills.loader import (
    FatalLoadError,
    FrontmatterUnterminated,
    IoFailure,
    LoadOutcome,
    SchemaViolation,
    SkillsLoader,
    SkillsLoadError,
    SymlinkRefused,
    UnsafeYaml,
)
from codegenie.skills.model import TIERS, EvidenceQuery, Skill, Tier

__all__ = [
    "TIERS",
    "EvidenceQuery",
    "FatalLoadError",
    "FrontmatterUnterminated",
    "IoFailure",
    "LoadOutcome",
    "SchemaViolation",
    "Skill",
    "SkillsLoadError",
    "SkillsLoader",
    "SymlinkRefused",
    "Tier",
    "UnsafeYaml",
]
