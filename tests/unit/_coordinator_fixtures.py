"""Test fakes for S3-05 coordinator unit tests.

The real Phase 0 ``LanguageDetectionProbe`` ships in S4-01; coordinator tests
in this phase use the :class:`FakeProbe` fake so the coordinator surface can
be validated independently of probe authoring.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from typing import Any

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task

__all__ = ["FakeProbe", "make_probe_context", "make_snapshot", "make_task"]


def make_snapshot(tmp_path: Path, **overrides: Any) -> RepoSnapshot:
    defaults: dict[str, Any] = dict(
        root=tmp_path.resolve(),
        git_commit=None,
        detected_languages={},
        config={},
    )
    defaults.update(overrides)
    return RepoSnapshot(**defaults)


def make_task() -> Task:
    return Task(type="__bullet_tracer__", options={})


@dataclass
class FakeProbe(Probe):
    """Configurable probe for coordinator tests. NOT @register_probe-d."""

    name: str = "fake"
    version: str = "0.1.0"
    layer: str = "A"
    tier: str = "task_specific"  # set to "base" for prelude probes
    applies_to_tasks: list[str] = field(default_factory=lambda: ["*"])
    applies_to_languages: list[str] = field(default_factory=lambda: ["*"])
    requires: list[str] = field(default_factory=list)
    declared_inputs: list[str] = field(default_factory=list)
    timeout_seconds: int = 5
    cache_strategy: str = "none"

    # Test hooks
    _run: Callable[[RepoSnapshot, ProbeContext], Awaitable[ProbeOutput]] | None = None
    _applies: bool = True
    _seen_snapshots: list[RepoSnapshot] = field(default_factory=list)

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return self._applies

    def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
        return f"sha256:{self.name}"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        self._seen_snapshots.append(repo)
        if self._run is None:
            return ProbeOutput(
                schema_slice={self.name: True},
                raw_artifacts=[],
                confidence="high",
                duration_ms=1,
                warnings=[],
                errors=[],
            )
        return await self._run(repo, ctx)


def make_probe_context(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=getLogger("test"),
        config={},
    )


async def _maybe_await(coro_or_value: Any) -> Any:  # noqa: ARG001 — reserved
    if asyncio.iscoroutine(coro_or_value):
        return await coro_or_value
    return coro_or_value
