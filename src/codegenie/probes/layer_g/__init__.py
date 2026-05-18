"""``codegenie.probes.layer_g`` — Layer G scanners (S6-06, S6-07, S6-08).

Each scanner is a separate sibling module. There is NO shared
``ScannerRunner`` base class — final-design §"Design patterns applied"
row 7 forbids it (SRP + Rule of Three; each scanner has a genuinely-
different I/O shape and semgrep/ripgrep have per-scanner exit-code
carve-outs).

The shared types live at the **kernel** level:

- :data:`~codegenie.probes._shared.scanner_outcome.ScannerOutcome` —
  the typed sum across all scanners (S5-01).
- :func:`~codegenie.exec.run_external_cli` — the only subprocess door
  (S1-07).

Helper-level sharing (a future ``_shared/scanner_common`` module for the
``_ToolMissing`` / ``_ProcessTimedOut`` / ``_ProcessExited`` tagged-union
dataclasses + ``_stderr_tail`` + ``_envelope``) is admitted by the same
row 7 — but only when the rule-of-three trigger fires (when S6-07's
``gitleaks.py`` lands, three of four scanners will duplicate verbatim).
Per-scanner classifiers and ``Finding`` models stay per-scanner: they
encode the carve-outs and the rich shapes.
"""

from codegenie.probes.layer_g import (
    ast_grep,
    ripgrep_curated,
    semgrep,
)

__all__ = ["ast_grep", "ripgrep_curated", "semgrep"]
