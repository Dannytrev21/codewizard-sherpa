"""``OwnershipProbe`` — Layer E, light heaviness.

Parses ``CODEOWNERS`` from three GitHub-convention locations and emits a
typed :class:`OwnershipSlice`. The probe is honest about the absent-file
case (``confidence="low"`` — a Planner-actionable upstream-absent
observation, mirroring the ``CertificateProbe`` precedent at
``src/codegenie/probes/layer_c/certificate.py:67-81``).

Phase 2 search order intentionally diverges from GitHub: this
implementation prefers ``<repo>/CODEOWNERS`` over
``<repo>/.github/CODEOWNERS`` because the repo-root file is the most
visible to operators. An operator who wants ``.github/CODEOWNERS`` to
win simply deletes the root file. (AC-NEW-7.)

Functional core / imperative shell: :func:`_parse_codeowners_lines` is
the pure core — bytes-in, parsed-tuples-out, no filesystem access, never
raises. :meth:`OwnershipProbe.run` is the only impure code (filesystem
search + size cap + file read).

Sources:

- ``docs/localv2.md`` §5.5 E1.
- ``docs/phases/02-context-gather-layers-b-g/stories/S6-05-layer-e-probes.md``
  — the canonical AC ledger; Notes §1-§13 carry the design rationale.
- ``src/codegenie/probes/layer_c/certificate.py:67-81`` — upstream-absent
  precedent (absent expected file → ``confidence='low'``).
- ``src/codegenie/probes/layer_d/external_docs.py`` — sibling deferred-stub
  shape; *not* the model for this probe — ``OwnershipProbe`` is real.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["OwnershipEntry", "OwnershipProbe", "OwnershipSlice"]

_LOCATIONS: Final[tuple[str, ...]] = (
    "CODEOWNERS",
    ".github/CODEOWNERS",
    "docs/CODEOWNERS",
)
OWNERSHIP_MAX_BYTES: Final[int] = 1 * 1024 * 1024  # 1 MB
_PROBE_ID: Final[ProbeId] = ProbeId("ownership")


class OwnershipEntry(BaseModel):
    """One parsed CODEOWNERS line."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    pattern: str
    owners: tuple[str, ...]
    line_number: int


class OwnershipSlice(BaseModel):
    """Schema slice for :class:`OwnershipProbe`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    source_path: str | None
    entries: tuple[OwnershipEntry, ...]


def _parse_codeowners_lines(
    text: str,
) -> tuple[tuple[OwnershipEntry, ...], tuple[str, ...]]:
    """Pure CODEOWNERS line parser.

    1-indexed line numbers include blank/comment lines in the count
    (operators expect ``vim +N``-compatible line numbers).
    """
    entries: list[OwnershipEntry] = []
    errors: list[str] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        # AC-NEW-5: truncate at the first ``#``-prefixed token (inline comment).
        for i, tok in enumerate(tokens):
            if tok.startswith("#"):
                tokens = tokens[:i]
                break
        if not tokens:
            continue
        pattern = tokens[0]
        owners = tuple(tokens[1:])
        if not owners:
            errors.append(f"empty_owners_at_line_{idx}")
        entries.append(OwnershipEntry(pattern=pattern, owners=owners, line_number=idx))
    return tuple(entries), tuple(errors)


@register_probe(heaviness="light")
class OwnershipProbe(Probe):
    """Layer E — CODEOWNERS parser."""

    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["E"] = "E"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = list(_LOCATIONS)
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        found: list[Path] = [repo.root / loc for loc in _LOCATIONS if (repo.root / loc).exists()]
        if not found:
            return ProbeOutput(
                schema_slice=OwnershipSlice(source_path=None, entries=()).model_dump(mode="json"),
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[],
                errors=["codeowners_absent"],
            )

        primary = found[0]
        extra_errors: list[str] = [
            f"additional_codeowners_present_at:{p.relative_to(repo.root)}" for p in found[1:]
        ]

        size = os.path.getsize(primary)
        if size > OWNERSHIP_MAX_BYTES:
            return ProbeOutput(
                schema_slice=OwnershipSlice(
                    source_path=str(primary.relative_to(repo.root)),
                    entries=(),
                ).model_dump(mode="json"),
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=[],
                errors=[f"codeowners_size_cap_exceeded:{size}", *extra_errors],
            )

        text = primary.read_text()
        entries, parse_errors = _parse_codeowners_lines(text)
        return ProbeOutput(
            schema_slice=OwnershipSlice(
                source_path=str(primary.relative_to(repo.root)),
                entries=entries,
            ).model_dump(mode="json"),
            raw_artifacts=[],
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[*parse_errors, *extra_errors],
        )
