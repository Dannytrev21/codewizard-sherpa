"""Per-probe resource budget contract (S3-05 / Gap 3 — ADR-0007 + ADR-0009).

This module exposes three names:

- :class:`ResourceBudget` — the frozen per-probe declared budget. Probes set
  ``declared_resource_budget = ResourceBudget(...)`` as a class attribute;
  probes that don't set one inherit :data:`DEFAULT_RESOURCE_BUDGET` via
  ``getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)`` in
  the coordinator. The default lives here (NOT on ``probes/base.py``'s
  :class:`Probe` ABC) because ADR-0007 freezes the contract surface; budgets
  are a coordinator-side concern.
- :class:`BudgetingContext` — the per-dispatch object the coordinator
  constructs and passes to a probe's ``run(snap, ctx)``. The contract is
  callback-based: a probe MUST call :meth:`BudgetingContext.report_bytes`
  before/after each artifact write. The ``workspace`` attribute remains a
  plain :class:`pathlib.Path` (ADR-0007 freezes ``ProbeContext.workspace:
  Path``). Phase 0's :class:`LanguageDetectionProbe` is metadata-only and
  never writes; the callback surface is reserved for Phase 1+ probes.
- :exc:`ProbeBudgetExceeded` — raised by ``report_bytes`` when cumulative
  ``bytes_written / (1024 * 1024) > raw_artifact_mb``. The coordinator
  catches it and lands the offending probe in ``Ran(errors=[...],
  confidence="low")``.

The boundary semantics are inclusive at the limit and exclusive above it:
writing exactly 1 MB against ``raw_artifact_mb=1`` does NOT raise; one byte
past it does. S3-05 AC-21 parametrizes ``[0.5, 1.0, 1.5]`` to pin both the
">" vs ">=" choice and the always-error mutant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codegenie.errors import ProbeBudgetExceeded

__all__ = [
    "DEFAULT_RESOURCE_BUDGET",
    "BudgetingContext",
    "ProbeBudgetExceeded",
    "ResourceBudget",
]


@dataclass(frozen=True)
class ResourceBudget:
    """Declared per-probe budget. Frozen so coordinator code can compare and
    reuse instances without defensive copies.

    Defaults are pinned by S3-05 AC-20:

    - ``rss_mb=200`` — RSS watermark for the advisory ``probe.rss.warn`` event.
    - ``raw_artifact_mb=10`` — cumulative artifact-write ceiling enforced by
      :meth:`BudgetingContext.report_bytes`.
    - ``wall_clock_s=30`` — coordinator-side wall-clock window combined with
      ``probe.timeout_seconds`` via ``min(...)`` in the dispatch path.
    """

    rss_mb: int = 200
    raw_artifact_mb: int = 10
    wall_clock_s: int = 30


DEFAULT_RESOURCE_BUDGET: ResourceBudget = ResourceBudget()


@dataclass
class BudgetingContext:
    """Per-dispatch context object carrying ``workspace`` and a write-budget
    callback.

    ``workspace`` stays a plain :class:`pathlib.Path` (ADR-0007 freeze on
    ``ProbeContext.workspace``); a probe writes its raw artifacts there and
    invokes :meth:`report_bytes` so the coordinator can enforce the
    per-probe ``raw_artifact_mb`` ceiling.
    """

    workspace: Path
    raw_artifact_mb: int
    bytes_written: int = field(default=0)

    def report_bytes(self, n: int) -> None:
        """Account ``n`` newly written bytes and raise if the budget is exceeded.

        The check is inclusive at the limit and exclusive above it: writing
        exactly ``raw_artifact_mb`` MB never raises; one byte past raises.
        """
        self.bytes_written += n
        if self.bytes_written / (1024 * 1024) > self.raw_artifact_mb:
            raise ProbeBudgetExceeded(
                f"raw_artifact_mb={self.raw_artifact_mb} exceeded "
                f"(bytes_written={self.bytes_written})"
            )
