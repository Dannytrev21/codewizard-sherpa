"""Phase 4 S1-02 — ``PlanProposal`` closed Pydantic v2 discriminated union.

The LLM emits exactly one of four named shapes — ``dep_bump``, ``override``,
``callsite_rewrite``, ``refuse`` — validated at the Anthropic SDK boundary via
``response_format=TypeAdapter(PlanProposal).json_schema()`` before bytes ever
reach Python. The discriminated union is the type-level firewall: an injected
LLM cannot structurally emit a shell command, an ``rm -rf``, or unfenced
markdown.

Two Pydantic-validated newtypes live alongside the variants:

* ``UnifiedDiff`` — ``Annotated[str, AfterValidator(_validate_unified_diff)]``
  enforces a 64 KB byte cap (ADR-0001 + synthesis-ledger 32 KB → 64 KB upgrade
  for headline major-bump fixtures), rejects binary/CRLF/empty/no-op/new-file
  diffs. The cross-field path-escape check (``diff paths ⊆ files``) is a
  ``@model_validator(mode="after")`` on ``PlanProposalCallsiteRewrite``.
* ``SandboxedRelativePath`` — ``Annotated[str, AfterValidator(...)]`` rejects
  empty, absolute, ``..``-traversing, NUL-byte, or backslash-bearing strings.
  Distinct from the Phase-3 ``codegenie.plugins.sandbox_path.SandboxedPath``
  jail-minted *absolute capability* — that type is unsuitable as an
  LLM-emitted JSON string at the SDK boundary.

Neither is a bare ``NewType`` because a validator must fire on every Pydantic
construction; the LLM emits both as raw JSON strings.

Sources:
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md``
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0004-plan-outcome-wraps-recipe-outcome.md``
- ``docs/production/adrs/0033-domain-modeling-discipline.md``
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from codegenie.types.identifiers import PackageId, SemverVersion

_MAX_DIFF_BYTES: Final[int] = 65_536
"""ADR-0001 + synthesis-ledger upgrade: the 32 KB cap was raised to 64 KB
after evidence the headline ``express-cve-2026-1234`` major-bump fixture
regularly produces ≥ 40 KB diffs. Boundary is strict ``>``: ``65_536`` is
accepted, ``65_537`` is rejected."""

_MAX_RATIONALE_CHARS: Final[int] = 2048
"""Rationale is audit-log-only (ADR-0001 §Consequences); the cap bounds the
worst-case audit-record growth and forces an LLM to be concise. Not a token
count — characters."""

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
"""Single-source the variant config: frozen instances + strict extra-key
rejection. Every ``PlanProposal*`` BaseModel references this constant (F15)."""


# --- UnifiedDiff smart constructor ---------------------------------------


def _validate_unified_diff(value: str) -> str:
    """Pure validator for the ``UnifiedDiff`` newtype.

    Each rejection raises with a *distinctive, stable* error keyword so the
    sad-path tests can prove a diff was rejected for the right reason (F9).
    """
    if value == "":
        raise ValueError("empty diff is not a valid UnifiedDiff")
    if "\r" in value:
        raise ValueError("CRLF / carriage return in diff is rejected; use LF line endings only")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as e:
        raise ValueError("binary or non-UTF-8 content in diff is rejected") from e
    if len(encoded) > _MAX_DIFF_BYTES:
        raise ValueError(
            f"diff size {len(encoded)} bytes exceeds 64 KB cap ({_MAX_DIFF_BYTES} bytes)"
        )
    if "--- /dev/null" in value:
        raise ValueError(
            "new file diffs (--- /dev/null marker) are not allowed for "
            "callsite_rewrite; modify existing files only"
        )
    data_line_count = 0
    for line in value.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            data_line_count += 1
    if data_line_count == 0:
        raise ValueError(
            "no-op diff (zero +/- data lines after the header) is not allowed; "
            "emit a 'refuse' proposal instead"
        )
    return value


UnifiedDiff = Annotated[str, AfterValidator(_validate_unified_diff)]
"""A unified-diff string that survives the smart constructor.

Capped at 64 KB; UTF-8 only; LF line endings; no ``/dev/null`` new-file
markers; at least one ``+``/``-`` data line. The cross-field path-escape
check lives on ``PlanProposalCallsiteRewrite`` because it needs ``files``.
"""


# --- SandboxedRelativePath smart constructor (AC-12) ----------------------


def _validate_sandboxed_relative_path(value: str) -> str:
    """Pure validator for the ``SandboxedRelativePath`` newtype.

    Rejects every LLM-emittable path that could escape the sandbox or smuggle
    a separator past a naive parser (F1, F6).
    """
    if value == "":
        raise ValueError("empty path is not a valid SandboxedRelativePath")
    if value.startswith("/"):
        raise ValueError(
            f"absolute path {value!r} is not a valid SandboxedRelativePath; "
            "paths must be repo-relative"
        )
    if "\x00" in value:
        raise ValueError("NUL byte in path is rejected (potential path-truncation smuggle)")
    if "\\" in value:
        raise ValueError(
            "backslash in path is rejected; Windows separators are not accepted, "
            "use forward slashes"
        )
    segments = value.split("/")
    if any(segment == ".." for segment in segments):
        raise ValueError(
            f"path {value!r} contains '..' traversal segment; "
            "SandboxedRelativePath rejects path-escape sequences"
        )
    return value


SandboxedRelativePath = Annotated[str, AfterValidator(_validate_sandboxed_relative_path)]
"""A repository-relative path the LLM may emit as a JSON string.

Rejects empty, absolute, ``..``-traversing, NUL-byte, and backslash-bearing
strings. Distinct from the Phase-3
``codegenie.plugins.sandbox_path.SandboxedPath`` jail-minted absolute
capability — that type cannot survive a JSON round-trip from an LLM and is
not appropriate at the SDK boundary."""


# --- Path-escape cross-field validator ------------------------------------


def _extract_diff_paths(diff: str) -> set[str]:
    """Pure helper — every ``--- a/<path>`` and ``+++ b/<path>`` path in a diff.

    Strips the ``a/``/``b/`` prefix conventional in ``git diff`` output. Lines
    that do not carry a prefix-stripped path are skipped silently — the
    ``UnifiedDiff`` validator already enforced the structural shape.
    """
    paths: set[str] = set()
    for line in diff.splitlines():
        for marker in ("--- a/", "+++ b/"):
            if line.startswith(marker):
                paths.add(line[len(marker) :])
                break
    return paths


# --- The four variants ----------------------------------------------------


class PlanProposalDepBump(BaseModel):
    """LLM emits this when the fix is a manifest-only version bump.

    The recipe layer (Phase 3) consumes ``(manifest_path, package,
    target_version)`` directly — no diff, no callsite touched. ADR-0001."""

    model_config = _FROZEN_FORBID
    kind: Literal["dep_bump"] = "dep_bump"
    manifest_path: SandboxedRelativePath
    package: PackageId
    target_version: SemverVersion
    rationale: Annotated[str, Field(max_length=_MAX_RATIONALE_CHARS)]


class PlanProposalOverride(BaseModel):
    """LLM emits this when a transitive dependency must be forced via an
    ecosystem override (``overrides`` / ``resolutions`` block).

    Distinct from ``dep_bump``: ``override`` injects a new entry in the
    manifest's override block rather than mutating a direct dependency.
    ADR-0001."""

    model_config = _FROZEN_FORBID
    kind: Literal["override"] = "override"
    manifest_path: SandboxedRelativePath
    package: PackageId
    forced_version: SemverVersion
    rationale: Annotated[str, Field(max_length=_MAX_RATIONALE_CHARS)]


class PlanProposalCallsiteRewrite(BaseModel):
    """LLM emits this when the fix needs a source-file edit (e.g., adapting
    a callsite to a breaking API).

    ``files`` is the LLM-declared allow-list of paths the diff may touch;
    every diff path must be a subset of ``files`` (arch §Data model line 734:
    ``diff paths ⊆ files`` — subset, *not* equality). ``files`` MAY legitimately
    list more than the diff touches. ADR-0001."""

    model_config = _FROZEN_FORBID
    kind: Literal["callsite_rewrite"] = "callsite_rewrite"
    manifest_path: SandboxedRelativePath
    files: Annotated[list[SandboxedRelativePath], Field(min_length=1)]
    diff: UnifiedDiff
    rationale: Annotated[str, Field(max_length=_MAX_RATIONALE_CHARS)]

    @model_validator(mode="after")
    def _diff_paths_subset_of_files(self) -> Self:
        """Cross-field check — every path in ``diff`` must appear in ``files``.

        Arch §Data model line 734 specifies subset (``⊆``), not equality —
        ``files`` MAY legitimately list more than the diff touches."""
        diff_paths = _extract_diff_paths(self.diff)
        declared = set(self.files)
        escapees = diff_paths - declared
        if escapees:
            raise ValueError(
                f"diff path escape: {sorted(escapees)!r} appear in diff but "
                f"not in declared files {sorted(declared)!r}"
            )
        return self


class PlanProposalRefuse(BaseModel):
    """LLM emits this when no safe fix is available.

    ``reason`` is a closed three-member ``Literal`` (Rule 2: three similar
    members beat premature abstraction; promote to ``StrEnum`` only if
    multi-site branching emerges — F16). ADR-0001."""

    model_config = _FROZEN_FORBID
    kind: Literal["refuse"] = "refuse"
    reason: Literal["out_of_scope", "insufficient_context", "policy_block"]
    rationale: Annotated[str, Field(max_length=_MAX_RATIONALE_CHARS)]


# --- The closed discriminated union ---------------------------------------

PlanProposal = Annotated[
    PlanProposalDepBump | PlanProposalOverride | PlanProposalCallsiteRewrite | PlanProposalRefuse,
    Field(discriminator="kind"),
]
"""The four shapes the LLM may emit, discriminated on ``kind``.

Pass ``TypeAdapter(PlanProposal).json_schema()`` to the Anthropic SDK as
``response_format`` (wiring lands in S3-02). Every consumer ``match``-es with
``assert_never`` in the default arm — mypy ``--strict`` is the only place
exhaustiveness is enforced.

The discriminator idiom is the codebase-wide convention (``Field(discriminator=
"kind")`` — 7+ shipped unions; Rule 11 mandates conformance)."""
