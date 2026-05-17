"""Pydantic models for the Dockerfile parser output (S5-03).

Lives in a sibling module so the parser + probe in :mod:`dockerfile` can
stay under the AC-V12 per-module source-line budget (≤ 100 lines).

All models are ``frozen=True, extra="forbid"`` per Phase 2 model
discipline. The pure parser at :mod:`dockerfile` returns these shapes;
the probe renders them to a slice dict at the writer boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ArgDirective",
    "CopyDirective",
    "DirectiveLine",
    "EntrypointForm",
    "Healthcheck",
    "ParsedDockerfile",
    "ParserDirective",
    "RunCommand",
    "Stage",
]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


EntrypointForm = Literal["exec", "shell", "absent", "malformed"]


class DirectiveLine(_M):
    """One tokenized Dockerfile directive — ``(kind, payload)``."""

    kind: str
    payload: str


class RunCommand(_M):
    command: str
    stage_index: int


class CopyDirective(_M):
    raw: str
    from_stage: str | None = None
    from_stage_resolved: bool = True
    stage_index: int


class ArgDirective(_M):
    name: str
    default: str | None = None
    before_first_from: bool = False


class Healthcheck(_M):
    kind: Literal["none", "cmd"]
    options: dict[str, str] = Field(default_factory=dict)
    cmd: str | None = None


class ParserDirective(_M):
    name: str
    value: str


class Stage(_M):
    index: int
    base_image: str
    name: str | None = None
    inherits_from: str | None = None
    user: str | None = None
    workdir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    expose: list[str] = Field(default_factory=list)
    healthcheck: Healthcheck | None = None
    entrypoint_form: EntrypointForm = "absent"
    entrypoint_argv: list[str] = Field(default_factory=list)
    entrypoint_command: str | None = None
    cmd_form: EntrypointForm = "absent"
    cmd_argv: list[str] = Field(default_factory=list)
    cmd_command: str | None = None
    args: list[ArgDirective] = Field(default_factory=list)


class ParsedDockerfile(_M):
    path: str
    stages: list[Stage]
    run_commands: list[RunCommand]
    copy_directives: list[CopyDirective]
    parser_directive: ParserDirective | None = None
    global_args: list[ArgDirective] = Field(default_factory=list)
