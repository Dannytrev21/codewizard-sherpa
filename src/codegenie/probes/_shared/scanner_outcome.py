"""``ScannerOutcome`` — typed result of running an external scanner once.

Consumed by **both** Layer C (``SyftProbe`` / ``GrypeProbe`` in S5-04) and
Layer G (``SemgrepProbe`` / ``GitleaksProbe`` in S6-06 / S6-07; coverage
mapping + freshness registry in S6-08). The location under ``_shared/`` is
load-bearing — duplicating the type per layer would re-introduce the
structural drift Phase 2 is rejecting.

Variant set (closed; extension is **ADR-amendment-gated** per
``02-ADR-0006 §Consequences``, NOT registry-by-addition):

- ``ScannerRan(findings: list[Finding])`` — scanner produced output.
- ``ScannerSkipped(reason: Literal[...])`` — tool missing / unhealthy /
  upstream slice unavailable.
- ``ScannerFailed(exit_code: int, stderr_tail: str)`` — non-zero exit /
  invalid-JSON stdout.

Producer/consumer ``assert_never`` ladder discipline (mirrors
``IndexFreshness`` ↔ ``confidence_section.py``):

- **Producer:** this module is the producer (zero probes consume it today;
  S5-04 / S6-06 / S6-07 / S6-08 are the consumers).
- **Consumers:** must ``match`` exhaustively on the top-level union AND
  on the inner ``Finding`` family if any. ``mypy --warn-unreachable``
  (repo-wide since Phase 0 S1-02; ``pyproject.toml`` line 154) enforces
  the discipline at every consumer's ``match`` site.

The ``stderr_tail`` cap (``STDERR_TAIL_CAP_BYTES = 4096``) is the
**per-outcome** cap; the writer (S3-03) caps the entire envelope at 64 MB.
Both bounds are honest-confidence guards — over-long stderr would balloon
the envelope's writer-side memory footprint without adding diagnostic value.

The validation-bypass pydantic ctor (a Pydantic API that constructs an
instance without running validators) is banned under this module by
``scripts/check_forbidden_patterns.py`` (S5-01 extension to S1-11's
ban); use ``Model(...)`` or ``Model.model_validate(...)`` so the smart-
constructor invariants are honored.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S5-01-scenario-scanner-outcome-types.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #5, §"Data model".
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
  — sum-type discipline this module rehearses.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §3 —
  make-illegal-states-unrepresentable.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codegenie.parsers import JSONValue

STDERR_TAIL_CAP_BYTES: Final[int] = 4096
"""Per-outcome stderr-tail cap (bytes). The writer (S3-03) caps the entire
envelope at 64 MB; this is the per-outcome cap a single ``ScannerFailed``
contributes before the writer composes."""


class Finding(BaseModel):
    """Minimal scanner-output placeholder.

    The full shape evolves with the consuming probes (S5-04 / S6-06 /
    S6-07): each scanner emits its own ``metadata`` payload (semgrep
    findings carry rule IDs + paths; gitleaks emits secret detections;
    grype emits CVE references). The base shape here is the smallest model
    that satisfies round-trip identity + nested-type preservation through
    ``ScannerRan.findings``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["finding"] = "finding"
    id: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    metadata: dict[str, JSONValue]


class ScannerRan(BaseModel):
    """The scanner executed; ``findings`` carries the typed payload (possibly
    empty)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["ran"] = "ran"
    findings: list[Finding] = Field(default_factory=list)


class ScannerSkipped(BaseModel):
    """The scanner did not execute; the typed ``reason`` is one of a closed
    set. Adding a 4th reason requires an ADR amendment to ``02-ADR-0006``
    (or a follow-up ADR) — NOT a ``metadata: dict`` escape hatch."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["skipped"] = "skipped"
    reason: Literal["tool_missing", "tool_unhealthy", "upstream_unavailable"]


class ScannerFailed(BaseModel):
    """The scanner executed but produced an error (non-zero exit or invalid
    JSON stdout). ``stderr_tail`` is capped at construction by a
    ``field_validator`` so the per-outcome envelope contribution is bounded
    regardless of upstream behavior.

    The optional ``reason`` field distinguishes structurally-different
    failure shapes inside the ``failed`` discriminator (e.g.
    ``"invalid_json"`` for malformed stdout, ``"sbom_artifact_missing"``
    for a CveProbe upstream-file gap). It defaults to ``None`` so the
    Phase-2 S5-01 baseline (``exit_code``/``stderr_tail`` only) remains
    valid; new variants are an additive extension, not a breaking
    rename.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["failed"] = "failed"
    exit_code: int
    stderr_tail: str
    reason: Literal["invalid_json", "sbom_artifact_missing"] | None = None

    @field_validator("stderr_tail")
    @classmethod
    def _cap_stderr_tail(cls, value: str) -> str:
        if len(value) > STDERR_TAIL_CAP_BYTES:
            return value[:STDERR_TAIL_CAP_BYTES]
        return value


ScannerOutcome = Annotated[
    ScannerRan | ScannerSkipped | ScannerFailed,
    Field(discriminator="kind"),
]


__all__ = [
    "STDERR_TAIL_CAP_BYTES",
    "Finding",
    "ScannerFailed",
    "ScannerOutcome",
    "ScannerRan",
    "ScannerSkipped",
]
