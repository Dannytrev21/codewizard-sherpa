"""Phase-3 ``ApplyContext`` + ``AttemptSummary`` — S1-04 contract surface.

These models carry the per-workflow / per-attempt context the recipe engine
and orchestrator pass around. Phase 3 itself does not populate
``prior_attempts``; Phase 5's ADR-P5-002 retry envelope is what folds
``AttemptSummary`` instances into ``ctx.prior_attempts`` via the
``ctx.model_copy(update={"prior_attempts": ctx.prior_attempts + (new,)})``
immutable-update idiom. Shipping ``prior_attempts`` *now* — already shaped
as a ``tuple[AttemptSummary, ...]`` — means Phase 5 amends *behavior*, not
the contract shape (ADR-0001 §Decision C, ADR-0001 §Tradeoffs row 1).

Container choice — ``tuple`` not ``list`` — is load-bearing: Pydantic v2
``frozen=True`` freezes attribute *reassignment*, not in-place container
mutation, so ``ctx.prior_attempts.append(x)`` on a list silently succeeds.
Tuples are truly immutable; the V-D-F2 closure on the original story draft.

``prior_failure_summary`` enforces a UTF-8-**bytes** cap (8 KB), not a
character count — a 4-byte emoji should not slip 4× the budget through a
``len(s)`` check. NUL / C0-control / bidi-control bytes are rejected per
ADR-0010 / E20 (adversarial repo content); ``\t \n \r`` are admitted.

ADRs: ADR-0001 (Phase-5 contract surface), ADR-0010 (smart-constructor
discipline), ADR-0011 (SandboxedPath / Capability framing).
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

from codegenie.transforms._forward import CapabilityBundle, SandboxedPath
from codegenie.types.identifiers import (
    AttemptNumber,
    SignalKind,
    TransformId,
    WorkflowId,
)

__all__ = ["ApplyContext", "AttemptSummary"]


# ---------------------------------------------------------------------------
# prior_failure_summary boundary constants
# ---------------------------------------------------------------------------

_SUMMARY_UTF8_BYTES_CAP: Final[int] = 8192

# Forbidden C0 controls (ADR-0010 / E20). Admitted: ``\t`` (\x09), ``\n``
# (\x0a), ``\r`` (\x0d). Rejected: \x00..\x08, \x0b..\x0c, \x0e..\x1f.
_FORBIDDEN_C0: Final[frozenset[str]] = frozenset(
    {chr(c) for c in range(0x00, 0x09)}
    | {chr(0x0B), chr(0x0C)}
    | {chr(c) for c in range(0x0E, 0x20)}
)

# Bidi controls (U+202A..U+202E, U+2066..U+2069) — Trojan-Source class
# (CVE-2021-42574).
_FORBIDDEN_BIDI: Final[frozenset[str]] = frozenset(
    {chr(c) for c in range(0x202A, 0x202F)} | {chr(c) for c in range(0x2066, 0x206A)}
)

_FORBIDDEN_CONTROL_CHARS: Final[frozenset[str]] = _FORBIDDEN_C0 | _FORBIDDEN_BIDI


# ---------------------------------------------------------------------------
# ``AttemptSummary`` — one row per remediation attempt; Phase 5 retry-envelope
# uses these as the historical record the orchestrator reads at retry time.
# ---------------------------------------------------------------------------


class AttemptSummary(BaseModel):
    """One row in :attr:`ApplyContext.prior_attempts`.

    ``transform_id`` is ``None`` when the failure occurred *before* a
    transform was produced (e.g., recipe-match failure, sandbox setup
    failure). Phase 5 distinguishes these via the discriminator-on-``None``
    pattern in its retry classifier.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt: AttemptNumber
    failing_signals: tuple[SignalKind, ...]
    prior_failure_summary: str
    evidence_paths: tuple[SandboxedPath, ...]
    transform_id: TransformId | None

    @field_validator("failing_signals", "evidence_paths", mode="before")
    @classmethod
    def _coerce_sequence_to_tuple(cls, v: object) -> object:
        """YAML / JSON arrays decode to ``list``; coerce so the stored
        container is the truly-immutable tuple shape (V-D-F2 closure)."""
        if isinstance(v, list):
            return tuple(v)
        return v

    @field_validator("prior_failure_summary")
    @classmethod
    def _summary_bounds(cls, v: str) -> str:
        # UTF-8 *bytes* cap — len(s) would let through up to 4× the budget
        # with 4-byte chars (emoji, CJK). Phase 5's canary check assumes
        # this byte cap.
        encoded = v.encode("utf-8")
        if len(encoded) > _SUMMARY_UTF8_BYTES_CAP:
            raise ValueError(
                f"prior_failure_summary exceeds {_SUMMARY_UTF8_BYTES_CAP}-byte "
                f"UTF-8 cap; got {len(encoded)} bytes"
            )
        # E20 adversarial-content closure — reject NUL, C0 controls (except
        # \t \n \r), and bidi controls.
        bad = {ch for ch in v if ch in _FORBIDDEN_CONTROL_CHARS}
        if bad:
            raise ValueError(
                "prior_failure_summary contains forbidden control / bidi "
                f"characters: {sorted(ord(c) for c in bad)}"
            )
        return v


# ---------------------------------------------------------------------------
# ``ApplyContext`` — workflow-scoped state the recipe engine sees.
# ---------------------------------------------------------------------------


class ApplyContext(BaseModel):
    """Per-workflow context passed to every recipe-engine ``apply()`` call.

    ``prior_attempts`` is **truly immutable** (``tuple[AttemptSummary, ...]``)
    so ``frozen=True``'s reassignment-only freeze isn't quietly bypassed by
    ``ctx.prior_attempts.append(x)``. Phase 5's retry envelope grows the
    field via ``ctx.model_copy(update={"prior_attempts": ctx.prior_attempts +
    (new,)})``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: WorkflowId
    attempt: AttemptNumber = AttemptNumber(1)
    prior_attempts: tuple[AttemptSummary, ...] = ()
    capabilities: CapabilityBundle

    @field_validator("prior_attempts", mode="before")
    @classmethod
    def _coerce_prior_attempts_to_tuple(cls, v: object) -> object:
        if isinstance(v, list):
            return tuple(v)
        return v
