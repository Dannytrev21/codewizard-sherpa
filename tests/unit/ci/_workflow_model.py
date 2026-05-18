"""Typed Pydantic models for parsing ``.github/workflows/*.yml`` (S8-03).

Every CI workflow test in this story loads the workflow through these
models instead of grep / string-matching the raw YAML. Two benefits:

1. Malformed YAML or a missing required field fails the parse step
   immediately with a Pydantic error pointing at the offending key, rather
   than a downstream ``KeyError`` in an opaque assertion.
2. Field access is type-checked by mypy — ``job.steps[0].run`` cannot be
   silently confused with ``job.steps[0].uses``.

Only the surface needed by this story is modeled. ``actions/setup-python``
inputs etc. land under ``Step.with_`` as ``dict[str, Any]`` — we never
introspect them. This is the "thin typed shell" that the workflow YAML
tests in :mod:`tests.unit.ci.test_workflow_yaml` consume; it deliberately
does not try to mirror GitHub Actions' full surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Step(BaseModel):
    """One step in a job. ``run`` and ``uses`` are mutually exclusive."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str | None = None
    run: str | None = None
    uses: str | None = None
    with_: dict[str, Any] | None = Field(default=None, alias="with")
    env: dict[str, str] | None = None
    if_: str | None = Field(default=None, alias="if")
    continue_on_error: bool | None = Field(default=None, alias="continue-on-error")
    timeout_minutes: int | None = Field(default=None, alias="timeout-minutes")


class Strategy(BaseModel):
    model_config = ConfigDict(extra="allow")

    matrix: dict[str, Any] | None = None
    fail_fast: bool | None = Field(default=None, alias="fail-fast")


class Job(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str | None = None
    runs_on: Any = Field(default=None, alias="runs-on")
    timeout_minutes: int | None = Field(default=None, alias="timeout-minutes")
    strategy: Strategy | None = None
    steps: list[Step] = Field(default_factory=list)
    env: dict[str, str] | None = None
    permissions: dict[str, str] | None = None
    needs: list[str] | str | None = None
    if_: str | None = Field(default=None, alias="if")
    continue_on_error: bool | None = Field(default=None, alias="continue-on-error")


class WorkflowFile(BaseModel):
    """A parsed ``.github/workflows/*.yml`` document.

    ``on`` is intentionally accessed as the raw mapping because PyYAML coerces
    the bare YAML key ``on`` to Python ``True`` (YAML 1.1 boolean-key surface);
    callers reach for it via ``WorkflowFile.triggers``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str | None = None
    jobs: dict[str, Job]
    permissions: dict[str, str] | None = None
    concurrency: dict[str, Any] | None = None
    triggers: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path) -> WorkflowFile:
        """Parse the given workflow path. Raises ``ValueError`` on missing file."""
        if not path.exists():
            raise ValueError(f"workflow file not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"workflow YAML root is not a mapping: {path}")
        # PyYAML 1.1 boolean-key surface: bare `on` becomes Python True.
        triggers_raw: Any = raw.get(True, raw.get("on"))
        if triggers_raw is None:
            triggers_raw = {}
        elif isinstance(triggers_raw, list):
            triggers_raw = {k: None for k in triggers_raw}
        raw["triggers"] = triggers_raw
        # Strip the original ``on`` keys so they don't trip ``extra="allow"``
        # validation paths twice.
        raw.pop(True, None)
        raw.pop("on", None)
        return cls.model_validate(raw)

    def step_run_strings(self) -> list[tuple[str, str, str]]:
        """Yield ``(job_name, step_name_or_index, run_string)`` for every run step.

        Used by metamorphic / regex-scan tests. ``step_name_or_index`` is the
        step's ``name`` when present, otherwise its 0-based index in the job.
        """
        out: list[tuple[str, str, str]] = []
        for job_name, job in self.jobs.items():
            for idx, step in enumerate(job.steps):
                if step.run is not None:
                    label = step.name if step.name else f"#{idx}"
                    out.append((job_name, label, step.run))
        return out
