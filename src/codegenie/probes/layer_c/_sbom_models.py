"""Pydantic models + classifier sum-type for :mod:`~codegenie.probes.\
layer_c.sbom` (S5-04).

Split from :mod:`sbom` so the probe module stays under its 200-source-line
budget (story AC). The Pydantic models are the DIP boundary against
syft's evolving JSON shape — see :mod:`sbom` module docstring for the
``extra="allow"`` rationale.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _SyftLocation(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str = ""


class _SyftArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    version: str = ""
    type: str = ""
    locations: list[_SyftLocation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class _SyftSourceTarget(BaseModel):
    model_config = ConfigDict(extra="allow")
    imageSize: int | None = None  # noqa: N815 — name matches syft JSON key


class _SyftSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    target: _SyftSourceTarget = Field(default_factory=_SyftSourceTarget)


class SyftJsonSchema(BaseModel):
    """Thin Pydantic model over the subset of syft v1.x JSON we consume.

    ``extra="allow"`` is the forward-compat seam; the emitted slice
    schema is the strict (``additionalProperties: false``) side.
    """

    model_config = ConfigDict(extra="allow")
    artifacts: list[_SyftArtifact] = Field(default_factory=list)
    source: _SyftSource = Field(default_factory=_SyftSource)


class _ToolMissing(BaseModel):
    """Classifier input: ``syft`` not on PATH."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["tool_missing"] = "tool_missing"


class _ProcessExited(BaseModel):
    """Classifier input: ``syft`` ran (any exit code)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["process_exited"] = "process_exited"
    exit_code: int
    stdout: bytes
    stderr_tail: str


ScannerAttempt = Annotated[_ToolMissing | _ProcessExited, Field(discriminator="kind")]
"""Tagged-union input to :func:`~codegenie.probes.layer_c.sbom.\
_classify_syft_outcome`. Lifts the (tool-present × exit-code) decision
tree into a sum type so the classifier's ``match`` is exhaustively
checked by ``mypy --strict``."""


__all__ = [
    "ScannerAttempt",
    "SyftJsonSchema",
    "_ProcessExited",
    "_ToolMissing",
]
