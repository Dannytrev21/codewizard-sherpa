"""``ADRProbe`` (S6-03) — Layer D, light. Indexes ADR markdown headings only."""

from __future__ import annotations

import itertools
import os
import re
import time
from collections.abc import Iterable, Sized
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["ADRProbe", "Adr", "AdrsSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("adrs")
_LOCATIONS: Final[tuple[str, ...]] = ("docs/adr", "docs/architecture", "docs/decisions")
_ID_RE: Final = re.compile(r"^(?:ADR-|adr-)?(\d+)")
_TITLE_RE: Final = re.compile(r"^(?:ADR-|adr-)?\d+[.:]\s*")
_STATUS_RE: Final = re.compile(r"^[Ss]tatus:\s*(\w+)")
_ADR_STATUSES: Final[frozenset[str]] = frozenset(
    {"proposed", "accepted", "deprecated", "superseded"}
)
_REASON_NO_H1: Final[str] = "no_h1"
_REASON_ADR_DIRS_ABSENT: Final[str] = "adr_dirs_absent"
AdrStatus = Literal["proposed", "accepted", "deprecated", "superseded", "unknown"]


class Adr(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    title: str
    status: AdrStatus
    path: str


class AdrsSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    adrs: tuple[Adr, ...]
    scanned_locations: tuple[str, ...]
    per_file_errors: tuple[str, ...]


def _parse_adr_text(lines: Iterable[str], filename_stem: str) -> tuple[str, str, AdrStatus]:
    """Extract ``(id, title, status)`` from a bounded line iter (pure)."""
    title = ""
    status: AdrStatus = "unknown"
    m_id = _ID_RE.match(filename_stem)
    adr_id = m_id.group(1) if m_id else filename_stem
    for line in lines:
        if not title and line.startswith("# "):
            title = _TITLE_RE.sub("", line[2:].strip())
        m = _STATUS_RE.match(line)
        if m and m.group(1).lower() in _ADR_STATUSES:
            status = m.group(1).lower()  # type: ignore[assignment]
    return adr_id, title, status


def _compute_confidence(items: Sized, errors: Sized) -> Literal["high", "medium", "low"]:
    if len(errors) == 0:
        return "high"
    return "medium" if len(items) > 0 else "low"


def _scan_dir(repo_root: Path, loc: str) -> tuple[list[Adr], list[str]]:
    adrs: list[Adr] = []
    errors: list[str] = []
    for md in sorted((repo_root / loc).glob("*.md")):
        with open(md, encoding="utf-8", errors="replace") as fh:  # noqa: PTH123
            adr_id, title, status = _parse_adr_text(itertools.islice(fh, 50), md.stem)
        if not title:
            errors.append(_REASON_NO_H1)
        rel = md.relative_to(repo_root).as_posix()
        adrs.append(Adr(id=adr_id, title=title, status=status, path=rel))
    return adrs, errors


@register_probe(heaviness="light")
class ADRProbe(Probe):
    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [f"adr_search_path:{loc}" for loc in _LOCATIONS]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        adrs: list[Adr] = []
        scanned: list[str] = []
        errors: list[str] = []
        for loc in _LOCATIONS:
            if not (repo.root / loc).exists():
                continue
            scanned.append(loc)
            a, e = _scan_dir(repo.root, loc)
            adrs.extend(a)
            errors.extend(e)
        if not scanned:
            errors.append(_REASON_ADR_DIRS_ABSENT)
        adrs.sort(key=lambda a: (a.id, a.path))
        slice_ = AdrsSlice(
            adrs=tuple(adrs), scanned_locations=tuple(scanned), per_file_errors=tuple(errors)
        )
        raw = ctx.output_dir / f"{_PROBE_ID}.json"
        tmp = raw.with_suffix(".tmp")
        tmp.write_text(slice_.model_dump_json())
        os.replace(tmp, raw)
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw],
            confidence=_compute_confidence(adrs, errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
