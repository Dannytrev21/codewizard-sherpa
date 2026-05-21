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

import json
import re
import time
from pathlib import Path
from typing import Any, Final

from codegenie.output.paths import raw_dir
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


_SLICE_FILENAME: Final[str] = "dockerfile.json"


def _write_files(repo_root: Path, schema_slice: dict[str, Any]) -> list[Path]:
    """Persist the dockerfile slice to ``raw/dockerfile.json``.

    The ``entrypoint`` and ``shell_usage`` marker probes consume this
    sidecar via :func:`~codegenie.probes.layer_b.index_health.read_raw_slices`;
    without it they can never see a parsed Dockerfile. Mirrors the
    ``cve``/``sbom`` ``_write_files`` precedent — the file is written on
    every ``run()`` (parsed and marker-absent alike) so consumers can tell
    "dockerfile probe ran, found nothing" from "upstream never ran".
    """
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    slice_path = rd / _SLICE_FILENAME
    slice_path.write_text(json.dumps(schema_slice, sort_keys=True))
    return [slice_path]


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
            schema_slice: dict[str, Any] = {
                "dockerfile": {"dockerfiles": [], "confidence": "unavailable"}
            }
            return ProbeOutput(
                schema_slice=schema_slice,
                raw_artifacts=_write_files(repo.root, schema_slice),
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
        schema_slice = _slice_for(parsed_dump)
        return ProbeOutput(
            schema_slice=schema_slice,
            raw_artifacts=_write_files(repo.root, schema_slice),
            confidence="high",
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
