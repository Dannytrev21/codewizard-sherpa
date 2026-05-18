"""``RepoNotesProbe`` (S6-03) — Layer D, light. Indexes ``.codegenie/notes/`` headings."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Sized
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["NoteFile", "RepoNotesProbe", "RepoNotesSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("repo_notes")
_NOTES_DIR: Final[str] = ".codegenie/notes"
_LINE_BYTE_CAP: Final[int] = 4096
_REASON_LINE_EXCEEDS_CAP: Final[str] = "note_line_exceeds_cap"
_REASON_NOTES_DIR_ABSENT: Final[str] = "repo_notes_dir_absent"


class NoteFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    headings: tuple[str, ...]
    byte_count: int
    last_modified: str


class RepoNotesSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    notes_dir: str | None
    files: tuple[NoteFile, ...]
    per_file_errors: tuple[str, ...]


def _collect_headings(line_bytes_iter: Iterable[bytes]) -> tuple[str, ...]:
    """Pure helper: decode bounded line-bytes and emit ``^#+ `` headings."""
    headings: list[str] = []
    for raw in line_bytes_iter:
        if len(raw) > _LINE_BYTE_CAP:
            continue
        line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
        i = 0
        while i < len(line) and line[i] == "#":
            i += 1
        if i > 0 and i < len(line) and line[i] == " ":
            headings.append(line)
    return tuple(headings)


def _read_note(path: Path) -> tuple[tuple[str, ...], bool]:
    """Stream a note file line-by-line, returning ``(headings, line_cap_breached)``."""
    breach = False
    with open(path, "rb") as fh:  # noqa: PTH123
        lines: list[bytes] = []
        for raw in fh:
            if len(raw) > _LINE_BYTE_CAP:
                breach = True
                continue
            lines.append(raw)
    return _collect_headings(iter(lines)), breach


def _compute_confidence(items: Sized, errors: Sized) -> Literal["high", "medium", "low"]:
    if len(errors) == 0:
        return "high"
    return "medium" if len(items) > 0 else "low"


@register_probe(heaviness="light")
class RepoNotesProbe(Probe):
    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [f"repo_notes_path:{_NOTES_DIR}"]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        notes_dir = repo.root / _NOTES_DIR
        files: list[NoteFile] = []
        errors: list[str] = []
        if not notes_dir.exists():
            slice_ = RepoNotesSlice(
                notes_dir=None, files=(), per_file_errors=(_REASON_NOTES_DIR_ABSENT,)
            )
            return _emit(slice_, ctx, t0, items=files, errors=(_REASON_NOTES_DIR_ABSENT,))
        for md in sorted(notes_dir.rglob("*.md")):
            headings, breached = _read_note(md)
            if breached:
                errors.append(_REASON_LINE_EXCEEDS_CAP)
            st = md.stat()
            files.append(
                NoteFile(
                    path=md.relative_to(repo.root).as_posix(),
                    headings=headings,
                    byte_count=st.st_size,
                    last_modified=datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
                )
            )
        files.sort(key=lambda f: f.path)
        slice_ = RepoNotesSlice(
            notes_dir=_NOTES_DIR, files=tuple(files), per_file_errors=tuple(errors)
        )
        return _emit(slice_, ctx, t0, items=files, errors=errors)


def _emit(
    slice_: RepoNotesSlice, ctx: ProbeContext, t0: float, *, items: Sized, errors: Sized
) -> ProbeOutput:
    raw = ctx.output_dir / f"{_PROBE_ID}.json"
    tmp = raw.with_suffix(".tmp")
    tmp.write_text(slice_.model_dump_json())
    os.replace(tmp, raw)
    return ProbeOutput(
        schema_slice=slice_.model_dump(mode="json"),
        raw_artifacts=[raw],
        confidence=_compute_confidence(items, errors),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        warnings=[],
        errors=[],
    )
