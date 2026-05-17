"""Pydantic models + classifier sum-type for :mod:`~codegenie.probes.\
layer_c.cve` (S5-04).

Split from :mod:`cve` so the probe module stays under its 200-source-line
budget. ``extra="allow"`` on the tool-shape models is the DIP boundary
against grype's evolving JSON; the emitted slice schema is the strict
``additionalProperties: false`` side.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _GrypeFix(BaseModel):
    model_config = ConfigDict(extra="allow")
    state: str | None = None


class _GrypeVulnerability(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    severity: str = ""
    fix: _GrypeFix = Field(default_factory=_GrypeFix)


class _GrypeArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    version: str = ""
    type: str = ""


class _GrypeMatch(BaseModel):
    model_config = ConfigDict(extra="allow")
    vulnerability: _GrypeVulnerability = Field(default_factory=_GrypeVulnerability)
    artifact: _GrypeArtifact = Field(default_factory=_GrypeArtifact)


class GrypeJsonSchema(BaseModel):
    """Thin Pydantic model over the subset of grype JSON we consume."""

    model_config = ConfigDict(extra="allow")
    matches: list[_GrypeMatch] = Field(default_factory=list)


class _ToolMissing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["tool_missing"] = "tool_missing"


class _SbomArtifactMissing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["sbom_artifact_missing"] = "sbom_artifact_missing"
    expected_path: str


class _ProcessExited(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["process_exited"] = "process_exited"
    exit_code: int
    stdout: bytes
    stderr_tail: str


ScannerAttempt = Annotated[
    _ToolMissing | _SbomArtifactMissing | _ProcessExited,
    Field(discriminator="kind"),
]
"""Tagged-union input to :func:`~codegenie.probes.layer_c.cve.\
_classify_grype_outcome`. The ``_SbomArtifactMissing`` variant is
CveProbe-only — SbomProbe's classifier never sees it."""


__all__ = [
    "GrypeJsonSchema",
    "ScannerAttempt",
    "_ProcessExited",
    "_SbomArtifactMissing",
    "_ToolMissing",
]
