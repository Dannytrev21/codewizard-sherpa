"""``AdapterConfidence`` — typed honest-confidence answer for adapters.

Phase 3 plugin adapters (``DepGraphAdapter``, ``ImportGraphAdapter``,
``ScipAdapter``, ``TestInventoryAdapter``) construct one of three variants
to label how trustworthy their answer is:

- :class:`Trusted` — the underlying tool / index is fully available.
- :class:`Degraded` — the answer is partial (e.g., a slice is stale,
  a fall-back path was used); ``reason: str`` describes why.
- :class:`Unavailable` — the answer is not available at all; ``reason``
  describes the failure (tool missing, index empty, parser cap exceeded).

The discriminator strings (``"trusted"``, ``"degraded"``, ``"unavailable"``)
are a **cross-ADR / cross-phase contract** (02-ADR-0007 §Consequences).
Phase 3 plugin renderers, golden files and ``repo-context.yaml`` all read
the literal key ``"kind"``; a symmetric rename would round-trip cleanly
but break every external consumer.

Module purity invariant (S1-03 AC-15): this module imports only
``__future__``, ``typing`` and ``pydantic``. No I/O, no logger, no
sibling Phase-2 modules. The Open/Closed seam for **new variants** is
*intentionally ADR-amendment-gated* (mirror of S1-01's ``StaleReason``
discipline): the ``assert_never`` arm in every consumer's ``match`` is
the structural enforcement against silent ``Union`` widening.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md``
  (02-ADR-0007) — Phase 2 ships Protocols + ``AdapterConfidence``, never
  implementations.
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md
  §"Data model"`` — Pydantic shape.
- ``docs/production/adrs/0032-plugin-adapter-protocols.md`` (ADR-0032) —
  Phase 3 plugin source-tree placement for the real implementations.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Trusted(BaseModel):
    """The adapter's answer is fully trustworthy — no degradation, no
    fall-back. Carries the *absence* of a reason; ``extra="forbid"``
    rejects a ``reason`` field on construction (AC-11)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["trusted"] = "trusted"


class Degraded(BaseModel):
    """The adapter's answer is partial. ``reason`` is a short
    machine-readable token (e.g., ``"scip_unavailable"``,
    ``"index_stale"``); the Phase-3 renderer maps it to operator-facing
    copy."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["degraded"] = "degraded"
    reason: str


class Unavailable(BaseModel):
    """The adapter cannot answer at all. ``reason`` describes the
    failure (``"tool_missing"``, ``"parser_cap_exceeded"``, etc.)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unavailable"] = "unavailable"
    reason: str


AdapterConfidence = Annotated[
    Trusted | Degraded | Unavailable,
    Field(discriminator="kind"),
]
