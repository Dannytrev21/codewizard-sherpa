"""``ExceptionProbe`` (S6-03) — Layer D, light. Reads ``.codegenie/exceptions.yaml``
(repo + user); partitions entries into ``active`` / ``expired`` against today's UTC date.
"""

from __future__ import annotations

import fnmatch
import os
import time
from collections.abc import Iterable, Sized
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from codegenie.errors import DepthCapExceeded, MalformedYAMLError, SizeCapExceeded
from codegenie.parsers import safe_yaml
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["ExceptionEntry", "ExceptionProbe", "ExceptionsSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("exceptions")
_REPO_REL: Final[str] = ".codegenie/exceptions.yaml"
_USER_REL: Final[str] = ".codegenie/exceptions.yaml"
_MAX_BYTES: Final[int] = 65536
_REASON_ABSENT: Final[str] = "exceptions_files_absent"
_REASON_NOT_MAPPING: Final[str] = "exceptions_yaml_not_mapping"
_REASON_MALFORMED_ENTRY: Final[str] = "exceptions_malformed_entry"


class ExceptionEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    repo_glob: str
    task: str
    reason: str
    expires: date
    approver: str


class ExceptionsSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    active: tuple[ExceptionEntry, ...]
    expired: tuple[ExceptionEntry, ...]
    per_file_errors: tuple[str, ...]

    @model_validator(mode="after")
    def _disjoint_partitions(self) -> ExceptionsSlice:
        active_ids = {(e.repo_glob, e.task, e.expires) for e in self.active}
        expired_ids = {(e.repo_glob, e.task, e.expires) for e in self.expired}
        overlap = active_ids & expired_ids
        if overlap:
            raise ValueError(f"active/expired must be disjoint; overlap={overlap!r}")
        return self


def _compute_confidence(items: Sized, errors: Sized) -> Literal["high", "medium", "low"]:
    if len(errors) == 0:
        return "high"
    return "medium" if len(items) > 0 else "low"


def _match_repo_glob(repo_name: str, repo_glob: str) -> bool:
    return fnmatch.fnmatchcase(repo_name, repo_glob)


def _partition_by_expiry(
    entries: Iterable[ExceptionEntry], now: date
) -> tuple[tuple[ExceptionEntry, ...], tuple[ExceptionEntry, ...]]:
    active: list[ExceptionEntry] = []
    expired: list[ExceptionEntry] = []
    for e in entries:
        (active if e.expires >= now else expired).append(e)
    return tuple(active), tuple(expired)


def _parse_entries(payload: object, errors: list[str]) -> list[ExceptionEntry]:
    if not isinstance(payload, dict) or not isinstance(payload.get("exceptions"), list):
        errors.append(_REASON_NOT_MAPPING)
        return []
    out: list[ExceptionEntry] = []
    for raw in payload["exceptions"]:
        try:
            out.append(ExceptionEntry.model_validate(raw))
        except (ValidationError, ValueError, TypeError):
            errors.append(_REASON_MALFORMED_ENTRY)
    return out


def _load_one(path: Path, errors: list[str]) -> list[ExceptionEntry]:
    if not path.exists():
        return []
    try:
        data = safe_yaml.load(path, max_bytes=_MAX_BYTES, max_depth=8)
    except (MalformedYAMLError, DepthCapExceeded, SizeCapExceeded):
        errors.append(_REASON_NOT_MAPPING)
        return []
    return _parse_entries(data, errors)


@register_probe(heaviness="light")
class ExceptionProbe(Probe):
    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        f"exceptions_repo:{_REPO_REL}",
        f"exceptions_user:{_USER_REL}",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        repo_path = repo.root / _REPO_REL
        user_home = Path(ctx.config.get("exceptions.user_home", "~")).expanduser()
        user_path = user_home / _USER_REL
        errors: list[str] = []
        if not repo_path.exists() and not user_path.exists():
            errors.append(_REASON_ABSENT)
            slice_ = ExceptionsSlice(active=(), expired=(), per_file_errors=tuple(errors))
        else:
            merged = _load_one(user_path, errors) + _load_one(repo_path, errors)
            filtered = [e for e in merged if _match_repo_glob(repo.root.name, e.repo_glob)]
            active, expired = _partition_by_expiry(filtered, now=datetime.now(tz=UTC).date())
            sort_key = lambda e: (e.repo_glob, e.task, e.expires)  # noqa: E731
            slice_ = ExceptionsSlice(
                active=tuple(sorted(active, key=sort_key)),
                expired=tuple(sorted(expired, key=sort_key)),
                per_file_errors=tuple(errors),
            )
        raw_path = ctx.output_dir / f"{_PROBE_ID}.json"
        tmp = raw_path.with_suffix(".tmp")
        tmp.write_text(slice_.model_dump_json())
        os.replace(tmp, raw_path)
        items = list(slice_.active) + list(slice_.expired)
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw_path],
            confidence=_compute_confidence(items, errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
