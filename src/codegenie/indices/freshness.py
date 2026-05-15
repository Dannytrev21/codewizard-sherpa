"""``IndexFreshness`` — typed honest-confidence answer for index probes.

The single Phase-2 consumer of this module is
``codegenie.report.confidence_section`` (lands in S8-01), which renders a
``CONTEXT_REPORT.md`` Confidence section by ``match``-ing every
``IndexFreshness`` value with ``assert_never``. The discriminated-union
shape — ``Fresh | Stale(reason: StaleReason)`` — is the typed surface that
the architecture's load-bearing "honest confidence" commitment
(``docs/production/design.md §2.3``) makes real.

The module is pure data: stdlib + Pydantic only. No registry, no decorator,
no I/O, no logger. The Open/Closed seam for **new index sources**
(``@register_index_freshness_check(index_name)``) lands in S1-02 at
``codegenie.indices.registry`` — it layers on top by import. The seam for
**new variants** (e.g., a fifth ``StaleReason``) is *intentionally
ADR-amendment-gated* per 02-ADR-0006 §Consequences: the ``assert_never``
arms in every consumer's ``match`` are the structural enforcement against
silent ``Union`` widening.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
  (02-ADR-0006) — module location, variant set, discriminator strings.
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md
  §"Component design" #2, §"Data model"`` — Pydantic shape.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` — sum-type +
  make-illegal-states-unrepresentable discipline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CommitsBehind(BaseModel):
    """Constructed by ``IndexHealthProbe`` (S4-01) when the last-indexed
    commit lags ``git rev-parse HEAD``. ``n`` is the count of commits the
    index is behind; ``last_indexed`` is the raw commit SHA string at the
    I/O boundary (not a newtype — commit SHAs are not kernel identifiers)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["commits_behind"] = "commits_behind"
    n: int
    last_indexed: str


class DigestMismatch(BaseModel):
    """Constructed when an index keyed by a content-addressable digest
    (e.g., a SCIP bundle whose `manifest.digest` no longer matches the
    repository's expected digest) is observed stale."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["digest_mismatch"] = "digest_mismatch"
    expected: str
    actual: str


class CoverageGap(BaseModel):
    """Constructed when the index covers fewer files than the repository
    contains (e.g., the indexer skipped a directory, or a recent file add
    isn't reflected). The pair lets the renderer report a coverage
    percentage without re-deriving it from cardinalities elsewhere."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["coverage_gap"] = "coverage_gap"
    files_indexed: int
    files_in_repo: int


class IndexerError(BaseModel):
    """Constructed when the upstream indexer is unavailable. ``message`` is
    a stable identifier — e.g., ``"strace_unavailable"``, ``"timeout"``,
    ``"upstream_X_unavailable"`` — not a free-form human string."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["indexer_error"] = "indexer_error"
    message: str


StaleReason = Annotated[
    CommitsBehind | DigestMismatch | CoverageGap | IndexerError,
    Field(discriminator="kind"),
]


class Fresh(BaseModel):
    """The index reflects the repository at the recorded ``indexed_at``
    timestamp. Producers MUST construct timezone-aware UTC datetimes; the
    type permits any ``datetime`` only because the smart-constructor
    discipline lives with the producer (``IndexHealthProbe``), not here."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["fresh"] = "fresh"
    indexed_at: datetime


class Stale(BaseModel):
    """The index does NOT reflect the repository. ``reason`` carries the
    typed *why*; every consumer must exhaustively ``match`` on it with
    ``assert_never`` in the default arm."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["stale"] = "stale"
    reason: StaleReason


IndexFreshness = Annotated[Fresh | Stale, Field(discriminator="kind")]
