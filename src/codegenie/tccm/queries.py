"""Five ``DerivedQuery`` variants — graph-aware context primitives.

Translates production ADR-0030's five primitive names into the phase-arch
literal set ratified by ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
§"Data model" line 721:

- ``consumers_of`` — downstream packages depending on ``pkg``.
- ``producers_of`` — upstream packages ``pkg`` depends on (phase-arch
  substitution for ADR-0030's ``transitive_callers``; reconciliation is
  recorded in S1-04's References as an open architectural note).
- ``reverse_lookup`` — files that import ``module``.
- ``refs_to`` — call/use sites for ``symbol``.
- ``tests_exercising`` — tests that exercise ``symbol``.

Sixth variant requires an ADR amendment. No ``Unknown`` fallback (production
ADR-0030 §Consequences): unknown ``compute:`` values are loader errors, not
data-model variants.

Module purity invariant (AC-18 mirrors S1-03 AC-15): imports only
``__future__``, ``typing``, ``pydantic``. No I/O, no logger, no sibling
Phase-2 modules. AST source-scan tests enforce.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Data
  model" line 721 — the literal five-tuple this module implements.
- ``docs/production/adrs/0030-graph-aware-context-queries.md`` — graph-aware
  derived queries; ADR-amendment is the only legal door for a sixth variant.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConsumersOf(BaseModel):
    """Downstream packages depending on ``pkg`` (dep-graph downstream)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["consumers_of"] = "consumers_of"
    pkg: str


class ProducersOf(BaseModel):
    """Upstream packages ``pkg`` depends on (dep-graph upstream).

    Phase-arch substitution for ADR-0030's ``transitive_callers`` primitive;
    reconciliation between phase-arch and ADR-0030 is recorded as an open
    architectural note and is out of S1-04's scope.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["producers_of"] = "producers_of"
    pkg: str


class ReverseLookup(BaseModel):
    """Files that import ``module`` (import-graph reverse lookup)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["reverse_lookup"] = "reverse_lookup"
    module: str


class RefsTo(BaseModel):
    """Call/use sites for ``symbol`` (SCIP refs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["refs_to"] = "refs_to"
    symbol: str


class TestsExercising(BaseModel):
    """Tests that exercise ``symbol`` (test-inventory coverage)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["tests_exercising"] = "tests_exercising"
    symbol: str


DerivedQuery = Annotated[
    ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising,
    Field(discriminator="compute"),
]
