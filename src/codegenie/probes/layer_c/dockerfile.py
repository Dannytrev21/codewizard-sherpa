"""S5-03 — :class:`DockerfileProbe` (Layer C marker probe).

Hand-rolled, line-by-line Dockerfile parser. No shell evaluation; no
``RUN`` execution; no ``${VAR}`` expansion. Captures literal directives
only — the supply-chain-safe shape Phase 3's distroless planner reads.

Models live in :mod:`._dockerfile_models` and the parser in
:mod:`._dockerfile_parse` so this module stays under the AC-V12
per-source-line budget. ``requires`` is metadata-only — the Phase 2
coordinator does not topo-sort by it (02-ADR-0003).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Final

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_c._dockerfile_parse import parse_dockerfile_text
from codegenie.probes.registry import register_probe

__all__ = ["DockerfileProbe", "find_dockerfiles"]

_FILE_GLOBS: Final[tuple[str, ...]] = (
    "Dockerfile",
    "Dockerfile.*",
    "Containerfile",
    "*.dockerfile",
)
_NESTED_NAMES: Final[tuple[str, ...]] = ("Dockerfile", "Containerfile")
_NESTED_RE: Final[re.Pattern[str]] = re.compile(r"^Dockerfile(?:\.[\w-]+)?$")


def find_dockerfiles(repo_root: Path) -> list[Path]:
    """Return every Dockerfile / Containerfile under *repo_root* (sorted)."""
    found: set[Path] = set()
    for glob in _FILE_GLOBS:
        for p in repo_root.rglob(glob):
            if p.is_file():
                found.add(p)
    for name in _NESTED_NAMES:
        for p in repo_root.rglob(name):
            if p.is_file():
                found.add(p)
    return sorted(found)


def _slice_for(parsed_dump: list[dict[str, Any]]) -> dict[str, Any]:
    return {"dockerfile": {"dockerfiles": parsed_dump, "confidence": "high"}}


@register_probe(heaviness="light")
class DockerfileProbe(Probe):
    """Layer C — Dockerfile marker probe (line-by-line parser, no shell eval).

    ``requires`` is metadata-only — see 02-ADR-0003.
    """

    name: str = "dockerfile"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = ["Dockerfile", "Containerfile", "**/Dockerfile*"]
    timeout_seconds: int = 10

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        files = find_dockerfiles(repo.root)
        if not files:
            return ProbeOutput(
                schema_slice={"dockerfile": {"dockerfiles": [], "confidence": "unavailable"}},
                raw_artifacts=[],
                confidence="low",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                warnings=["dockerfile.marker_absent"],
                errors=[],
            )
        parsed_dump: list[dict[str, Any]] = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            parsed = parse_dockerfile_text(text, path=str(path.relative_to(repo.root)))
            parsed_dump.append(parsed.model_dump(mode="json"))
        return ProbeOutput(
            schema_slice=_slice_for(parsed_dump),
            raw_artifacts=[],
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
