"""``codegenie.probes._shared`` — typed surfaces shared across probe layers.

This package houses pure-data types consumed by **two or more probe layers**.
Putting them under ``layer_c/`` or ``layer_g/`` would force the other layer
to reach across a sibling boundary and re-introduce the structural drift
Phase 2 is rejecting.

For Phase 2 the only public module is :mod:`scanner_outcome` — the
``ScannerOutcome`` discriminated-union sum consumed by Layer C
(``SyftProbe`` / ``GrypeProbe`` in S5-04) and by Layer G
(``SemgrepProbe`` / ``GitleaksProbe`` in S6-06 / S6-07 / S6-08).

See the S5-01 story
(``docs/phases/02-context-gather-layers-b-g/stories/S5-01-scenario-scanner-outcome-types.md``)
for the architectural rationale and 02-ADR-0006
(``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``)
for the sum-type discipline this module rehearses.
"""

from codegenie.probes._shared.scanner_outcome import (
    STDERR_TAIL_CAP_BYTES,
    Finding,
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)

__all__ = [
    "STDERR_TAIL_CAP_BYTES",
    "Finding",
    "ScannerFailed",
    "ScannerOutcome",
    "ScannerRan",
    "ScannerSkipped",
]
