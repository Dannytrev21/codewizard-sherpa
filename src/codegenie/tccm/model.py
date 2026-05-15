"""``TCCM`` Pydantic model — Task-Class Context Manifest schema.

Pure-typing module: no I/O, no logger, no sibling Phase-2 imports beyond
``codegenie.adapters`` (for :data:`AdapterConfidence`) and
``codegenie.types.identifiers`` (for the kernel newtypes). AST source-scan
tests (AC-18) enforce the allowlist.

The five fields match ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
§"Data model" exactly. ``schema_version: Literal["1"]`` is the upgrade door —
a future TCCM v2 would widen the Literal and the loader would dispatch
internally; do not preemptively introduce ``TCCMSchemaV1`` / ``V2`` classes.

Empty / duplicate collection decisions (AC-24):

- ``derived_queries: []`` is accepted (Phase 8 Bundle Builder handles).
- ``required_probes: []`` / ``required_skills: []`` are each accepted.
- ``required_probes: [a, a]`` is accepted at the schema layer; deduplication
  is a Phase 8 Bundle Builder concern.

These are deliberate acceptance decisions — failing loud belongs at the
*consumer* boundary, not the schema (Rule 12 preserved where it matters).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Data
  model" — exact field set.
- ``docs/production/adrs/0029-task-class-context-manifests.md`` — manifest
  purpose.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` — newtypes for
  identifiers; ``frozen=True`` + ``extra="forbid"`` for value objects.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from codegenie.adapters import AdapterConfidence
from codegenie.tccm.queries import DerivedQuery
from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId


class TCCM(BaseModel):
    """Task-Class Context Manifest — typed declaration of evidence needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["1"]
    task_class: TaskClassId
    required_probes: list[ProbeId]
    required_skills: list[SkillId]
    derived_queries: list[DerivedQuery]
    confidence_floor: AdapterConfidence
