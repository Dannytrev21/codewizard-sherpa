"""``AdapterConfidence`` — re-export of the canonical declaration.

Phase 2 keeps :data:`AdapterConfidence` and its three variants
(:class:`Trusted`, :class:`Degraded`, :class:`Unavailable`) as part of its
typed surface (02-ADR-0007); the **canonical class declarations live in**
:mod:`codegenie.transforms.outcomes` (Phase-3 S1-03). This module
re-exports the same class objects so that both layers see identity-equal
types — ADR-0010 Amendment 2026-05-18 records the de-duplication.

Phase 3 plugin adapters (``DepGraphAdapter``, ``ImportGraphAdapter``,
``ScipAdapter``, ``TestInventoryAdapter``) construct one of three
variants to label how trustworthy their answer is:

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

Module purity invariant (S1-03 AC-15 + adapters AC-15): this module
imports only from :mod:`codegenie.transforms.outcomes` (the canonical
home). It does not reach into ``codegenie.{parsers,probes,exec,coordinator,output}``
— fenced by ``tests/unit/adapters/test_protocols.py::test_adapter_modules_are_pure_typing``.
The Open/Closed seam for new variants is ADR-amendment-gated (the
``assert_never`` arm in every consumer's ``match`` is the structural
enforcement against silent ``Union`` widening).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md``
  (02-ADR-0007) — Phase 2 ships Protocols + ``AdapterConfidence``, never
  implementations.
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md
  §"Data model"`` — Pydantic shape.
- ``docs/phases/03-vuln-deterministic-recipe/ADRs/`` —
  ``0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md``
  §Amendments (2026-05-18) — canonical home + ``reason: str`` discipline.
- ``docs/production/adrs/0032-plugin-adapter-protocols.md`` (ADR-0032) —
  Phase 3 plugin source-tree placement for the real implementations.
"""

from __future__ import annotations

from codegenie.transforms.outcomes import (
    AdapterConfidence,
    Degraded,
    Trusted,
    Unavailable,
)

__all__ = [
    "AdapterConfidence",
    "Degraded",
    "Trusted",
    "Unavailable",
]
