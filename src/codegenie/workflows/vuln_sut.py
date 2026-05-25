"""Phase 6 S1-01 — ``VulnRemediationSut`` Protocol + the four ADR-0001 models.

This module is the public-surface declaration site for the four harness-facing
names committed by Phase 6 ADR-0001:

* :class:`VulnRemediationCase` — the case the harness hands to the SUT.
* :class:`VulnRemediationResult` — what comes back. Sanitization is enforced
  by construction (Pydantic field validators), not by convention.
* :data:`SutDigest` — a kernel-tier ``NewType("SutDigest", str)`` constructed
  via :func:`codegenie.types.parsers.parse_sut_digest`.
* :class:`VulnRemediationSut` — the ``@runtime_checkable`` Protocol the
  Phase 6.5 bench harness imports.

The concrete LangGraph builder lands in Phase-6 S3-01; the concrete adapter
in Phase-6 S5-01; Phase-9 contributes ``TemporalVulnRemediationSut``. None of
those edit this module — they implement the Protocol from outside.

The pure helper :func:`_compute_sut_digest_input` is the byte-stable digest
substrate Phase-9 S4-05 G5 conformance later asserts byte-identical across
Local + Temporal SUTs (functional-core/imperative-shell discipline). The
helper takes no env, clock, or filesystem; AC-7 enforces this with an AST
fence over any future ``digest()`` implementation that lands in this module.

Anti-refactor (story §"Anti-refactor"): no ``SutRegistry``, no ``BaseSut``
ABC, no ``EvidenceRef`` smart-constructor extraction beyond what AC-5 wants.
The rule-of-three threshold for that registry ships in Phase 9 + Phase 6.5
when there are three concrete SUTs — not before.
"""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

from codegenie.coordinator.validator import SECRET_FIELD_ALLOWLIST, SECRET_FIELD_PATTERN
from codegenie.hashing import content_hash_bytes
from codegenie.output.sanitizer import _PATTERNS as _CANONICAL_SECRET_PATTERNS
from codegenie.types.identifiers import (
    AttemptNumber,
    BlobDigest,
    CassetteId,
    CveId,
    ErrorId,
    RepoFixtureRef,
    SutDigest,
    TokenCount,
    VulnCaseId,
)
from codegenie.workflows._frozen import _FROZEN_FORBID

__all__ = [
    "SutDigest",
    "VulnRemediationCase",
    "VulnRemediationResult",
    "VulnRemediationSut",
]


# ---------------------------------------------------------------------------
# Closed Literal taxonomies (membership pinned by tests AC-3 + AC-4).
# ---------------------------------------------------------------------------

ExecutionMode = Literal["dry_run", "apply", "replay"]
"""Closed set of execution modes. Adding a fourth is an ADR-0001 amendment."""

TerminalState = Literal["completed", "awaiting_human_review", "failed_unrecoverable"]
"""The three terminal ledger states. The four non-terminal states
(``needs_plan``, ``plan_ready``, ``patch_applied``, ``gate_failed_retryable``)
MUST NOT appear here — they belong inside the ledger sum type (S1-02), not
the public Result. Adding a terminal state is an ADR-0001 amendment."""

GateLastOutcome = Literal["pass", "fail_retryable", "fail_terminal", "not_run"]
"""Closed set of summarised gate outcomes the harness reads."""

# Phase-1 ADR-0007 error-id format: ``^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$``.
_ERROR_ID_RX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

# Canonical cleartext-secret regexes — imported by identity from the Phase-2
# sanitizer so an upstream regex tweak propagates automatically. Forking
# them here would silently drift the contract (Phase-9 critique-report
# pattern; see story Notes-for-implementer).
_CLEARTEXT_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    pat for _, pat in _CANONICAL_SECRET_PATTERNS
)


# ---------------------------------------------------------------------------
# Sub-models for the Result payload (all frozen + extra="forbid").
# ---------------------------------------------------------------------------


class GateSummary(BaseModel):
    """Summarised Phase-5 gate outcome the harness consumes.

    *Not* the full gate transcript — that lives in the per-run artifact
    directory referenced by ``VulnRemediationResult.evidence_references``.
    """

    model_config = _FROZEN_FORBID
    attempts: AttemptNumber
    last_outcome: GateLastOutcome


class CostSummary(BaseModel):
    """Token + cassette-replay accounting summary.

    No provider names, no model slugs — those would couple the harness to
    Phase-4 internals; the bench scorecard reports token cost per case, not
    per model.
    """

    model_config = _FROZEN_FORBID
    tokens_in: TokenCount
    tokens_out: TokenCount
    cassette_replays: int

    @field_validator("cassette_replays")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("CostSummary.cassette_replays: must be non-negative")
        return v


class EvidenceRef(BaseModel):
    """A relative-path reference into the per-run artifact directory.

    Rejects at construction (AC-5):

    * Absolute paths (POSIX ``/...``, Windows drive ``C:\\...``).
    * ``..`` components anywhere in the path.
    * Null bytes (``\\x00``) and C0/DEL control chars.
    * Secret-shaped substrings — the canonical
      :data:`codegenie.coordinator.validator.SECRET_FIELD_PATTERN` matched as
      a *substring* (so ``foo /etc/passwd`` and ``GITHUB_TOKEN=ghp_...``
      both die before they reach the harness).
    * Cleartext secrets matching any of the Phase-2 sanitizer's
      ``_PATTERNS`` (AWS / GitHub / JWT / RSA / npm / Anthropic).
    """

    model_config = _FROZEN_FORBID
    ref: str

    @field_validator("ref")
    @classmethod
    def _enforce_safe_ref(cls, v: str) -> str:
        # Empty refs are not actionable.
        if not v:
            raise ValueError("EvidenceRef: ref must be non-empty")
        # Absolute paths (POSIX + Windows drive letter).
        if v.startswith("/"):
            raise ValueError(f"EvidenceRef: absolute path rejected (got {v!r})")
        if len(v) >= 2 and v[1] == ":" and v[0].isalpha():
            raise ValueError(f"EvidenceRef: Windows drive-letter path rejected (got {v!r})")
        # ``..`` components.
        if ".." in v.split("/") or ".." in v.split("\\"):
            raise ValueError(f"EvidenceRef: '..' path component rejected (got {v!r})")
        # Null + control chars (C0 + DEL).
        for ch in v:
            cp = ord(ch)
            if cp < 0x20 or cp == 0x7F:
                raise ValueError(f"EvidenceRef: control character U+{cp:04X} rejected in ref {v!r}")
        # Secret-name substring rejection — defense in depth against
        # "GITHUB_TOKEN=...". Allowlist mirrors the coordinator's discipline.
        if v not in SECRET_FIELD_ALLOWLIST and SECRET_FIELD_PATTERN.search(v):
            raise ValueError(
                f"EvidenceRef: secret-shaped substring rejected (got {v!r}). "
                f"Refs must be paths into the per-run artifact directory, never "
                f"credential names."
            )
        # Cleartext secret pattern rejection — same regex set as the Phase-2
        # sanitizer (imported by identity so an upstream tweak propagates).
        for pat in _CLEARTEXT_SECRET_PATTERNS:
            if pat.search(v):
                raise ValueError(
                    f"EvidenceRef: cleartext secret pattern matched in ref {v!r}; "
                    f"the SUT must not surface plaintext credentials to the harness."
                )
        return v


# ---------------------------------------------------------------------------
# VulnRemediationCase — the harness's input to the SUT.
# ---------------------------------------------------------------------------


class VulnRemediationCase(BaseModel):
    """Frozen Pydantic model — the bench harness hands one of these per case."""

    model_config = _FROZEN_FORBID

    case_id: VulnCaseId
    repo_fixture: RepoFixtureRef
    cve: CveId
    cassette_id: CassetteId
    execution_mode: ExecutionMode


# ---------------------------------------------------------------------------
# VulnRemediationResult — what the SUT returns.
# ---------------------------------------------------------------------------


class VulnRemediationResult(BaseModel):
    """Frozen Pydantic model — sanitization-enforcing harness output."""

    model_config = _FROZEN_FORBID

    case_id: VulnCaseId
    terminal_state: TerminalState
    patch_digest: BlobDigest | None
    gate_summary: GateSummary
    failure_modes: tuple[Annotated[ErrorId, Field()], ...]
    cost_summary: CostSummary
    evidence_references: tuple[EvidenceRef, ...]
    sut_digest: SutDigest

    @field_validator("failure_modes")
    @classmethod
    def _enforce_error_id_format(cls, v: tuple[ErrorId, ...]) -> tuple[ErrorId, ...]:
        for entry in v:
            if not isinstance(entry, str) or not _ERROR_ID_RX.fullmatch(entry):
                raise ValueError(
                    f"VulnRemediationResult.failure_modes: {entry!r} does not match "
                    f"Phase-1 ADR-0007 error-id format ``^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$``"
                )
        return v

    @model_validator(mode="after")
    def _terminal_state_invariants(self) -> VulnRemediationResult:
        completed = self.terminal_state == "completed"
        if completed and self.patch_digest is None:
            raise ValueError(
                "VulnRemediationResult: terminal_state='completed' requires a non-None patch_digest"
            )
        if not completed and self.patch_digest is not None:
            raise ValueError(
                f"VulnRemediationResult: terminal_state={self.terminal_state!r} requires "
                f"patch_digest=None (patch_digest is meaningful only on 'completed')"
            )
        if completed and self.failure_modes:
            raise ValueError(
                "VulnRemediationResult: terminal_state='completed' requires "
                "an empty failure_modes tuple"
            )
        return self


# ---------------------------------------------------------------------------
# VulnRemediationSut — the @runtime_checkable Protocol the harness imports.
# ---------------------------------------------------------------------------


@runtime_checkable
class VulnRemediationSut(Protocol):
    """The four-method-set frozen by ADR-0001. Two methods, no more.

    ``run_case`` is async (the concrete subgraph awaits Phase-4 LLM + Phase-5
    sandbox calls). ``digest`` is sync (a pure summary of the SUT's stable
    behaviour — Phase-9 S4-05 G5 byte-equality across Local/Temporal SUTs
    later depends on this purity, enforced by the AC-7 AST fence on any
    concrete ``digest()`` implementation under ``codegenie.workflows``).
    """

    async def run_case(self, request: VulnRemediationCase) -> VulnRemediationResult: ...

    def digest(self) -> SutDigest: ...


# ---------------------------------------------------------------------------
# Pure digest substrate — functional core, no I/O. Phase-9 S4-05 G5 substrate.
# ---------------------------------------------------------------------------


def _compute_sut_digest_input(case: VulnRemediationCase) -> SutDigest:
    """Return the byte-stable :data:`SutDigest` for ``case`` — purely functional.

    Serialises the case via ``model_dump_json()`` (sorted keys; Pydantic v2
    default), encodes to UTF-8, and feeds the bytes to ``content_hash_bytes``
    which returns ``"blake3:<64 lowercase hex>"`` — the canonical
    :data:`SutDigest` grammar.

    Determinism + sensitivity properties: AC-7. No clock, no env, no
    filesystem, no network — enforced by the AC-7 AST walk over any future
    ``digest()`` implementation in this package.
    """
    payload = case.model_dump_json().encode("utf-8")
    return SutDigest(content_hash_bytes(payload))
