"""Per-probe resource budget contract (S3-05 / Gap 3 — ADR-0007 + ADR-0009).

S1-07 (ADR-0002) extends :class:`BudgetingContext` with two additive
``None``-defaulted fields, ``parsed_manifest`` and ``input_snapshot``,
that mirror the S1-06 :class:`codegenie.probes.base.ProbeContext`
contract-type extension. The runtime ctx every probe receives via
``probe.run(snap, ctx)`` is still :class:`BudgetingContext`; mirroring
the field set closes the structural gap so probes reading
``ctx.parsed_manifest`` do not hit ``AttributeError`` at runtime.

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

S1-09 (ADR-0008 amendment) adds ``raw_artifact_truncate_mb: int = 5`` — the
soft on-disk truncation threshold. It is **distinct** from
``raw_artifact_mb``: the hard ceiling raises via
:meth:`BudgetingContext.report_bytes` (defends against runaway probes,
fires while the probe is still producing bytes), while the soft threshold
is enforced at writer-marshalling time by
:func:`codegenie.output.raw_truncation.apply_raw_artifact_truncation`,
which replaces over-budget payloads with a ``__truncated_at_budget__``
marker wrapper and emits ``probe.raw_artifact.truncated``. The two
companions enforce the invariant ``raw_artifact_truncate_mb <=
raw_artifact_mb`` at construction via :meth:`ResourceBudget.__post_init__`
(fail loud, Rule 12) — otherwise the soft policy would be unreachable
because the hard ceiling fires first.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegenie.errors import ProbeBudgetExceeded
from codegenie.output.paths import context_dir

_DEFAULT_LOGGER: Logger = logging.getLogger("codegenie.probe")

if TYPE_CHECKING:
    from codegenie.probes.base import InputFingerprint

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

    Defaults are pinned by S3-05 AC-20 and S1-09 AC-1:

    - ``rss_mb=200`` — RSS watermark for the advisory ``probe.rss.warn`` event.
    - ``raw_artifact_mb=10`` — cumulative artifact-write **hard** ceiling
      enforced by :meth:`BudgetingContext.report_bytes` (raises
      :exc:`ProbeBudgetExceeded`).
    - ``wall_clock_s=30`` — coordinator-side wall-clock window combined with
      ``probe.timeout_seconds`` via ``min(...)`` in the dispatch path.
    - ``raw_artifact_truncate_mb=5`` — **soft** on-disk truncation threshold
      enforced at writer-marshalling time by
      :func:`codegenie.output.raw_truncation.apply_raw_artifact_truncation`.
      Invariant: ``raw_artifact_truncate_mb <= raw_artifact_mb`` (checked by
      :meth:`__post_init__`); equality at the limit is allowed.
    """

    rss_mb: int = 200
    raw_artifact_mb: int = 10
    wall_clock_s: int = 30
    raw_artifact_truncate_mb: int = 5

    def __post_init__(self) -> None:
        if self.raw_artifact_truncate_mb > self.raw_artifact_mb:
            raise ValueError(
                f"raw_artifact_truncate_mb={self.raw_artifact_truncate_mb} "
                f"must be <= raw_artifact_mb={self.raw_artifact_mb}"
            )


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
    # S1-07 (ADR-0002) — additive ``None``-default fields mirroring the
    # S1-06 :class:`codegenie.probes.base.ProbeContext` extension.
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None
    input_snapshot: frozenset[InputFingerprint] | None = None
    # Structural parity with :class:`codegenie.probes.base.ProbeContext`
    # (ADR-0007 frozen contract). The contract says the runtime ctx is a
    # :class:`ProbeContext`; in practice the coordinator hands the probe a
    # :class:`BudgetingContext`. The five-attribute drift (``output_dir`` /
    # ``cache_dir`` / ``logger`` / ``config`` / ``image_digest_resolver``)
    # surfaced as ``scip_index``, ``tree_sitter_import_graph``, and ``slo``
    # silently ``AttributeError``-ing at runtime; the coordinator's
    # failure-isolation translated the crash into ``probe.failure`` with
    # empty ``schema_slice``. ``tests/fence/test_probe_context_conformance.py``
    # is the structural fence that catches this class of drift on every CI
    # run going forward.
    #
    # Defaults are wired so existing direct callers of
    # ``BudgetingContext(workspace=, raw_artifact_mb=)`` keep working
    # without modification: ``output_dir`` resolves to
    # ``workspace / .codegenie / context`` via :meth:`__post_init__`,
    # ``cache_dir`` to ``workspace / .codegenie / cache``, and the others
    # carry inert defaults that match a probe doing
    # ``ctx.config.get(...)`` or ``if ctx.image_digest_resolver is None``.
    output_dir: Path | None = None
    cache_dir: Path | None = None
    logger: Logger = field(default=_DEFAULT_LOGGER)
    config: dict[str, Any] = field(default_factory=dict)
    image_digest_resolver: Callable[[Path], str | None] | None = None

    def __post_init__(self) -> None:
        # ``ProbeContext.output_dir`` and ``ProbeContext.cache_dir`` are
        # non-Optional in the frozen spec; resolve the defaults so probes
        # can always do ``ctx.output_dir / X`` and ``ctx.cache_dir / X``
        # without an AttributeError. The on-disk layout matches the CLI
        # writer (``output.paths.context_dir``) and the CLI's
        # ``CacheStore`` construction at ``cli.py:536``.
        if self.output_dir is None:
            self.output_dir = context_dir(self.workspace)
        if self.cache_dir is None:
            self.cache_dir = self.workspace / ".codegenie" / "cache"

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
