"""``codegenie.probes.layer_b`` — Layer B (structural / index-health) probes.

This package is the Open/Closed seam for Phase 2 Layer-B probes. Each new
probe is a new module + a one-line explicit import in
``codegenie.probes.__init__``; the kernel-tier registry collects them via
``@register_probe`` at module import time.

Phase 2 starts with one probe: :class:`index_health.IndexHealthProbe` (B2,
S4-01) — the load-bearing index-freshness citizen. Subsequent stories
(S4-03 ``SCIPProbe``, S4-04 ``TreeSitterImportGraphProbe``, etc.) land
beside it.
"""

# NOTE: ``index_health`` is imported by ``codegenie.probes.__init__`` (the
# explicit-import probe registry collection point). Re-exporting it here
# would re-introduce a circular import with ``codegenie.indices.registry``
# (which itself imports ``codegenie.types.identifiers``, which transitively
# imports ``codegenie.probes.node_build_system`` and so triggers
# ``codegenie.probes.__init__``). Keep this package marker empty.

__all__: list[str] = []
