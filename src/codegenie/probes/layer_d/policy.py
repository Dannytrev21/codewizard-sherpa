"""``PolicyProbe`` (S6-03) — Layer D, light. Reads ``~/.codegenie/config.yaml``'s
``policy_repos:`` declaration (paths only; the probe never opens the policy bodies).
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

__all__ = ["PolicyProbe", "PolicyRepoRef", "PolicySlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("policy")
_CONFIG_REL: Final[str] = ".codegenie/config.yaml"
_MAX_BYTES: Final[int] = 65536
_REASON_ABSENT: Final[str] = "policy_config_absent"
_REASON_MALFORMED: Final[str] = "policy_config_malformed"
_REASON_NOT_LIST: Final[str] = "policy_repos_not_list"


class PolicyRepoRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    type: str
    exists_on_disk: bool


class PolicySlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_repos: tuple[PolicyRepoRef, ...]
    per_file_errors: tuple[str, ...]


def _compute_confidence(items: Sized, errors: Sized) -> Literal["high", "medium", "low"]:
    if len(errors) == 0:
        return "high"
    return "medium" if len(items) > 0 else "low"


def _project(raw_entries: list[object]) -> list[PolicyRepoRef]:
    refs: list[PolicyRepoRef] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        path_val = entry.get("path")
        if not isinstance(path_val, str):
            continue
        type_val = entry.get("type", "unknown")
        refs.append(
            PolicyRepoRef(
                path=path_val,
                type=str(type_val),
                exists_on_disk=Path(path_val).expanduser().exists(),
            )
        )
    return refs


@register_probe(heaviness="light")
class PolicyProbe(Probe):
    name: str = str(_PROBE_ID)
    version: str = "0.1.0"
    layer: Literal["D"] = "D"
    tier: Literal["base"] = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [f"policy_user_config:{_CONFIG_REL}"]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        home = Path(ctx.config.get("policy.user_home", "~")).expanduser()
        config_path = home / _CONFIG_REL
        refs: list[PolicyRepoRef] = []
        errors: list[str] = []
        if not config_path.exists():
            errors.append(_REASON_ABSENT)
        else:
            try:
                data = safe_yaml.load(config_path, max_bytes=_MAX_BYTES, max_depth=8)
                raw = data.get("policy_repos", [])
                if not isinstance(raw, list):
                    errors.append(_REASON_NOT_LIST)
                else:
                    refs = _project(list(raw))
                    refs.sort(key=lambda r: r.path)
            except (MalformedYAMLError, DepthCapExceeded, SizeCapExceeded):
                errors.append(_REASON_MALFORMED)
        slice_ = PolicySlice(policy_repos=tuple(refs), per_file_errors=tuple(errors))
        raw_path = ctx.output_dir / f"{_PROBE_ID}.json"
        tmp = raw_path.with_suffix(".tmp")
        tmp.write_text(slice_.model_dump_json())
        os.replace(tmp, raw_path)
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw_path],
            confidence=_compute_confidence(refs, errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
