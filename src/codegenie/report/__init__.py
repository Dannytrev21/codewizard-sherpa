"""``codegenie.report`` — human-readable companion artifacts.

Phase 2 ships exactly one renderer here: the **Confidence section** of
``CONTEXT_REPORT.md``, produced by :mod:`codegenie.report.confidence_section`.
That renderer is the only Phase-2 consumer of
:class:`codegenie.indices.freshness.IndexFreshness` — its exhaustive
``match`` + ``typing.assert_never`` is the type-level enforcement of the
"silent staleness is the worst failure mode" commitment
(``docs/production/design.md §2.3``).

The package is intentionally outside ``codegenie.probes/**`` so importing
the renderer never pulls in the probe registry — Phase 3's adapters and
Phase 8's bundle builder can compose this surface without circular
dependencies. The structural guarantee is exercised by
``tests/unit/report/test_confidence_section.py::test_no_probe_registry_import``.

References:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #2 §"Why not co-located".
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §3–4.
"""

from codegenie.report.confidence_section import (
    ConfidenceSectionRenderer,
    render_confidence_section,
)

__all__ = [
    "ConfidenceSectionRenderer",
    "render_confidence_section",
]
