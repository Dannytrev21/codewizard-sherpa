"""Data model for ``codegenie.skills`` — Phase 2 S2-01.

Defines the typed surface :class:`SkillsLoader` returns: :class:`Skill`
(frozen Pydantic record), :class:`EvidenceQuery` (the typed two-axis query
that replaces a flat ``set[str]``), and the tier-ordering constants
(:data:`Tier`, :data:`TIERS`).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #9, §"Data model" — :class:`Skill` shape,
  progressive-disclosure invariant, three-tier merge order.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §1, §3 —
  newtype identifiers (``SkillId``, ``TaskClassId``, ``Language``);
  ``Tier`` as ``Literal`` not ``int``-keyed lookup.
- ``CLAUDE.md`` §"Conventions to follow when writing the POC" —
  ``["*"]`` is the documented wildcard sentinel for
  ``applies_to_tasks`` / ``applies_to_languages``.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from codegenie.types.identifiers import Language, SkillId, TaskClassId

__all__ = [
    "TIERS",
    "EvidenceQuery",
    "Skill",
    "Tier",
]


# Three-tier search order is load-bearing: user wins over repo wins over
# org-shared. A hostile ``~/.codegenie/skills-org/`` cannot override a
# user-trusted skill because the user tier is iterated first and
# first-tier-wins. ADR-amend-gated — adding a fourth tier requires editing
# ``Tier`` + :data:`TIERS` + ``SkillsLoader.default()`` together.
Tier: TypeAlias = Literal["user", "repo", "org"]
TIERS: Final[tuple[Tier, ...]] = ("user", "repo", "org")


class Skill(BaseModel):
    """A loaded ``SKILL.md`` record — frozen, progressive-disclosure shape.

    The markdown ``body`` is **not** an attribute: only the byte offset,
    size, and BLAKE3 fingerprint are recorded. Bodies are read lazily by
    Phase 4+ planners through a separate code path so the gather artifact
    stays index-only (CLAUDE.md §"Progressive disclosure for context").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: SkillId
    applies_to_tasks: list[TaskClassId]
    applies_to_languages: list[Language]
    body_offset: Annotated[int, Field(ge=0)]
    body_size: Annotated[int, Field(ge=0)]
    body_blake3: Annotated[str, Field(pattern=r"^blake3:[0-9a-f]{64}$")]


class EvidenceQuery(BaseModel):
    """Typed two-axis query for :meth:`SkillsLoader.find_applicable`.

    ``task is None`` means "no task constraint" (only wildcard-task skills
    can match the task component); a non-``None`` ``task`` requires either
    the wildcard sentinel ``"*"`` or an exact match. ``languages`` is a
    set so callers can express "any of these languages" without ordering
    artifacts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskClassId | None
    languages: set[Language]
