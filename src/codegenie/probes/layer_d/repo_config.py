"""``RepoConfigProbe`` (S6-03) — Layer D, light. Indexes ``AGENTS.md`` / ``CLAUDE.md`` /
``.github/copilot-instructions.md`` frontmatter keys only; bodies are never decoded.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sized
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.errors import DepthCapExceeded, MalformedYAMLError, SizeCapExceeded
from codegenie.parsers import safe_yaml
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["RepoConfigFile", "RepoConfigProbe", "RepoConfigSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("repo_config")
_MARKERS: Final[tuple[str, ...]] = ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md")
_DEFAULT_MAX_BYTES: Final[int] = 65536
_FRONTMATTER_MAX_BYTES: Final[int] = 8192
_REASON_MARKERS_ABSENT: Final[str] = "repo_config_markers_absent"
_REASON_MALFORMED: Final[str] = "frontmatter_malformed"
_REASON_FILE_EXCEEDS_CAP: Final[str] = "file_exceeds_cap"


class RepoConfigFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    frontmatter_keys: tuple[str, ...]
    has_body: bool
    body_byte_offset: int


class RepoConfigSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    files: tuple[RepoConfigFile, ...]
    per_file_errors: tuple[str, ...]


def _extract_frontmatter_block(file_bytes: bytes) -> tuple[bytes | None, int]:
    """Pure helper: split first ``---`` / ``---`` fenced block. Returns
    ``(frontmatter_bytes, body_byte_offset)`` or ``(None, 0)`` if no closed block."""
    if not file_bytes.startswith(b"---\n") and not file_bytes.startswith(b"---\r\n"):
        return None, 0
    first_end = file_bytes.index(b"\n") + 1
    rest = file_bytes[first_end:]
    fence = b"\n---\n"
    fence_crlf = b"\r\n---\r\n"
    fence_mixed = b"\n---\r\n"
    for sep in (fence, fence_mixed, fence_crlf):
        idx = rest.find(sep)
        if idx != -1:
            return rest[: idx + 1], first_end + idx + len(sep)
    return None, 0


def _compute_confidence(items: Sized, errors: Sized) -> Literal["high", "medium", "low"]:
    if len(errors) == 0:
        return "high"
    return "medium" if len(items) > 0 else "low"


def _parse_one(
    path: Path, repo_root: Path, max_bytes: int
) -> tuple[RepoConfigFile | None, list[str]]:
    errs: list[str] = []
    with open(path, "rb") as fh:  # noqa: PTH123
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        errs.append(_REASON_FILE_EXCEEDS_CAP)
        return None, errs
    fm, off = _extract_frontmatter_block(data)
    keys: tuple[str, ...] = ()
    if fm is not None:
        try:
            parsed = safe_yaml.loads(fm, max_bytes=_FRONTMATTER_MAX_BYTES, max_depth=8)
            keys = tuple(sorted(parsed.keys()))
        except (MalformedYAMLError, DepthCapExceeded, SizeCapExceeded):
            errs.append(_REASON_MALFORMED)
    has_body = off < len(data) if fm is not None else len(data) > 0
    return (
        RepoConfigFile(
            path=path.relative_to(repo_root).as_posix(),
            frontmatter_keys=keys,
            has_body=has_body,
            body_byte_offset=off,
        ),
        errs,
    )


@register_probe(heaviness="light")
class RepoConfigProbe(Probe):
    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [f"repo_config_marker:{m}" for m in _MARKERS]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        max_bytes = int(ctx.config.get("repo_config.max_bytes", _DEFAULT_MAX_BYTES))
        files: list[RepoConfigFile] = []
        errors: list[str] = []
        for marker in _MARKERS:
            path = repo.root / marker
            if not path.exists():
                continue
            f, errs = _parse_one(path, repo.root, max_bytes)
            errors.extend(errs)
            if f is not None:
                files.append(f)
        if not files and not errors:
            errors.append(_REASON_MARKERS_ABSENT)
        files.sort(key=lambda f: f.path)
        slice_ = RepoConfigSlice(files=tuple(files), per_file_errors=tuple(errors))
        raw = ctx.output_dir / f"{_PROBE_ID}.json"
        tmp = raw.with_suffix(".tmp")
        tmp.write_text(slice_.model_dump_json())
        os.replace(tmp, raw)
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw],
            confidence=_compute_confidence(files, errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
